# CAMO TDD 补充说明

> 本文档是对 `docs/CAMO_SPEC.md` 与当前代码差异的补充实施说明。
>
> 目标不是改规格，而是指导下一轮代码实现。
>
> 本文只覆盖当前确认要做的缺口，不覆盖“多角色 Runtime / 群聊 / simulation / role_based visibility”这一整块能力。

## 1. 文档定位

当前仓库已经补齐了大部分接口面和主流程，但仍有几处关键能力与 `CAMO_SPEC.md` 不完全一致：

1. Redis / Worker / Queue / Session Store 仍存在“静默降级”为单进程本地模式的问题
2. 限流仍是进程内计数，而不是共享限流
3. 一致性校验在重试耗尽后还没有真正进入 `block`
4. Runtime 暴露了部分当前并未真正生效或未做校验的请求字段
5. 一致性校验中 Judge LLM 调用异常时静默返回空结果，等同于"全部通过"
6. 建模管线缺少：
   - Pass 1 后的别名消歧
   - 章节级聚合
   - 全书级冲突解决

本文档给出两轮实施方案，作为实际编码时的落地说明。

## 2. 范围与非目标

### 2.1 本轮纳入范围

- 严格化 Redis / ARQ / Worker 依赖
- 去除 API 进程内建模 fallback
- 去除 Session / Job 本地内存 fallback
- 共享限流
- 一致性校验 `block` 语义补齐
- 一致性校验 Judge LLM 异常可观测性
- Runtime 请求字段语义收紧
- 建模管线补齐别名消歧、章节级聚合、全书级冲突解决
- 建模任务进度阶段细化
- 对应测试补齐

### 2.2 本轮明确不做

- 多角色群聊调度
- `group_chat` / `simulation` 场景编排
- `role_based` / `hidden_state` 的多角色可见性裁剪
- 每个角色独立的 Working Memory 视图
- 同一 session 内切换说话角色

说明：这些能力仍以 `CAMO_SPEC.md` 为目标态，但不进入本轮实施范围。

## 3. 当前代码基线与差异定位

### 3.1 Runtime / 基础设施相关

当前关键代码位置：

- `src/camo/api/main.py`
- `src/camo/runtime/session_store.py`
- `src/camo/tasks/dispatch.py`
- `src/camo/api/routes/modeling.py`
- `src/camo/api/routes/runtime.py`
- `src/camo/runtime/engine.py`
- `src/camo/runtime/consistency.py`

当前问题：

1. `SessionStore.connect()` 在 Redis 不可用时会自动退回本地内存
2. `enqueue_job()` 在 ARQ/Redis 不可用时会自动 `asyncio.create_task(...)`
3. 限流在 `api.main` 中是本地窗口计数，不是共享存储
4. `run_runtime_turn()` 最终不会把高风险失败升级成 `block`
5. `RuntimeTurnRequest.speaker_target` 当前不校验与 session 绑定角色的一致性，传入不一致的值不会报错也不会生效
6. `RuntimeOptions.include_reasoning_summary` 当前实际不生效，reasoning_summary 始终返回
7. `run_consistency_check()` 中 Judge LLM 调用在 `ProviderConfigurationError` 或其他异常时 `return []`，不记录任何信息，上层无法区分"Judge 通过"和"Judge 不可用"

### 3.2 建模管线相关

当前关键代码位置：

- `src/camo/extraction/pass1.py`
- `src/camo/extraction/pass2.py`
- `src/camo/tasks/modeling.py`

当前问题：

1. Pass 1 的跨段合并主要依赖名字和别名重叠，没有真正的 LLM 别名消歧阶段
2. Pass 2 当前仍更接近“从若干证据片段直接生成最终画像”
3. 还没有章节级聚合
4. 还没有全书级冲突解决
5. 建模任务进度没有显式反映上述阶段

## 4. 实施原则

### 4.1 不改规格，代码追规格

本文档不对 `CAMO_SPEC.md` 做降级解释。实现以规格为准。

### 4.2 尽量复用当前代码骨架

不推翻当前目录结构，优先在现有模块基础上做：

- Runtime 链路补强
- Session / Queue 的严格化
- Pass 1 / Pass 2 的阶段拆分

