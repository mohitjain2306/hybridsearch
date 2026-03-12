# backend/tests/conftest.py

import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock

from app.models import Document, SearchResult, SearchResponse
from app.search.bm25 import BM25Index
from app.search.hybrid import HybridSearch


# ---------------------------------------------------------------------------
# Shared toy corpus
# ---------------------------------------------------------------------------

SPACE_TEXT = (
    "The space shuttle Columbia launched from Kennedy Space Center. "
    "Astronauts performed experiments in orbit around Earth. "
    "NASA engineers monitored the spacecraft systems during the mission."
)

HOCKEY_TEXT = (
    "The ice hockey team scored three goals in the final period. "
    "The goalie made several impressive saves throughout the game. "
    "Fans cheered as the puck crossed the line in overtime."
)

MEDICINE_TEXT = (
    "Penicillin was the first antibiotic discovered by Alexander Fleming. "
    "The drug revolutionised treatment of bacterial infections worldwide. "
    "Modern medicine relies heavily on antibiotics to fight disease."
)


@pytest.fixture
def corpus() -> list[Document]:
    return [
        Document(
            doc_id="doc_0001_aa111111",
            title="Space Shuttle",
            chunk_index=0,
            text=SPACE_TEXT,
            token_count=len(SPACE_TEXT.split()),
            category="space",
        ),
        Document(
            doc_id="doc_0002_bb222222",
            title="Ice Hockey",
            chunk_index=0,
            text=HOCKEY_TEXT,
            token_count=len(HOCKEY_TEXT.split()),
            category="sports",
        ),
        Document(
            doc_id="doc_0003_cc333333",
            title="Penicillin",
            chunk_index=0,
            text=MEDICINE_TEXT,
            token_count=len(MEDICINE_TEXT.split()),
            category="medicine",
        ),
    ]


@pytest.fixture
def built_bm25(corpus) -> BM25Index:
    idx = BM25Index()
    idx.build(corpus)
    return idx


@pytest.fixture
def mock_engine():
    """A HybridSearch mock that returns one fake result."""
    engine = MagicMock(spec=HybridSearch)
    engine.search.return_value = [
        SearchResult(
            doc_id="doc_0001_aa111111",
            title="Space Shuttle",
            chunk_index=0,
            text=SPACE_TEXT,
            snippet="NASA space shuttle launched",
            category="space",
            score=0.9,
            bm25_score=0.85,
            vector_score=0.95,
        )
    ]
    return engine


@pytest.fixture
def test_client(mock_engine):
    """FastAPI TestClient with indexes mocked out."""
    from app.main import create_app
    from app import dependencies

    app = create_app()
    dependencies.set_search_engine(mock_engine)

    with TestClient(app) as client:
        yield client
