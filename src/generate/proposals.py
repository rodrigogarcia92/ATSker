"""Assembly for generated text (PRD F7.3): what a proposal may claim, and accepting it.

Every function takes `profile_id` first and builds its `Sources` from that profile's
own rows, so a citation outside them is somebody else's row and fails provenance
without a second lookup. On accept the output is validated **again** against the
database's sources: the proposal travelled in a form, and a form is user input.

The writes go through the existing data paths — a summary joins the pool, a bullet
change keeps its old text as a revision (F2.5), a story bullet stores
`source_story_id` — so nothing accepted here bypasses a rule the rest of the app
already enforces.
"""

import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

from sqlalchemy.orm import Session

from src.bullets import bullet_text, create_bullet, get_bullet, list_bullets, update_bullet
from src.generate.validators import Sources, Violation, validate
from src.jd import StructuredJD
from src.models import Application, Bullet, BulletRevision, Profile, Story, Summary, Track
from src.normalize.vocabulary import match_text, resolve_terms
from src.roles import get_role, list_roles
from src.stories import get_story
from src.summaries import create_summary, get_summary, list_summaries
from src.tracks import get_track, set_track_summary, track_bullets
from src.vocabulary import alias_map


def _profile(profile_id: uuid.UUID, session: Session) -> Profile | None:
    # A profile's own id is its key, so the owner-scoped lookup is the row itself.
    return session.get(Profile, profile_id)


def pool_skills(profile_id: uuid.UUID, session: Session) -> frozenset[str]:
    """Every canonical this profile may be credited with: the pool and its bullet tags.

    This is F7.3's rule 3's allowed set. The pool alone is not enough — a skill can
    be tagged on a bullet before the user adds it to their list — and a bullet tag
    alone is not either, because the pool is what the user curated.
    """
    profile = _profile(profile_id, session)
    pool: set[str] = set(profile.skills or []) if profile is not None else set()
    for bullet in list_bullets(profile_id, session, active_only=False):
        pool.update(bullet.skills or [])
    return frozenset(pool)


def report_language(application: Application) -> str:
    """The posting's language, which is the language generated output follows (PRD 8)."""
    report = application.report or {}
    return str((report.get("jd") or {}).get("language") or "es")


def grades_of(application: Application) -> list[dict[str, Any]]:
    """The stored grades, in the shape the validator reads (level, cited bullet id)."""
    return grades_from_report(application.report or {})


def grades_from_report(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        {"level": grade.get("level", 0), "evidence_id": grade.get("bullet_id")}
        for grade in report.get("grades") or []
    ]


BASE_FILE = "file"
BASE_TRACK = "track"
BASE_CV = "cv"
BASE_OTHER_LANGUAGE = "other_language"


@dataclass(frozen=True)
class BaseSummary:
    """The summary the user already has, which a proposal follows and improves (F7.3 rule 3)."""

    text: str
    summary_id: str
    origin: str


def base_summary(
    profile_id: uuid.UUID, session: Session, track: Track, language: str
) -> BaseSummary | None:
    """The base for a proposed summary: one choice, shared by the prompt and the validators.

    In order: the track's summary in `language`; the most recent active pool summary in
    `language` that came from an uploaded CV; the track's summary in the other language
    (the prompt asks for a translation); else none.
    """

    def slot(lang: str) -> Summary | None:
        slot_id = track.summary_en_id if lang == "en" else track.summary_es_id
        entry = get_summary(profile_id, session, slot_id) if slot_id else None
        return entry if entry is not None and entry.text.strip() else None

    own = slot(language)
    if own is not None:
        return BaseSummary(own.text, str(own.id), BASE_TRACK)
    uploaded = [
        entry
        for entry in list_summaries(profile_id, session, lang=language)
        if entry.source_resume_id is not None and entry.text.strip()
    ]
    if uploaded:
        # `list_summaries` is oldest first, so the most recent is the last.
        return BaseSummary(uploaded[-1].text, str(uploaded[-1].id), BASE_CV)
    other = slot("es" if language == "en" else "en")
    if other is not None:
        return BaseSummary(other.text, str(other.id), BASE_OTHER_LANGUAGE)
    return None