### 4.3 尽量避免新增长期存储表

本轮优先不引入新的中间态数据库表。章节级结果、冲突候选等中间产物优先作为任务内临时对象处理，最终仍写回现有：

- `characters`
- `relationships`
- `events`
- `memories`
- `reviews`
- `character_versions`

### 4.4 测试不能依赖“静默 fallback”

生产代码不再自动退回本地模式。

如果测试需要无 Redis / 无 Worker 场景，应通过：

- dependency override
- test double
- monkeypatch

显式注入测试替身，而不是依赖生产代码的自动降级。

## 5. 第一轮实施：严格化 Runtime 与运行链路

第一轮目标：把“系统看起来有这些能力”改成“系统在运行层面真的按规格执行”。

### 5.1 Session Store 改造

#### 5.1.1 目标

去掉 `src/camo/runtime/session_store.py` 中“Redis 不可用时自动切到内存”的行为。

#### 5.1.2 设计

建议将当前 `SessionStore` 拆成两个明确角色：

1. `RedisSessionStore`
2. `InMemorySessionStore`（仅测试用）

推荐形态：

```python
class BaseSessionStore(Protocol):
    async def connect(self) -> None: ...
    async def save_session_meta(self, session_id: str, payload: dict[str, Any]) -> None: ...
    async def load_session_meta(self, session_id: str) -> dict[str, Any] | None: ...
    async def append_working_memory(self, session_id: str, item: dict[str, Any]) -> None: ...
    async def load_working_memory(self, session_id: str, *, limit: int | None = None) -> list[dict[str, Any]]: ...
    async def save_job_status(self, job_id: str, payload: dict[str, Any]) -> None: ...
    async def load_job_status(self, job_id: str) -> dict[str, Any] | None: ...
```

其中：

- `RedisSessionStore` 只做 Redis 实现
- `InMemorySessionStore` 只在测试或特定 mock 场景中显式使用

#### 5.1.3 关键改动点

- `src/camo/runtime/session_store.py`
  - 删除 `_use_memory` 自动切换逻辑
  - 删除 `_BACKEND` 作为生产 fallback 的角色
  - Redis 连接失败时直接抛出明确异常，例如 `SessionStoreUnavailableError`

- `src/camo/api/main.py`
  - 应用启动时初始化 `RedisSessionStore`
  - 若连接失败，应用启动直接失败，而不是默默进入降级模式

- `src/camo/api/deps.py`
  - 返回的类型改为基础协议或明确 store 类型

#### 5.1.4 验收标准

- Redis 不可用时，API 不应继续以“完整能力”启动
- Runtime session / working memory / modeling job status 全部只能走 Redis
- 测试若需要内存 store，必须显式 override

### 5.2 任务队列与 Worker 严格化

#### 5.2.1 目标

去掉 `src/camo/tasks/dispatch.py` 中“入队失败就 `asyncio.create_task(...)`”的 fallback。

#### 5.2.2 设计

新增明确的任务派发异常：

- `TaskQueueUnavailableError`
- `WorkerUnavailableError`

关键原则：

- 建模任务提交必须成功入 ARQ 队列，否则直接返回 503
- API 进程不再代替 Worker 执行建模任务

#### 5.2.3 Worker 存活检查

仅仅能连 Redis 还不够，还要避免“任务能入队，但没有 Worker 消费”。

建议加入 Worker 心跳机制：

- Worker 启动后定期写入 Redis Key，例如：
  - `worker:heartbeat:{worker_id}`
- TTL 例如 30 秒
- API 在建模任务提交前检查是否至少存在一个有效心跳

关键代码位置：

- `src/camo/tasks/worker.py`
  - 增加启动钩子 / 周期心跳上报

- `src/camo/tasks/dispatch.py`
  - 派发前或派发时检查 Worker 心跳

- `src/camo/api/routes/modeling.py`
  - 若无活跃 Worker，返回 `503 Service Unavailable`

#### 5.2.4 Runtime Memory Writeback 的处理策略

Runtime 对话本身不应因为“episodic memory 写回失败”而整体失败。

因此建议：

