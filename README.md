# README.md

# Hybrid Search Engine

A from-scratch search engine that combines old-school keyword matching
(BM25) with modern semantic embeddings (sentence-transformers + FAISS) into
a single ranked result list. You pick how much each method contributes at
query time with a single `alpha` parameter — no reindexing, no restarting.
Built on FastAPI, logged to SQLite, visualised in Streamlit. Everything
starts with one command.

---

## Quickstart
```bash
git clone https://github.com/mohitjain2306/hybridsearch.git
cd hybrid-search

cp .env.example .env

bash up.sh
```

That's it. `up.sh` will:

1. Create a `.venv` and install dependencies (CPU-only torch, no CUDA)
2. Initialise the SQLite database
3. Fetch ~300 Wikipedia articles across 12 topic categories
4. Build the BM25 index and the FAISS vector index
5. Generate ground-truth relevance judgments for 25 queries
6. Run evaluation across 5 alpha values and save `experiments.csv`
7. Start the API and wait for it to pass a health check
8. Start the Streamlit dashboard

Second run skips every step that already has output on disk.

**When it's ready:**

| What | URL |
|---|---|
| Dashboard | http://localhost:8501 |
| API | http://localhost:8000 |
| Swagger UI | http://localhost:8000/docs |
| Prometheus metrics | http://localhost:8000/api/v1/metrics |

Stop everything with `Ctrl+C` — both servers shut down cleanly.

---

## API Endpoints

### `GET /health`

Is the system up and are the indexes loaded?
```bash
curl http://localhost:8000/health
```
```json
{
  "status":               "ok",
  "version":              "1.0.0",
  "git_commit":           "a3f91bc",
  "indexes_loaded":       true,
  "total_queries_served": 142
}
```

If `indexes_loaded` is `false`, run `python -m scripts.build_index` from
`backend/` and restart the API.

---

### `POST /api/v1/search`

The main event. Send a query, get ranked results with per-result score
breakdown.
```bash
curl -X POST http://localhost:8000/api/v1/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "NASA space exploration missions",
    "alpha": 0.5,
    "top_k": 3,
    "filters": { "category": "space" }
  }'
```
```json
{
  "request_id":   "3f2a1b4c-9e8d-4a2b-b1c0-7f6e5d4c3b2a",
  "query":        "NASA space exploration missions",
  "alpha":        0.5,
  "top_k":        3,
  "result_count": 3,
  "latency_ms":   38.4,
  "results": [
    {
      "doc_id":       "doc_0001_ab12cd34",
      "title":        "Space Shuttle",
      "chunk_index":  0,
      "snippet":      "…**NASA** engineers monitored the **spacecraft** systems…",
      "category":     "space",
      "bm25_score":   0.9100,
      "vector_score": 0.8541,
      "score":        0.8821
    },
    {
      "doc_id":       "doc_0004_cd34ef56",
      "title":        "Apollo 11",
      "chunk_index":  0,
      "snippet":      "…the first crewed **mission** to land on the Moon…",
      "category":     "space",
      "bm25_score":   0.7300,
      "vector_score": 0.8901,
      "score":        0.8101
    },
    {
      "doc_id":       "doc_0009_gh78ij90",
      "title":        "International Space Station",
      "chunk_index":  0,
      "snippet":      "…**NASA** and partner agencies maintain a continuous…",
      "category":     "space",
      "bm25_score":   0.6800,
      "vector_score": 0.7200,
      "score":        0.7000
    }
  ]
}
```

**Alpha guide:**

| Alpha | Behaviour |
|---|---|
| `1.0` | Pure BM25 — exact keyword match, fast, literal |
| `0.5` | Balanced — usually the best starting point |
| `0.0` | Pure vector — semantic, handles synonyms and paraphrases |

**Filters:** pass `"filters": { "category": "space" }` to restrict results
to one of: `space medicine technology science history geography economics
sports culture nature society general`.

