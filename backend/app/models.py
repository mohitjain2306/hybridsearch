# backend/app/models.py

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
import uuid


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=512)
    top_k: int = Field(default=10, ge=1, le=100)
    alpha: float = Field(
        default=0.5, ge=0.0, le=1.0,
        description="0.0 = pure BM25, 1.0 = pure vector"
    )
    filters: Optional[dict] = Field(
        default=None,
        description="Optional metadata filters e.g. {'category': 'science'}"
    )


class SearchResult(BaseModel):
    doc_id: str
    title: str
    chunk_index: int
    text: str
    snippet: str = Field(description="Short preview of the result text")
    category: Optional[str] = Field(default=None)
    score: float
    bm25_score: float
    vector_score: float


class SearchResponse(BaseModel):
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    query: str
    alpha: float
    top_k: int
    result_count: int
    results: list[SearchResult]
    latency_ms: float


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------

class Document(BaseModel):
    doc_id: str
    title: str
    chunk_index: int
    text: str
    token_count: int
    category: Optional[str] = Field(default=None)


# ---------------------------------------------------------------------------
# Ingest
# ---------------------------------------------------------------------------

class IngestRequest(BaseModel):
    topics: list[str] = Field(..., min_length=1)
    max_articles: int = Field(default=50, ge=1, le=500)
    chunk_size: int = Field(default=200, ge=50, le=1000)
    chunk_overlap: int = Field(default=20, ge=0, le=100)


class IngestResponse(BaseModel):
    articles_fetched: int
    chunks_created: int
    duration_s: float


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

class QueryLog(BaseModel):
    id: Optional[int] = None
    request_id: str
    timestamp: datetime
    query: str
    alpha: float
    top_k: int
    latency_ms: float
    result_count: int
    filters: Optional[dict] = None
    error: Optional[str] = None      # ← add this


class StatsResponse(BaseModel):
    total_queries: int
    avg_latency_ms: float
    avg_alpha: float
    recent_logs: list[QueryLog]