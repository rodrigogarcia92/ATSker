"""Cover letters (PRD F8): the material a letter may cite, and the rules it must pass.

Pure or database-reading code, never a provider call — the calls live in
`src/extract/generation.py`. Two shapes:

* the track's **template** (F8): a presentation and an achievements paragraph, grounded
  in the track's own material;
* the **bridge** written for one application, one at a time (F8.3), assembled with the
  profile's common blocks and the track's template.

The bridge carries one rule the other generated text does not: it may not repeat a
number that appears in the track's achievements paragraph, because that would be the
same achievement twice rather than a new one. A hard failure means no paragraph; a soft
one (length, banned phrases) is shown and marked.
"""

import html
import json
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from functools import cache
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from src.bullets import list_bullets
from src.generate.proposals import pool_skills
from src.generate.validators import LITERAL, PROVENANCE, Sources, Violation, validate
from src.letters import get_letter_settings
from src.models import Application, LetterSettings, LetterTemplate, Track
from src.normalize.text import fold
from src.roles import list_roles
from src.stories import list_stories
from src.summaries import get_summary
from src.tracks import track_bullets
from src.vocabulary import alias_map

# F8's shape rules. Presentation is a paragraph; achievements is one paragraph long
# enough to carry a flagship achievement.
PRESENTATION_MAX_WORDS = 70
ACHIEVEMENTS_MIN_WORDS = 80
ACHIEVEMENTS_MAX_WORDS = 160

LENGTH = "length"
SHAPE = "shape"
BANNED = "banned"

# F8.3: the bridge is three sentences ideally, four at most, and at most 90 words.
BRIDGE_MAX_SENTENCES = 4
BRIDGE_MAX_WORDS = 90

_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")

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


def voice_notes_for(profile_id: Any, session: Session, language: str) -> str:
    """The register the profile asked for, in this language (F8's voice notes)."""
    entry = get_letter_settings(profile_id, session, language)
    return entry.voice_notes if entry is not None else ""


# --- N8.4: the bridge for one application ------------------------------------------


def letter_settings_for(
    profile_id: Any, session: Session, language: str
) -> LetterSettings | None:
    """The common blocks for the posting's language, or None (F8)."""
    return get_letter_settings(profile_id, session, language)


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


@cache
def _banned_phrases() -> dict[str, tuple[str, ...]]:
    """`banned_phrases.json`: the AI phrasing the bridge must not use, per language (F8.3)."""
    raw = json.loads(Path(__file__).with_name("banned_phrases.json").read_text("utf-8"))
    return {lang: tuple(phrases) for lang, phrases in raw.items()}


def _banned_key(text: str) -> str:
    """Lower-case, unaccented, one space between words, and a straight apostrophe."""
    return fold(text.replace("\u2019", "'").replace("\u2018", "'"))


def banned_phrases(lang: str) -> list[str]:
    """The banned phrases of one language, as written in the data file."""
    return list(_banned_phrases().get(lang, ()))


def banned_in(text: str, lang: str) -> list[str]:
    """Which banned phrases of `lang` the text uses (F8.3).

    Matched case-insensitively on word boundaries after folding whitespace and accents, so
    `Me apasiona` and `LEVERAGE` are found and `leverage` inside `leveraged` is not. The
    phrases come back as the data file spells them, once each, in file order.
    """
    key = _banned_key(text)
    found: list[str] = []
    for phrase in _banned_phrases().get(lang, ()):
        pattern = r"(?<!\w)" + r"\s+".join(re.escape(part) for part in _banned_key(phrase).split())
        if re.search(pattern + r"(?!\w)", key) and phrase not in found:
            found.append(phrase)
    return found


def sentences_in(text: str) -> list[str]:
    """The sentences of a paragraph, split after . ! ? or … and ignoring empty parts."""
    return [part for part in _SENTENCE_END.split(text.strip()) if part.strip()]


