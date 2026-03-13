# Hybrid Search Engine

A production-style search engine that combines BM25 (lexical) and sentence-transformers + FAISS (semantic) into a single ranked result list. The blend is controlled by a single `alpha` parameter at query time — no reindexing required. Built on FastAPI, logged to SQLite, visualised in Streamlit.

---

## Quickstart

```bash
git clone https://github.com/mohitjain2306/hybridsearch.git
cd hybridsearch
cp .env.example .env
./up.sh
```

`up.sh` will:
1. Create `.venv` and install CPU-only dependencies (no CUDA)
2. Initialise the SQLite database with migrations
3. Skip ingest + indexing if artifacts already exist (pre-built in repo)
4. Start the FastAPI backend and Streamlit dashboard
5. Print URLs when ready

On a fresh clone, startup takes under 2 minutes because the corpus and indexes are pre-committed.

| Service | URL |
|---|---|
| Dashboard | http://localhost:8501 |
| API | http://localhost:8000 |
| Swagger UI | http://localhost:8000/docs |
| Metrics | http://localhost:8000/api/v1/metrics |

Stop everything: `Ctrl+C` — both servers shut down cleanly.
Stop without Ctrl+C: `./down.sh`

---

## How to Run Tests

```bash
cd backend
source ../.venv/bin/activate
pytest tests/ -v
```

Run a specific file:
```bash
pytest tests/test_bm25.py -v
pytest tests/test_hybrid.py -v
pytest tests/test_api.py -v
pytest tests/test_ingest.py -v
pytest tests/test_vector.py -v
```

Run with coverage:
```bash
pytest tests/ --cov=app --cov-report=term-missing
```

The test suite uses an in-memory toy corpus (3 docs: space / hockey / medicine). No real indexes or network calls. All disk I/O uses `pytest`'s `tmp_path` fixture. **120 tests, ~80 seconds on CPU.**

---

## How to Run Evaluation

```bash
cd backend
source ../.venv/bin/activate

# Generate qrels (only needed if eval/qrels.json is missing)
python -m app.generate_qrels --docs ../data/processed/docs.jsonl --out ../eval/qrels.json

# Run sweep across 5 alpha values
python -m app.eval --qrels ../eval/qrels.json

# Custom alphas and cutoff
python -m app.eval --alphas 0.0 0.25 0.5 0.75 1.0 --k 10 --qrels ../eval/qrels.json
```

Results are appended to `data/metrics/experiments.csv` with timestamp and git commit:

```
run,alpha,ndcg_at_10,recall_at_10,mrr,num_queries,timestamp,git_commit
1,0.0,0.3837,0.36,0.8433,25,2026-03-12T21:11:09+00:00,ee017c3
2,0.25,0.3871,0.36,0.8600,25,2026-03-12T21:11:09+00:00,ee017c3
...
```

The dashboard Evaluation page reads this file and renders nDCG/Recall/MRR trend charts automatically.

---

## API Reference

> **Before running any API commands below, make sure the app is running first:**
> ```bash
> # Option 1 — local
> bash up.sh
>
> # Option 2 — Docker
> docker compose up -d
> ```
> Then open a **new terminal** and run the commands below.

### `GET /api/v1/health`
```bash
curl http://localhost:8000/api/v1/health
```
```json
{
  "status": "ok",
  "version": "1.0.0",
  "git_commit": "5001ac8",
  "indexes_loaded": true,
  "total_queries_served": 42
}
```

---

### `POST /api/v1/search`
```bash
curl -X POST http://localhost:8000/api/v1/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "NASA space exploration missions",
    "alpha": 0.5,
    "top_k": 5,
    "filters": { "category": "space" }
  }'
```
```json
{
  "request_id": "3f2a1b4c-9e8d-4a2b-b1c0-7f6e5d4c3b2a",
  "query": "NASA space exploration missions",
  "alpha": 0.5,
  "result_count": 5,
  "latency_ms": 38.4,
  "results": [
    {
      "doc_id": "doc_0001_ab12cd34",
      "title": "Space Shuttle",
      "snippet": "…**NASA** engineers monitored the **spacecraft** systems…",
      "category": "space",
      "bm25_score": 0.91,
      "vector_score": 0.85,
      "score": 0.88
    }
  ]
}
```

