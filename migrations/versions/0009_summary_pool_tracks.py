"""Pools and whole-track fields: the summary pool, track slots, skill families

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-22

Strictly additive (PRD 6's `0009` paragraph): the `summaries` pool, `tracks`' per-language
headline and summary slots with its skill selection, and `skills.family` — the one-hop
equivalence groups F5.4.1 credits as `equivalent`. Backfills are set-based SQL only, as
`0004` did: no Python-side reads, so `alembic upgrade --sql` renders the whole migration
and an operator can inspect it before it runs.

This is the *expand* half of an expand/contract change: `tracks.headline` and
`tracks.summary` stay, unread by the new code, so the database can be migrated before
the push while the old revision still serves. The *contract* migration that drops them
is not part of this run.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STRINGS = postgresql.ARRAY(sa.String(length=120))


def _pool_profile_summaries() -> None:
    """Each profile's summary joins the pool in 'es', with no source document.

    The column predates the pool and carries no language, and the profile's own
    summary is Spanish until something says otherwise.
    """
    op.execute(
        """
        INSERT INTO summaries (id, profile_id, lang, text, source_resume_id, active)
        SELECT gen_random_uuid(), id, 'es', summary, NULL, true FROM profiles
        WHERE summary IS NOT NULL AND btrim(summary) <> ''
        """
    )


def _copy_headlines() -> None:
    """The old single headline lands in the slot of the track's own language.

    `es` or `en`; anything else reads as `es`, the default language.
    """
    op.execute(
        """
        UPDATE tracks SET headline_en = headline
        WHERE headline IS NOT NULL AND btrim(headline) <> '' AND lang = 'en'
        """
    )
    op.execute(
        """
        UPDATE tracks SET headline_es = headline
        WHERE headline IS NOT NULL AND btrim(headline) <> '' AND lang IS DISTINCT FROM 'en'
        """
    )


def _pool_track_summaries() -> None:
    """Each track's summary becomes a pool row of its language, pointing its slot at it.

    The `src` CTE pre-generates the ids so the INSERT and the UPDATE agree row for row
    without matching on text: two tracks may legitimately hold the same summary, and
    here each gets its own pool row.
    """
    for lang, slot in (("en", "summary_en_id"), ("es", "summary_es_id")):
        where = "t.lang = 'en'" if lang == "en" else "t.lang IS DISTINCT FROM 'en'"
        op.execute(
            f"""
            WITH src AS (
                SELECT gen_random_uuid() AS new_id, t.id AS track_id,
                       t.profile_id AS profile_id, t.summary AS summary
                FROM tracks t
                WHERE t.summary IS NOT NULL AND btrim(t.summary) <> '' AND {where}
            ), ins AS (
                INSERT INTO summaries (id, profile_id, lang, text, source_resume_id, active)
                SELECT new_id, profile_id, '{lang}', summary, NULL, true FROM src
            )
            UPDATE tracks t SET {slot} = src.new_id FROM src WHERE t.id = src.track_id
            """
        )


def upgrade() -> None:
    op.create_table(
        "summaries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("lang", sa.String(length=5), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("source_resume_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_resume_id"], ["resumes.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_summaries_profile_id", "summaries", ["profile_id"])

    op.add_column("tracks", sa.Column("headline_es", sa.String(length=200), nullable=True))
    op.add_column("tracks", sa.Column("headline_en", sa.String(length=200), nullable=True))
    op.add_column(
        "tracks",
        sa.Column(
            "summary_es_id",
            sa.Uuid(),
            sa.ForeignKey("summaries.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "tracks",
        sa.Column(
            "summary_en_id",
            sa.Uuid(),
            sa.ForeignKey("summaries.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    # NOT NULL with existing rows: add, backfill, then enforce (as `0004` did for
    # `profiles.skills`).
    op.add_column("tracks", sa.Column("skills", _STRINGS, nullable=True))
    op.execute("UPDATE tracks SET skills = '{}' WHERE skills IS NULL")
    op.alter_column("tracks", "skills", nullable=False, existing_type=_STRINGS)

    op.add_column("skills", sa.Column("family", sa.String(length=60), nullable=True))

    _pool_profile_summaries()
    _copy_headlines()
    _pool_track_summaries()


def downgrade() -> None:
    op.drop_column("skills", "family")
    op.drop_column("tracks", "skills")
    op.drop_column("tracks", "summary_en_id")
    op.drop_column("tracks", "summary_es_id")
    op.drop_column("tracks", "headline_en")
    op.drop_column("tracks", "headline_es")
    op.drop_index("ix_summaries_profile_id", table_name="summaries")
    op.drop_table("summaries")
