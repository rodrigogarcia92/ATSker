"""applications: one analysis, its report, and eventually its outcome

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-16

Transcribed from the model metadata's PostgreSQL DDL and verified against it.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "applications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("company", sa.String(length=200), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=True),
        sa.Column("jd_text", sa.Text(), nullable=False),
        sa.Column("jd_hash", sa.String(length=80), nullable=False),
        sa.Column("report", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("weights_version", sa.String(length=20), nullable=False),
        sa.Column("prompt_versions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("token_cost_usd", sa.Numeric(precision=10, scale=6), nullable=False),
        sa.Column("outcome", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_applications_jd_hash", "applications", ["jd_hash"])
    op.create_index("ix_applications_profile_id", "applications", ["profile_id"])


def downgrade() -> None:
    op.drop_index("ix_applications_profile_id", table_name="applications")
    op.drop_index("ix_applications_jd_hash", table_name="applications")
    op.drop_table("applications")
