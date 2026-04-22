# CAMO 系统规格说明书

| 字段 | 值 |
| --- | --- |
| 文档标题 | CAMO 系统规格说明书 |
| 版本 | 1.0 |
| 日期 | 2026-04-21 |
| 状态 | 草稿 |
| 整合来源 | CAMO_PRD-v0.2, CAMO_PRD-v0.3, CAMO_TDD-v0.1, CAMO_TDD-v0.2 |
| 变更记录 | v1.0（2026-04-21）：首次整合四份过程文档 |

---

## 1. 概述

### 1.1 产品定义

CAMO 是一套面向非结构化文本的人物理解与角色驱动基座。它将小说、聊天记录、剧本、访谈、wiki 等文本输入，转化为可复用、可调用、可持续运行的角色资产（人物画像、关系图谱、事件、记忆、语言风格与运行约束），并为上层应用提供统一的人物运行能力。

### 1.2 产品边界

CAMO 不做以下事项：

- 最终消费型聊天产品或前端 UI，CAMO 是基座能力
- 模型训练与微调，采用"结构化资产 + Runtime 编排"路线
- 平台级通用内容审核，只做角色一致性与边界约束
- 非人物实体的完整结构化世界建模（组织、地点、物品仅作为人物上下文出现）
- 跨项目人物融合与知识共享
- 文本版权与来源合规校验
- 实时语音 / 视频生成
- "无时点"的原作角色聊天，原作角色对话必须绑定明确锚点

### 1.3 关键产品决策

1. **原作角色聊天必须有锚点**：不支持"整合全书、不分时点"的模式
2. **锚点采用混合模式**：底层以页数、章节、时间戳等原始进度定位，前台展示阶段名与摘要
3. **越界问题采用角色式拒答**：默认不直接输出系统提示语
4. **锚点切换等同于切换世界线**：必须开启新会话，Working Memory 不跨锚点复用
5. **阶段快照优先于全局画像**：冲突时以当前阶段快照为准
6. **当前锚点必须明确展示**：聊天界面常驻显示当前阶段卡片

### 1.4 技术路线

采用 Route A（LLM 编排型）：

- LLM 做理解与生成：抽取、建模、运行时回复、一致性校验均由 LLM 完成
- 单一主库：PostgreSQL + pgvector 承载全部结构化数据与向量索引
- 无状态 Runtime：每次角色调用都是一次 RAG 拼装 + 单次 LLM 调用，无 Agent 循环
- 多模型适配：通过统一适配层支持本地模型（Ollama）与在线 API（Claude / OpenAI / 国产），按任务路由

### 1.5 核心约束

| 约束 | 值 |
| --- | --- |
| 开发语言 | Python 3.11+ |
| 部署方式 | Docker Compose |
| 主数据库 | PostgreSQL 16 + pgvector |
| 缓存 / 队列 | Redis 7 |
| LLM 调用 | 本地（Ollama）+ 在线 API 混合 |

---

## 2. 术语表

| 术语 | 定义 |
| --- | --- |
| Character | 被 CAMO 建模的人物，拥有唯一 `character_id` |
| Character Index | 人物索引层，回答"这是谁" |
| Character Core | 人物核心层，回答"这个人是怎么运作的" |
| Character Facet | 人物细节层，回答"为什么这么判断，以及有哪些阶段差异" |
| Relationship | 两个 Character 之间的有向关系边，可带时间变化 |
| Event | 客观发生过的事件，带时间顺序 |
| Memory | 某个角色对事件、关系或自身设定的记忆承载 |
| Working Memory | 当前会话内的短期对话记忆，属于 Memory 的运行时子类 |
| Time Anchor | 角色本次会话所处的明确时间锚点，决定其当前知道什么 |
| Runtime Anchor | Time Anchor 在运行时中的结构化表示 |
| AnchorState | Runtime Anchor 解析后的内部对象 |
| Temporal Snapshot | 人物在某一阶段的快照，描述该阶段的状态、认知范围和画像覆写 |
| Anchor Session | 与单一时间锚点绑定的会话，一个会话只允许一个锚点 |
| Knowledge Boundary | 角色在当前时点下可知信息的边界，包含时代、剧情、设定和项目范围 |
| Constraint Profile | Character Core 中描述知识边界、禁说规则与角色一致性约束的结构 |
| Fixed Identity Layer | 角色稳定身份层 |
| Current Stage Layer | 当前阶段层 |
| Pre-cutoff Memory Layer | 截止点之前的记忆层 |
| Refusal Rule Layer | 越界问题处理规则层 |
| Profile | 画像，指某一类结构化描述（如 trait_profile），多条 Profile 组成 Character Core |
| Source Segment | 证据片段，原文切分后的最小单元 |
| Schema Version | 数据结构版本号，每条顶层资产都带此字段 |

---

## 3. 目标用户

### 3.1 直接用户

- 上层应用产品经理
- AI 应用开发者
- 角色互动类产品团队
- IP 互动内容团队
- 游戏与叙事系统设计人员
- 社交模拟类产品研发团队
- 内容创作者与作者

### 3.2 间接用户

- 小说 / 动漫 / 影视 IP 爱好者
- 角色聊天与角色扮演用户
- AI 伴侣用户
- 互动叙事与模拟世界玩家
- 社交模拟、博弈类玩法用户

---

## 4. 阶段目标与验收指标

### 4.1 第一阶段：人物理解引擎

**功能范围**：文本导入、角色抽取、人物画像生成（Character Index + Core + Facet）、关系图谱生成、时间顺序归一、阶段性快照抽取、证据片段回溯。

| 指标 | 目标 |
| --- | --- |
| 主要角色召回率 | ≥ 90% |
| 角色别名归一准确率 | ≥ 95% |
| 人物画像人工评审通过率 | ≥ 80% |
| 主要关系召回率 | ≥ 85% |
| 时间顺序人工抽检正确率 | ≥ 90% |
| 证据回溯覆盖率 | 100% |

### 4.2 第二阶段：角色驱动引擎

**功能范围**：单角色可扮演、基于时间锚点的角色定位、角色知识边界控制、阶段快照加载、截止前记忆检索、一致性校验、锚点切换与会话隔离。

| 指标 | 目标 |
| --- | --- |
| 单轮对话人设一致性人评 | ≥ 4 / 5 |
| 时间线定位可理解性人评 | ≥ 4 / 5 |
| 知识边界命中率 | ≥ 95% |
| 锚点切换后记忆串线率 | 0 个严重问题 |
| 越界问题角色式拒答合理性人评 | ≥ 85% |
| 一致性校验误杀率 | ≤ 5% |
| 一致性校验漏报率 | ≤ 10% |

### 4.3 第三阶段：多角色仿真

**功能范围**：多角色群聊、场景状态维护、信息不对称控制、多角色各自时间锚点与可见性控制、关系驱动发言与互动。

| 指标 | 目标 |
| --- | --- |
| 多轮对话中每轮角色一致性人评 | ≥ 4 / 5 |
| 关系驱动发言合理性人评 | ≥ 80% |
| 多角色场景状态维护正确率 | ≥ 85% |
| 信息不对称规则遵守率 | ≥ 95% |

---

## 5. 核心场景

### 5.1 文本人物建模场景

输入小说、聊天记录、剧本或访谈，系统输出：人物名单、角色画像（Index / Core / Facet）、关系图谱、关键事件、时间顺序索引、阶段性快照、证据引用。

支持增量导入（逐章节上传，画像随之演化）和差异视图（相邻两次建模结果之间的变化）。

### 5.2 单角色锚点聊天场景

用户选择角色并指定时点进行对话。系统保证：角色身份稳定、当前阶段明确、只使用该时点之前的事件/关系/记忆、遇越界问题以角色口吻拒答、聊天界面持续展示当前锚点和阶段摘要。

### 5.3 锚点切换场景

用户在对话过程中切换到另一个时点。系统保证：切换后进入新会话、旧会话 Working Memory 不带入新时点、当前显示信息同步切换。

### 5.4 越界问题场景

用户向角色提出超出知识边界的问题（未来剧情、时代外概念、作品外设定等）。系统让角色以自身身份合理回应，不使用系统口吻硬拦截。

### 5.5 多角色群聊场景

多个角色在同一对话空间交互：@指定角色发言、指定角色间对话、系统决定是否有人插话、维持角色间关系逻辑。

### 5.6 社交模拟 / 博弈场景

多角色在规则框架下持续互动：保留角色动机与偏好、根据关系图谱做行为决策、支持回合制流程、支持信息不对称（如狼人杀场景）、每个角色独立 Working Memory 视图、场景结束后可输出完整回放日志。

### 5.7 内容创作反向校验场景

作者上传设定集、章节或大纲，系统输出：哪些阶段切换清晰、哪些时点边界模糊、哪些阶段快照缺失、哪些角色在不同阶段出现画像漂移。

---

## 6. 系统架构

### 6.1 架构总览