**Alpha guide:**
| Alpha | Behaviour |
|---|---|
| `1.0` | Pure BM25 — exact keyword match |
| `0.5` | Balanced — best default |
| `0.0` | Pure vector — semantic, handles synonyms |

**Available filter categories:** `space medicine technology science history geography economics sports culture nature society general`

---

### `POST /api/v1/feedback`
Log relevance feedback for a result:
```bash
curl -X POST http://localhost:8000/api/v1/feedback \
  -H "Content-Type: application/json" \
  -d '{
    "request_id": "3f2a1b4c-...",
    "doc_id": "doc_0001_ab12cd34",
    "relevant": true,
    "comment": "exactly what I needed"
  }'
```

---

### `GET /api/v1/metrics`
Prometheus-compatible plain text:
```bash
curl http://localhost:8000/api/v1/metrics
```
```
# HELP search_requests_total Total number of search requests
# TYPE search_requests_total counter
search_requests_total 412

# HELP search_latency_p50_ms 50th percentile latency in ms
# TYPE search_latency_p50_ms gauge
search_latency_p50_ms 34.2

# HELP search_latency_p95_ms 95th percentile latency in ms
# TYPE search_latency_p95_ms gauge
search_latency_p95_ms 89.7
```

---

## Hybrid Scoring

BM25 and vector search each return up to 30 candidates independently. Their doc_id sets are unioned, then fused:

```
# 1. Missing scores filled with 0.0

# 2. Min-max normalise each score space to [0, 1]
#    If all scores equal → return 0.5 (avoids divide-by-zero NaN)

norm = (score - min) / (max - min)

# 3. Fuse
hybrid = alpha × bm25_norm + (1 - alpha) × vector_norm
```

Results sorted by `hybrid` descending, truncated to `top_k`. Every result carries `bm25_score`, `vector_score`, and `score` so the ranking is fully explainable.

Two normalisation strategies are compared in `docs/decision_log.md` — min-max was chosen over z-score for bounded [0,1] output and robustness on small result sets.

---

## SQLite Schema

All requests logged to `data/search_logs.db`:

```sql
CREATE TABLE query_logs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id    TEXT    NOT NULL,
    timestamp     TEXT    NOT NULL,   -- ISO-8601 UTC
    query         TEXT    NOT NULL,
    alpha         REAL    NOT NULL,
    top_k         INTEGER NOT NULL,
    latency_ms    REAL    NOT NULL,
    result_count  INTEGER NOT NULL,
    filters       TEXT,               -- JSON or NULL
    error         TEXT                -- NULL on success
);
```

Migrations are versioned in `app/db.py` via a `schema_meta` table — see Scenario B in `docs/break_fix_log.md` for how a bad migration was induced and recovered.

---

## Project Structure

