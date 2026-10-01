"""Importing the other-language CV as a translation (PRD F4.2, 2026-09-27).

A CV uploaded against a track whose CV is written in the other language is not a
second career: it is the same career, said again in the language the posting is in.
The import fills the empty language columns of the rows that already exist — the
bullet's other text, the role's other title, the track's headline and summary — and
everything it cannot match follows F2.5 as an ordinary new candidate.

What the model decides is only *meaning*: which line of the CV says the same thing
as which line of the résumé (`src.extract.pairing`). Which roles are the same job is
a date-and-employer decision, made here, without a provider call — the same line the
project draws everywhere else between the model's judgement and arithmetic.

Nothing is ever overwritten. A column that already holds text keeps it, and the
result counts it as kept.
"""

import calendar
import uuid
from dataclasses import dataclass, field, replace
from datetime import date

from sqlalchemy.orm import Session

from src.bullets import bullet_text, get_bullet, list_bullets
from src.extract.client import CallOptions, Completion, model_configured
from src.extract.pairing import pair_bullets
from src.ingest.draft import DraftBullet, DraftRole, ResumeDraft, parse_partial_date
from src.ingest.merge import MergePlan, MergeResult, Selections, apply_merge, diff_draft
from src.models import Bullet, Role, Track
from src.normalize.text import match_key
from src.roles import list_roles, mirror_title, role_language
from src.tracks import track_bullets

# F4.2: the same job is written with dates that miss each other by months — a
# contractor's notice period, a month-precision extractor, a role written "2019"
# against "2020-01". Three months either way, and a missing end date means today.
DATE_TOLERANCE_MONTHS = 3


def _clean(value: str | None) -> str | None:
    return (value or "").strip() or None


def _shift(day: date, months: int) -> date:
    """`day` moved by whole months, clamped to the last day of its new month."""
    month = day.month - 1 + months
    year = day.year + month // 12
    month = month % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def _overlaps(
    left: tuple[date | None, date | None],
    right: tuple[date | None, date | None],
    *,
    today: date,
    tolerance: int = DATE_TOLERANCE_MONTHS,
) -> bool:
    """Two spellings of one employment period (F4.2).

    A missing end is today — the person still holds the job — and a missing start is
    no lower bound at all, rather than a date invented in 1 A.D. The tolerance is
    applied to both ends, so two months' disagreement about when a job started is
    still one job.
    """
    left_start, left_end = left[0], left[1] or today
    right_start, right_end = right[0], right[1] or today
    if left_start is not None and _shift(left_start, -tolerance) > _shift(right_end, tolerance):
        return False
    if right_start is not None and _shift(right_start, -tolerance) > _shift(left_end, tolerance):
        return False
    return True


def track_roles(profile_id: uuid.UUID, session: Session, track: Track) -> list[Role]:
    """The roles the track's selection draws from, most recent first.

    A track owns no roles — it selects bullets — so the roles a translation import
    can match are the ones its bullets came from. A role whose bullets are all
    deactivated is not in the selection and cannot be matched.
    """
    role_ids = {bullet.role_id for bullet in track_bullets(profile_id, session, track.id)}
    return [
        role for role in list_roles(profile_id, session, active_only=True) if role.id in role_ids
    ]


def matched_roles(
    profile_id: uuid.UUID,
    session: Session,
    *,
    track: Track,
    draft: ResumeDraft,
    today: date | None = None,
) -> tuple[tuple[Role, DraftRole], ...]:
    """The role each draft role is the same job as (F4.2), in the draft's order.

    Deterministic: employer equality on `match_key` and overlapping dates, nothing else. Each
    existing role is consumed by at most one draft role, so a document with two
    spellings of one job pairs the first and leaves the second to F2.5 as a new
    candidate rather than filling the same columns twice.
    """
    day = today or date.today()
    remaining = track_roles(profile_id, session, track)
    matches: list[tuple[Role, DraftRole]] = []
    for draft_role in draft.roles:
        employer = match_key(draft_role.employer)
        if not employer:
            continue
        span = (parse_partial_date(draft_role.start_date), parse_partial_date(draft_role.end_date))
        for role in remaining:
            if match_key(role.employer) != employer:
                continue
            if not _overlaps((role.start_date, role.end_date), span, today=day):
                continue
            remaining.remove(role)
            matches.append((role, draft_role))
            break
    return tuple(matches)