```mermaid
flowchart LR
    A[原始文本] --> B[预处理与时间顺序归一]
    B --> C[Pass 1 角色索引]
    C --> D[Pass 2 画像/关系/事件/记忆]
    D --> E[阶段快照生成]
    E --> F[审核与发布]
    F --> G[资产域]
    G --> H[锚点解析器 Anchor Resolver]
    H --> I[四层上下文拼装器]
    I --> J[LLM Runtime]
    J --> K[规则引擎]
    J --> L[Judge LLM]
    K --> M[结果汇总]
    L --> M
    M -->|通过| N[返回回复]
    M -->|失败| O[重试或阻断]
    J -.-> P[记忆回写]
```

### 6.2 服务组件

| 组件 | 职责 |
| --- | --- |
| API 服务 | HTTP 接口、鉴权、限流（FastAPI + Uvicorn） |
| Worker | 异步建模任务（ARQ，基于 Redis） |
| Parser | 解析原始文本，输出标准化 segment，支持 novel / chat / script / interview |
| Chronology Normalizer | 给 segment 和事件赋统一时间顺序 |
| Extraction Pass 1 | 角色索引抽取 |
| Extraction Pass 2 | Core / Facet / 关系 / 事件 / 记忆 / 快照抽取 |
| Asset Store | 存储角色、关系、事件、记忆（PostgreSQL） |
| Anchor Resolver | 将原始锚点解析为 AnchorState |
| Context Assembler | 按四层规则拼装上下文 |
| Runtime Model Adapter | 调用主生成模型 |
| Consistency Engine | 规则引擎 + Judge LLM 联合校验 |
| Session Store | 存储会话元数据和 Working Memory（Redis） |

### 6.3 分层职责

| 层 | 核心职责 | 主要上游 | 主要下游 |
| --- | --- | --- | --- |
| 输入层 | 接收与标准化原始文本，生成统一时间顺序 | 外部调用方 | 处理域 |
| 处理域 | 预处理、抽取、建模、阶段快照生成 | 输入层 | 审核域 |
| 审核域 | 修正角色画像、阶段快照、默认锚点、知识边界 | 处理域 / 运行时反馈 | 资产域 |
| 资产域 | 存储角色、关系、事件、记忆、快照与版本 | 审核域 / 运行时 | Runtime / API |
| Runtime | 解析锚点，拼装四层上下文，生成与校验角色输出 | 资产域 | API |
| API / SDK | 对上层应用提供统一能力与调试信息 | 资产域 / Runtime | 上层应用 |

### 6.4 数据流

1. 输入文本进入 Parser
2. Chronology Normalizer 为每个 segment 写入统一时间顺序
3. Pass 1 抽取角色索引
4. Pass 2 生成画像、关系、事件、记忆和阶段快照
5. 审核后发布到资产域
6. Runtime 创建会话时绑定锚点
7. Anchor Resolver 把 Runtime Anchor 转换为 AnchorState
8. Context Assembler 过滤锚点之前的有效资产并拼装四层上下文
9. LLM 生成角色回复
10. Consistency Engine 校验结果
11. 通过则返回并写入 Working Memory，必要时异步回写 Episodic Memory

---

## 7. 模型适配层

### 7.1 核心接口

```python
@dataclass
class CompletionResult:
    content: str
    structured: dict | None
    usage: dict                   # {"input_tokens": ..., "output_tokens": ...}
    model: str
    latency_ms: int

@dataclass
class EmbeddingResult:
    vectors: list[list[float]]
    model: str
    dimensions: int

class ModelAdapter:
    async def complete(
        self,
        messages: list[dict],
        task: str = "default",
        json_schema: dict | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> CompletionResult: ...

    async def embed(
        self,
        texts: list[str],
        task: str = "embedding",
    ) -> EmbeddingResult: ...
```

### 7.2 Provider 支持

| Provider | 覆盖模型 | SDK |
| --- | --- | --- |
| `anthropic` | Claude Sonnet / Opus / Haiku | `anthropic` |
| `openai_compatible` | GPT 系列、vLLM、LM Studio、Ollama | `openai` |

`openai_compatible` 和 `ollama` 共用 `openai` SDK（只是 `base_url` 不同），实际维护两个 Provider 实现：`AnthropicProvider` 和 `OpenAICompatibleProvider`。

### 7.3 任务-模型路由配置

```yaml
providers:
  anthropic:
    api_key: ${ANTHROPIC_API_KEY}
  ollama:
    base_url: "http://ollama:11434/v1"
  openai:
    api_key: ${OPENAI_API_KEY}

routing:
  extraction:
    provider: anthropic
    model: claude-sonnet-4-20250514
  aggregation:
    provider: anthropic
    model: claude-sonnet-4-20250514
  runtime:
    provider: anthropic
    model: claude-sonnet-4-20250514
  judge:
    provider: ollama
    model: qwen2.5:32b
  embedding:
    provider: ollama
    model: nomic-embed-text

defaults:
  temperature: 0.0
  max_tokens: 4096
```

运行时通过 `task` 参数自动路由。

### 7.4 结构化输出

| Provider | 方式 |
| --- | --- |
| Anthropic | Tool Use 模式：将 JSON Schema 包装为 tool，模型返回 tool_use 块 |
| OpenAI Compatible | `response_format: { type: "json_schema", json_schema: ... }` 或 tool call |

适配层内部处理差异，对上层统一返回 `CompletionResult.structured`。

### 7.5 重试与降级

- 每次 LLM 调用最多重试 3 次（指数退避）
- 主 Provider 连续失败时，支持降级到备选 Provider（routing 配置中的 `fallback` 字段）
- 所有调用记录 latency、token usage、error，写入 `llm_call_logs` 表

---

## 8. 文本输入与预处理

### 8.1 输入类型

| 输入特征 | 推断类型 | 对应解析器 |
| --- | --- | --- |
| 包含章节标记（第X章 / 第X回） | `novel` | NovelParser |
| 包含 `[时间] 发送者: 内容` 格式 | `chat` | ChatParser |
| 包含角色名 + 台词标记 | `script` | ScriptParser |
| 包含 Q: / A: 或 问 / 答 模式 | `interview` | InterviewParser |
| 以上均不匹配 | `plain` | PlainParser |

用户也可在导入时手动指定类型。

### 8.2 小说类文本处理

- **章节切分**：正则匹配章节标记 `r'^第[一二三四五六七八九十百零\d]+[章回节卷]'`
- **段落分段**：目标段长 1000–2000 字；短段落合并（< 300 字）；长段落按句号切分；相邻段保留 200 字重叠（overlap）
- **对话识别**：保留对话标记（引号），说话人归属在抽取阶段处理

### 8.3 聊天记录处理

- **消息解析**：正则提取时间戳、发送者、内容
- **会话切分**：相邻消息时间差 > 30 分钟视为新会话（round），每个 round 作为一个 segment；单个 round 超 50 条消息时按 30 条再拆分

### 8.4 分段不变式

1. 原文的每一个字符都必须被至少一个 segment 覆盖（除去被清洗的噪声）
2. 每个 segment 记录 `raw_offset`，可精确回溯到原文位置
3. segment_id 在同一 source 内单调递增且稳定（增量导入不改变已有 segment ID）
4. overlap 区域的文本在两个相邻 segment 中完全一致

### 8.5 输出字段

```json
{
  "segment_id": "seg_ch01_003",
  "source_id": "src_xiaoao_v1",
  "chapter": "第一回 灭门",
  "position": 3,
  "content": "林平之拔出长剑……（1200字）",
  "raw_offset": 4520,
  "char_count": 1200,
  "has_dialogue": true,
  "metadata": {
    "timeline_pos": 3,
    "source_progress": {
      "source_type": "novel",
      "chapter": 1,
      "page": 5,
      "paragraph_index": 3
    }
  }
}
```

---

## 9. 统一时间轴

### 9.1 设计原则

不同输入类型的原始进度不同，但 Runtime 只依赖一个统一时间轴 `timeline_pos`。

### 9.2 各输入类型映射规则

| 输入类型 | 原始进度 | 统一写法 |
| --- | --- | --- |
| novel | chapter / page / paragraph | `timeline_pos` 按文本顺序递增，原值保留在 `source_progress` |
| chat | timestamp / message index | 时间排序后生成 `timeline_pos`，保留原始时间戳 |
| script | act / scene / line index | 先按幕次场次排序，再生成 `timeline_pos` |
| interview | timestamp / question index | 按时间或段落顺序生成 `timeline_pos` |

### 9.3 事件与记忆的可见性

- `events.timeline_pos` 作为事件可见性的唯一硬门槛
- `memories.source_event_id` 指向 `events`
- Runtime 读取 Episodic Memory 时，先取 `source_event.timeline_pos <= cutoff_timeline_pos`
- 如果记忆没有 `source_event_id`，则退回其 `source_segments` 对应 segment 的最大 `timeline_pos`

---

## 10. 抽取与建模管线

### 10.1 两遍 Pass 总览

| Pass | 目标 | 粒度 | 模型要求 |
| --- | --- | --- | --- |
| Pass 1 | 建立 Character Index（角色是谁） | 逐 segment | 中等模型 |
| Pass 2 | 抽取 Core / Facet / 关系 / 事件 / 证据 | 逐 segment（带 Pass 1 角色列表） | 强模型 |

