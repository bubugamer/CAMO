from __future__ import annotations

from camo.db import models as _models  # noqa: F401
from camo.db.base import Base


def test_metadata_contains_expected_schema_tables() -> None:
    assert set(Base.metadata.tables) == {
        "camo.character_versions",
        "camo.characters",
        "camo.events",
        "camo.feedbacks",
        "camo.llm_call_logs",
        "camo.memories",
        "camo.projects",
        "camo.relationships",
        "camo.reviews",
        "camo.text_segments",
        "camo.text_sources",
    }
