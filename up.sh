#!/usr/bin/env bash
# up.sh — single-command launcher for the hybrid search engine
# Usage: bash up.sh

set -euo pipefail

# ---------------------------------------------------------------------------
# Colours
# ---------------------------------------------------------------------------

GREEN="\033[0;32m"
YELLOW="\033[0;33m"
RED="\033[0;31m"
BOLD="\033[1m"
RESET="\033[0m"

info()   { echo -e "${GREEN}[INFO]${RESET}  $*"; }
warn()   { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
error()  { echo -e "${RED}[ERROR]${RESET} $*" >&2; }
header() { echo -e "\n${BOLD}$*${RESET}"; }

# ---------------------------------------------------------------------------
# Absolute paths — everything anchored to SCRIPT_DIR, never cwd-relative
# ---------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
VENV_DIR="$SCRIPT_DIR/.venv"
REQUIREMENTS="$SCRIPT_DIR/requirements.txt"

DATA_DIR="$SCRIPT_DIR/data"
EVAL_DIR="$SCRIPT_DIR/eval"
METRICS_DIR="$DATA_DIR/metrics"

DOCS_JSONL="$DATA_DIR/processed/docs.jsonl"
BM25_INDEX="$DATA_DIR/indexes/bm25/index.pkl"
VECTOR_INDEX="$DATA_DIR/indexes/vector/index.faiss"
QRELS="$EVAL_DIR/qrels.json"
EXPERIMENTS_CSV="$METRICS_DIR/experiments.csv"

UVICORN_PORT=8000
STREAMLIT_PORT=8501
HEALTH_URL="http://localhost:${UVICORN_PORT}/health"

UVICORN_PID=""
STREAMLIT_PID=""

# ---------------------------------------------------------------------------
# Cleanup trap
# ---------------------------------------------------------------------------

cleanup() {
    echo ""
    header "Shutting down…"
    if [[ -n "$UVICORN_PID" ]] && kill -0 "$UVICORN_PID" 2>/dev/null; then
        info "Stopping API server (PID $UVICORN_PID)"
        kill "$UVICORN_PID" 2>/dev/null || true
    fi
    if [[ -n "$STREAMLIT_PID" ]] && kill -0 "$STREAMLIT_PID" 2>/dev/null; then
        info "Stopping dashboard (PID $STREAMLIT_PID)"
        kill "$STREAMLIT_PID" 2>/dev/null || true
    fi
    info "Bye."
    exit 0
}

trap cleanup INT TERM

# ---------------------------------------------------------------------------
# Port conflict helper
# ---------------------------------------------------------------------------

kill_port() {
    local port="$1"
    local name="$2"
    # lsof -ti returns PIDs listening on the port; empty if none
    local pids
    pids=$(lsof -ti tcp:"$port" 2>/dev/null || true)
    if [[ -n "$pids" ]]; then
        warn "Port $port already in use by PID(s) $pids ($name) — killing…"
        echo "$pids" | xargs kill -9 2>/dev/null || true
        sleep 1
        info "Port $port is now free."
    else
        info "Port $port is free."
    fi
}

# ---------------------------------------------------------------------------
# Step 1 — virtual environment
# ---------------------------------------------------------------------------

header "── Step 1 · Python environment ──────────────────────────────"

if [[ ! -d "$VENV_DIR" ]]; then
    info "Creating virtual environment at .venv…"
    python3 -m venv "$VENV_DIR"
else
    info ".venv already exists — skipping creation."
fi

# shellcheck source=/dev/null
source "$VENV_DIR/bin/activate"

info "Installing CPU-only torch first to prevent GPU variant download…"
pip install -q \
    torch==2.6.0 \
    --index-url https://download.pytorch.org/whl/cpu

info "Installing remaining dependencies (quiet)…"
pip install -q -r "$REQUIREMENTS"

# ---------------------------------------------------------------------------
# Step 2 — database
# cd into BACKEND_DIR once here; stays for all subsequent python -m calls
# ---------------------------------------------------------------------------

header "── Step 2 · Database ─────────────────────────────────────────"

cd "$BACKEND_DIR"
info "Working directory: $(pwd)"

info "Running init_db…"
python - <<'EOF'
from app.db import init_db
init_db()
print("Database initialised.")
EOF

# ---------------------------------------------------------------------------
# Step 3 — ingest
# Pass absolute paths explicitly so no default inside ingest.py is used
# ---------------------------------------------------------------------------

header "── Step 3 · Ingest ───────────────────────────────────────────"

if [[ -f "$DOCS_JSONL" ]]; then
    DOC_COUNT=$(wc -l < "$DOCS_JSONL" | tr -d ' ')
    info "docs.jsonl already exists ($DOC_COUNT lines) — skipping ingest."
else
    warn "docs.jsonl not found — running ingest (this may take a few minutes)…"
    python -m app.ingest \
        --input "$DATA_DIR/raw" \
        --out   "$DATA_DIR/processed"
    info "Ingest complete."
fi

# ---------------------------------------------------------------------------
# Step 4 — indexes
# Pass absolute paths so build_index never relies on cwd defaults
# ---------------------------------------------------------------------------

header "── Step 4 · Search indexes ───────────────────────────────────"

BM25_MISSING=false
VECTOR_MISSING=false
[[ ! -f "$BM25_INDEX"   ]] && BM25_MISSING=true
[[ ! -f "$VECTOR_INDEX" ]] && VECTOR_MISSING=true

if $BM25_MISSING || $VECTOR_MISSING; then
    if $BM25_MISSING && $VECTOR_MISSING; then
        warn "Both indexes missing — building from scratch…"
    elif $BM25_MISSING; then
        warn "BM25 index missing — rebuilding both indexes…"
    else
        warn "Vector index missing — rebuilding both indexes…"
    fi

    python -m scripts.build_index \
        --docs       "$DOCS_JSONL" \
        --bm25-dir   "$DATA_DIR/indexes/bm25" \
        --vector-dir "$DATA_DIR/indexes/vector"

    info "Indexes built."
else
    info "Both indexes found — skipping build."
fi

# ---------------------------------------------------------------------------
# Step 5 — qrels
# Pass absolute --out so generate_qrels never writes relative to backend/
# ---------------------------------------------------------------------------

header "── Step 5 · Qrels ────────────────────────────────────────────"

if [[ -f "$QRELS" ]]; then
    info "eval/qrels.json already exists — skipping generation."
else
    warn "qrels.json not found — generating…"
    mkdir -p "$EVAL_DIR"
    python -m app.generate_qrels \
        --docs "$DOCS_JSONL" \
        --out  "$QRELS"
    info "qrels.json generated."
fi

# ---------------------------------------------------------------------------
# Step 6 — evaluation
# All paths passed as absolute; heredoc uses SCRIPT_DIR env var
# ---------------------------------------------------------------------------

header "── Step 6 · Evaluation ───────────────────────────────────────"

if [[ -f "$EXPERIMENTS_CSV" ]]; then
    info "experiments.csv already exists — skipping eval."
else
    warn "experiments.csv not found — running evaluation across 5 alpha values…"
    mkdir -p "$METRICS_DIR"

    EXPERIMENTS_CSV="$EXPERIMENTS_CSV" \
    BM25_INDEX_PATH="$DATA_DIR/indexes/bm25/index.pkl" \
    BM25_META_PATH="$DATA_DIR/indexes/bm25/meta.json" \
    VECTOR_INDEX_PATH="$DATA_DIR/indexes/vector/index.faiss" \
    VECTOR_META_PATH="$DATA_DIR/indexes/vector/meta.json" \
    VECTOR_ID_MAP_PATH="$DATA_DIR/indexes/vector/id_map.json" \
    QRELS_PATH="$QRELS" \
    python - <<'EOF'
import csv
import os
import sys
from pathlib import Path

from app.search.bm25   import BM25Index
from app.search.vector import VectorIndex
from app.search.hybrid import HybridSearch
from app.eval          import Evaluator

bm25_index = BM25Index.load(
    index_path=Path(os.environ["BM25_INDEX_PATH"]),
    meta_path= Path(os.environ["BM25_META_PATH"]),
)
vector_index = VectorIndex.load(
    index_path=  Path(os.environ["VECTOR_INDEX_PATH"]),
    meta_path=   Path(os.environ["VECTOR_META_PATH"]),
    id_map_path= Path(os.environ["VECTOR_ID_MAP_PATH"]),
)

if not isinstance(bm25_index, BM25Index) or not isinstance(vector_index, VectorIndex):
    print("Indexes not found — skipping eval.")
    sys.exit(0)

engine    = HybridSearch(bm25_index, vector_index)
evaluator = Evaluator(engine, qrels_path=Path(os.environ["QRELS_PATH"]))
rows      = evaluator.run(alphas=[0.0, 0.25, 0.5, 0.75, 1.0])

out = Path(os.environ["EXPERIMENTS_CSV"])
out.parent.mkdir(parents=True, exist_ok=True)

fieldnames = ["run", "alpha", "ndcg_at_k", "recall_at_k", "mrr", "num_queries"]
with open(out, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    for i, row in enumerate(rows, start=1):
        writer.writerow({"run": i, **row})

print(f"experiments.csv written → {out}")
EOF

    info "Evaluation complete."
fi

# ---------------------------------------------------------------------------
# Step 7 — clear ports then start API
# ---------------------------------------------------------------------------

header "── Step 7 · API server ───────────────────────────────────────"

kill_port "$UVICORN_PORT"  "uvicorn"

uvicorn app.main:app \
    --host 0.0.0.0 \
    --port "$UVICORN_PORT" \
    --log-level warning \
    > "$SCRIPT_DIR/uvicorn.log" 2>&1 &

UVICORN_PID=$!
info "API server started (PID $UVICORN_PID) — logs → uvicorn.log"

# ---------------------------------------------------------------------------
# Step 8 — health poll
# ---------------------------------------------------------------------------

header "── Step 8 · Waiting for API ──────────────────────────────────"

MAX_TRIES=30
TRIES=0
API_READY=false

while [[ $TRIES -lt $MAX_TRIES ]]; do
    if curl -sf "$HEALTH_URL" > /dev/null 2>&1; then
        API_READY=true
        break
    fi

    TRIES=$((TRIES + 1))

    if ! kill -0 "$UVICORN_PID" 2>/dev/null; then
        error "API process died unexpectedly. Check uvicorn.log:"
        tail -20 "$SCRIPT_DIR/uvicorn.log" >&2
        exit 1
    fi

    echo -ne "\r${YELLOW}[WAIT]${RESET}  Polling /health… (${TRIES}/${MAX_TRIES})"
    sleep 1
done

echo ""

if ! $API_READY; then
    error "API did not become healthy after ${MAX_TRIES}s."
    error "Last 20 lines of uvicorn.log:"
    tail -20 "$SCRIPT_DIR/uvicorn.log" >&2
    kill "$UVICORN_PID" 2>/dev/null || true
    exit 1
fi

info "API is healthy ✓"

# ---------------------------------------------------------------------------
# Step 9 — clear port then start dashboard
# ---------------------------------------------------------------------------

header "── Step 9 · Dashboard ────────────────────────────────────────"

kill_port "$STREAMLIT_PORT" "streamlit"

streamlit run "$SCRIPT_DIR/frontend/dashboard.py" \
    --server.port     "$STREAMLIT_PORT" \
    --server.headless true \
    --server.address  0.0.0.0 \
    > "$SCRIPT_DIR/streamlit.log" 2>&1 &

STREAMLIT_PID=$!
info "Dashboard started (PID $STREAMLIT_PID) — logs → streamlit.log"

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------

echo ""
echo -e "${BOLD}${GREEN}┌──────────────────────────────────────────────────┐${RESET}"
echo -e "${BOLD}${GREEN}│        Hybrid Search Engine is live              │${RESET}"
echo -e "${BOLD}${GREEN}├──────────────────────────────────────────────────┤${RESET}"
echo -e "${BOLD}${GREEN}│${RESET}  API        http://localhost:${UVICORN_PORT}               ${BOLD}${GREEN}│${RESET}"
echo -e "${BOLD}${GREEN}│${RESET}  API Docs   http://localhost:${UVICORN_PORT}/docs          ${BOLD}${GREEN}│${RESET}"
echo -e "${BOLD}${GREEN}│${RESET}  Dashboard  http://localhost:${STREAMLIT_PORT}               ${BOLD}${GREEN}│${RESET}"
echo -e "${BOLD}${GREEN}│${RESET}  Metrics    http://localhost:${UVICORN_PORT}/api/v1/metrics ${BOLD}${GREEN}│${RESET}"
echo -e "${BOLD}${GREEN}└──────────────────────────────────────────────────┘${RESET}"
echo ""
info "Press Ctrl+C to stop both servers."
echo ""

wait "$UVICORN_PID" "$STREAMLIT_PID"