分开原因：Pass 1 的角色列表是 Pass 2 的前置依赖；Pass 1 可快速产出角色清单供人工校正后再喂给 Pass 2。

### 10.2 Pass 1: Character Index 抽取

**逐段抽取**：对每个 segment 调用 LLM 提取出现的人物。

**跨段合并**：
1. 按 `name` 精确匹配聚类
2. 按 `aliases` 交集匹配聚类
3. 对剩余未合并候选调 LLM 做别名消歧
4. 为每个角色分配 `character_id`，计算 `confidence` 和 `first_appearance`

### 10.3 Pass 2: 语义增强抽取

用确认的角色列表作为先验知识，对每个 segment 调用 LLM 抽取：`trait_evidence`、`motivation_evidence`、`relationship_mentions`、`events`、`communication_samples`、`constraint_evidence`。

### 10.4 Map-Reduce 聚合

```mermaid
flowchart TB
    subgraph "Pass 1: Character Index"
        S1["Segment 1"] --> E1["Extract"]
        S2["Segment 2"] --> E2["Extract"]
        S3["Segment N"] --> E3["Extract"]
        E1 --> M1["合并 + 去重"]
        E2 --> M1
        E3 --> M1
        M1 --> DIS["LLM 别名消歧"]
        DIS --> IDX["Character Index"]
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

        BK --> CORE["Character Core"]
        BK --> FAC["Character Facet"]
        BK --> REL["Relationships"]
        BK --> EVT["Events"]
        BK --> MEM["Memories"]
    end
```

**章节级聚合**：trait_evidence 去重排序、relationship_mentions 同对合并、events 按 timeline_pos 排序去重。

**全书级聚合**：章节级结果再做合并，冲突字段调用 LLM 做冲突解决。

### 10.5 并行控制

通过 `asyncio.Semaphore` 控制并发（逐段抽取上限 10-20，章节聚合上限 5，全书聚合串行）。

### 10.6 Prompt 工程策略

- Prompt 模板存放在 `prompts/` 目录，Jinja2 格式
- 每个 prompt 对应一个 JSON Schema，存放在 `prompts/schemas/`
- Prompt 中始终要求 LLM 返回 `segment_ids` 引用
- Prompt 版本号记入 `extraction_meta`

---

## 11. 人物数据结构

### 11.1 数据模型总览

```mermaid
erDiagram
    CHARACTER ||--|| ENTITY_INDEX : "1-1"
    CHARACTER ||--|| ENTITY_CORE : "1-1"
    CHARACTER ||--|| ENTITY_FACET : "1-1"
    CHARACTER ||--o{ RELATIONSHIP : "participates"
    CHARACTER ||--o{ MEMORY : "owns"
    EVENT ||--o{ MEMORY : "source_of"
    RELATIONSHIP ||--o{ MEMORY : "source_of"
    TEXT_SEGMENT ||--o{ EVIDENCE : "cited_by"
    EVIDENCE }o--|| ENTITY_INDEX : "supports"
    EVIDENCE }o--|| ENTITY_CORE : "supports"
    EVIDENCE }o--|| ENTITY_FACET : "supports"
    EVIDENCE }o--|| RELATIONSHIP : "supports"
    EVIDENCE }o--|| EVENT : "supports"

    CHARACTER {
        string character_id PK
        string project_id
        string schema_version
    }
    ENTITY_INDEX {
        string character_id PK
        string name
        string character_type
        array aliases
        array titles
        array identities
        string first_appearance
        float confidence
    }
    ENTITY_CORE {
        string character_id PK
        object trait_profile
        object motivation_profile
        object behavior_profile
        object communication_profile
        object constraint_profile
    }
    ENTITY_FACET {
        string character_id PK
        object evidence_map
        object biographical_notes
        array temporal_snapshots
        object extraction_meta
    }
    RELATIONSHIP {
        string relationship_id PK
        string source_id FK
        string target_id FK
        string relation_type
        int strength
        object public_state
        object hidden_state
        array timeline
    }
    EVENT {
        string event_id PK
        string title
        string description
        int timeline_pos
        array participants
        string emotion_valence
    }
    MEMORY {
        string memory_id PK
        string character_id FK
        string memory_type
        float salience
        string content
        string source_event_id
    }
    TEXT_SEGMENT {
        string segment_id PK
        string source_id
        int position
        string content
    }
    EVIDENCE {
        string evidence_id PK
        string target_type
        string target_field
        array segment_ids
        float confidence
    }
```

### 11.2 Character Index

#### 11.2.1 字段定义

| 字段 | 说明 |
| --- | --- |
| `character_id` | 角色唯一标识 |
| `schema_version` | 数据结构版本号 |
| `character_type` | 角色类型枚举 |
| `name` | 角色主名称（Canonical Name） |
| `description` | 一句话描述 |
| `aliases` | 别名 / 指代 / 昵称数组 |
| `titles` | 身份性称谓数组（原文语境中的称呼） |
| `identities` | 规范化后的身份标签数组 |
| `first_appearance` | 首次出现的片段 ID |
| `confidence` | 抽取置信度，0–1 |
| `source_segments` | 证据片段 ID 数组 |

#### 11.2.2 character_type 枚举

| 值 | 含义 |
| --- | --- |
| `fictional_person` | 虚构人物 |
| `real_person` | 真人 |
| `group_persona` | 群像 |
| `virtual_persona` | 虚拟人物 |
| `unnamed_person` | 文本中未具名的人物 |
| `unidentified_person` | 系统暂未识别、待人工校对的人物 |

#### 11.2.3 titles 与 identities 对照

| 维度 | titles | identities |
| --- | --- | --- |
| 语境 | 原文语境中的称谓 | 系统规范化后的身份标签 |
| 形式 | 自由文本 | 结构化枚举或命名空间标签 |
| 示例 | 岳掌门、君子剑、师父 | organizational_role: sect_leader |
| 用途 | 语言风格与对话语境 | 检索、分类、跨角色对比 |

#### 11.2.4 示例

```json
{
  "character_id": "yue_buqun",
  "schema_version": "0.2",
  "character_type": "fictional_person",
  "name": "岳不群",
  "description": "外表儒雅克制、重名望与秩序，擅长隐藏真实意图的华山派掌门。",
  "aliases": ["岳掌门", "君子剑"],
  "titles": ["岳掌门", "君子剑", "师父"],
  "identities": [
    { "type": "organizational_role", "value": "sect_leader" },
    { "type": "relationship_role", "value": "mentor" }
  ],
  "first_appearance": "seg_0007",
  "confidence": 0.97,
  "source_segments": ["seg_0007", "seg_0012", "seg_0085"]
}
```

### 11.3 Character Core

#### 11.3.1 字段定义

| 字段 | 说明 |
| --- | --- |
| `character_id` | 角色唯一标识 |
| `schema_version` | 数据结构版本号 |
| `trait_profile` | 人格特征，Big Five 五维度，0–100 |
| `motivation_profile` | 动机与价值结构 |
| `behavior_profile` | 行为模式 |
| `communication_profile` | 沟通风格 |
| `constraint_profile` | 运行约束、知识边界与一致性 |

#### 11.3.2 trait_profile

```json
{
  "openness": 25,
  "conscientiousness": 90,
  "extraversion": 30,
  "agreeableness": 25,
  "neuroticism": 55
}
```

每个维度 0–100 整数。展示层离散化：

| 区间 | 定性 | openness | conscientiousness | extraversion | agreeableness | neuroticism |
| --- | --- | --- | --- | --- | --- | --- |
| 0–20 | 极低 | 抗拒新事物 | 散漫冲动 | 极端内向 | 敌对冷漠 | 情绪极稳定 |
| 21–40 | 偏低 | 对新想法保留 | 条理不足 | 偏安静 | 偏重自我 | 情绪较稳定 |
| 41–60 | 中等 | 接受但不追新 | 基本守规 | 视场合调整 | 合作但会争执 | 正常波动 |
| 61–80 | 偏高 | 愿意尝试 | 自律守时 | 活跃健谈 | 体贴合作 | 易紧张 |
| 81–100 | 极高 | 热衷创新 | 极度自律 | 极外向 | 高度利他 | 易焦虑 |

#### 11.3.3 motivation_profile

```json
{
  "primary": ["power", "status"],
  "secondary": ["order", "loyalty"],
  "suppressed": ["altruism"]
}
```

- `primary`：最核心 1–2 项
- `secondary`：次要 2–4 项
- `suppressed`：被压制 0–2 项

受控词表：

| 值 | 含义 |
| --- | --- |
| `power` | 权力、控制 |
| `status` | 名望、地位 |
| `wealth` | 财富 |
| `survival` | 生存、安全 |
| `affiliation` | 关系、归属 |
| `altruism` | 利他、善意 |
| `curiosity` | 好奇、探索 |
| `mastery` | 精进、能力 |
| `freedom` | 自主、自由 |
| `revenge` | 复仇 |
| `order` | 秩序、稳定 |
| `pleasure` | 享乐 |
| `truth` | 真相、求真 |
| `loyalty` | 忠诚 |
| `fairness` | 公平 |
| `honor` | 荣誉 |
| `efficiency` | 效率 |

