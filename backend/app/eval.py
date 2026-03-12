# backend/app/eval.py

"""
Evaluation harness — computes nDCG@k, Recall@k, MRR across alpha values.

Usage:
    python -m app.eval
    python -m app.eval --qrels eval/qrels.json --k 10 --alphas 0.0 0.25 0.5 0.75 1.0
"""

import json
import logging
import argparse
import statistics
from pathlib import Path
from itertools import product as iterproduct

import numpy as np

from app.models import SearchRequest
from app.search.bm25 import BM25Index
from app.search.vector import VectorIndex
from app.search.hybrid import HybridSearch

logger = logging.getLogger(__name__)

DEFAULT_QRELS_PATH = Path("eval/qrels.json")
DEFAULT_K          = 10
DEFAULT_ALPHAS     = [0.0, 0.25, 0.5, 0.75, 1.0]


# ---------------------------------------------------------------------------
# Metric implementations
# ---------------------------------------------------------------------------

def _dcg(relevances: list[float]) -> float:
    """Discounted Cumulative Gain."""
    return sum(
        rel / np.log2(rank + 2)
        for rank, rel in enumerate(relevances)
    )


def ndcg_at_k(ranked_doc_ids: list[str], qrel: dict[str, int], k: int) -> float:
    """
    nDCG@k — normalised discounted cumulative gain.
    qrel maps doc_id → relevance grade (typically 0, 1, 2).
    """
    ranked_rels  = [qrel.get(doc_id, 0) for doc_id in ranked_doc_ids[:k]]
    ideal_rels   = sorted(qrel.values(), reverse=True)[:k]

    dcg  = _dcg(ranked_rels)
    idcg = _dcg([float(r) for r in ideal_rels])

    return round(dcg / idcg, 4) if idcg > 0 else 0.0


def recall_at_k(ranked_doc_ids: list[str], qrel: dict[str, int], k: int) -> float:
    """
    Recall@k — fraction of relevant docs found in top-k.
    A doc is considered relevant if its grade > 0.
    """
    relevant   = {doc_id for doc_id, grade in qrel.items() if grade > 0}
    if not relevant:
        return 0.0

    retrieved  = set(ranked_doc_ids[:k])
    hits       = relevant & retrieved

    return round(len(hits) / len(relevant), 4)


def mrr(ranked_doc_ids: list[str], qrel: dict[str, int]) -> float:
    """
    Mean Reciprocal Rank — reciprocal of rank of first relevant result.
    Returns 0.0 if no relevant result is found.
    """
    for rank, doc_id in enumerate(ranked_doc_ids, start=1):
        if qrel.get(doc_id, 0) > 0:
            return round(1.0 / rank, 4)
    return 0.0


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------

class Evaluator:

    def __init__(
        self,
        engine:     HybridSearch,
        qrels_path: Path = DEFAULT_QRELS_PATH,
        k:          int  = DEFAULT_K,
    ) -> None:
        self._engine     = engine
        self._k          = k
        self._qrels      = self._load_qrels(qrels_path)

    @staticmethod
    def _load_qrels(path: Path) -> dict[str, dict[str, int]]:
        """
        Load qrels from JSON.
        Format: { "query text": { "doc_id": relevance_grade, … }, … }
        """
        if not path.exists():
            raise FileNotFoundError(
                f"qrels file not found at {path}. "
                "Run `python -m app.generate_qrels` first."
            )
        data = json.loads(path.read_text(encoding="utf-8"))
        logger.info("Loaded %d queries from %s", len(data), path)
        return data

    def evaluate_alpha(self, alpha: float) -> dict:
        """Run all queries at a given alpha and return aggregated metrics."""
        ndcg_scores:   list[float] = []
        recall_scores: list[float] = []
        mrr_scores:    list[float] = []

        for query_text, qrel in self._qrels.items():
            request = SearchRequest(
                query= query_text,
                top_k= self._k,
                alpha= alpha,
            )
            results      = self._engine.search(request)
            ranked_ids   = [r.doc_id for r in results]

            ndcg_scores.append(  ndcg_at_k(ranked_ids, qrel, self._k))
            recall_scores.append(recall_at_k(ranked_ids, qrel, self._k))
            mrr_scores.append(   mrr(ranked_ids, qrel))

        return {
            "alpha":        alpha,
            "ndcg_at_k":    round(statistics.mean(ndcg_scores),   4),
            "recall_at_k":  round(statistics.mean(recall_scores), 4),
            "mrr":          round(statistics.mean(mrr_scores),    4),
            "num_queries":  len(self._qrels),
        }

    def run(self, alphas: list[float] = DEFAULT_ALPHAS) -> list[dict]:
        """Evaluate across all alpha values and return sorted results."""
        rows = []
        for alpha in sorted(alphas):
            logger.info("Evaluating alpha=%.2f…", alpha)
            row = self.evaluate_alpha(alpha)
            rows.append(row)
            logger.info(
                "  alpha=%.2f  nDCG@%d=%.4f  Recall@%d=%.4f  MRR=%.4f",
                alpha, self._k, row["ndcg_at_k"],
                self._k, row["recall_at_k"], row["mrr"],
            )
        return rows


