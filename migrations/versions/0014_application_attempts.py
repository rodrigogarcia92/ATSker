"""Application attempts (PRD F10, A8)

Revision ID: 0014
Revises: 0013
Create Date: 2026-09-28

Strictly additive (F10.8, amended by A8). Two things arrive together because they are
one feature's shape:

* `application_attempts` — one test of an edited CV against a stored analysis. Per the
  spec's column list plus A8: `status` (running/done/failed) and `error` are added, and
  the partial unique index that keeps at most one `is_sent` per application carries
  both `postgresql_where` and `sqlite_where` so it holds in production and in the
  offline tests. No file bytes are ever stored (A5).
* `applications.sent_attempt_id` — a nullable FK to the attempt marked as sent,
  `ON DELETE SET NULL`, so deleting the attempt cannot take the analysis with it.

Nothing is dropped and nothing is backfilled, so **the database is migrated before the
code is pushed** (A8). Column types mirror the models (`sa.Uuid`, a JSON variant) so the
same DDL runs against PostgreSQL and against the SQLite the tests build the schema in.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# JSONB where the dialect has it, plain JSON in the offline tests — the same variant
# the models use, so the migration runs wherever the models do.
_JsonDoc = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.create_table(
        "application_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column("file_sha256", sa.String(length=64), nullable=True),
        sa.Column("file_format", sa.String(length=10), nullable=True),
        sa.Column("lang", sa.String(length=5), nullable=True),
        sa.Column("report", _JsonDoc, nullable=True),
        sa.Column("job_match", sa.Integer(), nullable=True),
        sa.Column("ceiling_low", sa.Integer(), nullable=True),
        sa.Column("ceiling_high", sa.Integer(), nullable=True),
        sa.Column("weights_version", sa.String(length=20), nullable=True),
        sa.Column("vocabulary_hash", sa.String(length=80), nullable=True),
        sa.Column("prompt_versions", _JsonDoc, nullable=True),
        sa.Column("token_cost_usd", sa.Numeric(precision=10, scale=6), nullable=False),
        sa.Column(
            "is_sent", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "status", sa.String(length=10), nullable=False, server_default=sa.text("'running'")
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_application_attempts_application_id", "application_attempts", ["application_id"]
    )
    op.create_index(
        "ix_application_attempts_profile_id", "application_attempts", ["profile_id"]
    )
    # F10.8: at most one sent attempt per application. The partial predicate is spelled
    # for both dialects (A8), so the constraint holds in production and offline alike.
    op.create_index(
        "uq_application_attempt_sent",
        "application_attempts",
        ["application_id"],
        unique=True,
        postgresql_where=sa.text("is_sent"),
        sqlite_where=sa.text("is_sent"),
    )

    # Batch mode: identical DDL on PostgreSQL, and on SQLite it recreates the table,
    # which is the only way to add a foreign-key-bearing column there (A8 keeps the
    # migration runnable against the same store the offline tests build).
    with op.batch_alter_table("applications") as batch_op:
        batch_op.add_column(sa.Column("sent_attempt_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            "fk_applications_sent_attempt_id",
            "application_attempts",
            ["sent_attempt_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index("ix_applications_sent_attempt_id", "applications", ["sent_attempt_id"])


def downgrade() -> None:
    op.drop_index("ix_applications_sent_attempt_id", table_name="applications")
    with op.batch_alter_table("applications") as batch_op:
        batch_op.drop_constraint("fk_applications_sent_attempt_id", type_="foreignkey")
        batch_op.drop_column("sent_attempt_id")
    op.drop_index("uq_application_attempt_sent", table_name="application_attempts")
    op.drop_index("ix_application_attempts_profile_id", table_name="application_attempts")
    op.drop_index("ix_application_attempts_application_id", table_name="application_attempts")
    op.drop_table("application_attempts")
