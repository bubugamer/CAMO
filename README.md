[English](README.md) | [中文](README-zh.md)

# CAMO

CAMO (Character Modeling & Simulation Base) turns unstructured text into reusable character assets that can be indexed, profiled, stored, and used at runtime.

## What It Includes

- A FastAPI service for project setup, text import, entity indexing, character portrait extraction, and runtime chat
- PostgreSQL with `pgvector` for structured storage and retrieval
- Redis for runtime cache and working memory support
- Prompt templates and model routing config for extraction and chat
- Demo pages for inspecting portraits and chatting with characters
- A sample asset package for Yue Buqun in [examples/yue-buqun](examples/yue-buqun)

## Docker Stack

The Docker setup is built around `docker-compose.yml`:

- `api`: builds from the local `Dockerfile`, runs Alembic migrations on startup, then launches the API on port `8000`
- `postgres`: uses `pgvector/pgvector:pg16` as the primary database
- `redis`: provides cache and short-lived runtime state
- `ollama`: optional local model service, enabled only when you start the `local-llm` profile

Runtime data is handled in two ways:

- `./data` is mounted into the API container at `/app/data`
- named volumes keep PostgreSQL, Redis, and optional Ollama data across restarts

## Quick Start

1. Create a local environment file:

   ```bash
   cp .env.example .env
   ```

2. Update `.env` with the model endpoint and keys you want to use.

   By default, `config/models.yaml` points the extraction and runtime tasks to an OpenAI-compatible provider and embeddings to Ollama. The sample `.env.example` uses `http://ollama:11434/v1` so Docker containers can reach the optional Ollama service directly.

3. Start the standard stack:

   ```bash
   docker compose up --build
   ```

4. Start with local Ollama included:

   ```bash
   docker compose --profile local-llm up --build
   ```

   If you run the app outside Docker and want to use a host-installed Ollama instead, change `OLLAMA_BASE_URL` to `http://localhost:11434/v1`.

5. Open the common entry points:

   - API health: `http://localhost:8000/healthz`
   - System health: `http://localhost:8000/api/v1/system/health`
   - Demo hub: `http://localhost:8000/demo`
   - Portrait demo: `http://localhost:8000/demo/portrait`
   - Chat demo: `http://localhost:8000/demo/chat`

To stop the stack:

```bash
docker compose down
```

## Example Assets

The repository includes a small example package for Yue Buqun:

- [examples/yue-buqun/portrait.json](examples/yue-buqun/portrait.json): a full portrait extraction example that follows the project schema
- [examples/yue-buqun/memories.json](examples/yue-buqun/memories.json): normalized memory records derived from the same example

These files are intended as reference assets for demos, inspection, and downstream integration work. They are included instead of committing raw local source texts.

## Repository Layout

- `src/camo`: API, extraction pipeline, runtime logic, model adapters, and persistence code
- `prompts`: prompt templates and JSON schemas
- `migrations`: Alembic migration files
- `docker`: container startup scripts
- `config`: shared model routing configuration
- `tests`: automated checks
- `examples`: sample output assets
- `data`: local runtime data directory mounted into Docker

## Local-Only Files

Local machine settings should stay out of Git. The repository ignores common local-only files such as:

- `.env` and `.env.*` (except `.env.example`)
- `.claude/`
- editor folders like `.vscode/` and `.idea/`
- local override files such as `docker-compose.override.yml` and `config/*.local.yaml`

## Status

The core API, Docker stack, prompt schemas, migrations, and demo surfaces are present. The project is ready for local bring-up and iterative feature work.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
