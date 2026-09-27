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

Three more arrive with N1's ingest:

* `bullet_revisions` — F2.5 says a changed bullet keeps its history; the old text of
  every superseded wording lives here.
* `profiles.skills` — F2.3 extracts a résumé's skills list and no §6 table holds it.
* `resumes.draft` / `resumes.gate` / `resumes.merged_at` — the review screen renders
  the archived upload's findings and draft before anything is merged; §6 lists the
  archive columns only.
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
    LargeBinary,
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
    # The skills an uploaded résumé lists, as reviewed by the user (F2.3 has nowhere
    # else to put them and §6 has no column). Annotation only: evidence and every
    # score still read bullet chips, so a skill listed here cannot inflate a number.
    skills: Mapped[list[str]] = mapped_column(_StringList, default=list)
    # What could work against an application before a posting is read (F6.1): free
    # text the gap interpretation weighs. Never scored, never inferred.
    standing_risks: Mapped[list[str]] = mapped_column(_StringList, default=list)


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


class Certification(Base):
    """A credential (PRD 3).

    Stored apart from education even when the résumé prints both under one heading:
    the database does not merge what the document merges. `credential_id` is not in
    §6's column list but F2.3's classification rule reads it, and dropping an ID the
    document carries would lose what the user must be able to review.
    """

    __tablename__ = "certifications"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    issuer: Mapped[str | None] = mapped_column(String(200))
    issued_date: Mapped[date | None] = mapped_column(Date)
    expiry_date: Mapped[date | None] = mapped_column(Date)
    credential_id: Mapped[str | None] = mapped_column(String(120))
    credential_url: Mapped[str | None] = mapped_column(String(500))
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))


class Role(Base):
    """A position held. Deactivated rather than deleted, so historical reports render."""

    __tablename__ = "roles"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), index=True
    )
    employer: Mapped[str] = mapped_column(String(200))
    # `title` keeps being written — older code, stored reports and the snapshots
    # inside them read it — and holds the title in the role's primary language. The
    # two slots below are what a posting in a given language reads (F4.2): one
    # language per title, filled by the user or by importing the other-language CV,
    # never by an automatic translation.
    title: Mapped[str] = mapped_column(String(200))
    title_es: Mapped[str | None] = mapped_column(String(200))
    title_en: Mapped[str | None] = mapped_column(String(200))
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    # Optional scale (PRD 3): what the position was responsible for. Hand-entered;
    # the extractor does not propose these, so they cannot be invented by a model.
    team_size: Mapped[int | None] = mapped_column(Integer)
    budget_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    budget_currency: Mapped[str | None] = mapped_column(String(3))
    scope_note: Mapped[str | None] = mapped_column(Text)
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
    # F2.9: chips the vocabulary does not know, kept rather than dropped. A pending
    # term counts for nothing — pools, tracks, scoring and advice all read `skills`
    # — until the operator promotes it, which moves it into `skills` and the pool.
    pending_terms: Mapped[list[str]] = mapped_column(_StringList, default=list)
    metrics: Mapped[list[str]] = mapped_column(_StringList, default=list)
    # Set when a story proposed the bullet (F7.3): provenance is permanent, and the
    # column is what the validators will read. Nothing writes it until N7.
    source_story_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("stories.id", ondelete="SET NULL"), index=True
    )
    # Which CV created the bullet (F2.8): "only this CV contributed" deletes by this
    # and never touches a bullet whose provenance is unknown — NULL is not "every CV".
    source_resume_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("resumes.id", ondelete="SET NULL"), index=True
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BulletRevision(Base):
    """The superseded text of a bullet (PRD F2.5).

    A merge may change a bullet's wording; the old text stays readable afterwards so
    nothing the database once claimed becomes unrecoverable. Rows are append-only.
    """

    __tablename__ = "bullet_revisions"

    id: Mapped[int] = mapped_column(_BigInt, primary_key=True, autoincrement=True)
    bullet_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("bullets.id", ondelete="CASCADE"), index=True
    )
    text_en: Mapped[str | None] = mapped_column(Text)
    text_es: Mapped[str | None] = mapped_column(Text)
    resume_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("resumes.id", ondelete="SET NULL")
    )
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
    """Shared vocabulary. Growth is alias promotion only; no automatic expansion.

    `kind` (PRD F3) groups entries in the UI — technical, tool, domain, soft or
    experience — and never changes matching: an experience type matches exactly like
    `python` does.
    """

    __tablename__ = "skills"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    canonical: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    aliases: Mapped[list[str]] = mapped_column(_StringList, default=list)
    lang_tags: Mapped[list[str]] = mapped_column(_StringList, default=list)
    kind: Mapped[str] = mapped_column(
        String(20), default="technical", server_default=text("'technical'")
    )
    # One-hop equivalence group (PRD F5.4.1): two canonicals in the same family are
    # equivalents, and a flat group has no second hop, so nothing chains the way the
    # forbidden `implies` relation would. Nullable free text the operator reviews —
    # data, never a list in code — and most skills belong to no family.
    family: Mapped[str | None] = mapped_column(String(60))


