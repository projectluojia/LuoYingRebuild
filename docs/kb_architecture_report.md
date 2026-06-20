# 珞樱知识库架构报告

更新时间：2026-06-20

## 1. 总体定位

当前知识库不是单纯 RAG，而是一个面向多源资料、结构化事实、实体理解和多端 Agent 调用的 KB 子系统。核心原则是：

- 文档型知识使用 Markdown artifact + chunk hybrid retrieval。
- 事实型知识使用 Postgres 结构化表 + SQL 精确计算。
- 实体型知识使用轻量 Entity Registry + 关系解析。
- 实体和事实统一生成可搜索投影 `kb_search_items`，用于召回；最终答案仍回到事实表或原文档证据。
- 所有运行时数据集中在 Postgres + pgvector 内，不再依赖 Directus / RAGFlow。

当前核心链路：

```text
Source
  -> raw artifact / markdown artifact
  -> structured fact tables
  -> entity registry
  -> kb_search_items hybrid projection
  -> KBQueryAgent
  -> EntityResolver
  -> Analytics SQL or RAG retrieval
  -> AnswerGenerator
  -> Agent Skill / Web API
```

## 2. 代码结构

主要目录：

```text
src/luoying_bot/capabilities/knowledge_base/
  artifacts.py          # raw/markdown artifact 写入、frontmatter、graph edges
  crawling.py           # 站点爬取编排
  extraction.py         # Crawl4AI 网页提取、清洗、链接规范化
  quality.py            # Markdown 质量检测
  embeddings.py         # OpenAI-compatible embedding provider
  entities.py           # entity id、search item id、文本归一化、metadata 解析
  entity_resolver.py    # 基于 kb_search_items + relations 的实体解析
  postgres_store.py     # Postgres/pgvector 存储、检索、结构化写入
  semantic_layer.py     # text-to-SQL 可用表、字段、语义规则
  analytics.py          # 实体优先 SQL planner + fallback LLM SQL planner
  query_agent.py        # KB 子 agent 查询编排
  answering.py          # 基于证据生成答案
  policy.py             # 引用/证据策略
  service.py            # KB service facade
```

入口接入：

```text
src/luoying_bot/bootstrap.py
  PostgresKnowledgeStore
  EntityResolver
  KnowledgeAnalyticsEngine
  KBQueryAgent
  KnowledgeBaseService

src/luoying_bot/application/agent/skills/knowledge_base_skill.py
  Agent skill: knowledge_base

src/luoying_bot/infra/web/knowledge_base_api.py
  /knowledge/answer
  /knowledge/search
  /knowledge/admin/sources
```

数据导入：

```text
scripts/import_whu_admission_data.py
  武汉大学招生 API + Excel 强基数据
  写入 fact tables
  写入 entities / aliases / relations
  重建 kb_search_items
  写入 markdown/raw artifacts

scripts/crawl_site_to_kb.py
  根据 site config 爬取网站并写入 Markdown artifact + kb_documents/kb_chunks

scripts/rebuild_kb_index.py
  从已有 Markdown artifact 重建文档索引
```

## 3. 数据流

### 3.1 网页资料流

网页资料使用 Crawl4AI 提取正文和链接：

```text
SiteCrawlConfig
  -> KnowledgeSiteCrawler
  -> Crawl4AIExtractor
  -> ParsedPage
  -> MarkdownArtifactStore
  -> KnowledgeCrawlRecorder
  -> kb_documents / kb_chunks
```

artifact 保存在：

```text
knowledge/sources/{site_id}/source.yaml
knowledge/sources/{site_id}/pages/*.md
knowledge/sources/{site_id}/raw/*.html
knowledge/sources/{site_id}/graph.jsonl
```

Markdown artifact frontmatter 包含：

- `id`
- `site_id`
- `space_id`
- `title`
- `url`
- `published_at`
- `content_hash`
- `content_type`
- `fetched_at`
- `depth`
- `link_count`
- `raw_path`
- `quality`

正文入库时会切 chunk，写入 `kb_chunks`，同时生成：

- dense vector: `embedding`
- sparse lexical index: `search_vector`

