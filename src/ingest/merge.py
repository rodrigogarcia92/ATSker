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
"""

import uuid
from dataclasses import dataclass, fields
from datetime import date
from typing import Literal

from sqlalchemy.orm import Session

from src.bullets import bullet_text, create_bullet, get_bullet, list_bullets, update_bullet
from src.certifications import create_certification, list_certifications, update_certification
from src.education import create_education, list_educations, update_education
from src.ingest.draft import DraftCertification, DraftEducation, ResumeDraft, parse_partial_date
from src.models import Bullet, BulletRevision, Certification, Education, Profile, Role
from src.normalize.text import fold
from src.resumes import get_resume, mark_merged
from src.roles import create_role, list_roles, update_role

Label = Literal["new", "changed", "unchanged"]

# A draft bullet is a changed version of an existing one when this share of their
# folded token sets overlaps. 0.6 separates "reduje el tiempo de reporte en un 30%
# con python" (changed) from a different achievement that shares a verb (new).
BULLET_SIMILARITY = 0.6


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


def _tokens(text: str) -> frozenset[str]:
    return frozenset(token for token in fold(text).split() if len(token) > 1)


def _similarity(left: frozenset[str], right: frozenset[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _role_index(roles: list[Role]) -> dict[str, Role]:
    """Folded employer+title → the role to match; the active, most recent one wins."""
    index: dict[str, Role] = {}
    for role in roles:
        key = f"{fold(role.employer)}\x00{fold(role.title)}"
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
            (bullet for bullet in unused if fold(bullet_text(bullet)) == fold(text)), None
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
        existing = index.get(f"{fold(raw.employer)}\x00{fold(raw.title)}")
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


def apply_merge(
    profile_id: uuid.UUID,
    session: Session,
    *,
    resume_id: uuid.UUID,
    draft: ResumeDraft,
    plan: MergePlan,
    selections: Selections,
) -> MergeResult | None:
    """Write the ticked candidates; None when the résumé belongs to someone else."""
    resume = get_resume(profile_id, session, resume_id)
    profile = session.get(Profile, profile_id)
    if resume is None or profile is None:
        return None

    counts = {field.name: 0 for field in fields(MergeResult)}

    role_ids: dict[int, uuid.UUID] = {}
    for index, role in enumerate(plan.roles):
        if index not in selections.roles:
            continue
        if role.label == "new":
            created = create_role(
                profile_id,
                session,
                employer=role.employer,
                title=role.title,
                start_date=role.start_date,
                end_date=role.end_date,
            )
            counts["roles_created"] += 1
            role_ids[index] = created.id
        elif role.label == "changed":
            updated = update_role(
                profile_id,
                session,
                role.existing_id,
                employer=role.employer,
                title=role.title,
                start_date=role.start_date,
                end_date=role.end_date,
                active=True,
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
                create_bullet(
                    profile_id,
                    session,
                    role_id=role_ids[index],
                    text_en=text_en,
                    text_es=text_es,
                    chips=bullet.chips,
                )
                counts["bullets_created"] += 1
            elif bullet.label == "changed":
                existing = get_bullet(profile_id, session, bullet.existing_id)
                if existing is None:
                    counts["skipped"] += 1
                    continue
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

    mark_merged(profile_id, session, resume.id)
    return MergeResult(**counts)