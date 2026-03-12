# docs/codex_log.md

# Codex Log — Hybrid Search Engine

This document logs the prompts I gave Claude (Codex) during the build,
what it generated, what I changed manually, and which commit the work
landed in. The goal is to show how the project was actually built —
iteratively, with real bugs, fixes, and back-and-forth.

---

### Prompt 1 — Project overview + folder structure discussion

**Prompt given:** "Hey, I have an assignment where I need to build a hybrid
search engine from scratch. It's a fairly complete system, not just a
script. Let me explain what it needs to do and then we'll build it together
file by file.

The system needs to:
- Ingest documents (Wikipedia articles) and clean them
- Build two search indexes: BM25 (keyword) and vector (semantic embeddings)
- Combine both into hybrid search with a tunable alpha parameter
- Expose everything via a FastAPI backend
- Show results + KPIs on a Streamlit dashboard
- Log all queries to SQLite
- Have an evaluation harness that computes nDCG, Recall, MRR
- Start the whole thing with one command (up.sh)
- Have pytest tests, and proper documentation

Tech stack I want to use:
- Python 3.13, CPU only, macOS
- FastAPI + uvicorn for the API
- rank-bm25 for keyword search
- sentence-transformers (all-MiniLM-L6-v2) + faiss-cpu for vector search
- Streamlit + plotly for the dashboard
- SQLite for logging
- wikipedia-api for data

Before we write any code, can you help me think through:
1. What folder structure makes sense for this?
2. What files do I need and what does each one do?
3. What should requirements.txt look like for this stack?

Once we align on structure, we'll go file by file."

**Response summary:** Claude proposed a `src/` flat layout with `api/`,
`dashboard/`, `eval/`, `tests/`, `scripts/` folders. Gave a full
requirements.txt with pinned versions and explained design decisions around
score normalisation, chunking strategy, and why pickle is used for BM25
over JSON. Suggested a build order starting from models.py.

**What I changed manually:** Rejected the structure — felt too flat and
unorganised for what the project needed.

**Commit:** 5f9e8ef

---

### Prompt 2 — Production-style folder structure

**Prompt given:** "Hmm I like this overall but I feel like the structure
could be a bit more organized? Like having everything search related
together, API stuff separate from app logic, that kind of thing. What would
a more production-style layout look like?"

**Response summary:** Claude proposed a layered `core/`, `search/`,
`api/routers/`, `infra/` structure with strict one-way dependency rules.
Explained the dependency arrow (nothing in core/ or search/ imports from
api/ or infra/) and why infra and domain should be separated.

**What I changed manually:** Still felt like overkill — too many nested
folders for the actual scale of this project.

**Commit:** 5f9e8ef

---

### Prompt 3 — Final folder structure decision

**Prompt given:** "okay this looks clean but honestly feels a bit overkill
for what I need to submit — like core/ infra/ routers/ is a lot of nesting.
I was thinking something simpler, like keep all the app logic under
backend/app/ and just have a search/ subfolder inside it for the three
search files. API stuff in backend/app/api/. Tests in backend/tests/.
Frontend separate. Does that work or am I missing something?"

**Response summary:** Claude agreed this was the right call and built out
the final structure: `backend/app/`, `backend/app/search/`,
`backend/app/api/`, `backend/tests/`, `frontend/`, `data/indexes/bm25/`,
`data/indexes/vector/`, `docs/`. Noted the one rule to keep: `api/` imports
from `search/`, never the reverse.

**What I changed manually:** Nothing yet — took this to the next prompt for
two more adjustments.

**Commit:** 5f9e8ef

---

### Prompt 4 — Final structure adjustments + created directory tree

**Prompt given:** "yes lets go but two things — I want ingest.py, eval.py
and generate_qrels.py directly inside backend/app/ not inside search/. And
data/ should have index/bm25/ and index/vector/ as subfolders instead of
just indexes/. Also docs/ folder with some md files for architecture,
decisions etc."

**Response summary:** Claude produced the locked final structure with
`ingest.py`, `eval.py`, `generate_qrels.py` at `app/` root, `indexes/bm25/`
and `indexes/vector/` subfolders, and `docs/` with four placeholder md
files. Explained why pipeline-level files belong at app root rather than
inside search/.

**What I changed manually:** Created the full directory tree using `mkdir`
and `touch` in terminal on my Mac.

