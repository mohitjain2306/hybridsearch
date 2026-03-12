# backend/tests/test_hybrid.py

import pytest
from unittest.mock import MagicMock
from app.models import SearchRequest, SearchResult
from app.search.hybrid import HybridSearch, _minmax, _snippet


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_result(
    doc_id: str,
    title: str,
    text: str = "sample text",
    bm25_score: float = 0.0,
    vector_score: float = 0.0,
    category: str = "general",
) -> SearchResult:
    return SearchResult(
        doc_id=doc_id,
        title=title,
        chunk_index=0,
        text=text,
        snippet="",
        category=category,
        score=max(bm25_score, vector_score),
        bm25_score=bm25_score,
        vector_score=vector_score,
    )


def make_request(
    query: str = "test query",
    top_k: int = 10,
    alpha: float = 0.5,
    filters: dict | None = None,
) -> SearchRequest:
    return SearchRequest(query=query, top_k=top_k, alpha=alpha, filters=filters)


def make_hybrid(bm25_returns: list, vector_returns: list) -> HybridSearch:
    bm25   = MagicMock()
    vector = MagicMock()
    bm25.query.return_value   = bm25_returns
    vector.query.return_value = vector_returns
    bm25.__len__   = MagicMock(return_value=len(bm25_returns))
    vector.__len__ = MagicMock(return_value=len(vector_returns))
    return HybridSearch(bm25, vector)


# ---------------------------------------------------------------------------
# _minmax
# ---------------------------------------------------------------------------

def test_minmax_normalises_to_unit_range():
    result = _minmax({"a": 0.0, "b": 5.0, "c": 10.0})
    assert result["a"] == pytest.approx(0.0)
    assert result["b"] == pytest.approx(0.5)
    assert result["c"] == pytest.approx(1.0)


def test_minmax_all_equal_returns_half():
    """The NaN guard — all-equal scores must return 0.5, not NaN."""
    result = _minmax({"a": 0.0, "b": 0.0, "c": 0.0})
    assert all(v == pytest.approx(0.5) for v in result.values())


def test_minmax_all_zeros_returns_half():
    result = _minmax({"a": 0.0, "b": 0.0})
    assert result["a"] == pytest.approx(0.5)
    assert result["b"] == pytest.approx(0.5)


def test_minmax_single_entry_returns_half():
    result = _minmax({"only": 7.3})
    assert result["only"] == pytest.approx(0.5)


def test_minmax_empty_returns_empty():
    assert _minmax({}) == {}


def test_minmax_preserves_all_keys():
    scores = {"x": 1.0, "y": 2.0, "z": 3.0}
    result = _minmax(scores)
    assert set(result) == set(scores)


# ---------------------------------------------------------------------------
# _snippet
# ---------------------------------------------------------------------------

def test_snippet_highlights_matching_word():
    text = "The space shuttle launched successfully from Kennedy."
    result = _snippet(text, "space shuttle", window=60)
    assert "**space**" in result or "**Space**" in result
    assert "**shuttle**" in result or "**Shuttle**" in result


def test_snippet_is_case_insensitive():
    text = "SPACE exploration is amazing."
    result = _snippet(text, "space")
    assert "**SPACE**" in result


def test_snippet_falls_back_to_start_on_no_match():
    text = "Completely unrelated content about cooking pasta."
    result = _snippet(text, "quantum physics", window=30)
    assert len(result) <= 35             # window + possible ellipsis chars
    assert "**" not in result


def test_snippet_adds_ellipsis_when_truncated():
    text = "word " * 200                 # long text
    result = _snippet(text, "word", window=50)
    assert result.endswith("…")


def test_snippet_empty_text_returns_empty():
    assert _snippet("", "query") == ""


def test_snippet_respects_window_length():
    text = "alpha " * 100
    result = _snippet(text, "alpha", window=50)
    # strip markdown and ellipsis before measuring
    clean = result.replace("**", "").replace("…", "")
    assert len(clean) <= 55             # small tolerance for word boundaries


