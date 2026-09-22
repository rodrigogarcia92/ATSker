"""track axes and standing risks (PRD F4, 2026-09-21; F6.1)

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-21

`tracks.organisation_kind` and `tracks.specialisation` are the two axes the
recommender will read: what kind of employer the track targets, and the role's own
axis. Free text, no enum anywhere in code (design principle 4), both optional.

`profiles.standing_risks` is what could work against an application before any
posting is read; F6.1's interpretation call weighs it. NOT NULL with existing rows:
add, backfill, then enforce — exactly as `0004` did for `profiles.skills`.

Additive and safe to apply before the code that reads it: the two track columns are
nullable and the new array defaults to an empty backfill, so every row written by the
current code keeps today's meaning. Transcribed DDL, as `0004` and `0007` were.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STRINGS = postgresql.ARRAY(sa.String(length=120))


def upgrade() -> None:
    op.add_column("tracks", sa.Column("organisation_kind", sa.String(length=60), nullable=True))
    op.add_column("tracks", sa.Column("specialisation", sa.String(length=60), nullable=True))

    op.add_column("profiles", sa.Column("standing_risks", _STRINGS, nullable=True))
    op.execute("UPDATE profiles SET standing_risks = '{}' WHERE standing_risks IS NULL")
    op.alter_column("profiles", "standing_risks", nullable=False, existing_type=_STRINGS)


def downgrade() -> None:
    op.drop_column("profiles", "standing_risks")
    op.drop_column("tracks", "specialisation")
    op.drop_column("tracks", "organisation_kind")