- `POST /runtime/sessions/{session_id}/turns` 的主回复链路不依赖 Worker 心跳
- 但 memory writeback 只能尝试入队，不再退回 API 进程本地执行
- 若 writeback 入队失败：
  - 不中断对话主回复
  - 在日志或 debug trace 中记录失败

这样可以同时满足：

- 建模任务严格依赖 Worker
- Runtime 对话主链路不被非关键异步副作用拖垮

#### 5.2.5 关键改动点

- `src/camo/tasks/dispatch.py`
  - 删除 `asyncio.create_task(fallback_runner(payload))`
  - 改为只做 ARQ enqueue
  - 失败即抛异常

- `src/camo/api/routes/modeling.py`
  - 捕获队列/Worker 不可用异常并返回 503

- `src/camo/api/routes/runtime.py`
  - writeback callback 中捕获入队失败，仅记录，不替代执行

#### 5.2.6 验收标准

- 建模任务绝不在 API 进程中直接执行
- Worker 挂掉时，建模提交立即失败而不是假成功
- Runtime 对话仍可返回，但 writeback 不会偷偷在 API 内执行

### 5.3 限流改造为共享限流

#### 5.3.1 目标

将 `src/camo/api/main.py` 中当前本地窗口计数的限流逻辑，替换为规格中要求的共享限流。

#### 5.3.2 设计

建议使用：

- `slowapi`
- Redis 作为 storage backend

建议新增模块：

- `src/camo/api/rate_limit.py`

模块职责：

1. 初始化 `Limiter`
2. 配置 Redis storage URI
3. 提供统一的限流装饰器
4. 提供 429 异常处理器

例如：

```python
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=settings.redis_url,
)
```

#### 5.3.3 分类映射

按规格固定以下分类：

- 读操作：`60/minute`
- 写操作：`20/minute`
- Runtime 对话：`30/minute`
- 建模任务提交：`5/minute`

#### 5.3.4 路由层实现方式

推荐在路由层显式加 decorator，而不是继续保留一套自定义 middleware 分类器。

注意：

- `slowapi` decorator 需要 endpoint 签名中显式包含 `request: Request`
- 因此需要为被限流的接口补上 `request: Request`

关键文件：

- `src/camo/api/main.py`
  - 删除当前自定义限流 middleware
  - 注册 `slowapi` limiter 与异常处理

- `src/camo/api/routes/*.py`
  - 给对应 endpoint 增加 decorator

#### 5.3.5 验收标准

- 多实例部署时限流结果一致
- 应用重启不再重置限流状态
- 限流分类与 `CAMO_SPEC.md` 保持一致

### 5.4 一致性校验补齐 `block`

#### 5.4.1 目标

当高风险问题触发 `regenerate` 且超过最大重试次数时，最终结果必须进入 `block`，而不是把最后一次生成结果直接返回。

#### 5.4.2 设计

当前 `src/camo/runtime/consistency.py` 的 `resolve_action()` 可以保持“单轮校验决议”不变：

- 无问题：`accept`
- 中风险：`warn`
- 高风险：`regenerate`

但在 `src/camo/runtime/engine.py` 中增加“重试耗尽后的最终收口逻辑”：

```python
for attempt in range(max_retries + 1):
    ...
    if final_check["action"] != "regenerate":
        break

if final_check["action"] == "regenerate":
    final_check["action"] = "block"
    result_payload["response"] = build_block_response(...)
```

#### 5.4.3 `block` 时的返回策略

不能把最后一轮不合规回复原样返回。

建议：

- 用一个确定性的、安全的角色口吻拒答模板覆盖原始回复
- 返回：
  - `consistency_check.passed = false`
  - `consistency_check.action = "block"`

建议新增函数：

- `build_block_response(character, anchor_state) -> dict[str, Any]`

输出应满足：

- 保持角色口吻
- 不泄露未来信息
- 不包含系统口吻
- 长度可控

#### 5.4.4 关键改动点

- `src/camo/runtime/engine.py`
  - 增加 block 收口逻辑
  - 增加安全 fallback 回复构造

- `src/camo/core/schemas.py`
  - `ConsistencyCheckResponse.action` 已包含 `block`，无需再扩展

#### 5.4.5 验收标准

- 高风险问题在多次 regenerate 后，不再返回原始危险回复
- 最终返回中明确出现 `block`

