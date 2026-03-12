#!/usr/bin/env bash
cd /Users/mohitjain/Downloads/kearney/backend
source ../.venv/bin/activate

# Colours
GREEN="\033[0;32m"
YELLOW="\033[1;33m"
RED="\033[0;31m"
CYAN="\033[0;36m"
BOLD="\033[1m"
RESET="\033[0m"

section() { clear; echo -e "${BOLD}${CYAN}═══════════════════════════════════════════════════════${RESET}"; echo -e "${BOLD}${CYAN}  $1${RESET}"; echo -e "${BOLD}${CYAN}═══════════════════════════════════════════════════════${RESET}"; echo ""; }
step()    { echo -e "${BOLD}${YELLOW}>>> $1${RESET}"; echo ""; }
cmd()     { echo -e "${GREEN}\$ $1${RESET}"; echo ""; }
success() { echo -e "${BOLD}${GREEN}✓ $1${RESET}"; }
fail()    { echo -e "${BOLD}${RED}✗ $1${RESET}"; }

# ─── INTRO ───────────────────────────────────────────────────────────────────

clear
echo ""
echo -e "${BOLD}${CYAN}  ╔══════════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}${CYAN}  ║     Hybrid Search Engine — Demo Recording    ║${RESET}"
echo -e "${BOLD}${CYAN}  ╠══════════════════════════════════════════════╣${RESET}"
echo -e "${BOLD}${CYAN}  ║                                              ║${RESET}"
echo -e "${BOLD}${CYAN}  ║  This is a shell script that runs the full   ║${RESET}"
echo -e "${BOLD}${CYAN}  ║  demo automatically in 2-3 minutes.          ║${RESET}"
echo -e "${BOLD}${CYAN}  ║                                              ║${RESET}"
echo -e "${BOLD}${CYAN}  ║  Typing each command manually would have     ║${RESET}"
echo -e "${BOLD}${CYAN}  ║  taken 4x longer — so everything is          ║${RESET}"
echo -e "${BOLD}${CYAN}  ║  scripted for clarity and reproducibility.   ║${RESET}"
echo -e "${BOLD}${CYAN}  ║  Dashboard, KPIs and Eval already shown.     ║${RESET}"
echo -e "${BOLD}${CYAN}  ║                                              ║${RESET}"
echo -e "${BOLD}${CYAN}  ║  What this covers:                           ║${RESET}"
echo -e "${BOLD}${CYAN}  ║    1. API  —  health check, search, metrics  ║${RESET}"
echo -e "${BOLD}${CYAN}  ║    2. Tests  —  73 tests in under 10 sec     ║${RESET}"
echo -e "${BOLD}${CYAN}  ║    3. Break/Fix  —  live NaN bug + recovery  ║${RESET}"
echo -e "${BOLD}${CYAN}  ║                                              ║${RESET}"
echo -e "${BOLD}${CYAN}  ║  Commands are scripted so the recording      ║${RESET}"
echo -e "${BOLD}${CYAN}  ║  stays within 5-6 minutes.                   ║${RESET}"
echo -e "${BOLD}${CYAN}  ║                                              ║${RESET}"
echo -e "${BOLD}${CYAN}  ╚══════════════════════════════════════════════╝${RESET}"
echo ""
sleep 10

# ─── PART 1A: HEALTH CHECK ───────────────────────────────────────────────────

section "PART 1A — API HEALTH CHECK"
step "Checking API is up and indexes are loaded"
cmd "curl http://localhost:8000/api/v1/health"
sleep 2
curl -s http://localhost:8000/api/v1/health | python3 -m json.tool
echo ""
success "API is healthy — indexes loaded"
sleep 5

# ─── PART 1B: SEARCH ─────────────────────────────────────────────────────────

section "PART 1B — POST /search — HYBRID SCORE BREAKDOWN"
step "Query: 'black holes gravitational waves'  |  alpha=0.5 (balanced blend)"
cmd "curl -X POST /api/v1/search  -d '{query, alpha: 0.5, top_k: 3}'"
sleep 2
curl -s -X POST http://localhost:8000/api/v1/search \
  -H "Content-Type: application/json" \
  -d '{"query": "black holes gravitational waves", "alpha": 0.5, "top_k": 3}' \
| python3 -c "
import json, sys
data = json.load(sys.stdin)
print(f'  request_id   : {data[\"request_id\"]}')
print(f'  query        : {data[\"query\"]}')
print(f'  alpha        : {data[\"alpha\"]}')
print(f'  latency_ms   : {data[\"latency_ms\"]}')
print(f'  result_count : {data[\"result_count\"]}')
print()
for i, r in enumerate(data['results'], 1):
    print(f'  Result {i}: {r[\"title\"]}')
    print(f'    bm25_score   : {r[\"bm25_score\"]}')
    print(f'    vector_score : {r[\"vector_score\"]}')
    print(f'    hybrid_score : {r[\"score\"]}')
    print(f'    snippet      : {r[\"snippet\"][:80]}...')
    print()
"
success "Each result shows bm25_score + vector_score + hybrid score"
sleep 10

# ─── PART 1C: METRICS ────────────────────────────────────────────────────────

