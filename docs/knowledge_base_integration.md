# Knowledge Base Integration

LuoYing 的知识库以 Git 管理的网页知识 artifact 作为内容源。运行时数据库和索引都是派生物，可以随时从 `knowledge/` 重建。

## Architecture

```text
Crawl4AI web crawler
-> raw HTML snapshot
-> clean Markdown with frontmatter
-> quality checker
-> Git commit
-> Postgres metadata DB
-> hybrid index
   -> ParadeDB pg_search BM25 index
   -> pgvector index
   -> required LLM reranker
-> KB API
-> Agent
```

Core rules:

- `knowledge/` 是知识资产，必须可 review、可 diff、可提交。
- Postgres/ParadeDB `pg_search`/pgvector 是运行时派生库，可以从 `knowledge/` 重建。
- Markdown 文件是单页事实源；frontmatter 保存该页核心元数据和质量结果。
- `graph.jsonl` 保存网页之间的链接关系；索引可以用它扩展上下文。
- crawler/extractor 使用 Crawl4AI；没有旧抽取器和降级路径。

## Code Layout

```text
src/luoying_bot/capabilities/knowledge_base/
├── artifacts.py      # write source.yaml, pages/*.md, raw/*.html, graph.jsonl
├── crawling.py       # crawl site and record artifacts/index
├── extraction.py     # Crawl4AI extraction
├── postgres_store.py # Postgres metadata, ParadeDB BM25, pgvector search
├── quality.py        # markdown quality checks
├── query_agent.py    # KB query sub-agent orchestration
├── analytics.py      # Text-to-SQL analytics engine
├── semantic_layer.py # structured data semantic layer
├── service.py        # answer/search API facade
├── answering.py
├── policy.py
└── models.py
```

Agent entry:

```text
src/luoying_bot/application/agent/skills/knowledge_base_skill.py
```

Web API entry:

```text
src/luoying_bot/infra/http/knowledge_base_api.py
```

## Configuration

```env
KB_ARTIFACT_ROOT=./knowledge
KB_DATABASE_URL=postgresql://luoying_kb:luoying_kb@127.0.0.1:15432/luoying_kb
KB_DEFAULT_SPACE_ID=sai
KB_REQUIRE_CITATION=true
KB_MIN_RERANK_SCORE=30
KB_EMBEDDING_BASE_URL=http://127.0.0.1:8080/v1
KB_EMBEDDING_API_KEY=
KB_EMBEDDING_MODEL=/models/bge-small-zh-v1.5
KB_EMBEDDING_QUERY_INSTRUCTION=为这个句子生成表示以用于检索相关文章：
KB_EMBEDDING_BATCH_SIZE=4
KB_EMBEDDING_DIMENSIONS=512
KB_RERANK_CANDIDATE_LIMIT=40
KB_RERANK_MAX_TEXT_CHARS=900
```

Embedding is asymmetric:

- query text is embedded with `KB_EMBEDDING_QUERY_INSTRUCTION`
- document and structured search-item text is embedded without a query instruction

Changing the embedding model, dimension, or pooling requires rebuilding the derived Postgres
index. Changing only the query instruction affects new queries immediately; run the quality
harness after changing it.

For chunk-only answers, `KB_MIN_RERANK_SCORE` is the primary relevance gate. Candidates below
that score are treated as non-answerable even if dense vector similarity is high.

## Artifact Layout

```text
knowledge/
└── sources/
    └── sai_whu/
        ├── source.yaml
        ├── graph.jsonl
        ├── pages/
        │   └── rencaipy_bkspy_cf495a68c45f.md
        └── raw/
            └── rencaipy_bkspy_cf495a68c45f.html
```

Markdown page example:

```md
---
id: "rencaipy_bkspy.htm_cf495a68c45f"
site_id: "sai_whu"
space_id: "sai"
title: "本科生培养"
url: "https://sai.whu.edu.cn/rencaipy/bkspy.htm"
published_at: null
content_hash: "..."
content_type: "listing"
fetched_at: "2026-06-18T18:00:00"
depth: 0
link_count: 12
raw_path: "raw/rencaipy_bkspy.htm_cf495a68c45f.html"
quality: {"ok": true, "warnings": []}
---

# 本科生培养
```

`graph.jsonl` is an edge table:

```json
{"from":"https://sai.whu.edu.cn/rencaipy/bkspy.htm","from_id":"rencaipy_bkspy.htm_cf495a68c45f","to":"https://sai.whu.edu.cn/info/xxx.htm","to_id":"info_xxx","site_id":"sai_whu","type":"content_link","text":"2025级人工智能专业培养方案"}
```

## Commands

Crawl into Git artifacts and local index:

```bash
uv run python scripts/crawl_site_to_kb.py \
  --config docs/site_configs/sai_whu.json
```

Rebuild metadata DB and hybrid index from committed artifacts:

```bash
uv run python scripts/rebuild_kb_index.py
```

Run retrieval tests:

```bash
uv run python test/kb/run_kb_harness.py smoke

uv run python test/kb/run_kb_harness.py eval \
  --cases test/kb/cases/sai_whu_core.json
```