```
hybridsearch/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app + lifespan
│   │   ├── dependencies.py      # get_search_engine(), get_db()
│   │   ├── models.py            # Pydantic schemas
│   │   ├── db.py                # SQLite + versioned migrations
│   │   ├── ingest.py            # Wikipedia fetch + preprocessing
│   │   ├── eval.py              # nDCG / Recall / MRR harness
│   │   ├── generate_qrels.py    # ground-truth relevance judgments
│   │   ├── search/
│   │   │   ├── bm25.py          # BM25Index: build, save, load, query
│   │   │   ├── vector.py        # FAISS index: embed, build, save, load, query
│   │   │   └── hybrid.py        # score fusion + snippet highlighting
│   │   └── api/
│   │       ├── search.py        # POST /api/v1/search
│   │       ├── feedback.py      # POST /api/v1/feedback
│   │       ├── ingest.py        # POST /api/v1/ingest
│   │       └── stats.py         # GET /api/v1/stats|metrics|health
│   ├── scripts/
│   │   └── build_index.py       # standalone: ingest → build both indexes
│   └── tests/
│       ├── conftest.py          # shared fixtures (toy corpus, tmp indexes)
│       ├── test_bm25.py         # BM25 scoring + ordering
│       ├── test_vector.py       # embedding + FAISS search
│       ├── test_hybrid.py       # fusion, NaN guard, normalization
│       ├── test_ingest.py       # preprocessing + JSONL output
│       └── test_api.py          # FastAPI contract tests (TestClient)
├── frontend/
│   └── dashboard.py             # Streamlit: Search / KPIs / Eval / Debug
├── data/
│   ├── raw/                     # drop custom .txt/.md files here
│   ├── processed/docs.jsonl     # pre-built, committed
│   ├── indexes/                 # pre-built, committed
│   │   ├── bm25/index.pkl + meta.json
│   │   └── vector/index.faiss + meta.json + id_map.json
│   └── metrics/experiments.csv  # eval results across runs
├── eval/
│   └── qrels.json               # 25 queries × 3-10 relevant docs
├── docs/
│   ├── architecture.md
│   ├── decision_log.md          # normalization strategy, tech choices
│   ├── codex_log.md             # granular Codex prompt log
│   ├── break_fix_log.md         # 3 induced failure scenarios + fixes
│   ├── api.md
│   └── evaluation.md
├── up.sh                        # one-command start
├── down.sh                      # one-command stop
├── pytest.ini
├── requirements.txt
├── .env.example
└── README.md
```

---

## Docs

| File | Contents |
|---|---|
| `docs/architecture.md` | System design, data flow, component diagram |
| `docs/decision_log.md` | Why min-max over z-score, why SQLite, why Streamlit |
| `docs/codex_log.md` | Every Codex prompt mapped to a commit |
| `docs/break_fix_log.md` | Scenario A (index mismatch), B (schema migration), C (NaN scoring) |
| `docs/api.md` | Full API reference |
| `docs/evaluation.md` | Eval methodology and qrels construction |

---

## Constraints

- **CPU-only** — torch installed from CPU wheel index, `faiss-cpu` pinned explicitly. No CUDA required.
- **No paid services** — everything runs locally.
- **No hardcoded paths** — all paths relative to repo root via `SCRIPT_DIR` in `up.sh`.
- **Reviewer time** — fresh clone to running system in under 5 minutes.

---


---


---

## Docker

Run the full stack in containers — no Python install required on your host.
```bash
cp .env.example .env
docker compose up --build
```

| Service | URL |
|---|---|
| Dashboard | http://localhost:8501 |
| API | http://localhost:8000 |
| Swagger UI | http://localhost:8000/docs |

The first build downloads and installs all Python dependencies including CPU-only torch — this takes a few minutes but subsequent builds are fast thanks to Docker layer caching.

**Useful commands:**
```bash
docker compose up -d               # run in the background
docker compose logs -f api         # tail API logs
docker compose logs -f dashboard   # tail dashboard logs
docker compose down                # stop containers
```

Data (indexes, SQLite DB, processed docs) is served directly from the repo's `data/` folder via a bind mount — pre-built indexes are available immediately on first start, no rebuild needed.

---

## CI/CD (GitHub Actions)

The pipeline at `.github/workflows/ci.yml` runs automatically on every push and PR to `main`:

| Job | Trigger | What it does |
|---|---|---|
| **test** | every push / PR | Runs pytest with coverage |
| **build** | after tests pass | Builds both Docker images |
| **publish** | push to main only | Pushes images to Docker Hub |

Images are published to Docker Hub as:
```
mohitjain2306/hybridsearch:api
mohitjain2306/hybridsearch:dashboard
```

Each commit also gets a unique `:<git-sha>` tag so you can pin to exact versions.

**Required GitHub secrets** (Settings → Secrets → Actions):

| Secret | Value |
|---|---|
| `DOCKERHUB_USERNAME` | your Docker Hub username |
| `DOCKERHUB_TOKEN` | Docker Hub access token |
