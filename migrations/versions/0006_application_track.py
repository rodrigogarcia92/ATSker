"""applications.track_id: the track an analysis was scored with (PRD F4, §6)

Revision ID: 0006
Revises: 0004
Create Date: 2026-09-20

`0005` belongs to the N1b handoff (`llm_calls.degenerate`), which also branches
from `0004`; whichever of the two lands second is rebased onto the other or joined
by a merge revision. Both are additive, neither reads the other's column, and
neither backfills anything, so the order they are applied in does not matter.

Transcribed from the model metadata's PostgreSQL DDL, as `0004` was. Nullable with
`ON DELETE SET NULL`: an analysis keeps its report — and the track name it recorded
inside that report — when the track it used is deactivated or removed, and rows
written before this column existed simply carry no track. Safe to apply before the
code that reads it.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "applications",
        sa.Column(
            "track_id",
            sa.Uuid(),
            sa.ForeignKey("tracks.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_applications_track_id", "applications", ["track_id"])


def downgrade() -> None:
    op.drop_index("ix_applications_track_id", table_name="applications")
    op.drop_column("applications", "track_id")
