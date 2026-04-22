"""rename entity payload columns to character payload columns

Revision ID: 20260421_0002
Revises: 20260413_0001
Create Date: 2026-04-21 00:00:00
"""

from __future__ import annotations

from alembic import op


revision = "20260421_0002"
down_revision = "20260413_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('ALTER TABLE camo.characters RENAME COLUMN "index" TO character_index')
    op.execute("ALTER TABLE camo.characters RENAME COLUMN core TO character_core")
    op.execute("ALTER TABLE camo.characters RENAME COLUMN facet TO character_facet")
    op.execute("ALTER INDEX camo.idx_characters_index RENAME TO idx_characters_character_index")
    op.execute("ALTER INDEX camo.idx_characters_core RENAME TO idx_characters_character_core")


def downgrade() -> None:
    op.execute("ALTER INDEX camo.idx_characters_character_core RENAME TO idx_characters_core")
    op.execute("ALTER INDEX camo.idx_characters_character_index RENAME TO idx_characters_index")
    op.execute("ALTER TABLE camo.characters RENAME COLUMN character_facet TO facet")
    op.execute("ALTER TABLE camo.characters RENAME COLUMN character_core TO core")
    op.execute("ALTER TABLE camo.characters RENAME COLUMN character_index TO \"index\"")
