# backend/app/search/bm25.py

import pickle
import json
import logging
import re
from pathlib import Path

from rank_bm25 import BM25Okapi

from app.models import Document, SearchResult
from app.ingest import _make_snippet

logger = logging.getLogger(__name__)

# replace these two lines at the top


# with absolute paths anchored to this file's location
_HERE      = Path(__file__).resolve().parent          # backend/app/search/
_ROOT      = _HERE.parent.parent.parent               # repo root
INDEX_FILE = _ROOT / "data/indexes/bm25/index.pkl"
META_FILE  = _ROOT / "data/indexes/bm25/meta.json"

# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------

def tokenize(text: str) -> list[str]:
    """Lowercase, strip punctuation, split on whitespace."""
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return text.split()


# ---------------------------------------------------------------------------
# BM25Index
# ---------------------------------------------------------------------------

class BM25Index:

    def __init__(self) -> None:
        self._bm25:    BM25Okapi | None = None
        self._docs:    list[Document]   = []
        self._is_built: bool            = False

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def build(self, docs: list[Document]) -> None:
        """Tokenize docs and fit the BM25 model."""
        if not docs:
            raise ValueError("Cannot build BM25 index from empty document list.")

        logger.info("Building BM25 index over %d docs…", len(docs))

        self._docs = docs
        corpus     = [tokenize(doc.text) for doc in docs]
        self._bm25 = BM25Okapi(corpus)
        self._is_built = True

        logger.info("BM25 index built.")

    # ------------------------------------------------------------------
    # Persist
    # ------------------------------------------------------------------

    def save(
        self,
        index_path: Path = INDEX_FILE,
        meta_path:  Path = META_FILE,
    ) -> None:
        if not self._is_built:
            raise RuntimeError("Index must be built before saving.")

        index_path.parent.mkdir(parents=True, exist_ok=True)

        with open(index_path, "wb") as f:
            pickle.dump({"bm25": self._bm25, "docs": self._docs}, f)

        meta = {
            "doc_count": len(self._docs),
            "categories": sorted({d.category for d in self._docs if d.category}),
        }
        meta_path.write_text(json.dumps(meta, indent=2))

        logger.info("BM25 index saved → %s", index_path)

    @classmethod
    def load(
        cls,
        index_path: Path = INDEX_FILE,
        meta_path:  Path = META_FILE,
    ) -> "BM25Index | bool":
        if not index_path.exists():
            logger.warning("BM25 index not found at %s", index_path)
            return False

        instance = cls()

        with open(index_path, "rb") as f:
            data = pickle.load(f)

        instance._bm25     = data["bm25"]
        instance._docs     = data["docs"]
        instance._is_built = True

        logger.info(
            "BM25 index loaded — %d docs from %s",
            len(instance._docs), index_path,
        )
        return instance

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def query(
        self,
        text:     str,
        top_k:    int = 10,
        filters:  dict | None = None,
    ) -> list[SearchResult]:
        if not self._is_built or self._bm25 is None:
            raise RuntimeError("Index is not built or loaded.")

        tokens = tokenize(text)
        raw_scores: list[float] = self._bm25.get_scores(tokens).tolist()

        # Pair scores with docs, apply optional category filter
        pairs = [
            (score, doc)
            for score, doc in zip(raw_scores, self._docs)
            if self._passes_filter(doc, filters)
        ]

        if not pairs:
            return []

        # Normalise to [0, 1]
        max_score = max(s for s, _ in pairs)
        min_score = min(s for s, _ in pairs)
        score_range = max_score - min_score or 1.0

        ranked = sorted(pairs, key=lambda x: x[0], reverse=True)[:top_k]

        return [
            SearchResult(
                doc_id=       doc.doc_id,
                title=        doc.title,
                chunk_index=  doc.chunk_index,
                text=         doc.text,
                snippet=      _make_snippet(doc.text),
                category=     doc.category,
                score=        round((score - min_score) / score_range, 6),
                bm25_score=   round((score - min_score) / score_range, 6),
                vector_score= 0.0,
            )
            for score, doc in ranked
        ]

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _passes_filter(doc: Document, filters: dict | None) -> bool:
        if not filters:
            return True
        if "category" in filters and doc.category != filters["category"]:
            return False
        return True

    def __len__(self) -> int:
        return len(self._docs)

    def __repr__(self) -> str:
        status = f"{len(self._docs)} docs" if self._is_built else "not built"
        return f"BM25Index({status})"