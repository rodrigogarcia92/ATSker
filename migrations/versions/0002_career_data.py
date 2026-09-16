"""career data: educations, roles, bullets, stories, letter templates, vocabulary

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-15

Transcribed from the model metadata's PostgreSQL DDL and verified against it, so
the offline `--sql` output is identical to what `create_all` would emit.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STRINGS = postgresql.ARRAY(sa.String(length=120))


def upgrade() -> None:
    op.add_column("profiles", sa.Column("headline", sa.String(length=200), nullable=True))
    op.add_column("profiles", sa.Column("summary", sa.Text(), nullable=True))

    op.create_table(
        "educations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("institution", sa.String(length=200), nullable=False),
        sa.Column("degree", sa.String(length=200), nullable=True),
        sa.Column("field", sa.String(length=200), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_educations_profile_id", "educations", ["profile_id"])

    op.create_table(
        "roles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("employer", sa.String(length=200), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_roles_profile_id", "roles", ["profile_id"])

    op.create_table(
        "bullets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.Column("text_en", sa.Text(), nullable=True),
        sa.Column("text_es", sa.Text(), nullable=True),
        sa.Column("skills", _STRINGS, nullable=False),
        sa.Column("metrics", _STRINGS, nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_bullets_profile_id", "bullets", ["profile_id"])
    op.create_index("ix_bullets_role_id", "bullets", ["role_id"])

    op.create_table(
        "stories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("role_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("tags", _STRINGS, nullable=False),
        sa.Column("lang", sa.String(length=5), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_stories_profile_id", "stories", ["profile_id"])
    op.create_index("ix_stories_role_id", "stories", ["role_id"])

    op.create_table(
        "story_bullet",
        sa.Column("story_id", sa.Uuid(), nullable=False),
        sa.Column("bullet_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["story_id"], ["stories.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["bullet_id"], ["bullets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("story_id", "bullet_id"),
    )

    op.create_table(
        "letter_templates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("applies_when", sa.Text(), nullable=False),
        sa.Column("presentation", sa.Text(), nullable=False),
        sa.Column("achievements", sa.Text(), nullable=False),
        sa.Column("lang", sa.String(length=5), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_letter_templates_profile_id", "letter_templates", ["profile_id"])

    op.create_table(
        "skills",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("canonical", sa.String(length=120), nullable=False),
        sa.Column("aliases", _STRINGS, nullable=False),
        sa.Column("lang_tags", _STRINGS, nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_skills_canonical", "skills", ["canonical"], unique=True)

    op.create_table(
        "unmapped_terms",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("term", sa.String(length=120), nullable=False),
        sa.Column("seen_count", sa.Integer(), nullable=False),
        sa.Column(
            "first_seen",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_unmapped_terms_term", "unmapped_terms", ["term"], unique=True)

    op.create_table(
        "llm_calls",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("purpose", sa.String(length=40), nullable=False),
        sa.Column("prompt_version", sa.String(length=40), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("response_json", sa.JSON(), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False),
        sa.Column("completion_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Numeric(precision=10, scale=6), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_llm_calls_cache_key", "llm_calls", ["purpose", "prompt_version", "input_hash"]
    )


def downgrade() -> None:
    op.drop_index("ix_llm_calls_cache_key", table_name="llm_calls")
    op.drop_table("llm_calls")
    op.drop_index("ix_unmapped_terms_term", table_name="unmapped_terms")
    op.drop_table("unmapped_terms")
    op.drop_index("ix_skills_canonical", table_name="skills")
    op.drop_table("skills")
    op.drop_index("ix_letter_templates_profile_id", table_name="letter_templates")
    op.drop_table("letter_templates")
    op.drop_table("story_bullet")
    op.drop_index("ix_stories_role_id", table_name="stories")
    op.drop_index("ix_stories_profile_id", table_name="stories")
    op.drop_table("stories")
    op.drop_index("ix_bullets_role_id", table_name="bullets")
    op.drop_index("ix_bullets_profile_id", table_name="bullets")
    op.drop_table("bullets")
    op.drop_index("ix_roles_profile_id", table_name="roles")
    op.drop_table("roles")
    op.drop_index("ix_educations_profile_id", table_name="educations")
    op.drop_table("educations")
    op.drop_column("profiles", "summary")
    op.drop_column("profiles", "headline")
