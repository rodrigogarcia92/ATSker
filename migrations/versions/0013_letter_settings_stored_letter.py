"""Letter settings, the template↔track link, and the stored letter

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-27

Strictly additive (PRD F8, N8.1). Three things arrive together because they are one
feature's shape:

* `letter_settings` — the blocks every letter shares (header, greeting, closing,
  sign-off, `voice_notes`), one row per profile and language, unique on the pair.
* `letter_templates.track_id` — the optional link between a template and the track it
  is written for; deleting the track only unlinks it.
* `applications.letter_text` and `applications.letter_template_id` — the letter that
  was sent, kept as text so deleting the template cannot change it.

Nothing is dropped and nothing is backfilled, so **the database is migrated before the
code is pushed**. That is the opposite order of `0012`: dropping columns could only run
after its code was live, because the revision that still mapped them would have failed
on every query once they were gone.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "letter_settings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("lang", sa.String(length=5), nullable=False),
        sa.Column("header", sa.Text(), nullable=False),
        sa.Column("greeting", sa.Text(), nullable=False),
        sa.Column("closing", sa.Text(), nullable=False),
        sa.Column("sign_off", sa.Text(), nullable=False),
        sa.Column("voice_notes", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("profile_id", "lang", name="uq_letter_settings_profile_lang"),
    )
    op.create_index("ix_letter_settings_profile_id", "letter_settings", ["profile_id"])

    op.add_column(
        "letter_templates",
        sa.Column(
            "track_id",
            sa.Uuid(),
            sa.ForeignKey("tracks.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_letter_templates_track_id", "letter_templates", ["track_id"])

    op.add_column("applications", sa.Column("letter_text", sa.Text(), nullable=True))
    op.add_column(
        "applications",
        sa.Column(
            "letter_template_id",
            sa.Uuid(),
            sa.ForeignKey("letter_templates.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("applications", "letter_template_id")
    op.drop_column("applications", "letter_text")
    op.drop_index("ix_letter_templates_track_id", table_name="letter_templates")
    op.drop_column("letter_templates", "track_id")
    op.drop_index("ix_letter_settings_profile_id", table_name="letter_settings")
    op.drop_table("letter_settings")