### 3.2 招生结构化资料流

当前武汉大学招生数据来自两类来源：

- 招生网站 API：`https://zsdata.whu.edu.cn/wzgl/wxmini`
- 本地 Excel：`docs/2025分省（区）录取分数及位次 - 挂网 - 最新.xlsx`

导入流程：

```text
fetch zsjh API
  -> normalize_plan_rows
  -> admission_plans

fetch lnfs API
  -> normalize_score_rows
  -> admission_scores

load Excel 强基列
  -> normalize_strong_foundation_rows
  -> admission_strong_foundation_scores

build_admission_entities
  -> kb_entities / kb_entity_aliases / kb_entity_relations

build_search_items
  -> kb_search_items
```

当前导入统计：

```text
kb_search_items:
  entity = 109
  fact   = 2772

kb_entities:
  school       = 2
  province     = 32
  major        = 73
  program_type = 1
  program      = 1

admission_plans                    = 5524
admission_scores                   = 6650
admission_strong_foundation_scores = 13
```

## 4. 查询逻辑

### 4.1 整体编排（KnowledgeBaseService.answer）

入口在 `service.py`。一次 `answer()` 的完整链路：

```text
answer(question, space_id, ...)
  1. _build_query()              问题 strip（空 -> KnowledgeBaseError）；space_id 缺省 -> default
  2. _retrieve()                 -> KBQueryAgent.retrieve()（见 4.2）
  3. policy.validate_retrieval   命中回退 -> 记日志 + 直接返回 KnowledgeAnswer（跳过 LLM）（见 4.5）
  4. answer_generator.generate   LLM 依据结构化资料 + 文档块生成答案
  5. policy.validate_answer      require_citation 且无引用 -> 回退
  6. _record_answer_log()        -> kb_answer_logs
```

`search()` 是检索专用入口，只做 1+2，不生成答案、不走策略回退。`submit_dynamic_qa` / `submit_feedback` 走结构化写入。

调用方接入：用户消息 -> AgentService -> knowledge_base skill -> `KnowledgeBaseService.answer`。`KnowledgeBaseSkill` 支持 QQ / Web / CLI，主 Agent 判断需要知识库时调用该 skill。

### 4.2 KBQueryAgent 查询路径

```text
KnowledgeQuery
  -> EntityResolver.resolve        实体解析（kb_search_items + relations）
  -> KnowledgeAnalyticsEngine.query 结构化 SQL（三级规划，见 4.4）
  -> space_id 解析                  query.space_id -> 结构化结果里的 space_id -> default
  -> RagBackend.search             文档混合检索（向量 + 词面 + 标题，见 4.6）
  -> RetrievalResult(structured_records, chunks)
```

注意：当前实现**不再**「有结构化结果就提前返回」，而是结构化证据与文档 RAG 并存于同一个 `RetrievalResult`，由后续 policy 与 AnswerGenerator 一起使用。文档标题匹配已并入 RAG 打分（见 4.6），`query_agent` 不再单独做 page title 匹配。

space_id 解析顺序：`query.space_id` → 否则取结构化记录里的 `space_id` → 否则 `default_space_id`；RAG 的 filters 会并上 `space_id` 限定。

### 4.3 EntityResolver

当前实体解析不再依赖组合别名。它使用 `kb_search_items` 搜索实体投影，再使用关系做组合解析。

例子：

```text
问题：2025年人智强基计划哪个省分数线最高？

search item 召回：
  人智 -> 人工智能学院
  强基 -> 强基计划

关系解析：
  数学与应用数学（智能科学）强基计划 is_a 强基计划
  数学与应用数学（智能科学）强基计划 related_to 人工智能学院

解析结果：
  program = 数学与应用数学（智能科学）强基计划
```

seed 中不保存组合别名：

```text
不保存：人智强基
不保存：人工智能学院强基
不保存：人工智能强基
```

当前 seed 只保存原子实体和原子别名：

```text
武汉大学: 武大
人工智能学院: 人智、人智学院、武大人工智能学院
强基计划: 强基、基础学科招生改革试点
```

