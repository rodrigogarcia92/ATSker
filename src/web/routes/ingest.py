"""Import (PRD F2): upload a résumé, review the extraction, merge it or not.

The flow is deliberately three screens: the readability findings come first, the
draft is editable, and the merge screen labels every candidate new / changed /
unchanged so nothing overwrites silently. Career data changes only in the last
step, and the uploaded file is archived with its SHA-256 from the first (F2.6).
"""

import hashlib
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from src.extract.client import (
    NoModelConfigured,
    ProviderUnavailable,
    StructuredOutputError,
    model_configured,
)
from src.extract.resume import EmptyExtraction, extract_resume
from src.i18n import t
from src.ingest.documents import UnreadableDocument, UnsupportedDocument, load_document
from src.ingest.draft import (
    DraftBullet,
    DraftCertification,
    DraftEducation,
    DraftRole,
    ResumeDraft,
    build_draft,
)
from src.ingest.merge import Selections, apply_merge, diff_draft
from src.models import Resume, Track
from src.parse.gate import checks_not_run
from src.resumes import (
    create_resume,
    get_resume,
    list_resumes,
    save_draft,
    set_resume_active,
)
from src.tracks import get_track, list_tracks
from src.web.deps import DbSession, OwnProfile, SignedInUser
from src.web.templating import render

router = APIRouter()

# 512 MiB of instance memory and a bytea column say no to a 40 MB scan; a résumé is
# a text document, and anything past this is a mistake the user can see immediately.
MAX_UPLOAD_BYTES = 10 * 1024 * 1024

EMPTY_FORM = {"filename": "", "track_id": ""}

# Which stored checks carry a page number on a PDF; without one the finding came
# from a DOCX and its detail sentence has no page to name.
_PAGE_CHECKS = {
    "contact_in_margin",
    "text_in_table",
    "invisible_text",
    "multi_column",
    "mojibake",
}


def _document_kind(filename: str) -> str:
    return Path(filename).suffix.lower().lstrip(".")


def _finding_detail(check: str, detail: Mapping[str, Any], lang: str) -> str:
    """One finding's detail sentence. Page numbers, bands and counts only — never text."""
    variant = ""
    if check == "no_extractable_text":
        variant = "" if detail.get("pages") else "_docx"
    elif check == "multi_column":
        variant = "" if "gap_pt" in detail else "_docx"
    elif check in _PAGE_CHECKS and detail.get("page") is None:
        variant = "_docx"
    fonts = [str(font) for font in detail.get("fonts", [])]
    first_pages = detail.get("first_pages") or {}
    gutter = list(detail.get("gutter") or [])
    values: dict[str, Any] = {
        "page": detail.get("page") if detail.get("page") is not None else "",
        "pages": ", ".join(str(value) for value in detail.get("pages", []))
        or t("common.none", lang),
        "band": t(f"gate.band.{detail.get('band', 'header')}", lang),
        "kinds": ", ".join(t(f"gate.kind.{kind}", lang) for kind in detail.get("kinds", [])),
        "words": detail.get("words", 0),
        "cells": detail.get("cells", 0),
        "tables": detail.get("tables", 0),
        "runs": detail.get("runs", 0),
        "gap_pt": detail.get("gap_pt", 0),
        "gutter_start": gutter[0] if len(gutter) == 2 else "",
        "gutter_end": gutter[1] if len(gutter) == 2 else "",
        "height_percent": round(float(detail.get("height_fraction") or 0) * 100),
        "columns": detail.get("columns", 0),
        "count": detail.get("count", 0),
        "markers": ", ".join(str(marker) for marker in detail.get("markers", [])),
        "fonts": ", ".join(
            f"{font} (p. {first_pages[font]})" if font in first_pages else font for font in fonts
        ),
    }
    return t(f"gate.detail.{check}{variant}", lang, **values)


