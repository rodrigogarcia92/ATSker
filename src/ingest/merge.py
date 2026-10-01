"""The F2.5 merge: diff a reviewed draft against the master database, then apply it.

Diffing is deterministic and explainable, and never overwrites anything silently:

* a role matches an existing role by folded employer and title; it is *changed*
  when its dates differ or when it had been deactivated;
* a bullet matches by folded text — *unchanged* — or, failing that, by token
  overlap with a bullet of the same role — *changed*, and the review screen shows
  the old wording beside the new one; everything else is *new*;
* education and certifications match by folded name, so a second upload of the
  same document diffs as unchanged rather than duplicating rows.

Nothing here is inferred: the merge writes what the user ticked, and a changed
bullet's superseded text lands in `bullet_revisions` before the row is updated.

Every merge ends in a track (F2.7): tagged joins, untagged creates one named after
the file, and the track is filled from the document — headline, summary, skills —
without ever overwriting what it already has.
"""

import uuid
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal

from sqlalchemy.orm import Session

from src.bullets import bullet_text, create_bullet, get_bullet, list_bullets, update_bullet
from src.certifications import create_certification, list_certifications, update_certification
from src.education import create_education, list_educations, update_education
from src.i18n import t
from src.ingest.draft import DraftCertification, DraftEducation, ResumeDraft, parse_partial_date
from src.models import (
    Bullet,
    BulletRevision,
    Certification,
    Education,
    Profile,
    Role,
    Summary,
    Track,
    TrackBullet,
)
from src.normalize.text import fold, match_key
from src.resumes import get_resume, mark_merged
from src.roles import create_role, get_role, list_roles, update_role
from src.summaries import create_summary, list_summaries
from src.tracks import create_track, get_track, set_track_bullets, track_bullets

Label = Literal["new", "changed", "unchanged"]

# A draft bullet is a changed version of an existing one when this share of their
# folded token sets overlaps. 0.6 separates "reduje el tiempo de reporte en un 30%
# con python" (changed) from a different achievement that shares a verb (new).
BULLET_SIMILARITY = 0.6

# The headline slots are String(200) and both the note and the review warning name
# the limit out loud, so it is read from the column rather than written twice and
# drifting from the schema.
HEADLINE_LIMIT = Track.__table__.c.headline_es.type.length


@dataclass(frozen=True)
class BulletCandidate:
    label: Label
    text: str
    chips: tuple[str, ...]
    existing_id: uuid.UUID | None = None
    old_text: str | None = None  # set when the wording changes
    reactivates: bool = False


@dataclass(frozen=True)
class RoleCandidate:
    label: Label
    employer: str
    title: str
    start_date: date | None
    end_date: date | None
    existing_id: uuid.UUID | None = None
    dates_changed: bool = False
    reactivates: bool = False
    bullets: tuple[BulletCandidate, ...] = ()


@dataclass(frozen=True)
class EducationCandidate:
    label: Label
    institution: str
    award: str | None
    field: str | None
    start_date: date | None
    end_date: date | None
    needs_review: bool = False
    existing_id: uuid.UUID | None = None
    changes: tuple[str, ...] = ()


@dataclass(frozen=True)
class CertificationCandidate:
    label: Label
    name: str
    issuer: str | None
    issued_date: date | None
    expiry_date: date | None
    credential_id: str | None
    credential_url: str | None
    needs_review: bool = False
    existing_id: uuid.UUID | None = None
    changes: tuple[str, ...] = ()


@dataclass(frozen=True)
class SkillCandidate:
    label: Label
    canonical: str


@dataclass(frozen=True)
class MergePlan:
    roles: tuple[RoleCandidate, ...] = ()
    educations: tuple[EducationCandidate, ...] = ()
    certifications: tuple[CertificationCandidate, ...] = ()
    skills: tuple[SkillCandidate, ...] = ()

    def label_counts(self) -> dict[str, int]:
        buckets = {"new": 0, "changed": 0, "unchanged": 0}
        for item in [*self.roles, *self.educations, *self.certifications, *self.skills]:
            buckets[item.label] += 1
        for role in self.roles:
            for bullet in role.bullets:
                buckets[bullet.label] += 1
        return buckets