def check_bridge(
    output: Mapping[str, Any],
    *,
    sources: Sources,
    template: LetterTemplate,
    jd_text: str,
    company: str | None,
    title: str | None,
    lang: str,
) -> tuple[list[Violation], list[Violation]]:
    """Every rule F8.3 and F8.4 put on one bridge: `(hard, soft)`.

    **Hard** failures mean no paragraph is shown: no own material cited or an id that was
    never supplied, a number, date or name the cited material, the posting, the company
    and the title do not hold (literal preservation, with `__posting__` as an allowed
    source), a company fact without a verbatim posting quote, and a number taken from the
    track's achievements paragraph. **Soft** failures are shown, marked: more than four
    sentences, more than 90 words, a banned phrase.
    """
    text = str(output.get("text") or "")
    cites = [str(value) for value in output.get("sources") or []]
    hard: list[Violation] = []

    # The posting is not the user's material: a bridge must cite at least one of the
    # profile's own bullets, stories or roles *before* `__posting__` is added, or a
    # bridge built only from the posting's own words would pass provenance.
    if not any(cite in sources.ids for cite in cites):
        hard.append(Violation(PROVENANCE, "bridge", "", "the bridge cites none of your material"))
    # The posting, the company and the title are citable for the literal rule: a bridge
    # may name the employer it is writing to (F8.4).
    hard.extend(
        validate(
            {"text": text, "cites": [*cites, "__posting__"]},
            sources=_bridge_sources(sources, jd_text, company, title),
            profile_id=None,
            session=None,
            kind="bullet",
        )
    )
    fact = output.get("company_fact")
    if fact:
        quote = " ".join(str(fact.get("jd_quote") or "").split()).lower()
        if not quote or quote not in " ".join(jd_text.split()).lower():
            hard.append(
                Violation(
                    PROVENANCE,
                    "company_fact",
                    str(fact.get("text") or ""),
                    "the company fact has no verbatim quote from the posting",
                )
            )
    repeated = numbers_in(text) & numbers_in(template.achievements or "")
    if repeated:
        hard.append(
            Violation(
                LITERAL,
                "bridge",
                ", ".join(sorted(repeated)),
                "repeats a number from the template's achievements paragraph",
            )
        )

    soft: list[Violation] = []
    count = len(sentences_in(text))
    if count > BRIDGE_MAX_SENTENCES:
        soft.append(
            Violation(LENGTH, "bridge", text, f"{count} sentences, over {BRIDGE_MAX_SENTENCES}")
        )
    words = len(text.split())
    if words > BRIDGE_MAX_WORDS:
        soft.append(Violation(LENGTH, "bridge", text, f"{words} words, over {BRIDGE_MAX_WORDS}"))
    for phrase in banned_in(text, lang):
        soft.append(Violation(BANNED, "bridge", phrase, f"uses the banned phrase {phrase!r}"))
    return hard, soft


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


# --- N8.4: assembly -----------------------------------------------------------------

# The placeholders, accepted in either language (F8). Kept here and mirrored in
# `src/i18n/strings.py` for the legend; the fill is code, the legend is copy.
PLACEHOLDER_PAIRS: dict[str, tuple[str, ...]] = {
    "role": ("[PUESTO]", "[ROLE]"),
    "company": ("[EMPRESA]", "[COMPANY]"),
    "area": ("[ÁREA]", "[AREA]"),
    "date": ("[FECHA]", "[DATE]"),
}

_MONTHS = {
    "es": (
        "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
        "septiembre", "octubre", "noviembre", "diciembre",
    ),
    "en": (
        "January", "February", "March", "April", "May", "June", "July", "August",
        "September", "October", "November", "December",
    ),
}


def format_date(value: date, language: str) -> str:
    """The date as the language writes it: `27 de septiembre de 2026` / `September 27, 2026`."""
    months = _MONTHS["en"] if language == "en" else _MONTHS["es"]
    if language == "en":
        return f"{months[value.month - 1]} {value.day}, {value.year}"
    return f"{value.day} de {months[value.month - 1]} de {value.year}"


def fill_placeholders(text: str, values: Mapping[str, str | None]) -> tuple[str, list[str]]:
    """Fill the known placeholders; return the text and the keys left unresolved."""
    filled = text
    unresolved: list[str] = []
    for key, tokens in PLACEHOLDER_PAIRS.items():
        value = values.get(key)
        for token in tokens:
            if token not in filled:
                continue
            if value:
                filled = filled.replace(token, value)
            elif key not in unresolved:
                unresolved.append(key)
    return filled, unresolved


def letter_values(
    application: Application, language: str, *, today: date | None = None
) -> dict[str, str | None]:
    """What the placeholders resolve to for one application (F8)."""
    return {
        "role": application.title,
        "company": application.company,
        # The posting's area is not stored per application: the placeholder stays and
        # is highlighted rather than guessed.
        "area": None,
        "date": format_date(today or datetime.now(UTC).date(), language),
    }


def _resolve_blocks(
    raw_blocks: Sequence[str], values: Mapping[str, str | None]
) -> tuple[list[str], list[str]]:
    """Each block with its placeholders filled, and the keys that stayed literal."""
    resolved: list[str] = []
    unresolved: list[str] = []
    for raw in raw_blocks:
        text, missing = fill_placeholders(raw or "", values)
        resolved.append(text.strip())
        for key in missing:
            if key not in unresolved:
                unresolved.append(key)
    return resolved, unresolved


def _before_blocks(
    settings: LetterSettings | None,
    template: LetterTemplate | None,
    values: Mapping[str, str | None],
) -> list[str]:
    """Header · date · greeting · presentation · achievements: what comes before the bridge."""
    return [
        settings.header if settings else "",
        values["date"] or "",
        settings.greeting if settings else "",
        template.presentation if template else "",
        template.achievements if template else "",
    ]


