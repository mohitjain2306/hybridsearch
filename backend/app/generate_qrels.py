# backend/app/generate_qrels.py

"""
Generate ground-truth relevance judgments (qrels) for evaluation.

Reads data/processed/docs.jsonl, groups doc_ids by category, then maps
each query to its category and assigns up to 10 relevant doc_ids.

Output format (eval/qrels.json):
{
  "NASA space exploration": {
    "doc_0001_ab12cd34": 2,
    "doc_0002_ef56gh78": 1,
    ...
  },
  ...
}

Relevance grades:
  2 — highly relevant  (first 3 docs from category)
  1 — relevant         (remaining docs up to limit)

Usage:
    python -m app.generate_qrels
    python -m app.generate_qrels --docs data/processed/docs.jsonl \
                                  --out eval/qrels.json \
                                  --limit 10
"""

import json
import logging
import argparse
from collections import defaultdict
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_DOCS_PATH  = Path("data/processed/docs.jsonl")
DEFAULT_OUTPUT     = Path("eval/qrels.json")
DEFAULT_LIMIT      = 10

# ---------------------------------------------------------------------------
# Query catalogue  (query_text → category)
# ---------------------------------------------------------------------------

QUERIES: list[tuple[str, str]] = [
    # q01 — space
    ("NASA space exploration missions",                         "space"),
    # q02 — space
    ("black holes and gravitational waves",                     "space"),
    # q03 — medicine
    ("cancer treatment advances immunotherapy",                 "medicine"),
    # q04 — medicine
    ("antibiotic resistance bacterial infections",              "medicine"),
    # q05 — technology
    ("machine learning algorithms neural networks",             "technology"),
    # q06 — technology
    ("quantum computing cryptography applications",             "technology"),
    # q07 — science
    ("CRISPR gene editing DNA repair",                          "science"),
    # q08 — science
    ("climate change greenhouse gas emissions",                 "science"),
    # q09 — history
    ("causes and consequences of World War II",                 "history"),
    # q10 — history
    ("Roman Empire expansion decline fall",                     "history"),
    # q11 — geography
    ("Amazon rainforest deforestation biodiversity",            "geography"),
    # q12 — economics
    ("inflation monetary policy central banks",                 "economics"),
    # q13 — sports
    ("Olympic Games history athletic records",                  "sports"),
    # q14 — sports
    ("Formula One racing engineering aerodynamics",             "sports"),
    # q15 — culture
    ("Renaissance art architecture Florence",                   "culture"),
    # q16 — medicine
    ("vaccine development mRNA immunology",                     "medicine"),
    # q17 — technology
    ("electric vehicles battery technology range",              "technology"),
    # q18 — science
    ("quantum mechanics wave particle duality",                 "science"),
    # q19 — history
    ("Silk Road trade routes ancient civilisations",            "history"),
    # q20 — geography
    ("Himalayan mountain formation tectonic plates",            "geography"),
    # q21 — economics
    ("globalisation international trade supply chains",         "economics"),
    # q22 — sports
    ("football World Cup tournament history",                   "sports"),
    # q23 — society
    ("social media impact mental health democracy",             "society"),
    # q24 — general
    ("human consciousness perception decision making",          "general"),
    # q25 — space
    ("exoplanets habitable zone stellar classification",        "space"),
]


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def load_docs_by_category(docs_path: Path) -> dict[str, list[str]]:
    """
    Read docs.jsonl and return {category: [doc_id, …]} mapping.
    Preserves insertion order — earlier docs get higher relevance grades.
    """
    if not docs_path.exists():
        raise FileNotFoundError(
            f"Processed docs not found at {docs_path}. "
            "Run `python -m app.ingest` first."
        )

    by_category: dict[str, list[str]] = defaultdict(list)
    total = 0
    bad   = 0

    with open(docs_path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                doc      = json.loads(line)
                doc_id   = doc["doc_id"]
                category = doc.get("category", "general")
                by_category[category].append(doc_id)
                total += 1
            except (json.JSONDecodeError, KeyError) as exc:
                logger.warning("Skipping malformed line %d: %s", lineno, exc)
                bad += 1

    logger.info(
        "Loaded %d docs across %d categories (%d bad lines skipped).",
        total, len(by_category), bad,
    )
    for cat, ids in sorted(by_category.items()):
        logger.info("  %-12s  %d docs", cat, len(ids))

    return dict(by_category)


# ---------------------------------------------------------------------------
# qrels builder
# ---------------------------------------------------------------------------

def build_qrels(
    by_category: dict[str, list[str]],
    queries:     list[tuple[str, str]] = QUERIES,
    limit:       int                   = DEFAULT_LIMIT,
) -> dict[str, dict[str, int]]:
    """
    For each (query, category) pair, assign relevance grades to the first
    `limit` doc_ids from that category:
        grade 2 — top-3 docs   (highly relevant)
        grade 1 — docs 4..limit (relevant)

    Queries whose category has no docs get an empty judgment dict and a
    warning — the eval harness handles empty qrels gracefully.
    """
    qrels: dict[str, dict[str, int]] = {}

    for query_text, category in queries:
        doc_ids = by_category.get(category, [])

        if not doc_ids:
            logger.warning(
                "No docs found for category %r — query %r will have empty qrel.",
                category, query_text,
            )
            qrels[query_text] = {}
            continue

        candidates = doc_ids[:limit]
        judgment: dict[str, int] = {}

        for rank, doc_id in enumerate(candidates):
            grade         = 2 if rank < 3 else 1
            judgment[doc_id] = grade

        qrels[query_text] = judgment
        logger.debug(
            "  %-50s  category=%-12s  relevant_docs=%d",
            query_text, category, len(judgment),
        )

    return qrels


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def run_generate_qrels(
    docs_path:   Path = DEFAULT_DOCS_PATH,
    output_path: Path = DEFAULT_OUTPUT,
    limit:       int  = DEFAULT_LIMIT,
) -> Path:
    by_category = load_docs_by_category(docs_path)
    qrels       = build_qrels(by_category, limit=limit)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(qrels, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    total_queries   = len(qrels)
    total_judgments = sum(len(v) for v in qrels.values())
    empty_queries   = sum(1 for v in qrels.values() if not v)

    logger.info("─" * 50)
    logger.info("qrels written → %s", output_path)
    logger.info("  queries:          %d", total_queries)
    logger.info("  total judgments:  %d", total_judgments)
    logger.info("  avg per query:    %.1f", total_judgments / max(total_queries, 1))
    if empty_queries:
        logger.warning("  empty qrels:    %d (category had no docs)", empty_queries)
    logger.info("─" * 50)

    return output_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%H:%M:%S",
    )

    parser = argparse.ArgumentParser(
        description="Generate qrels for hybrid search evaluation"
    )
    parser.add_argument(
        "--docs",  type=Path, default=DEFAULT_DOCS_PATH,
        help=f"Processed docs JSONL (default: {DEFAULT_DOCS_PATH})",
    )
    parser.add_argument(
        "--out",   type=Path, default=DEFAULT_OUTPUT,
        help=f"Output path for qrels.json (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--limit", type=int,  default=DEFAULT_LIMIT,
        help=f"Max relevant docs per query (default: {DEFAULT_LIMIT})",
    )
    args = parser.parse_args()

    out = run_generate_qrels(args.docs, args.out, args.limit)
    print(f"\n✓ qrels written → {out}")


if __name__ == "__main__":
    main()