@dataclass(frozen=True)
class Selections:
    """What the user ticked, by index into `MergePlan`; absent means skip."""

    roles: frozenset[int] = frozenset()
    bullets: frozenset[tuple[int, int]] = frozenset()
    educations: frozenset[int] = frozenset()
    certifications: frozenset[int] = frozenset()
    skills: frozenset[int] = frozenset()


@dataclass(frozen=True)
class MergeResult:
    roles_created: int = 0
    roles_updated: int = 0
    bullets_created: int = 0
    bullets_updated: int = 0
    educations_created: int = 0
    educations_updated: int = 0
    certifications_created: int = 0
    certifications_updated: int = 0
    skills_added: int = 0
    skipped: int = 0
    # Bullets appended to the track this résumé was tagged with (F4 path 1).
    track_bullets_added: int = 0
    # Skills appended to the landed track's selection (F2.7's auto-fill).
    track_skills_added: int = 0
    # What the auto-fill wrote, and what it left alone because the track already had
    # it (F2.7): a headline or summary somebody chose is never replaced.
    track_headline_filled: bool = False
    track_headline_kept: bool = False
    track_summary_filled: bool = False
    track_summary_kept: bool = False
    # The track this merge landed in (F2.7): every merge ends in one — created here,
    # or joined because the upload was tagged with it.
    track_id: uuid.UUID | None = None
    track_created: bool = False
    # F4.2's translation import: the columns a confirmed pair filled, the pairs whose
    # column already held different text, and — with the bullets created above — the
    # filled / kept / new the translation result page reports. They count as writes:
    # an import whose only action was filling columns did something.
    translations_filled: int = 0
    translations_kept: int = 0
    # A draft headline longer than the column is never written and never truncated:
    # a cut sentence says something else. (characters, limit) is the note both
    # screens render in either language; `note` is its English form.
    headline_not_set: tuple[int, int] | None = None

    # The counter fields, for the two questions below. `track_id` and `track_created`
    # are deliberately not among them: they report an artefact, not a count.
    COUNTERS = (
        "roles_created",
        "roles_updated",
        "bullets_created",
        "bullets_updated",
        "educations_created",
        "educations_updated",
        "certifications_created",
        "certifications_updated",
        "skills_added",
        "skipped",
        "track_bullets_added",
        "track_skills_added",
        "translations_filled",
        "translations_kept",
    )

    @property
    def note(self) -> str | None:
        """The note in English; the screens localize it from `headline_not_set`."""
        if self.headline_not_set is None:
            return None
        characters, limit = self.headline_not_set
        return t("import.headline_not_set", "en", count=characters, limit=limit)

    @property
    def is_empty(self) -> bool:
        """True when the merge wrote nothing at all (F2.5) — not even a track.

        A screen that renders this as a blank summary reads as a failed page; the
        result has to say that the database is unchanged, on purpose. A "kept" flag
        is not a write: it is what the merge left alone.
        """
        return (
            not self.track_created
            and not self.track_headline_filled
            and not self.track_summary_filled
            and not any(getattr(self, name) for name in self.COUNTERS)
        )


def _tokens(text: str) -> frozenset[str]:
    return frozenset(token for token in fold(text).split() if len(token) > 1)