### 4.4 Analytics SQL（三级规划）

`KnowledgeAnalyticsEngine.query` 先用 `is_analytics_question`（关键词：分数/录取/招生/专业/学院/学部/试验班/热点…）做守卫，非结构化问题直接返回 `[]`。然后按**三级优先级**生成 SQL，命中即停：

1. `_site_content_plan`（纯规则，不调 LLM）：试验班→`admission_media_items`、热点武大→`admission_articles`、学部/学院列表/专业列表等，直接生成 SQL。
2. `_entity_plan`（实体落地）：读取实体 metadata，取第一个有合法 `fact_table + fact_column` 的，按 province/year/subject_type 拼 `review_status='approved'` 的 SQL。
3. `_plan`（LLM 兜底）：把语义层 schema + 候选值 + 实体喂 LLM 生成 SQL。

`_entity_plan` 读取的实体 metadata 形如：

```json
{
  "fact_table": "admission_strong_foundation_scores",
  "fact_column": "program_name",
  "metric": "min_score"
}
```

如果实体有 `fact_table/fact_column`，直接生成受控 SQL。比如：

```sql
select space_id, year, province, program_name, subject_type,
       min_score, min_rank, source_url, source_document,
       source_department, published_at, review_status
from admission_strong_foundation_scores
where review_status = 'approved'
  and program_name = '数学与应用数学（智能科学）强基计划'
  and space_id = 'whu'
  and year = 2025
order by min_score desc nulls last, min_rank asc nulls last, province asc
limit 1;
```

**置信度门（`_entity_plan`）**：只有 `score >= 100` 或 `alias_type == 'relation_resolution'` 的高置信实体才能驱动 SQL。低置信噪声（如被模糊匹配进来的强基项目，而问题根本没提强基）会被跳过——否则会把查询钉到错误事实表、返回 0 行，并静默遮蔽 LLM planner（这是 fact_metric 类问题曾经的根因）。

强约束规则：

- 年份用正则提取：`2025年` / `25年`。
- 省份必须字面出现在用户问题中才作为 SQL filter，避免向量召回噪声误过滤。
- “最高”按 `min_score desc`。
- “最低”按 `min_score asc`。
- “所有/全部/列出/各省”放宽 `limit`，当前上限 `max_rows`（默认 50）。

若三级规划都没有产出可用 SQL（实体不满足置信度门、无 fact mapping），则该问题不返回结构化证据，交给文档 RAG。所有生成的 SQL 都必须经过 `validate_select_sql`：

- 只允许 SELECT。
- 禁止 insert/update/delete/drop 等操作。
- 禁止多语句、注释。
- 只允许查询白名单表。
- 强制 limit。

### 4.5 策略回退（KnowledgeBasePolicy）

`validate_retrieval` 按顺序判定，任一命中即回退——回退的 `KnowledgeAnswer`（answer 为统一的"未收录可靠材料"提示）会**直接作为最终答案返回**，跳过 LLM 生成，并写入 `kb_answer_logs`：

| 顺序 | 条件 | fallback_reason |
|---|---|---|
| 1 | `follow_up_question` 非空 | `missing_required_filters` |
| 2 | 无任何证据（records + chunks 都空） | `no_reliable_source` |
| 3 | `require_citation` 且无引用 | `no_reliable_source` |
| 4 | 无结构化记录 且 `max(vector_score) < min_relevance` | `low_relevance` |

第 4 条是**相关度阈值**（`min_relevance` 默认 0.5，`KB_MIN_RELEVANCE` 可调）：仅当只有文档块、没有可信结构化记录时，若返回结果里最高的余弦相似度仍低于阈值，判定为越界/低相关而拒答。结构化记录来自 filtered SQL，不受此门槛约束。这解决了"天气/订票"等越界问题被硬答的泄漏。

`validate_answer` 在 LLM 生成后再做一次引用校验（`require_citation` 且无引用 → `no_reliable_source`）。

### 4.6 文档 RAG 检索

文档检索仍走 `kb_chunks`：

```text
query
  -> embedding vector search
  -> full-text search
  -> title candidates
  -> phrase overlap scoring
  -> document support scoring
  -> RetrievedChunk[]
```

