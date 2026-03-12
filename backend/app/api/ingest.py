# backend/app/api/ingest.py

import time
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, status

from app.models import IngestRequest, IngestResponse
from app.ingest import run_ingest

logger = logging.getLogger(__name__)
router  = APIRouter()

DEFAULT_INPUT_DIR  = Path("data/raw")
DEFAULT_OUTPUT_DIR = Path("data/processed")



@router.post("/ingest", response_model=IngestResponse)
async def ingest(request: IngestRequest):
    logger.info(
        "Ingest triggered — topics: %s, max_articles: %d",
        request.topics, request.max_articles,
    )

    t_start = time.perf_counter()

    try:
        total_written = run_ingest(
            input_dir=  DEFAULT_INPUT_DIR,
            output_dir= DEFAULT_OUTPUT_DIR,
            categories= request.topics,        # ← pass through
        )
    except Exception as exc:
        logger.exception("Ingest pipeline failed.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ingest failed: {exc}",
        ) from exc

    duration = round(time.perf_counter() - t_start, 2)
    logger.info("Ingest complete — %d docs written in %.2fs", total_written, duration)

    return IngestResponse(
        articles_fetched= total_written,
        chunks_created=   total_written,
        duration_s=       duration,
    )