### 5.5 Judge LLM 异常可观测性

#### 5.5.1 目标

当前 `src/camo/runtime/consistency.py` 中 Judge LLM 调用在异常时直接 `return []`，上层无法区分"Judge 校验通过"和"Judge 不可用"。

#### 5.5.2 设计

不改变 Judge 异常时不阻塞主链路的策略（Judge 挂掉不应导致对话不可用），但必须让上层知道 Judge 被跳过了。

建议：

- Judge 异常时，在返回的 `rule_trace` 中追加一条标记：

```python
{
    "dimension": "judge_availability",
    "severity": "low",
    "description": "Judge LLM unavailable, skipped semantic consistency check",
    "evidence_rule_id": "system.judge_unavailable"
}
```

- 同时在日志中记录异常详情（当前完全吞掉了异常信息）

#### 5.5.3 关键改动点

- `src/camo/runtime/consistency.py`
  - Judge 异常分支：记录日志 + 返回包含 `judge_unavailable` 标记的 issues 列表
  - 该标记 severity 为 `low`，不会触发 `warn` 或 `regenerate`

#### 5.5.4 验收标准

- Judge 不可用时，对话仍正常返回
- 返回的 `consistency_check.issues` 或 debug trace 中包含 `judge_unavailable` 标记
- 日志中记录 Judge 调用异常的具体原因

### 5.6 Runtime 请求字段语义收紧

#### 5.6.1 `speaker_target`

本轮不做多角色，因此每轮 turn request 中传入的 `speaker_target` 不应再表现得像可切换角色。

建议策略：

- 若请求未传 `speaker_target`：沿用 session 绑定角色
- 若传入值与 session 绑定角色一致：允许
- 若传入值与 session 绑定角色不一致：返回 `400 Bad Request`

这样比“静默忽略”更明确。

关键文件：

- `src/camo/api/routes/runtime.py`
- `src/camo/core/schemas.py`

#### 5.6.2 `include_reasoning_summary`

当前字段已定义，但未生效。

建议：

- 在 `run_runtime_turn()` 中接收该布尔值
- 若为 `false`，最终响应中将 `reasoning_summary` 置为 `None`

关键文件：

- `src/camo/api/routes/runtime.py`
- `src/camo/runtime/engine.py`

#### 5.6.3 验收标准

- `speaker_target` 不再承诺未实现能力
- `include_reasoning_summary=false` 时，响应不再返回 reasoning summary

### 5.7 第一轮建议新增测试

- `tests/runtime/test_runtime_blocking.py`
  - 高风险重试耗尽后进入 `block`

- `tests/runtime/test_runtime_options.py`
  - `include_reasoning_summary=false` 时被抑制
  - `speaker_target` 不一致时报 400

- `tests/api/test_modeling_queue.py`
  - 无 Worker 心跳时建模提交返回 503

- `tests/api/test_rate_limit.py`
  - 验证四类限流规则接入

- `tests/runtime/test_session_store.py`
  - Redis store 不再自动降级

- `tests/runtime/test_consistency_judge.py`
  - Judge 异常时返回 `judge_unavailable` 标记
  - Judge 异常不影响主链路返回

## 6. 第二轮实施：补齐建模管线的最后三步

第二轮目标：在不推翻现有 Pass 1 / Pass 2 框架的前提下，把规格中的“别名消歧 -> 章节级聚合 -> 全书级冲突解决”补齐。

### 6.1 Pass 1：补真正的别名消歧

#### 6.1.1 当前问题

当前 `src/camo/extraction/pass1.py` 的 `_aggregate_mentions()` 仅按：

- `name`
- `aliases`

做重叠合并。

这会导致两类问题：

1. 同人异名未合并
2. 同名异人被误合并

#### 6.1.2 目标

在当前“初步聚类”之后，增加一轮候选对判定，把不确定的 cluster pair 送给 LLM 判断“是否同一角色”。

#### 6.1.3 推荐实现

在 `pass1.py` 中把当前流程拆成三步：

1. `extract_mentions(...)`
2. `initial_cluster_mentions(...)`
3. `disambiguate_clusters(...)`

推荐流程：

