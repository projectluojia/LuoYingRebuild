# Knowledge Base Integration

LuoYing 的知识库能力现在以 `capabilities/knowledge_base` 作为通用能力模块实现，不再使用旧的本地 JSON 知识库。

## Architecture

```text
QQ / Web / CLI
-> Agent
-> knowledge_base Skill
-> KnowledgeBaseService
-> Directus structured backend
-> RAGFlow document backend
```

Responsibilities:

- `LuoYing`: multi-platform Agent integration, answer orchestration, policy checks, citation formatting.
- `Directus`: structured records, review status, permissions, answer logs, feedback, dynamic QA.
- `RAGFlow`: non-structured documents, parsing, chunking, retrieval, citations.

## Code Layout

```text
src/luoying_bot/capabilities/knowledge_base/
├── models.py
├── schemas.py
├── service.py
├── policy.py
├── answering.py
├── directus_client.py
├── ragflow_client.py
└── domains/
    ├── general.py
    └── admissions/
        └── domain.py
```

Agent entry:

```text
src/luoying_bot/application/agent/skills/knowledge_base_skill.py
```

Web API entry:

```text
src/luoying_bot/infra/web/knowledge_base_api.py
```

Crawler entry:

```text
src/luoying_bot/capabilities/knowledge_base/crawling.py
scripts/crawl_site_preview.py
scripts/setup_directus_knowledge_schema.py
scripts/seed_directus_site_config.py
scripts/crawl_site_to_directus.py
docs/site_configs/sai_whu.json
```

## Configuration

```env
RAGFLOW_URL=http://127.0.0.1:9380
RAGFLOW_API_KEY=
RAGFLOW_SEARCH_PATH=/api/v1/retrieval
RAGFLOW_DEFAULT_DATASET_ID=
RAGFLOW_ADMISSIONS_DATASET_ID=

DIRECTUS_URL=http://127.0.0.1:8055
DIRECTUS_TOKEN=
DIRECTUS_COLLECTION_PREFIX=

KB_DEFAULT_SPACE_ID=sai
KB_DEFAULT_DOMAIN=admissions
KB_REQUIRE_CITATION=true
```

Local Directus and RAGFlow deployment lives under:

```text
deploy/kb/
```

Start local services:

```bash
bash deploy/kb/bin/start-directus.sh
bash deploy/kb/bin/start-ragflow.sh
```

`start-ragflow.sh` creates or reuses the local RAGFlow API token, registers the local TEI embedding model, registers the project OpenAI-compatible chat model from `.env`, creates or reuses the `sai_whu` dataset, and writes `RAGFLOW_DEFAULT_DATASET_ID` back into `.env`.

## API

LuoYing exposes a thin knowledge API for platform and debugging integration:

- `POST /knowledge/answer`
- `POST /knowledge/search`
- `POST /knowledge/dynamic-qa`
- `POST /knowledge/feedback`

Directus remains the management backend. LuoYing does not reimplement Directus administration screens or RBAC.

## Site Crawling

Site crawling is implemented as a knowledge-base capability, but site configuration and official run records should be stored in Directus.

Core Directus collections expected by the crawler:

- `kb_sites`
- `kb_crawl_runs`
- `kb_pages`
- `kb_page_versions`

The crawler records canonical URL, title, inferred publish date, content hash, clean text, raw HTML version, crawl run, and sync status. Pages that changed hash get a new `kb_page_versions` record.

Each site config may define `blocked_page_patterns` for pages that return HTTP 200 but are not usable knowledge content, such as verification, captcha, login wall, or rate-limit pages. Blocked pages are recorded as failed crawl results and are never written into Directus or RAGFlow.

Directus is the source of truth for managed sites. The SAI JSON file is a seed file for local preview and Directus initialization:

```text
docs/site_configs/sai_whu.json
```

Preview command:

```bash
PYTHONPATH=src python scripts/crawl_site_preview.py \
  --config docs/site_configs/sai_whu.json \
  --output /tmp/sai_crawl_preview.json
```

Directus sync command:

```bash
PYTHONPATH=src python scripts/setup_directus_knowledge_schema.py

PYTHONPATH=src python scripts/seed_directus_site_config.py \
  --config docs/site_configs/sai_whu.json

PYTHONPATH=src python scripts/crawl_site_to_directus.py \
  --site-id sai_whu
```

The sync command requires:

```env
DIRECTUS_URL=http://127.0.0.1:8055
DIRECTUS_TOKEN=
RAGFLOW_URL=http://127.0.0.1:9380
RAGFLOW_API_KEY=
RAGFLOW_DEFAULT_DATASET_ID=
```

If `docs/site_configs/sai_whu.json` sets `ragflow_dataset_id`, that dataset is used; otherwise the sync command uses `RAGFLOW_DEFAULT_DATASET_ID`. The command fails fast if no dataset ID is available while `sync_to_ragflow` is enabled.

Observed result on 2026-06-18 against the real local Directus/RAGFlow deployment:

- `https://sai.whu.edu.cn/` returned 80 successful pages and 0 failed pages with the configured browser User-Agent.
- Directus contains 80 `kb_pages`, 81 `kb_page_versions`, and 2 `kb_crawl_runs`.
- RAGFlow contains 81 real documents, 81 chunks, and 43,887 tokens for dataset `sai_whu`.
- Retrieval query `本科生培养` returned the official `本科生培养-武汉大学人工智能学院` page as the top hit.
- No Obscura or stealth browser is required for this site in current tests.

Important: the site returned `403` when using the default bot User-Agent. The SAI config therefore uses a normal browser User-Agent while still limiting scope to `sai.whu.edu.cn` and configured entry URLs.

## Removed Legacy Path

The old local JSON knowledge base has been removed from the active application path:

- old `/kb_*` commands are removed.
- old `knowledge` Skill is removed.
- old JSON repository/service files are removed.
- official KB data must come from Directus or RAGFlow.
