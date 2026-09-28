"""Cover letters (PRD F8): the material a letter may cite, and the rules it must pass.

Pure or database-reading code, never a provider call — the calls live in
`src/extract/generation.py`. Two shapes:

* the reusable **blocks** of a template (N8.3): a presentation and an achievements
  paragraph, grounded in the track's own material;
* the **bridge** written for one application (N8.4), assembled with the profile's
  common blocks and a chosen template.

The bridge carries one rule the other generated text does not: it may not repeat a
number that appears in the chosen template's achievements paragraph, because that
would be the same achievement twice rather than a new one.
"""

import re
from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy.orm import Session

from src.bullets import list_bullets
from src.generate.proposals import pool_skills
from src.generate.validators import LITERAL, PROVENANCE, Sources, Violation, validate
from src.letters import get_letter, get_letter_settings, list_letters, update_letter
from src.models import Application, LetterSettings, LetterTemplate, Track
from src.roles import list_roles
from src.stories import list_stories
from src.summaries import get_summary
from src.tracks import get_track, track_bullets
from src.vocabulary import alias_map

# F8's shape rules. Presentation is a paragraph; achievements is one paragraph long
# enough to carry a flagship achievement.
PRESENTATION_MAX_WORDS = 70
ACHIEVEMENTS_MIN_WORDS = 80
ACHIEVEMENTS_MAX_WORDS = 160

LENGTH = "length"
SHAPE = "shape"

_NUMBER = re.compile(r"\d[\d.,]*%?")


def _join(*parts: str | None) -> str:
    return " ".join(part for part in parts if part)


def block_material(
    profile_id: Any, session: Session, track: Track, language: str
) -> tuple[dict[str, Any], Sources]:
    """The material a template's blocks may use, and the sources they may cite.

    Built together so the prompt and the validators see exactly the same rows: the
    track's bullets in order, the profile's roles and stories, the track's summary in
    the template's language.
    """
    bullets = track_bullets(profile_id, session, track.id)
    bullet_rows = [(str(bullet.id), _join(bullet.text_es, bullet.text_en)) for bullet in bullets]
    role_rows = []
    for role in list_roles(profile_id, session, active_only=False):
        role_rows.append((str(role.id), _join(role.title_es, role.title_en, role.title)))
    story_rows = [(str(story.id), story.body) for story in list_stories(profile_id, session)]

    slot = track.summary_en_id if language == "en" else track.summary_es_id
    summary_row = get_summary(profile_id, session, slot) if slot else None

    material = {
        "bullets": bullet_rows,
        "roles": role_rows,
        "stories": story_rows,
        "summary": summary_row.text if summary_row is not None else None,
    }
    sources = Sources(
        bullets=dict(bullet_rows),
        stories=dict(story_rows),
        roles=dict(role_rows),
        skills=pool_skills(profile_id, session),
        aliases=alias_map(session),
    )
    return material, sources


def check_blocks(output: Mapping[str, Any], sources: Sources) -> list[Violation]:
    """F7.3's three rules, plus F8's shape rules for the two paragraphs (N8.3)."""
    violations = list(
        validate(
            output,
            sources=sources,
            profile_id=None,
            session=None,
            kind="letter_blocks",
        )
    )
    presentation = str((output.get("presentation") or {}).get("text") or "")
    achievements = str((output.get("achievements") or {}).get("text") or "")
    if len(presentation.split()) > PRESENTATION_MAX_WORDS:
        violations.append(
            Violation(
                LENGTH,
                "presentation",
                presentation,
                f"the presentation is over {PRESENTATION_MAX_WORDS} words",
            )
        )
    words = len(achievements.split())
    if not ACHIEVEMENTS_MIN_WORDS <= words <= ACHIEVEMENTS_MAX_WORDS:
        violations.append(
            Violation(
                LENGTH,
                "achievements",
                achievements,
                f"the achievements paragraph is {words} words, outside "
                f"{ACHIEVEMENTS_MIN_WORDS}-{ACHIEVEMENTS_MAX_WORDS}",
            )
        )
    if "\n\n" in achievements.strip():
        violations.append(
            Violation(
                SHAPE,
                "achievements",
                achievements,
                "the achievements block is one paragraph",
            )
        )
    return violations


def accept_blocks(
    profile_id: Any,
    session: Session,
    letter_id: Any,
    output: Mapping[str, Any],
) -> tuple[LetterTemplate | None, list[Violation]]:
    """Accept a template's proposed blocks: validate again, then write them (N8.3)."""
    letter = get_letter(profile_id, session, letter_id)
    if letter is None:
        return None, []
    track = get_track(profile_id, session, letter.track_id) if letter.track_id else None
    if track is None:
        return letter, [
            Violation(PROVENANCE, "letter", "", "the template is not linked to a track")
        ]
    _material, sources = block_material(profile_id, session, track, letter.lang)
    violations = check_blocks(output, sources)
    if violations:
        return None, violations
    update_letter(
        profile_id,
        session,
        letter.id,
        name=letter.name,
        applies_when=letter.applies_when,
        presentation=str((output.get("presentation") or {}).get("text") or ""),
        achievements=str((output.get("achievements") or {}).get("text") or ""),
        lang=letter.lang,
        track_id=letter.track_id,
    )
    return letter, []


# --- N8.4: the bridge for one application ------------------------------------------


def letter_settings_for(
    profile_id: Any, session: Session, language: str
) -> LetterSettings | None:
    """The common blocks for the posting's language, or None (F8)."""
    return get_letter_settings(profile_id, session, language)