def _findings(gate: Mapping[str, Any], lang: str) -> list[dict[str, str]]:
    """A stored gate report, translated for the template."""
    rows: list[dict[str, str]] = []
    for finding in gate.get("findings", []):
        check = str(finding.get("check"))
        detail = finding.get("detail") or {}
        severity = str(finding.get("severity"))
        rows.append(
            {
                "check": check,
                "severity": severity,
                "label": t(f"gate.check.{check}", lang),
                "severity_label": t(f"gate.severity.{severity}", lang),
                "detail": _finding_detail(check, detail, lang),
            }
        )
    return rows


def _credential_rows(draft: ResumeDraft) -> list[dict[str, Any]]:
    """Education and certifications as one editable list; the kind is the user's call.

    The extractor's classifier is deterministic first, but a rule that fired wrong
    must be fixable — so both kinds share one form and a select decides which fields
    the merge reads.
    """
    rows: list[dict[str, Any]] = []
    for entry in draft.educations:
        rows.append(
            {
                "kind": "education",
                "name": entry.award or "",
                "issuer": entry.institution,
                "field": entry.field or "",
                "start": entry.start_date or "",
                "end": entry.end_date or "",
                "issued": "",
                "expiry": "",
                "credential_id": "",
                "credential_url": "",
                "needs_review": entry.needs_review,
            }
        )
    for entry in draft.certifications:
        rows.append(
            {
                "kind": "certification",
                "name": entry.name,
                "issuer": entry.issuer or "",
                "field": "",
                "start": "",
                "end": "",
                "issued": entry.issued_date or "",
                "expiry": entry.expiry_date or "",
                "credential_id": entry.credential_id or "",
                "credential_url": entry.credential_url or "",
                "needs_review": entry.needs_review,
            }
        )
    return rows


def _str(form: Mapping[str, Any], key: str) -> str:
    return str(form.get(key) or "").strip()


def _count(form: Mapping[str, Any], key: str) -> int:
    try:
        return int(str(form.get(key) or 0))
    except ValueError:
        return 0


def _checked_indices(form: Mapping[str, Any], prefix: str) -> set[int]:
    found: set[int] = set()
    for key in form:
        if key.startswith(prefix):
            suffix = key[len(prefix) :]
            if suffix.isdigit():
                found.add(int(suffix))
    return found


def _checked_pairs(form: Mapping[str, Any], prefix: str) -> set[tuple[int, int]]:
    found: set[tuple[int, int]] = set()
    for key in form:
        if not key.startswith(prefix):
            continue
        left, _, right = key[len(prefix) :].partition("_")
        if left.isdigit() and right.isdigit():
            found.add((int(left), int(right)))
    return found


def draft_from_form(form: Mapping[str, Any], *, language: str) -> ResumeDraft:
    """Rebuild the draft from the review screen's fields.

    Blank rows are dropped rather than stored empty: clearing a role's employer and
    title is how the user removes an extraction they do not want.
    """
    roles: list[DraftRole] = []
    for index in range(_count(form, "role_count")):
        bullets: list[DraftBullet] = []
        for bullet_index in range(_count(form, f"bullet_count_{index}")):
            text = _str(form, f"bullet_{index}_{bullet_index}_text")
            if not text:
                continue
            chips = [
                part.strip()
                for part in _str(form, f"bullet_{index}_{bullet_index}_chips").split(",")
                if part.strip()
            ]
            bullets.append(DraftBullet(text=text, chips=chips))
        employer = _str(form, f"role_{index}_employer")
        title = _str(form, f"role_{index}_title")
        if not employer and not title:
            continue
        roles.append(
            DraftRole(
                employer=employer,
                title=title,
                start_date=_str(form, f"role_{index}_start") or None,
                end_date=_str(form, f"role_{index}_end") or None,
                bullets=bullets,
            )
        )

    educations: list[DraftEducation] = []
    certifications: list[DraftCertification] = []
    for index in range(_count(form, "credential_count")):
        kind = _str(form, f"credential_{index}_kind") or "education"
        name = _str(form, f"credential_{index}_name")
        issuer = _str(form, f"credential_{index}_issuer")
        if not name and not issuer:
            continue
        needs_review = _str(form, f"credential_{index}_review") == "on"
        if kind == "certification":
            certifications.append(
                DraftCertification(
                    name=name,
                    issuer=issuer or None,
                    issued_date=_str(form, f"credential_{index}_issued") or None,
                    expiry_date=_str(form, f"credential_{index}_expiry") or None,
                    credential_id=_str(form, f"credential_{index}_credential_id") or None,
                    credential_url=_str(form, f"credential_{index}_credential_url") or None,
                    needs_review=needs_review,
                )
            )
        else:
            educations.append(
                DraftEducation(
                    institution=issuer,
                    award=name or None,
                    field=_str(form, f"credential_{index}_field") or None,
                    start_date=_str(form, f"credential_{index}_start") or None,
                    end_date=_str(form, f"credential_{index}_end") or None,
                    needs_review=needs_review,
                )
            )

    skills = [
        part.strip()
        for part in _str(form, "skills").split(",")
        if part.strip()
    ]
    return ResumeDraft(
        language=language,
        headline=_str(form, "headline") or None,
        summary=_str(form, "summary") or None,
        skills=skills,
        roles=roles,
        educations=educations,
        certifications=certifications,
    )