# ---------------------------------------------------------------------------
# Report printer
# ---------------------------------------------------------------------------

def print_report(rows: list[dict], k: int) -> None:
    col_w = 12
    header = (
        f"{'alpha':>{col_w}}"
        f"{'nDCG@' + str(k):>{col_w}}"
        f"{'Recall@' + str(k):>{col_w}}"
        f"{'MRR':>{col_w}}"
        f"{'Queries':>{col_w}}"
    )
    sep = "─" * len(header)

    print(f"\n{sep}")
    print(header)
    print(sep)
    for row in rows:
        print(
            f"{row['alpha']:>{col_w}.2f}"
            f"{row['ndcg_at_k']:>{col_w}.4f}"
            f"{row['recall_at_k']:>{col_w}.4f}"
            f"{row['mrr']:>{col_w}.4f}"
            f"{row['num_queries']:>{col_w}}"
        )
    print(sep)

    best_ndcg   = max(rows, key=lambda r: r["ndcg_at_k"])
    best_recall = max(rows, key=lambda r: r["recall_at_k"])
    best_mrr    = max(rows, key=lambda r: r["mrr"])

    print(f"\nBest nDCG@{k}:    alpha={best_ndcg['alpha']:.2f}  ({best_ndcg['ndcg_at_k']:.4f})")
    print(f"Best Recall@{k}:  alpha={best_recall['alpha']:.2f}  ({best_recall['recall_at_k']:.4f})")
    print(f"Best MRR:        alpha={best_mrr['alpha']:.2f}  ({best_mrr['mrr']:.4f})\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%H:%M:%S",
    )

    parser = argparse.ArgumentParser(description="Evaluate hybrid search")
    parser.add_argument(
        "--qrels",  type=Path,  default=DEFAULT_QRELS_PATH,
        help=f"Path to qrels JSON (default: {DEFAULT_QRELS_PATH})",
    )
    parser.add_argument(
        "--k",      type=int,   default=DEFAULT_K,
        help=f"Cutoff for nDCG and Recall (default: {DEFAULT_K})",
    )
    parser.add_argument(
        "--alphas", type=float, nargs="+", default=DEFAULT_ALPHAS,
        help="Alpha values to evaluate (default: 0.0 0.25 0.5 0.75 1.0)",
    )
    args = parser.parse_args()

    # Load indexes
    bm25_index   = BM25Index.load()
    vector_index = VectorIndex.load()

    if not isinstance(bm25_index, BM25Index) or not isinstance(vector_index, VectorIndex):
        raise SystemExit(
            "Indexes not found. Run `python -m scripts.build_index` first."
        )

    engine    = HybridSearch(bm25_index, vector_index)
    evaluator = Evaluator(engine, qrels_path=args.qrels, k=args.k)
    rows      = evaluator.run(alphas=args.alphas)

    print_report(rows, args.k)


if __name__ == "__main__":
    main()