```python
mentions = await extract_mentions(...)
clusters = initial_cluster_mentions(mentions)
candidate_pairs = build_disambiguation_candidates(clusters)
decisions = await disambiguate_cluster_pairs(candidate_pairs, model_adapter)
clusters = apply_disambiguation_decisions(clusters, decisions)
payloads = finalize_character_index_payloads(clusters)
```

#### 6.1.4 候选对筛选规则

只把“不确定但值得判”的 pair 送 LLM，避免 N² 爆炸。

候选条件建议：

- canonical name 不同，但 alias / title / identity 存在交叉
- canonical name 相同，但身份描述、title、first appearance 差异较大
- 同章节或相邻章节高频共现

#### 6.1.5 Prompt 与 Schema

建议新增：

- `prompts/extraction/character_disambiguation.jinja2`
- `prompts/schemas/character_disambiguation.json`

输出格式建议：

```json
{
  "same_character": true,
  "confidence": 0.88,
  "reason": "“君子剑”与“岳掌门”在多段证据中都指向同一华山掌门身份。"
}
```

#### 6.1.6 关键改动点

- `src/camo/extraction/pass1.py`
  - 拆函数
  - 增加 disambiguation 阶段

- `tests/extraction/test_pass1_disambiguation.py`
  - 增加 alias / title / same-name edge cases

### 6.2 Pass 2：先章节级，再全书级

#### 6.2.1 当前问题

当前 `src/camo/extraction/pass2.py` 更接近：

- 挑一批角色相关 evidence
- 一次性让模型生成最终画像、关系、事件、记忆

这种方式已经可用，但还不是规格里的：

- 章节级聚合
- 全书级冲突解决

#### 6.2.2 目标

将当前项目级画像生成流程拆为三层：

1. segment evidence 级输入
2. chapter aggregate 级中间结果
3. book aggregate 级最终结果

#### 6.2.3 推荐实现结构

建议在 `src/camo/extraction/pass2.py` 内部引入以下阶段函数：

- `group_evidence_by_chapter(...)`：按章节分组证据（确定性）
- `build_chapter_payload(...)`：在章节内做确定性合并（去重、归类），**不调 LLM**
- `merge_chapter_payloads(...)`：跨章节确定性合并（**不调 LLM**）
- `resolve_book_level_conflicts(...)`：全书级冲突解决（**调 LLM**）
- `finalize_character_assets(...)`：构造最终写入对象（确定性）

推荐流程：

```python
evidence = select_character_evidence(...)
chapter_groups = group_evidence_by_chapter(evidence, segment_lookup)

# 章节级：纯确定性合并，不调 LLM
chapter_payloads = []
for chapter_key, chapter_evidence in chapter_groups:
    payload = build_chapter_payload(chapter_key, chapter_evidence)
    chapter_payloads.append(payload)

# 跨章节：确定性合并
merged = merge_chapter_payloads(chapter_payloads)

# 全书级：仅冲突字段调 LLM
resolved = await resolve_book_level_conflicts(merged, model_adapter)

final_assets = finalize_character_assets(resolved)
```

**关键约束**：章节级函数（`build_chapter_payload`、`merge_chapter_payloads`）是同步的确定性操作，不涉及 LLM 调用。LLM 成本集中在 `resolve_book_level_conflicts` 一次调用中。

### 6.3 evidence 采样参数的语义变化

当前 `select_character_evidence()` 有一个 `max_segments` 参数（默认 18），语义是"从全部 source 中均匀采样 N 个 segment"。

章节级聚合后，这个参数的语义需要调整：

- **改前**：全书采样上限，超过则均匀抽样丢弃
- **改后**：每章节采样上限，控制单章节输入不超限

建议：

- 将参数重命名为 `max_segments_per_chapter`，默认值可适当降低（如 10）
- 全书不再设硬上限，因为章节级合并是确定性操作，不受 LLM 上下文窗口限制
- 全书级冲突解决的输入是章节级合并后的结构化摘要，不是原始 segment，token 量可控

关键文件：

- `src/camo/extraction/pass2.py`
- `src/camo/core/schemas.py`（`ModelingJobCreateRequest.max_segments_per_character` → `max_segments_per_chapter`）