def _failure_message(failure: Exception, lang: str) -> str:
    """What to say when an extraction produced nothing (F2.3.1).

    `EmptyExtraction` is its own case: the document was read and the answer said
    nothing, which is a different problem from a provider that could not be reached
    and has a different fix.
    """
    if isinstance(failure, EmptyExtraction):
        return t("import.empty_extraction", lang, characters=failure.characters)
    return t("import.failed", lang)


def _archive_resume(
    profile_id: uuid.UUID,
    session: Session,
    *,
    filename: str,
    data: bytes,
    gate: dict,
    track: Track | None,
    draft: dict | None = None,
) -> Resume:
    """Store the upload with its findings, draft or not (F2.6, F2.3.1)."""
    return create_resume(
        profile_id,
        session,
        filename=filename,
        data=data,
        sha256=hashlib.sha256(data).hexdigest(),
        track_id=track.id if track else None,
        gate=gate,
        draft=draft,
    )


def _review_page(
    request: Request,
    user,
    profile,
    *,
    resume,
    gate: Mapping[str, Any],
    kind: str,
    draft: ResumeDraft | None = None,
    error: str | None = None,
):
    """The draft screen in all its states: editable draft, failed extraction, no text.

    `can_retry` is true exactly when there is an archived row with no draft and a
    model to call — the retry runs on the stored bytes, which is what the archive is
    for (F2.3.1).
    """
    return render(
        request,
        "import/review.html",
        user=user,
        profile=profile,
        resume=resume,
        gate=gate,
        findings=_findings(gate, user.ui_lang),
        document_kind=kind,
        not_run=checks_not_run(kind),
        draft=draft,
        credentials=_credential_rows(draft) if draft else [],
        error=error,
        can_retry=bool(resume is not None and draft is None and model_configured()),
    )


def _upload_page(
    request: Request,
    user,
    session,
    profile,
    *,
    error: str | None = None,
    can_extract: bool | None = None,
    values: dict | None = None,
):
    return render(
        request,
        "import/upload.html",
        user=user,
        profile=profile,
        values=values or EMPTY_FORM,
        resumes=list_resumes(profile.id, session, active_only=False),
        tracks=list_tracks(profile.id, session, active_only=True),
        can_extract=model_configured() if can_extract is None else can_extract,
        error=error,
    )


@router.get("/import")
def import_index(request: Request, user: SignedInUser, session: DbSession, profile: OwnProfile):
    return _upload_page(request, user, session, profile)


