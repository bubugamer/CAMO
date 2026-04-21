from __future__ import annotations

from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Index, Integer, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from camo.db.base import Base


EMPTY_JSON = text("'{}'::jsonb")
EMPTY_JSON_ARRAY = text("'[]'::jsonb")
EMPTY_TEXT_ARRAY = text("'{}'::text[]")


class Project(Base):
    __tablename__ = "projects"

    project_id: Mapped[str] = mapped_column(Text, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    config: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=EMPTY_JSON,
    )
    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'active'"),
    )
    created_at: Mapped[Any] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[Any] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class TextSource(Base):
    __tablename__ = "text_sources"

    source_id: Mapped[str] = mapped_column(Text, primary_key=True)
    project_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("projects.project_id"),
        nullable=False,
    )
    filename: Mapped[str | None] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    file_path: Mapped[str | None] = mapped_column(Text)
    char_count: Mapped[int | None] = mapped_column(Integer)
    source_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=EMPTY_JSON,
    )
    created_at: Mapped[Any] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class TextSegment(Base):
    __tablename__ = "text_segments"
    __table_args__ = (
        Index("idx_segments_source", "source_id", "position"),
    )

    segment_id: Mapped[str] = mapped_column(Text, primary_key=True)
    source_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("text_sources.source_id"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    chapter: Mapped[str | None] = mapped_column(Text)
    round: Mapped[int | None] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    raw_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    char_count: Mapped[int] = mapped_column(Integer, nullable=False)
    segment_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=EMPTY_JSON,
    )
    created_at: Mapped[Any] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class Character(Base):
    __tablename__ = "characters"
    __table_args__ = (
        Index("idx_characters_project", "project_id"),
        Index("idx_characters_index", "index", postgresql_using="gin"),
        Index("idx_characters_core", "core", postgresql_using="gin"),
    )

    character_id: Mapped[str] = mapped_column(Text, primary_key=True)
    project_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("projects.project_id"),
        nullable=False,
    )
    schema_version: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'0.2'"),
    )
    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'draft'"),
    )
    index_payload: Mapped[dict[str, Any]] = mapped_column("index", JSONB, nullable=False)
    core: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    facet: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[Any] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[Any] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class Relationship(Base):
    __tablename__ = "relationships"
    __table_args__ = (
        Index("idx_relationships_source", "source_id"),
        Index("idx_relationships_target", "target_id"),
        Index("idx_relationships_project", "project_id"),
    )

    relationship_id: Mapped[str] = mapped_column(Text, primary_key=True)
    project_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("projects.project_id"),
        nullable=False,
    )
    schema_version: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'0.2'"),
    )
    source_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("characters.character_id"),
        nullable=False,
    )
    target_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("characters.character_id"),
        nullable=False,
    )
    relation_category: Mapped[str] = mapped_column(Text, nullable=False)
    relation_subtype: Mapped[str] = mapped_column(Text, nullable=False)
    public_state: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    hidden_state: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    timeline: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=EMPTY_JSON_ARRAY,
    )
    source_segments: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        server_default=EMPTY_TEXT_ARRAY,
    )
    confidence: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[Any] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[Any] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        Index("idx_events_project", "project_id", "timeline_pos"),
    )

    event_id: Mapped[str] = mapped_column(Text, primary_key=True)
    project_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("projects.project_id"),
        nullable=False,
    )
    schema_version: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'0.2'"),
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    timeline_pos: Mapped[int | None] = mapped_column(Integer)
    participants: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        server_default=EMPTY_TEXT_ARRAY,
    )
    location: Mapped[str | None] = mapped_column(Text)
    emotion_valence: Mapped[str | None] = mapped_column(Text)
    source_segments: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        server_default=EMPTY_TEXT_ARRAY,
    )
    created_at: Mapped[Any] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class Memory(Base):
    __tablename__ = "memories"
    __table_args__ = (
        Index("idx_memories_character", "character_id", "memory_type"),
        Index("idx_memories_project", "project_id"),
        Index(
            "idx_memories_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
            postgresql_with={"m": 16, "ef_construction": 64},
        ),
    )

    memory_id: Mapped[str] = mapped_column(Text, primary_key=True)
    character_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("characters.character_id"),
        nullable=False,
    )
    project_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("projects.project_id"),
        nullable=False,
    )
    schema_version: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'0.2'"),
    )
    memory_type: Mapped[str] = mapped_column(Text, nullable=False)
    salience: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        server_default=text("0.5"),
    )
    recency: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        server_default=text("1.0"),
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_event_id: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey("events.event_id"),
    )
    related_character_ids: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        server_default=EMPTY_TEXT_ARRAY,
    )
    emotion_valence: Mapped[str | None] = mapped_column(Text)
    source_segments: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        server_default=EMPTY_TEXT_ARRAY,
    )
    embedding: Mapped[list[float] | None] = mapped_column(Vector(768))
    created_at: Mapped[Any] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class CharacterVersion(Base):
    __tablename__ = "character_versions"
    __table_args__ = (
        UniqueConstraint("character_id", "version_num", name="uq_character_versions_character_id_version_num"),
    )

    version_id: Mapped[str] = mapped_column(Text, primary_key=True)
    character_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("characters.character_id"),
        nullable=False,
    )
    version_num: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    diff: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_by: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[Any] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class Review(Base):
    __tablename__ = "reviews"

    review_id: Mapped[str] = mapped_column(Text, primary_key=True)
    target_type: Mapped[str] = mapped_column(Text, nullable=False)
    target_id: Mapped[str] = mapped_column(Text, nullable=False)
    diff: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    reviewer: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'pending'"),
    )
    note: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[Any | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[Any] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class Feedback(Base):
    __tablename__ = "feedbacks"

    feedback_id: Mapped[str] = mapped_column(Text, primary_key=True)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    target_type: Mapped[str] = mapped_column(Text, nullable=False)
    target_id: Mapped[str] = mapped_column(Text, nullable=False)
    rating: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)
    linked_assets: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        server_default=EMPTY_TEXT_ARRAY,
    )
    suggested_action: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[Any] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class LLMCallLog(Base):
    __tablename__ = "llm_call_logs"

    log_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    task: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[Any] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