def translation_available(
    profile_id: uuid.UUID,
    session: Session,
    *,
    track: Track | None,
    draft: ResumeDraft,
) -> bool:
    """F4.2: the option exists when a tagged track is in the other language, a model
    can answer, and at least one role of the document is a job the track holds."""
    if track is None or not model_configured():
        return False
    if (draft.language if draft.language == "en" else "es") == (
        track.lang if track.lang == "en" else "es"
    ):
        return False
    return bool(matched_roles(profile_id, session, track=track, draft=draft))


@dataclass(frozen=True)
class PairedBullet:
    """One proposed pair: the line that exists, the CV's line, and the column."""

    existing_id: uuid.UUID
    existing_text: str
    draft_text: str
    column: str
    current: str | None
    index: int


@dataclass(frozen=True)
class RoleTranslation:
    role: Role
    draft_role: DraftRole
    pairs: tuple[PairedBullet, ...] = ()
    unpaired: tuple[DraftBullet, ...] = ()


@dataclass(frozen=True)
class TranslationPlan:
    """What the translation screen shows, and what applying it would write.

    `draft` is the document reduced to what is *not* a translation — the unmatched
    roles whole and each matched role's unpaired bullets under the existing role's
    own title and dates, so the ordinary F2.5 diff matches the row instead of
    inventing one — and `plan` is that diff. The screen shows one form over both.
    """

    matches: tuple[RoleTranslation, ...] = ()
    draft: ResumeDraft = field(default_factory=ResumeDraft)
    plan: MergePlan = field(default_factory=MergePlan)
    calls: tuple[Completion, ...] = ()
    column: str = "en"

    @property
    def pairs(self) -> tuple[PairedBullet, ...]:
        return tuple(pair for match in self.matches for pair in match.pairs)


def plan_translation(
    profile_id: uuid.UUID,
    session: Session,
    *,
    track: Track,
    draft: ResumeDraft,
    model: str | None = None,
    options: CallOptions | None = None,
    today: date | None = None,
) -> TranslationPlan:
    """Match the roles, ask the model which lines pair, and reduce the draft.

    One provider call per matched role — the pairing is about meaning, and two roles
    of the same document are different pairs of lists. Nothing is held across the
    calls: the caller commits before this runs and after it, like every provider
    path in the project.
    """
    column = "en" if draft.language == "en" else "es"
    index = 0
    calls: list[Completion] = []
    matches: list[RoleTranslation] = []
    reduced: list[DraftRole] = []
    matched = matched_roles(profile_id, session, track=track, draft=draft, today=today)

    for role, draft_role in matched:
        existing = [
            bullet
            for bullet in list_bullets(profile_id, session, role_id=role.id, active_only=True)
        ]
        # The existing side is read in the track's language — that is the CV the
        # track presents — and the draft's side is what the CV says, in its own.
        existing_texts = [bullet_text(bullet, track.lang) for bullet in existing]
        draft_texts = [bullet.text.strip() for bullet in draft_role.bullets]
        distinct_existing = len(set(existing_texts)) == len(existing_texts)
        pairs: list[PairedBullet] = []
        if existing_texts and draft_texts and distinct_existing:
            # The reads above are the whole input of the call below, so the
            # transaction ends here — nothing is ever held across a provider call,
            # and the next role's reads open their own.
            session.commit()
            report = pair_bullets(
                session,
                existing=existing_texts,
                draft=draft_texts,
                lang_existing=track.lang if track.lang == "en" else "es",
                lang_draft=column,
                model=model,
                options=options,
            )
            calls.extend(report.calls)
            paired_draft = set()
            for pair in report.pairs:
                bullet = existing[pair.existing]
                pairs.append(
                    PairedBullet(
                        existing_id=bullet.id,
                        existing_text=existing_texts[pair.existing],
                        draft_text=draft_texts[pair.draft],
                        column=column,
                        current=_clean(getattr(bullet, f"text_{column}")),
                        index=index,
                    )
                )
                paired_draft.add(pair.draft)
                index += 1
            unpaired = tuple(
                bullet for position, bullet in enumerate(draft_role.bullets)
                if position not in paired_draft
            )
        else:
            unpaired = tuple(draft_role.bullets)
        matches.append(
            RoleTranslation(
                role=role, draft_role=draft_role, pairs=tuple(pairs), unpaired=unpaired
            )
        )
        if unpaired:
            # The existing role's own title and dates: the diff must find this row
            # and write nothing to it, so only the new bullets are candidates.
            reduced.append(
                draft_role.model_copy(
                    update={
                        "title": role.title,
                        "start_date": role.start_date.isoformat() if role.start_date else None,
                        "end_date": role.end_date.isoformat() if role.end_date else None,
                        "bullets": list(unpaired),
                    }
                )
            )

    matched_ids = {id(draft_role) for _, draft_role in matched}
    reduced.extend(
        draft_role for draft_role in draft.roles if id(draft_role) not in matched_ids
    )
    reduced_draft = draft.model_copy(update={"roles": reduced})
    return TranslationPlan(
        matches=tuple(matches),
        draft=reduced_draft,
        plan=diff_draft(profile_id, session, reduced_draft),
        calls=tuple(calls),
        column=column,
    )


