"""SQLAlchemy models.

Column types are dialect-neutral (`Uuid`, `JSON` variants) so that tests can create
the same schema in SQLite and stay offline. PostgreSQL is the only dialect that runs
in production; the migrations are the authority on the real DDL.

Two tables are not in PRD 6 as written:

* `educations` and `profiles.headline`/`summary` — F2's review screen and F7's
  Tier-1 block both need somewhere to store them, and the table list omits it.
* `llm_calls` — PRD 7 requires per-call token and cost logging, but
  `applications.token_cost_usd` cannot hold a call that happens outside an analysis
  (F3's story suggestions). The row doubles as the content-hash cache.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# SQLite refuses AUTOINCREMENT on BIGINT primary keys; PostgreSQL has no such complaint.
_BigInt = BigInteger().with_variant(Integer, "sqlite")

# PostgreSQL arrays where the PRD asks for `[]` columns; JSON elsewhere so the same
# models create in SQLite. MutableList keeps in-place edits visible to the session.
_StringList = MutableList.as_mutable(ARRAY(String(120)).with_variant(JSON(), "sqlite"))

# JSONB in production (indexable, typed); plain JSON where the dialect lacks it.
_JsonDoc = JSONB().with_variant(JSON(), "sqlite")


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    ui_lang: Mapped[str] = mapped_column(String(5), default="es")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Profile(Base):
    __tablename__ = "profiles"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )
    display_name: Mapped[str] = mapped_column(String(200))
    headline: Mapped[str | None] = mapped_column(String(200))
    summary: Mapped[str | None] = mapped_column(Text)


class Education(Base):
    __tablename__ = "educations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), index=True
    )
    institution: Mapped[str] = mapped_column(String(200))
    degree: Mapped[str | None] = mapped_column(String(200))
    field: Mapped[str | None] = mapped_column(String(200))
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)


class Role(Base):
    """A position held. Deactivated rather than deleted, so historical reports render."""

    __tablename__ = "roles"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), index=True
    )
    employer: Mapped[str] = mapped_column(String(200))
    title: Mapped[str] = mapped_column(String(200))
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))


class Bullet(Base):
    """One résumé-ready line: the superset from which tailored résumés select."""

    __tablename__ = "bullets"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), index=True
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), index=True
    )
    text_en: Mapped[str | None] = mapped_column(Text)
    text_es: Mapped[str | None] = mapped_column(Text)
    skills: Mapped[list[str]] = mapped_column(_StringList, default=list)
    metrics: Mapped[list[str]] = mapped_column(_StringList, default=list)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Story(Base):
    """Long-form narrative. Feeds cover letters; never enters a résumé (PRD 3)."""

    __tablename__ = "stories"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), index=True
    )
    role_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("roles.id", ondelete="SET NULL"), index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    tags: Mapped[list[str]] = mapped_column(_StringList, default=list)
    lang: Mapped[str] = mapped_column(String(5), default="es")


class StoryBullet(Base):
    __tablename__ = "story_bullet"

    story_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("stories.id", ondelete="CASCADE"), primary_key=True
    )
    bullet_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("bullets.id", ondelete="CASCADE"), primary_key=True
    )


class LetterTemplate(Base):
    """User-defined reusable blocks. Replaces any hardcoded track taxonomy."""

    __tablename__ = "letter_templates"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    applies_when: Mapped[str] = mapped_column(Text)
    presentation: Mapped[str] = mapped_column(Text)
    achievements: Mapped[str] = mapped_column(Text)
    lang: Mapped[str] = mapped_column(String(5), default="es")


class Skill(Base):
    """Shared vocabulary. Growth is alias promotion only; no automatic expansion."""

    __tablename__ = "skills"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    canonical: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    aliases: Mapped[list[str]] = mapped_column(_StringList, default=list)
    lang_tags: Mapped[list[str]] = mapped_column(_StringList, default=list)


class UnmappedTerm(Base):
    """Terms the extractor or a bullet proposed that the vocabulary does not know."""

    __tablename__ = "unmapped_terms"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    term: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    seen_count: Mapped[int] = mapped_column(Integer, default=1)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    status: Mapped[str] = mapped_column(String(20), default="new")


class LlmCall(Base):
    """One model call: the cost ledger (PRD 7) and the content-hash cache.

    `response_json` is stored so a repeat of the same input and prompt version makes
    no network call and returns byte-identical output.
    """

    __tablename__ = "llm_calls"
    __table_args__ = (Index("ix_llm_calls_cache_key", "purpose", "prompt_version", "input_hash"),)

    id: Mapped[int] = mapped_column(_BigInt, primary_key=True, autoincrement=True)
    purpose: Mapped[str] = mapped_column(String(40))
    prompt_version: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(120))
    input_hash: Mapped[str] = mapped_column(String(64))
    response_json: Mapped[dict] = mapped_column(JSON)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Application(Base):
    """One analysis: the posting, the score report, and eventually the outcome (PRD F8).

    The schema exists from the first real application so the dataset accumulates
    from day one; the outcome column is what later answers whether the sub-scores
    predict callbacks.
    """

    __tablename__ = "applications"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), index=True
    )
    company: Mapped[str | None] = mapped_column(String(200))
    title: Mapped[str | None] = mapped_column(String(200))
    jd_text: Mapped[str] = mapped_column(Text)
    jd_hash: Mapped[str] = mapped_column(String(80), index=True)
    report: Mapped[dict] = mapped_column(_JsonDoc, default=dict)
    weights_version: Mapped[str] = mapped_column(String(20))
    prompt_versions: Mapped[dict] = mapped_column(_JsonDoc, default=dict)
    token_cost_usd: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("0"))
    outcome: Mapped[str] = mapped_column(String(20), default="no_reply")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class LoginAttempt(Base):
    """Failed logins, for the per-username rate limit (PRD F1).

    Kept in the database rather than in process memory: Cloud Run runs up to two
    instances and scales to zero, so an in-memory counter would be both wrong and
    forgetful. Rows are deleted on a successful login and aged out by query window.
    """

    __tablename__ = "login_attempts"

    id: Mapped[int] = mapped_column(_BigInt, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(320), index=True)
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