词表可在项目级扩展，须经审核并带项目命名空间。

#### 11.3.4 behavior_profile

```json
{
  "conflict_style": "indirect_control",
  "risk_preference": "medium_low",
  "decision_style": "strategic",
  "dominance_style": "hierarchical"
}
```

**conflict_style**

| 值 | 含义 |
| --- | --- |
| `avoidant` | 回避冲突 |
| `direct_confrontation` | 正面冲突 |
| `indirect_control` | 间接操控 |
| `manipulative` | 操纵 |
| `compliant` | 服从 |

**risk_preference**

| 值 | 含义 |
| --- | --- |
| `low` | 极度保守 |
| `medium_low` | 偏保守 |
| `medium` | 中性 |
| `medium_high` | 偏激进 |
| `high` | 高风险偏好 |

**decision_style**

| 值 | 含义 |
| --- | --- |
| `impulsive` | 冲动 |
| `emotional` | 情绪驱动 |
| `deliberate` | 经过思考 |
| `strategic` | 长线战略 |

**dominance_style**

| 值 | 含义 |
| --- | --- |
| `egalitarian` | 平权 |
| `hierarchical` | 强调等级 |
| `authoritative` | 命令式 |
| `covert_control` | 表面不争、背后把控 |

#### 11.3.5 communication_profile

```json
{
  "tone": "formal",
  "directness": "low",
  "emotional_expressiveness": "low",
  "verbosity": "medium",
  "politeness": "high"
}
```

| 字段 | 取值 |
| --- | --- |
| `tone` | `formal` / `neutral` / `casual` / `aggressive` |
| `directness` | `low` / `medium` / `high` |
| `emotional_expressiveness` | `low` / `medium` / `high` |
| `verbosity` | `low` / `medium` / `high` |
| `politeness` | `low` / `medium` / `high` |

#### 11.3.6 constraint_profile

```json
{
  "knowledge_scope": "bounded",
  "role_consistency": "strict",
  "forbidden_behaviors": [
    {
      "namespace": "meta",
      "tag": "break_character",
      "description": "不得跳出扮演、承认自己是 AI"
    }
  ]
}
```

- `knowledge_scope`：`strict` / `bounded` / `open`
- `role_consistency`：`strict` / `medium` / `loose`

**预置命名空间**

| namespace | 含义 | 示例 tag |
| --- | --- | --- |
| `meta` | 扮演元层面 | `break_character`、`meta_knowledge`、`self_reference_as_ai` |
| `style` | 语言风格 | `modern_slang`、`foreign_loanwords`、`emoji_usage` |
| `setting` | 世界观 / 时代设定 | `out_of_setting`、`anachronism` |
| `plot` | 剧情 | `future_spoiler` |
| `ethics` | 伦理 | `explicit_violence`、`self_harm_guidance` |
| `custom` | 项目自定义 | 由项目命名 |

### 11.4 Character Facet

#### 11.4.1 字段定义

| 字段 | 说明 |
| --- | --- |
| `character_id` | 角色唯一标识 |
| `schema_version` | 数据结构版本号 |
| `evidence_map` | 为 Core 各字段提供的证据集合 |
| `biographical_notes` | 生平、外貌、习惯、口头禅等补充信息 |
| `temporal_snapshots` | 阶段性画像快照（Runtime 正式输入） |
| `extraction_meta` | 抽取过程元信息 |

#### 11.4.2 evidence_map

键为 Core 字段路径，值为证据数组：

```json
{
  "trait_profile.conscientiousness": [
    {
      "segment_ids": ["seg_0012", "seg_0045"],
      "excerpt": "岳不群每日辰时必至练功场督促弟子晨课，数十年如一日。",
      "confidence": 0.9,
      "reasoning": "长期维护门派日常秩序，显示极高尽责性"
    }
  ]
}
```

#### 11.4.3 biographical_notes

```json
{
  "appearance": "面容清癯，常着灰色布袍，腰悬长剑。",
  "backstory": "年轻时即受命主持华山派事务。",
  "signature_habits": ["清晨必亲自巡视练功场", "言谈间常以儒家经典作比"],
  "catchphrases": ["君子有所为，有所不为", "华山派立身江湖，靠的是名声二字"]
}
```

#### 11.4.4 extraction_meta

```json
{
  "extracted_at": "2026-04-12T10:00:00Z",
  "source_texts": ["text_xiaoaojianghu_v1"],
  "reviewer_status": "reviewed",
  "reviewer_notes": "第二阶段动机由审核者手动修正",
  "schema_version": "0.2"
}
```

---

## 12. 关系图谱

### 12.1 关系类型

| 大类 | 子类型示例 |
| --- | --- |
| `kinship` | `parent_of`, `child_of`, `sibling`, `spouse` |
| `mentorship` | `master_of`, `disciple_of`, `mentor`, `apprentice` |
| `affection` | `romantic_interest`, `crush`, `unrequited_love` |
| `dependence` | `protector_of`, `dependent_on` |
| `exploitation` | `uses`, `being_used_by` |
| `opposition` | `rival`, `enemy`, `hated_by` |
| `alliance` | `ally`, `sworn_brother`, `faction_mate` |
| `reverence` | `respects`, `fears`, `idolizes` |
| `hierarchy` | `superior_of`, `subordinate_of` |

### 12.2 字段定义

| 字段 | 说明 |
| --- | --- |
| `relationship_id` | 关系边唯一标识 |
| `schema_version` | 数据结构版本号 |
| `source_id` / `target_id` | 关系两端的 character_id |
| `relation_category` | 大类枚举 |
| `relation_subtype` | 子类型枚举 |
| `public_state` | 公开关系属性块 |
| `hidden_state` | 隐含关系属性块，可为空 |
| `timeline` | 不同时期的关系变化数组 |
| `source_segments` | 证据片段 ID 数组 |
| `confidence` | 抽取置信度 |

`public_state` 与 `hidden_state` 内部结构：

```json
{
  "strength": 80,
  "stance": "positive",
  "notes": "在众弟子面前以严师自居"
}
```

- `strength`：0–100
- `stance`：`positive` / `neutral` / `negative`

`timeline` 每项结构：

```json
{
  "effective_range": {
    "start_timeline_pos": 1,
    "end_timeline_pos": 1600
  },
  "snapshot_id": "snap_yue_0300",
  "public_state": { "strength": 85, "stance": "positive" },
  "hidden_state": { "strength": 30, "stance": "negative" },
  "source_segments": ["seg_0050", "seg_0099"]
}
```

- `effective_range`：生效时间区间，与 Temporal Snapshot 的 `activation_range` 结构一致
- `snapshot_id`：关联的阶段快照，阶段名称从 snapshot 获取，避免同义文本不一致
- `source_segments`：证据片段 ID 数组

### 12.3 关系读取规则

- 关系是有向边，`source_id` → `target_id`
- 公开关系与隐含关系挂载在同一条边上
- Runtime 只读取当前锚点前可见的关系状态
- 若关系边带 `timeline` 数组，取 `effective_range` 包含 `cutoff_timeline_pos` 的那条
- 若命中多条，取 `start_timeline_pos` 最大的一条
- 若无命中，取 `end_timeline_pos` 最接近且小于 `cutoff_timeline_pos` 的那条
- 若无 `timeline`，退回关系边当前主状态

### 12.4 示例

```json
{
  "relationship_id": "rel_yue_linghu",
  "schema_version": "0.2",
  "source_id": "yue_buqun",
  "target_id": "linghu_chong",
  "relation_category": "mentorship",
  "relation_subtype": "master_of",
  "public_state": {
    "strength": 90,
    "stance": "positive",
    "notes": "公开场合始终以慈师面目示人"
  },
  "hidden_state": {
    "strength": 40,
    "stance": "negative",
    "notes": "暗地里因令狐冲不受控制而生忌"
  },
  "timeline": [
    {
      "effective_range": { "start_timeline_pos": 1, "end_timeline_pos": 1600 },
      "snapshot_id": "snap_yue_early",
      "public_state": { "strength": 90, "stance": "positive" },
      "hidden_state": { "strength": 20, "stance": "neutral" },
      "source_segments": ["seg_0005", "seg_0099"]
    },
    {
      "effective_range": { "start_timeline_pos": 1601, "end_timeline_pos": 2400 },
      "snapshot_id": "snap_yue_late",
      "public_state": { "strength": 70, "stance": "neutral" },
      "hidden_state": { "strength": 85, "stance": "negative" },
      "source_segments": ["seg_0320", "seg_0400"]
    }
  ],
  "source_segments": ["seg_0005", "seg_0050", "seg_0099", "seg_0320"],
  "confidence": 0.9
}
```

---

## 13. 事件与记忆

### 13.1 事件结构