---

### `GET /api/v1/metrics`

Prometheus-compatible plain text. Wire this up to a Prometheus scraper or
just curl it to see live counters.
```bash
curl http://localhost:8000/api/v1/metrics
```
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

### `GET /api/v1/stats`

Aggregated query statistics for the dashboard.
```bash
curl http://localhost:8000/api/v1/stats
```
```json
{
  "total_queries":  412,
  "avg_latency_ms": 38.7,
  "avg_alpha":      0.51,
  "recent_logs": [
    {
      "id":           42,
      "request_id":   "3f2a1b4c-...",
      "timestamp":    "2024-01-15T10:23:41+00:00",
      "query":        "black holes gravitational waves",
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

## Running Tests
```bash
cd backend
pytest tests/ -v
```

Run a specific test file:
```bash
pytest tests/test_bm25.py -v
pytest tests/test_hybrid.py -v
pytest tests/test_api.py -v
```

Run with coverage:
```bash
pytest tests/ --cov=app --cov-report=term-missing
```

The test suite uses a small three-document corpus (space / hockey /
medicine) so it runs in seconds without touching any real indexes or the
network. Disk I/O tests use `pytest`'s `tmp_path` fixture — nothing
written to your working tree.

---

## Evaluation

Generate relevance judgments (only needed once after ingest):
```bash
cd backend
python -m app.generate_qrels
```

Run the evaluation sweep across five alpha values:
```bash
python -m app.eval
```

Or target specific alphas and a different cutoff:
```bash
python -m app.eval --alphas 0.0 0.25 0.5 0.75 1.0 --k 10
```

Sample output:
```
──────────────────────────────────────────────────────────
       alpha     nDCG@10    Recall@10         MRR
──────────────────────────────────────────────────────────
        0.00      0.3821       0.2900      0.4102
        0.25      0.4103       0.3200      0.4418
        0.50      0.4387       0.3500      0.4731
        0.75      0.4201       0.3300      0.4523
        1.00      0.3644       0.2700      0.3899
──────────────────────────────────────────────────────────

Best nDCG@10:    alpha=0.50  (0.4387)
Best Recall@10:  alpha=0.50  (0.3500)
Best MRR:        alpha=0.50  (0.4731)
```

Results are saved to `data/metrics/experiments.csv`:
```
run,alpha,ndcg_at_k,recall_at_k,mrr,num_queries
1,0.0,0.3821,0.2900,0.4102,25
2,0.25,0.4103,0.3200,0.4418,25
3,0.5,0.4387,0.3500,0.4731,25
4,0.75,0.4201,0.3300,0.4523,25
5,1.0,0.3644,0.2700,0.3899,25
```

The dashboard Evaluation page reads this file directly and renders
the metric charts — no extra steps needed.

---

## SQLite Schema

Every search request is logged to `data/search_logs.db`, including failed
ones. The `error` column is null for successful queries.
```sql
CREATE TABLE schema_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE query_logs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id    TEXT    NOT NULL,   -- UUID linking log to API response
    timestamp     TEXT    NOT NULL,   -- ISO-8601 UTC
    query         TEXT    NOT NULL,   -- raw query string
    alpha         REAL    NOT NULL,   -- fusion weight used
    top_k         INTEGER NOT NULL,   -- results requested
    latency_ms    REAL    NOT NULL,   -- total request time in milliseconds
    result_count  INTEGER NOT NULL,   -- results actually returned
    filters       TEXT,               -- JSON-encoded filter dict or NULL
    error         TEXT                -- error message or NULL on success
);

CREATE INDEX idx_timestamp ON query_logs(timestamp);
CREATE INDEX idx_query     ON query_logs(query);
```

Inspect it directly:
```bash
sqlite3 data/search_logs.db "SELECT query, alpha, latency_ms, result_count FROM query_logs ORDER BY timestamp DESC LIMIT 10;"
```

---

## Hybrid Scoring

Each query fetches up to 30 candidates from BM25 and 30 from the vector
index independently. Their doc_id sets are unioned, then scores are
normalised and fused:
```
# 1. Fill missing scores with 0.0
#    (a doc that only appeared in BM25 gets vector_score = 0.0 and vice versa)

