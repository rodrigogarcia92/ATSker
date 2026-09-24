"""bullets.source_resume_id and llm_calls.profile_id: provenance and ownership (PRD F2.8)

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-23

Two nullable, indexed, `ON DELETE SET NULL` columns. Strictly additive and safe
before the code that reads it: which CV created a bullet — F2.8's "only this CV
contributed" option deletes by this column and never touches a bullet whose
provenance is unknown — and whose model call a ledger row was, so "Eliminar todo"
can redact that profile's personal content. Rows written before either column
existed simply carry no value; F2.8 says the confirmation screen says so and
`llm_costs.py purge --hash` remains the tool for those.

One backfill, set-based like `0004`'s — no Python-side reads, so
`alembic upgrade --sql` renders the whole migration for inspection before it runs.
`bullets.source_resume_id` takes the résumé named by the bullet's *oldest*
revision with a non-null `resume_id`: the earliest evidence of where the bullet
came from. A bullet no such revision names keeps NULL.

Transcribed from the model metadata's PostgreSQL DDL, as `0004` was.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "bullets",
        sa.Column(
            "source_resume_id",
            sa.Uuid(),
            sa.ForeignKey("resumes.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_bullets_source_resume_id", "bullets", ["source_resume_id"])

    op.add_column(
        "llm_calls",
        sa.Column(
            "profile_id",
            sa.Uuid(),
            sa.ForeignKey("profiles.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_llm_calls_profile_id", "llm_calls", ["profile_id"])

    op.execute(
        """
        UPDATE bullets SET source_resume_id = (
            SELECT br.resume_id FROM bullet_revisions br
            WHERE br.bullet_id = bullets.id AND br.resume_id IS NOT NULL
            ORDER BY br.created_at, br.id
            LIMIT 1
        ) WHERE EXISTS (
            SELECT 1 FROM bullet_revisions br
            WHERE br.bullet_id = bullets.id AND br.resume_id IS NOT NULL
        )
        """
    )


def downgrade() -> None:
    op.drop_index("ix_llm_calls_profile_id", table_name="llm_calls")
    op.drop_column("llm_calls", "profile_id")
    op.drop_index("ix_bullets_source_resume_id", table_name="bullets")
    op.drop_column("bullets", "source_resume_id")