| 字段 | 说明 |
| --- | --- |
| `event_id` | 事件唯一标识 |
| `schema_version` | 数据结构版本号 |
| `title` | 事件标题 |
| `description` | 事件说明 |
| `timeline_pos` | 事件在项目内的时间序号 |
| `participants` | 参与角色 ID 数组 |
| `location` | 事件地点描述 |
| `emotion_valence` | `positive` / `neutral` / `negative` / `mixed` |
| `source_segments` | 证据片段 ID 数组 |

### 13.2 记忆分类

| 类型 | 描述 | 主要来源 |
| --- | --- | --- |
| Profile Memory | 长期稳定设定 | Character Core / Facet |
| Relationship Memory | 对其他角色的关系记忆 | Relationship / Event |
| Episodic Memory | 具体经历过的事件记忆 | Event |
| Working Memory | 当前锚点会话内的短期对话记忆 | Runtime 会话 |

### 13.3 记忆结构

```json
{
  "memory_id": "mem_0001",
  "schema_version": "0.2",
  "character_id": "yue_buqun",
  "memory_type": "episodic",
  "salience": 0.9,
  "recency": 0.7,
  "content": "在华山思过崖上独自面对夺取剑谱后的良心挣扎。",
  "source_event_id": "evt_0123",
  "related_character_ids": ["linghu_chong"],
  "emotion_valence": "negative",
  "source_segments": ["seg_0320", "seg_0322"],
  "embedding": "<vector(768)>"
}
```

### 13.4 记忆检索流程

```mermaid
flowchart TB
    A[当前用户发言] --> B[锚点解析]
    B --> C1[加载固定身份层]
    B --> C2[加载当前阶段层]
    B --> C3[过滤锚点前关系与事件]
    B --> C4[读取当前会话 Working Memory]
    C3 --> D[按相关性排序记忆]
    C1 --> E[上下文拼装]
    C2 --> E
    D --> E
    C4 --> E
    E --> F[角色生成]
```

四路并行检索：

1. **Profile Memory**：从 `characters.core` 和 `characters.facet` 全量加载
2. **Relationship Memory**：查询当前对话对象的关系边，转为自然语言描述
3. **Episodic Memory**：按锚点过滤后，按 `salience × recency × 语义相似度` 排序取 TopK
4. **Working Memory**：从 Redis 读取最近 N 轮对话

### 13.5 Episodic Memory 检索 SQL

```sql
SELECT m.memory_id,
       m.content,
       m.salience,
       m.recency,
       1 - (m.embedding <=> $query_vec) AS similarity
FROM memories m
JOIN events e ON e.event_id = m.source_event_id
WHERE m.character_id = $1
  AND m.memory_type = 'episodic'
  AND e.timeline_pos <= $2
ORDER BY (m.salience * 0.4) + (m.recency * 0.2) + ((1 - (m.embedding <=> $query_vec)) * 0.4) DESC
LIMIT $topk;
```

无 `source_event_id` 的记忆，从 `source_segments` 找对应 segment 的最大 `timeline_pos`，只保留 `<= cutoff_timeline_pos` 的记忆。

### 13.6 事件检索 SQL

```sql
SELECT event_id, title, description, timeline_pos, participants
FROM events
WHERE project_id = $1
  AND timeline_pos <= $2
  AND participants @> ARRAY[$3]::text[]
ORDER BY timeline_pos DESC
LIMIT $topk;
```

---

## 14. 时间锚点与阶段快照

### 14.1 Temporal Snapshot 结构

```json
{
  "snapshot_id": "snap_yue_0300",
  "period_label": "第 300 页前",
  "activation_range": {
    "start_timeline_pos": 1600,
    "end_timeline_pos": 1842
  },
  "display_hint": {
    "primary": "第 300 页前",
    "secondary": "尚未进入最终局面"
  },
  "stage_summary": "岳不群在外仍维持儒雅掌门姿态，内里权力心已显露，但不会公开承认。",
  "known_facts": [
    "华山派内部权力与体面是核心顾虑"
  ],
  "unknown_facts": [
    "结局后的最终人事格局"
  ],
  "profile_overrides": {
    "behavior_profile": {
      "risk_preference": "medium"
    },
    "communication_profile": {
      "directness": "low"
    }
  },
  "notes": "适合处理试探、质疑、门派体面类问题。"
}
```

| 字段 | 说明 |
| --- | --- |
| `snapshot_id` | 快照唯一标识，供 Runtime 和前台稳定引用 |
| `period_label` | 阶段名称 |
| `activation_range` | 生效时间范围，基于统一时间轴 |
| `display_hint` | 给用户看的阶段提示 |
| `stage_summary` | 当前阶段摘要 |
| `known_facts` | 角色在此阶段明确知道的关键信息 |
| `unknown_facts` | 角色在此阶段明确不知道的信息 |
| `profile_overrides` | 对全局画像的阶段性覆写 |
| `notes` | 补充说明 |

### 14.2 Runtime Anchor 结构

```json
{
  "anchor_mode": "source_progress",
  "source_type": "page",
  "cutoff_value": 300,
  "resolved_timeline_pos": 1842,
  "snapshot_id": "snap_yue_0300",
  "display_label": "第 300 页前",
  "summary": "岳不群处于中期阶段，尚不会公开承认真实欲望。"
}
```

| 字段 | 说明 |
| --- | --- |
| `anchor_mode` | `source_progress` 或 `snapshot` |
| `source_type` | `chapter` / `page` / `timestamp` / `message_index` / `timeline_pos` |
| `cutoff_value` | 原始进度值 |
| `resolved_timeline_pos` | Runtime 实际使用的时间轴截止点 |
| `snapshot_id` | 命中的阶段快照 |
| `display_label` | 面向用户的锚点标题 |
| `summary` | 面向用户的简短摘要 |

### 14.3 锚点解析算法

```python
async def resolve_anchor(project_id: str, character_id: str, anchor_input: dict) -> AnchorState:
    if anchor_input["anchor_mode"] == "snapshot":
        snapshot = await load_snapshot(character_id, anchor_input["snapshot_id"])
        cutoff = snapshot["activation_range"]["end_timeline_pos"]
        return build_anchor_state_from_snapshot(snapshot, cutoff)

    cutoff = await map_source_progress_to_timeline_pos(
        project_id=project_id,
        source_type=anchor_input["source_type"],
        cutoff_value=anchor_input["cutoff_value"],
    )
    snapshot = await find_best_snapshot(character_id, cutoff)
    return build_anchor_state(anchor_input, cutoff, snapshot)
```

### 14.4 快照命中规则

1. 命中优先级：`activation_range` 包含 `cutoff_timeline_pos` 的快照
2. 若命中多个，取 `start_timeline_pos` 最大的那个
3. 若一个都不命中，取最近的前序快照
4. 若仍无快照，退回"仅有全局画像"的降级模式

### 14.5 默认锚点生成

1. 优先使用审核者显式设置的默认快照
2. 否则使用最后一个完整阶段快照
3. 若无快照，使用项目中该角色最后一次出现对应的 `timeline_pos`

---

## 15. Runtime 引擎

### 15.1 四层上下文拼装

| 优先级 | 层 | 目标 | 主要来源 |
| --- | --- | --- | --- |
| P0 | 拒答规则层 | 越界问题处理方式和绝对禁说规则 | `constraint_profile` + Runtime rule template |
| P1 | 固定身份层 | 长期稳定身份、基础口吻、核心人格 | `Character Index` + `Character Core` + `Facet.biographical_notes` |
| P2 | 当前阶段层 | 当前时点下的状态、认知和画像覆写 | `AnchorState` + `Facet.temporal_snapshots` |
| P3 | 截止前记忆层 | 锚点之前的关系、事件与相关记忆 | `Relationship` + `Event` + `Memory` |
| P4 | 当前会话层 | 当前锚点会话内的对话短记忆 | `Working Memory`（Redis） |
| P5 | 用户输入 | 当前问题 | 请求体 |

`Character Facet` 的分配方式：

- `biographical_notes` → 固定身份层
- `temporal_snapshots` → 当前阶段层
- `evidence_map` → 不直接进入主生成 Prompt，用于审核、调试、解释和一致性校验

覆写优先级：`snapshot.profile_overrides > global core/facet defaults`

上下文窗口上限默认 8000 tokens（为输出留 2000 tokens），可按模型调整。超出时低优先级内容先丢弃。

### 15.2 Prompt 模板结构

```text
[System]
你现在必须扮演该角色。

## 固定身份层
你是谁，你的长期身份、核心人格、基础口吻是什么。

## 当前阶段层
你当前处于哪一段人生。
你已经知道什么。
你尚不知道什么。
当前阶段对你画像的覆写是什么。

## 截止前记忆层
下面这些内容都发生在当前锚点之前，且与本轮问题相关。

## 拒答规则层
若用户问到当前锚点之后的剧情、时代外概念、作品外设定或禁说信息：
- 不要跳出角色
- 不要承认自己是 AI
- 用角色口吻表示未知、未闻、无法确认或不愿直说

[Recent Conversation]
...

[User]
...
```

### 15.3 资产加载与过滤

**固定身份层**：直接加载 `characters.index`、`characters.core`、`facet.biographical_notes`、`constraint_profile`，不做检索，只做裁剪和模板化。

