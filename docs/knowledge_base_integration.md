# Knowledge Base Integration

LuoYing 的知识库现在以 Git 管理的 Markdown artifact 作为内容源，不再依赖 Directus 或 RAGFlow。

## Architecture

```text
Web crawler
-> raw artifact
-> markdown extractor
-> quality checker
-> Git-managed Markdown
-> SQLite metadata DB
-> hybrid index
   -> SQLite FTS5 keyword index
   -> local hash-vector index
-> KB API
-> Agent
```

Core rules:

- Markdown is the canonical cleaned content.
- Git is the version system for Markdown and metadata artifacts.
- SQLite stores runtime metadata, logs, chunks, keyword index, and vector index.
- Agent and Web API call `KnowledgeBaseService`; they do not know about crawler details.
- Directus and RAGFlow are not part of the active path.

## Code Layout

```text
src/luoying_bot/capabilities/knowledge_base/
├── artifacts.py      # write raw.html/current.md/metadata.json
├── crawling.py       # crawl site and record artifacts/index
├── extraction.py     # HTML extraction with Trafilatura
├── local_store.py    # SQLite metadata, FTS5, vector search
├── quality.py        # markdown quality checks
├── service.py        # answer/search orchestration
├── answering.py
├── policy.py
├── models.py
└── domains/
```

Agent entry:

```text
src/luoying_bot/application/agent/skills/knowledge_base_skill.py
```

Web API entry:

```text
src/luoying_bot/infra/web/knowledge_base_api.py
```

## Configuration

```env
KB_ARTIFACT_ROOT=./knowledge
KB_METADATA_DB=./var/kb/metadata.sqlite3
KB_DEFAULT_SPACE_ID=sai
KB_DEFAULT_DOMAIN=admissions
KB_REQUIRE_CITATION=true
KB_VECTOR_DIMENSIONS=384
```

`knowledge/` should be committed. `var/` is runtime state and is ignored.

## Artifact Layout

Each crawled page writes a stable document directory:

```text
knowledge/
└── sources/
    └── sai_whu/
        └── documents/
            └── <stable_document_id>/
                ├── current.md
                ├── raw.html
                └── metadata.json
```

`current.md` is the content source for review and retrieval.

`metadata.json` stores source URL, title, content hash, quality report, and file paths.

## Commands

Preview crawl without writing:

```bash
PYTHONPATH=src python scripts/crawl_site_preview.py \
  --config docs/site_configs/sai_whu.json \
  --output /tmp/sai_crawl_preview.json
```

Crawl into Markdown artifacts and local index:

```bash
PYTHONPATH=src python scripts/crawl_site_to_kb.py \
  --config docs/site_configs/sai_whu.json
```

Rebuild metadata DB and hybrid index from committed Markdown artifacts:

```bash
PYTHONPATH=src python scripts/rebuild_kb_index.py
```

Test retrieval:

```bash
PYTHONPATH=src python test/kb/run_kb_harness.py smoke

PYTHONPATH=src python test/kb/run_kb_harness.py eval \
  --cases test/kb/cases/sai_whu_core.json
```

## Data Ownership

- `raw.html`: debugging and future extractor improvements.
- `current.md`: canonical cleaned document.
- `metadata.json`: machine metadata and quality report.
- `var/kb/metadata.sqlite3`: rebuildable runtime DB and index.

If Markdown changes in Git, run `scripts/rebuild_kb_index.py`.

If crawler or extractor improves, run `scripts/crawl_site_to_kb.py`, review Markdown diffs, then commit.
