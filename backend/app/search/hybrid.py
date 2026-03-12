# backend/app/search/hybrid.py

import re
import logging
from app.models import Document, SearchResult, SearchRequest
from app.search.bm25 import BM25Index
from app.search.vector import VectorIndex

logger = logging.getLogger(__name__)

FETCH_K = 30


# ---------------------------------------------------------------------------
# Snippet helper
# ---------------------------------------------------------------------------

def _snippet(text: str, query: str, window: int = 150) -> str:
    """
    Return a ~window-char excerpt centred on the first query word match.
    Matched words are wrapped in **bold** markdown.
    Falls back to the first window chars if no match is found.
    """
    if not text:
        return ""

    words   = [w.strip() for w in query.lower().split() if w.strip()]
    pattern = re.compile(
        r"(" + "|".join(re.escape(w) for w in words) + r")",
        re.IGNORECASE,
    )

    # Find first match position for windowing
    match = pattern.search(text)
    if match:
        centre = match.start()
        half   = window // 2
        start  = max(0, centre - half)
        end    = min(len(text), start + window)
        # Slide start back if we're near the end
        start  = max(0, end - window)
        excerpt = text[start:end].strip()
    else:
        excerpt = text[:window].strip()

    # Bold all matched words in the excerpt
    highlighted = pattern.sub(r"**\1**", excerpt)

    # Add ellipsis markers
    prefix = "…" if (match and start > 0)      else ""
    suffix = "…" if len(text) > (start + window) else ""

    return f"{prefix}{highlighted}{suffix}"


# ---------------------------------------------------------------------------
# Score normalisation
# ---------------------------------------------------------------------------

def _minmax(scores: dict[str, float]) -> dict[str, float]:
    """
    Min-max normalise a {doc_id: score} dict to [0, 1].
    If all scores are equal (including all-zero), returns 0.5 for every key
    instead of NaN — avoids division-by-zero on degenerate BM25 results.
    """
    if not scores:
        return {}

    lo  = min(scores.values())
    hi  = max(scores.values())
    rng = hi - lo

    if rng == 0.0:
        return {doc_id: 0.5 for doc_id in scores}

    return {doc_id: (s - lo) / rng for doc_id, s in scores.items()}


# ---------------------------------------------------------------------------
# HybridSearch
# ---------------------------------------------------------------------------

class HybridSearch:

    def __init__(self, bm25: BM25Index, vector: VectorIndex) -> None:
        self._bm25   = bm25
        self._vector = vector

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def search(self, request: SearchRequest) -> list[SearchResult]:
        query   = request.query
        top_k   = request.top_k
        alpha   = request.alpha
        filters = request.filters

        # ── Fetch from both indexes ──────────────────────────────────────
        bm25_results   = self._bm25.query(query,   top_k=FETCH_K, filters=filters)
        vector_results = self._vector.query(query, top_k=FETCH_K, filters=filters)

        # ── Build raw score maps {doc_id: raw_score} ─────────────────────
        bm25_raw:   dict[str, float] = {r.doc_id: r.bm25_score   for r in bm25_results}
        vector_raw: dict[str, float] = {r.doc_id: r.vector_score for r in vector_results}

        # ── Union of all doc_ids ─────────────────────────────────────────
        all_ids = set(bm25_raw) | set(vector_raw)

        # ── Fill missing scores with 0.0 before normalisation ───────────
        bm25_filled:   dict[str, float] = {d: bm25_raw.get(d,   0.0) for d in all_ids}
        vector_filled: dict[str, float] = {d: vector_raw.get(d, 0.0) for d in all_ids}

        # ── Normalise each space independently ──────────────────────────
        bm25_norm   = _minmax(bm25_filled)
        vector_norm = _minmax(vector_filled)

        # ── Fuse ─────────────────────────────────────────────────────────
        # alpha=1.0 → pure BM25   alpha=0.0 → pure vector
        fused: dict[str, float] = {
            doc_id: alpha * bm25_norm[doc_id] + (1.0 - alpha) * vector_norm[doc_id]
            for doc_id in all_ids
        }

        # ── Build a lookup for result metadata ───────────────────────────
        meta: dict[str, SearchResult] = {
            r.doc_id: r
            for r in (*bm25_results, *vector_results)
        }

        # ── Sort and truncate ────────────────────────────────────────────
        ranked_ids = sorted(fused, key=lambda d: fused[d], reverse=True)[:top_k]

        results: list[SearchResult] = []
        for doc_id in ranked_ids:
            src = meta[doc_id]
            results.append(
                SearchResult(
                    doc_id=       doc_id,
                    title=        src.title,
                    chunk_index=  src.chunk_index,
                    text=         src.text,
                    snippet=      _snippet(src.text, query),
                    category=     src.category,
                    score=        round(fused[doc_id],              6),
                    bm25_score=   round(bm25_norm.get(doc_id, 0.0), 6),
                    vector_score= round(vector_norm.get(doc_id, 0.0), 6),
                )
            )

        logger.debug(
            "HybridSearch query=%r alpha=%.2f → %d results",
            query, alpha, len(results),
        )
        return results

    # ------------------------------------------------------------------
    # Repr
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"HybridSearch("
            f"bm25={len(self._bm25)} docs, "
            f"vector={len(self._vector)} docs)"
        )