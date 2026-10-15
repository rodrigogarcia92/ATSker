"""Analysis on a CV (PRD F11.10)

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-11

Additive. Three changes arrive together because they are one feature's shape:

* `applications.resume_id` — the CV the analysis scored (F11.3). Nullable, indexed,
  `ON DELETE SET NULL`, so deleting a CV cannot take an analysis with it; the report
  keeps the file name. No backfill: an old application keeps NULL (F11.8).
* `resumes.file_bytes` becomes nullable — a CV saved from an attempt has no file,
  because attempts never store one (F10, F11.7).
* `resumes.source_attempt_id` — the attempt a CV was saved from. Nullable, indexed,
  `ON DELETE SET NULL`.

Dev, then prod, **before** the code is pushed. Batch mode throughout: identical DDL on
PostgreSQL, and on SQLite it recreates the table, the only way to add a foreign key
there (as 0014 does).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("resumes") as batch_op:
        batch_op.alter_column("file_bytes", existing_type=sa.LargeBinary(), nullable=True)
        batch_op.add_column(sa.Column("source_attempt_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            "fk_resumes_source_attempt_id",
            "application_attempts",
            ["source_attempt_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index("ix_resumes_source_attempt_id", "resumes", ["source_attempt_id"])

    with op.batch_alter_table("applications") as batch_op:
        batch_op.add_column(sa.Column("resume_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            "fk_applications_resume_id",
            "resumes",
            ["resume_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index("ix_applications_resume_id", "applications", ["resume_id"])


def downgrade() -> None:
    op.drop_index("ix_applications_resume_id", table_name="applications")
    with op.batch_alter_table("applications") as batch_op:
        batch_op.drop_constraint("fk_applications_resume_id", type_="foreignkey")
        batch_op.drop_column("resume_id")

    op.drop_index("ix_resumes_source_attempt_id", table_name="resumes")
    # A CV saved from an attempt has no bytes; the old column forbids NULL, so those
    # rows get an empty document before the constraint returns.
    op.execute(
        sa.text("UPDATE resumes SET file_bytes = :empty WHERE file_bytes IS NULL").bindparams(
            sa.bindparam("empty", value=b"", type_=sa.LargeBinary())
        )
    )
    with op.batch_alter_table("resumes") as batch_op:
        batch_op.drop_constraint("fk_resumes_source_attempt_id", type_="foreignkey")
        batch_op.drop_column("source_attempt_id")
        batch_op.alter_column("file_bytes", existing_type=sa.LargeBinary(), nullable=False)
