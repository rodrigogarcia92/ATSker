"""The account's theme (PRD §12.6, dark mode)

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-27

Additive: one column, `users.ui_theme` — "light" or "dark" — with every existing account
defaulting to "light", the design's default. Batch mode, as 0018: identical DDL on PostgreSQL
and on SQLite.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(
            sa.Column("ui_theme", sa.String(5), nullable=False, server_default="light")
        )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("ui_theme")
