"""New-in-this-document flags and the change list (PRD F10.5, F10.4 step 4, B.4).

The file was edited outside ATSker, so the F7.3 validators never saw it. This module
points F7.3's own literal-preservation extractor at the file and diffs it against every
stored bullet, story and role: a skill the pool does not hold, a number or a name no
stored row supports, and a role title the master database does not carry. They are
flags, not blockers, and nothing here changes the master database.
"""

import uuid
from collections.abc import Mapping

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.bullets import list_bullets
from src.certifications import list_certifications
from src.education import list_educations
from src.generate.validators import unsupported_claims
from src.ingest.draft import ResumeDraft
from src.models import ApplicationAttempt, Profile
from src.normalize.text import fold, match_key
from src.normalize.vocabulary import match_text
from src.roles import list_roles
from src.stories import list_stories
from src.summaries import list_summaries
from src.tracks import list_tracks
from src.vocabulary import alias_map


def _profile_corpus(
    profile_id: uuid.UUID, session: Session, aliases: Mapping[str, str]
) -> tuple[str, set[str], set[str]]:
    """Every stored word the file's claims are checked against, and the held titles.

    Bullets in both languages, story bodies, and each role's employer and titles — the
    three tables F10.5 names — plus everything else the user stored in words: the pool's
    canonicals and their aliases (so "Science" in "Data Science" is supported), educations,
    certifications, every track's headlines and summaries, and the display name.
    `fold`ed titles come back separately so a title the user already holds is not flagged
    twice, and the canonicals the bullets hold come back so a skill evidenced anywhere is
    not flagged as invented.
    """
    parts: list[str] = []
    held: set[str] = set()
    profile = session.get(Profile, profile_id)
    if profile is not None:
        parts.append(profile.display_name or "")
        pool = set(profile.skills or [])
        parts.extend(pool)
        parts.extend(alias for alias, canonical in aliases.items() if canonical in pool)
    for education in list_educations(profile_id, session):
        parts.extend(
            part for part in (education.institution, education.degree, education.field) if part
        )
    for certification in list_certifications(profile_id, session):
        parts.extend(part for part in (certification.name, certification.issuer) if part)
    summaries = {
        summary.id: summary.text
        for summary in list_summaries(profile_id, session, active_only=False)
    }
    for track in list_tracks(profile_id, session, active_only=False):
        parts.extend(part for part in (track.headline_es, track.headline_en) if part)
        for summary_id in (track.summary_es_id, track.summary_en_id):
            if summary_id in summaries:
                parts.append(summaries[summary_id])
    for bullet in list_bullets(profile_id, session, active_only=True):
        held.update(bullet.skills)
        for text in (bullet.text_es, bullet.text_en):
            if text:
                parts.append(text)
                held.update(match_text(text, aliases))
    for story in list_stories(profile_id, session):
        if story.body:
            parts.append(story.body)
    titles: set[str] = set()
    for role in list_roles(profile_id, session, active_only=True):
        if role.employer:
            parts.append(role.employer)
        for title in (role.title, role.title_es, role.title_en):
            if title:
                parts.append(title)
                titles.add(match_key(title))
    return " ".join(parts), titles, held


def document_flags(
    profile_id: uuid.UUID,
    session: Session,
    *,
    draft: ResumeDraft,
    above_ceiling: bool = False,
) -> dict[str, object]:
    """What the file says that the master database does not (F10.5).

    Flags, not blockers: the user may simply have forgotten to enter something. The
    extractors are F7.3's — the same code that keeps generated text true — so a file
    edited outside ATSker is held to the same rule.
    """
    aliases = alias_map(session)
    corpus, stored_titles, held = _profile_corpus(profile_id, session, aliases)
    profile = session.get(Profile, profile_id)
    if profile is not None:
        held.update(profile.skills)

    # What the file claims: its prose and its employers. Titles are handled separately
    # so an invented role title is not reported twice. The parts are joined with a newline:
    # a bullet's first word begins a sentence, it is not a name in the middle of one.
    scanned = "\n".join(
        [
            draft.headline or "",
            draft.summary or "",
            *(role.employer for role in draft.roles),
            *(bullet.text for role in draft.roles for bullet in role.bullets),
        ]
    )
    named = set(match_text(scanned, aliases, skip_ambiguous=True)) | set(draft.skills)
    title_words = {fold(role.title) for role in draft.roles if role.title}
    claims = [
        token
        for token in unsupported_claims(scanned, corpus, aliases, skip_ambiguous=True)
        if fold(token) not in aliases and fold(token) not in title_words
    ]
    return {
        # A skill the pool does not hold *and* no bullet evidences: the F10.5 flag is an
        # invented skill, not one the user simply has not added to the pool list.
        "skills": sorted(named - held),
        "claims": claims,
        "titles": sorted(
            {
                role.title
                for role in draft.roles
                if role.title and match_key(role.title) not in stored_titles
            }
        ),
        "above_ceiling": above_ceiling,
    }


def keyword_terms(report: Mapping[str, object] | None) -> list[str]:
    """The Keywords card's matched terms of a stored report, in its own wording.

    The card's terms are the posting's labels and carry no annotation (unlike the Skills
    card's), so one is the label as the posting wrote it. A report without the card — an
    old row, or a failed run — has none.
    """
    score = (report or {}).get("score")
    sub_scores = score.get("sub_scores") if isinstance(score, Mapping) else None
    block = (sub_scores or {}).get("keywords") if isinstance(sub_scores, Mapping) else None
    terms = block.get("matched") if isinstance(block, Mapping) else None
    return [str(term) for term in (terms or []) if str(term).strip()]