**Commit:** 5f9e8ef

---

### Prompt 5 — models.py

**Prompt given:** "perfect, locked in. I created the whole structure using
mkdir and touch on my mac terminal. I'll be writing all files using cat or
vim in the terminal as we go. Ready  let's start with models.py"

**Response summary:** Claude generated `SearchRequest`, `SearchResult`,
`SearchResponse`, `Document`, `IngestRequest`, `IngestResponse`,
`QueryLog`, `StatsResponse` with Pydantic v2. Explained why `SearchResult`
carries both component scores, why `Document` and `SearchResult` are
separate models, and why `QueryLog.id` is `Optional[int]`.

**What I changed manually:** Nothing — moved straight to requesting
additions in the next prompt.

**Commit:** 5f9e8ef

---

### Prompt 6 — models.py additions + db.py

**Prompt given:** "looks good. few things before we move on  SearchRequest
needs a filters field (optional dict for category filtering), SearchResult
needs a snippet field (short preview text) and category. Also SearchResponse
needs a request_id and result_count field. Can you update models.py with
those and then lets do db.py"

**Response summary:** Claude updated all models with the requested fields.
Added `filters` to `SearchRequest`, `snippet` and `category` to
`SearchResult`, `request_id` (auto-generated UUID via `default_factory`)
and `result_count` to `SearchResponse`. Also added `category` to
`Document` and `request_id` + `filters` to `QueryLog`. Then generated
full `db.py` with SQLite, `log_query()` async wrapper via
`asyncio.to_thread`, `get_stats()`, `get_logs_for_eval()`, WAL mode, and
two indexes on `query_logs`.

**What I changed manually:** Nothing immediately — asked for schema
migration support in the next prompt.

**Commit:** 5f9e8ef

---

### Prompt 7 — db.py schema migrations + error column

**Prompt given:** "this is good but I realized I need the db to handle
schema migrations properly. like if I change the schema later it should not
break. can you add a schema_meta table that tracks the current version and
run migrations incrementally? also query_logs needs an error column
(nullable text) for when searches fail. then lets move to ingest.py"

**Response summary:** Claude rewrote `db.py` with a `MIGRATIONS` dict
keyed by version number, `schema_meta` table storing current version,
`_run_migrations()` that runs only pending entries, and an idempotency
check via `PRAGMA table_info` for the `error` column ALTER so it never
crashes on a clean install. Also added `error: Optional[str] = None` to
`QueryLog` in `models.py`. Explained the append-only rule for migrations.

**What I changed manually:** Nothing.

**Commit:** 5f9e8ef

---

### Prompt 8 — ingest.py

**Prompt given:** "okay lets do ingest.py now. so this file needs to fetch
Wikipedia articles and save them as processed docs. requirements are:
use wikipedia-api to fetch around 300 articles across these categories:
space, medicine, technology, science, history, geography, economics,
sports, culture, nature, society, general — roughly 20 per category
for each article clean the text, remove extra whitespace, truncate at
3000 chars
save output to data/processed/docs.jsonl where each line is:
{"doc_id": "doc_0001_abc12345", "title": "...", "text": "...",
"source": "https://en.wikipedia.org/wiki/...", "category": "space",
"created_at": "2024-01-01T00:00:00Z"}
doc_id format should be doc_{4digit_index}_{first8chars_of_md5_of_title}
also scan an input folder for any .txt files and include those too
add a 0.05 second sleep between requests to be polite
show a tqdm progress bar
CLI should be: python -m app.ingest --input data/raw --out data/processed
running it should produce 250+ valid JSONL lines"

**Response summary:** Claude generated full `ingest.py` with 12 categories
× 20 article titles hardcoded, `_make_doc_id()` using md5, `_clean_text()`
stripping non-ASCII and section headers, `_make_snippet()`, `fetch_wikipedia_docs()`,
`load_txt_docs()`, `run_ingest()`, tqdm on the write loop, and argparse CLI.
Outputs JSONL with all required fields.

**What I changed manually:** After running it I noticed ingest was taking
10+ minutes. Another project I compared against fetched only `page.summary`
instead of `page.text` — full article text is ~10× more data per request.
Changed to `(page.summary + " " + page.text)[:MAX_CHARS]` to get speed
of summary fetch with a bit of extra context.

**Commit:** 5f9e8ef

---

### Prompt 9 — bm25.py + test_bm25.py

