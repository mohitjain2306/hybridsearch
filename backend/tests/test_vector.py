# backend/tests/test_vector.py

import json
import pytest
import numpy as np
from unittest.mock import patch, MagicMock

from app.models import Document, SearchResult
from app.search.vector import VectorIndex, DEFAULT_MODEL

# ---------------------------------------------------------------------------
# Shared corpus
# ---------------------------------------------------------------------------

SPACE_TEXT = (
    "The space shuttle Columbia launched from Kennedy Space Center. "
    "Astronauts performed experiments in orbit around Earth. "
    "NASA engineers monitored spacecraft systems during the mission."
)
HOCKEY_TEXT = (
    "The ice hockey team scored three goals in the final period. "
    "The goalie made several impressive saves throughout the game. "
    "Fans cheered as the puck crossed the line in overtime."
)
MEDICINE_TEXT = (
    "Penicillin was the first antibiotic discovered by Alexander Fleming. "
    "The drug revolutionised treatment of bacterial infections worldwide. "
    "Modern medicine relies heavily on antibiotics to fight disease."
)


@pytest.fixture
def corpus() -> list[Document]:
    return [
        Document(
            doc_id="doc_0001_aa111111", title="Space Shuttle",
            chunk_index=0, text=SPACE_TEXT,
            token_count=len(SPACE_TEXT.split()), category="space",
        ),
        Document(
            doc_id="doc_0002_bb222222", title="Ice Hockey",
            chunk_index=0, text=HOCKEY_TEXT,
            token_count=len(HOCKEY_TEXT.split()), category="sports",
        ),
        Document(
            doc_id="doc_0003_cc333333", title="Penicillin",
            chunk_index=0, text=MEDICINE_TEXT,
            token_count=len(MEDICINE_TEXT.split()), category="medicine",
        ),
    ]


@pytest.fixture
def built_index(corpus) -> VectorIndex:
    idx = VectorIndex()
    idx.build(corpus)
    return idx


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def test_build_sets_is_built(corpus):
    idx = VectorIndex()
    assert not idx._is_built
    idx.build(corpus)
    assert idx._is_built


def test_build_empty_corpus_raises():
    idx = VectorIndex()
    with pytest.raises(ValueError, match="empty"):
        idx.build([])


def test_build_sets_correct_dimension(built_index):
    # all-MiniLM-L6-v2 produces 384-dim embeddings
    assert built_index._dim == 384


def test_len_after_build(built_index, corpus):
    assert len(built_index) == len(corpus)


def test_repr_after_build(built_index):
    r = repr(built_index)
    assert "384" in r
    assert "all-MiniLM-L6-v2" in r


def test_repr_before_build():
    assert "not built" in repr(VectorIndex())


# ---------------------------------------------------------------------------
# Embeddings — L2 normalisation
# ---------------------------------------------------------------------------

def test_embeddings_are_unit_normalised(built_index):
    """Vectors stored in FAISS should all have L2 norm ≈ 1.0."""
    import faiss
    n = len(built_index)
    vecs = np.zeros((n, built_index._dim), dtype=np.float32)
    built_index._index.reconstruct_n(0, n, vecs)
    norms = np.linalg.norm(vecs, axis=1)
    np.testing.assert_allclose(norms, np.ones(n), atol=1e-5)


def test_scores_are_cosine_range(built_index):
    """IndexFlatIP on L2-normalised vectors returns cosine similarity ∈ [-1, 1]."""
    results = built_index.query("space shuttle", top_k=3)
    for r in results:
        assert -1.0 <= r.vector_score <= 1.0


# ---------------------------------------------------------------------------
# Query — ranking correctness
# ---------------------------------------------------------------------------

def test_space_query_ranks_space_doc_first(built_index):
    results = built_index.query("space shuttle NASA orbit", top_k=3)
    assert results[0].doc_id == "doc_0001_aa111111"


def test_hockey_query_ranks_hockey_doc_first(built_index):
    results = built_index.query("ice hockey goal puck", top_k=3)
    assert results[0].doc_id == "doc_0002_bb222222"


def test_medicine_query_ranks_medicine_doc_first(built_index):
    results = built_index.query("antibiotic penicillin bacteria", top_k=3)
    assert results[0].doc_id == "doc_0003_cc333333"


def test_results_sorted_descending(built_index):
    results = built_index.query("space shuttle", top_k=3)
    scores = [r.vector_score for r in results]
    assert scores == sorted(scores, reverse=True)


def test_top_k_respected(built_index):
    assert len(built_index.query("space", top_k=2)) == 2


def test_top_k_larger_than_corpus(built_index):
    results = built_index.query("space", top_k=100)
    assert len(results) <= 3


def test_bm25_score_is_zero(built_index):
    """VectorIndex never populates bm25_score — hybrid.py handles that."""
    results = built_index.query("space shuttle", top_k=3)
    assert all(r.bm25_score == 0.0 for r in results)


