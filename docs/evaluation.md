# docs/evaluation.md

# Evaluation

## Overview

The evaluation harness measures retrieval quality across five alpha values
by computing three standard IR metrics against a fixed set of 25 queries
with human-assignable relevance judgments.

---

## Ground-truth construction (`generate_qrels.py`)

Relevance judgments are stored in `eval/qrels.json` in the standard qrels
format:
```json
{
  "NASA space exploration missions": {
    "doc_0001_ab12cd34": 2,
    "doc_0003_ef56gh78": 1,
    "doc_0007_aa99bb11": 1
  }
}
```

**Grading scheme**

| Grade | Meaning | Assignment rule |
|---|---|---|
| 2 | Highly relevant | First 3 docs from matching category |
| 1 | Relevant | Docs 4–10 from matching category |
| 0 | Not relevant | All other documents (implicit) |

Each query is mapped to one of the 12 topic categories. Up to 10 documents
from that category are marked relevant, with the first three receiving
grade 2 on the assumption that earlier-fetched Wikipedia articles are more
topically central.

**Limitation:** Grades are assigned programmatically by category membership
and insertion order, not by human judgment. This makes the eval harness
useful for comparing alpha values against each other but the absolute metric
values should not be taken as ground-truth quality scores.

Regenerate qrels after re-ingesting:
```bash
python -m app.generate_qrels \
    --docs data/processed/docs.jsonl \
    --out  eval/qrels.json
```

---

## Metrics

### nDCG@k — Normalised Discounted Cumulative Gain

Measures ranking quality, giving more credit for relevant documents
appearing near the top of the result list. Penalises systems that bury
highly relevant documents lower in the ranking.
```
DCG@k  = Σ rel_i / log2(i + 1)   for i = 1..k
nDCG@k = DCG@k / IDCG@k
```

Where `IDCG@k` is the DCG of the ideal ranking. Score range: [0, 1].
Higher is better.

### Recall@k

Fraction of all relevant documents for a query that appear in the top-k
results. Does not penalise for irrelevant results in the top-k.
```
Recall@k = |relevant ∩ top-k| / |relevant|
```

Score range: [0, 1]. Higher is better.

### MRR — Mean Reciprocal Rank

Measures how high the first relevant document appears. Useful when users
are expected to click the first good result and stop.
```
RR  = 1 / rank_of_first_relevant_result
MRR = mean(RR) across queries
```

Score range: (0, 1]. Higher is better. Returns 0.0 if no relevant result
is found in the result list.

---

## Running evaluation
```bash
# Default: 5 alpha values, k=10, reads eval/qrels.json
python -m app.eval

# Custom parameters
python -m app.eval \
    --qrels eval/qrels.json \
    --k     10 \
    --alphas 0.0 0.1 0.2 0.3 0.4 0.5 0.6 0.7 0.8 0.9 1.0
```

Sample output:
```
──────────────────────────────────────────────────────
       alpha     nDCG@10    Recall@10         MRR
──────────────────────────────────────────────────────
        0.00      0.3821       0.2900      0.4102
        0.25      0.4103       0.3200      0.4418
        0.50      0.4387       0.3500      0.4731
        0.75      0.4201       0.3300      0.4523
        1.00      0.3644       0.2700      0.3899
──────────────────────────────────────────────────────

Best nDCG@10:    alpha=0.50  (0.4387)
Best Recall@10:  alpha=0.50  (0.3500)
Best MRR:        alpha=0.50  (0.4731)
```

---

## Output format (`data/metrics/experiments.csv`)
```
run,alpha,ndcg_at_k,recall_at_k,mrr,num_queries
1,0.0,0.3821,0.2900,0.4102,25
2,0.25,0.4103,0.3200,0.4418,25
3,0.5,0.4387,0.3500,0.4731,25
4,0.75,0.4201,0.3300,0.4523,25
5,1.0,0.3644,0.2700,0.3899,25
```

Each row is one alpha value evaluated across all 25 queries. The dashboard
Evaluation page reads this file directly to render the metric charts.

---

## Interpreting results

**alpha ≈ 0.5 typically wins** on this corpus because Wikipedia articles
contain consistent factual language (favouring BM25) but the queries are
phrased naturally and semantically (favouring vector). The optimal alpha is
corpus and query dependent — use the eval harness to find it empirically
for any new document set.

**nDCG > Recall** as the primary metric for this use case. Users see a
ranked list of 10 results — where the relevant results appear matters more
than whether every relevant document in the corpus was retrieved.

**Low absolute scores are expected** given the programmatic qrels
construction. The metrics are meaningful for comparing alpha values
relative to each other, not as absolute quality benchmarks.

---

## Adding new queries

Edit the `QUERIES` list in `generate_qrels.py`, add entries as
`("query text", "category")`, then re-run:
```bash
python -m app.generate_qrels
python -m app.eval
```

The 25 built-in queries cover all 12 categories and were chosen to have
clear category membership so the programmatic relevance assignment is
defensible.