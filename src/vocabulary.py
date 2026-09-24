"""The shared skill vocabulary (PRD F3).

Alias promotion is the only way the vocabulary grows: nothing here invents a
canonical, and terms the vocabulary does not know are logged for a human decision.
"""

from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models import Skill, UnmappedTerm
from src.normalize.text import fold
from src.normalize.vocabulary import match_text, resolve_terms

# PRD F3. An experience type matches exactly like `python` does; kind only groups
# entries in the UI. The list lives here so a typo in the seed data fails the tests.
SKILL_KINDS: tuple[str, ...] = ("technical", "tool", "domain", "soft", "experience")


def alias_map(session: Session) -> dict[str, str]:
    """folded alias → canonical, including each canonical as its own alias."""
    mapping: dict[str, str] = {}
    for skill in session.scalars(select(Skill)):
        mapping[fold(skill.canonical)] = skill.canonical
        for alias in skill.aliases:
            mapping[fold(alias)] = skill.canonical
    return mapping


def skills_in_text(session: Session, text: str, *, limit: int | None = None) -> list[str]:
    """Canonical skills named in prose — used to pre-fill a bullet's skill chips."""
    if not text.strip():
        return []
    return match_text(text, alias_map(session), limit=limit)


def resolve_bullet_terms(session: Session, chips: Iterable[str]) -> tuple[list[str], list[str]]:
    """User-typed chips → (canonical skills, unknown terms to log)."""
    return resolve_terms(chips, alias_map(session))


def log_unmapped(session: Session, terms: Iterable[str]) -> int:
    """Record unknown terms, incrementing the count for terms already seen."""
    logged = 0
    for raw in terms:
        term = fold(raw)
        if not term:
            continue
        existing = session.scalar(select(UnmappedTerm).where(UnmappedTerm.term == term))
        if existing is None:
            session.add(UnmappedTerm(term=term, seen_count=1, first_seen=datetime.now(UTC)))
        else:
            existing.seen_count += 1
            if existing.status == "promoted":
                existing.status = "reopened"
        logged += 1
    session.flush()
    return logged


def seed_vocabulary(session: Session, entries: Iterable[Mapping[str, object]]) -> dict[str, int]:
    """Insert missing canonicals and add missing aliases; never deletes anything.

    Idempotent, so the operator can re-run it on any branch after editing the seed
    file. Existing entries keep aliases a human promoted (PRD F3).
    """
    existing = {skill.canonical: skill for skill in session.scalars(select(Skill))}
    created = 0
    enriched = 0
    for entry in entries:
        canonical = str(entry["canonical"])
        aliases = [str(value) for value in entry["aliases"]]  # type: ignore[union-attr]
        lang_tags = [str(value) for value in entry["lang_tags"]]  # type: ignore[union-attr]
        kind = str(entry.get("kind") or "technical")
        family = str(entry["family"]) if entry.get("family") else None
        skill = existing.get(canonical)
        if skill is None:
            skill = Skill(
                canonical=canonical,
                aliases=aliases,
                lang_tags=lang_tags,
                kind=kind,
                family=family,
            )
            session.add(skill)
            existing[canonical] = skill
            created += 1
            continue
        changed = False
        missing = [alias for alias in aliases if alias not in skill.aliases]
        if missing:
            skill.aliases = [*skill.aliases, *missing]
            changed = True
        # A kind is seed data, not something a human promoted, so re-running the
        # seed corrects it (which is how the 140 pre-N1 rows get their real kinds).
        if skill.kind != kind:
            skill.kind = kind
            changed = True
        # A family is the opposite (F5.4.1): equivalence is a judgement the operator
        # reviews, so the seed fills empty families and never overwrites one that is
        # already set — a human edit survives every future seed run.
        if skill.family is None and family is not None:
            skill.family = family
            changed = True
        if changed:
            enriched += 1
    session.flush()
    return {"created": created, "enriched": enriched, "total": len(existing)}


def list_skills(session: Session) -> Sequence[Skill]:
    return list(session.scalars(select(Skill).order_by(Skill.canonical)))


def list_unmapped(session: Session, *, status: str | None = None) -> Sequence[UnmappedTerm]:
    stmt = select(UnmappedTerm).order_by(UnmappedTerm.seen_count.desc(), UnmappedTerm.term)
    if status is not None:
        stmt = stmt.where(UnmappedTerm.status == status)
    return list(session.scalars(stmt))


def promote_alias(
    session: Session, canonical: str, alias: str, *, lang_tags: Sequence[str] = ("es", "en")
) -> Skill:
    """Add an alias to an existing canonical skill, or create the canonical.

    The operator runs this monthly against the unmapped-term log; the term's status
    moves to `promoted` so the same decision is not asked twice.
    """
    canonical = fold(canonical)
    alias = fold(alias)
    skill = session.scalar(select(Skill).where(Skill.canonical == canonical))
    if skill is None:
        skill = Skill(canonical=canonical, aliases=[alias], lang_tags=list(lang_tags))
        session.add(skill)
    elif alias not in skill.aliases and alias != skill.canonical:
        skill.aliases = [*skill.aliases, alias]

    if alias != canonical:
        record = session.scalar(select(UnmappedTerm).where(UnmappedTerm.term == alias))
        if record is not None:
            record.status = "promoted"
    session.flush()
    return skill
