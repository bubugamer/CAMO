# CAMO 技术设计文档 v0.1

> 本文档基于 CAMO_PRD-v0.2 编写，采用 Route A（LLM 编排型）技术路线，描述第一至第二阶段的技术实现方案。技术选型以单人开发可落地为约束。

## 1. 概述

### 1.1 文档定位

本文档是 CAMO 产品方案（CAMO_PRD-v0.2）的技术实现方案，覆盖：

- 系统架构与组件划分
- 模型适配层设计
- 文本预处理与抽取管线
- 数据存储 schema
- 角色运行时与一致性校验
- 部署方案与项目结构
- 单人开发计划与风险

不覆盖：

- 前端 / 审核工作台 UI（由上层应用自行实现）
- 第三阶段多角色仿真的完整设计（留待 TDD v0.2）
- 具体 Prompt 的正式版本（Prompt 作为工程产物在代码仓库中迭代，本文档只给出结构与示例）

### 1.2 技术路线总述

采用 Route A（LLM 编排型）：

- **LLM 做理解与生成**：抽取、建模、运行时回复、一致性校验均由 LLM 完成
- **单一主库**：PostgreSQL + pgvector 承载全部结构化数据与向量索引
- **无状态 Runtime**：每次角色调用都是一次 RAG 拼装 + 单次 LLM 调用，无 Agent 循环
- **多模型适配**：通过统一适配层支持本地模型（Ollama）与在线 API（Claude / OpenAI / 国产），按任务路由

### 1.3 核心约束

| 约束 | 值 |
| --- | --- |
| 开发语言 | Python 3.11+ |
| 团队规模 | 1 人 |
| 部署方式 | Docker Compose |
| 主数据库 | PostgreSQL 16 + pgvector |
| 缓存 / 队列 | Redis |
| LLM 调用 | 本地（Ollama）+ 在线 API 混合 |
| 首批测试语料 | 笑傲江湖（长篇小说，~100 万字）、微信聊天记录 |

## 2. 系统架构

### 2.1 架构总览

```mermaid
graph TB
    Client["上层应用"] -->|REST API| API["API 服务<br/>FastAPI"]

    API --> Router["模型适配层<br/>Model Adapter"]
    API --> PG["PostgreSQL 16<br/>+ pgvector"]
    API --> RD["Redis"]

    Worker["异步任务 Worker<br/>ARQ"] --> Router
    Worker --> PG
    API -->|"提交建模任务"| RD
    RD -->|"消费任务"| Worker

    Router --> Online["在线 LLM API<br/>Claude / GPT / 通义"]
    Router --> Local["本地 LLM<br/>Ollama"]

    FS["文件存储<br/>Docker Volume"] --- API
    FS --- Worker

    subgraph Docker Compose
        API
        Worker
        PG
        RD
        Local
    end
```

### 2.2 服务组件

| 服务 | 职责 | 技术选型 |
| --- | --- | --- |
| `api` | HTTP 接口、鉴权、限流 | FastAPI + Uvicorn |
| `worker` | 异步建模任务（文本导入 → 抽取 → 建模 → 入库） | ARQ（基于 Redis 的轻量任务队列） |
| `postgres` | 结构化数据、JSONB 画像、向量索引 | PostgreSQL 16 + pgvector 0.7+ |
| `redis` | 任务队列 broker、Working Memory（按 session）、缓存 | Redis 7 |
| `ollama` | 本地模型推理（可选，按需启动） | Ollama |
| 文件存储 | 原始文本文件 | Docker Volume（本地磁盘） |

### 2.3 数据流

以"导入一部小说 → 生成角色资产 → 单角色对话"为例：

```
1. 用户上传文本 → API 接收 → 存原文到文件存储 → 写 text_sources 表
2. API 提交异步任务 → Redis 队列
3. Worker 消费任务：
   a. 预处理：清洗、分段 → 写 text_segments 表
   b. Pass 1：逐段抽取 Entity Index → 跨段合并去重 → 写 characters 表
   c. Pass 2：逐段抽取 Core/关系/事件/证据 → 章节级聚合 → 全书聚合
   d. 写 characters (Core/Facet)、relationships、events、memories 表
   e. 状态更新为"待审核"
4. 用户（或自动）审核通过 → 资产发布
5. 用户发起对话：
   a. API 加载角色 Profile → 检索 Memory → 拼装上下文 → 调 LLM → 一致性校验
   b. 返回角色回复
```

## 3. 模型适配层

### 3.1 设计目标

- 上层代码不直接依赖任何 LLM SDK，只通过适配层调用
- 支持按"任务类型"路由到不同模型（抽取用强模型，Judge 用便宜模型，Embedding 用本地模型）
- 支持 JSON Schema 结构化输出
- 支持流式与非流式
- 配置驱动，不改代码即可切换模型

### 3.2 核心接口

```python
from dataclasses import dataclass
from typing import Any

@dataclass
class CompletionResult:
    content: str
    structured: dict | None      # JSON Schema 解析后的结构
    usage: dict                   # {"input_tokens": ..., "output_tokens": ...}
    model: str                    # 实际使用的模型 ID
    latency_ms: int

@dataclass
class EmbeddingResult:
    vectors: list[list[float]]
    model: str
    dimensions: int

class ModelAdapter:
    """统一模型调用接口"""

    async def complete(
        self,
        messages: list[dict],
        task: str = "default",             # 任务类型，用于路由
        json_schema: dict | None = None,   # 结构化输出 schema
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> CompletionResult: ...

    async def embed(
        self,
        texts: list[str],
        task: str = "embedding",
    ) -> EmbeddingResult: ...
```

### 3.3 Provider 支持

| Provider | 覆盖模型 | SDK | 说明 |
| --- | --- | --- | --- |
| `anthropic` | Claude Sonnet / Opus / Haiku | `anthropic` | 在线 API |
| `openai_compatible` | GPT 系列、vLLM、LM Studio | `openai` | 在线或本地均适用 |
| `ollama` | Qwen、Llama、Gemma、Mistral 等 | `openai`（Ollama 兼容 OpenAI API） | 本地推理 |