# 2. Min-max normalise each score space independently to [0, 1]

           score - min(scores)
norm  =  ─────────────────────
           max(scores) - min(scores)

# Special case: if all scores are equal (including all-zero from a
# nonsense query), return 0.5 for every document instead of NaN.

# 3. Fuse

hybrid = alpha × bm25_norm + (1 - alpha) × vector_norm
```

`alpha = 1.0` → pure BM25, ignores vector scores entirely.
`alpha = 0.0` → pure vector, ignores BM25 scores entirely.
`alpha = 0.5` → equal blend, usually the best default.

The final ranked list is sorted by `hybrid` score descending and truncated
to `top_k`. Each result carries all three scores (`bm25_score`,
`vector_score`, `score`) so you can see exactly why a document ranked
where it did.

---

## Project Structure
```
hybrid-search/
│
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app factory + lifespan
│   │   ├── dependencies.py      # get_search_engine(), get_db()
│   │   ├── models.py            # all Pydantic schemas
│   │   ├── db.py                # SQLite logging + migrations
│   │   ├── ingest.py            # Wikipedia fetch + cleaning
│   │   ├── eval.py              # nDCG / Recall / MRR harness
│   │   ├── generate_qrels.py    # ground-truth relevance judgments
│   │   │
│   │   ├── search/
│   │   │   ├── bm25.py          # BM25 index: build, save, load, query
│   │   │   ├── vector.py        # FAISS index: embed, build, save, load, query
│   │   │   └── hybrid.py        # score fusion + snippet highlighting
│   │   │
│   │   └── api/
│   │       ├── search.py        # POST /api/v1/search
│   │       ├── ingest.py        # POST /api/v1/ingest
│   │       └── stats.py         # GET  /api/v1/stats|logs|metrics|health
│   │
│   ├── scripts/
│   │   └── build_index.py       # ingest → BM25 + vector indexes
│   │
│   └── tests/
│       ├── conftest.py
│       ├── test_bm25.py
│       ├── test_vector.py
│       ├── test_hybrid.py
│       ├── test_ingest.py
│       └── test_api.py
│
├── frontend/
│   └── dashboard.py             # Streamlit: Search, KPIs, Eval, Debug Logs
│
├── data/                        # generated — gitignored
│   ├── raw/                     # drop .txt files here for custom docs
│   ├── processed/
│   │   └── docs.jsonl
│   ├── indexes/
│   │   ├── bm25/
│   │   │   ├── index.pkl
│   │   │   └── meta.json
│   │   └── vector/
│   │       ├── index.faiss
│   │       ├── meta.json
│   │       └── id_map.json
│   └── metrics/
│       └── experiments.csv
│
├── eval/
│   └── qrels.json
│
├── docs/
│   ├── architecture.md
│   ├── decisions.md
│   ├── api.md
│   └── evaluation.md
│
├── up.sh                        # start everything with one command
├── requirements.txt
├── .env.example
└── README.md
```

---

## What's not included

- **GPU support** — intentionally CPU-only. `torch` is installed from the
  CPU wheel index, `faiss-cpu` is pinned explicitly.
- **Authentication** — no API keys, no auth headers. Add FastAPI's
  `Security` dependency if you need it.
- **Persistent re-ingestion** — running `POST /ingest` overwrites
  `docs.jsonl`. Incremental updates would need a dedup step on `doc_id`.
- **Approximate nearest neighbours** — FAISS `IndexFlatIP` is exact search.
  Swap to `IndexIVFFlat` or `IndexHNSWFlat` if corpus size grows past ~50k
  documents and latency becomes a concern.