@router.post("/import")
async def import_upload(
    request: Request,
    user: SignedInUser,
    session: DbSession,
    profile: OwnProfile,
    file: Annotated[UploadFile, File()],
    track_id: Annotated[str | None, Form()] = None,
):
    filename = (file.filename or "documento").strip()
    data = await file.read()
    values = {"filename": filename, "track_id": track_id or ""}

    error: str | None = None
    if not data:
        error = t("import.no_file", user.ui_lang)
    elif len(data) > MAX_UPLOAD_BYTES:
        error = t("import.too_large", user.ui_lang)
    if error is not None:
        return _upload_page(request, user, session, profile, error=error, values=values)

    try:
        loaded = load_document(filename, data)
    except UnsupportedDocument:
        return _upload_page(
            request,
            user,
            session,
            profile,
            error=t("import.unsupported", user.ui_lang),
            values=values,
        )
    except UnreadableDocument:
        return _upload_page(
            request,
            user,
            session,
            profile,
            error=t("import.unreadable", user.ui_lang),
            values=values,
        )

    gate = loaded.gate.to_dict()
    if not loaded.text.strip():
        # Nothing for an ATS to read and nothing to extract: show the findings and
        # store nothing — there is no draft to review and no merge to make.
        return _review_page(
            request,
            user,
            profile,
            resume=None,
            gate=gate,
            kind=loaded.kind,
            error=t("import.no_text", user.ui_lang),
        )

    # The route owns its transaction: the session's reads (the signed-in profile and
    # the intended track among them) are released before the provider call, and
    # `complete_json` refuses to run while a transaction is held.
    track = get_track(profile.id, session, track_id) if track_id else None
    session.commit()
    try:
        extraction, completion = extract_resume(
            session,
            loaded.text,
            known_names=[profile.display_name] if profile.display_name else None,
        )
    except NoModelConfigured:
        # No call was attempted and nothing was paid for: there is no answer to purge
        # and none to retry, so the findings are shown and nothing is archived.
        message = t("import.no_model", user.ui_lang)
    except (ProviderUnavailable, StructuredOutputError, EmptyExtraction) as failure:
        # The calls that were paid for stay in the ledger. The document is archived
        # with no draft (F2.3.1), which is what makes the retry cheap: it runs on the
        # stored bytes instead of asking the user to upload the file again.
        session.commit()
        resume = _archive_resume(
            profile.id, session, filename=filename, data=data, gate=gate, track=track
        )
        session.commit()
        return _review_page(
            request,
            user,
            profile,
            resume=resume,
            gate=gate,
            kind=loaded.kind,
            error=_failure_message(failure, user.ui_lang),
        )
    else:
        draft = build_draft(session, extraction, language_hint=user.ui_lang)
        resume = _archive_resume(
            profile.id,
            session,
            filename=filename,
            data=data,
            gate=gate,
            track=track,
            draft=draft.model_dump(mode="json"),
        )
        session.commit()
        if completion.ledger_error:
            # The draft is real; the ledger row is not. Show the review screen with
            # the warning instead of redirecting into a page that would read as clean.
            return _review_page(
                request,
                user,
                profile,
                resume=resume,
                gate=gate,
                kind=loaded.kind,
                draft=draft,
                error=t("common.ledger_unrecorded", user.ui_lang),
            )
        return RedirectResponse(f"/import/{resume.id}", status_code=303)

    return _review_page(
        request, user, profile, resume=None, gate=gate, kind=loaded.kind, error=message
    )


@router.get("/import/{resume_id}")
def import_review(
    resume_id: str, request: Request, user: SignedInUser, session: DbSession, profile: OwnProfile
):
    resume = get_resume(profile.id, session, resume_id)
    if resume is None:
        return render(request, "not_found.html", user=user, status_code=404)
    if resume.merged_at is not None:
        return render(
            request,
            "import/merged.html",
            user=user,
            profile=profile,
            resume=resume,
            draft=ResumeDraft.model_validate(resume.draft) if resume.draft else None,
            result=None,
        )
    draft = ResumeDraft.model_validate(resume.draft) if resume.draft else None
    if draft is None:
        # F2.3.1: the row is here because the upload was archived before its
        # extraction failed. Say so and offer the retry, rather than a 404 that
        # would read as "this document is gone".
        return _review_page(
            request,
            user,
            profile,
            resume=resume,
            gate=resume.gate or {},
            kind=_document_kind(resume.filename),
            error=t("import.extraction_failed", user.ui_lang),
        )
    return _review_page(
        request,
        user,
        profile,
        resume=resume,
        gate=resume.gate or {},
        kind=_document_kind(resume.filename),
        draft=draft,
    )