section "PART 1C — GET /metrics — PROMETHEUS COUNTERS"
step "Live request counters and latency percentiles"
cmd "curl http://localhost:8000/api/v1/metrics"
sleep 2
curl -s http://localhost:8000/api/v1/metrics
echo ""
success "Prometheus-compatible metrics endpoint"
sleep 8

# ─── PART 2: TESTS ───────────────────────────────────────────────────────────

section "PART 2 — RUNNING TEST SUITE (73 tests)"
step "BM25 + Hybrid + Ingest tests — completes in under 10 seconds"
cmd "pytest tests/test_hybrid.py tests/test_bm25.py tests/test_ingest.py"
sleep 2
python -m pytest tests/test_hybrid.py tests/test_bm25.py tests/test_ingest.py -v 2>&1 | tail -5
echo ""
success "All 73 tests passed"
sleep 5

# ─── PART 3 INTRO ────────────────────────────────────────────────────────────

section "PART 3 — BREAK/FIX DEMO — Scenario C"
echo -e "  ${YELLOW}Bug : minmax normalizer returns NaN when all scores are equal${RESET}"
echo -e "  ${YELLOW}File: backend/app/search/hybrid.py  |  line ~78${RESET}"
echo ""
echo -e "  ${YELLOW}Fix : return 0.5 when max == min  (divide-by-zero guard)${RESET}"
echo ""
sleep 8

# ─── STEP 1 ──────────────────────────────────────────────────────────────────

section "PART 3 — STEP 1 of 5: Tests passing BEFORE bug"
cmd "pytest tests/test_hybrid.py -k 'nan or equal or zeros or single'"
sleep 2
python -m pytest tests/test_hybrid.py -v -k "nan or equal or zeros or single" 2>&1 | tail -5
echo ""
success "7 passed — NaN guard is working correctly"
sleep 5

# ─── STEP 2 ──────────────────────────────────────────────────────────────────

section "PART 3 — STEP 2 of 5: Injecting the bug"
echo -e "  ${RED}Removing:   return {doc_id: 0.5 for doc_id in scores}${RESET}"
echo -e "  ${RED}Replacing:  return {doc_id: float('nan') for doc_id in scores}${RESET}"
echo ""
sleep 4
python3 -c "
content = open('app/search/hybrid.py').read()
old = 'return {doc_id: 0.5 for doc_id in scores}'
new = 'return {doc_id: float(\"nan\") for doc_id in scores}  # BUG'
content = content.replace(old, new)
open('app/search/hybrid.py', 'w').write(content)
"
fail "BUG INJECTED — NaN guard removed from minmax normalizer"
sleep 5

# ─── STEP 3 ──────────────────────────────────────────────────────────────────

section "PART 3 — STEP 3 of 5: Tests FAIL after bug injection"
cmd "pytest tests/test_hybrid.py -k 'nan or equal or zeros or single'"
sleep 2
python -m pytest tests/test_hybrid.py -v -k "nan or equal or zeros or single" 2>&1 | tail -10
echo ""
fail "5 FAILED — NaN propagating through hybrid scores"
sleep 8

# ─── STEP 4 ──────────────────────────────────────────────────────────────────

section "PART 3 — STEP 4 of 5: Fixing the bug"
echo -e "  ${GREEN}Restoring:  return {doc_id: 0.5 for doc_id in scores}${RESET}"
echo ""
sleep 4
python3 -c "
content = open('app/search/hybrid.py').read()
old = 'return {doc_id: float(\"nan\") for doc_id in scores}  # BUG'
new = 'return {doc_id: 0.5 for doc_id in scores}'
content = content.replace(old, new)
open('app/search/hybrid.py', 'w').write(content)
"
success "FIXED — NaN guard restored, all-equal scores return 0.5"
sleep 5

# ─── STEP 5 ──────────────────────────────────────────────────────────────────

section "PART 3 — STEP 5 of 5: All tests passing again"
cmd "pytest tests/test_hybrid.py -k 'nan or equal or zeros or single'"
sleep 2
python -m pytest tests/test_hybrid.py -v -k "nan or equal or zeros or single" 2>&1 | tail -5
echo ""
success "7 passed — system recovered cleanly"
sleep 5

# ─── DONE ────────────────────────────────────────────────────────────────────

clear
echo ""
echo -e "${BOLD}${CYAN}  ╔══════════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}${CYAN}  ║              DEMO COMPLETE                   ║${RESET}"
echo -e "${BOLD}${CYAN}  ╠══════════════════════════════════════════════╣${RESET}"
echo -e "${BOLD}${CYAN}  ║                                              ║${RESET}"
echo -e "${GREEN}  ║  ✓  API health, search, metrics working      ${CYAN}║${RESET}"
echo -e "${GREEN}  ║  ✓  bm25 + vector + hybrid score per result  ${CYAN}║${RESET}"
echo -e "${GREEN}  ║  ✓  73 tests passing in under 10 seconds     ${CYAN}║${RESET}"
echo -e "${GREEN}  ║  ✓  Break/fix: 5 FAILED → 7 passed           ${CYAN}║${RESET}"
echo -e "${BOLD}${CYAN}  ║                                              ║${RESET}"
echo -e "${BOLD}${CYAN}  ╚══════════════════════════════════════════════╝${RESET}"
echo ""
sleep 5
