# backend/tests/test_bm25.py

import pytest
from app.models import Document
from app.search.bm25 import BM25Index, tokenize


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SPACE_TEXT = (
    "The space shuttle Columbia launched from Kennedy Space Center. "
    "Astronauts performed experiments in orbit around Earth. "
    "NASA engineers monitored the spacecraft systems during the mission."
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
            doc_id="doc_0001_aa111111",
            title="Space Shuttle",
            chunk_index=0,
            text=SPACE_TEXT,
            token_count=len(SPACE_TEXT.split()),
            category="space",
        ),
        Document(
            doc_id="doc_0002_bb222222",
            title="Ice Hockey",
            chunk_index=0,
            text=HOCKEY_TEXT,
            token_count=len(HOCKEY_TEXT.split()),
            category="sports",
        ),
        Document(
            doc_id="doc_0003_cc333333",
            title="Penicillin",
            chunk_index=0,
            text=MEDICINE_TEXT,
            token_count=len(MEDICINE_TEXT.split()),
            category="medicine",
        ),
    ]


@pytest.fixture
def built_index(corpus) -> BM25Index:
    idx = BM25Index()
    idx.build(corpus)
    return idx


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------

def test_tokenize_lowercases():
    assert tokenize("Space Shuttle") == ["space", "shuttle"]


def test_tokenize_strips_punctuation():
    tokens = tokenize("NASA's rocket-launch!")
    assert "nasa" in tokens
    assert "rocket" in tokens
    assert "launch" in tokens


def test_tokenize_empty_string():
    assert tokenize("") == []


def test_tokenize_whitespace_only():
    assert tokenize("   ") == []


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def test_build_sets_is_built(corpus):
    idx = BM25Index()
    assert not idx._is_built
    idx.build(corpus)
    assert idx._is_built


def test_build_empty_corpus_raises():
    idx = BM25Index()
    with pytest.raises(ValueError, match="empty"):
        idx.build([])


def test_len_after_build(built_index, corpus):
    assert len(built_index) == len(corpus)


def test_repr_after_build(built_index):
    assert "3 docs" in repr(built_index)


def test_repr_before_build():
    assert "not built" in repr(BM25Index())


# ---------------------------------------------------------------------------
# Query — ranking correctness
# ---------------------------------------------------------------------------

def test_space_query_ranks_space_doc_first(built_index):
    results = built_index.query("space shuttle", top_k=3)
    assert results[0].doc_id == "doc_0001_aa111111"


def test_hockey_query_ranks_hockey_doc_first(built_index):
    results = built_index.query("ice hockey goal", top_k=3)
    assert results[0].doc_id == "doc_0002_bb222222"


def test_medicine_query_ranks_medicine_doc_first(built_index):
    results = built_index.query("antibiotic penicillin", top_k=3)
    assert results[0].doc_id == "doc_0003_cc333333"


# ---------------------------------------------------------------------------
# Query — scores
# ---------------------------------------------------------------------------

def test_scores_are_normalised(built_index):
    results = built_index.query("space shuttle", top_k=3)
    for r in results:
        assert 0.0 <= r.bm25_score <= 1.0
        assert 0.0 <= r.score <= 1.0


def test_vector_score_is_zero(built_index):
    """BM25Index never populates vector_score — hybrid.py handles that."""
    results = built_index.query("space shuttle", top_k=3)
    assert all(r.vector_score == 0.0 for r in results)


def test_top_k_respected(built_index):
    assert len(built_index.query("space", top_k=2)) == 2


def test_top_k_larger_than_corpus(built_index):
    results = built_index.query("space", top_k=100)
    assert len(results) <= 3


def test_results_are_sorted_descending(built_index):
    results = built_index.query("space shuttle NASA", top_k=3)
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# Query — filters
# ---------------------------------------------------------------------------

def test_category_filter_limits_results(built_index):
    results = built_index.query("space", top_k=10, filters={"category": "space"})
    assert all(r.category == "space" for r in results)
    assert len(results) == 1


def test_unknown_category_filter_returns_empty(built_index):
    results = built_index.query("space", top_k=10, filters={"category": "cooking"})
    assert results == []


def test_none_filter_returns_all(built_index):
    results = built_index.query("the", top_k=10, filters=None)
    assert len(results) == 3


# ---------------------------------------------------------------------------
# Persist — save / load roundtrip
# ---------------------------------------------------------------------------

def test_save_and_load_roundtrip(built_index, corpus, tmp_path):
    index_path = tmp_path / "bm25" / "index.pkl"
    meta_path  = tmp_path / "bm25" / "meta.json"

    built_index.save(index_path, meta_path)

    assert index_path.exists()
    assert meta_path.exists()

    loaded = BM25Index.load(index_path, meta_path)
    assert len(loaded) == len(corpus)


def test_load_missing_file_returns_false(tmp_path):
    result = BM25Index.load(tmp_path / "nonexistent.pkl")
    assert result is False


def test_loaded_index_ranks_correctly(built_index, tmp_path):
    index_path = tmp_path / "bm25" / "index.pkl"
    meta_path  = tmp_path / "bm25" / "meta.json"

    built_index.save(index_path, meta_path)
    loaded = BM25Index.load(index_path, meta_path)

    assert loaded is not False                         # guard before querying
    results = loaded.query("space shuttle", top_k=3)
    assert results[0].doc_id == "doc_0001_aa111111"

def test_save_before_build_raises(tmp_path):
    idx = BM25Index()
    with pytest.raises(RuntimeError, match="built"):
        idx.save(tmp_path / "index.pkl", tmp_path / "meta.json")


def test_query_before_build_raises():
    idx = BM25Index()
    with pytest.raises(RuntimeError, match="not built"):
        idx.query("anything")