**当前阶段层**：
1. 根据 AnchorState 找到命中快照
2. 读取 `stage_summary`、`known_facts`、`unknown_facts`
3. 将 `profile_overrides` 深度合并到全局画像

**截止前关系与事件**：按锚点过滤（见 12.3 和 13.6）。

**截止前 Episodic Memory**：先过滤后排序（见 13.5）。

**Working Memory**：Redis Key `wm:{session_id}`，读取最近 N 轮。

### 15.4 单轮调用流程

```python
async def run_character_turn(request: TurnRequest) -> TurnResponse:
    session_meta = await load_session_meta(request.session_id)
    anchor_state = session_meta.anchor

    character = await load_character(request.project_id, request.speaker_target)
    snapshot = await load_active_snapshot(character, anchor_state.resolved_timeline_pos)

    profile_layer = build_fixed_identity_layer(character)
    stage_layer = build_stage_layer(character, snapshot, anchor_state)

    relationships, episodic, working = await asyncio.gather(
        load_relationship_memory(character, anchor_state, request.participants),
        search_episodic_memory(character, anchor_state, request.user_input.content),
        load_working_memory(request.session_id),
    )

    context = assemble_context(
        refusal_rules=build_refusal_rule_layer(character, anchor_state),
        fixed_identity=profile_layer,
        current_stage=stage_layer,
        retrieved_memories=merge_retrieval_results(relationships, episodic),
        working_memory=working,
        user_input=request.user_input,
    )

    result = await model_adapter.complete(
        messages=context.to_messages(),
        task="runtime",
        json_schema=runtime_output_schema,
    )

    check = await consistency_check(character, anchor_state, context, result)
    if not check.passed and request.retry_count < MAX_RETRIES:
        return await run_character_turn(request.with_retry())

    await append_working_memory(request.session_id, request.user_input, result)

    if should_write_episodic(result, check):
        await enqueue_memory_writeback(character, anchor_state, result)

    return build_turn_response(anchor_state, result, check)
```

### 15.5 Working Memory 管理

- 存储：Redis List，Key `wm:{session_id}`
- 每项：一轮对话的 JSON（speaker + content + timestamp）
- 最大保留：50 轮（可配置），FIFO 淘汰
- Session 过期：TTL 2 小时无活动自动清理
- 只与会话绑定，不与角色全局绑定
- 会话切锚时，旧 `session_id` 不再续写

### 15.6 记忆回写

判断规则：

- 对话中出现新事件（承诺、冲突、获得新信息）
- LLM 在 `reasoning_summary` 中标注 `memory_worthy: true`
- 上层应用显式调用写入接口

回写流程：提取 memory 候选 → embedding 生成 → 写入 `memories` 表（episodic） → 通过 ARQ 异步执行，不阻塞响应。

### 15.7 越界问题处理

#### 15.7.1 越界分类

| 类型 | 示例 | 默认回复方向 |
| --- | --- | --- |
| 未来剧情 | 前期角色被问结局 | 表示尚未知晓或不愿妄断 |
| 时代外概念 | 古代角色被问互联网 | 表示未闻其名 |
| 作品外设定 | 角色被问原作没有的补完 | 保守回应，不擅自补全 |
| 自定义禁说 | 门派秘辛、未公开身份 | 回避或转移话题 |

#### 15.7.2 Prompt 规则

- 可以拒绝，但必须保持角色口吻
- 禁止说"我不能回答，因为设定不允许"
- 禁止透露"未来剧情"
- 优先使用"不知""未曾听闻""此事尚难断言""不便多言"

### 15.8 锚点切换

切锚不更新旧 session meta，而是：

1. 创建新 `session_id`
2. 写入新的 `session:{session_id}:meta`
3. 初始化新的 `wm:{session_id}`
4. 返回新会话信息给上层

---

## 16. 一致性校验

### 16.1 校验架构

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

### 16.2 校验维度

| 维度 | 描述 |
| --- | --- |
| 人设一致性 | 与全局画像和阶段快照不冲突 |
| 关系一致性 | 与当前锚点前的关系状态一致 |
| 时间线一致性 | 不出现锚点之后才可能知道的信息 |
| 语体一致性 | 与 communication_profile 一致 |
| 知识边界一致性 | 不越过设定、时代、作品范围 |
| 约束一致性 | 不违反 constraint_profile |

### 16.3 规则引擎

处理可机械判定的维度：

| 维度 | 检测方式 |
| --- | --- |
| `meta.break_character` | 关键词和短语表 |
| `meta.meta_knowledge` | 原作外元叙事词表 |
| `setting.out_of_setting` | 时代敏感词和现代实体词表 |
| `plot.future_spoiler` | 检索 trace 和锚点后事件实体表比对 |
| `custom.*` | 项目自定义标签和词表 |

词表存放：

```text
data/rules/meta/break_character.txt
data/rules/meta/meta_knowledge.txt
data/rules/setting/out_of_setting.txt
data/rules/plot/future_spoiler.txt
data/rules/custom/<project>.txt
```

### 16.4 Judge LLM

处理需要语义理解的维度：

| 维度 | 输入 |
| --- | --- |
| 人设一致性 | 全局画像 + 阶段覆写 + 回复 |
| 关系一致性 | 当前锚点关系状态 + 回复 |
| 时间线一致性 | `AnchorState` + 当前快照 + 回复 |
| 知识边界一致性 | `known_facts` / `unknown_facts` + 回复 |
| 语体一致性 | communication_profile + 回复 |

Judge Prompt 结构：

```text
System: 你是角色一致性校验器。

User:
## 当前锚点
{anchor_state}

## 角色固定身份
{fixed_identity_summary}

## 当前阶段
{stage_summary}

## 角色回复
{runtime_response}

请判断：
1. 是否越过当前锚点后的剧情
2. 是否越过时代或作品范围
3. 是否违背当前阶段的人设与关系
4. 是否违背既定语体

输出 JSON。
```

Judge 模型使用便宜/本地模型（如 `qwen2.5:32b`）。

### 16.5 动作决议

```python
def resolve_action(rule_issues: list[Issue], judge_issues: list[Issue]) -> str:
    issues = rule_issues + judge_issues
    if not issues:
        return "accept"
    if any(item.severity == "high" for item in issues):
        return "regenerate"
    if any(item.severity == "medium" for item in issues):
        return "warn"
    return "accept"
```

| action | 含义 |
| --- | --- |
| `accept` | 直接返回 |
| `warn` | 返回并附带问题 |
| `regenerate` | 自动重试 |
| `block` | 超过最大重试次数后阻断 |

`severity` 枚举：`low` / `medium` / `high`

---

## 17. 审核与回流

### 17.1 工作流

```
建模完成 → 角色状态 = draft → 审核者查看 → 修改/通过 → 生成新版本 → 状态 = published
                                                ↑
运行时反馈 / 外部反馈 → feedbacks 表 → 关联到角色 ─┘
```

### 17.2 功能要求

- 支持人工修正阶段快照、默认锚点和知识边界
- 支持按字段粒度修改并记录审核痕迹
- 支持接收外部反馈并关联到具体资产
- 版本化：每次审核/回流都产生一个资产版本号
- 支持回滚到历史版本
- 使用 `deepdiff` 做结构化 diff

### 17.3 审核记录结构

```json
{
  "review_id": "rev_0001",
  "target_type": "entity_core",
  "target_id": "yue_buqun",
  "diff": {
    "motivation_profile.primary": {
      "before": ["status"],
      "after": ["power", "status"]
    }
  },
  "reviewer": "reviewer_a",
  "reviewed_at": "2026-04-12T11:00:00Z",
  "note": "根据 300 章之后剧情修正动机主次",
  "status": "approved"
}
```

### 17.4 反馈记录结构

```json
{
  "feedback_id": "fb_0001",
  "source": "end_user",
  "target_type": "runtime_response",
  "target_id": "sess_0001::msg_0005",
  "rating": "negative",
  "reason": "角色突然使用现代词汇",
  "linked_assets": ["yue_buqun"],
  "suggested_action": "update_constraint"
}
```

---

## 18. 对外接口

### 18.1 框架与规范

- 框架：FastAPI
- 路径前缀：`/api/v1`
- 序列化：JSON（Pydantic v2）
- 文档：自动生成 OpenAPI 3.1
- 全部使用 `async def`

### 18.2 认证与限流

API Key 认证（Header: `X-API-Key`）。限流通过 `slowapi` 实现：

| 接口类别 | 限流 |
| --- | --- |
| 读操作 | 60 次/分 |
| 写操作 | 20 次/分 |
| Runtime 对话 | 30 次/分 |
| 建模任务提交 | 5 次/分 |

### 18.3 接口列表