def posting_title(application: Application) -> str:
    """The title the summary is written for: the user's copy of it, else the extracted one.

    Never one of the user's own role titles (F7.3 rule 1).
    """
    typed = (application.title or "").strip()
    if typed:
        return typed
    report = application.report or {}
    return str((report.get("jd") or {}).get("title") or "").strip()


def summary_sources(
    profile_id: uuid.UUID,
    session: Session,
    track: Track,
    language: str,
    application: Application,
) -> Sources:
    """The track's bullets, the base summary, and the profile's skills.

    The summary may name a title the user holds (F7.3), so the track's headlines in both
    languages and every stored role title travel as `titles`: they support proper nouns.
    The posting's title joins them, because the summary opens with it. The base summary is
    a source too: it supports the numbers and names the user already wrote.
    """
    bullets = track_bullets(profile_id, session, track.id)
    texts = {str(bullet.id): bullet_text(bullet, language) for bullet in bullets}
    titles = [track.headline_es, track.headline_en, posting_title(application)]
    for role in list_roles(profile_id, session):
        titles.extend((role.title, role.title_es, role.title_en))
    base = base_summary(profile_id, session, track, language)
    return Sources(
        bullets=texts,
        summaries={base.summary_id: base.text} if base is not None else {},
        skills=pool_skills(profile_id, session),
        aliases=alias_map(session),
        titles=tuple(title for title in titles if title),
    )


def bullet_sources(profile_id: uuid.UUID, session: Session, bullet: Bullet) -> Sources:
    """One bullet's both language columns — a translation keeps every number and name."""
    text = " ".join(part for part in (bullet.text_es, bullet.text_en) if part)
    return Sources(
        bullets={str(bullet.id): text},
        skills=pool_skills(profile_id, session),
        aliases=alias_map(session),
    )


def story_sources(
    profile_id: uuid.UUID, session: Session, story: Story, roles: Sequence[Any]
) -> Sources:
    """The story's own body and the roles a derived bullet may cite."""
    titles = {}
    for role in roles:
        titles[str(role.id)] = " ".join(part for part in (role.title_es, role.title_en) if part)
    return Sources(
        stories={str(story.id): story.body},
        roles=titles,
        skills=pool_skills(profile_id, session),
        aliases=alias_map(session),
    )


def summary_validator(
    profile_id: uuid.UUID,
    session: Session,
    application: Application,
    track: Track,
) -> Callable[[Mapping[str, Any]], list[Violation]]:
    """The three validators as a function of the output, with the sources read up front.

    The retry in `propose_summary` runs it between two provider calls, and the client refuses a
    call while the caller holds a transaction, so every read happens here, before the first.
    """
    sources = summary_sources(
        profile_id, session, track, report_language(application), application
    )
    grades = grades_of(application)

    def run(output: Mapping[str, Any]) -> list[Violation]:
        return validate(
            output,
            sources=sources,
            profile_id=profile_id,
            session=session,
            kind="summary",
            grades=grades,
        )

    return run


def check_summary(
    profile_id: uuid.UUID,
    session: Session,
    application: Application,
    track: Track,
    output: Mapping[str, Any],
) -> list[Violation]:
    """The three validators over a Tier-1 proposal, against this application's grades."""
    language = report_language(application)
    return validate(
        output,
        sources=summary_sources(profile_id, session, track, language, application),
        profile_id=profile_id,
        session=session,
        kind="summary",
        grades=grades_of(application),
    )


