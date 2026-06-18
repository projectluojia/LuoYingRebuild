# KB Test Harness

This directory contains repeatable tests for the LuoYing knowledge base.

The harness reads the local SQLite metadata/index configured by `KB_METADATA_DB`.
Build it from committed Markdown artifacts with:

```bash
PYTHONPATH=src python scripts/rebuild_kb_index.py
```

Or crawl fresh Markdown artifacts and index them with:

```bash
PYTHONPATH=src python scripts/crawl_site_to_kb.py \
  --config docs/site_configs/sai_whu.json
```

## Commands

Smoke test:

```bash
PYTHONPATH=src python test/kb/run_kb_harness.py smoke
```

Retrieval evaluation:

```bash
PYTHONPATH=src python test/kb/run_kb_harness.py eval \
  --cases test/kb/cases/sai_whu_core.json
```

Performance test:

```bash
PYTHONPATH=src python test/kb/run_kb_harness.py perf \
  --cases test/kb/cases/sai_whu_core.json \
  --concurrency 4 \
  --iterations 20
```

Reports are written to `test/kb/reports/` by default and are intentionally ignored.
