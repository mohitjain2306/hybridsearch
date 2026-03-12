# backend/app/api/stats.py

import subprocess
import logging
import statistics
from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import PlainTextResponse

from app.models import StatsResponse
from app.db import get_stats, get_logs_for_eval
from app.dependencies import _search_engine

logger = logging.getLogger(__name__)
router  = APIRouter()


def _git_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=3,
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def _percentile(data: list[float], pct: float) -> float:
    if not data:
        return 0.0
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * pct / 100
    lo, hi = int(k), min(int(k) + 1, len(sorted_data) - 1)
    return round(sorted_data[lo] + (sorted_data[hi] - sorted_data[lo]) * (k - lo), 2)


# ---------------------------------------------------------------------------
# GET /stats
# ---------------------------------------------------------------------------

@router.get("/stats", response_model=StatsResponse)
async def stats():
    return get_stats()


# ---------------------------------------------------------------------------
# GET /logs
# ---------------------------------------------------------------------------

@router.get("/logs")
async def logs(limit: int = Query(default=100, ge=1, le=1000)):
    all_logs = get_logs_for_eval()
    return {
        "count": len(all_logs[:limit]),
        "logs":  [log.model_dump() for log in all_logs[:limit]],
    }


# ---------------------------------------------------------------------------
# GET /metrics  (Prometheus-style plain text)
# ---------------------------------------------------------------------------

@router.get("/metrics", response_class=PlainTextResponse)
async def metrics():
    all_logs    = get_logs_for_eval()
    total       = len(all_logs)
    zero_result = sum(1 for log in all_logs if log.result_count == 0)
    latencies   = [log.latency_ms for log in all_logs if log.error is None]

    p50 = _percentile(latencies, 50)
    p95 = _percentile(latencies, 95)

    lines = [
        "# HELP search_requests_total Total number of search requests",
        "# TYPE search_requests_total counter",
        f"search_requests_total {total}",
        "",
        "# HELP search_zero_results_total Searches that returned no results",
        "# TYPE search_zero_results_total counter",
        f"search_zero_results_total {zero_result}",
        "",
        "# HELP search_latency_p50_ms 50th percentile search latency in ms",
        "# TYPE search_latency_p50_ms gauge",
        f"search_latency_p50_ms {p50}",
        "",
        "# HELP search_latency_p95_ms 95th percentile search latency in ms",
        "# TYPE search_latency_p95_ms gauge",
        f"search_latency_p95_ms {p95}",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------

@router.get("/health")
async def health():
    stats_data = get_stats()
    return {
        "status":               "ok",
        "version":              "1.0.0",
        "git_commit":           _git_commit(),
        "indexes_loaded":       _search_engine is not None,
        "total_queries_served": stats_data.total_queries,
    }