**Prompt given:** "okay bm25.py time. I want a BM25Index class in
backend/app/search/bm25.py using rank-bm25. it should be able to build
from a list of docs, save itself to disk, load back up, and answer queries.
tokenization just lowercase split, nothing fancy. also write the pytest
tests for it in backend/tests/test_bm25.py using a small 3 doc corpus —
space, hockey, medicine — and make sure querying "space shuttle" actually
ranks the space doc first"

**Response summary:** Claude generated `BM25Index` with `build()`,
`save()` (pickle + meta.json), `load()` (raised FileNotFoundError at this
point), `query()` with min-max normalisation and category filter,
`_passes_filter()`, `__len__`, `__repr__`. Test file had 23 tests across
tokenizer, build, ranking, scores, filters, and roundtrip.

**What I changed manually:** `load()` was changed to return `False` on
missing file in the next prompt instead of raising.

**Commit:** 5f9e8ef

---

### Prompt 10 — bm25.py load() fix + vector.py + test_vector.py

**Prompt given:** "this is great. one thing though — I need load() to
return True or False instead of raising FileNotFoundError, so main.py can
check if indexes exist at startup without try/catch everywhere. can you fix
just that method and then lets move to vector.py
for vector.py I want a VectorIndex class using sentence-transformers with
all-MiniLM-L6-v2 and faiss-cpu with IndexFlatIP. embeddings should be
L2 normalized so inner product equals cosine similarity. it should save
a meta.json with model name, dimension, corpus hash and built_at. on load
it must validate model name and dimension against meta.json and raise
RuntimeError with a clear message if they dont match — I dont want it to
silently return wrong results"

**Response summary:** Claude fixed `BM25Index.load()` to return `False`
on missing file. Generated full `VectorIndex` with `normalize_embeddings=True`
in `_encode()`, saves `meta.json` with model name, dimension, corpus hash,
`built_at`. Load validates model name then reads actual FAISS dim and
compares against meta — raises `RuntimeError` with specific message for
model mismatch, missing meta, missing id_map, or dimension mismatch.
Test file had 28 tests including tampered meta.json for dimension mismatch.

**What I changed manually:** Nothing.

**Commit:** 5f9e8ef

---

### Prompt 11 — hybrid.py + test_hybrid.py

**Prompt given:** "okay hybrid.py time. this is the core of the whole thing
so want to get it right. it should take results from both bm25 and vector
and combine them. here are the requirements:
class HybridSearch that takes a BM25Index and VectorIndex in __init__
search method that fetches top 30 from each, takes the union by doc_id,
then normalizes scores using min-max separately for bm25 and vector,
then combines as: hybrid = alpha * bm25 + (1-alpha) * vector
one thing thats really important — if all scores are equal (max == min),
dont return NaN, return 0.5 for everything. I got burned by this before
with nonsense queries where bm25 returns all zeros
alpha=1.0 should be pure bm25, alpha=0.0 should be pure vector
also a _snippet helper that returns a 150 char window around the first
matching word, with matched words wrapped in bold markdown
write the tests too in test_hybrid.py — make sure NaN case is covered,
and that alpha=1.0 makes hybrid score equal bm25 score"

**Response summary:** Claude generated `HybridSearch.search()` with
union-based fusion, `_minmax()` with explicit NaN guard
(`if rng == 0.0: return {doc_id: 0.5}`), `_snippet()` with regex
highlighting and ellipsis markers. Tests used `MagicMock` for indexes,
covered NaN for all-zero BM25, all-zero vector, both zero, alpha=1.0
equals BM25, alpha=0.0 equals vector, deduplication, union, edge cases.

**What I changed manually:** The NaN guard was later intentionally removed
and restored as a documented break/fix scenario — see break_fix_log.md.

**Commit:** 5f9e8ef

---

### Prompt 12 — dependencies.py + main.py

**Prompt given:** "great, lets do the API now. I want two files —
dependencies.py and main.py in backend/app/
dependencies.py should have a get_search_engine() function that returns
the HybridSearch instance, and get_db() for the database connection.
inject them into routes using FastAPIs dependency injection so routes
dont reach into globals
main.py should use a lifespan context manager for startup and shutdown.
on startup: run init_db(), load both indexes, if they exist create
HybridSearch and register it, if indexes are missing just print a warning
and keep going so the API still starts. add CORS middleware for the
streamlit frontend, slowapi rate limiting at 100 requests per minute per
IP, and mount the router. app title Knowledge Search API version 1.0.0"