### 6.4 章节级聚合策略

#### 6.4.1 章节粒度定义

优先使用已有字段：

- `segment.chapter`

若缺失，则退化为：

- `source_id + round`
- 或 `source_id + 固定窗口`

目标是先把项目内证据切成较小、稳定的局部块。

#### 6.4.2 章节级输出内容

每个 chapter payload 至少包含：

- trait evidence
- motivation evidence
- relationship mentions
- events
- memories
- temporal snapshot candidates

#### 6.4.3 章节级合并原则

章节内优先做确定性合并：

- trait / motivation evidence：按 `source_segments` 去重
- relationship mentions：按 `(target, category, subtype)` 合并
- events：按 `timeline_pos + title` 去重
- memories：按 `content + source_event_id` 去重

### 6.5 全书级冲突解决

#### 6.5.1 需要 LLM 参与的冲突类型

以下字段仅靠 deterministic merge 容易出错，建议进 LLM 冲突解决：

- `motivation_profile`
- `behavior_profile`
- `communication_profile`
- 同一关系在不同阶段的解释冲突
- 同一事件描述文本冲突
- temporal snapshot 的阶段边界与摘要冲突

#### 6.5.2 Prompt 与 Schema

建议新增：

- `prompts/extraction/character_portrait_conflict.jinja2`
- `prompts/schemas/character_portrait_conflict.json`

输入内容：

- 章节级聚合后的结构化候选
- 冲突字段列表
- 保留的 `source_segments`

输出内容：

- 最终 `character_core`
- 最终 `character_facet`
- 最终 relationships / events / memories
- 冲突解释摘要（可用于 debug / review）

#### 6.5.3 证据链要求

无论章节级还是全书级，最终输出都必须保留 `source_segments`。

实现原则：

- 聚合只做“引用集合并集”
- 不在聚合阶段丢证据

### 6.6 建模任务进度更新

#### 6.6.1 当前问题

`src/camo/tasks/modeling.py` 当前进度仍是比较粗的两段：

- source indexing
- portrait aggregation

#### 6.6.2 新的阶段建议

建议 job status 增加：

- `stage`
- `stage_message`
- `current_source_id`
- `current_character_id`
- `current_chapter`

建议阶段枚举：

1. `queued`
2. `pass1_extract`
3. `pass1_disambiguate`
4. `pass2_chapter_aggregate`
5. `pass2_book_resolve`
6. `persist_assets`
7. `review_seed`
8. `completed`

#### 6.6.3 关键改动点

- `src/camo/tasks/modeling.py`
  - 细化 job status patch

- `src/camo/core/schemas.py`
  - `ModelingJobStatusResponse` 增加上述字段

### 6.7 LLM 成本影响

章节级聚合改造后，LLM 调用次数变化如下（以笑傲江湖 40 回、10 个主要角色为例）：

| 阶段 | 改前 | 改后 | 说明 |
| --- | --- | --- | --- |
| Pass 1 逐段抽取 | ~700 次 | ~700 次 | 不变 |
| Pass 1 别名消歧 | 0 | ~5-10 次 | 新增，候选对数量有限 |
| Pass 2 画像生成 | ~10 次（每角色 1 次） | ~10 次 | 章节级是确定性合并，不增加 LLM 调用 |
| 全书级冲突解决 | 0 | ~10 次（每角色 1 次） | 新增 |
| **总计** | **~710 次** | **~725 次** | **增幅约 2%** |

成本增幅可控。主要变化不在调用次数，而在 Pass 2 画像生成的**输入 token 量**——改前每角色仅采样 18 个 segment，改后章节级合并覆盖全书证据，全书级冲突解决的输入是结构化摘要而非原始文本，token 增长有限。

### 6.8 第二轮建议新增测试

- `tests/extraction/test_pass1_disambiguation.py`
  - 同人异名
  - 同名异人
  - title 交叉

- `tests/extraction/test_pass2_chapter_aggregation.py`
  - 同一章节去重
  - 跨章节关系合并

- `tests/extraction/test_pass2_book_conflict_resolution.py`
  - 不同章节下 motivation / style / snapshot 边界冲突

- `tests/tasks/test_modeling_progress.py`
  - job stage 按顺序推进