def new_terms(
    session: Session,
    *,
    flags: Mapping[str, object],
    report: Mapping[str, object],
    compared: Mapping[str, object] | None,
) -> list[str]:
    """What the file names that neither the material nor the compared report held (§12.9).

    Two sources, de-duplicated by canonical (`alias_map`) so one thing is listed once and
    the file's own wording wins: the F10.5 skill flags (a skill the stored material does
    not hold, in the file's words), then the posting's Keywords-card terms that this report
    matches and the report it is compared with (`compared`: the previous attempt, or the
    analysis for attempt 1) did not. The user decides whether it is true — a new CV is
    expected to carry new information — so this is a list, never a verdict.
    """
    aliases = alias_map(session)

    def key(term: str) -> str:
        return aliases.get(fold(term), fold(term))

    was = {key(term) for term in keyword_terms(compared)}
    seen: dict[str, str] = {}
    for term in (str(item) for item in flags.get("skills") or []):
        seen.setdefault(key(term), term)
    for term in keyword_terms(report):
        if key(term) not in was:
            seen.setdefault(key(term), term)
    return list(seen.values())


def change_list(
    previous: Mapping[str, object] | None, current: Mapping[str, object]
) -> dict[str, object]:
    """What changed against the previous attempt (F10.4 step 4).

    Score changes first (`score` for the Job Match, `sub_scores` for each sub-score whose
    integer value moved), then searches that now return the user, gaps closed or opened,
    readability findings fixed or introduced. Empty for the first attempt — there is
    nothing to compare.
    """

    def total(report: Mapping[str, object]) -> int | None:
        score = report.get("score")
        value = score.get("capped") if isinstance(score, Mapping) else None
        return int(value) if isinstance(value, int | float) else None

    def sub_scores(report: Mapping[str, object]) -> dict[str, int]:
        score = report.get("score")
        block = score.get("sub_scores") if isinstance(score, Mapping) else None
        return {
            str(name): round(float(row["value"]) * 100)
            for name, row in (block or {}).items()
            if isinstance(row, Mapping) and isinstance(row.get("value"), int | float)
        }

    def searches(report: Mapping[str, object]) -> dict[str, bool]:
        recall = report.get("recall") or {}
        rows = recall.get("queries") if isinstance(recall, Mapping) else None
        return {
            str(row.get("label") or ""): bool(row.get("passed"))
            for row in (rows or [])
            if isinstance(row, Mapping)
        }

    def gaps(report: Mapping[str, object]) -> set[str]:
        block = report.get("gaps") or {}
        rows = block.get("gaps") if isinstance(block, Mapping) else None
        return {
            str(row.get("requirement") or "") for row in (rows or []) if isinstance(row, Mapping)
        }

    def findings(report: Mapping[str, object]) -> set[str]:
        gate = report.get("gate") or {}
        rows = gate.get("findings") if isinstance(gate, Mapping) else None
        return {str(row.get("check") or "") for row in (rows or []) if isinstance(row, Mapping)}

    if not previous:
        return {}
    was, now = searches(previous), searches(current)
    before_total, after_total = total(previous), total(current)
    before_subs, after_subs = sub_scores(previous), sub_scores(current)
    return {
        "score": (
            {"before": before_total, "after": after_total}
            if before_total is not None
            and after_total is not None
            and before_total != after_total
            else None
        ),
        "sub_scores": [
            {"name": name, "before": before_subs[name], "after": after_subs[name]}
            for name in ("skills", "experience", "title", "keywords")
            if name in before_subs and name in after_subs and before_subs[name] != after_subs[name]
        ],
        "searches_found": sorted(
            label for label, passed in now.items() if passed and not was.get(label)
        ),
        "searches_lost": sorted(
            label for label, passed in was.items() if passed and not now.get(label)
        ),
        "gaps_closed": sorted(gaps(previous) - gaps(current)),
        "gaps_opened": sorted(gaps(current) - gaps(previous)),
        "findings_fixed": sorted(findings(previous) - findings(current)),
        "findings_introduced": sorted(findings(current) - findings(previous)),
    }


def previous_attempt_report(
    profile_id: uuid.UUID,
    session: Session,
    application_id: uuid.UUID,
    *,
    before: int,
) -> dict | None:
    """The most recent finished attempt before this one, for the change list."""
    stmt = (
        select(ApplicationAttempt)
        .where(
            ApplicationAttempt.profile_id == profile_id,
            ApplicationAttempt.application_id == application_id,
            ApplicationAttempt.attempt_no < before,
            ApplicationAttempt.status == "done",
        )
        .order_by(ApplicationAttempt.attempt_no.desc())
        .limit(1)
    )
    row = session.scalar(stmt)
    return dict(row.report) if row is not None and row.report else None


def discard_attempt(attempt: ApplicationAttempt) -> None:
    """Drop the draft but keep the report and its flags (F10.7 "Descartar")."""
    report = dict(attempt.report or {})
    report["draft"] = None
    attempt.report = report