当前 `kb_search_items` 已覆盖 entity/fact 投影；文档 chunk 仍保留在 `kb_chunks` 中作为 RAG 专用索引。这是当前实现状态。后续如果要完全统一入口，可以把 chunk 也同步投影到 `kb_search_items`。

## 5. 数据库结构

数据库：Postgres + pgvector。

核心扩展：

```sql
create extension if not exists vector;
```

### 5.1 文档表

#### `kb_documents`

文档级元数据，一条 Markdown artifact 对应一条记录。

| 字段 | 类型 | 说明 |
|---|---|---|
| `document_id` | text pk | 稳定文档 ID |
| `space_id` | text | 知识空间 |
| `site_id` | text | 来源站点 |
| `title` | text | 标题 |
| `source_url` | text | 原始 URL |
| `published_at` | text | 发布时间 |
| `content_hash` | text | markdown 内容 hash |
| `markdown_path` | text | 本地 markdown 路径 |
| `raw_html_path` | text | 本地 raw HTML 路径 |
| `quality_json` | jsonb | 质量检测结果 |
| `status` | text | active/inactive |
| `updated_at` | timestamptz | 更新时间 |

索引：

```sql
primary key(document_id)
index(space_id, status)
```

#### `kb_chunks`

文档 chunk 检索表。

| 字段 | 类型 | 说明 |
|---|---|---|
| `chunk_id` | text pk | `{document_id}:{chunk_index}` |
| `document_id` | text fk | 关联 `kb_documents` |
| `chunk_index` | integer | chunk 顺序 |
| `title` | text | 文档标题 |
| `source_url` | text | 来源 URL |
| `published_at` | text | 发布时间 |
| `text` | text | chunk 正文 |
| `search_text` | text | 搜索增强文本 |
| `embedding` | vector | dense embedding |
| `embedding_provider` | text | embedding provider |
| `embedding_model` | text | embedding model |
| `embedding_dimensions` | integer | 向量维度 |
| `search_vector` | tsvector | Postgres full-text 向量 |

索引：

```sql
primary key(chunk_id)
index(document_id, chunk_index)
gin(search_vector)
hnsw(embedding vector_cosine_ops)
```

### 5.2 实体表

#### `kb_entities`

标准实体表，只保存原子实体。

| 字段 | 类型 | 说明 |
|---|---|---|
| `entity_id` | text pk | 稳定实体 ID |
| `space_id` | text | 知识空间 |
| `entity_type` | text | school / province / major / program_type / program |
| `canonical_name` | text | 标准名 |
| `description` | text | 描述 |
| `source_collection` | text | 来源集合 |
| `source_key` | text | 来源 key |
| `metadata_json` | jsonb | fact table mapping 等 |
| `review_status` | text | approved 等 |
| `updated_at` | timestamptz | 更新时间 |

唯一约束：

```sql
unique(space_id, entity_type, canonical_name)
```

#### `kb_entity_aliases`

实体原子别名表。

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | bigserial pk | 主键 |
| `entity_id` | text fk | 实体 |
| `space_id` | text | 知识空间 |
| `alias` | text | 原始别名 |
| `normalized_alias` | text | 归一化别名 |
| `alias_type` | text | official / short_name / abbreviation |
| `confidence` | numeric | 静态可信度 |
| `review_status` | text | approved 等 |
| `updated_at` | timestamptz | 更新时间 |

唯一约束：

```sql
unique(space_id, entity_id, normalized_alias)
```

#### `kb_entity_relations`

轻量实体关系表。

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | bigserial pk | 主键 |
| `space_id` | text | 知识空间 |
| `subject_entity_id` | text fk | 主体实体 |
| `predicate` | text | belongs_to / is_a / related_to |
| `object_entity_id` | text fk | 客体实体 |
| `confidence` | numeric | 关系可信度 |
| `metadata_json` | jsonb | 关系元数据 |
| `review_status` | text | approved 等 |
| `updated_at` | timestamptz | 更新时间 |

当前关键关系：

