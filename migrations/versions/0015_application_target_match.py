"""The application's personal readiness target (PRD F10.6, C.2)

Revision ID: 0015
Revises: 0014
Create Date: 2026-09-28

Strictly additive: `applications.target_match` is the Job Match the user decided is
good enough for this posting (F10.6). It lives on the application, not on an attempt,
because it is the user's own stopping point for that posting and outlives any single
file. Nullable — no target set is the normal state, and the readiness condition then
falls back to the stability band. Migrated before the code is pushed, as `0014` was.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("applications", sa.Column("target_match", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("applications", "target_match")
