# backend/scripts/build_index.py

"""
One-shot pipeline: processed docs → BM25 index + Vector index.

Usage:
    python -m scripts.build_index
    python -m scripts.build_index --docs data/processed/docs.jsonl
    python -m scripts.build_index --docs data/processed/docs.jsonl \
                                  --bm25-dir data/indexes/bm25 \
                                  --vector-dir data/indexes/vector
"""

import json
import logging
import argparse
from pathlib import Path

from tqdm import tqdm

from app.models import Document
from app.search.bm25 import BM25Index
from app.search.vector import VectorIndex

logger = logging.getLogger(__name__)

DEFAULT_DOCS_PATH  = Path("data/processed/docs.jsonl")
DEFAULT_BM25_DIR   = Path("data/indexes/bm25")
DEFAULT_VECTOR_DIR = Path("data/indexes/vector")


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def load_documents(docs_path: Path) -> list[Document]:
    if not docs_path.exists():
        raise FileNotFoundError(
            f"Processed docs not found at {docs_path}. "
            "Run `python -m app.ingest` first."
        )

    docs: list[Document] = []
    bad  = 0

    with open(docs_path, encoding="utf-8") as f:
        lines = f.readlines()

    for i, line in enumerate(tqdm(lines, desc="Loading docs"), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            raw = json.loads(line)
            docs.append(Document(
                doc_id=      raw["doc_id"],
                title=       raw["title"],
                chunk_index= raw.get("chunk_index", 0),
                text=        raw["text"],
                token_count= len(raw["text"].split()),
                category=    raw.get("category"),
            ))
        except (json.JSONDecodeError, KeyError) as exc:
            logger.warning("Skipping malformed line %d: %s", i, exc)
            bad += 1

    logger.info(
        "Loaded %d documents (%d malformed lines skipped).",
        len(docs), bad,
    )
    return docs


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def build_bm25(docs: list[Document], output_dir: Path) -> None:
    logger.info("── Building BM25 index ──────────────────────────────")
    idx = BM25Index()
    idx.build(docs)
    idx.save(
        index_path= output_dir / "index.pkl",
        meta_path=  output_dir / "meta.json",
    )
    logger.info("BM25 index saved → %s", output_dir)


def build_vector(docs: list[Document], output_dir: Path) -> None:
    logger.info("── Building vector index ────────────────────────────")
    idx = VectorIndex()
    idx.build(docs)
    idx.save(
        index_path=  output_dir / "index.faiss",
        meta_path=   output_dir / "meta.json",
        id_map_path= output_dir / "id_map.json",
    )
    logger.info("Vector index saved → %s", output_dir)


def run_build(
    docs_path:  Path = DEFAULT_DOCS_PATH,
    bm25_dir:   Path = DEFAULT_BM25_DIR,
    vector_dir: Path = DEFAULT_VECTOR_DIR,
) -> None:
    docs = load_documents(docs_path)

    if not docs:
        raise ValueError("No documents loaded — cannot build indexes.")

    build_bm25(docs,   bm25_dir)
    build_vector(docs, vector_dir)

    logger.info(
        "✓ Both indexes built from %d documents.", len(docs)
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%H:%M:%S",
    )

    parser = argparse.ArgumentParser(description="Build BM25 + vector indexes")
    parser.add_argument(
        "--docs",       type=Path, default=DEFAULT_DOCS_PATH,
        help=f"Path to processed JSONL (default: {DEFAULT_DOCS_PATH})",
    )
    parser.add_argument(
        "--bm25-dir",   type=Path, default=DEFAULT_BM25_DIR,
        help=f"Output dir for BM25 index (default: {DEFAULT_BM25_DIR})",
    )
    parser.add_argument(
        "--vector-dir", type=Path, default=DEFAULT_VECTOR_DIR,
        help=f"Output dir for vector index (default: {DEFAULT_VECTOR_DIR})",
    )
    args = parser.parse_args()

    run_build(
        docs_path=  args.docs,
        bm25_dir=   args.bm25_dir,
        vector_dir= args.vector_dir,
    )


if __name__ == "__main__":
    main()