```text
人工智能学院 belongs_to 武汉大学
数学与应用数学（智能科学）强基计划 is_a 强基计划
数学与应用数学（智能科学）强基计划 related_to 人工智能学院
```

### 5.3 搜索投影表

#### `kb_search_items`

统一搜索投影表。当前存实体和事实投影，负责 hybrid search 召回。

| 字段 | 类型 | 说明 |
|---|---|---|
| `item_id` | text pk | 稳定投影 ID |
| `space_id` | text | 知识空间 |
| `item_type` | text | entity / fact |
| `entity_id` | text fk nullable | 关联实体 |
| `fact_table` | text | 事实来源表 |
| `fact_key` | text | 事实行稳定 key |
| `document_id` | text nullable | 文档 ID，当前未用于 fact/entity |
| `chunk_id` | text nullable | chunk ID，当前未用于 fact/entity |
| `title` | text | 投影标题 |
| `content_text` | text | 用于 embedding 的自然语言投影 |
| `search_text` | text | full-text 增强文本 |
| `metadata_json` | jsonb | 回表需要的元数据 |
| `embedding` | vector | dense embedding |
| `embedding_provider` | text | embedding provider |
| `embedding_model` | text | embedding model |
| `embedding_dimensions` | integer | 向量维度 |
| `review_status` | text | approved 等 |
| `updated_at` | timestamptz | 更新时间 |
| `search_vector` | tsvector | full-text search vector |

索引：

```sql
primary key(item_id)
index(space_id, item_type, review_status)
gin(search_vector)
hnsw(embedding vector_cosine_ops)
```

投影示例：

```text
item_type=entity
title=人工智能学院
content_text=
  人工智能学院
  类型：school
  别名：人工智能学院，武汉大学人工智能学院，武大人工智能学院，人智，人智学院
  描述：武汉大学人工智能学院
```

```text
item_type=fact
title=武汉大学强基计划录取分数
content_text=
  2025年，四川，数学与应用数学（智能科学）强基计划，最低分 664.0，最低位次 1383
```

### 5.4 招生事实表

#### `admission_plans`

招生计划事实表。

| 字段 | 类型 |
|---|---|
| `id` | bigserial pk |
| `space_id` | text |
| `year` | integer |
| `province` | text |
| `subject_type` | text |
| `batch` | text |
| `major_name` | text |
| `class_type` | text |
| `plan_count` | integer |
| `tuition` | text |
| `schooling_years` | text |
| `remarks` | text |
| `source_url` | text |
| `source_document` | text |
| `source_text` | text |
| `source_department` | text |
| `published_at` | text |
| `review_status` | text |
| `raw_json` | jsonb |
| `updated_at` | timestamptz |

唯一约束：

```sql
unique(space_id, year, province, subject_type, batch, major_name, class_type)
```

#### `admission_scores`

历年录取分数事实表。

| 字段 | 类型 |
|---|---|
| `id` | bigserial pk |
| `space_id` | text |
| `year` | integer |
| `province` | text |
| `subject_type` | text |
| `batch` | text |
| `major_name` | text |
| `min_score` | numeric |
| `max_score` | numeric |
| `avg_score` | numeric |
| `min_rank` | integer |
| `source_url` | text |
| `source_document` | text |
| `source_text` | text |
| `source_department` | text |
| `published_at` | text |
| `review_status` | text |
| `raw_json` | jsonb |
| `updated_at` | timestamptz |

唯一约束：

```sql
unique(space_id, year, province, subject_type, batch, major_name)
```

#### `admission_strong_foundation_scores`

强基计划分省录取分数事实表。

| 字段 | 类型 |
|---|---|
| `id` | bigserial pk |
| `space_id` | text |
| `year` | integer |
| `province` | text |
| `program_name` | text |
| `subject_type` | text |
| `min_score` | numeric |
| `min_rank` | integer |
| `source_url` | text |
| `source_document` | text |
| `source_text` | text |
| `source_department` | text |
| `published_at` | text |
| `review_status` | text |
| `raw_json` | jsonb |
| `updated_at` | timestamptz |

唯一约束：