**Response summary:** Claude generated `dependencies.py` with
`set_search_engine()`, `get_search_engine()` (raises 503 if not loaded),
`get_db()` generator, and `Annotated` aliases for clean route signatures.
Generated `main.py` with lifespan (init_db, load indexes via
`isinstance` check, create HybridSearch, warn if missing), CORS for
localhost:8501, slowapi rate limiting, three routers at `/api/v1`, and a
basic `/health` route.

**What I changed manually:** The `/health` route in `main.py` caused a
conflict with the richer one in `stats.py` — asked Claude to remove it in
the next prompt.

**Commit:** 5f9e8ef

---

### Prompt 13 — api/search.py, api/stats.py, api/ingest.py

**Prompt given:** "yes lets do the three router files now. here are the
requirements for each:
search.py — POST /search that takes SearchRequest, calls
HybridSearch.search(), measures latency with time.perf_counter(), logs
to SQLite via log_query() using try/finally so logging always runs even
if search throws, returns SearchResponse with request_id, results,
latency_ms, result_count
stats.py — GET /stats that returns StatsResponse from get_stats(),
and GET /logs?limit=100 that returns recent logs, and GET /metrics that
returns plain text prometheus style with search_requests_total,
search_zero_results_total, search_latency_p50_ms, search_latency_p95_ms
ingest.py — POST /ingest that triggers the ingest pipeline, this one
can be simple just runs run_ingest() and returns IngestResponse
also GET /health should return status, version 1.0.0, git commit hash
from git rev-parse, index_loaded bool, and total_queries_served count"

**Response summary:** Claude generated all three routers. `search.py` uses
`try/finally` so `log_query()` always runs, captures latency at two points
(happy path and finally). `stats.py` has `/metrics` with `_percentile()`
helper and `/health` with `subprocess` git rev-parse. `ingest.py` calls
`run_ingest()` and returns accurate counts.

**What I changed manually:** Nothing yet — conflict with `/health` in
`main.py` handled in next prompt.

**Commit:** 5f9e8ef

---

### Prompt 14 — Remove duplicate /health + wire ingest topics + build_index.py + eval.py

**Prompt given:** "looks good but I have /health defined in both main.py
and stats.py now which will cause a conflict. can you remove the one from
main.py and keep only the richer one in stats.py? also the ingest endpoint
is ignoring the topics from IngestRequest completely, can you at least pass
them through to run_ingest so it filters which categories get fetched —
that means run_ingest needs a categories parameter too
once thats done lets move to build_index.py and eval.py"

**Response summary:** Claude removed `/health` from `main.py`, added
`categories: list[str] | None` parameter to `run_ingest()` and
`fetch_wikipedia_docs()`, wired `request.topics` through in
`api/ingest.py` with fallback to all categories if none match. Generated
`scripts/build_index.py` with argparse and malformed-line skipping.
Generated `eval.py` with `Evaluator` class, `ndcg_at_k()`, `recall_at_k()`,
`mrr()` implementations, and `print_report()`.

**What I changed manually:** Nothing.

**Commit:** 5f9e8ef

---

### Prompt 15 — generate_qrels.py

**Prompt given:** "nice. now I need generate_qrels.py inside backend/app/.
it should read data/processed/docs.jsonl, group doc_ids by category, then
for each query map it to a category and take up to 10 doc_ids from that
category as relevant docs, save to eval/qrels.json
here are my 25 queries and their category mappings:
q01→space, q02→space, q03→medicine, q04→medicine,
q05→technology, q06→technology, q07→science, q08→science,
q09→history, q10→history, q11→geography, q12→economics,
q13→sports, q14→sports, q15→culture, q16→medicine,
q17→technology, q18→science, q19→history, q20→geography,
q21→economics, q22→sports, q23→society, q24→general, q25→space
the queries themselves should be meaningful ones like "NASA space
exploration", "cancer treatment advances", "machine learning algorithms"
etc matching the categories. CLI: python -m app.generate_qrels"

**Response summary:** Claude generated `generate_qrels.py` with a hardcoded
`QUERIES` list of 25 `(query_text, category)` tuples with meaningful
query strings, `load_docs_by_category()`, `build_qrels()` with graded
relevance (grade 2 for first 3 docs, grade 1 for docs 4–10), and full
argparse CLI. Outputs to `eval/qrels.json`.