def accept_summary(
    profile_id: uuid.UUID,
    session: Session,
    application: Application,
    track: Track,
    *,
    text: str,
    cites: Sequence[str],
    use_in_track: bool,
) -> tuple[Summary | None, list[Violation]]:
    """Accept a summary: validate again, then write the pool row and, if asked, the slot.

    The form's text is never trusted. The summary joins the pool in the posting's
    language; with "usar en esta línea" the new pool row becomes the track's summary for
    that language. It never touches the track's skills (F7.5: skills are keywords now).
    """
    if not text.strip():
        return None, [Violation("shape", "summary", "", "the summary is empty")]
    output = {"summary": {"text": text, "cites": list(cites)}}
    violations = check_summary(profile_id, session, application, track, output)
    if violations:
        return None, violations
    language = report_language(application)
    summary = create_summary(profile_id, session, text=text, lang=language)
    if use_in_track:
        set_track_summary(profile_id, session, track.id, lang=language, summary_id=summary.id)
    session.flush()
    return summary, []


@dataclass(frozen=True)
class AttemptSummaryMaterial:
    """Everything `propose_summary` needs for a summary written for one attempt's file (F10.7).

    Built from this profile's own rows and the attempt's stored report, before any provider
    call. `validate` closes over the file's sources, so a cite of the file's own base
    (`summary:attempt-<id>`) or of one of its temporary bullet ids is a supplied source.
    """

    jd: Any
    language: str
    title: str
    bullets: list[tuple[str, str]]
    prompt_grades: list[Mapping[str, Any]]
    base: BaseSummary | None
    pool: frozenset[str]
    track_skills: list[str]
    report: dict[str, Any]
    sources: Sources
    grades: list[dict[str, Any]]
    track: Any

    def validate(self, output: Mapping[str, Any]) -> list[Violation]:
        return validate(
            output,
            sources=self.sources,
            profile_id=None,
            session=None,
            kind="summary",
            grades=self.grades,
        )


def attempt_summary_material(
    profile_id: uuid.UUID,
    session: Session,
    application: Application,
    attempt: Any,
) -> AttemptSummaryMaterial:
    """The sources for a summary of an attempt's file (PRD F10.7).

    The bullets are the file's own (temporary ids included), the grades the attempt's, the base
    the draft's summary when it has one (else F7.3's chain, the track's first) and the closure
    set the profile's pool plus the canonicals of the draft's skills list and of the file's
    bullets. It reads only this profile's rows; the route has already 404'd a foreign id.
    """
    report: dict[str, Any] = dict(attempt.report or {})
    draft = report.get("draft") or {}
    language = report_language(application)
    aliases = alias_map(session)
    title = posting_title(application)
    bullets = [
        (str(row.get("id")), str(row.get("text") or ""))
        for row in report.get("bullets") or []
        if row.get("id") and str(row.get("text") or "").strip()
    ]

    file_skills = set(resolve_terms([str(s) for s in draft.get("skills") or []], aliases)[0])
    for _bullet_id, text in bullets:
        file_skills.update(match_text(text, aliases, skip_ambiguous=True))
    pool = frozenset(pool_skills(profile_id, session) | file_skills)

    track = get_track(profile_id, session, application.track_id) if application.track_id else None
    file_summary = str(draft.get("summary") or "").strip()
    if file_summary:
        base: BaseSummary | None = BaseSummary(
            file_summary, f"attempt-{attempt.id}", BASE_FILE
        )
    else:
        # Without a track the chain starts at the uploaded-CV summaries.
        chain_track = track or SimpleNamespace(summary_es_id=None, summary_en_id=None)
        base = base_summary(profile_id, session, chain_track, language)

    titles = [draft.get("headline"), title]
    if track is not None:
        titles.extend((track.headline_es, track.headline_en))
    titles.extend(str(role.get("title") or "") for role in draft.get("roles") or [])
    for role in list_roles(profile_id, session):
        titles.extend((role.title, role.title_es, role.title_en))
    sources = Sources(
        bullets=dict(bullets),
        summaries={base.summary_id: base.text} if base is not None else {},
        skills=pool,
        aliases=aliases,
        titles=tuple(str(item) for item in titles if item),
    )
    jd_report = {**report, "jd": report.get("jd") or (application.report or {}).get("jd") or {}}
    return AttemptSummaryMaterial(
        jd=StructuredJD.model_validate(jd_report["jd"]),
        language=language,
        title=title,
        bullets=bullets,
        prompt_grades=list(report.get("grades") or []),
        base=base,
        pool=pool,
        track_skills=sorted(file_skills),
        report=jd_report,
        sources=sources,
        grades=grades_from_report(report),
        track=track
        or SimpleNamespace(
            name="",
            headline_es=draft.get("headline"),
            headline_en=draft.get("headline"),
        ),
    )


