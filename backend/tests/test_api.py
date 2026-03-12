# backend/tests/test_api.py

import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

from app.models import SearchResult
from app.search.hybrid import HybridSearch


SPACE_TEXT = (
    "The space shuttle Columbia launched from Kennedy Space Center. "
    "Astronauts performed experiments in orbit around Earth."
)


def make_engine(results=None):
    engine = MagicMock(spec=HybridSearch)
    if results is None:
        results = [
            SearchResult(
                doc_id="doc_0001_aa111111",
                title="Space Shuttle",
                chunk_index=0,
                text=SPACE_TEXT,
                snippet="**NASA** space shuttle launched",
                category="space",
                score=0.9,
                bm25_score=0.85,
                vector_score=0.95,
            )
        ]
    engine.search.return_value = results
    return engine


def get_client(engine):
    from app.main import create_app
    from app import dependencies
    app = create_app()
    dependencies.set_search_engine(engine)
    return TestClient(app)


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------

def test_health_returns_ok():
    client = get_client(make_engine())
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["version"] == "1.0.0"
    assert "indexes_loaded" in data
    assert "git_commit" in data


def test_health_indexes_loaded_true_when_engine_set():
    client = get_client(make_engine())
    r = client.get("/api/v1/health")
    assert r.json()["indexes_loaded"] is True


# ---------------------------------------------------------------------------
# POST /search — happy path
# ---------------------------------------------------------------------------

def test_search_returns_200():
    client = get_client(make_engine())
    r = client.post("/api/v1/search", json={"query": "space shuttle"})
    assert r.status_code == 200


def test_search_response_has_required_fields():
    client = get_client(make_engine())
    r = client.post("/api/v1/search", json={"query": "space shuttle"})
    data = r.json()
    assert "request_id" in data
    assert "query" in data
    assert "results" in data
    assert "latency_ms" in data
    assert "result_count" in data


def test_search_result_has_score_breakdown():
    client = get_client(make_engine())
    r = client.post("/api/v1/search", json={"query": "space shuttle"})
    result = r.json()["results"][0]
    assert "bm25_score" in result
    assert "vector_score" in result
    assert "score" in result


def test_search_result_has_snippet():
    client = get_client(make_engine())
    r = client.post("/api/v1/search", json={"query": "space shuttle"})
    result = r.json()["results"][0]
    assert "snippet" in result
    assert result["snippet"] != ""


def test_search_result_count_matches_results_length():
    client = get_client(make_engine())
    r = client.post("/api/v1/search", json={"query": "space shuttle"})
    data = r.json()
    assert data["result_count"] == len(data["results"])


def test_search_respects_alpha_parameter():
    engine = make_engine()
    client = get_client(engine)
    client.post("/api/v1/search", json={"query": "space", "alpha": 0.75})
    call_args = engine.search.call_args[0][0]
    assert call_args.alpha == 0.75


def test_search_respects_top_k_parameter():
    engine = make_engine()
    client = get_client(engine)
    client.post("/api/v1/search", json={"query": "space", "top_k": 5})
    call_args = engine.search.call_args[0][0]
    assert call_args.top_k == 5


def test_search_respects_filters():
    engine = make_engine()
    client = get_client(engine)
    client.post(
        "/api/v1/search",
        json={"query": "space", "filters": {"category": "space"}},
    )
    call_args = engine.search.call_args[0][0]
    assert call_args.filters == {"category": "space"}


# ---------------------------------------------------------------------------
# POST /search — validation errors
# ---------------------------------------------------------------------------

def test_search_empty_query_returns_422():
    client = get_client(make_engine())
    r = client.post("/api/v1/search", json={"query": ""})
    assert r.status_code == 422


def test_search_alpha_out_of_range_returns_422():
    client = get_client(make_engine())
    r = client.post("/api/v1/search", json={"query": "test", "alpha": 1.5})
    assert r.status_code == 422


def test_search_top_k_zero_returns_422():
    client = get_client(make_engine())
    r = client.post("/api/v1/search", json={"query": "test", "top_k": 0})
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# POST /search — 503 when no engine loaded
# ---------------------------------------------------------------------------

def test_search_returns_503_when_indexes_not_loaded():
    from app.main import create_app
    from app import dependencies
    app = create_app()
    dependencies._search_engine = None
    client = TestClient(app, raise_server_exceptions=False)
    r = client.post("/api/v1/search", json={"query": "space"})
    assert r.status_code == 503


# ---------------------------------------------------------------------------
# GET /stats
# ---------------------------------------------------------------------------

def test_stats_returns_200():
    client = get_client(make_engine())
    r = client.get("/api/v1/stats")
    assert r.status_code == 200


def test_stats_has_required_fields():
    client = get_client(make_engine())
    r = client.get("/api/v1/stats")
    data = r.json()
    assert "total_queries" in data
    assert "avg_latency_ms" in data
    assert "avg_alpha" in data
    assert "recent_logs" in data


# ---------------------------------------------------------------------------
# GET /metrics
# ---------------------------------------------------------------------------

def test_metrics_returns_200():
    client = get_client(make_engine())
    r = client.get("/api/v1/metrics")
    assert r.status_code == 200


def test_metrics_contains_prometheus_counters():
    client = get_client(make_engine())
    r = client.get("/api/v1/metrics")
    text = r.text
    assert "search_requests_total" in text
    assert "search_latency_p50_ms" in text
    assert "search_latency_p95_ms" in text
