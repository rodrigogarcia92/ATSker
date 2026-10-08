"""Probable keywords on demand (PRD F7.5): the leftovers, the one paid call, the guards.

The Keywords card (`src.keyword_advice`) classifies a missing keyword by the user's own data
and leaves the rest. This module takes those leftovers — minus the named tools, which are
never inferred — makes one call about them and checks the answer with
`validators.validate_keyword_items`. It writes nothing: no skill, no bullet, no score, no
vocabulary relation moves because of it (F7.5 guards 5-7); the card's items are suggestions
the user applies to their own file.

`prepare_inference` reads everything the call needs and `run_inference` makes the call, so a
route can end its transaction in between: the client refuses a call made inside one.
"""

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.bullets import bullet_text, list_bullets
from src.extract.client import CallOptions
from src.extract.generation import Proposal, generate_keyword_inference
from src.generate.letters import banned_phrases
from src.generate.validators import KeywordMaterial, validate_keyword_items
from src.keyword_advice import Candidate, KeywordAdvice, keyword_advice
from src.models import Profile, Skill, Track
from src.roles import list_roles
from src.vocabulary import alias_map

# What the card says a supporting id is, in the partial: a skill's name, a bullet's text.
_SNIPPET = 90


@dataclass(frozen=True)
class Prepared:
    """Everything one inference call is built from, read once and owner-scoped."""

    candidates: list[Candidate]
    pool: list[str]
    bullets: list[tuple[str, str]]
    roles: list[tuple[str, str]]
    material: KeywordMaterial
    language: str


@dataclass(frozen=True)
class Inference:
    """The shown items, how many were dropped, and the proposal that carried them."""

    items: list[dict[str, Any]]
    dropped: int
    proposal: Proposal


def _role_title(role: Any, language: str) -> str:
    titles = (role.title_en, role.title_es) if language == "en" else (role.title_es, role.title_en)
    return titles[0] or titles[1] or ""


def inferable(session: Session, card: KeywordAdvice | None) -> list[Candidate]:
    """The keywords the card found no basis for, without the named tools (F7.5 guard 4).

    A tool is dropped before the call rather than after it: asking a paid question whose
    answer the guards would discard is waste, and the equivalent basis already covers the
    honest case. A phrase the vocabulary does not know stays — it may be a method.
    """
    if card is None:
        return []
    kinds = {skill.canonical: skill.kind for skill in session.scalars(select(Skill))}
    return [
        candidate
        for candidate in card.unsupported
        if candidate.canonical is None or kinds.get(candidate.canonical) != "tool"
    ]


def leftover_candidates(
    profile_id: uuid.UUID,
    session: Session,
    *,
    report: Mapping[str, object],
    track: Track | None,
    for_file: bool,
) -> list[Candidate]:
    """`inferable` for a stored report, from the material the user holds now."""
    card = keyword_advice(profile_id, session, report=report, track=track, for_file=for_file)
    return inferable(session, card)


def prepare_inference(
    profile_id: uuid.UUID,
    session: Session,
    *,
    report: Mapping[str, object],
    track: Track | None,
    for_file: bool,
) -> Prepared | None:
    """Read the candidates, the pool, the bullets and the roles; `None` when none is left."""
    candidates = leftover_candidates(
        profile_id, session, report=report, track=track, for_file=for_file
    )
    profile = session.get(Profile, profile_id)
    if not candidates or profile is None:
        return None
    jd = report.get("jd") if isinstance(report.get("jd"), Mapping) else {}
    language = str((jd or {}).get("language") or "es")
    bullets = [
        (str(bullet.id), bullet_text(bullet, language))
        for bullet in list_bullets(profile_id, session, active_only=True)
    ]
    roles = [
        (str(role.id), _role_title(role, language))
        for role in list_roles(profile_id, session, active_only=True)
    ]
    pool = sorted(profile.skills or [])
    skills = {skill.canonical: skill.kind for skill in session.scalars(select(Skill))}
    material = KeywordMaterial(
        candidates=tuple(candidate.keyword for candidate in candidates),
        canonicals={candidate.keyword: candidate.canonical for candidate in candidates},
        kinds={name: skills[name] for name in skills},
        skills=frozenset(pool),
        bullets=dict(bullets),
        roles=dict(roles),
        aliases=alias_map(session),
    )
    return Prepared(candidates, pool, bullets, roles, material, language)


def run_inference(
    session: Session,
    prepared: Prepared,
    *,
    profile_id: uuid.UUID,
    known_names: list[str] | None = None,
) -> Inference:
    """The one paid call, then F7.5's guards; the caller has ended its transaction."""
    proposal = generate_keyword_inference(
        session,
        candidates=[candidate.keyword for candidate in prepared.candidates],
        pool=prepared.pool,
        bullets=prepared.bullets,
        roles=prepared.roles,
        banned=banned_phrases(prepared.language),
        language=prepared.language,
        known_names=known_names,
        options=CallOptions(profile_id=profile_id),
    )
    items, dropped = validate_keyword_items(proposal.output.get("items") or [], prepared.material)
    return Inference(items=items, dropped=dropped, proposal=proposal)


def describe(items: list[dict[str, Any]], prepared: Prepared) -> list[dict[str, Any]]:
    """The shown items with what their ids stand for, so the partial needs no lookups.

    A supporting `skill:<canonical>` reads as the canonical and a `bullet:<id>` as the start
    of that bullet's text; `bullet_text` and `role_title` name where the item would go.
    """
    bullets, roles = prepared.material.bullets, prepared.material.roles
    described = []
    for item in items:
        labels = []
        for support in item["supports"]:
            kind, _, name = support.partition(":")
            text = name if kind == "skill" else bullets.get(name, "")
            shown = text if len(text) <= _SNIPPET else text[:_SNIPPET] + "…"
            labels.append({"kind": kind, "text": shown})
        described.append(
            {
                **item,
                "supports_labelled": labels,
                "bullet_text": bullets.get(item["bullet_id"] or "", ""),
                "role_title": roles.get(item["role_id"] or "", ""),
            }
        )
    return described
