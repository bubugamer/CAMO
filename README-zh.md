[English](README.md) | [中文](README-zh.md)

# CAMO

CAMO（Character Modeling & Simulation Base）用于把非结构化文本中的人物转成可复用的角色资产，便于后续索引、画像、记忆存储和运行时对话。

## 项目内容

- 基于 FastAPI 的服务，支持项目创建、文本导入、角色索引、角色画像抽取和角色对话
- 基于 PostgreSQL + `pgvector` 的结构化存储与检索
- 基于 Redis 的缓存与短期运行时记忆
- 用于抽取与对话的提示词模板和模型路由配置
- 可直接查看的 Demo 页面
- 一套岳不群示例资产，放在 [examples/yue-buqun](examples/yue-buqun)

## Docker 运行框架

当前 Docker 编排由 `docker-compose.yml` 驱动，包含以下服务：

- `api`：基于本仓库的 `Dockerfile` 构建，启动时先执行数据库迁移，再对外提供 `8000` 端口的 API
- `postgres`：主数据库，镜像为 `pgvector/pgvector:pg16`
- `redis`：缓存和短期运行时状态
- `ollama`：可选的本地模型服务，只在启用 `local-llm` profile 时启动

数据持久化方式分两部分：

- 本地 `./data` 挂载到容器内 `/app/data`
- PostgreSQL、Redis 和可选的 Ollama 使用命名卷保存数据

## 快速开始

1. 先在本地生成环境文件：

   ```bash
   cp .env.example .env
   ```

2. 按你的模型接入方式修改 `.env`。

   默认情况下，`config/models.yaml` 会把抽取和运行时任务路由到 OpenAI 兼容接口，把向量任务路由到 Ollama。示例里的 `OLLAMA_BASE_URL` 使用 `http://ollama:11434/v1`，这样 Docker 容器能直接访问可选的 Ollama 服务。

3. 启动标准栈：

   ```bash
   docker compose up --build
   ```

4. 如果要连同本地 Ollama 一起启动：

   ```bash
   docker compose --profile local-llm up --build
   ```

   如果你不是用 Docker 跑 API，而是直接在宿主机本地运行，再把 `OLLAMA_BASE_URL` 改回 `http://localhost:11434/v1`。

5. 启动后可访问这些入口：

   - API 健康检查：`http://localhost:8000/healthz`
   - 系统健康检查：`http://localhost:8000/api/v1/system/health`
   - Demo 首页：`http://localhost:8000/demo`
   - 角色画像 Demo：`http://localhost:8000/demo/portrait`
   - 角色对话 Demo：`http://localhost:8000/demo/chat`

停止服务：

```bash
docker compose down
```

## 示例资产

仓库内附带了一组岳不群示例资产：

- [examples/yue-buqun/portrait.json](examples/yue-buqun/portrait.json)：完整的角色画像抽取示例，结构符合项目 schema
- [examples/yue-buqun/memories.json](examples/yue-buqun/memories.json)：由同一示例整理出的记忆记录，便于快速查看最终落库形态

这组示例用于演示产物结构和联调流程，替代直接上传本地原始文本。

## 目录说明

- `src/camo`：API、抽取流程、运行时逻辑、模型适配和持久层代码
- `prompts`：提示词模板和 JSON Schema
- `migrations`：Alembic 迁移文件
- `docker`：容器启动脚本
- `config`：共享模型路由配置
- `tests`：自动化测试
- `examples`：示例输出资产
- `data`：Docker 挂载的本地运行数据目录

## 不应上传的本地文件

仓库已经忽略常见的本地专用配置，避免误传：

- `.env` 和 `.env.*`（保留 `.env.example`）
- `.claude/`
- `.vscode/`、`.idea/` 这类编辑器配置
- `docker-compose.override.yml`、`config/*.local.yaml` 这类本地覆盖配置

## 当前状态

目前已经包含核心 API、Docker 编排、提示词 schema、数据库迁移和 Demo 页面，可以直接在本地拉起并继续迭代。

## 开源协议

本项目采用 MIT 开源协议，详见 [LICENSE](LICENSE)。
