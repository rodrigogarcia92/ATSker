"""Latency in the model-call ledger (PRD §6, §7, N8.13)

Revision ID: 0017
Revises: 0015
Create Date: 2026-10-08

Strictly additive: `llm_calls.latency_ms` is the wall-clock time of the provider request
whose answer the row records. Nullable, no default: rows written before this migration
have no latency and the cost script shows a dash for them. `0016` was withdrawn and is
unused, so this revision follows `0015`. Migrated before the code is pushed.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("llm_calls", sa.Column("latency_ms", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("llm_calls", "latency_ms")
