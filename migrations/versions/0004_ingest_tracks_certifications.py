"""ingest: tracks, certifications, résumé archive, role scale, scan columns

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-19

Transcribed from the model metadata's PostgreSQL DDL and verified against it, so
the offline `--sql` output is identical to what `create_all` would emit.

Two data operations ride along. Existing bullets are assigned to a default track
named after the profile, so nothing orphans when tracks arrive, and the v1
`jd_corpus` table is dropped — it was created outside the migrations by the pgvector
step, it is empty, and v2 removed semantic fit, its only consumer. The pgvector
extension itself is left enabled: dropping it buys nothing.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STRINGS = postgresql.ARRAY(sa.String(length=120))


def _default_tracks() -> None:
    """One track per existing profile, holding every bullet that profile already has.

    Set-based on purpose: no Python-side reads, so `alembic upgrade --sql` renders
    the whole migration and an operator can inspect it before it runs.
    """
    op.execute(
        """
        INSERT INTO tracks (id, profile_id, name, applies_when, lang, active)
        SELECT gen_random_uuid(), id, display_name, '', 'es', true FROM profiles
        """
    )
    op.execute(
        """
        INSERT INTO track_bullets (track_id, bullet_id, position)
        SELECT t.id, b.id,
               row_number() OVER (PARTITION BY b.profile_id ORDER BY b.created_at, b.id) - 1
        FROM bullets b
        JOIN tracks t ON t.profile_id = b.profile_id
        """
    )


def upgrade() -> None:
    # NOT NULL with existing rows: add, backfill, then enforce (F2.3's extracted
    # skills list; the model's final shape carries no server default).
    op.add_column("profiles", sa.Column("skills", _STRINGS, nullable=True))
    op.execute("UPDATE profiles SET skills = '{}' WHERE skills IS NULL")
    op.alter_column("profiles", "skills", nullable=False, existing_type=_STRINGS)

    op.add_column("roles", sa.Column("team_size", sa.Integer(), nullable=True))
    op.add_column(
        "roles", sa.Column("budget_amount", sa.Numeric(precision=14, scale=2), nullable=True)
    )
    op.add_column("roles", sa.Column("budget_currency", sa.String(length=3), nullable=True))
    op.add_column("roles", sa.Column("scope_note", sa.Text(), nullable=True))

    op.add_column(
        "bullets",
        sa.Column(
            "source_story_id",
            sa.Uuid(),
            sa.ForeignKey("stories.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_bullets_source_story_id", "bullets", ["source_story_id"])

    op.add_column(
        "skills",
        sa.Column(
            "kind",
            sa.String(length=20),
            server_default=sa.text("'technical'"),
            nullable=False,
        ),
    )

    op.add_column(
        "applications",
        sa.Column("scan_readability", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "applications",
        sa.Column("scan_boolean", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    op.create_table(
        "certifications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("issuer", sa.String(length=200), nullable=True),
        sa.Column("issued_date", sa.Date(), nullable=True),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("credential_id", sa.String(length=120), nullable=True),
        sa.Column("credential_url", sa.String(length=500), nullable=True),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_certifications_profile_id", "certifications", ["profile_id"])

    op.create_table(
        "tracks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("applies_when", sa.Text(), nullable=False),
        sa.Column("lang", sa.String(length=5), nullable=False),
        sa.Column("target_seniority", sa.String(length=20), nullable=True),
        sa.Column("headline", sa.String(length=200), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tracks_profile_id", "tracks", ["profile_id"])

    op.create_table(
        "track_bullets",
        sa.Column("track_id", sa.Uuid(), nullable=False),
        sa.Column("bullet_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["track_id"], ["tracks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["bullet_id"], ["bullets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("track_id", "bullet_id"),
    )

    op.create_table(
        "resumes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("file_bytes", sa.LargeBinary(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("track_id", sa.Uuid(), nullable=True),
        sa.Column("draft", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("gate", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("merged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["track_id"], ["tracks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_resumes_profile_id", "resumes", ["profile_id"])
    op.create_index("ix_resumes_sha256", "resumes", ["sha256"])

    op.create_table(
        "bullet_revisions",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("bullet_id", sa.Uuid(), nullable=False),
        sa.Column("text_en", sa.Text(), nullable=True),
        sa.Column("text_es", sa.Text(), nullable=True),
        sa.Column("resume_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["bullet_id"], ["bullets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["resume_id"], ["resumes.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_bullet_revisions_bullet_id", "bullet_revisions", ["bullet_id"])

    _default_tracks()

    # v1's embeddings corpus, created by hand when pgvector was enabled and never
    # written to. v2 removed its only consumer; leave the extension alone.
    op.execute("DROP TABLE IF EXISTS jd_corpus")


def downgrade() -> None:
    op.drop_index("ix_bullet_revisions_bullet_id", table_name="bullet_revisions")
    op.drop_table("bullet_revisions")
    op.drop_index("ix_resumes_sha256", table_name="resumes")
    op.drop_index("ix_resumes_profile_id", table_name="resumes")
    op.drop_table("resumes")
    op.drop_table("track_bullets")
    op.drop_index("ix_tracks_profile_id", table_name="tracks")
    op.drop_table("tracks")
    op.drop_index("ix_certifications_profile_id", table_name="certifications")
    op.drop_table("certifications")
    op.drop_column("applications", "scan_boolean")
    op.drop_column("applications", "scan_readability")
    op.drop_column("skills", "kind")
    op.drop_index("ix_bullets_source_story_id", table_name="bullets")
    op.drop_column("bullets", "source_story_id")
    op.drop_column("roles", "scope_note")
    op.drop_column("roles", "budget_currency")
    op.drop_column("roles", "budget_amount")
    op.drop_column("roles", "team_size")
    op.drop_column("profiles", "skills")