# docs/break_fix_log.md

# Break / Fix Log

This document records three intentional failure scenarios introduced during
development to validate error handling, schema resilience, and scoring
correctness. Each scenario has a break commit, observed symptoms, and a fix
commit.

---

## Scenario A — Semantic index mismatch (model name + dimension)

### How I broke it

Edited `data/indexes/vector/meta.json` directly and changed two fields:
- `model_name`: `"all-MiniLM-L6-v2"` → `"wrong-model"`
- `dimension`: `384` → `999`

The FAISS index on disk was not rebuilt — only the metadata was corrupted.

### What happened

On next API startup, `VectorIndex.load()` read `meta.json` first and
compared the stored model name against the expected model name. It raised:
```
RuntimeError: Model mismatch: index was built with 'wrong-model'
but loader was given 'all-MiniLM-L6-v2'.
Rebuild the index or pass the correct model name.
```

The API lifespan caught this during startup. BM25 loaded fine but vector
index failed, so `HybridSearch` was never registered. All `/search`
requests returned `503 Service Unavailable` with the message:
`"Search indexes are not loaded."` The API itself stayed alive — it just
couldn't serve search traffic.

### Fix

Restored the correct values in `data/indexes/vector/meta.json`:
- `model_name`: `"all-MiniLM-L6-v2"`
- `dimension`: `384`

No code change was needed — the validation logic in `vector.py` already
handled this correctly. The fix confirmed that the startup guard works
as intended: it catches mismatches before serving any traffic rather than
returning silently wrong results.

### Commits

- `5def909` — break: corrupted meta.json
- `84eb14b` — fix: restored correct meta.json

---

## Scenario B — Schema migration break (NOT NULL column without default)

### How I broke it

Added a new migration (version 3) to `db.py` that attempts to add a
`user_id TEXT NOT NULL` column to `query_logs`. The column had already
been added manually to the live database via:
```sql
ALTER TABLE query_logs ADD COLUMN user_id TEXT NOT NULL DEFAULT '';
```

The migration had no idempotency check — it did not verify whether the
column already existed before running the `ALTER TABLE`. `SCHEMA_VERSION`
was bumped from 2 to 3.

### What happened

On next startup, `init_db()` called `_run_migrations()` which tried to
run migration 3. SQLite raised:
```
sqlite3.OperationalError: duplicate column name: user_id
```

This was caught and re-raised as:
```
RuntimeError: Migration to version 3 failed: duplicate column name: user_id
```

The API failed to start entirely — `init_db()` is called in the lifespan
before indexes load, so the crash happened before any routes were
registered. The database was not corrupted but the service was completely
down.

### Fix

Added an idempotency check for migration 3 in `_run_migrations()`,
mirroring the existing check for migration 2. Before running the ALTER,
the code now reads `PRAGMA table_info(query_logs)` and checks whether
`user_id` already exists. If it does, it sets the schema version and
skips the ALTER:
```python
if version in (2, 3):
    columns = [
        row[1] for row in
        conn.execute("PRAGMA table_info(query_logs)").fetchall()
    ]
    col_name = "error" if version == 2 else "user_id"
    if col_name in columns:
        _set_schema_version(conn, version)
        continue
```

After the fix, `init_db()` ran cleanly and all 120 tests passed.

### Commits

- `4e15540` — break: added NOT NULL migration 3 without idempotency check
- `fix(scenario-B) commit` — restored idempotency check, init_db passes

---

## Scenario C — Divide by zero in hybrid score normalisation

### How I broke it

Removed the NaN guard from `_minmax()` in `hybrid.py`. The original guard:
```python
if rng == 0.0:
    return {doc_id: 0.5 for doc_id in scores}
```

was deleted, leaving only the raw division:
```python
return {doc_id: (s - lo) / rng for doc_id, s in scores.items()}
```

### What happened

Querying with a nonsense string like `xyzxyzxyz123nonsense` caused BM25
to return all-zero scores for every document — it found no matching terms
so every document got the same raw score of 0.0. This made:

- `lo = 0.0`
- `hi = 0.0`  
- `rng = hi - lo = 0.0`

Division by zero produced `NaN` for every normalised BM25 score. The
fused hybrid scores were also `NaN`, making ranking undefined. Results
were returned in arbitrary order with `bm25_score: NaN` and
`score: NaN` in the response JSON. The eval harness also produced
`NaN` nDCG values for any query that triggered this path.

### Fix

Restored the guard in `_minmax()`:
```python
if rng == 0.0:
    return {doc_id: 0.5 for doc_id in scores}
```

When all scores are equal (including all-zero), every document gets
`0.5` as its normalised BM25 contribution. This is correct behaviour —
BM25 cannot differentiate between documents for this query, so it
contributes nothing to the ranking and vector scores decide the order.

The test suite has explicit coverage for this case:
- `test_all_zero_bm25_scores_do_not_produce_nan`
- `test_all_zero_vector_scores_do_not_produce_nan`
- `test_both_indexes_all_zero_scores`

All three pass after the fix.

### Commits

- `61225e6` — break: removed NaN guard from `_minmax()`
- `817f90e` — fix: restored guard, all scores equal returns 0.5
