from __future__ import annotations

from copy import deepcopy
from typing import Any

from sqlalchemy.ext.asyncio import async_sessionmaker

from camo.db.queries.characters import get_character_by_id, list_characters
from camo.db.queries.projects import get_project
from camo.db.queries.reviews import create_review
from camo.db.queries.texts import list_text_sources
from camo.db.queries.versions import create_character_version
from camo.extraction.pass1 import run_character_index
from camo.extraction.pass2 import run_project_character_portrait
from camo.models.adapter import ModelAdapter
from camo.runtime.session_store import SessionStore


async def run_project_modeling(
    *,
    session_factory: async_sessionmaker,
    model_adapter: ModelAdapter,
    store: SessionStore,
    job_id: str,
    project_id: str,
    source_ids: list[str] | None = None,
    segment_limit: int | None = None,
    max_segments_per_chapter: int = 10,
) -> dict[str, Any]:
    async with session_factory() as session:
        project = await get_project(session, project_id)
        if project is None:
            payload = {
                "job_id": job_id,
                "project_id": project_id,
                "status": "failed",
                "progress": 1.0,
                "message": "Project not found",
                "stage": "failed",
                "stage_message": "Project not found",
                "current_source_id": None,
                "current_character_id": None,
                "current_chapter": None,
                "error": "Project not found",
            }
            await store.save_job_status(job_id, payload)
            return payload

        sources = await list_text_sources(session, project_id)
        if source_ids:
            source_filter = set(source_ids)
            sources = [item for item in sources if item.source_id in source_filter]
        await store.patch_job_status(
            job_id,
            status="running",
            progress=0.02,
            message="Running character index extraction",
            stage="pass1_extract",
            stage_message="Running character index extraction",
            current_source_id=None,
            current_character_id=None,
            current_chapter=None,
        )

        total_sources = max(1, len(sources))
        for index, source in enumerate(sources, start=1):
            await store.patch_job_status(
                job_id,
                stage="pass1_extract",
                stage_message=f"Extracting source {index}/{total_sources}",
                current_source_id=source.source_id,
                current_character_id=None,
                current_chapter=None,
            )
            await run_character_index(
                session=session,
                model_adapter=model_adapter,
                project_id=project_id,
                source_id=source.source_id,
                source_type=source.source_type,
                segment_limit=segment_limit,
            )
            await store.patch_job_status(
                job_id,
                stage="pass1_disambiguate",
                stage_message=f"Disambiguated source {index}/{total_sources}",
                processed_sources=index,
                progress=0.05 + 0.4 * (index / total_sources),
                message=f"Indexed {index}/{total_sources} text source(s)",
                current_source_id=source.source_id,
            )

        characters = await list_characters(session, project_id)
        total_characters = max(1, len(characters))
        await store.patch_job_status(
            job_id,
            message="Aggregating portraits and memories",
            character_count=len(characters),
            current_source_id=None,
        )
        for index, character in enumerate(characters, start=1):
            aliases = character.character_index.get("aliases", [])
            await store.patch_job_status(
                job_id,
                stage="pass2_chapter_aggregate",
                stage_message=f"Aggregating chapter evidence for {character.character_id}",
                current_character_id=character.character_id,
                current_chapter=None,
            )

            async def portrait_progress(stage: str, chapter_key: str | None) -> None:
                await store.patch_job_status(
                    job_id,
                    stage=stage,
                    stage_message=(
                        f"Aggregating chapter {chapter_key}" if stage == "pass2_chapter_aggregate" and chapter_key else "Resolving book-level conflicts"
                    ),
                    current_character_id=character.character_id,
                    current_chapter=chapter_key,
                )

            updated, _, _, _, _, _ = await run_project_character_portrait(
                session=session,
                model_adapter=model_adapter,
                project_id=project_id,
                name=character.character_index.get("name", ""),
                aliases=aliases,
                max_segments_per_chapter=max_segments_per_chapter,
                progress_callback=portrait_progress,
            )
            await store.patch_job_status(
                job_id,
                stage="persist_assets",
                stage_message=f"Persisting assets for {updated.character_id}",
                current_character_id=updated.character_id,
                current_chapter=None,
            )
            await create_character_version(
                session,
                character_id=updated.character_id,
                snapshot=build_character_snapshot(updated),
                created_by="modeling_pipeline",
                note="Automated modeling output",
            )
            await store.patch_job_status(
                job_id,
                stage="review_seed",
                stage_message=f"Creating review seed for {updated.character_id}",
                current_character_id=updated.character_id,
                current_chapter=None,
            )
            await create_review(
                session,
                target_type="character_asset",
                target_id=updated.character_id,
                status="pending",
                note="Generated from modeling pipeline",
            )
            await store.patch_job_status(
                job_id,
                processed_characters=index,
                progress=0.5 + 0.5 * (index / total_characters),
                message=f"Aggregated {index}/{total_characters} character portrait(s)",
                stage="review_seed",
                stage_message=f"Review seeded for {updated.character_id}",
                current_character_id=updated.character_id,
                current_chapter=None,
            )

        payload = {
            "job_id": job_id,
            "project_id": project_id,
            "status": "completed",
            "progress": 1.0,
            "message": "Modeling completed",
            "stage": "completed",
            "stage_message": "Modeling completed",
            "processed_sources": len(sources),
            "processed_characters": len(characters),
            "character_count": len(characters),
            "current_source_id": None,
            "current_character_id": None,
            "current_chapter": None,
            "error": None,
        }
        await store.save_job_status(job_id, payload)
        return payload


async def write_runtime_memory(
    *,
    session_factory: async_sessionmaker,
    model_adapter: ModelAdapter,
    payload: dict[str, Any],
) -> None:
    from uuid import uuid4

    from camo.db.queries.memories import upsert_memories

    content = str(payload.get("response", {}).get("content", "")).strip()
    if not content:
        return

    related_character_ids = [
        item
        for item in payload.get("participants", [])
        if item and item != payload.get("character_id")
    ]
    try:
        embedding_result = await model_adapter.embed([content])
        embedding = embedding_result.vectors[0] if embedding_result.vectors else None
    except Exception:
        embedding = None

    async with session_factory() as session:
        await upsert_memories(
            session,
            [
                {
                    "memory_id": f"mem_{uuid4().hex[:12]}",
                    "character_id": payload["character_id"],
                    "project_id": payload["project_id"],
                    "schema_version": "0.2",
                    "memory_type": "episodic",
                    "salience": 0.72,
                    "recency": 1.0,
                    "content": content,
                    "source_event_id": None,
                    "related_character_ids": related_character_ids,
                    "emotion_valence": None,
                    "source_segments": [],
                    "embedding": embedding,
                }
            ],
        )


def build_character_snapshot(character) -> dict[str, Any]:
    return {
        "character_index": deepcopy(character.character_index),
        "character_core": deepcopy(character.character_core),
        "character_facet": deepcopy(character.character_facet),
        "status": character.status,
    }


async def load_character_snapshot(session_factory: async_sessionmaker, character_id: str) -> dict[str, Any] | None:
    async with session_factory() as session:
        character = await get_character_by_id(session, character_id)
        if character is None:
            return None
        return build_character_snapshot(character)