# ---------------------------------------------------------------------------
# Query — filters
# ---------------------------------------------------------------------------

def test_category_filter_limits_results(built_index):
    results = built_index.query("space", top_k=10, filters={"category": "space"})
    assert all(r.category == "space" for r in results)
    assert len(results) == 1


def test_unknown_category_returns_empty(built_index):
    results = built_index.query("space", top_k=10, filters={"category": "cooking"})
    assert results == []


def test_none_filter_returns_all(built_index):
    results = built_index.query("the", top_k=10, filters=None)
    assert len(results) == 3


# ---------------------------------------------------------------------------
# Persist — save / load roundtrip
# ---------------------------------------------------------------------------

def test_save_creates_all_files(built_index, tmp_path):
    ip = tmp_path / "vector" / "index.faiss"
    mp = tmp_path / "vector" / "meta.json"
    idp = tmp_path / "vector" / "id_map.json"

    built_index.save(ip, mp, idp)

    assert ip.exists()
    assert mp.exists()
    assert idp.exists()


def test_meta_json_contents(built_index, tmp_path):
    ip  = tmp_path / "v" / "index.faiss"
    mp  = tmp_path / "v" / "meta.json"
    idp = tmp_path / "v" / "id_map.json"

    built_index.save(ip, mp, idp)
    meta = json.loads(mp.read_text())

    assert meta["model_name"] == DEFAULT_MODEL
    assert meta["dimension"]  == 384
    assert meta["doc_count"]  == 3
    assert "corpus_hash" in meta
    assert "built_at"    in meta


def test_load_missing_index_returns_false(tmp_path):
    result = VectorIndex.load(tmp_path / "nope.faiss")
    assert result is False


def test_load_roundtrip_doc_count(built_index, tmp_path):
    ip  = tmp_path / "v" / "index.faiss"
    mp  = tmp_path / "v" / "meta.json"
    idp = tmp_path / "v" / "id_map.json"

    built_index.save(ip, mp, idp)
    loaded = VectorIndex.load(ip, mp, idp)

    assert loaded is not False
    assert len(loaded) == 3


def test_load_roundtrip_ranks_correctly(built_index, tmp_path):
    ip  = tmp_path / "v" / "index.faiss"
    mp  = tmp_path / "v" / "meta.json"
    idp = tmp_path / "v" / "id_map.json"

    built_index.save(ip, mp, idp)
    loaded = VectorIndex.load(ip, mp, idp)

    assert loaded is not False
    results = loaded.query("space shuttle NASA", top_k=3)
    assert results[0].doc_id == "doc_0001_aa111111"


# ---------------------------------------------------------------------------
# Persist — validation errors on load
# ---------------------------------------------------------------------------

def test_load_raises_on_model_mismatch(built_index, tmp_path):
    ip  = tmp_path / "v" / "index.faiss"
    mp  = tmp_path / "v" / "meta.json"
    idp = tmp_path / "v" / "id_map.json"

    built_index.save(ip, mp, idp)

    with pytest.raises(RuntimeError, match="Model mismatch"):
        VectorIndex.load(ip, mp, idp, model_name="all-mpnet-base-v2")


def test_load_raises_on_missing_meta(built_index, tmp_path):
    ip  = tmp_path / "v" / "index.faiss"
    mp  = tmp_path / "v" / "meta.json"
    idp = tmp_path / "v" / "id_map.json"

    built_index.save(ip, mp, idp)
    mp.unlink()                                  # simulate missing meta

    with pytest.raises(RuntimeError, match="meta.json is missing"):
        VectorIndex.load(ip, mp, idp)


def test_load_raises_on_missing_id_map(built_index, tmp_path):
    ip  = tmp_path / "v" / "index.faiss"
    mp  = tmp_path / "v" / "meta.json"
    idp = tmp_path / "v" / "id_map.json"

    built_index.save(ip, mp, idp)
    idp.unlink()                                 # simulate missing id_map

    with pytest.raises(RuntimeError, match="id_map.json not found"):
        VectorIndex.load(ip, mp, idp)


def test_load_raises_on_dimension_mismatch(built_index, tmp_path):
    ip  = tmp_path / "v" / "index.faiss"
    mp  = tmp_path / "v" / "meta.json"
    idp = tmp_path / "v" / "id_map.json"

    built_index.save(ip, mp, idp)

    # Tamper with meta to report a wrong dimension
    meta = json.loads(mp.read_text())
    meta["dimension"] = 999
    mp.write_text(json.dumps(meta))

    with pytest.raises(RuntimeError, match="Dimension mismatch"):
        VectorIndex.load(ip, mp, idp)


def test_save_before_build_raises(tmp_path):
    idx = VectorIndex()
    with pytest.raises(RuntimeError, match="built"):
        idx.save(tmp_path / "i.faiss", tmp_path / "m.json", tmp_path / "id.json")


def test_query_before_build_raises():
    with pytest.raises(RuntimeError, match="not built"):
        VectorIndex().query("anything")