# docs/decisions.md

# Architectural Decision Records

## ADR-001 — BM25 for keyword search

**Decision:** Use `rank-bm25` (BM25Okapi variant).

**Rationale:** BM25 is the standard strong baseline for keyword retrieval.
BM25Okapi applies term frequency saturation and document length
normalisation, making it robust across documents of varying length — which
matters here since Wikipedia articles are chunked but still vary
considerably. The `rank-bm25` library has no C dependencies, installs
cleanly on macOS with CPU-only Python, and is fast enough for a corpus of a
few hundred documents without needing an inverted index on disk.

**Alternatives considered:** TF-IDF (weaker, no length normalisation),
Elasticsearch (operational overhead far exceeds project scope),
Whoosh (pure Python but slower and less maintained).

---

## ADR-002 — FAISS IndexFlatIP for vector search

**Decision:** Use `faiss-cpu` with `IndexFlatIP` (flat inner product).

**Rationale:** `IndexFlatIP` performs exact nearest-neighbour search with no
approximation error. For a corpus of ~300 documents the brute-force scan is
fast enough that approximate methods (IVF, HNSW) would add complexity
without any meaningful latency benefit. L2-normalising embeddings before
insertion makes inner product equivalent to cosine similarity, which is the
correct similarity measure for `sentence-transformers` models.

**Alternatives considered:** `IndexFlatL2` (works but requires different
normalisation reasoning), `IndexIVFFlat` (faster at scale but requires a
training step and introduces recall loss), `chromadb` / `qdrant` (add a
server dependency).

---

## ADR-003 — all-MiniLM-L6-v2 as the embedding model

**Decision:** Use `sentence-transformers/all-MiniLM-L6-v2`.

**Rationale:** 384-dimensional embeddings strike the right balance for this
project — small enough that FAISS search and embedding generation are fast
on CPU, accurate enough for general-domain Wikipedia content. The model
is part of the `sentence-transformers` default model hub and downloads
automatically. It consistently scores well on MTEB benchmarks for
retrieval tasks despite its small size.

**Alternatives considered:** `all-mpnet-base-v2` (768 dims, stronger but
twice the memory and inference time), `multi-qa-MiniLM-L6-cos-v1`
(query-tuned variant — marginal gain for this use case),
OpenAI embeddings (requires API key and network call, breaks CPU-only
constraint).

---

## ADR-004 — Linear interpolation for score fusion

**Decision:** Fuse BM25 and vector scores as
`alpha × bm25_norm + (1 − alpha) × vector_norm`.

**Rationale:** Linear interpolation is interpretable and directly
controllable — alpha has a clear meaning (contribution weight) that users
can reason about. Both score spaces are independently min-max normalised to
[0, 1] before fusion so the blend is dimensionally consistent regardless
of the raw score magnitudes of each system.

**Alternatives considered:** Reciprocal Rank Fusion (RRF) — rank-based,
does not require normalisation, robust to score scale differences. RRF was
deliberately kept out of scope to keep the alpha parameter meaningful;
adding it as a `method` toggle is a clean follow-on.

**Known limitation:** Min-max normalisation is sensitive to outliers — a
single very high-scoring document compresses all other scores toward zero.
For a ~300-doc corpus this is acceptable; at larger scale a percentile-based
normalisation would be preferable.

---

## ADR-005 — SQLite for query logging

**Decision:** Use the stdlib `sqlite3` module with a versioned schema.

**Rationale:** Query logs are append-heavy and read only for dashboard
queries — SQLite handles this workload easily. No external process is
needed, the database is a single file in `data/`, and the stdlib driver
means zero additional dependencies. Schema migrations are handled by a
`schema_meta` version table so the log file survives code changes without
manual intervention.

**Alternatives considered:** PostgreSQL (operational overhead), ClickHouse
(analytics-optimised but far exceeds scope), plain JSON lines (no
queryable structure for the dashboard aggregations).

---

## ADR-006 — FastAPI + uvicorn

**Decision:** Use FastAPI with uvicorn for the API layer.

**Rationale:** FastAPI's dependency injection system (`Depends`) is the
right tool for injecting the search engine and DB connection into routes
without globals. Pydantic v2 integration means request/response validation
is free. Async support lets DB writes happen in a thread pool without
blocking search responses. Auto-generated OpenAPI docs at `/docs` are
useful during development.

**Alternatives considered:** Flask (no native async, no DI), Django REST
Framework (too heavy), aiohttp (lower level, more boilerplate).

---

## ADR-007 — Graded relevance in qrels

**Decision:** Use grades 2 (highly relevant) and 1 (relevant) rather than
binary 0/1 judgments.

**Rationale:** Graded relevance makes nDCG a more informative metric. With
binary relevance, nDCG degrades toward a less discriminative measure because
all relevant documents are equally weighted regardless of rank. Assigning
grade 2 to the first three documents per category (most canonical articles)
and grade 1 to the rest encodes a reasonable quality signal without
requiring manual annotation.

**Limitation:** Relevance grades are assigned by insertion order in
`docs.jsonl`, not by human judgment. This is a known limitation — the eval
harness is structurally correct and the metrics are meaningful for comparing
alpha values against each other, but absolute metric values should not be
interpreted as ground-truth quality scores.