# ---------------------------------------------------------------------------
# HybridSearch.search — basic mechanics
# ---------------------------------------------------------------------------

def test_search_returns_list_of_search_results():
    bm25_r   = [make_result("d1", "Doc1", bm25_score=0.8)]
    vector_r = [make_result("d1", "Doc1", vector_score=0.9)]
    h = make_hybrid(bm25_r, vector_r)
    results = h.search(make_request())
    assert isinstance(results, list)
    assert all(isinstance(r, SearchResult) for r in results)


def test_search_deduplicates_by_doc_id():
    """Same doc appearing in both indexes should produce one result."""
    bm25_r   = [make_result("d1", "Doc1", bm25_score=0.8)]
    vector_r = [make_result("d1", "Doc1", vector_score=0.6)]
    h = make_hybrid(bm25_r, vector_r)
    results = h.search(make_request(top_k=10))
    ids = [r.doc_id for r in results]
    assert len(ids) == len(set(ids))


def test_search_union_includes_bm25_only_docs():
    bm25_r   = [make_result("bm25_only", "BM25 Doc", bm25_score=0.9)]
    vector_r = [make_result("vec_only",  "Vec Doc",  vector_score=0.9)]
    h = make_hybrid(bm25_r, vector_r)
    results = h.search(make_request(top_k=10))
    ids = {r.doc_id for r in results}
    assert "bm25_only" in ids
    assert "vec_only"  in ids


def test_search_top_k_respected():
    bm25_r   = [make_result(f"d{i}", f"Doc{i}", bm25_score=float(i)) for i in range(20)]
    vector_r = [make_result(f"d{i}", f"Doc{i}", vector_score=float(i)) for i in range(20)]
    h = make_hybrid(bm25_r, vector_r)
    results = h.search(make_request(top_k=5))
    assert len(results) == 5


def test_search_results_sorted_by_score_descending():
    bm25_r   = [make_result(f"d{i}", f"D{i}", bm25_score=float(i)) for i in range(5)]
    vector_r = [make_result(f"d{i}", f"D{i}", vector_score=float(i)) for i in range(5)]
    h = make_hybrid(bm25_r, vector_r)
    results = h.search(make_request(top_k=5))
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# Alpha semantics
# ---------------------------------------------------------------------------

def test_alpha_1_makes_hybrid_score_equal_bm25_score():
    """alpha=1.0 → pure BM25. hybrid score must equal normalised bm25_score."""
    bm25_r   = [
        make_result("d1", "Doc1", bm25_score=0.9),
        make_result("d2", "Doc2", bm25_score=0.4),
        make_result("d3", "Doc3", bm25_score=0.1),
    ]
    vector_r = [
        make_result("d1", "Doc1", vector_score=0.2),
        make_result("d2", "Doc2", vector_score=0.5),
        make_result("d3", "Doc3", vector_score=0.8),
    ]
    h = make_hybrid(bm25_r, vector_r)
    results = h.search(make_request(alpha=1.0, top_k=3))

    for r in results:
        assert r.score == pytest.approx(r.bm25_score, abs=1e-5)


def test_alpha_0_makes_hybrid_score_equal_vector_score():
    """alpha=0.0 → pure vector. hybrid score must equal normalised vector_score."""
    bm25_r   = [
        make_result("d1", "Doc1", bm25_score=0.9),
        make_result("d2", "Doc2", bm25_score=0.4),
        make_result("d3", "Doc3", bm25_score=0.1),
    ]
    vector_r = [
        make_result("d1", "Doc1", vector_score=0.2),
        make_result("d2", "Doc2", vector_score=0.5),
        make_result("d3", "Doc3", vector_score=0.8),
    ]
    h = make_hybrid(bm25_r, vector_r)
    results = h.search(make_request(alpha=0.0, top_k=3))

    for r in results:
        assert r.score == pytest.approx(r.vector_score, abs=1e-5)


