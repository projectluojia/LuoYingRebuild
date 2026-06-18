# KB Test Harness

This directory contains repeatable tests for the LuoYing knowledge base.

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