```sql
unique(space_id, year, province, program_name)
```

当前 2025 强基数据 13 条，最高为：

```text
四川，数学与应用数学（智能科学）强基计划，最低分 664，最低位次 1383
```

### 5.5 事件表

#### `kb_events`

轻量事件/日志表，用于写入：

- `kb_answer_logs`
- `kb_feedback`
- `dynamic_qa`
- `kb_crawl_runs`

字段：

| 字段 | 类型 |
|---|---|
| `id` | bigserial pk |
| `collection` | text |
| `payload_json` | jsonb |
| `created_at` | timestamptz |

## 6. Entity Seed 策略

seed 文件：

```text
knowledge/seeds/whu_admissions_entities.json
```

seed 是初始化/管理数据，不是查询补丁。它只放无法稳定从事实表自动抽取的基础实体和原子别名。

当前 seed 包含：

```text
武汉大学
人工智能学院
强基计划
```

导入脚本会额外从事实数据派生：

- 省份实体
- 专业实体
- 具体项目实体：`数学与应用数学（智能科学）强基计划`
- 项目关系：`is_a 强基计划`、`related_to 人工智能学院`

禁止模式：

```text
人智强基 -> 具体项目
人工智能学院强基 -> 具体项目
```

正确模式：

```text
人智 -> 人工智能学院
强基 -> 强基计划
具体项目 is_a 强基计划
具体项目 related_to 人工智能学院
```

## 7. 检索和排序设计

### 7.1 `kb_search_items` hybrid retrieval

当前 `search_kb_items`：

1. 对 query 生成 embedding。
2. 对 `kb_search_items.embedding` 做 HNSW cosine vector search。
3. 如果 `build_tsquery(query)` 非空，同时走 `search_vector @@ to_tsquery(...)`。
4. 合并 vector 和 lexical candidates。
5. 按 `score desc` 排序。

### 7.2 `kb_chunks` RAG retrieval

当前文档 RAG 对 `kb_chunks` 做三路召回：

- title candidates
- lexical candidates
- vector candidates

再计算：

```text
score =
  2.8 * title_score
  + 1.4 * phrase_score
  + 1.0 * vector_score
  + 0.7 * lexical_score
  + document_support_score
```

## 8. 测试和验证

测试目录：

```text
test/kb/run_kb_harness.py
test/kb/cases/*.json
```

常用命令：

```bash
UV_CACHE_DIR=var/uv-cache UV_PROJECT_ENVIRONMENT=var/venv \
PYTHONPATH=src uv run --frozen python test/kb/run_kb_harness.py eval \
  --cases test/kb/cases/whu_strong_foundation.json
```

带回答生成：

```bash
UV_CACHE_DIR=var/uv-cache UV_PROJECT_ENVIRONMENT=var/venv \
PYTHONPATH=src uv run --frozen python test/kb/run_kb_harness.py eval \
  --with-answer \
  --cases test/kb/cases/whu_strong_foundation.json
```

当前强基测试结果：

```text
eval:        3/3 passed
with-answer: 3/3 passed
```

覆盖问题：

- `2025年武汉大学强基计划哪个省分数线最高？`
- `2025年数学与应用数学智能科学强基计划四川最低分是多少？`
- `2025年人智强基计划哪个省分数线最高？然后把25年人工智能学院强基所有数据都列给我`

最后一个问题返回：

```text
structured_count = 13
chunks_count = 0
```

说明它走的是结构化事实，不是 RAG fallback。

### 8.1 检索质量 / 效率评测（quality / perf）

`run_kb_harness.py` 新增两个命令，针对多类型问题度量检索质量与效率（命中真实 Postgres + embedding + LLM）：

```bash
# 检索质量：按问题类型算 hit@k / MRR / precision@k / recall / 回退正确率
uv run python test/kb/run_kb_harness.py quality \
  --cases test/kb/cases/retrieval_quality.json

# 检索效率：延迟 p50/p95/p99、并发吞吐、按类型延迟、embedding 调用数
uv run python test/kb/run_kb_harness.py perf \
  --cases test/kb/cases/retrieval_quality.json --concurrency 4 --iterations 40
```