实现上，`openai_compatible` 和 `ollama` 共用 `openai` SDK，只是 `base_url` 不同，代码层面是同一个 Provider。因此实际只需维护两个 Provider 实现：`AnthropicProvider` 和 `OpenAICompatibleProvider`。

### 3.4 任务-模型路由配置

```yaml
# config/models.yaml
providers:
  anthropic:
    api_key: ${ANTHROPIC_API_KEY}
  ollama:
    base_url: "http://ollama:11434/v1"
  openai:
    api_key: ${OPENAI_API_KEY}

routing:
  extraction:       # 抽取任务：用强模型
    provider: anthropic
    model: claude-sonnet-4-20250514
  aggregation:      # 聚合/冲突解决：用强模型
    provider: anthropic
    model: claude-sonnet-4-20250514
  runtime:          # 角色对话：用强模型
    provider: anthropic
    model: claude-sonnet-4-20250514
  judge:            # 一致性校验：用本地便宜模型
    provider: ollama
    model: qwen2.5:32b
  embedding:        # 向量化：用本地 embedding 模型
    provider: ollama
    model: nomic-embed-text

defaults:
  temperature: 0.0
  max_tokens: 4096
```

运行时通过 `task` 参数自动路由：`adapter.complete(messages, task="extraction")` 会查 routing 表找到对应 provider 和 model。

### 3.5 结构化输出

两种 Provider 的结构化输出策略：

| Provider | 方式 |
| --- | --- |
| Anthropic | Tool Use 模式：将 JSON Schema 包装为 tool，模型返回 tool_use 块 |
| OpenAI Compatible | `response_format: { type: "json_schema", json_schema: ... }` 或 tool call |

适配层内部处理差异，对上层统一返回 `CompletionResult.structured`。

### 3.6 重试与降级

- 每次 LLM 调用最多重试 3 次（指数退避）
- 如果主 Provider 连续失败，支持降级到备选 Provider（在 routing 配置中增加 `fallback` 字段）
- 所有调用记录 latency、token usage、error，写入 `llm_call_logs` 表，供后续成本分析

## 4. 文本输入与预处理

### 4.1 预处理管线总览

```
原始文本 → 类型检测 → 类型专用解析器 → 清洗 → 分段 → 写入 text_segments 表
```

类型检测规则：

| 输入特征 | 推断类型 | 对应解析器 |
| --- | --- | --- |
| 包含章节标记（第X章 / 第X回） | `novel` | NovelParser |
| 包含 `[时间] 发送者: 内容` 格式 | `chat` | ChatParser |
| 包含角色名 + 台词标记（冒号、括号注释） | `script` | ScriptParser |
| 包含 Q: / A: 或 问 / 答 模式 | `interview` | InterviewParser |
| 以上均不匹配 | `plain` | PlainParser |

用户也可以在导入时手动指定类型，跳过自动检测。

### 4.2 小说类文本处理（以笑傲江湖为例）

笑傲江湖约 100 万字、40 回。处理要点：

**章节切分**

- 正则匹配章节标记：`r'^第[一二三四五六七八九十百零\d]+[章回节卷]'`
- 每章作为一个 `chapter`，保留章节编号与标题

**段落分段**

- 在章节内按段落边界切分
- 目标段长：1000–2000 字
- 短段落合并（< 300 字的连续段落合并到上一段）
- 长段落按句号切分（保持语义完整性）
- 相邻段之间保留 200 字重叠（overlap），用于跨段指代消解

**对话识别**

- 中文小说对话通常以引号标记（"……"）
- 预处理阶段不做说话人归属（这是抽取阶段的工作），但保留对话标记用于后续特征

**输出**

每个 segment 写入 `text_segments` 表：

```json
{
  "segment_id": "seg_ch01_003",
  "source_id": "src_xiaoao_v1",
  "chapter": "第一回 灭门",
  "position": 3,
  "content": "林平之拔出长剑……（1200字）",
  "raw_offset": 4520,
  "char_count": 1200,
  "has_dialogue": true
}
```

### 4.3 聊天记录处理（以微信记录为例）

微信聊天记录导出后的典型格式：

```
2026-03-15 14:32:05 张三
今天下午开会吧

2026-03-15 14:32:45 李四
好的，几点？

2026-03-15 14:33:12 张三
3点，老地方
```

**消息解析**

- 正则提取：时间戳、发送者、内容
- 每条消息保留原始发送者（天然的 speaker 标注）

**会话切分**

- 相邻消息时间差 > 30 分钟视为新会话（`round`）
- 每个 round 作为一个 segment
- 如果单个 round 消息过多（> 50 条），按 30 条一组再拆分

**输出**

```json
{
  "segment_id": "seg_chat_r005",
  "source_id": "src_wechat_export",
  "round": 5,
  "position": 5,
  "content": "[14:32:05 张三] 今天下午开会吧\n[14:32:45 李四] 好的，几点？\n[14:33:12 张三] 3点，老地方",
  "raw_offset": 12800,
  "char_count": 85,
  "participants": ["张三", "李四"],
  "timestamp_range": ["2026-03-15T14:32:05", "2026-03-15T14:33:12"]
}
```

### 4.4 通用分段规则

无论哪种类型，分段时遵守以下不变式（invariant）：

1. 原文的每一个字符都必须被至少一个 segment 覆盖（除去被清洗掉的噪声）
2. 每个 segment 都记录 `raw_offset`，可以精确回溯到原文位置
3. segment_id 在同一 source 内单调递增且稳定（增量导入新章节不改变已有 segment 的 ID）
4. overlap 区域的文本在两个相邻 segment 中完全一致

## 5. 抽取与建模管线

### 5.1 两遍 Pass 总览