## 7. 关键代码改动清单

### 7.1 第一轮

- `src/camo/api/main.py`
  - 移除本地限流 middleware
  - 注册共享限流
  - 启动时强连接 Redis session store

- `src/camo/runtime/session_store.py`
  - 拆 Redis / InMemory store
  - 删除自动 fallback

- `src/camo/tasks/dispatch.py`
  - 删除 API 进程本地执行 fallback
  - 增加严格 enqueue + Worker 可用性检查

- `src/camo/tasks/worker.py`
  - 增加心跳上报

- `src/camo/api/routes/modeling.py`
  - 队列失败 / 无 Worker 时返回 503

- `src/camo/api/routes/runtime.py`
  - 收紧 `speaker_target`
  - 传递 `include_reasoning_summary`

- `src/camo/runtime/engine.py`
  - 重试耗尽后转 `block`
  - 构造安全 fallback 回复
  - 控制 reasoning summary 输出

- `src/camo/runtime/consistency.py`
  - 保持单轮 action 决议逻辑
  - 配合 engine 完成 block 收口
  - Judge 异常分支：记录日志 + 返回 `judge_unavailable` 标记

- `src/camo/core/schemas.py`
  - 视需要补充响应字段

- `pyproject.toml`
  - 增加限流相关依赖

### 7.2 第二轮

- `src/camo/extraction/pass1.py`
  - 拆分 extract / cluster / disambiguate / finalize

- `src/camo/extraction/pass2.py`
  - 拆分 chapter-level / book-level aggregation

- `src/camo/tasks/modeling.py`
  - 新阶段进度上报

- `prompts/extraction/character_disambiguation.jinja2`
- `prompts/schemas/character_disambiguation.json`
- `prompts/extraction/character_portrait_conflict.jinja2`
- `prompts/schemas/character_portrait_conflict.json`

## 8. 交付顺序

### 8.1 第一轮交付顺序

1. 先改 `SessionStore` 和 `dispatch`
2. 再改 `api.main` 启动逻辑与限流
3. 再改 runtime block 与请求字段语义
4. 最后补第一轮测试

理由：

- 先把“系统是否真的按规格运行”这件事收紧
- 再处理生成结果的行为语义

### 8.2 第二轮交付顺序

1. 先做 Pass 1 别名消歧
2. 再做 Pass 2 章节级聚合
3. 再做全书级冲突解决
4. 最后补 job progress 和测试

理由：

- Pass 1 角色集合更准，Pass 2 才更稳定
- 章节级先有了，全书级冲突解决才能建立在较干净的输入之上

## 9. 风险与控制

### 9.1 第一轮风险

- 开发环境若未启动 Redis / Worker，会比现在更容易直接报错
- 共享限流接入后，部分测试需要改写

控制方式：

- 为测试提供显式 `InMemorySessionStore`
- 在 README / `.env.example` 中明确本地启动要求

### 9.2 第二轮风险

- 建模耗时会增加
- Prompt 数量增加，测试替身需要同步维护
- 聚合逻辑拆开后，pass2.py 复杂度会上升

控制方式：

- 用章节级 deterministic merge 先尽量收敛，再把少量冲突交给 LLM
- 保持“中间结果不落库，最终结果才落库”，避免迁移范围膨胀

## 10. 完成定义

当且仅当满足以下条件，本补充说明对应的实施才算完成：

1. Redis 不可用时，Session / Job 不再静默退回本地内存
2. 建模任务不再在 API 进程内执行
3. 建模提交在无活跃 Worker 时会明确失败
4. 限流成为共享限流，并按规格分类
5. Runtime 在高风险重试耗尽后会进入 `block`
6. Judge LLM 不可用时，对话仍可返回，但 trace 中包含 `judge_unavailable` 标记
7. `speaker_target` 与 `include_reasoning_summary` 的行为与实际能力一致
8. Pass 1 补齐别名消歧
9. Pass 2 补齐章节级聚合与全书级冲突解决，章节级为确定性合并，仅全书级调 LLM
10. `max_segments_per_character` 语义调整为 `max_segments_per_chapter`
11. 建模进度可反映真实阶段
12. 新增测试通过，并且全量测试继续通过