**What I changed manually:** Nothing.

**Commit:** 5f9e8ef

---

### Prompt 16 — frontend/dashboard.py

**Prompt given:** "okay lets do the streamlit dashboard in frontend/app.py.
needs 4 pages:
Page 1 Search — text input for query, slider for alpha 0.0 to 1.0 step
0.05, number input for top_k 1-20 default 10, dropdown to filter by
category, search button. show result count latency and request_id. for
each result show an expander with title snippet doc_id and inside it a
horizontal plotly bar chart showing bm25_score vector_score hybrid_score.
each chart needs a unique key
Page 2 KPI — fetch from /api/v1/logs, show 4 metric cards total queries
p50 latency p95 latency zero result queries, bar chart of request volume
by hour, top 10 queries table, latency histogram
Page 3 Evaluation — read data/metrics/experiments.csv, show full
dataframe, line chart of ndcg over experiment runs, scatter plots for
recall and mrr by alpha
Page 4 Debug Logs — fetch logs, add severity column ERROR if error field
not null else INFO, filter by severity, show dataframe with datetime
severity query latency error columns
sidebar should have navigation and an API health badge showing git commit
and whether indexes are loaded. all API calls go to http://localhost:8000"

**Response summary:** Claude generated the full four-page Streamlit app.
Search page uses `st.form` with unique plotly chart keys via
`f"score_chart_{rid}_{i}"`. KPI page computes p50/p95 client-side from
raw logs. Eval page degrades gracefully if CSV missing. Debug Logs derives
severity from `error` field being null or not.

**What I changed manually:** Claude wrote `frontend/app.py` but the file
was `frontend/dashboard.py`. Asked Claude to correct it — one line change
in `up.sh`.

**Commit:** 5f9e8ef

---

### Prompt 17 — up.sh first version

**Prompt given:** "lets do up.sh now. requirements:
use set -euo pipefail at the top
create .venv if it doesnt exist, activate it, pip install -r requirements.txt quietly
run init_db
if data/processed/docs.jsonl doesnt exist run python -m app.ingest
if bm25 or vector index missing run python -m scripts.build_index
if eval/qrels.json missing run python -m app.generate_qrels
if data/metrics/experiments.csv missing run eval for all 5 alpha values
0.0 0.25 0.5 0.75 1.0 and save results to that csv
start uvicorn in background on port 8000
poll /health every second until it returns 200, max 30 tries
start streamlit in background on port 8501
print the URLs nicely at the end
trap ctrl+c to kill both processes cleanly
add coloured output, green for info yellow for warning red for error
second run should skip everything that already exists"

**Response summary:** Claude generated `up.sh` with colour helper
functions, cleanup trap, idempotent checks for all six artifacts, health
polling loop with `kill -0` liveness check, eval heredoc writing CSV,
and the URL banner at the end. Made it executable with `chmod +x`.

**What I changed manually:** Path issues discovered on first run —
addressed in next prompt.

**Commit:** 5f9e8ef

---

### Prompt 18 — up.sh path audit + port conflict check

**Prompt given:** "up.sh looks mostly good but I think there are some path
issues. the script cd's into backend/ for the python commands but then some
paths like ../data/processed and ../data/metrics might not resolve correctly
depending on where things are called from. can you audit all the paths and
make sure everything is consistent? also can you add a check that if
uvicorn or streamlit are already running on those ports it kills them before
starting fresh"

**Response summary:** Claude audited all paths and found: `generate_qrels`
was writing to `backend/eval/` instead of `eval/`, eval heredoc used
relative `Path("../data/metrics/...")` which depended on cwd. Rewrote
`up.sh` with all paths anchored to `$SCRIPT_DIR` as absolute variables
(`DATA_DIR`, `EVAL_DIR`, `METRICS_DIR`), passed all paths explicitly to
every Python command via flags or env vars, and added `kill_port()` using
`lsof -ti tcp:PORT`.

**What I changed manually:** Applied the rewrite. Also found that
`HEALTH_URL` was set to `/health` not `/api/v1/health` — fixed separately
in a later debug session.

**Commit:** 55a0e6a / ef74c1c

---

### Prompt 19 — docs (architecture.md, decisions.md, api.md, evaluation.md)

**Prompt given:** "yes lets start the docs"