用例集 `retrieval_quality.json` 覆盖 9 类检索路径：`fact_metric / ranking / listing / strong_foundation / entity / site_media / site_article / doc_rag / out_of_scope`，基于真实索引数据编写 ground truth。当前基线（含相关度阈值 + `_entity_plan` 置信度门修复后）：

```text
quality: overall pass 1.00（9 类全 100%，含 out_of_scope 越界回退）
perf:    p50≈390ms p95≈1.7s，embedding 2 次/查询；
         命中 LLM SQL 规划的类型（fact_metric/doc_rag）比规则型慢 2-4 倍
```

## 9. 运行和维护命令

导入招生事实、实体、搜索投影：

```bash
UV_CACHE_DIR=var/uv-cache UV_PROJECT_ENVIRONMENT=var/venv \
PYTHONPATH=src uv run --frozen python scripts/import_whu_admission_data.py --year 2025
```

爬取学院网站：

```bash
UV_CACHE_DIR=var/uv-cache UV_PROJECT_ENVIRONMENT=var/venv \
PYTHONPATH=src uv run --frozen python scripts/crawl_site_to_kb.py \
  --config docs/site_configs/sai_whu.json
```

从 Markdown artifact 重建文档索引：

```bash
UV_CACHE_DIR=var/uv-cache UV_PROJECT_ENVIRONMENT=var/venv \
PYTHONPATH=src uv run --frozen python scripts/rebuild_kb_index.py
```

查看搜索投影统计：

```bash
docker exec luoying-kb-postgres psql -U luoying_kb -d luoying_kb \
  -c "select item_type, count(*) from kb_search_items group by item_type;"
```

重启珞樱：

```bash
docker compose restart luoying
```

## 10. 当前边界和建议

### 10.1 当前边界

1. 文档 chunk 仍在 `kb_chunks`，没有同步进入 `kb_search_items`。
   - 当前效果可用：结构化实体/事实走 `kb_search_items`，文档 RAG 走 `kb_chunks`。
   - 若要实现完全统一召回入口，应把 document chunk 也投影成 `item_type=document_chunk`。

2. EntityResolver 当前只实现了有限关系模式：
   - `school + program_type -> program`
   - 依赖 `is_a` 和 `related_to`
   - 后续若引入更多领域，可以扩展为通用 relation pattern resolver。

3. Analytics entity-grounded SQL 当前主要覆盖有 `fact_table/fact_column` 的实体。
   - 对招生强基问题已经稳定。
   - 对复杂 joins、跨事实表对比，仍依赖 LLM SQL planner。

4. `kb_events` 是轻量事件存储。
   - 适合早期日志/反馈。
   - 如果后台管理要做强审计，建议拆成正式 answer_logs / feedback / crawl_runs 表。

### 10.2 建议的下一步

1. 将 `kb_chunks` 同步写入 `kb_search_items`，形成真正统一召回层。
2. 为 `kb_search_items` 增加 RRF 排序或 reranker 字段，避免 vector/lexical 分数尺度不一致。
3. 将 entity seed 接入管理后台，支持人工审核 alias 和 relation。
4. 增加 fact coverage 表，用于明确表达“不招生/无数据/未收录”的区别。
5. 增加 SQL execution verifier：
   - 空结果时区分实体不存在、实体存在但年份无数据、实体存在但省份无招生。
6. 为每类事实表增加专门 eval cases，避免新增数据源时破坏已有查询。

## 11. 架构判断

当前 KB 已从纯 RAG 发展为：

```text
Postgres fact tables
+ Entity Registry
+ Search Projection
+ Markdown/RAG
+ Agent Skill
```

这是适合本项目的方向。它比纯 RAG 更适合回答招生人数、分数线、最高/最低、各省列表等计算型问题；比完整知识图谱更轻，维护成本更低；比手写别名匹配更可持续。

最佳实践边界是：

```text
向量检索负责召回候选
实体关系负责理解用户说的是谁
SQL 负责精确计算
Markdown/RAG 负责补充解释和出处
AnswerGenerator 只根据证据回答
```