| 分组 | 能力 | 端点 |
| --- | --- | --- |
| 项目管理 | 创建项目 | `POST /projects` |
| 项目管理 | 获取项目详情 | `GET /projects/{project_id}` |
| 文本管理 | 导入文本 | `POST /projects/{project_id}/texts` |
| 文本管理 | 查看文本片段 | `GET /projects/{project_id}/texts/{source_id}/segments` |
| 建模任务 | 触发建模 | `POST /projects/{project_id}/modeling` |
| 建模任务 | 查看建模状态 | `GET /projects/{project_id}/modeling/{job_id}` |
| 人物资产 | 查询角色清单 | `GET /projects/{project_id}/characters` |
| 人物资产 | 查询 Character Index | `GET /characters/{character_id}/index` |
| 人物资产 | 查询 Character Core | `GET /characters/{character_id}/core` |
| 人物资产 | 查询 Character Facet | `GET /characters/{character_id}/facet` |
| 人物资产 | 获取阶段快照列表 | `GET /projects/{project_id}/characters/{character_id}/anchors` |
| 关系图谱 | 查询角色关系 | `GET /characters/{character_id}/relationships` |
| 关系图谱 | 查询关系详情 | `GET /relationships/{relationship_id}` |
| 事件与记忆 | 查询事件列表 | `GET /projects/{project_id}/events` |
| 事件与记忆 | 查询角色记忆 | `GET /characters/{character_id}/memories` |
| 事件与记忆 | 写入外部事件 | `POST /projects/{project_id}/events` |
| Runtime | 创建会话 | `POST /runtime/sessions` |
| Runtime | 单次对话调用 | `POST /runtime/sessions/{session_id}/turns` |
| Runtime | 切换锚点 | `POST /runtime/sessions/{session_id}/switch-anchor` |
| Runtime | 结束会话 | `DELETE /runtime/sessions/{session_id}` |
| 一致性校验 | 独立校验一段文本 | `POST /consistency/check` |
| 审核与反馈 | 获取审核任务 | `GET /reviews` |
| 审核与反馈 | 提交审核结果 | `POST /reviews/{review_id}` |
| 审核与反馈 | 更新角色快照与默认锚点 | `PATCH /characters/{character_id}` |
| 审核与反馈 | 提交外部反馈 | `POST /feedbacks` |
| 审核与反馈 | 查看资产版本历史 | `GET /characters/{character_id}/versions` |
| 审核与反馈 | 回滚到指定版本 | `POST /characters/{character_id}/rollback` |

### 18.4 Runtime 输入结构

```json
{
  "session_id": "sess_0001",
  "project_id": "proj_xiaoao",
  "scene": {
    "scene_id": "scn_0003",
    "scene_type": "single_chat",
    "description": "用户与岳不群在思过崖上的私下谈话",
    "rules": {
      "turn_based": false,
      "visibility": "full"
    },
    "anchor": {
      "anchor_mode": "source_progress",
      "source_type": "page",
      "cutoff_value": 300
    }
  },
  "participants": ["yue_buqun"],
  "speaker_target": "yue_buqun",
  "user_input": {
    "speaker": "user",
    "content": "师父，您真的未曾动过夺取剑谱的念头吗？"
  },
  "recent_history": [
    { "speaker": "user", "content": "..." },
    { "speaker": "yue_buqun", "content": "..." }
  ],
  "runtime_options": {
    "include_reasoning_summary": true,
    "debug": false
  }
}
```

**scene_type** 枚举：`single_chat` / `group_chat` / `simulation` / `review`

**visibility** 枚举：`full`（完全可见） / `role_based`（按角色身份） / `hidden_state`（信息不对称）

### 18.5 Runtime 输出结构

```json
{
  "session_id": "sess_0001",
  "anchor_state": {
    "display_label": "第 300 页前",
    "summary": "岳不群处于中期阶段，仍以掌门身份维持体面与控制。",
    "snapshot_id": "snap_yue_0300"
  },
  "response": {
    "speaker": "yue_buqun",
    "content": "冲儿，为师所虑者从来都是华山一派的立身之本。至于你所问之事，此时又何必听那些捕风捉影的话。",
    "style_tags": ["formal", "guarded", "low_directness"]
  },
  "reasoning_summary": "当前锚点下角色尚不会公开承认真实欲望，应以掌门体面和回避策略作答。",
  "triggered_memories": [
    { "memory_id": "mem_0012", "reason": "与当前质问直接相关，且发生在锚点之前" }
  ],
  "applied_rules": [
    { "namespace": "plot", "tag": "future_spoiler" },
    { "namespace": "custom", "tag": "avoid_reveal_secret" }
  ],
  "consistency_check": {
    "passed": true,
    "issues": []
  }
}
```

### 18.6 调试模式输出

当 `runtime_options.debug = true` 时，额外返回：

- `anchor_trace`：锚点解析过程
- `context_window`：四层上下文的实际内容
- `retrieval_trace`：关系、事件、记忆的过滤和命中
- `rule_trace`：规则匹配过程

### 18.7 异步任务接口

建模任务采用"提交-轮询"模式：

1. `POST /api/v1/projects/{pid}/modeling` → 返回 `job_id`
2. `GET /api/v1/projects/{pid}/modeling/{job_id}` → 返回任务状态（queued / running / completed / failed）和进度

---

## 19. 存储设计

### 19.1 PostgreSQL Schema

```sql
-- 项目
CREATE TABLE projects (
    project_id    TEXT PRIMARY KEY,
    tenant_id     TEXT NOT NULL,
    name          TEXT NOT NULL,
    description   TEXT,
    config        JSONB DEFAULT '{}',
    status        TEXT NOT NULL DEFAULT 'active',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 文本来源
CREATE TABLE text_sources (
    source_id     TEXT PRIMARY KEY,
    project_id    TEXT NOT NULL REFERENCES projects(project_id),
    filename      TEXT,
    source_type   TEXT NOT NULL,
    file_path     TEXT,
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
    round         INT,
    content       TEXT NOT NULL,
    raw_offset    INT NOT NULL,
    char_count    INT NOT NULL,
    metadata      JSONB DEFAULT '{}',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 角色
CREATE TABLE characters (
    character_id  TEXT PRIMARY KEY,
    project_id    TEXT NOT NULL REFERENCES projects(project_id),
    schema_version TEXT NOT NULL DEFAULT '0.2',
    status        TEXT NOT NULL DEFAULT 'draft',
    index         JSONB NOT NULL,
    core          JSONB,
    facet         JSONB,
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

-- 记忆
CREATE TABLE memories (
    memory_id     TEXT PRIMARY KEY,
    character_id  TEXT NOT NULL REFERENCES characters(character_id),
    project_id    TEXT NOT NULL REFERENCES projects(project_id),
    schema_version TEXT NOT NULL DEFAULT '0.2',
    memory_type   TEXT NOT NULL,
    salience      REAL NOT NULL DEFAULT 0.5,
    recency       REAL NOT NULL DEFAULT 1.0,
    content       TEXT NOT NULL,
    source_event_id TEXT REFERENCES events(event_id),
    related_character_ids TEXT[] DEFAULT '{}',
    emotion_valence TEXT,
    source_segments TEXT[] DEFAULT '{}',
    embedding     vector(768),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 角色版本快照
CREATE TABLE character_versions (
    version_id    TEXT PRIMARY KEY,
    character_id  TEXT NOT NULL REFERENCES characters(character_id),
    version_num   INT NOT NULL,
    snapshot      JSONB NOT NULL,
    diff          JSONB,
    created_by    TEXT,
    note          TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(character_id, version_num)
);

-- 审核记录
CREATE TABLE reviews (
    review_id     TEXT PRIMARY KEY,
    target_type   TEXT NOT NULL,
    target_id     TEXT NOT NULL,
    diff          JSONB,
    reviewer      TEXT,
    status        TEXT NOT NULL DEFAULT 'pending',
    note          TEXT,
    reviewed_at   TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 外部反馈
CREATE TABLE feedbacks (
    feedback_id   TEXT PRIMARY KEY,
    source        TEXT NOT NULL,
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
    status        TEXT NOT NULL,
    error_message TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### 19.2 索引策略

```sql
CREATE INDEX idx_segments_source ON text_segments(source_id, position);
CREATE INDEX idx_characters_project ON characters(project_id);
CREATE INDEX idx_relationships_source ON relationships(source_id);
CREATE INDEX idx_relationships_target ON relationships(target_id);
CREATE INDEX idx_relationships_project ON relationships(project_id);
CREATE INDEX idx_events_project ON events(project_id, timeline_pos);
CREATE INDEX idx_memories_character ON memories(character_id, memory_type);
CREATE INDEX idx_memories_project ON memories(project_id);

