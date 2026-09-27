"""drop tracks.headline and tracks.summary

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-27

The contract half of the expand/contract change `0009` opened (PRD §6): the two
legacy single-language text slots that `headline_es/en` and `summary_es_id/en_id`
superseded are dropped here.

**Run only after the E.1 code is deployed.** A revision that still maps the columns
would fail on every track query once they are gone — SQLAlchemy selects the mapped
attributes by name. Between the push of E.1 and this migration, `/health/schema`
reports `0012 != 0011`; that window is expected and harmless, because no code reads
the two columns any more.

The downgrade re-adds both columns, nullable and empty: the data they held is not
restored, and cannot be — `0009`'s backfill copied it into the per-language columns
and the summary pool, which is where it lives now.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("tracks", "summary")
    op.drop_column("tracks", "headline")


def downgrade() -> None:
    op.add_column("tracks", sa.Column("headline", sa.String(length=200), nullable=True))
    op.add_column("tracks", sa.Column("summary", sa.Text(), nullable=True))