**Response summary:** Claude generated all four docs files.
`architecture.md` with ASCII component diagram, data flow diagram, and
directory tree. `decisions.md` with seven ADRs covering BM25 choice,
FAISS IndexFlatIP, model selection, linear interpolation vs RRF, SQLite,
FastAPI, and graded relevance. `api.md` with full endpoint reference,
request/response examples, and error table. `evaluation.md` with metric
formulas, qrels format, CLI usage, and interpretation guidance.

**What I changed manually:** Nothing.

**Commit:** 5f9e8ef

---

### Prompt 20 — requirements.txt

**Prompt given:** "create requirements.txt in the repo root. i need pinned
versions for everything the project uses. the stack is fastapi, uvicorn
with standard extras, pydantic v2, rank-bm25, sentence-transformers,
faiss-cpu (not the gpu version), wikipedia-api, streamlit, plotly, slowapi
for rate limiting, pytest, pytest-asyncio, httpx for testing, and tqdm.
python version is 3.11, cpu only machine, no cuda. make sure the versions
are actually compatible with each other and don't pull in any gpu torch
variants."

**Response summary:** Claude generated pinned `requirements.txt` with torch
installed from the CPU wheel index (`download.pytorch.org/whl/cpu`),
`faiss-cpu` explicitly (not `faiss-gpu`), `numpy==1.26.4` for
compatibility with torch and faiss, and all transitive deps pinned.
Explained why torch must be installed before requirements.txt runs.

**What I changed manually:** Hit three version errors on actual install —
`torch==2.3.1` not found for my Python version, then `faiss-cpu==1.8.0`
not found, then `pydantic-core` Python 3.13 compile failure. Went through
multiple rounds with Claude to land on a working set: `torch==2.6.0`,
`faiss-cpu==1.9.0.post1`, `pydantic==2.10.3`, `numpy==2.1.3`,
`sentence-transformers==3.3.1`.

**Commit:** 55a0e6a

---

### Prompt 21 — .env.example

**Prompt given:** "create a .env.example file in the repo root. the app
uses sqlite at data/search_logs.db, indexes at data/indexes/bm25 and
data/indexes/vector, processed docs at data/processed/docs.jsonl, and
qrels at eval/qrels.json. the api runs on port 8000 and streamlit on 8501.
cors is allowed for localhost:8501. rate limit is 100 requests per minute.
no secrets or api keys anywhere. just environment variable names with
placeholder values and a short comment on each line explaining what it
does."

**Response summary:** Claude generated `.env.example` with variables for
API host/port/log level, Streamlit host/port, CORS origins, rate limit,
DB path, index dirs, docs path, raw docs dir, qrels path, metrics dir,
ingest config (max articles, max chars, request delay), and embedding
model/device. Each line has a short inline comment. Noted that
`EMBEDDING_DEVICE=cpu` should be wired through to `SentenceTransformer`
to prevent GPU use on CUDA machines.

**What I changed manually:** Nothing.

**Commit:** 5f9e8ef

---

### Prompt 22 — README.md

**Prompt given:** "create README.md in the repo root. it needs a one
paragraph project description at the top, then a quickstart section
showing exactly how to clone and run ./up.sh and what urls come up. then
an api endpoints table covering GET /health, POST /search with example
request and response json showing bm25_score vector_score and hybrid_score
fields, GET /metrics, and GET /stats. then a section on how to run tests
with pytest. then how to run eval and what experiments.csv looks like.
then the sqlite schema for query_logs table. then the hybrid scoring
formula written out clearly. then a folder structure tree. keep it
readable, not corporate, like a student project that actually works.
in readme you can generate it as you like to make it good, explaining
itselt and attractive"

**Response summary:** Claude generated the full `README.md` with a
one-paragraph intro, quickstart table of URLs, per-endpoint sections with
curl examples and JSON responses showing all three score fields, pytest
section with coverage command, eval section with sample output table and
CSV format, SQLite schema block with `CREATE TABLE` DDL, hybrid scoring
formula written out step by step with the NaN special case noted, and
full folder tree. Corrected the clone URL from placeholder to
`github.com/mohitjain2306/hybridsearch`.

**What I changed manually:** Noticed the clone URL still had
`you/hybrid-search.git` placeholder — asked Claude to fix it to the actual
repo. That was the only edit needed across all files.

**Commit:** 5f9e8ef