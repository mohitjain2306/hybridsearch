# backend/app/search/vector.py

import json
import logging
import hashlib
from datetime import datetime, timezone
from pathlib import Path

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

from app.models import Document, SearchResult
from app.ingest import _make_snippet

logger = logging.getLogger(__name__)

# replace these three lines at the top

# with absolute paths
_HERE       = Path(__file__).resolve().parent
_ROOT       = _HERE.parent.parent.parent
INDEX_FILE  = _ROOT / "data/indexes/vector/index.faiss"
META_FILE   = _ROOT / "data/indexes/vector/meta.json"
ID_MAP_FILE = _ROOT / "data/indexes/vector/id_map.json"

DEFAULT_MODEL = "all-MiniLM-L6-v2"


# ---------------------------------------------------------------------------
# VectorIndex
# ---------------------------------------------------------------------------

class VectorIndex:

    def __init__(self, model_name: str = DEFAULT_MODEL) -> None:
        self._model_name  = model_name
        self._model:  SentenceTransformer | None = None
        self._index:  faiss.IndexFlatIP | None   = None
        self._docs:   list[Document]             = []
        self._dim:    int | None                 = None
        self._is_built: bool                     = False

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def build(self, docs: list[Document]) -> None:
        if not docs:
            raise ValueError("Cannot build vector index from empty document list.")

        logger.info(
            "Building vector index over %d docs with model %s…",
            len(docs), self._model_name,
        )

        self._docs  = docs
        self._model = self._load_model()

        texts      = [doc.text for doc in docs]
        embeddings = self._encode(texts)

        self._dim   = embeddings.shape[1]
        self._index = faiss.IndexFlatIP(self._dim)
        self._index.add(embeddings)
        self._is_built = True

        logger.info(
            "Vector index built — %d vectors, dim=%d", len(docs), self._dim
        )

    # ------------------------------------------------------------------
    # Persist
    # ------------------------------------------------------------------

    def save(
        self,
        index_path:  Path = INDEX_FILE,
        meta_path:   Path = META_FILE,
        id_map_path: Path = ID_MAP_FILE,
    ) -> None:
        if not self._is_built:
            raise RuntimeError("Index must be built before saving.")

        index_path.parent.mkdir(parents=True, exist_ok=True)

        faiss.write_index(self._index, str(index_path))

        id_map = [
            {"position": i, "doc_id": doc.doc_id, "title": doc.title}
            for i, doc in enumerate(self._docs)
        ]
        id_map_path.write_text(json.dumps(id_map, indent=2))

        meta = {
            "model_name":   self._model_name,
            "dimension":    self._dim,
            "doc_count":    len(self._docs),
            "corpus_hash":  self._corpus_hash(),
            "built_at":     datetime.now(timezone.utc).isoformat(),
        }
        meta_path.write_text(json.dumps(meta, indent=2))

        logger.info("Vector index saved → %s", index_path)

    @classmethod
    def load(
        cls,
        index_path:  Path = INDEX_FILE,
        meta_path:   Path = META_FILE,
        id_map_path: Path = ID_MAP_FILE,
        model_name:  str  = DEFAULT_MODEL,
    ) -> "VectorIndex | bool":
        if not index_path.exists():
            logger.warning("Vector index not found at %s", index_path)
            return False

        # ── Validate meta before loading anything else ──────────────────
        if not meta_path.exists():
            raise RuntimeError(
                f"Index file found at {index_path} but meta.json is missing. "
                "The index may be corrupt — rebuild it."
            )

        meta = json.loads(meta_path.read_text())

        if meta["model_name"] != model_name:
            raise RuntimeError(
                f"Model mismatch: index was built with '{meta['model_name']}' "
                f"but loader was given '{model_name}'. "
                "Rebuild the index or pass the correct model name."
            )

        raw_index = faiss.read_index(str(index_path))
        actual_dim = raw_index.d

        if actual_dim != meta["dimension"]:
            raise RuntimeError(
                f"Dimension mismatch: meta.json records dim={meta['dimension']} "
                f"but the FAISS index has dim={actual_dim}. "
                "The index files are inconsistent — rebuild."
            )

        # ── Rehydrate docs from id_map ───────────────────────────────────
        if not id_map_path.exists():
            raise RuntimeError(
                f"id_map.json not found at {id_map_path}. "
                "The index may be corrupt — rebuild it."
            )

        id_map = json.loads(id_map_path.read_text())
        docs = [
            Document(
                doc_id=      entry["doc_id"],
                title=       entry["title"],
                chunk_index= 0,
                text=        "",          # text not stored in id_map; used for display only
                token_count= 0,
            )
            for entry in sorted(id_map, key=lambda x: x["position"])
        ]

        instance              = cls(model_name=model_name)
        instance._index       = raw_index
        instance._docs        = docs
        instance._dim         = actual_dim
        instance._is_built    = True

        logger.info(
            "Vector index loaded — %d vectors, dim=%d, model=%s",
            len(docs), actual_dim, model_name,
        )
        return instance

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def query(
        self,
        text:    str,
        top_k:   int = 10,
        filters: dict | None = None,
    ) -> list[SearchResult]:
        if not self._is_built or self._index is None:
            raise RuntimeError("Index is not built or loaded.")

        if self._model is None:
            self._model = self._load_model()

        query_vec = self._encode([text])                    # (1, dim)
        k_fetch   = min(len(self._docs), top_k * 5)        # over-fetch for filtering
        scores, indices = self._index.search(query_vec, k_fetch)

        results: list[SearchResult] = []

        for score, idx in zip(scores[0], indices[0]):
            if idx == -1:                                   # FAISS sentinel
                continue

            doc = self._docs[idx]

            if not self._passes_filter(doc, filters):
                continue

            results.append(
                SearchResult(
                    doc_id=       doc.doc_id,
                    title=        doc.title,
                    chunk_index=  doc.chunk_index,
                    text=         doc.text,
                    snippet=      _make_snippet(doc.text) if doc.text else "",
                    category=     doc.category,
                    score=        round(float(score), 6),
                    bm25_score=   0.0,
                    vector_score= round(float(score), 6),
                )
            )

            if len(results) >= top_k:
                break

        return results

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _load_model(self) -> SentenceTransformer:
        logger.info("Loading sentence-transformer model %s…", self._model_name)
        return SentenceTransformer(self._model_name)

    def _encode(self, texts: list[str]) -> np.ndarray:
        """Encode texts and L2-normalise so IndexFlatIP == cosine similarity."""
        model = self._model or self._load_model()
        embeddings = model.encode(
            texts,
            convert_to_numpy=True,
            show_progress_bar=False,
            normalize_embeddings=True,      # L2 norm → IP == cosine
        )
        return embeddings.astype(np.float32)

    def _corpus_hash(self) -> str:
        ids = "".join(doc.doc_id for doc in self._docs)
        return hashlib.md5(ids.encode()).hexdigest()

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
        if self._is_built:
            return f"VectorIndex(model={self._model_name}, docs={len(self._docs)}, dim={self._dim})"
        return f"VectorIndex(model={self._model_name}, not built)"