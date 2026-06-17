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

## Configuration

```env
RAGFLOW_URL=
RAGFLOW_API_KEY=
RAGFLOW_SEARCH_PATH=/api/v1/retrieval
RAGFLOW_DEFAULT_DATASET_ID=
RAGFLOW_ADMISSIONS_DATASET_ID=

DIRECTUS_URL=
DIRECTUS_TOKEN=
DIRECTUS_COLLECTION_PREFIX=

KB_DEFAULT_SPACE_ID=admissions
KB_DEFAULT_DOMAIN=admissions
KB_REQUIRE_CITATION=true
```

## API

LuoYing exposes a thin knowledge API for platform and debugging integration:

- `POST /knowledge/answer`
- `POST /knowledge/search`
- `POST /knowledge/dynamic-qa`
- `POST /knowledge/feedback`

Directus remains the management backend. LuoYing does not reimplement Directus administration screens or RBAC.

## Removed Legacy Path

The old local JSON knowledge base has been removed from the active application path:

- old `/kb_*` commands are removed.
- old `knowledge` Skill is removed.
- old JSON repository/service files are removed.
- official KB data must come from Directus or RAGFlow.