def _similarity(left: frozenset[str], right: frozenset[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _role_titles(role: Role) -> set[str]:
    """Every non-empty title the role carries, folded (F4.2).

    `title` holds one language — the role's primary one — so the document of the
    other language names the same job only through `title_es`/`title_en`. A row
    from before the split carries `title` alone and is indexed by it.
    """
    return {match_key(title) for title in (role.title, role.title_es, role.title_en) if title}


def _role_index(roles: list[Role]) -> dict[str, Role]:
    """Folded employer+any title → the role to match; the active, most recent wins.

    One role is indexed under each of its titles: reached through two of them it is
    still one row, and two roles sharing a key are separated by the same preference
    whichever key found them (F2.5, F4.2).
    """
    index: dict[str, Role] = {}
    for role in roles:
        employer = match_key(role.employer)
        for title in _role_titles(role):
            key = f"{employer}\x00{title}"
            current = index.get(key)
            if current is None or (role.active, role.start_date or date.min) > (
                current.active,
                current.start_date or date.min,
            ):
                index[key] = role
    return index


def _education_changes(
    existing: Education,
    raw: DraftEducation,
    start_date: date | None,
    end_date: date | None,
) -> tuple[str, ...]:
    """Which fields a matched education entry differs in, for the merge screen."""
    changed: list[str] = []
    if existing.institution != raw.institution:
        changed.append("institution")
    if existing.degree != raw.award:
        changed.append("award")
    if existing.field != raw.field:
        changed.append("field")
    if existing.start_date != start_date or existing.end_date != end_date:
        changed.append("dates")
    return tuple(changed)


def _certification_changes(
    existing: Certification,
    raw: DraftCertification,
    issued_date: date | None,
    expiry_date: date | None,
) -> tuple[str, ...]:
    changed: list[str] = []
    if existing.name != raw.name:
        changed.append("name")
    if existing.issuer != raw.issuer:
        changed.append("issuer")
    if existing.issued_date != issued_date or existing.expiry_date != expiry_date:
        changed.append("dates")
    if existing.credential_id != raw.credential_id or existing.credential_url != raw.credential_url:
        changed.append("credential")
    return tuple(changed)


def _bullet_candidates(draft_bullets, existing: list[Bullet]) -> tuple[BulletCandidate, ...]:
    unused = list(existing)
    candidates: list[BulletCandidate] = []
    for draft_bullet in draft_bullets:
        text = draft_bullet.text
        identical = next(
            (bullet for bullet in unused if match_key(bullet_text(bullet)) == match_key(text)),
            None,
        )
        if identical is not None:
            unused.remove(identical)
            candidates.append(
                BulletCandidate(
                    label="changed" if not identical.active else "unchanged",
                    text=text,
                    chips=tuple(draft_bullet.chips),
                    existing_id=identical.id,
                    reactivates=not identical.active,
                )
            )
            continue

        wanted = _tokens(text)
        best: Bullet | None = None
        best_score = 0.0
        for bullet in unused:
            score = _similarity(wanted, _tokens(bullet_text(bullet)))
            if score > best_score:
                best, best_score = bullet, score
        if best is not None and best_score >= BULLET_SIMILARITY:
            unused.remove(best)
            candidates.append(
                BulletCandidate(
                    label="changed",
                    text=text,
                    chips=tuple(draft_bullet.chips),
                    existing_id=best.id,
                    old_text=bullet_text(best),
                    reactivates=not best.active,
                )
            )
        else:
            candidates.append(
                BulletCandidate(label="new", text=text, chips=tuple(draft_bullet.chips))
            )
    return tuple(candidates)


def _role_candidates(
    profile_id: uuid.UUID, session: Session, draft: ResumeDraft
) -> tuple[RoleCandidate, ...]:
    index = _role_index(list_roles(profile_id, session, active_only=False))
    bullets = list_bullets(profile_id, session, active_only=False)
    candidates: list[RoleCandidate] = []
    for raw in draft.roles:
        start_date = parse_partial_date(raw.start_date)
        end_date = parse_partial_date(raw.end_date)
        existing = index.get(f"{match_key(raw.employer)}\x00{match_key(raw.title)}")
        if existing is None:
            candidates.append(
                RoleCandidate(
                    label="new",
                    employer=raw.employer,
                    title=raw.title,
                    start_date=start_date,
                    end_date=end_date,
                    bullets=_bullet_candidates(raw.bullets, []),
                )
            )
            continue
        same_dates = existing.start_date == start_date and existing.end_date == end_date
        candidates.append(
            RoleCandidate(
                label="unchanged" if same_dates and existing.active else "changed",
                employer=raw.employer,
                title=raw.title,
                start_date=start_date,
                end_date=end_date,
                existing_id=existing.id,
                dates_changed=not same_dates,
                reactivates=not existing.active,
                bullets=_bullet_candidates(
                    raw.bullets, [bullet for bullet in bullets if bullet.role_id == existing.id]
                ),
            )
        )
    return tuple(candidates)


def _education_candidates(
    profile_id: uuid.UUID, session: Session, draft: ResumeDraft
) -> tuple[EducationCandidate, ...]:
    index = {
        f"{fold(entry.institution)}\x00{fold(entry.degree or '')}": entry
        for entry in list_educations(profile_id, session)
    }
    candidates: list[EducationCandidate] = []
    for raw in draft.educations:
        start_date = parse_partial_date(raw.start_date)
        end_date = parse_partial_date(raw.end_date)
        existing = index.get(f"{fold(raw.institution)}\x00{fold(raw.award or '')}")
        if existing is None:
            candidates.append(
                EducationCandidate(
                    label="new",
                    institution=raw.institution,
                    award=raw.award,
                    field=raw.field,
                    start_date=start_date,
                    end_date=end_date,
                    needs_review=raw.needs_review,
                )
            )
            continue
        same = _education_changes(existing, raw, start_date, end_date)
        candidates.append(
            EducationCandidate(
                label="unchanged" if not same else "changed",
                institution=raw.institution,
                award=raw.award,
                field=raw.field,
                start_date=start_date,
                end_date=end_date,
                needs_review=raw.needs_review,
                existing_id=existing.id,
                changes=same,
            )
        )
    return tuple(candidates)


def _certification_candidates(
    profile_id: uuid.UUID, session: Session, draft: ResumeDraft
) -> tuple[CertificationCandidate, ...]:
    index = {
        f"{fold(entry.name)}\x00{fold(entry.issuer or '')}": entry
        for entry in list_certifications(profile_id, session)
    }
    candidates: list[CertificationCandidate] = []
    for raw in draft.certifications:
        issued_date = parse_partial_date(raw.issued_date)
        expiry_date = parse_partial_date(raw.expiry_date)
        existing = index.get(f"{fold(raw.name)}\x00{fold(raw.issuer or '')}")
        if existing is None:
            candidates.append(
                CertificationCandidate(
                    label="new",
                    name=raw.name,
                    issuer=raw.issuer,
                    issued_date=issued_date,
                    expiry_date=expiry_date,
                    credential_id=raw.credential_id,
                    credential_url=raw.credential_url,
                    needs_review=raw.needs_review,
                )
            )
            continue
        same = _certification_changes(existing, raw, issued_date, expiry_date)
        candidates.append(
            CertificationCandidate(
                label="unchanged" if not same else "changed",
                name=raw.name,
                issuer=raw.issuer,
                issued_date=issued_date,
                expiry_date=expiry_date,
                credential_id=raw.credential_id,
                credential_url=raw.credential_url,
                needs_review=raw.needs_review,
                existing_id=existing.id,
                changes=same,
            )
        )
    return tuple(candidates)


def _skill_candidates(profile: Profile, draft: ResumeDraft) -> tuple[SkillCandidate, ...]:
    existing = {fold(skill) for skill in profile.skills}
    return tuple(
        SkillCandidate(label="unchanged" if fold(skill) in existing else "new", canonical=skill)
        for skill in draft.skills
    )


def diff_draft(profile_id: uuid.UUID, session: Session, draft: ResumeDraft) -> MergePlan:
    """Everything the draft would do to the master database, labelled and checkable."""
    profile = session.get(Profile, profile_id)
    if profile is None:
        raise RuntimeError("a merge needs a profile that exists")
    return MergePlan(
        roles=_role_candidates(profile_id, session, draft),
        educations=_education_candidates(profile_id, session, draft),
        certifications=_certification_candidates(profile_id, session, draft),
        skills=_skill_candidates(profile, draft),
    )


def _text_columns(language: str, text: str) -> tuple[str | None, str | None]:
    """(text_en, text_es) for a bullet written in the document's language."""
    return (text, None) if language == "en" else (None, text)


def _title_columns(
    existing: Role | None, language: str, title: str
) -> tuple[str | None, str | None]:
    """(title_en, title_es) for a role written from a document (F4.2).

    The document carries one title, in its own language: that is the column it fills.
    The other column keeps whatever the row already held — a translation somebody
    typed is not something this document brought, so it is never replaced by the
    empty half of the pair. A new role has nothing to keep, and gets one column.
    """
    provided_en, provided_es = _text_columns(language, title)
    if existing is None:
        return provided_en, provided_es
    return (
        provided_en if provided_en is not None else existing.title_en,
        provided_es if provided_es is not None else existing.title_es,
    )


def _contributed_bullet_ids(
    plan: MergePlan, new_bullet_ids: dict[tuple[int, int], uuid.UUID]
) -> list[uuid.UUID]:
    """The bullets this document contributes, in document order (F4 path 1).

    A new bullet exists only if the user ticked it — the others were never created —
    while a matched bullet joins whether or not it was ticked, because it is already
    in the master database and this document says it belongs to the résumé's shape.
    """
    contributed: list[uuid.UUID] = []
    for index, role in enumerate(plan.roles):
        for bullet_index, bullet in enumerate(role.bullets):
            if bullet.label == "new":
                created_id = new_bullet_ids.get((index, bullet_index))
                if created_id is not None:
                    contributed.append(created_id)
                continue
            if bullet.existing_id is not None:
                contributed.append(bullet.existing_id)
    return contributed


def apply_merge(
    profile_id: uuid.UUID,
    session: Session,
    *,
    resume_id: uuid.UUID,
    draft: ResumeDraft,
    plan: MergePlan,
    selections: Selections,
    track_name: str | None = None,
) -> MergeResult | None:
    """Write the ticked candidates; None when the résumé belongs to someone else.

    Every merge ends in a track (F2.7): a résumé tagged with one joins it, appending
    to the selection and never replacing it, and an untagged one becomes a track named
    `track_name` — the file's stem when absent. A new bullet enters the selection only
    if the user ticked it — the others do not exist — while a matched bullet enters it
    whether or not it was ticked, because it is already in the master database and
    this document says it belongs to the résumé's shape.

    The track is filled from the document, never overwritten by it (F2.7): the
    confirmed skills are appended de-duplicated, and the headline and the pool summary
    are set only where that language's slot is empty. The summary enters the profile's
    pool whatever the track does with it.
    """
    resume = get_resume(profile_id, session, resume_id)
    profile = session.get(Profile, profile_id)
    if resume is None or profile is None:
        return None

    counts = {name: 0 for name in MergeResult.COUNTERS}
    # Which bullets this merge created, by plan position: the track's selection needs
    # the ids, and only the ticked ones exist.
    new_bullet_ids: dict[tuple[int, int], uuid.UUID] = {}

    role_ids: dict[int, uuid.UUID] = {}
    for index, role in enumerate(plan.roles):
        if index not in selections.roles:
            continue
        if role.label == "new":
            # F4.2: the document's title is the one title it carries, so it goes into
            # the column of the document's language. `title` is derived from both, as
            # it always was.
            title_en, title_es = _title_columns(None, draft.language, role.title)
            created = create_role(
                profile_id,
                session,
                employer=role.employer,
                title_es=title_es,
                title_en=title_en,
                start_date=role.start_date,
                end_date=role.end_date,
                language=draft.language,
            )
            counts["roles_created"] += 1
            role_ids[index] = created.id
        elif role.label == "changed":
            # The document's title fills its own language's column; the other column
            # keeps what the row holds (F4.2) — a merge never replaces a translation
            # it did not bring.
            title_en, title_es = _title_columns(
                get_role(profile_id, session, role.existing_id)
                if role.existing_id is not None
                else None,
                draft.language,
                role.title,
            )
            updated = update_role(
                profile_id,
                session,
                role.existing_id,
                employer=role.employer,
                title_es=title_es,
                title_en=title_en,
                start_date=role.start_date,
                end_date=role.end_date,
                active=True,
                language=draft.language,
            )
            if updated is not None:
                counts["roles_updated"] += 1
                role_ids[index] = updated.id
        else:
            # Unchanged: nothing to write, but its bullets may still need the id.
            role_ids[index] = role.existing_id

    for index, role in enumerate(plan.roles):
        for bullet_index, bullet in enumerate(role.bullets):
            if (index, bullet_index) not in selections.bullets:
                continue
            if index not in role_ids:
                # A bullet cannot exist without its role; the plan says so, and the
                # result counts it as skipped rather than dropping it silently.
                counts["skipped"] += 1
                continue
            text_en, text_es = _text_columns(draft.language, bullet.text)
            if bullet.label == "new":
                created_bullet = create_bullet(
                    profile_id,
                    session,
                    role_id=role_ids[index],
                    text_en=text_en,
                    text_es=text_es,
                    chips=bullet.chips,
                )
                # Provenance (F2.8): which CV created this bullet, so "only this CV
                # contributed" can delete it later. Matched and changed bullets keep
                # whatever provenance they already carry.
                created_bullet.source_resume_id = resume.id
                counts["bullets_created"] += 1
                new_bullet_ids[(index, bullet_index)] = created_bullet.id
            elif bullet.label == "changed":
                existing = get_bullet(profile_id, session, bullet.existing_id)
                if existing is None:
                    counts["skipped"] += 1
                    continue
                # A document carries one language, so it rewrites that column and
                # leaves the other alone (F4.2): the draft's `None` half is "this
                # document says nothing about that language", never "erase it".
                if draft.language == "en":
                    text_es = existing.text_es
                else:
                    text_en = existing.text_en
                if bullet.old_text is not None:
                    session.add(
                        BulletRevision(
                            bullet_id=existing.id,
                            text_en=existing.text_en,
                            text_es=existing.text_es,
                            resume_id=resume.id,
                        )
                    )
                update_bullet(
                    profile_id,
                    session,
                    bullet.existing_id,
                    text_en=text_en,
                    text_es=text_es,
                    chips=bullet.chips,
                    active=True,
                )
                counts["bullets_updated"] += 1

    for index, education in enumerate(plan.educations):
        if index not in selections.educations:
            continue
        if not education.institution.strip():
            counts["skipped"] += 1
            continue
        if education.label == "new":
            create_education(
                profile_id,
                session,
                institution=education.institution,
                degree=education.award,
                field=education.field,
                start_date=education.start_date,
                end_date=education.end_date,
            )
            counts["educations_created"] += 1
        elif education.label == "changed":
            update_education(
                profile_id,
                session,
                education.existing_id,
                institution=education.institution,
                degree=education.award,
                field=education.field,
                start_date=education.start_date,
                end_date=education.end_date,
            )
            counts["educations_updated"] += 1

    for index, certification in enumerate(plan.certifications):
        if index not in selections.certifications:
            continue
        if not certification.name.strip():
            counts["skipped"] += 1
            continue
        if certification.label == "new":
            create_certification(
                profile_id,
                session,
                name=certification.name,
                issuer=certification.issuer,
                issued_date=certification.issued_date,
                expiry_date=certification.expiry_date,
                credential_id=certification.credential_id,
                credential_url=certification.credential_url,
            )
            counts["certifications_created"] += 1
        elif certification.label == "changed":
            update_certification(
                profile_id,
                session,
                certification.existing_id,
                name=certification.name,
                issuer=certification.issuer,
                issued_date=certification.issued_date,
                expiry_date=certification.expiry_date,
                credential_id=certification.credential_id,
                credential_url=certification.credential_url,
            )
            counts["certifications_updated"] += 1

    current = list(profile.skills)
    for index, skill in enumerate(plan.skills):
        if index not in selections.skills or skill.label == "unchanged":
            continue
        if skill.canonical not in current:
            current.append(skill.canonical)
            counts["skills_added"] += 1
    profile.skills = current

    # F2.7: the document's summary joins the profile's pool whatever the track does
    # with it. The pool matches after folding — case, accents and whitespace are not
    # a new summary — so the same text is never pooled twice for a profile and
    # language, and the matched row is reused as it is.
    lang = draft.language if draft.language == "en" else "es"
    summary_text = " ".join((draft.summary or "").split()).strip()
    pooled: Summary | None = None
    if summary_text:
        wanted = fold(summary_text)
        pooled = next(
            (
                entry
                for entry in list_summaries(profile_id, session, lang=lang)
                if fold(entry.text) == wanted
            ),
            None,
        )
        if pooled is None:
            pooled = create_summary(
                profile_id, session, text=summary_text, lang=lang, source_resume_id=resume.id
            )

    contributed = _contributed_bullet_ids(plan, new_bullet_ids)
    track = get_track(profile_id, session, resume.track_id) if resume.track_id else None
    track_created = False
    if track is None:
        # F2.7: there is no no-track outcome. A CV the operator bothered to upload is
        # a CV he applies with, and a CV that belongs to no track cannot be analysed
        # as itself — so an untagged document becomes a track named after its file
        # (`track_name` overrides; the form pre-fills it with the stem and requires it).
        track = create_track(
            profile_id,
            session,
            name=(track_name or "").strip() or Path(resume.filename).stem,
            # The document's own language: it is the only signal this screen has, and
            # the track's language is what the résumé it produced is written in.
            lang=draft.language,
        )
        # Document order, not selection order: the track is the document's shape.
        set_track_bullets(profile_id, session, track.id, contributed)
        resume.track_id = track.id
        track_created = True
    else:
        # The other half of F4 path 1: a résumé tagged with an existing track joins
        # it. Append, never replace — the selection may hold other documents' bullets
        # and hand-picked ones — and a bullet already there stays where it is.
        already = {bullet.id for bullet in track_bullets(profile_id, session, track.id)}
        position = len(already)
        seen: set[uuid.UUID] = set()
        for bullet_id in contributed:
            if bullet_id in already or bullet_id in seen:
                continue
            seen.add(bullet_id)
            session.add(TrackBullet(track_id=track.id, bullet_id=bullet_id, position=position))
            position += 1
            counts["track_bullets_added"] += 1
        session.flush()

    # F2.7's auto-fill: the track is filled from the document, never overwritten by
    # it. A headline or summary the track already has is a choice somebody made, and
    # stays — the result screen says which of the two happened.
    slot = "en" if lang == "en" else "es"
    filled_headline = kept_headline = False
    headline_note: tuple[int, int] | None = None
    headline_text = (draft.headline or "").strip()
    if headline_text:
        if len(headline_text) > HEADLINE_LIMIT:
            # Never truncated: a cut sentence says something else. The track keeps
            # the headline it has or none, and the result says why the draft's is
            # not in it.
            headline_note = (len(headline_text), HEADLINE_LIMIT)
            kept_headline = bool(getattr(track, f"headline_{slot}"))
        elif getattr(track, f"headline_{slot}"):
            kept_headline = True
        else:
            setattr(track, f"headline_{slot}", headline_text)
            filled_headline = True
    filled_summary = kept_summary = False
    if pooled is not None:
        if getattr(track, f"summary_{slot}_id"):
            kept_summary = True
        else:
            setattr(track, f"summary_{slot}_id", pooled.id)
            filled_summary = True

    # The confirmed canonicals join the track's selection, de-duplicated; order is
    # irrelevant in a skills section.
    selection = list(track.skills)
    for index, skill in enumerate(plan.skills):
        if index not in selections.skills or skill.canonical in selection:
            continue
        selection.append(skill.canonical)
        counts["track_skills_added"] += 1
    track.skills = selection

    mark_merged(profile_id, session, resume.id)
    return MergeResult(
        **counts,
        track_headline_filled=filled_headline,
        track_headline_kept=kept_headline,
        track_summary_filled=filled_summary,
        track_summary_kept=kept_summary,
        track_id=track.id,
        track_created=track_created,
        headline_not_set=headline_note,
    )