@dataclass(frozen=True)
class TranslationSelections:
    """What the user ticked: the confirmed pairs, and the ordinary F2.5 boxes."""

    pairs: frozenset[int] = frozenset()
    merge: Selections = Selections()


def apply_translation(
    profile_id: uuid.UUID,
    session: Session,
    *,
    resume_id: uuid.UUID,
    plan: TranslationPlan,
    selections: TranslationSelections,
) -> MergeResult | None:
    """Write the confirmed pairs and the ordinary candidates; None if not owned.

    A pair fills the empty column of its bullet and nothing else: a column that
    already holds text keeps it, whether or not it differs from the CV's wording, and
    is counted kept. A matched role's empty title in the CV's language is filled the
    same way, and `title` is re-derived by `roles`' own rule rather than patched.
    The headline, the summary pool and the new bullets are `apply_merge`'s work —
    the reduced draft is a document in the CV's language like any other.
    """
    if selections.pairs:
        for pair in plan.pairs:
            if pair.index not in selections.pairs:
                continue
            bullet: Bullet | None = get_bullet(profile_id, session, pair.existing_id)
            if bullet is None:
                continue
            current = _clean(getattr(bullet, f"text_{pair.column}"))
            if current is None:
                setattr(bullet, f"text_{pair.column}", pair.draft_text)
            # A filled column is never touched; the count is the result's, not a write.
        session.flush()

    result = apply_merge(
        profile_id,
        session,
        resume_id=resume_id,
        draft=plan.draft,
        plan=plan.plan,
        selections=selections.merge,
    )
    if result is None:
        return None

    filled = sum(
        1
        for pair in plan.pairs
        if pair.index in selections.pairs and pair.current is None
    )
    kept = len(
        [
            pair
            for pair in plan.pairs
            if pair.index in selections.pairs
            and pair.current is not None
            and pair.current != pair.draft_text
        ]
    )
    for match in plan.matches:
        title = _clean(getattr(match.role, f"title_{plan.column}"))
        wanted = _clean(match.draft_role.title)
        if title is None and wanted is not None:
            setattr(match.role, f"title_{plan.column}", wanted)
            match.role.title = mirror_title(
                match.role.title_es,
                match.role.title_en,
                role_language(profile_id, session, match.role.id),
            )
            filled += 1
    session.flush()
    return replace(result, translations_filled=filled, translations_kept=kept)