| Pass | 目标 | 粒度 | 模型要求 |
| --- | --- | --- | --- |
| Pass 1 | 建立 Entity Index（角色是谁） | 逐 segment | 中等模型即可 |
| Pass 2 | 抽取 Core / Facet / 关系 / 事件 / 证据 | 逐 segment（带 Pass 1 角色列表作为上下文） | 强模型 |

两遍分开的原因：

- Pass 1 的角色列表是 Pass 2 的前置依赖（Pass 2 需要知道"张三"就是"三哥"就是"张大侠"）
- Pass 1 开销小，可以快速给用户一份角色清单做人工校正
- 人工校正后的角色列表再喂给 Pass 2，提高准确率

### 5.2 Pass 1: Entity Index 抽取

**逐段抽取**

对每个 segment 调用 LLM，提取出现的人物：

```
Prompt 结构（简化示意）：
- System: 你是人物实体识别器。从给定文本中抽取所有出现的人物，输出 JSON。
- User: {segment.content}
- JSON Schema: { characters: [{ name, aliases, titles, description, character_type }] }
```

每个 segment 返回该段中出现的人物列表。

**跨段合并**

在所有 segment 完成 Pass 1 后，执行确定性合并：

1. 按 `name` 精确匹配聚类
2. 按 `aliases` 交集匹配聚类（如果 A 的 aliases 包含 B 的 name，合并）
3. 对剩余未合并的候选，调一次 LLM 做"别名消歧"：给出候选列表，让模型判断哪些是同一人
4. 为每个角色分配 `character_id`，计算 `confidence`（被多少 segment 独立提到）、`first_appearance`

**输出**

写入 `characters` 表的 `index` JSONB 字段。

### 5.3 Pass 2: 语义增强抽取

Pass 1 完成并经过人工校正（可选）后，用确认的角色列表作为先验知识启动 Pass 2。

**逐段抽取**

对每个 segment 调用 LLM，上下文中注入角色清单：

```
Prompt 结构（简化示意）：
- System: 你是人物分析器。已知角色清单如下：{character_list}。
         从给定文本中抽取人物特征、关系、事件，输出 JSON。
- User: {segment.content}
- JSON Schema: {
    trait_evidence: [...],
    motivation_evidence: [...],
    relationship_mentions: [...],
    events: [...],
    communication_samples: [...],
    constraint_evidence: [...]
  }
```

每个 segment 返回该段中的各类证据和信号。

**章节级聚合**

同一章节内的所有段落结果做确定性合并：

- trait_evidence：去重、按 confidence 排序
- relationship_mentions：相同 source-target 对合并，strength 取平均
- events：按 timeline_pos 排序，去重

**全书级聚合**

章节级结果再做一次合并。对于有冲突的字段（例如某章节认为角色"偏保守"但另一章节认为"偏激进"），调用 LLM 做冲突解决：

```
Prompt：以下是角色 {name} 在不同章节中被抽取到的 risk_preference：
- 第3章: low（证据: ...）
- 第15章: medium_high（证据: ...）
请综合判断该角色的 risk_preference，并说明理由。
```

**输出**

写入 `characters` 表的 `core` 和 `facet` JSONB 字段，以及 `relationships`、`events`、`memories` 表。

### 5.4 Map-Reduce 聚合流程

```mermaid
flowchart TB
    subgraph "Pass 1: Entity Index"
        S1["Segment 1"] --> E1["Extract"]
        S2["Segment 2"] --> E2["Extract"]
        S3["Segment N"] --> E3["Extract"]
        E1 --> M1["合并 + 去重"]
        E2 --> M1
        E3 --> M1
        M1 --> DIS["LLM 别名消歧"]
        DIS --> IDX["Entity Index"]
    end

    IDX --> P2["注入角色清单"]

    subgraph "Pass 2: 语义增强"
        P2 --> S1B["Segment 1"] --> EX1["Extract"]
        P2 --> S2B["Segment 2"] --> EX2["Extract"]
        P2 --> S3B["Segment N"] --> EX3["Extract"]

        EX1 --> CH1["Chapter 聚合"]
        EX2 --> CH1
        EX3 --> CH2["Chapter 聚合"]

        CH1 --> BK["全书聚合 + LLM 冲突解决"]
        CH2 --> BK

        BK --> CORE["Entity Core"]
        BK --> FAC["Entity Facet"]
        BK --> REL["Relationships"]
        BK --> EVT["Events"]
        BK --> MEM["Memories"]
    end
```

### 5.5 并行与成本控制

对于笑傲江湖（~100 万字、~700 segments）：

| 阶段 | 预估 LLM 调用次数 | 并行策略 |
| --- | --- | --- |
| Pass 1 逐段 | ~700 次 | asyncio.Semaphore 控制并发（上限 10-20） |
| Pass 1 别名消歧 | 1 次 | 单次调用 |
| Pass 2 逐段 | ~700 次 | 同上 |
| 章节聚合 | ~40 次 | 低并发（5） |
| 全书聚合 + 冲突解决 | ~10–20 次 | 串行 |

总计约 1500 次 LLM 调用。按 Claude Sonnet 计费：
- 平均每次 ~3000 input tokens + ~1500 output tokens
- 总计约 450 万 input + 100 万 output tokens
- 预估成本：~$20–30 / 本小说

并行控制通过 `asyncio.Semaphore` 实现，避免 API 限流。每个 segment 的抽取结果独立，天然可并行。

### 5.6 Prompt 工程策略

- Prompt 模板存放在 `prompts/` 目录，Jinja2 格式，版本跟随代码
- 每个 prompt 对应一个 JSON Schema，存放在 `prompts/schemas/` 目录
- Prompt 中始终要求 LLM 返回 `segment_ids` 引用，确保证据回溯
- Prompt 版本号记入 `extraction_meta`，方便追溯哪个 prompt 版本产出了哪份画像

## 6. 数据存储

### 6.1 PostgreSQL Schema

所有表共用 `camo` schema。以下为核心表定义（省略索引，索引策略单列说明）。