def letter_candidates(
    profile_id: Any, session: Session, application: Application, language: str
) -> list[LetterTemplate]:
    """Templates in the posting's language; with a track, the linked ones first (F8.1)."""
    templates = [letter for letter in list_letters(profile_id, session) if letter.lang == language]
    linked = [
        letter
        for letter in templates
        if application.track_id is not None and letter.track_id == application.track_id
    ]
    return linked + [letter for letter in templates if letter not in linked]


def material_for_application(
    profile_id: Any, session: Session, application: Application, language: str
) -> tuple[dict[str, Any], Sources]:
    """The person's own material for a bridge, the report's matched evidence first.

    The evidence the report cited is what the posting already graded as relevant, so it
    leads; the rest of the profile's bullets, roles and stories follow. The sources the
    validator checks against are the same rows.
    """
    cited = {
        str(grade.get("bullet_id"))
        for grade in (application.report or {}).get("grades") or []
        if grade.get("bullet_id")
    }
    bullets = list(_profile_bullets(profile_id, session))
    ordered = sorted(bullets, key=lambda bullet: (str(bullet.id) not in cited,))
    bullet_rows = [(str(bullet.id), _join(bullet.text_es, bullet.text_en)) for bullet in ordered]
    role_rows = [
        (str(role.id), _join(role.title_es, role.title_en, role.title))
        for role in list_roles(profile_id, session, active_only=False)
    ]
    story_rows = [(str(story.id), story.body) for story in list_stories(profile_id, session)]
    sources = Sources(
        bullets=dict(bullet_rows),
        stories=dict(story_rows),
        roles=dict(role_rows),
        skills=pool_skills(profile_id, session),
        aliases=alias_map(session),
    )
    return {"bullets": bullet_rows, "roles": role_rows, "stories": story_rows}, sources


def _profile_bullets(profile_id: Any, session: Session):
    return list_bullets(profile_id, session, active_only=True)


def numbers_in(text: str) -> set[str]:
    """The number tokens of a paragraph, for the achievements-number rule (N8.4)."""
    return {
        match.group().replace("%", "").replace(",", "").rstrip(".")
        for match in _NUMBER.finditer(text)
    }


def check_variants(
    output: Mapping[str, Any],
    *,
    sources: Sources,
    candidates: Sequence[LetterTemplate],
    jd_text: str,
    company: str | None,
    title: str | None,
    achievements_text: str,
) -> tuple[list[dict[str, Any]], list[Violation]]:
    """Every rule F8.4 puts on the bridge; returns the surviving variants.

    A variant whose company fact is not a verbatim quote of the posting is **dropped**,
    not weakened (F8.4); the other rules are reported as violations for the variants
    that keep.
    """
    allowed_ids = {str(letter.id) for letter in candidates}
    chosen = str(output.get("template_id") or "")
    runner_up = output.get("runner_up_id")
    violations: list[Violation] = []
    if chosen not in allowed_ids:
        violations.append(Violation(PROVENANCE, "template", chosen, "not a candidate template"))
    if runner_up is not None and str(runner_up) not in allowed_ids:
        violations.append(Violation(PROVENANCE, "template", str(runner_up), "not a candidate"))

    forbidden = numbers_in(achievements_text)
    jd_folded = " ".join(jd_text.split()).lower()
    survivors: list[dict[str, Any]] = []
    for index, variant in enumerate(output.get("variants") or []):
        name = f"variant {index + 1}"
        text = str(variant.get("text") or "")
        cites = [str(value) for value in variant.get("sources") or []]
        fact = variant.get("company_fact")
        if fact:
            quote = " ".join(str(fact.get("jd_quote") or "").split()).lower()
            if not quote or quote not in jd_folded:
                # Inventing a company detail is a failure, not a fallback: the variant
                # is dropped, and the others still stand (F8.4).
                continue
        words = len(text.split())
        if words > 90:
            violations.append(Violation(LENGTH, name, text, f"{words} words, over 90"))
        repeated = numbers_in(text) & forbidden
        if repeated:
            violations.append(
                Violation(
                    LITERAL,
                    name,
                    ", ".join(sorted(repeated)),
                    "repeats a number from the template's achievements paragraph",
                )
            )
        # The posting, the company and the title are citable for this rule: a variant
        # may name the employer it is writing to (F8.4).
        variant_sources = _bridge_sources(sources, jd_text, company, title)
        violations.extend(
            validate(
                {"text": text, "cites": [*cites, "__posting__"]},
                sources=variant_sources,
                profile_id=None,
                session=None,
                kind="bullet",
            )
        )
        survivors.append({**variant, "text": text, "sources": cites})
    return survivors, violations


def _bridge_sources(
    sources: Sources,
    jd_text: str,
    company: str | None,
    title: str | None,
) -> Sources:
    """The cited rows plus the posting, the company and the title (F8.4's allowance)."""
    return Sources(
        bullets={**sources.bullets, "__posting__": " ".join([jd_text, company or "", title or ""])},
        stories=sources.stories,
        roles=sources.roles,
        skills=sources.skills,
        aliases=sources.aliases,
    )


def missing_blocks(settings: LetterSettings | None) -> list[str]:
    """Which common blocks are still empty, for the checklist (F8.6, N8.5)."""
    if settings is None:
        return ["header", "greeting", "closing", "sign_off"]
    return [
        name
        for name in ("header", "greeting", "closing", "sign_off")
        if not (getattr(settings, name) or "").strip()
    ]
