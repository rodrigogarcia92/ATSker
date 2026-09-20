"""The reviewed draft (PRD F2.3/F2.4): the extraction normalised, nothing persisted.

Two decisions live here rather than in the prompt:

* **Certification classification is deterministic first.** A credential id or url, a
  name that says certificate/certification/professional, or an issuer that is not an
  academic institution routes an entry to `certifications`; an academic issuer routes
  it to `educations`. Only what no rule can decide follows the model's own `kind`
  proposal, and those entries are flagged for the review screen.
* **Bullet chips are matched, never proposed.** A chip is a vocabulary canonical that
  actually appears in the bullet's own text, so no model can attach a skill to a line
  that does not mention it.
"""

import json
import re
from datetime import date
from pathlib import Path

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.extract.resume import ExtractedCredential, ResumeExtraction
from src.normalize.text import fold
from src.normalize.vocabulary import match_text
from src.vocabulary import alias_map, log_unmapped

_DATA = json.loads((Path(__file__).parent / "institutions.json").read_text(encoding="utf-8"))
INSTITUTION_MARKERS: tuple[str, ...] = tuple(_DATA["institution_markers"])
CREDENTIAL_MARKERS: tuple[str, ...] = tuple(_DATA["credential_markers"])

_PARTIAL_DATE = re.compile(r"^(\d{4})(?:-(\d{1,2}))?(?:-(\d{1,2}))?$")


class DraftBullet(BaseModel):
    text: str
    chips: list[str] = Field(default_factory=list)


class DraftRole(BaseModel):
    employer: str = ""
    title: str = ""
    start_date: str | None = None
    end_date: str | None = None
    bullets: list[DraftBullet] = Field(default_factory=list)


class DraftEducation(BaseModel):
    institution: str = ""
    award: str | None = None
    field: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    needs_review: bool = False


class DraftCertification(BaseModel):
    name: str = ""
    issuer: str | None = None
    issued_date: str | None = None
    expiry_date: str | None = None
    credential_id: str | None = None
    credential_url: str | None = None
    needs_review: bool = False


class ResumeDraft(BaseModel):
    """What the review screen edits and the merge reads. Stored as `resumes.draft`."""

    language: str = "es"
    headline: str | None = None
    summary: str | None = None
    skills: list[str] = Field(default_factory=list)
    roles: list[DraftRole] = Field(default_factory=list)
    educations: list[DraftEducation] = Field(default_factory=list)
    certifications: list[DraftCertification] = Field(default_factory=list)


def parse_partial_date(value: str | None) -> date | None:
    """`YYYY`, `YYYY-MM` or `YYYY-MM-DD`, as the extractor returns them.

    Anything else is None rather than a guess: a date the parser cannot read is
    shown empty on the review screen for the user to fix, never invented.
    """
    if not value:
        return None
    match = _PARTIAL_DATE.match(value.strip())
    if match is None:
        return None
    year = int(match.group(1))
    month = int(match.group(2) or 1)
    day = int(match.group(3) or 1)
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _iso(value: str | None) -> str | None:
    parsed = parse_partial_date(value)
    return parsed.isoformat() if parsed else None


def _clean(value: str | None) -> str | None:
    return (value or "").strip() or None


def classify_credential(entry: ExtractedCredential) -> tuple[str, bool]:
    """One entry → (kind, needs_review); deterministic signals first (PRD F2.3)."""
    name = fold(entry.name)
    issuer = fold(entry.issuer or "")
    has_reference = bool(
        (entry.credential_id or "").strip() or (entry.credential_url or "").strip()
    )
    has_credential_word = any(marker in name for marker in CREDENTIAL_MARKERS)
    academic = any(marker in issuer for marker in INSTITUTION_MARKERS)

    if has_reference or has_credential_word or (issuer and not academic):
        return "certification", False
    if academic:
        return "education", False
    # No rule can decide: the model's own proposal decides, and a human reviews it.
    kind = entry.kind if entry.kind in ("education", "certification") else "education"
    return kind, True


def build_draft(
    session: Session,
    extraction: ResumeExtraction,
    *,
    language_hint: str | None = None,
) -> ResumeDraft:
    """Normalise one extraction into the draft the user reviews before anything merges."""
    aliases = alias_map(session)
    language = fold(extraction.language or "")[:2] or (language_hint or "es")

    skills: list[str] = []
    unknown: list[str] = []
    for raw in extraction.skills:
        canonical = aliases.get(fold(raw))
        if canonical is None:
            unknown.append(raw)
        elif canonical not in skills:
            skills.append(canonical)
    log_unmapped(session, unknown)

    roles: list[DraftRole] = []
    for raw in extraction.roles:
        employer = raw.employer.strip()
        title = raw.title.strip()
        if not employer and not title:
            continue
        bullets: list[DraftBullet] = []
        for line in raw.bullets:
            text = " ".join(line.split()).strip()
            if not text:
                continue
            bullets.append(DraftBullet(text=text, chips=match_text(text, aliases)))
        roles.append(
            DraftRole(
                employer=employer,
                title=title,
                start_date=_iso(raw.start_date),
                end_date=_iso(raw.end_date),
                bullets=bullets,
            )
        )

    educations: list[DraftEducation] = []
    certifications: list[DraftCertification] = []
    for entry in extraction.credentials:
        name = entry.name.strip()
        if not name:
            continue
        kind, needs_review = classify_credential(entry)
        if kind == "certification":
            certifications.append(
                DraftCertification(
                    name=name,
                    issuer=_clean(entry.issuer),
                    issued_date=_iso(entry.issued_date),
                    expiry_date=_iso(entry.expiry_date),
                    credential_id=_clean(entry.credential_id),
                    credential_url=_clean(entry.credential_url),
                    needs_review=needs_review,
                )
            )
        else:
            educations.append(
                DraftEducation(
                    institution=_clean(entry.issuer) or "",
                    award=name,
                    field=_clean(entry.field),
                    start_date=_iso(entry.start_date),
                    end_date=_iso(entry.end_date),
                    needs_review=needs_review,
                )
            )

    return ResumeDraft(
        language=language,
        headline=_clean(extraction.headline),
        summary=_clean(extraction.summary),
        skills=skills,
        roles=roles,
        educations=educations,
        certifications=certifications,
    )