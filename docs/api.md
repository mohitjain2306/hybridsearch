# docs/api.md

# API Reference

Base URL: `http://localhost:8000`
All search and data endpoints are prefixed with `/api/v1`.

---

## POST /api/v1/search

Run a hybrid search query.

**Request body**
```json
{
  "query":   "NASA space exploration missions",
  "alpha":   0.5,
  "top_k":   10,
  "filters": { "category": "space" }
}
```

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `query` | string | yes | — | 1–512 characters |
| `alpha` | float | no | 0.5 | 0.0 = pure vector, 1.0 = pure BM25 |
| `top_k` | int | no | 10 | 1–100 |
| `filters` | object | no | null | Supported key: `category` |

**Response**
```json
{
  "request_id":   "3f2a1b4c-...",
  "query":        "NASA space exploration missions",
  "alpha":        0.5,
  "top_k":        10,
  "result_count": 10,
  "latency_ms":   42.3,
  "results": [
    {
      "doc_id":       "doc_0001_ab12cd34",
      "title":        "Space Shuttle",
      "chunk_index":  0,
      "text":         "...",
      "snippet":      "…**NASA** **space** exploration began…",
      "category":     "space",
      "score":        0.8821,
      "bm25_score":   0.9100,
      "vector_score": 0.8541
    }
  ]
}
```

**Error responses**

| Status | Condition |
|---|---|
| 422 | Request validation failed (e.g. alpha out of range) |
| 503 | Indexes not loaded — run `build_index.py` and restart |
| 429 | Rate limit exceeded (100 req/min per IP) |

---

## POST /api/v1/ingest

Trigger the ingest pipeline. Fetches Wikipedia articles for the specified
topic categories, cleans them, and overwrites `data/processed/docs.jsonl`.

**Request body**
```json
{
  "topics":       ["space", "medicine", "technology"],
  "max_articles": 50,
  "chunk_size":   200,
  "chunk_overlap": 20
}
```

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `topics` | list[string] | yes | — | Must match category names in `CATEGORIES` |
| `max_articles` | int | no | 50 | 1–500 |
| `chunk_size` | int | no | 200 | 50–1000 words |
| `chunk_overlap` | int | no | 20 | 0–100 words |

**Response**
```json
{
  "articles_fetched": 147,
  "chunks_created":   147,
  "duration_s":       38.2
}
```

> **Note:** After ingesting you must rebuild indexes by calling
> `python -m scripts.build_index` and restarting the API for changes to
> take effect.

---

## GET /api/v1/stats

Return aggregated query statistics.

**Response**
```json
{
  "total_queries":  412,
  "avg_latency_ms": 38.7,
  "avg_alpha":      0.51,
  "recent_logs": [ ... ]
}
```

---

## GET /api/v1/logs

Return recent query logs.

**Query parameters**

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `limit` | int | 100 | 1–1000 |

**Response**
```json
{
  "count": 100,
  "logs": [
    {
      "id":           42,
      "request_id":   "3f2a1b4c-...",
      "timestamp":    "2024-01-15T10:23:41+00:00",
      "query":        "black holes",
      "alpha":        0.5,
      "top_k":        10,
      "latency_ms":   35.1,
      "result_count": 10,
      "filters":      null,
      "error":        null
    }
  ]
}
```

---

## GET /api/v1/metrics

Prometheus-compatible plain text metrics.

**Response** (`text/plain`)
```
# HELP search_requests_total Total number of search requests
# TYPE search_requests_total counter
search_requests_total 412

# HELP search_zero_results_total Searches that returned no results
# TYPE search_zero_results_total counter
search_zero_results_total 3

# HELP search_latency_p50_ms 50th percentile search latency in ms
# TYPE search_latency_p50_ms gauge
search_latency_p50_ms 34.2

# HELP search_latency_p95_ms 95th percentile search latency in ms
# TYPE search_latency_p95_ms gauge
search_latency_p95_ms 89.7
```

---

## GET /api/v1/health

System health check. Used by `up.sh` during startup polling and by the
dashboard sidebar.

**Response**
```json
{
  "status":               "ok",
  "version":              "1.0.0",
  "git_commit":           "a3f91bc",
  "indexes_loaded":       true,
  "total_queries_served": 412
}
```

---

## Rate limiting

All endpoints are limited to **100 requests per minute per IP address**.
Exceeding this returns HTTP 429 with a `Retry-After` header.

## Running locally
```bash
# Start everything
bash up.sh

# API docs (Swagger UI)
open http://localhost:8000/docs

# ReDoc
open http://localhost:8000/redoc
```