def check_bullet(
    profile_id: uuid.UUID,
    session: Session,
    bullet: Bullet,
    output: Mapping[str, Any],
) -> list[Violation]:
    return validate(
        output,
        sources=bullet_sources(profile_id, session, bullet),
        profile_id=profile_id,
        session=session,
        kind="bullet",
    )


def accept_bullet(
    profile_id: uuid.UUID,
    session: Session,
    bullet_id: str | uuid.UUID,
    *,
    text: str,
    cites: Sequence[str],
    language: str,
) -> tuple[Bullet | None, list[Violation]]:
    """Accept a rephrased bullet: validate again, then revise the one language column.

    The old text is kept as a revision (F2.5), so nothing is overwritten without one;
    the other language column is untouched.
    """
    bullet = get_bullet(profile_id, session, bullet_id)
    if bullet is None:
        return None, []
    output = {"text": text, "cites": list(cites)}
    violations = check_bullet(profile_id, session, bullet, output)
    if violations:
        return None, violations

    text_en, text_es = bullet.text_en, bullet.text_es
    if language == "en":
        text_en = text.strip()
    else:
        text_es = text.strip()
    session.add(
        # No résumé produced this change, so `resume_id` is NULL — the revision is
        # still append-only history, which is what F2.5 asks for.
        BulletRevision(bullet_id=bullet.id, text_en=bullet.text_en, text_es=bullet.text_es)
    )
    update_bullet(
        profile_id,
        session,
        bullet.id,
        text_en=text_en,
        text_es=text_es,
        chips=bullet.skills,
        active=bullet.active,
    )
    session.flush()
    return bullet, []


def check_story_bullet(
    profile_id: uuid.UUID,
    session: Session,
    story: Story,
    roles: Sequence[Any],
    output: Mapping[str, Any],
) -> list[Violation]:
    return validate(
        output,
        sources=story_sources(profile_id, session, story, roles),
        profile_id=profile_id,
        session=session,
        kind="story_bullets",
    )


def accept_story_bullet(
    profile_id: uuid.UUID,
    session: Session,
    *,
    story_id: str | uuid.UUID,
    role_id: str | uuid.UUID,
    text: str,
    language: str,
    chips: Sequence[str] = (),
) -> tuple[Bullet | None, list[Violation]]:
    """Accept one story-derived bullet: validate again, then create it on the role.

    The bullet stores `source_story_id`, so its provenance is permanent (PRD 3), and
    it joins no track: the user adds it to one deliberately.
    """
    story = get_story(profile_id, session, story_id)
    role = get_role(profile_id, session, role_id)
    if story is None or role is None:
        return None, []
    output = {"bullets": [{"text": text, "story_id": str(story.id), "role_id": str(role.id)}]}
    violations = check_story_bullet(profile_id, session, story, [role], output)
    if violations:
        return None, violations
    bullet = create_bullet(
        profile_id,
        session,
        role_id=role.id,
        text_en=text.strip() if language == "en" else None,
        text_es=text.strip() if language != "en" else None,
        chips=chips,
    )
    bullet.source_story_id = story.id
    session.flush()
    return bullet, []


__all__ = [
    "AttemptSummaryMaterial",
    "BASE_CV",
    "BASE_FILE",
    "BASE_OTHER_LANGUAGE",
    "BASE_TRACK",
    "BaseSummary",
    "accept_bullet",
    "accept_story_bullet",
    "accept_summary",
    "attempt_summary_material",
    "base_summary",
    "bullet_sources",
    "check_bullet",
    "check_story_bullet",
    "check_summary",
    "grades_from_report",
    "grades_of",
    "pool_skills",
    "posting_title",
    "report_language",
    "story_sources",
    "summary_sources",
    "summary_validator",
]