class Track(Base):
    """A named target role and a saved selection of master bullets (PRD F4).

    A track owns no content: it references bullets, so editing one updates it
    everywhere and removing it from a track deletes nothing. Rows, not an enum.
    """

    __tablename__ = "tracks"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    applies_when: Mapped[str] = mapped_column(Text, default="")
    lang: Mapped[str] = mapped_column(String(5), default="es")
    target_seniority: Mapped[str | None] = mapped_column(String(20))
    # The two axes (PRD F4, 2026-09-21): the kind of employer this track targets and
    # the role's own axis. Free text, optional; N6's recommender reads them and
    # nothing ranks on them yet.
    organisation_kind: Mapped[str | None] = mapped_column(String(60))
    specialisation: Mapped[str | None] = mapped_column(String(60))
    # Legacy single-language slots: the expand half of an expand/contract change
    # (PRD 6's `0009` paragraph). Unread by the new code, so the database can be
    # migrated before the push while the old revision still serves; the contract
    # migration that drops them is not part of this run.
    headline: Mapped[str | None] = mapped_column(String(200))
    summary: Mapped[str | None] = mapped_column(Text)
    # The whole CV the track presents (F4.1): a headline and a pool summary per
    # language, plus the skill selection from the profile's pool. A track owns no
    # content: the slots reference pool rows the way the selection references
    # master bullets, and a merge fills them from a document, never overwrites them.
    headline_es: Mapped[str | None] = mapped_column(String(200))
    headline_en: Mapped[str | None] = mapped_column(String(200))
    summary_es_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("summaries.id", ondelete="SET NULL")
    )
    summary_en_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("summaries.id", ondelete="SET NULL")
    )
    skills: Mapped[list[str]] = mapped_column(_StringList, default=list)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))


class TrackBullet(Base):
    """Ordered membership: which master bullets a track selects, in what order."""

    __tablename__ = "track_bullets"

    track_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tracks.id", ondelete="CASCADE"), primary_key=True
    )
    bullet_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("bullets.id", ondelete="CASCADE"), primary_key=True
    )
    position: Mapped[int] = mapped_column(Integer, default=0)


class Resume(Base):
    """An uploaded source document, archived (PRD F2.6).

    The bytes and their SHA-256 are kept so a bullet can be traced to the document
    it came from. `draft` is the reviewed extraction and `gate` the readability
    findings; both are what the review screen renders, and career data changes only
    when the user confirms the merge. `merged_at` is NULL while a draft is pending.
    """

    __tablename__ = "resumes"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), index=True
    )
    filename: Mapped[str] = mapped_column(String(255))
    file_bytes: Mapped[bytes] = mapped_column(LargeBinary)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    track_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tracks.id", ondelete="SET NULL"))
    draft: Mapped[dict | None] = mapped_column(_JsonDoc)
    gate: Mapped[dict | None] = mapped_column(_JsonDoc)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    merged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))


class Summary(Base):
    """One summary text in the per-profile pool (PRD F2.7).

    An upload's summary joins the pool on merge, and a track's slot references a pool
    row the way its selection references bullets: a summary written for one track can
    be reused by another, and editing it here changes it in every track that uses it
    (F4.1). `source_resume_id` is the résumé it came from — NULL when the user wrote
    it by hand — and soft delete is the delete, so a stored report that cited one
    keeps rendering it.
    """

    __tablename__ = "summaries"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), index=True
    )
    lang: Mapped[str] = mapped_column(String(5), default="es")
    source_resume_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("resumes.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    # `text` comes last on purpose: the column name shadows SQLAlchemy's `text()`
    # helper inside this class body, where `active`'s server default needs it.
    text: Mapped[str] = mapped_column(Text)


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
    no network call and returns byte-identical output. A `degenerate` row is the
    exception the cache must forget (F2.3.1): an answer the caller's own check
    rejected keeps its cost — a paid call stays in the ledger (decision 21) — but is
    never served back, so one bad answer cannot become permanent.
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
    degenerate: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    # Whose call it was (F2.8): "Eliminar todo" redacts that profile's personal
    # answers through this. Rows written before the column existed carry NULL and
    # cannot be attributed — the screen says so; `llm_costs.py purge --hash` remains
    # the operator's tool for them.
    profile_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("profiles.id", ondelete="SET NULL"), index=True
    )
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
    # The track whose selection produced the score (F4). SET NULL, so removing a
    # track cannot take an analysis with it; the report names the track it used.
    track_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tracks.id", ondelete="SET NULL"), index=True
    )
    company: Mapped[str | None] = mapped_column(String(200))
    title: Mapped[str | None] = mapped_column(String(200))
    jd_text: Mapped[str] = mapped_column(Text)
    jd_hash: Mapped[str] = mapped_column(String(80), index=True)
    report: Mapped[dict] = mapped_column(_JsonDoc, default=dict)
    # Both ATS realism scans are persisted beside the score (PRD F5.1/F5.2): the
    # readability findings of the track's source document, and the boolean recall
    # result. Boolean recall is a gate reported next to the score, never in it.
    scan_readability: Mapped[dict | None] = mapped_column(_JsonDoc)
    scan_boolean: Mapped[dict | None] = mapped_column(_JsonDoc)
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