```sql
-- 项目
CREATE TABLE projects (
    project_id    TEXT PRIMARY KEY,
    tenant_id     TEXT NOT NULL,
    name          TEXT NOT NULL,
    description   TEXT,
    config        JSONB DEFAULT '{}',       -- 项目级配置（扩展词表、自定义约束等）
    status        TEXT NOT NULL DEFAULT 'active',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 文本来源
CREATE TABLE text_sources (
    source_id     TEXT PRIMARY KEY,
    project_id    TEXT NOT NULL REFERENCES projects(project_id),
    filename      TEXT,
    source_type   TEXT NOT NULL,             -- novel / chat / script / interview / plain
    file_path     TEXT,                      -- 原始文件在文件存储中的路径
    char_count    INT,
    metadata      JSONB DEFAULT '{}',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 文本片段
CREATE TABLE text_segments (
    segment_id    TEXT PRIMARY KEY,
    source_id     TEXT NOT NULL REFERENCES text_sources(source_id),
    position      INT NOT NULL,
    chapter       TEXT,
    round         INT,                       -- 聊天记录专用
    content       TEXT NOT NULL,
    raw_offset    INT NOT NULL,
    char_count    INT NOT NULL,
    metadata      JSONB DEFAULT '{}',        -- has_dialogue, participants, timestamp_range 等
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 角色（Index + Core + Facet 作为 JSONB 列）
CREATE TABLE characters (
    character_id  TEXT PRIMARY KEY,
    project_id    TEXT NOT NULL REFERENCES projects(project_id),
    schema_version TEXT NOT NULL DEFAULT '0.2',
    status        TEXT NOT NULL DEFAULT 'draft',  -- draft / reviewing / published
    index         JSONB NOT NULL,            -- Entity Index 字段
    core          JSONB,                     -- Entity Core 字段
    facet         JSONB,                     -- Entity Facet 字段
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 关系
CREATE TABLE relationships (
    relationship_id TEXT PRIMARY KEY,
    project_id      TEXT NOT NULL REFERENCES projects(project_id),
    schema_version  TEXT NOT NULL DEFAULT '0.2',
    source_id       TEXT NOT NULL REFERENCES characters(character_id),
    target_id       TEXT NOT NULL REFERENCES characters(character_id),
    relation_category TEXT NOT NULL,
    relation_subtype  TEXT NOT NULL,
    public_state    JSONB NOT NULL,
    hidden_state    JSONB,
    timeline        JSONB DEFAULT '[]',
    source_segments TEXT[] DEFAULT '{}',
    confidence      REAL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 事件
CREATE TABLE events (
    event_id      TEXT PRIMARY KEY,
    project_id    TEXT NOT NULL REFERENCES projects(project_id),
    schema_version TEXT NOT NULL DEFAULT '0.2',
    title         TEXT NOT NULL,
    description   TEXT,
    timeline_pos  INT,
    participants  TEXT[] DEFAULT '{}',
    location      TEXT,
    emotion_valence TEXT,
    source_segments TEXT[] DEFAULT '{}',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 记忆（含 pgvector 列）
CREATE TABLE memories (
    memory_id     TEXT PRIMARY KEY,
    character_id  TEXT NOT NULL REFERENCES characters(character_id),
    project_id    TEXT NOT NULL REFERENCES projects(project_id),
    schema_version TEXT NOT NULL DEFAULT '0.2',
    memory_type   TEXT NOT NULL,             -- profile / relationship / episodic / working
    salience      REAL NOT NULL DEFAULT 0.5,
    recency       REAL NOT NULL DEFAULT 1.0,
    content       TEXT NOT NULL,
    source_event_id TEXT REFERENCES events(event_id),
    related_character_ids TEXT[] DEFAULT '{}',
    emotion_valence TEXT,
    source_segments TEXT[] DEFAULT '{}',
    embedding     vector(768),               -- pgvector，维度匹配 embedding 模型
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 角色版本快照
CREATE TABLE character_versions (
    version_id    TEXT PRIMARY KEY,
    character_id  TEXT NOT NULL REFERENCES characters(character_id),
    version_num   INT NOT NULL,
    snapshot      JSONB NOT NULL,            -- 完整 index + core + facet 快照
    diff          JSONB,                     -- 与上一版本的差异
    created_by    TEXT,                      -- 审核者或 system
    note          TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(character_id, version_num)
);

-- 审核记录
CREATE TABLE reviews (
    review_id     TEXT PRIMARY KEY,
    target_type   TEXT NOT NULL,             -- entity_index / entity_core / entity_facet / relationship
    target_id     TEXT NOT NULL,
    diff          JSONB,
    reviewer      TEXT,
    status        TEXT NOT NULL DEFAULT 'pending',  -- pending / approved / rejected
    note          TEXT,
    reviewed_at   TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 外部反馈
CREATE TABLE feedbacks (
    feedback_id   TEXT PRIMARY KEY,
    source        TEXT NOT NULL,             -- end_user / reviewer / system
    target_type   TEXT NOT NULL,
    target_id     TEXT NOT NULL,
    rating        TEXT,
    reason        TEXT,
    linked_assets TEXT[] DEFAULT '{}',
    suggested_action TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- LLM 调用日志
CREATE TABLE llm_call_logs (
    log_id        BIGSERIAL PRIMARY KEY,
    task          TEXT NOT NULL,
    provider      TEXT NOT NULL,
    model         TEXT NOT NULL,
    input_tokens  INT,
    output_tokens INT,
    latency_ms    INT,
    status        TEXT NOT NULL,             -- success / error
    error_message TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### 6.2 索引策略

```sql
-- 高频查询路径
CREATE INDEX idx_segments_source ON text_segments(source_id, position);
CREATE INDEX idx_characters_project ON characters(project_id);
CREATE INDEX idx_relationships_source ON relationships(source_id);
CREATE INDEX idx_relationships_target ON relationships(target_id);
CREATE INDEX idx_relationships_project ON relationships(project_id);
CREATE INDEX idx_events_project ON events(project_id, timeline_pos);
CREATE INDEX idx_memories_character ON memories(character_id, memory_type);
CREATE INDEX idx_memories_project ON memories(project_id);