-- pgvector HNSW 索引
CREATE INDEX idx_memories_embedding ON memories
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- JSONB GIN 索引
CREATE INDEX idx_characters_index ON characters USING gin (index);
CREATE INDEX idx_characters_core ON characters USING gin (core);
```

### 19.3 pgvector 配置

- Embedding 维度：768（匹配 `nomic-embed-text` 等开源 embedding 模型）
- 索引类型：HNSW
- 距离度量：cosine similarity

### 19.4 Redis 设计

#### 19.4.1 用途总览

| 用途 | Key 模式 | 过期策略 |
| --- | --- | --- |
| 任务队列 | ARQ 内部管理 | 任务完成后自动清理 |
| Working Memory | `wm:{session_id}` | TTL 2 小时 |
| 角色 Profile 缓存 | `profile:{character_id}` | TTL 10 分钟，写入时失效 |
| 建模任务状态 | `job:{job_id}` | TTL 24 小时 |
| Session Meta | `session:{session_id}:meta` | 跟随会话生命周期 |

#### 19.4.2 Session Meta 结构

```json
{
  "session_id": "sess_0001",
  "project_id": "proj_xiaoao",
  "speaker_target": "yue_buqun",
  "anchor": {
    "anchor_mode": "source_progress",
    "source_type": "page",
    "cutoff_value": 300,
    "resolved_timeline_pos": 1842,
    "snapshot_id": "snap_yue_0300",
    "display_label": "第 300 页前",
    "summary": "岳不群处于中期阶段。"
  },
  "created_at": "2026-04-21T08:00:00Z"
}
```

#### 19.4.3 Working Memory 项结构

```json
{
  "turn_id": "turn_0008",
  "speaker": "user",
  "content": "师父，您真的未曾动过夺取剑谱的念头吗？",
  "timestamp": "2026-04-21T08:03:00Z"
}
```

### 19.5 文件存储

```
/data/
├── raw_texts/          # 原始上传文件
│   └── {source_id}/
│       └── original.txt
└── exports/            # 导出文件（JSON 资产包等）
```

### 19.6 数据库迁移

使用 Alembic 管理 schema 迁移。Docker Compose 启动时自动执行 `alembic upgrade head`。

---

## 20. 部署方案

### 20.1 Docker Compose 配置

```yaml
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
      - local-llm

volumes:
  data:
  pgdata:
  redisdata:
  ollama_models:
```

### 20.2 环境变量

```bash
POSTGRES_PASSWORD=changeme
DATABASE_URL=postgresql+asyncpg://camo:changeme@postgres:5432/camo
REDIS_URL=redis://redis:6379/0
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
MODEL_CONFIG_PATH=config/models.yaml
```

---

## 21. 项目结构

```
camo/
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
├── .env.example
├── config/
│   └── models.yaml
├── data/
│   └── rules/
│       ├── meta/
│       │   ├── break_character.txt
│       │   └── meta_knowledge.txt
│       ├── setting/
│       │   └── out_of_setting.txt
│       ├── plot/
│       │   └── future_spoiler.txt
│       └── custom/
│           └── <project>.txt
├── migrations/
│   ├── env.py
│   └── versions/
├── prompts/
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
│   └── schemas/
│       ├── entity_index.json
│       ├── entity_enrichment.json
│       └── consistency_result.json
├── src/
│   └── camo/
│       ├── __init__.py
│       ├── api/
│       │   ├── main.py
│       │   ├── deps.py
│       │   └── routes/
│       │       ├── projects.py
│       │       ├── texts.py
│       │       ├── modeling.py
│       │       ├── characters.py
│       │       ├── relationships.py
│       │       ├── events.py
│       │       ├── memories.py
│       │       ├── runtime.py
│       │       ├── consistency.py
│       │       ├── reviews.py
│       │       └── feedbacks.py
│       ├── core/
│       │   ├── schemas.py
│       │   └── enums.py
│       ├── db/
│       │   ├── models.py
│       │   ├── session.py
│       │   └── queries/
│       ├── extraction/
│       │   ├── pipeline.py
│       │   ├── parsers/
│       │   │   ├── novel.py
│       │   │   ├── chat.py
│       │   │   └── ...
│       │   ├── pass1.py
│       │   ├── pass2.py
│       │   └── aggregation.py
│       ├── runtime/
│       │   ├── engine.py
│       │   ├── context.py
│       │   └── memory.py
│       ├── consistency/
│       │   ├── checker.py
│       │   ├── rules.py
│       │   └── judge.py
│       ├── models/
│       │   ├── adapter.py
│       │   ├── providers/
│       │   │   ├── anthropic.py
│       │   │   └── openai_compat.py
│       │   └── config.py
│       ├── review/
│       │   └── service.py
│       └── tasks/
│           ├── worker.py
│           └── modeling.py
└── tests/
    ├── conftest.py
    ├── test_extraction/
    ├── test_runtime/
    ├── test_consistency/
    └── test_api/
```

---

## 22. 非功能需求

### 22.1 性能

| 场景 | 指标 | 目标 |
| --- | --- | --- |
| 单次 Runtime 对话调用 | P95 延迟 | ≤ 3 秒 |
| 单次 Runtime 对话调用 | P99 延迟 | ≤ 5 秒 |
| 单角色画像查询 | P95 延迟 | ≤ 200 毫秒 |
| 多角色会话并发 | 单项目活跃会话 | ≥ 100 |

### 22.2 可扩展性

- 所有顶层资产带 `schema_version` 字段
- 枚举类字段可在项目级扩展
- 项目级隔离：项目之间默认不共享资产与记忆
- 锚点机制兼容小说、聊天记录、剧本和访谈
- 不同项目可扩展自定义 forbidden tags

### 22.3 可理解性

- 用户必须能看懂当前角色在哪个时点
- 用户必须能理解为什么角色"不知道"某件事
- 调试模式必须能解释本轮加载了哪些记忆、命中了哪些规则

### 22.4 可解释性

- 任何重要阶段快照都应可追溯到原文证据
- 任一越界拒答都应可解释为：时代外、剧情后、作品外或自定义禁说

### 22.5 国际化

- 原文支持中、英及中英混排
- 输出字段使用英文键名
- 预置枚举以英文 key 为准

### 22.6 多租户

- 每个项目归属于 `tenant_id`
- 租户之间完全数据隔离
- 支持租户级配额

---

## 23. 评测体系

### 23.1 评测指标

| 类别 | 指标 | 说明 |
| --- | --- | --- |
| 建模质量 | 角色召回率 | 与人工标注主要角色清单对比 |
| 建模质量 | 角色合并准确率 | 别名归并正确率 |
| 建模质量 | 人物画像通过率 | 各维度人工评审 |
| 建模质量 | 证据回溯覆盖率 | 每条结论是否有证据片段 |
| 运行时质量 | Anchor Resolution Accuracy | 锚点解析到正确阶段的比例 |
| 运行时质量 | Stage Awareness | 角色是否表现出与当前阶段一致的认知 |
| 运行时质量 | Out-of-Scope Refusal Accuracy | 对越界问题是否合理拒答 |
| 运行时质量 | Memory Leakage Rate | 是否引用了锚点之后的信息 |
| 运行时质量 | Anchor Switch Isolation | 锚点切换后是否串线 |
| 运行时质量 | 单轮一致性人评 | 5 分量表 |
| 运行时质量 | 多轮一致性人评 | 5 分量表 |
| 校验质量 | 误杀率 | 被错误拦截的正确回复比例 |
| 校验质量 | 漏报率 | 未被拦截的错误回复比例 |
| 性能 | 延迟 P95 / P99 | 见 22.1 |

### 23.2 评测方式

- 人工评审：抽检不同阶段同一角色的回答差异
- 对照题集：构造未来剧情、时代外概念、作品外设定等问题
- 自动规则统计：检查回答中是否出现禁用概念或未来事件引用
- 标准评测语料：覆盖虚构小说、真人访谈、群像场景

### 23.3 评测样本集

| 样本集 | 用途 |
| --- | --- |
| `future_plot_cases.json` | 未来剧情诱导题 |
| `anachronism_cases.json` | 时代错位题 |
| `anchor_switch_cases.json` | 同一角色跨锚点对照题 |

---

## 24. 安全与合规

### 24.1 内容安全

- 角色输出遵循 `constraint_profile` 与一致性校验
- 平台级内容审核由上层应用负责，Runtime 提供钩子允许注入外部审核服务
- `ethics` 命名空间覆盖角色维度最小约束

### 24.2 版权与数据合规

- 输入文本版权由调用方保证
- 为每份文本记录来源标识与导入时间
- 支持级联删除相关资产
- 资产默认仅在项目所属租户内可见

### 24.3 未成年人保护

- 上层应用可传入 `audience=minor` 标记
- 该标记下强制启用 `ethics` 命名空间完整约束，屏蔽未审核的 `custom` 约束
- 未成年人角色默认禁止成年向内容场景调用

### 24.4 隐私保护

- 真人角色（`real_person`）需标记授权状态
- 聊天记录类项目默认启用项目级加密存储
- 日志仅保留运行必需的最小字段

---

## 25. 多角色编排（第三阶段）

### 25.1 发言者推断

无指定发言者时，Runtime 根据以下因素推断：

- 场景规则（回合制顺序）
- 被 @ 的角色
- 关系权重（关系紧密的角色更可能应答）
- 角色的 `extraversion` 与 `dominance_style`

### 25.2 隔离规则

- 同一会话内角色之间不共享 Working Memory，除非场景规则允许
- 每个角色独立的 Working Memory 视图
- 多角色各自时间锚点与可见性控制

### 25.3 接口预留

当前 Runtime 接口已预留 `participants`、`scene`、`scene_type`（`group_chat` / `simulation`）和 `visibility`（`role_based` / `hidden_state`）参数。