def _after_blocks(settings: LetterSettings | None) -> list[str]:
    """Closing · sign-off: what comes after the bridge."""
    return [settings.closing if settings else "", settings.sign_off if settings else ""]


def assemble_parts(
    *,
    settings: LetterSettings | None,
    template: LetterTemplate | None,
    application: Application,
    language: str,
    today: date | None = None,
) -> dict[str, Any]:
    """The letter up to the bridge and after it, placeholders filled (F8).

    The letter page renders both and lets the browser put the bridge between them, so
    typing in the bridge field needs no round trip. `unresolved` names the placeholder
    keys that stayed literal.
    """
    values = letter_values(application, language, today=today)
    resolved, unresolved = _resolve_blocks(
        [*_before_blocks(settings, template, values), *_after_blocks(settings)], values
    )
    before, after = resolved[:5], resolved[5:]
    return {
        "before": "\n\n".join(block for block in before if block),
        "after": "\n\n".join(block for block in after if block),
        "unresolved": unresolved,
    }


def assemble_letter(
    *,
    settings: LetterSettings | None,
    template: LetterTemplate | None,
    bridge_text: str,
    application: Application,
    language: str,
    today: date | None = None,
) -> dict[str, Any]:
    """The whole letter in F8's order, with placeholders filled (N8.4).

    Header · date · greeting · presentation · achievements · bridge · closing ·
    sign-off. `unresolved` names the placeholder keys that stayed literal, so the page
    can highlight them instead of shipping a blank.
    """
    values = letter_values(application, language, today=today)
    raw_blocks = [
        *_before_blocks(settings, template, values),
        bridge_text,
        *_after_blocks(settings),
    ]
    resolved, unresolved = _resolve_blocks(raw_blocks, values)
    return {"text": "\n\n".join(block for block in resolved if block), "unresolved": unresolved}


def unresolved_placeholders(text: str) -> list[str]:
    """The placeholder keys whose token is still in `text` (a saved or edited letter)."""
    return [
        key for key, tokens in PLACEHOLDER_PAIRS.items() if any(token in text for token in tokens)
    ]


def highlight_placeholders(text: str, unresolved: Sequence[str]) -> str:
    """The letter as HTML with the unresolved placeholders marked (autoescape-safe)."""
    escaped = html.escape(text)
    for key in unresolved:
        for token in PLACEHOLDER_PAIRS[key]:
            escaped = escaped.replace(
                html.escape(token),
                f'<mark class="bg-surface-2 text-sev-warning">{html.escape(token)}</mark>',
            )
    return escaped


# --- N8.5: the deterministic checklist ---------------------------------------------

CHECKLIST_WORD_LIMIT = 420


def letter_checklist(
    *,
    text: str,
    application: Application,
    language: str,
    unresolved: Sequence[str],
    facts_attributed: bool,
    track_lang: str | None = None,
    bridge_text: str = "",
    banned_text: str | None = None,
) -> list[dict[str, Any]]:
    """F8.6's checks, in order, with what each one saw.

    Deterministic and free: it reads the assembled letter, never a model. A check that
    cannot pass is reported as failed, never hidden. `language` is the language the letter
    was written in and `track_lang` the track's, which decides it (F8); `bridge_text` is
    the generated paragraph that the banned-phrase and sentence checks read. A letter
    that was saved has no separate bridge, so its banned-phrase check reads `banned_text`,
    the whole letter.
    """
    words = len(text.split())
    title = (application.title or "").strip()
    company = (application.company or "").strip()
    banned = banned_in(bridge_text if banned_text is None else banned_text, track_lang or language)
    sentences = len(sentences_in(bridge_text))
    return [
        {
            "key": "placeholders",
            "ok": not unresolved,
            "detail": ", ".join(unresolved),
        },
        {"key": "title", "ok": bool(title) and title in text, "detail": title},
        {"key": "company", "ok": bool(company) and company in text, "detail": company},
        {
            "key": "length",
            "ok": words <= CHECKLIST_WORD_LIMIT,
            "detail": f"{words} / {CHECKLIST_WORD_LIMIT}",
        },
        {"key": "facts", "ok": facts_attributed, "detail": ""},
        {
            "key": "language",
            "ok": language in ("es", "en") and language == (track_lang or language),
            "detail": language,
        },
        {"key": "banned", "ok": not banned, "detail": ", ".join(banned)},
        {
            "key": "sentences",
            "ok": sentences <= BRIDGE_MAX_SENTENCES,
            "detail": f"{sentences} / {BRIDGE_MAX_SENTENCES}" if sentences else "",
        },
    ]