@router.post("/import/{resume_id}/retry")
def import_retry(
    resume_id: str, request: Request, user: SignedInUser, session: DbSession, profile: OwnProfile
):
    """Re-run the extraction on the archived bytes (F2.3.1).

    The file was stored for exactly this: a failed extraction whose paid answer has
    since been purged, or a provider that was down, must not cost the user the upload
    again.
    """
    resume = get_resume(profile.id, session, resume_id)
    if resume is None or resume.merged_at is not None:
        return render(request, "not_found.html", user=user, status_code=404)
    if resume.draft is not None:
        return RedirectResponse(f"/import/{resume_id}", status_code=303)

    filename = resume.filename
    data = resume.file_bytes
    gate = resume.gate or {}
    kind = _document_kind(filename)
    try:
        loaded = load_document(filename, data)
    except (UnsupportedDocument, UnreadableDocument):
        return _review_page(
            request,
            user,
            profile,
            resume=resume,
            gate=gate,
            kind=kind,
            error=t("import.unreadable", user.ui_lang),
        )

    session.commit()
    try:
        extraction, completion = extract_resume(
            session,
            loaded.text,
            known_names=[profile.display_name] if profile.display_name else None,
        )
    except NoModelConfigured:
        message = t("import.no_model", user.ui_lang)
    except (ProviderUnavailable, StructuredOutputError, EmptyExtraction) as failure:
        session.commit()
        message = _failure_message(failure, user.ui_lang)
    else:
        draft = build_draft(session, extraction, language_hint=user.ui_lang)
        save_draft(profile.id, session, resume_id, draft.model_dump(mode="json"))
        session.commit()
        return RedirectResponse(f"/import/{resume_id}", status_code=303)

    return _review_page(
        request, user, profile, resume=resume, gate=gate, kind=kind, error=message
    )


@router.post("/import/{resume_id}/review")
async def import_confirm(
    resume_id: str,
    request: Request,
    user: SignedInUser,
    session: DbSession,
    profile: OwnProfile,
):
    resume = get_resume(profile.id, session, resume_id)
    if resume is None or resume.merged_at is not None:
        raise HTTPException(status_code=404)
    form = await request.form()
    language = _str(form, "language") or user.ui_lang
    draft = draft_from_form(form, language=language)
    save_draft(profile.id, session, resume_id, draft.model_dump(mode="json"))
    session.commit()
    return render(
        request,
        "import/merge.html",
        user=user,
        profile=profile,
        resume=resume,
        draft=draft,
        plan=diff_draft(profile.id, session, draft),
    )


@router.post("/import/{resume_id}/merge")
async def import_merge(
    resume_id: str,
    request: Request,
    user: SignedInUser,
    session: DbSession,
    profile: OwnProfile,
):
    resume = get_resume(profile.id, session, resume_id)
    if resume is None or resume.merged_at is not None or not resume.draft:
        raise HTTPException(status_code=404)
    draft = ResumeDraft.model_validate(resume.draft)
    plan = diff_draft(profile.id, session, draft)
    form = await request.form()
    selections = Selections(
        roles=frozenset(_checked_indices(form, "merge_role_")),
        bullets=frozenset(_checked_pairs(form, "merge_bullet_")),
        educations=frozenset(_checked_indices(form, "merge_education_")),
        certifications=frozenset(_checked_indices(form, "merge_certification_")),
        skills=frozenset(_checked_indices(form, "merge_skill_")),
    )
    result = apply_merge(
        profile.id,
        session,
        resume_id=resume.id,
        draft=draft,
        plan=plan,
        selections=selections,
    )
    if result is None:
        raise HTTPException(status_code=404)
    session.commit()
    # Deliberately not a redirect: the result counts are the point, and a resubmit is
    # a no-op because every merged candidate now diffs as unchanged.
    return render(
        request,
        "import/merged.html",
        user=user,
        profile=profile,
        resume=resume,
        draft=draft,
        result=result,
    )


@router.post("/import/{resume_id}/discard")
def import_discard(
    resume_id: str, session: DbSession, profile: OwnProfile
):
    if set_resume_active(profile.id, session, resume_id, active=False) is None:
        raise HTTPException(status_code=404)
    session.commit()
    return RedirectResponse("/import", status_code=303)