# backend/app/dependencies.py

import sqlite3
import logging
from typing import Annotated

from fastapi import Depends, HTTPException, status

from app.search.hybrid import HybridSearch

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level holders — written once at startup, read-only after that.
# Never import these directly in routes; always go through the dependency.
# ---------------------------------------------------------------------------

_search_engine: HybridSearch | None = None


def set_search_engine(engine: HybridSearch) -> None:
    global _search_engine
    _search_engine = engine


def get_search_engine() -> HybridSearch:
    if _search_engine is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Search indexes are not loaded. "
                "Run `python -m app.scripts.build_index` then restart the API."
            ),
        )
    return _search_engine


# ---------------------------------------------------------------------------
# DB dependency — opens a connection per request, closes on teardown.
# Using a generator lets FastAPI call the finally block automatically.
# ---------------------------------------------------------------------------

def get_db():
    from app.db import get_connection          # local import avoids circular
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Annotated aliases — import these in route files for cleaner signatures.
# ---------------------------------------------------------------------------

SearchEngineDep = Annotated[HybridSearch,    Depends(get_search_engine)]
DBDep           = Annotated[sqlite3.Connection, Depends(get_db)]