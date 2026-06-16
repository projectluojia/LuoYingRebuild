# 知识库功能文档

## 功能概述

知识库是一个全局共享的信息存储模块，所有用户可以通过指令或自然语言向知识库添加带标签的富内容条目，支持关键词搜索和 LLM 智能摘要生成。

**特性：**
- 全局共享：所有用户操作同一个知识库
- 持久化存储：数据保存在 `data/knowledge.json`，重启不丢失
- 富内容结构：每条包含标题、内容、标签、来源 URL
- LLM 摘要：调用大模型对知识库内容生成自然语言摘要
- 双入口操作：既可通过指令直接操作，也可通过自然语言让 Agent 调用

## 命令列表

### `/kb_add` — 添加知识条目

向知识库添加一条新记录。

**用法：**
```
/kb_add --title 标题 --content 内容 [--tags 标签1,标签2] [--source 来源URL]
```

**参数说明：**
| 参数 | 缩写 | 必需 | 说明 |
|------|------|------|------|
| `--title` | `-t` | ✅ | 条目标题 |
| `--content` | `-c` | ✅ | 条目正文内容 |
| `--tags` | `-g` | ❌ | 逗号分隔的标签列表 |
| `--source` | `-s` | ❌ | 来源 URL 或说明 |

**示例：**
```
/kb_add --title "Python 装饰器" --content "装饰器是一种设计模式，用于在不修改原函数代码的情况下扩展函数功能。" --tags Python,编程 --source https://docs.python.org
```

---

### `/kb_list` — 列出所有条目

展示知识库中所有条目的摘要信息（序号、ID、标题、标签、时间）。

**用法：**
```
/kb_list
```

---

### `/kb_search` — 搜索知识库

按关键词在标题、内容和标签中搜索匹配的条目。

**用法：**
```
/kb_search --keyword 关键词
```

**参数说明：**
| 参数 | 缩写 | 必需 | 说明 |
|------|------|------|------|
| `--keyword` | `-k` | ✅ | 搜索关键词 |

**示例：**
```
/kb_search --keyword Python
```

---

### `/kb_summary` — 生成知识库摘要

调用大模型对知识库全部内容生成一份简洁有条理的中文摘要。

**用法：**
```
/kb_summary
```

> ⚠️ 需要配置 LLM 服务（`OPENAI_BASE_URL`、`OPENAI_API_KEY`、`OPENAI_MODEL`）。

---

### `/kb_del` — 删除条目

根据条目 ID 删除指定条目。

**用法：**
```
/kb_del --id 条目ID
```

**参数说明：**
| 参数 | 缩写 | 必需 | 说明 |
|------|------|------|------|
| `--id` | `-i` | ✅ | 条目 ID（如 `kb_001`） |

**示例：**
```
/kb_del --id kb_003
```

---

### `/kb_clear` — 清空知识库

删除知识库中的全部条目。**需要管理员权限。**

**用法：**
```
/kb_clear
```

---

## 自然语言操作（Agent Skill）

除了指令操作外，用户也可以通过自然语言与 Agent 交互来操作知识库。Agent 会自动调用 `knowledge` Skill 完成对应操作。

**示例对话：**
- "帮我往知识库加一条关于 Python 装饰器的内容"
- "查一下知识库里有没有关于机器学习的条目"
- "帮我总结一下知识库的内容"
- "把知识库清空"

---

## 数据结构

### KnowledgeItem

```python
@dataclass
class KnowledgeItem:
    id: str              # 条目 ID，格式如 kb_001
    title: str           # 标题
    content: str         # 正文内容
    tags: list[str]      # 标签列表
    source: str          # 来源 URL 或说明
    created_at: str      # 创建时间
    updated_at: str      # 更新时间
```

### 存储格式

数据存储在 `data/knowledge.json`，JSON 格式：

```json
{
  "items": [
    {
      "id": "kb_001",
      "title": "Python 装饰器",
      "content": "装饰器是一种设计模式...",
      "tags": ["Python", "编程"],
      "source": "https://docs.python.org",
      "created_at": "2026-06-16 12:00:00",
      "updated_at": "2026-06-16 12:00:00"
    }
  ]
}
```

---

## 实现架构

```
用户输入
  │
  ├─ 指令路径（/kb_*）          Agent 路径（自然语言）
  │                               │
  ▼                               ▼
CommandDispatcher              AgentService
  │                               │
  ▼                               ▼
KnowledgeCommand               KnowledgeSkill
  │                               │
  └───────────┬───────────────────┘
              ▼
      KnowledgeService
              │
              ▼
      JsonKnowledgeRepo
              │
              ▼
      data/knowledge.json
```

### 文件清单

| 文件 | 类型 | 说明 |
|------|------|------|
| `src/luoying_bot/ports/repos.py` | 修改 | `KnowledgeItem` 数据类 + `KnowledgeRepo` 接口 |
| `src/luoying_bot/infra/repos/json_knowledge_repo.py` | 新建 | JSON 文件持久化实现 |
| `src/luoying_bot/config.py` | 修改 | 新增 `knowledge_db_file` 配置 |
| `src/luoying_bot/application/services/knowledge_service.py` | 新建 | 知识库业务逻辑（CRUD + 搜索 + LLM 摘要） |
| `src/luoying_bot/application/service_hub.py` | 修改 | 注册 `knowledge_service` |
| `src/luoying_bot/bootstrap.py` | 修改 | 创建并注入 `KnowledgeService` |
| `src/luoying_bot/application/commands/knowledge.py` | 新建 | 6 个知识库命令 |
| `src/luoying_bot/application/agent/skills/knowledge_skill.py` | 新建 | Agent Skill |

---

## 配置项

在 `.env` 中可配置：

```env
# 知识库数据文件路径（默认 ./data/knowledge.json）
KNOWLEDGE_DB_FILE=./data/knowledge.json
```

---

## 命令别名对照

| 指令 | 别名 |
|------|------|
| `/kb_add` | `/知识库添加` |
| `/kb_list` | `/知识库列表` |
| `/kb_search` | `/知识库搜索` |
| `/kb_summary` | `/知识库摘要` |
| `/kb_del` | `/知识库删除` |
| `/kb_clear` | `/知识库清空` |