-- pgvector HNSW 索引（用于记忆语义检索）
CREATE INDEX idx_memories_embedding ON memories
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- JSONB GIN 索引（用于角色画像内部字段查询）
CREATE INDEX idx_characters_index ON characters USING gin (index);
CREATE INDEX idx_characters_core ON characters USING gin (core);
```

### 6.3 pgvector 配置

- Embedding 维度：768（匹配 `nomic-embed-text` 等主流开源 embedding 模型）
- 索引类型：HNSW（查询延迟低，适合在线检索）
- 距离度量：cosine similarity
- 如果后续切换 embedding 模型导致维度变化，需要重建 embedding 列和索引。通过 Alembic migration 管理

### 6.4 Redis 用途

| 用途 | Key 模式 | 过期策略 |
| --- | --- | --- |
| 任务队列 | ARQ 内部管理 | 任务完成后自动清理 |
| Working Memory | `wm:{session_id}` | session 结束或 TTL 2 小时 |
| 角色 Profile 缓存 | `profile:{character_id}` | TTL 10 分钟，写入时失效 |
| 建模任务状态 | `job:{job_id}` | TTL 24 小时 |

### 6.5 文件存储

初期使用 Docker Volume 挂载本地目录：

```
/data/
├── raw_texts/          # 原始上传文件
│   └── {source_id}/
│       └── original.txt
└── exports/            # 导出文件（JSON 资产包等）
```

后续如需迁移到云存储，只需替换文件读写层为 S3 兼容接口。

### 6.6 版本化策略

角色资产的每一次审核修改都产生一个新版本：

1. 修改 `characters` 表中的 `index` / `core` / `facet` 字段
2. 同时向 `character_versions` 插入一行，包含完整快照和 diff
3. `version_num` 单调递增

回滚操作：从 `character_versions` 读取目标版本的 `snapshot`，覆写到 `characters` 表，并记录新的版本条目（记录回滚动作本身）。

### 6.7 数据库迁移

使用 Alembic 管理 schema 迁移：

- `migrations/` 目录存放迁移脚本
- 每次 schema 变更生成迁移文件
- Docker Compose 启动时自动执行 `alembic upgrade head`

## 7. 角色运行时

### 7.1 总体流程

```mermaid
flowchart LR
    A[用户请求] --> B[加载角色 Profile]
    B --> C[四路记忆检索]
    C --> D[上下文拼装]
    D --> E[LLM 调用]
    E --> F[一致性校验]
    F -->|通过| G[返回回复]
    F -->|不通过| E
    E -.->|新记忆| H[记忆回写]
```

### 7.2 上下文拼装

Runtime 的核心工作是把散落在数据库各处的角色信息拼成一个 LLM 能理解的上下文窗口。

拼装顺序与优先级（从高到低，超出窗口上限时低优先级的先丢弃）：

| 优先级 | 内容 | 来源 | 预估 token |
| --- | --- | --- | --- |
| P0 | System Prompt（角色扮演指令 + 约束规则） | 模板 + constraint_profile | ~500 |
| P1 | 角色身份与核心画像 | Entity Index + Core | ~800 |
| P2 | 当前对话对象的关系状态 | relationships 表 | ~300 |
| P3 | 最近 Working Memory | Redis | ~1000 |
| P4 | 相关 Episodic Memory（TopK） | pgvector 检索 | ~800 |
| P5 | 补充性 Facet 信息（口头禅、外貌） | Entity Facet.biographical_notes | ~300 |
| P6 | 用户当前输入 | 请求体 | 变长 |

上下文窗口上限默认 8000 tokens（为输出留 2000 tokens 余量，合计 10K 窗口）。可在 config 中按模型调整。

**拼装模板结构**

```
[System]
你是{name}。{description}

## 你的核心人格
- 开放性: {openness}/100 — {openness_desc}
- ...

## 你的动机
- 主要: {primary_motivations}
- 次要: {secondary_motivations}

## 你的说话风格
- 语气: {tone}
- 直接程度: {directness}
- ...

## 约束规则（绝对不可违反）
{forbidden_behaviors_list}

## 你与当前对话者的关系
{relationship_summary}

## 你的相关记忆
{retrieved_memories}

[Recent conversation]
{working_memory}

[User]
{user_input}
```

### 7.3 记忆检索细节

四路并行检索（`asyncio.gather`）：

1. **Profile Memory**：直接从 `characters.core` 和 `characters.facet` 中提取，无需检索，全量加载
2. **Relationship Memory**：`SELECT * FROM relationships WHERE (source_id = $1 OR target_id = $1)`，结果转为自然语言描述
3. **Episodic Memory**：
   ```sql
   SELECT memory_id, content, salience,
          1 - (embedding <=> $query_vec) AS similarity
   FROM memories
   WHERE character_id = $1
     AND memory_type = 'episodic'
   ORDER BY salience * (1 - (embedding <=> $query_vec)) DESC
   LIMIT $topk
   ```
   其中 `$query_vec` 是用户当前输入的 embedding
4. **Working Memory**：从 Redis `wm:{session_id}` 读取最近 N 轮对话，按时间倒序

### 7.4 单角色调用

每次调用是一次无状态请求：

```python
async def run_character_turn(request: TurnRequest) -> TurnResponse:
    # 1. 加载角色
    character = await load_character(request.speaker_target)

    # 2. 四路记忆检索
    profile, relationships, episodic, working = await asyncio.gather(
        load_profile_memory(character),
        load_relationship_memory(character, request.participants),
        search_episodic_memory(character, request.user_input.content),
        load_working_memory(request.session_id),
    )

    # 3. 拼装上下文
    context = assemble_context(character, profile, relationships,
                               episodic, working, request)

    # 4. LLM 调用
    result = await model_adapter.complete(
        messages=context.to_messages(),
        task="runtime",
        json_schema=runtime_output_schema,
    )

    # 5. 一致性校验
    check = await consistency_check(character, result, context)
    if not check.passed and request.retry_count < MAX_RETRIES:
        return await run_character_turn(request.with_retry())

    # 6. 写 Working Memory
    await append_working_memory(request.session_id, result)

    # 7. 记忆回写（异步，不阻塞响应）
    if should_write_episodic(result):
        await enqueue_memory_writeback(character, result)

    return TurnResponse(response=result, consistency_check=check)
