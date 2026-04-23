[English](#english) | [中文](#zh-cn)

# CAMO

CAMO (Character Modeling & Simulation Base) turns unstructured text into reusable character assets and runtime character sessions.

<a id="english"></a>
## English

### What CAMO does today

CAMO ingests story material such as novels, chats, scripts, interviews, and plain text, then turns that material into structured character data that can be stored, reviewed, retrieved, and used in runtime conversations.

The current codebase includes:

- A FastAPI service for projects, text import, modeling jobs, characters, events, relationships, runtime sessions, consistency checks, reviews, feedback, and system health
- A background worker for long-running modeling jobs and runtime memory writeback
- PostgreSQL with `pgvector` for structured storage and retrieval
- Redis for session state, rate limiting, queue/job status, and short-lived working memory
- Demo pages at `/demo`, `/demo/portrait`, and `/demo/chat`
- Prompt templates, JSON schemas, and example assets in `examples/yue-buqun`

### Current workflow

1. Create a project.
2. Import one or more text sources.
3. Start a modeling job.
4. Let the worker build character indexes, portraits, events, memories, relationships, and anchorable snapshots.
5. Inspect the results through the API or demo pages.
6. Start a runtime session for a character, choose an anchor, send turns, and let the system retrieve memories, run consistency checks, and queue writeback.

### Docker stack

`docker-compose.yml` starts these services:

| Service | Purpose |
| --- | --- |
| `api` | Runs migrations on startup, then serves the FastAPI app on port `8000` |
| `worker` | Runs the ARQ worker for modeling jobs and runtime memory writeback |
| `postgres` | Primary database |
| `redis` | Session store, queue backend, job status store, and rate-limit backend |
| `ollama` | Optional local model endpoint, started only with the `local-llm` profile |

The default path uses the provider settings from `.env`. You only need the `ollama` profile when you explicitly want to test a local model endpoint.

### Quick start

1. Create your local environment file:

   ```bash
   cp .env.example .env
   ```

2. Fill in the model keys or custom base URLs you want to use in `.env`.

   Default startup uses the online provider settings from `.env`. The optional local path uses `OLLAMA_BASE_URL`.

3. Start the standard stack:

   ```bash
   docker compose up --build
   ```

4. Start with the optional local model service:

   ```bash
   docker compose --profile local-llm up --build
   ```

5. Open the common entry points:

   - API health: `http://localhost:8000/healthz`
   - System health: `http://localhost:8000/api/v1/system/health`
   - OpenAPI docs: `http://localhost:8000/docs`
   - Demo hub: `http://localhost:8000/demo`
   - Portrait inspector: `http://localhost:8000/demo/portrait`
   - Chat demo: `http://localhost:8000/demo/chat`

6. Stop everything:

   ```bash
   docker compose down
   ```

If you set `API_KEY`, add `X-API-Key: <your key>` to requests under `/api/v1`.

### Minimal API walkthrough

Create a project:

```bash
curl -X POST http://localhost:8000/api/v1/projects \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Swordsman Demo",
    "description": "Local CAMO test project"
  }'
```

Import text directly:

```bash
curl -X POST http://localhost:8000/api/v1/projects/<project_id>/texts \
  -H "Content-Type: application/json" \
  -d '{
    "filename": "sample.txt",
    "source_type": "novel",
    "content": "Chapter 1..."
  }'
```

Or upload a file:

```bash
curl -X POST http://localhost:8000/api/v1/projects/<project_id>/texts/upload \
  -F "file=@/absolute/path/to/sample.txt" \
  -F "source_type=novel"
```

Start a modeling job:

```bash
curl -X POST http://localhost:8000/api/v1/projects/<project_id>/modeling \
  -H "Content-Type: application/json" \
  -d '{
    "max_segments_per_chapter": 6
  }'
```

Check modeling progress:

```bash
curl http://localhost:8000/api/v1/projects/<project_id>/modeling/<job_id>
```

List modeled characters:

```bash
curl http://localhost:8000/api/v1/projects/<project_id>/characters
```

Create a runtime session:

```bash
curl -X POST http://localhost:8000/api/v1/runtime/sessions \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "<project_id>",
    "speaker_target": "<character_id>",
    "scene": {
      "scene_type": "single_chat",
      "description": "Local runtime test",
      "anchor": {
        "anchor_mode": "source_progress",
        "source_type": "timeline_pos",
        "cutoff_value": 999999
      }
    }
  }'
```

Send a turn:

```bash
curl -X POST http://localhost:8000/api/v1/runtime/sessions/<session_id>/turns \
  -H "Content-Type: application/json" \
  -d '{
    "user_input": {
      "content": "Who are you?"
    }
  }'
```

### Repository layout

- `src/camo/api`: HTTP routes, dependencies, demo pages, and request handling
- `src/camo/tasks`: background worker, job dispatch, and writeback tasks
- `src/camo/runtime`: anchor resolution, consistency checks, and runtime turn logic
- `src/camo/extraction`: text parsing and multi-pass modeling pipeline
- `prompts`: prompt templates and JSON schemas
- `migrations`: Alembic migrations
- `config`: model routing configuration
- `tests`: automated checks
- `docs`: product, spec, and technical design notes
- `examples`: example outputs such as the Yue Buqun portrait and memories

### Local-only files

Keep machine-specific files out of Git. The repository already ignores common local-only files such as:

- `.env` and `.env.*` except `.env.example`
- `.claude/`, `.vscode/`, `.idea/`, `.venv/`, and `.playwright-cli/`
- `books/`
- `data/raw_texts/` and `data/exports/`
- `docker-compose.override.yml`
- `config/*.local.yaml` and `config/local/`

### License

This project is licensed under the MIT License. See [LICENSE](LICENSE).

<a id="zh-cn"></a>
## 中文

### 现在这套 CAMO 能做什么

CAMO 现在可以把小说、聊天记录、剧本、访谈和普通文本导入进来，抽取成结构化的人物资产，并把这些资产用于后续检索、审阅和运行时对话。

当前代码仓库已经包含：

- 基于 FastAPI 的服务，覆盖项目、文本导入、建模任务、角色、事件、关系、运行时会话、一致性检查、审阅、反馈和系统健康检查
- 一个后台 worker，用来处理耗时建模任务和运行时记忆回写
- PostgreSQL + `pgvector`，用于结构化存储和检索
- Redis，用于会话状态、限流、队列和短期工作记忆
- `/demo`、`/demo/portrait`、`/demo/chat` 三个演示页面
- 提示词模板、JSON Schema，以及 `examples/yue-buqun` 里的岳不群示例资产

### 当前工作流

1. 创建项目。
2. 导入一个或多个文本源。
3. 发起建模任务。
4. 由 worker 在后台生成角色索引、角色画像、事件、记忆、关系和可锚定快照。
5. 通过 API 或 Demo 页面检查结果。
6. 为某个角色创建运行时会话，选定锚点后进行多轮对话，并让系统自动做记忆检索、一致性检查和回写排队。

### Docker 运行框架

`docker-compose.yml` 目前会启动这些服务：

| 服务 | 作用 |
| --- | --- |
| `api` | 启动时先跑迁移，再在 `8000` 端口提供 FastAPI 服务 |
| `worker` | 运行 ARQ worker，处理建模任务和运行时记忆回写 |
| `postgres` | 主数据库 |
| `redis` | 会话存储、队列后端、任务状态存储和限流后端 |
| `ollama` | 可选的本地模型服务，只在 `local-llm` profile 下启动 |

默认路径使用 `.env` 里配置的在线模型服务。只有在你明确要测试本地模型时，才需要把 `ollama` 一起拉起来。

### 快速开始

1. 先生成本地环境文件：

   ```bash
   cp .env.example .env
   ```

2. 在 `.env` 里填入你要使用的模型密钥或自定义基地址。

   默认启动路径走在线模型配置。可选的本地路径使用 `OLLAMA_BASE_URL`。

3. 启动标准栈：

   ```bash
   docker compose up --build
   ```

4. 如果要把可选的本地模型服务一起启动：

   ```bash
   docker compose --profile local-llm up --build
   ```

5. 启动后可访问这些入口：

   - API 健康检查：`http://localhost:8000/healthz`
   - 系统健康检查：`http://localhost:8000/api/v1/system/health`
   - OpenAPI 文档：`http://localhost:8000/docs`
   - Demo 首页：`http://localhost:8000/demo`
   - 画像检查页：`http://localhost:8000/demo/portrait`
   - 对话演示页：`http://localhost:8000/demo/chat`

6. 停止服务：

   ```bash
   docker compose down
   ```

如果你配置了 `API_KEY`，那么访问 `/api/v1` 下的接口时要带上 `X-API-Key: <你的 key>`。

### 最小调用流程

先创建项目：

```bash
curl -X POST http://localhost:8000/api/v1/projects \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Swordsman Demo",
    "description": "本地 CAMO 测试项目"
  }'
```

直接导入文本：

```bash
curl -X POST http://localhost:8000/api/v1/projects/<project_id>/texts \
  -H "Content-Type: application/json" \
  -d '{
    "filename": "sample.txt",
    "source_type": "novel",
    "content": "第一章……"
  }'
```

或者上传文件：

```bash
curl -X POST http://localhost:8000/api/v1/projects/<project_id>/texts/upload \
  -F "file=@/absolute/path/to/sample.txt" \
  -F "source_type=novel"
```

发起建模任务：

```bash
curl -X POST http://localhost:8000/api/v1/projects/<project_id>/modeling \
  -H "Content-Type: application/json" \
  -d '{
    "max_segments_per_chapter": 6
  }'
```

查看建模进度：

```bash
curl http://localhost:8000/api/v1/projects/<project_id>/modeling/<job_id>
```

列出已建模角色：

```bash
curl http://localhost:8000/api/v1/projects/<project_id>/characters
```

创建运行时会话：

```bash
curl -X POST http://localhost:8000/api/v1/runtime/sessions \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "<project_id>",
    "speaker_target": "<character_id>",
    "scene": {
      "scene_type": "single_chat",
      "description": "本地运行时测试",
      "anchor": {
        "anchor_mode": "source_progress",
        "source_type": "timeline_pos",
        "cutoff_value": 999999
      }
    }
  }'
```

发送一轮对话：

```bash
curl -X POST http://localhost:8000/api/v1/runtime/sessions/<session_id>/turns \
  -H "Content-Type: application/json" \
  -d '{
    "user_input": {
      "content": "你是谁？"
    }
  }'
```

### 仓库目录

- `src/camo/api`：HTTP 路由、依赖注入、Demo 页面和请求处理
- `src/camo/tasks`：后台 worker、任务派发和回写任务
- `src/camo/runtime`：锚点解析、一致性检查和运行时对话逻辑
- `src/camo/extraction`：文本解析和多阶段建模流水线
- `prompts`：提示词模板和 JSON Schema
- `migrations`：Alembic 迁移
- `config`：模型路由配置
- `tests`：自动化测试
- `docs`：产品文档、规格说明和技术设计文档
- `examples`：示例产物，例如岳不群画像和记忆

### 不应上传的本地文件

仓库已经默认忽略常见的本地专用文件，例如：

- `.env` 和 `.env.*`，但保留 `.env.example`
- `.claude/`、`.vscode/`、`.idea/`、`.venv/`、`.playwright-cli/`
- `books/`
- `data/raw_texts/` 和 `data/exports/`
- `docker-compose.override.yml`
- `config/*.local.yaml` 和 `config/local/`

### 开源协议

本项目采用 MIT 协议，详见 [LICENSE](LICENSE)。
