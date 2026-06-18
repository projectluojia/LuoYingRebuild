# Knowledge Base Integration

LuoYing 的知识库以 Git 管理的网页知识 artifact 作为内容源。运行时数据库和索引都是派生物，可以随时从 `knowledge/` 重建。

## Architecture

```text
Crawl4AI web crawler
-> raw HTML snapshot
-> clean Markdown with frontmatter
-> quality checker
-> Git commit
-> SQLite metadata DB
-> hybrid index
   -> SQLite FTS5 keyword index
   -> local vector index
-> KB API
-> Agent
```

Core rules:

- `knowledge/` 是知识资产，必须可 review、可 diff、可提交。
- `var/kb/metadata.sqlite3` 是运行时派生库，不提交。
- Markdown 文件是单页事实源；frontmatter 保存该页核心元数据和质量结果。
- `graph.jsonl` 保存网页之间的链接关系；索引可以用它扩展上下文。
- crawler/extractor 使用 Crawl4AI；没有旧抽取器和降级路径。

## Code Layout

```text
src/luoying_bot/capabilities/knowledge_base/
├── artifacts.py      # write source.yaml, pages/*.md, raw/*.html, graph.jsonl
├── crawling.py       # crawl site and record artifacts/index
├── extraction.py     # Crawl4AI extraction
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
PYTHONPATH=src python scripts/crawl_site_to_kb.py \
  --config docs/site_configs/sai_whu.json
```

Rebuild metadata DB and hybrid index from committed artifacts:

```bash
PYTHONPATH=src python scripts/rebuild_kb_index.py
```

Run retrieval tests:

```bash
PYTHONPATH=src python test/kb/run_kb_harness.py smoke

PYTHONPATH=src python test/kb/run_kb_harness.py eval \
  --cases test/kb/cases/sai_whu_core.json
```