```

### 7.5 多角色调度（第三阶段预留）

第一、二阶段只支持单角色对话。多角色调度在 TDD v0.2 中展开。

当前 Runtime 接口已预留 `participants` 和 `scene` 参数，确保后续多角色支持不需要改 API 契约。

### 7.6 Working Memory 管理

- 存储格式：Redis List，每项是一轮对话的 JSON（speaker + content + timestamp）
- 最大保留轮数：50 轮（可配置）
- 超出时按 FIFO 淘汰最早轮次
- Session 过期：TTL 2 小时无活动自动清理
- Session 显式结束时：可选择将 Working Memory 中有价值的内容提升为 Episodic Memory

### 7.7 记忆回写

Runtime 在生成回复后，异步判断是否需要创建新的 Episodic Memory：

判断规则（初版，可迭代）：

- 对话中出现了新的事件（角色做出承诺、发生冲突、获得新信息）
- 由 LLM 在 `reasoning_summary` 中标注 `memory_worthy: true`
- 由上层应用显式调用写入接口

回写流程：

1. 从 LLM 回复中提取 memory 候选
2. 调 embedding 模型生成向量
3. 写入 `memories` 表（memory_type = 'episodic'）
4. 不阻塞 Runtime 响应（通过 ARQ 异步执行）

## 8. 一致性校验

### 8.1 校验架构

```mermaid
flowchart LR
    A[Runtime 输出] --> B[规则引擎]
    A --> C[Judge LLM]
    B --> D[汇总]
    C --> D
    D -->|全部通过| E[accept]
    D -->|有 warning| F[warn]
    D -->|有 high severity| G[regenerate / block]
```

规则引擎和 Judge LLM 并行执行，结果汇总后取最严重的 action。

### 8.2 规则引擎（Python）

处理机械性、可精确判定的维度：

| 维度 | 检测方式 |
| --- | --- |
| forbidden_behaviors | 遍历所有 tag，按 namespace 匹配：`meta.break_character` 用关键词表（"我是AI"、"作为语言模型"等）；`style.modern_slang` 用现代网络用语词表；`setting.out_of_setting` 用时代敏感词表 |
| knowledge_scope | 如果 scope = `strict` 或 `bounded`，检测回复中是否出现明显超出原文范围的实体或概念 |
| 约束一致性 | 直接匹配 `constraint_profile` 中的 tag |

规则引擎的优势：延迟 < 10ms，零 LLM 成本，零误判（在词表覆盖范围内）。

词表存放在 `data/rules/` 目录，格式为文本文件，每行一个词 / 短语。可按项目扩展。

### 8.3 Judge LLM

处理需要语义理解的维度：

| 维度 | 给 Judge 的输入 |
| --- | --- |
| 人设一致性 | trait_profile + motivation_profile + 生成的回复 |
| 关系一致性 | 当前对话对象的 relationship 状态 + 回复中的称谓和态度 |
| 语体一致性 | communication_profile + 回复的语言风格特征 |
| 时间线一致性 | 角色的 temporal_snapshots + 回复中提到的时间敏感信息 |

Judge Prompt 结构：

```
System: 你是角色一致性校验器。给定角色画像和角色输出，判断是否存在不一致。
User:
## 角色画像
{character_summary}

## 角色输出
{runtime_response}

## 请检查以下维度
1. 人设一致性：回复是否符合角色的人格特质和动机？
2. 关系一致性：回复对对话对象的态度是否符合关系图谱？
3. 语体一致性：回复的语言风格是否符合 communication_profile？
4. 时间线一致性：回复是否包含超出角色当前时间线的信息？

输出 JSON。
```

Judge 模型使用便宜/本地模型（如 `qwen2.5:32b`），降低延迟和成本。

### 8.4 校验结果处理

```python
def resolve_action(rule_issues: list, judge_issues: list) -> str:
    all_issues = rule_issues + judge_issues
    if not all_issues:
        return "accept"

    max_severity = max(i.severity for i in all_issues)
    if max_severity == "high":
        return "regenerate"    # 交给 Runtime 重试
    elif max_severity == "medium":
        return "warn"          # 放行但标记
    else:
        return "accept"        # low severity 不阻塞
```

重试上限由 `runtime_options.max_retries` 控制（默认 2 次）。超过上限仍不通过的，返回 `block` 并附带所有 issues。

## 9. 审核与回流

### 9.1 工作流

审核模块不含 UI，只提供数据接口。审核工作台由上层应用或独立前端实现。

```
建模完成 → 角色状态 = draft → 审核者查看 → 修改/通过 → 生成新版本 → 状态 = published
                                                ↑
