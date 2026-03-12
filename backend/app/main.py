# backend/app/main.py

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.db import init_db
from app.dependencies import set_search_engine
from app.search.bm25 import BM25Index
from app.search.vector import VectorIndex
from app.search.hybrid import HybridSearch
from app.api import search, ingest, stats

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------

limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])

# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ─────────────────────────────────────────────────────────
    logger.info("Starting up Knowledge Search API…")

    # 1. Initialise DB / run migrations
    try:
        init_db()
        logger.info("Database initialised.")
    except Exception as exc:
        logger.error("DB initialisation failed: %s", exc)
        raise

    # 2. Load indexes — non-fatal if missing
    bm25_index   = BM25Index.load()
    vector_index = VectorIndex.load()

    indexes_ok = (
        isinstance(bm25_index,   BM25Index)   and bm25_index._is_built and
        isinstance(vector_index, VectorIndex) and vector_index._is_built
    )

    if indexes_ok:
        engine = HybridSearch(bm25_index, vector_index)
        set_search_engine(engine)
        logger.info(
            "HybridSearch ready — BM25: %d docs, Vector: %d docs.",
            len(bm25_index), len(vector_index),
        )
    else:
        missing = []
        if not isinstance(bm25_index, BM25Index):
            missing.append("BM25")
        if not isinstance(vector_index, VectorIndex):
            missing.append("Vector")
        logger.warning(
            "⚠️  Search indexes not found (%s). "
            "API will start but /search will return 503 until indexes are built. "
            "Run: python -m scripts.build_index",
            ", ".join(missing),
        )

    logger.info("Startup complete.")
    yield

    # ── Shutdown ─────────────────────────────────────────────────────────
    logger.info("Shutting down Knowledge Search API.")


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    app = FastAPI(
        title="Knowledge Search API",
        version="1.0.0",
        description=(
            "Hybrid BM25 + semantic search over Wikipedia articles. "
            "Tune retrieval with the alpha parameter: "
            "1.0 = pure keyword, 0.0 = pure semantic."
        ),
        lifespan=lifespan,
    )

    # ── Middleware ────────────────────────────────────────────────────────

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:8501",      # Streamlit default
            "http://127.0.0.1:8501",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Rate limiting ─────────────────────────────────────────────────────

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # ── Routers ───────────────────────────────────────────────────────────

    app.include_router(search.router, prefix="/api/v1", tags=["search"])
    app.include_router(ingest.router, prefix="/api/v1", tags=["ingest"])
    app.include_router(stats.router,  prefix="/api/v1", tags=["stats"])

    return app


app = create_app()