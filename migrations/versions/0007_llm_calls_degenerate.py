"""llm_calls.degenerate: an answer the cache must not serve again (PRD F2.3.1)

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-21

Revision `0005` is intentionally absent: it was reserved for this column and never
written, and the number is skipped permanently rather than reused.

Additive and safe to apply before the code that reads it: the column has a server
default of `false`, so every row written by the current code keeps today's meaning
("this answer may be served from the cache") while the new code learns to mark the
ones it must not. No backfill, no data migration, and nothing here reads or rewrites
an existing row.

Transcribed from the model metadata's PostgreSQL DDL, as `0004` was.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "llm_calls",
        sa.Column("degenerate", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("llm_calls", "degenerate")