运行时反馈 / 外部反馈 → feedbacks 表 → 关联到角色 ─┘
```

### 9.2 关键接口行为

- **获取审核任务**：查 `characters WHERE status = 'draft'` 或 `reviews WHERE status = 'pending'`
- **提交审核**：修改 `characters` 表对应 JSONB 字段 → 创建 `character_versions` 快照 → 更新 `reviews` 状态
- **回滚**：从 `character_versions` 读取目标版本 `snapshot` → 覆写 `characters` → 记录新版本（标记为回滚操作）
- **外部反馈**：写入 `feedbacks` 表 → 可选自动关联到待审核队列

### 9.3 diff 计算

使用 Python `deepdiff` 库对两份 JSONB 做结构化 diff，存入 `character_versions.diff`。前端可以基于 diff 渲染"变化高亮视图"。

## 10. 对外接口

### 10.1 框架与规范

- 框架：FastAPI
- 路径前缀：`/api/v1`
- 序列化：JSON（Pydantic v2 model）
- 文档：自动生成 OpenAPI 3.1（FastAPI 内置）
- 异步：全部使用 `async def`

### 10.2 认证与限流

初期采用 API Key 认证（Header: `X-API-Key`），单人开发阶段足够。后续如需多租户可升级为 OAuth2 / JWT。

限流通过 `slowapi`（基于 `limits`）实现，按 API Key 限制：

| 接口类别 | 限流 |
| --- | --- |
| 读操作 | 60 次/分 |
| 写操作 | 20 次/分 |
| Runtime 对话 | 30 次/分 |
| 建模任务提交 | 5 次/分 |

### 10.3 路由模块划分

```python
# api/routes/
├── projects.py        # /api/v1/projects
├── texts.py           # /api/v1/projects/{pid}/texts
├── modeling.py         # /api/v1/projects/{pid}/modeling
├── characters.py       # /api/v1/characters
├── relationships.py    # /api/v1/relationships
├── events.py           # /api/v1/projects/{pid}/events
├── memories.py         # /api/v1/characters/{cid}/memories
├── runtime.py          # /api/v1/runtime
├── consistency.py      # /api/v1/consistency
├── reviews.py          # /api/v1/reviews
└── feedbacks.py        # /api/v1/feedbacks
```

端点与 PRD 8.8.3 的接口列表一一对应，此处不重复列出。所有端点均通过 FastAPI 自动生成 OpenAPI 文档，可在 `/docs` 访问。

### 10.4 异步任务接口

建模任务是长时间运行的操作，采用"提交-轮询"模式：

1. `POST /api/v1/projects/{pid}/modeling` → 返回 `job_id`
2. `GET /api/v1/projects/{pid}/modeling/{job_id}` → 返回任务状态（queued / running / completed / failed）和进度百分比
3. 任务进度通过 Redis `job:{job_id}` 键实时更新

后续如需 WebSocket 推送，可在 FastAPI 中增加 WS 端点，监听 Redis 发布的进度消息。

## 11. 部署方案

### 11.1 Docker Compose 配置

```yaml
# docker-compose.yml
version: "3.8"

services:
  api:
    build: .
    command: uvicorn camo.api.main:app --host 0.0.0.0 --port 8000
    ports:
      - "8000:8000"
    env_file: .env
    volumes:
      - data:/data
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy

  worker:
    build: .
    command: arq camo.tasks.worker.WorkerSettings
    env_file: .env
    volumes:
      - data:/data
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy

  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_DB: camo
      POSTGRES_USER: camo
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U camo"]
      interval: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redisdata:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      retries: 5

  ollama:
    image: ollama/ollama:latest
    ports:
      - "11434:11434"
    volumes:
      - ollama_models:/root/.ollama
    profiles:
      - local-llm    # 只在需要本地模型时启动: docker compose --profile local-llm up

volumes:
  data:
  pgdata:
  redisdata:
  ollama_models:
```

### 11.2 环境变量

```bash
# .env
POSTGRES_PASSWORD=changeme
DATABASE_URL=postgresql+asyncpg://camo:changeme@postgres:5432/camo
REDIS_URL=redis://redis:6379/0

# LLM API Keys（按需配置）
ANTHROPIC_API_KEY=
OPENAI_API_KEY=

# 模型路由配置
MODEL_CONFIG_PATH=config/models.yaml
```

### 11.3 初始化流程

```bash
# 首次部署
docker compose up -d postgres redis
docker compose run --rm api alembic upgrade head    # 执行数据库迁移
docker compose up -d

# 如需本地模型
docker compose --profile local-llm up -d ollama
docker compose exec ollama ollama pull nomic-embed-text
docker compose exec ollama ollama pull qwen2.5:32b
```

## 12. 项目结构

```
camo/
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml              # 依赖管理（uv / pip）
├── .env.example
├── config/
│   └── models.yaml             # 模型路由配置
├── data/
│   └── rules/                  # 一致性校验词表
│       ├── modern_slang.txt
│       ├── ai_self_reference.txt
│       └── anachronism_keywords.txt
├── migrations/                 # Alembic 迁移
│   ├── env.py
│   └── versions/
├── prompts/                    # Prompt 模板
│   ├── extraction/
│   │   ├── entity_index.jinja2
│   │   ├── entity_enrichment.jinja2
│   │   └── alias_disambiguation.jinja2
│   ├── aggregation/
│   │   └── conflict_resolution.jinja2
│   ├── runtime/
│   │   └── character_system.jinja2
│   ├── judge/
│   │   └── consistency_check.jinja2
│   └── schemas/                # JSON Schema 定义
│       ├── entity_index.json
│       ├── entity_enrichment.json
│       └── consistency_result.json
├── src/
│   └── camo/
│       ├── __init__.py
│       ├── api/                # FastAPI 应用
│       │   ├── main.py         # FastAPI app 实例、中间件
│       │   ├── deps.py         # 依赖注入（DB session、adapter）
│       │   └── routes/         # 路由模块（见 10.3）
│       ├── core/               # 领域模型
│       │   ├── schemas.py      # Pydantic models（对应 PRD 数据结构）
│       │   └── enums.py        # 枚举定义
│       ├── db/                 # 数据层
│       │   ├── models.py       # SQLAlchemy ORM models
│       │   ├── session.py      # async session factory
│       │   └── queries/        # 常用查询封装
│       ├── extraction/         # 抽取管线
│       │   ├── pipeline.py     # 总调度：Pass 1 + Pass 2
│       │   ├── parsers/        # 各类型文本解析器
│       │   │   ├── novel.py
│       │   │   ├── chat.py
│       │   │   └── ...
│       │   ├── pass1.py        # Entity Index 抽取
│       │   ├── pass2.py        # 语义增强抽取
│       │   └── aggregation.py  # Map-Reduce 聚合
│       ├── runtime/            # 角色运行时
│       │   ├── engine.py       # 核心调用逻辑
│       │   ├── context.py      # 上下文拼装
│       │   └── memory.py       # 记忆检索 + 回写
│       ├── consistency/        # 一致性校验
│       │   ├── checker.py      # 总入口
│       │   ├── rules.py        # 规则引擎
│       │   └── judge.py        # Judge LLM
│       ├── models/             # LLM 适配层
│       │   ├── adapter.py      # ModelAdapter 实现
│       │   ├── providers/
│       │   │   ├── anthropic.py
│       │   │   └── openai_compat.py
│       │   └── config.py       # 路由配置加载
│       ├── review/             # 审核与回流
│       │   └── service.py
│       └── tasks/              # 异步任务
│           ├── worker.py       # ARQ WorkerSettings
│           └── modeling.py     # 建模任务定义
└── tests/
    ├── conftest.py
    ├── test_extraction/
    ├── test_runtime/
    ├── test_consistency/
    └── test_api/
