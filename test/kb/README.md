# KB Test Harness

Two layers of tests for the LuoYing knowledge base:

1. **Unit tests** (`test/kb/unit/`) — hermetic, fast, no external services. Covers the pure
   logic of the kb modules (models, entities, semantic layer, policy, quality checker).
   Run with `uv run pytest`.
2. **Retrieval eval** (`test/kb/run_kb_harness.py`) — runs against the **live** Postgres +
   pgvector + embedding API + LLM configured by `KB_DATABASE_URL`. Measures **retrieval
   quality** and **efficiency** across many question types. This is where you answer
   "for various questions, is retrieval quality high and is it fast?".

Build the index from committed Markdown artifacts:

```bash
uv run python scripts/rebuild_kb_index.py
```

Or crawl fresh and index:

```bash
uv run python scripts/crawl_site_to_kb.py --config docs/site_configs/sai_whu.json
```

## Retrieval quality — `quality`

```bash
uv run python test/kb/run_kb_harness.py quality \
  --cases test/kb/cases/retrieval_quality.json
```

For every case it runs **retrieval + policy only (no LLM answer)** and computes IR metrics:

- `hit@k` — did a relevant item appear in the top-k results?
- `mrr` — reciprocal rank of the first relevant item
- `precision@k` — fraction of top-k that are relevant
- `recall` — relevant found / expected (vs `expected_match`/`min_relevant`, or expected-set coverage for listings)
- `fallback_correct` — did the policy make the right refuse/answer decision?

Results are aggregated **per question type** (`type` field) plus an overall rollup, so you can
see exactly which retrieval paths are strong and which leak. `--pass-threshold` (default 80)
sets the overall pass-rate floor; the run exits non-zero below it.

### Case schema (`retrieval_quality.json`)

```jsonc
{
  "id": "fact_hubei_2024_score",
  "type": "fact_metric",            // groups results: fact_metric|ranking|listing|strong_foundation|entity|site_media|site_article|doc_rag|out_of_scope
  "question": "武汉大学2024年在湖北的录取分数线是多少？",
  "space_id": "whu",                // optional; defaults to KB_DEFAULT_SPACE_ID
  "top_k": 8,
  "expected_match": ["湖北", "2024"], // AND: a relevant item must contain all of these
  "expected_any": ["分数线"],         // soft term coverage; for listings this IS the relevance set
  "min_relevant": 1,                // for recall in AND mode
  "expect_fallback": false          // true for out_of_scope → success = system refused
}
```

Relevance matching normalizes text (lowercase, keep CJK + alphanumeric) and checks token
substrings, so it works for both structured records (matched on field values like
`province=湖北`) and document chunks (matched on title/source/text).

## Retrieval efficiency — `perf`

```bash
uv run python test/kb/run_kb_harness.py perf \
  --cases test/kb/cases/retrieval_quality.json \
  --concurrency 4 --iterations 40
```

Reports latency `p50/p90/p95/p99` + mean/max, throughput (qps), **embedding calls per query**,
and **latency broken down by question type** — useful for spotting which paths are slow
(typically the LLM SQL-planning paths vs. the cheap rule-based ones).

## Smoke / answer eval — `smoke` / `eval`

```bash
uv run python test/kb/run_kb_harness.py smoke                       # single question
uv run python test/kb/run_kb_harness.py eval --cases test/kb/cases/sai_whu_core.json
uv run python test/kb/run_kb_harness.py eval --cases ... --with-answer  # also generate the LLM answer
```

Reports are written to `test/kb/reports/` by default and are intentionally git-ignored.
`quality_latest.json` / `perf_latest.json` are overwritten each run for convenience.
