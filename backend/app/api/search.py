# backend/app/api/search.py

import time
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.models import SearchRequest, SearchResponse, QueryLog
from app.dependencies import SearchEngineDep
from app.db import log_query

# replace



# with


logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)
router  = APIRouter()


@router.post("/search", response_model=SearchResponse)
@limiter.limit("100/minute")
async def search(request: Request, request_data: SearchRequest, engine: SearchEngineDep):
    response: SearchResponse | None = None
    error:    str | None            = None
    t_start = time.perf_counter()

    try:
        results  = engine.search(request_data)
        latency  = (time.perf_counter() - t_start) * 1000

        response = SearchResponse(
            query=        request_data.query,
            alpha=        request_data.alpha,
            top_k=        request_data.top_k,
            result_count= len(results),
            results=      results,
            latency_ms=   round(latency, 2),
        )
        return response

    except Exception as exc:
        latency = (time.perf_counter() - t_start) * 1000
        error   = str(exc)
        logger.exception("Search failed for query %r", request_data.query)
        raise

    finally:
        latency_ms   = round((time.perf_counter() - t_start) * 1000, 2)
        result_count = len(response.results) if response else 0

        log = QueryLog(
            request_id=   response.request_id if response else "error",
            timestamp=    datetime.now(timezone.utc),
            query=        request_data.query,
            alpha=        request_data.alpha,
            top_k=        request_data.top_k,
            latency_ms=   latency_ms,
            result_count= result_count,
            filters=      request_data.filters,
            error=        error,
        )
        await log_query(log)