```

## 13. 开发计划

### 13.1 单人开发节奏

以一个人全职为前提，预估各里程碑耗时。

### 13.2 第一阶段：人物理解引擎（~10 周）

| 周 | 里程碑 | 主要交付 |
| --- | --- | --- |
| 1–2 | M1.1 基础设施 | Docker Compose、PG schema、Alembic、FastAPI 骨架、模型适配层、项目/文本 CRUD API |
| 3–4 | M1.2 Entity Index | 文本预处理管线（novel + chat 解析器）、Pass 1 抽取、别名消歧、角色清单 API |
| 5–7 | M1.3 Entity Core | Pass 2 抽取、Map-Reduce 聚合、冲突解决、Core 查询 API |
| 8 | M1.4 Entity Facet | evidence_map 构建、biographical_notes、temporal_snapshots |
| 9 | M1.5 关系图谱 | 关系抽取（Pass 2 产物落库）、关系查询 API |
| 10 | M1.6–M1.7 审核 + 验收 | 审核 CRUD、版本化、在笑傲江湖语料上对标 PRD 验收指标 |

### 13.3 第二阶段：角色驱动引擎（~8 周）

| 周 | 里程碑 | 主要交付 |
| --- | --- | --- |
| 11–12 | M2.1 记忆结构与检索 | Event/Memory 表、embedding 生成、pgvector 检索、四路并行检索 |
| 13–15 | M2.2 单角色运行时 | 上下文拼装、Runtime 调用流程、Working Memory（Redis）、Session 管理 |
| 16–17 | M2.3 一致性校验 | 规则引擎 + Judge LLM、校验流程、词表建设 |
| 18 | M2.4–M2.5 记忆回写 + 验收 | 记忆回写闭环、在笑傲江湖角色上对标 PRD 验收指标 |

**总计约 18 周（~4.5 个月）完成第一 + 第二阶段。**

### 13.4 关键依赖与可并行项

- 模型适配层（第 1 周）是几乎所有后续工作的前置依赖，必须最先完成
- 文本预处理和 PG schema 可并行开发
- Pass 1 和 Pass 2 的 Prompt 设计可以在代码框架搭好后集中迭代
- 一致性校验的词表可以在等 LLM 测试结果的间隙手动整理

## 14. 风险与缓解

| 风险 | 影响 | 缓解措施 |
| --- | --- | --- |
| LLM API 限流 / 不稳定 | 建模任务中断、延迟超标 | 指数退避重试 + Provider 降级 + 本地模型兜底 |
| 100 万字小说抽取成本高 | 单次建模 $20–30 | 按需抽取（只处理有对话的段落）+ 本地模型分担 Pass 1 |
| Prompt 质量不稳定 | 画像准确率不达标 | Prompt 版本管理 + 评测语料回归测试 |
| pgvector 在大规模记忆下性能下降 | 记忆检索延迟升高 | 初期数据量远不到瓶颈；到瓶颈时迁移到专用向量库 |
| 单人开发的 bus factor | 项目中断风险 | 代码仓库 + 文档 + 自动化测试保持项目可接手性 |
| 角色运行时 P95 > 3s | 用户体验差 | LLM 调用占延迟主体，选快模型 + 控制上下文长度 + 缓存 Profile |
| 别名消歧准确率不足 | 角色合并出错 | Pass 1 后加人工校正环节 + 增量修正 |

## 15. A→B 迁移预留

当前 Route A 架构在以下位置为未来 Route B 迁移预留了接口：

| 组件 | 当前实现 | 迁移到 Route B 时 | 预留措施 |
| --- | --- | --- | --- |
| 关系存储 | PG 边表 | Neo4j 图库 | 关系查询封装在 `db/queries/relationships.py` 中，上层不直接写 SQL |
| 记忆向量 | pgvector | Qdrant / Milvus | 记忆检索封装在 `runtime/memory.py` 中，只暴露 `search(query, topk)` 接口 |
| Runtime | 无状态 RAG | Agent 循环 | Runtime 入口封装在 `runtime/engine.py`，替换内部实现不影响 API |
| 模型调用 | 单次 complete | Agent 工具调用 | ModelAdapter 已支持 tool use，扩展为 agent loop 只需在 engine 层加循环 |
| 一致性校验 | 规则 + Judge LLM | 规则 + 图查询 + Judge | checker.py 采用策略模式，可插入新的 check 策略 |

**迁移触发点建议**：当以下任一条件成立时，启动向 Route B 的渐进迁移：

- 单项目角色数超过 200 且关系边超过 5000 条（PG 关系查询开始变慢）
- 第三阶段的多角色仿真场景开发启动
- 记忆条目超过 100 万条（pgvector 性能到临界点）

本版本到此结束。
