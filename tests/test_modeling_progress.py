from __future__ import annotations

import asyncio
from types import SimpleNamespace

from camo.db.models import Character
from camo.runtime.session_store import InMemorySessionStore
from camo.tasks.modeling import run_project_modeling


class _TrackingStore(InMemorySessionStore):
    def __init__(self) -> None:
        super().__init__()
        self.stage_history: list[str] = []

    async def patch_job_status(self, job_id: str, **updates):
        if updates.get("stage"):
            self.stage_history.append(updates["stage"])
        return await super().patch_job_status(job_id, **updates)

    async def save_job_status(self, job_id: str, payload):
        if payload.get("stage"):
            self.stage_history.append(payload["stage"])
        await super().save_job_status(job_id, payload)


class _FakeSessionFactory:
    def __call__(self):
        return self

    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        return False


def test_modeling_progress_reports_new_stages(monkeypatch) -> None:
    store = _TrackingStore()
    character = Character(
        character_id="char_demo",
        project_id="proj_demo",
        character_index={"name": "岳不群", "aliases": []},
    )

    async def fake_get_project(session, project_id):
        return SimpleNamespace(project_id=project_id)

    async def fake_list_text_sources(session, project_id):
        return [SimpleNamespace(source_id="src_demo", source_type="novel")]

    async def fake_run_character_index(**kwargs):
        return [character], 1

    async def fake_list_characters(session, project_id):
        return [character]

    async def fake_run_project_character_portrait(**kwargs):
        progress_callback = kwargs.get("progress_callback")
        if progress_callback is not None:
            await progress_callback("pass2_chapter_aggregate", "第一回")
            await progress_callback("pass2_book_resolve", None)
        return character, [], [], [], 1, ["seg_1"]

    async def fake_create_character_version(*args, **kwargs):
        return None

    async def fake_create_review(*args, **kwargs):
        return None

    monkeypatch.setattr("camo.tasks.modeling.get_project", fake_get_project)
    monkeypatch.setattr("camo.tasks.modeling.list_text_sources", fake_list_text_sources)
    monkeypatch.setattr("camo.tasks.modeling.run_character_index", fake_run_character_index)
    monkeypatch.setattr("camo.tasks.modeling.list_characters", fake_list_characters)
    monkeypatch.setattr("camo.tasks.modeling.run_project_character_portrait", fake_run_project_character_portrait)
    monkeypatch.setattr("camo.tasks.modeling.create_character_version", fake_create_character_version)
    monkeypatch.setattr("camo.tasks.modeling.create_review", fake_create_review)

    async def run() -> dict:
        await store.connect()
        await store.save_job_status("job_demo", {"job_id": "job_demo", "project_id": "proj_demo", "status": "queued"})
        return await run_project_modeling(
            session_factory=_FakeSessionFactory(),
            model_adapter=object(),
            store=store,
            job_id="job_demo",
            project_id="proj_demo",
            max_segments_per_chapter=2,
        )

    result = asyncio.run(run())

    assert result["stage"] == "completed"
    ordered_unique_stages = list(dict.fromkeys(store.stage_history))
    assert ordered_unique_stages == [
        "pass1_extract",
        "pass1_disambiguate",
        "pass2_chapter_aggregate",
        "pass2_book_resolve",
        "persist_assets",
        "review_seed",
        "completed",
    ]
