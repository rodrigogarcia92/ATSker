"""bullets.pending_terms, roles.title_es and roles.title_en

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-27

Strictly additive, and safe before the code that reads it: the pending terms of a
bullet (PRD F2.9 — a chip the vocabulary does not know is kept and logged, never
dropped) and the two per-language title slots of a role (PRD F4.2 — a posting in
English reads an English title, falling back to the Spanish one). Rows written
before either column existed carry `'{}'` and NULL, which is exactly what the code
reads them as: a bullet with nothing pending, a role whose title lives in `title`
only.

`pending_terms` is `bullets.skills`' own array type, NOT NULL with `'{}'` as its
server default, so the column is added in one statement with every existing row
already valid. The two title columns are nullable: the backfill below fills one of
them per role and leaves the other for the user or for importing the
other-language CV — never for an automatic translation.

The backfill is set-based (`alembic upgrade --sql` renders the whole migration for
inspection before it runs), one rule per role, in F4.2's order: the draft language
of the résumé that produced the role's earliest bullet with provenance; otherwise
the language most of the role's bullets are written in, a tie falling through;
otherwise the language of a track holding one of its bullets; otherwise `es`.

Transcribed from the model metadata's PostgreSQL DDL, as `0004` and `0010` were.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STRINGS = postgresql.ARRAY(sa.String(length=120))

# A role's language, as a chain of scalar subqueries: a rule answers `en` only when
# it says so, and anything else — no rule applies, or a tie — is NULL, so COALESCE
# falls through to the next rule instead of inventing a language.
_ROLE_LANGUAGE = """
COALESCE(
    (
        SELECT CASE WHEN resumes.draft ->> 'language' = 'en' THEN 'en' ELSE 'es' END
        FROM bullets
        JOIN resumes ON resumes.id = bullets.source_resume_id
        WHERE bullets.role_id = roles.id
          AND bullets.source_resume_id IS NOT NULL
          AND resumes.draft ->> 'language' IS NOT NULL
        ORDER BY bullets.created_at, bullets.id
        LIMIT 1
    ),
    (
        SELECT CASE
            WHEN count(*) FILTER (WHERE text_es IS NOT NULL)
               > count(*) FILTER (WHERE text_en IS NOT NULL) THEN 'es'
            WHEN count(*) FILTER (WHERE text_en IS NOT NULL)
               > count(*) FILTER (WHERE text_es IS NOT NULL) THEN 'en'
        END
        FROM bullets
        WHERE bullets.role_id = roles.id
    ),
    (
        SELECT CASE WHEN tracks.lang = 'en' THEN 'en' ELSE 'es' END
        FROM track_bullets
        JOIN tracks ON tracks.id = track_bullets.track_id
        JOIN bullets ON bullets.id = track_bullets.bullet_id
        WHERE bullets.role_id = roles.id
        ORDER BY tracks.id
        LIMIT 1
    ),
    'es'
)
"""


def upgrade() -> None:
    op.add_column(
        "bullets",
        sa.Column("pending_terms", _STRINGS, server_default=sa.text("'{}'"), nullable=False),
    )

    op.add_column("roles", sa.Column("title_es", sa.String(length=200), nullable=True))
    op.add_column("roles", sa.Column("title_en", sa.String(length=200), nullable=True))
    op.execute(
        f"""
        WITH role_language AS (
            SELECT roles.id, {_ROLE_LANGUAGE} AS lang FROM roles
        )
        UPDATE roles SET
            title_es = CASE WHEN role_language.lang = 'es' THEN roles.title END,
            title_en = CASE WHEN role_language.lang = 'en' THEN roles.title END
        FROM role_language
        WHERE role_language.id = roles.id
        """
    )


def downgrade() -> None:
    op.drop_column("roles", "title_en")
    op.drop_column("roles", "title_es")
    op.drop_column("bullets", "pending_terms")
