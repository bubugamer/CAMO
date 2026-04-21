"""create core schema

Revision ID: 20260413_0001
Revises:
Create Date: 2026-04-13 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql


revision = "20260413_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS camo")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "projects",
        sa.Column("project_id", sa.Text(), primary_key=True),
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'active'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        schema="camo",
    )

    op.create_table(
        "text_sources",
        sa.Column("source_id", sa.Text(), primary_key=True),
        sa.Column(
            "project_id",
            sa.Text(),
            sa.ForeignKey("camo.projects.project_id"),
            nullable=False,
        ),
        sa.Column("filename", sa.Text(), nullable=True),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=True),
        sa.Column("char_count", sa.Integer(), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        schema="camo",
    )

    op.create_table(
        "text_segments",
        sa.Column("segment_id", sa.Text(), primary_key=True),
        sa.Column(
            "source_id",
            sa.Text(),
            sa.ForeignKey("camo.text_sources.source_id"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("chapter", sa.Text(), nullable=True),
        sa.Column("round", sa.Integer(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("raw_offset", sa.Integer(), nullable=False),
        sa.Column("char_count", sa.Integer(), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        schema="camo",
    )

    op.create_table(
        "characters",
        sa.Column("character_id", sa.Text(), primary_key=True),
        sa.Column(
            "project_id",
            sa.Text(),
            sa.ForeignKey("camo.projects.project_id"),
            nullable=False,
        ),
        sa.Column(
            "schema_version",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'0.2'"),
        ),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'draft'"),
        ),
        sa.Column(
            "index",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("core", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("facet", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        schema="camo",
    )

    op.create_table(
        "relationships",
        sa.Column("relationship_id", sa.Text(), primary_key=True),
        sa.Column(
            "project_id",
            sa.Text(),
            sa.ForeignKey("camo.projects.project_id"),
            nullable=False,
        ),
        sa.Column(
            "schema_version",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'0.2'"),
        ),
        sa.Column(
            "source_id",
            sa.Text(),
            sa.ForeignKey("camo.characters.character_id"),
            nullable=False,
        ),
        sa.Column(
            "target_id",
            sa.Text(),
            sa.ForeignKey("camo.characters.character_id"),
            nullable=False,
        ),
        sa.Column("relation_category", sa.Text(), nullable=False),
        sa.Column("relation_subtype", sa.Text(), nullable=False),
        sa.Column(
            "public_state",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("hidden_state", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "timeline",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "source_segments",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        schema="camo",
    )

    op.create_table(
        "events",
        sa.Column("event_id", sa.Text(), primary_key=True),
        sa.Column(
            "project_id",
            sa.Text(),
            sa.ForeignKey("camo.projects.project_id"),
            nullable=False,
        ),
        sa.Column(
            "schema_version",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'0.2'"),
        ),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("timeline_pos", sa.Integer(), nullable=True),
        sa.Column(
            "participants",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column("location", sa.Text(), nullable=True),
        sa.Column("emotion_valence", sa.Text(), nullable=True),
        sa.Column(
            "source_segments",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        schema="camo",
    )

    op.create_table(
        "memories",
        sa.Column("memory_id", sa.Text(), primary_key=True),
        sa.Column(
            "character_id",
            sa.Text(),
            sa.ForeignKey("camo.characters.character_id"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            sa.Text(),
            sa.ForeignKey("camo.projects.project_id"),
            nullable=False,
        ),
        sa.Column(
            "schema_version",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'0.2'"),
        ),
        sa.Column("memory_type", sa.Text(), nullable=False),
        sa.Column(
            "salience",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0.5"),
        ),
        sa.Column(
            "recency",
            sa.Float(),
            nullable=False,
            server_default=sa.text("1.0"),
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "source_event_id",
            sa.Text(),
            sa.ForeignKey("camo.events.event_id"),
            nullable=True,
        ),
        sa.Column(
            "related_character_ids",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column("emotion_valence", sa.Text(), nullable=True),
        sa.Column(
            "source_segments",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column("embedding", Vector(dim=768), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        schema="camo",
    )

    op.create_table(
        "character_versions",
        sa.Column("version_id", sa.Text(), primary_key=True),
        sa.Column(
            "character_id",
            sa.Text(),
            sa.ForeignKey("camo.characters.character_id"),
            nullable=False,
        ),
        sa.Column("version_num", sa.Integer(), nullable=False),
        sa.Column(
            "snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("diff", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_by", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("character_id", "version_num", name="uq_character_versions_character_id_version_num"),
        schema="camo",
    )

    op.create_table(
        "reviews",
        sa.Column("review_id", sa.Text(), primary_key=True),
        sa.Column("target_type", sa.Text(), nullable=False),
        sa.Column("target_id", sa.Text(), nullable=False),
        sa.Column("diff", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("reviewer", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        schema="camo",
    )

    op.create_table(
        "feedbacks",
        sa.Column("feedback_id", sa.Text(), primary_key=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("target_type", sa.Text(), nullable=False),
        sa.Column("target_id", sa.Text(), nullable=False),
        sa.Column("rating", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "linked_assets",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column("suggested_action", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        schema="camo",
    )

    op.create_table(
        "llm_call_logs",
        sa.Column("log_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("task", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        schema="camo",
    )

    op.create_index("idx_segments_source", "text_segments", ["source_id", "position"], schema="camo")
    op.create_index("idx_characters_project", "characters", ["project_id"], schema="camo")
    op.create_index(
        "idx_relationships_source",
        "relationships",
        ["source_id"],
        schema="camo",
    )
    op.create_index(
        "idx_relationships_target",
        "relationships",
        ["target_id"],
        schema="camo",
    )
    op.create_index(
        "idx_relationships_project",
        "relationships",
        ["project_id"],
        schema="camo",
    )
    op.create_index(
        "idx_events_project",
        "events",
        ["project_id", "timeline_pos"],
        schema="camo",
    )
    op.create_index(
        "idx_memories_character",
        "memories",
        ["character_id", "memory_type"],
        schema="camo",
    )
    op.create_index("idx_memories_project", "memories", ["project_id"], schema="camo")
    op.create_index(
        "idx_characters_index",
        "characters",
        ["index"],
        schema="camo",
        postgresql_using="gin",
    )
    op.create_index(
        "idx_characters_core",
        "characters",
        ["core"],
        schema="camo",
        postgresql_using="gin",
    )
    op.create_index(
        "idx_memories_embedding",
        "memories",
        ["embedding"],
        schema="camo",
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
        postgresql_with={"m": 16, "ef_construction": 64},
    )


def downgrade() -> None:
    op.drop_index("idx_memories_embedding", table_name="memories", schema="camo")
    op.drop_index("idx_characters_core", table_name="characters", schema="camo")
    op.drop_index("idx_characters_index", table_name="characters", schema="camo")
    op.drop_index("idx_memories_project", table_name="memories", schema="camo")
    op.drop_index("idx_memories_character", table_name="memories", schema="camo")
    op.drop_index("idx_events_project", table_name="events", schema="camo")
    op.drop_index("idx_relationships_project", table_name="relationships", schema="camo")
    op.drop_index("idx_relationships_target", table_name="relationships", schema="camo")
    op.drop_index("idx_relationships_source", table_name="relationships", schema="camo")
    op.drop_index("idx_characters_project", table_name="characters", schema="camo")
    op.drop_index("idx_segments_source", table_name="text_segments", schema="camo")

    op.drop_table("llm_call_logs", schema="camo")
    op.drop_table("feedbacks", schema="camo")
    op.drop_table("reviews", schema="camo")
    op.drop_table("character_versions", schema="camo")
    op.drop_table("memories", schema="camo")
    op.drop_table("events", schema="camo")
    op.drop_table("relationships", schema="camo")
    op.drop_table("characters", schema="camo")
    op.drop_table("text_segments", schema="camo")
    op.drop_table("text_sources", schema="camo")
    op.drop_table("projects", schema="camo")
    op.execute("DROP SCHEMA IF EXISTS camo")
