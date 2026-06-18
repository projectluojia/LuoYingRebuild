# Local Knowledge Base Deployment

This directory contains the local self-hosted infrastructure for LuoYing knowledge base.

## Services

- Directus: structured knowledge records, site configuration, review status, permissions.
- RAGFlow: document parsing, chunking, vector retrieval.

Directus is maintained by this project through `compose.directus.yml`.
RAGFlow uses the official Docker deployment files under `ragflow/`.

## Start

```bash
bash deploy/kb/bin/start-directus.sh
bash deploy/kb/bin/start-ragflow.sh
```

Then initialize LuoYing KB schema and seed the SAI site:

```bash
PYTHONPATH=src python scripts/setup_directus_knowledge_schema.py
PYTHONPATH=src python scripts/seed_directus_site_config.py --config docs/site_configs/sai_whu.json
```

`start-ragflow.sh` bootstraps the local RAGFlow tenant with:

- an API token stored in `.env`;
- the local TEI embedding model at `http://luoying-embedding:80`;
- the project OpenAI-compatible chat model from `.env` when `OPENAI_API_KEY`, `OPENAI_BASE_URL`, and `OPENAI_MODEL` are set;
- a `sai_whu` dataset stored in `.env` as `RAGFLOW_DEFAULT_DATASET_ID`;
- the same dataset id written back to Directus `kb_sites.ragflow_dataset_id` when the site already exists.

Then run the full ingest:

```bash
PYTHONPATH=src python scripts/crawl_site_to_directus.py --site-id sai_whu
```

The RAGFlow UI remains available for inspection at:

```text
http://localhost:8088
```

## Health Checks

```bash
bash deploy/kb/bin/healthcheck.sh
```

Expected local endpoints:

- Directus Studio/API: `http://localhost:8055`
- RAGFlow Web UI: `http://localhost:8088`
- RAGFlow HTTP API: `http://localhost:9380`