def test_alpha_0_5_score_is_average_of_components():
    """At alpha=0.5 the fused score must be the mean of bm25 and vector scores."""
    bm25_r   = [make_result("d1", "Doc1", bm25_score=1.0)]
    vector_r = [make_result("d1", "Doc1", vector_score=1.0)]
    h = make_hybrid(bm25_r, vector_r)
    results = h.search(make_request(alpha=0.5, top_k=1))

    r = results[0]
    expected = 0.5 * r.bm25_score + 0.5 * r.vector_score
    assert r.score == pytest.approx(expected, abs=1e-5)


# ---------------------------------------------------------------------------
# NaN guard
# ---------------------------------------------------------------------------

def test_all_zero_bm25_scores_do_not_produce_nan():
    """Nonsense queries make BM25 return all-zero scores — must not NaN."""
    bm25_r = [
        make_result("d1", "Doc1", bm25_score=0.0),
        make_result("d2", "Doc2", bm25_score=0.0),
        make_result("d3", "Doc3", bm25_score=0.0),
    ]
    vector_r = [
        make_result("d1", "Doc1", vector_score=0.3),
        make_result("d2", "Doc2", vector_score=0.6),
        make_result("d3", "Doc3", vector_score=0.9),
    ]
    h = make_hybrid(bm25_r, vector_r)
    results = h.search(make_request(alpha=0.5, top_k=3))

    for r in results:
        assert r.score == r.score        # NaN != NaN
        assert r.bm25_score == pytest.approx(0.5)


def test_all_zero_vector_scores_do_not_produce_nan():
    bm25_r = [
        make_result("d1", "Doc1", bm25_score=0.3),
        make_result("d2", "Doc2", bm25_score=0.6),
        make_result("d3", "Doc3", bm25_score=0.9),
    ]
    vector_r = [
        make_result("d1", "Doc1", vector_score=0.0),
        make_result("d2", "Doc2", vector_score=0.0),
        make_result("d3", "Doc3", vector_score=0.0),
    ]
    h = make_hybrid(bm25_r, vector_r)
    results = h.search(make_request(alpha=0.5, top_k=3))

    for r in results:
        assert r.score == r.score
        assert r.vector_score == pytest.approx(0.5)


def test_both_indexes_all_zero_scores():
    """Absolute worst case — both indexes return all zeros."""
    bm25_r   = [make_result(f"d{i}", f"D{i}", bm25_score=0.0)   for i in range(3)]
    vector_r = [make_result(f"d{i}", f"D{i}", vector_score=0.0) for i in range(3)]
    h = make_hybrid(bm25_r, vector_r)
    results = h.search(make_request(alpha=0.5, top_k=3))

    for r in results:
        assert r.score == pytest.approx(0.5)
        assert r.bm25_score   == pytest.approx(0.5)
        assert r.vector_score == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_empty_bm25_returns_vector_only_results():
    bm25_r   = []
    vector_r = [make_result("v1", "Vec Doc", vector_score=0.8)]
    h = make_hybrid(bm25_r, vector_r)
    results = h.search(make_request(top_k=5))
    assert len(results) == 1
    assert results[0].doc_id == "v1"


def test_empty_vector_returns_bm25_only_results():
    bm25_r   = [make_result("b1", "BM25 Doc", bm25_score=0.8)]
    vector_r = []
    h = make_hybrid(bm25_r, vector_r)
    results = h.search(make_request(top_k=5))
    assert len(results) == 1
    assert results[0].doc_id == "b1"


def test_both_empty_returns_empty():
    h = make_hybrid([], [])
    assert h.search(make_request()) == []


def test_snippet_populated_in_results():
    bm25_r   = [make_result("d1", "Doc1", text="The space shuttle orbited Earth.", bm25_score=0.9)]
    vector_r = []
    h = make_hybrid(bm25_r, vector_r)
    results = h.search(make_request(query="space shuttle", top_k=1))
    assert results[0].snippet != ""
    assert "**" in results[0].snippet


def test_repr_contains_doc_counts():
    bm25   = MagicMock()
    vector = MagicMock()
    bm25.__len__   = MagicMock(return_value=100)
    vector.__len__ = MagicMock(return_value=100)
    h = HybridSearch(bm25, vector)
    assert "100" in repr(h)