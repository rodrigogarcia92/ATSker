"""Import (PRD F2): upload a résumé, review the extraction, merge it or not.

The flow is deliberately three screens: the readability findings come first, the
draft is editable, and the merge screen labels every candidate new / changed /
unchanged so nothing overwrites silently. Career data changes only in the last
step, and the uploaded file is archived with its SHA-256 from the first (F2.6).
"""

import hashlib
import uuid
from collections.abc import Mapping
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session

from src.deletion import delete_resume, impact_resume
from src.extract.client import (
    CallOptions,
    NoModelConfigured,
    ProviderUnavailable,
    StructuredOutputError,
    model_configured,
)
from src.extract.grading import CitationViolation
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
from src.ingest.merge import HEADLINE_LIMIT, Selections, apply_merge, diff_draft
from src.ingest.translation import (
    TranslationSelections,
    apply_translation,
    plan_translation,
    translation_available,
)
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
from src.vocabulary import resolve_bullet_terms
from src.web.deps import DbSession, OwnProfile, SignedInUser
from src.web.findings import document_kind, finding_rows
from src.web.forms import is_checked
from src.web.locations import (
    box_characters,
    characters_apply,
    finding_boxes,
    finding_page,
    is_locatable,
    page_exists,
    render_page_png,
)
from src.web.templating import render

router = APIRouter()

# 512 MiB of instance memory and a bytea column say no to a 40 MB scan; a résumé is
# a text document, and anything past this is a mistake the user can see immediately.
MAX_UPLOAD_BYTES = 10 * 1024 * 1024

EMPTY_FORM = {"filename": "", "track_id": ""}

# The findings panel and its sentences live in `src.web.findings`: the report page
# shows the same stored gate, and one translation serves both screens.


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


def _pending_chips(session: Session, draft: ResumeDraft | None) -> list[str]:
    """The draft's chips the vocabulary does not know (F2.9).

    The merge stores them on the bullet as pending terms rather than dropping them,
    and the result screen labels them with the same function that decided it — a
    second answer here would be a second convention.
    """
    if draft is None:
        return []
    _, pending = resolve_bullet_terms(
        session,
        [chip for role in draft.roles for bullet in role.bullets for chip in bullet.chips],
    )
    return pending


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
        findings=finding_rows(gate, user.ui_lang),
        findings_resume=resume,
        findings_kind=kind,
        document_kind=kind,
        not_run=checks_not_run(kind),
        draft=draft,
        credentials=_credential_rows(draft) if draft else [],
        headline_limit=HEADLINE_LIMIT,
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
        max_upload_bytes=MAX_UPLOAD_BYTES,
        resumes=list_resumes(profile.id, session, active_only=False),
        tracks=list_tracks(profile.id, session, active_only=True),
        can_extract=model_configured() if can_extract is None else can_extract,
        error=error,
    )


@router.get("/import")
def import_index(request: Request, user: SignedInUser, session: DbSession, profile: OwnProfile):
    return _upload_page(request, user, session, profile)


@router.post("/import")
def import_upload(
    request: Request,
    user: SignedInUser,
    session: DbSession,
    profile: OwnProfile,
    file: Annotated[UploadFile, File()],
    track_id: Annotated[str | None, Form()] = None,
):
    filename = (file.filename or "documento").strip()
    # Sync on purpose: the handler runs in the threadpool, so the extraction cannot
    # freeze the event loop every request on this instance shares (F10.C0).
    data = file.file.read()
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
            options=CallOptions(profile_id=profile.id),
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
        merged_draft = ResumeDraft.model_validate(resume.draft) if resume.draft else None
        return render(
            request,
            "import/merged.html",
            user=user,
            profile=profile,
            resume=resume,
            draft=merged_draft,
            result=None,
            pending=_pending_chips(session, merged_draft),
            track=get_track(profile.id, session, resume.track_id) if resume.track_id else None,
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
            kind=document_kind(resume.filename),
            error=t("import.extraction_failed", user.ui_lang),
        )
    return _review_page(
        request,
        user,
        profile,
        resume=resume,
        gate=resume.gate or {},
        kind=document_kind(resume.filename),
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
    if data is None:
        # A CV saved from an attempt has no file to read again (F11.7).
        return RedirectResponse(f"/import/{resume_id}", status_code=303)
    gate = resume.gate or {}
    kind = document_kind(filename)
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
            options=CallOptions(profile_id=profile.id),
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


@router.get("/import/{resume_id}/delete")
def import_delete_form(
    resume_id: str, request: Request, user: SignedInUser, session: DbSession, profile: OwnProfile
):
    impact = impact_resume(profile.id, session, resume_id)
    if impact is None:
        return render(request, "not_found.html", user=user, status_code=404)
    return render(
        request,
        "delete/confirm.html",
        user=user,
        impact_text=t("delete.impact.resume", user.ui_lang, **impact),
        action=f"/import/{resume_id}/delete",
        cancel="/import",
        delete_bullets_option=True,
    )


@router.post("/import/{resume_id}/delete")
def import_delete(
    resume_id: str,
    session: DbSession,
    profile: OwnProfile,
    delete_bullets: Annotated[str | None, Form()] = None,
):
    removed = delete_resume(
        profile.id, session, resume_id, delete_bullets=is_checked(delete_bullets)
    )
    if removed is None:
        raise HTTPException(status_code=404)
    session.commit()
    return RedirectResponse("/import", status_code=303)


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
    track = get_track(profile.id, session, resume.track_id) if resume.track_id else None
    return render(
        request,
        "import/merge.html",
        user=user,
        profile=profile,
        resume=resume,
        draft=draft,
        track=track,
        plan=diff_draft(profile.id, session, draft),
        # F4.2: the screen offers the translation import when this document is the
        # other language of the track it was tagged with, and holds a job that track
        # already has. No provider call is made to decide it.
        translation_available=translation_available(
            profile.id, session, track=track, draft=draft
        ),
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
    # F2.7: there is no no-track outcome. The name names the track an untagged upload
    # becomes (the form pre-fills it with the file's stem and requires it, and the
    # merge falls back to the stem); a tagged upload joins its track whatever the
    # field says.
    track_name = _str(form, "track_name")
    result = apply_merge(
        profile.id,
        session,
        resume_id=resume.id,
        draft=draft,
        plan=plan,
        selections=selections,
        track_name=track_name,
    )
    if result is None:
        raise HTTPException(status_code=404)
    session.commit()
    # Deliberately not a redirect: the result counts are the point, and a resubmit is
    # a no-op because every merged candidate now diffs as unchanged. `resume.track_id`
    # is the created track or the one this upload was tagged with and joined.
    return render(
        request,
        "import/merged.html",
        user=user,
        profile=profile,
        resume=resume,
        draft=draft,
        result=result,
        pending=_pending_chips(session, draft),
        track=get_track(profile.id, session, resume.track_id) if resume.track_id else None,
    )


@router.post("/import/{resume_id}/translate")
def import_translate(
    resume_id: str,
    request: Request,
    user: SignedInUser,
    session: DbSession,
    profile: OwnProfile,
):
    """The other-language CV as a translation (F4.2): propose the pairs, then apply.

    One provider call per matched role, made with no transaction held. The screen
    that follows is the same form as the merge screen — the pairs above, the ordinary
    candidates below — posting to one route, so a confirmed pair and a ticked new
    bullet are one write.
    """
    resume = get_resume(profile.id, session, resume_id)
    if resume is None or resume.merged_at is not None or not resume.draft:
        raise HTTPException(status_code=404)
    draft = ResumeDraft.model_validate(resume.draft)
    track = get_track(profile.id, session, resume.track_id) if resume.track_id else None
    if track is None or not translation_available(profile.id, session, track=track, draft=draft):
        raise HTTPException(status_code=404)
    plan = diff_draft(profile.id, session, draft)
    session.commit()
    try:
        translation = plan_translation(
            profile.id,
            session,
            track=track,
            draft=draft,
            options=CallOptions(profile_id=profile.id),
        )
    except (NoModelConfigured, ProviderUnavailable, StructuredOutputError, CitationViolation):
        # The pairs cannot be reviewed without the answer, and a citation violation
        # after its retry is not something to paper over. The normal merge is still
        # there, so the screen says what failed rather than losing the upload.
        session.commit()
        return render(
            request,
            "import/merge.html",
            user=user,
            profile=profile,
            resume=resume,
            draft=draft,
            track=track,
            plan=plan,
            translation_available=True,
            error=t("import.translate_failed", user.ui_lang),
        )
    session.commit()
    return render(
        request,
        "import/translate.html",
        user=user,
        profile=profile,
        resume=resume,
        draft=draft,
        track=track,
        translation=translation,
        plan=translation.plan,
    )


@router.post("/import/{resume_id}/translate/apply")
async def import_translate_apply(
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
    track = get_track(profile.id, session, resume.track_id) if resume.track_id else None
    if track is None or not translation_available(profile.id, session, track=track, draft=draft):
        raise HTTPException(status_code=404)
    plan = diff_draft(profile.id, session, draft)
    session.commit()
    # The pairing is re-derived from the same inputs, so the cache serves it and the
    # review the user confirmed and the write are the same answer by construction.
    try:
        translation = plan_translation(
            profile.id,
            session,
            track=track,
            draft=draft,
            options=CallOptions(profile_id=profile.id),
        )
    except (NoModelConfigured, ProviderUnavailable, StructuredOutputError, CitationViolation):
        # The same failure the first route catches (F4.2): the screen says what
        # happened and nothing is written — no pair, no candidate, no merge.
        session.commit()
        return render(
            request,
            "import/merge.html",
            user=user,
            profile=profile,
            resume=resume,
            draft=draft,
            track=track,
            plan=plan,
            translation_available=True,
            error=t("import.translate_failed", user.ui_lang),
        )
    form = await request.form()
    selections = TranslationSelections(
        pairs=frozenset(_checked_indices(form, "pair_")),
        merge=Selections(
            roles=frozenset(_checked_indices(form, "merge_role_")),
            bullets=frozenset(_checked_pairs(form, "merge_bullet_")),
            educations=frozenset(_checked_indices(form, "merge_education_")),
            certifications=frozenset(_checked_indices(form, "merge_certification_")),
            skills=frozenset(_checked_indices(form, "merge_skill_")),
        ),
    )
    result = apply_translation(
        profile.id, session, resume_id=resume.id, plan=translation, selections=selections
    )
    if result is None:
        raise HTTPException(status_code=404)
    session.commit()
    return render(
        request,
        "import/merged.html",
        user=user,
        profile=profile,
        resume=resume,
        draft=draft,
        result=result,
        pending=_pending_chips(session, translation.draft),
        track=get_track(profile.id, session, resume.track_id) if resume.track_id else None,
    )


@router.post("/import/{resume_id}/discard")
def import_discard(
    resume_id: str, session: DbSession, profile: OwnProfile
):
    if set_resume_active(profile.id, session, resume_id, active=False) is None:
        raise HTTPException(status_code=404)
    session.commit()
    return RedirectResponse("/import", status_code=303)


def _stored_findings(resume: Resume) -> list[Mapping[str, Any]]:
    """The findings of the archived gate, in the order they were stored."""
    return list((resume.gate or {}).get("findings") or [])


def _addressed_finding(
    resume: Resume | None, index: int
) -> Mapping[str, Any] | None:
    """The finding an index addresses, or None — unknown résumé, index out of range."""
    if resume is None:
        return None
    findings = _stored_findings(resume)
    if 0 <= index < len(findings):
        return findings[index]
    return None


@router.get("/import/{resume_id}/findings/{index}")
def finding_location(
    resume_id: str,
    index: int,
    request: Request,
    user: SignedInUser,
    session: DbSession,
    profile: OwnProfile,
):
    """The "show me where" view: the page with the finding's boxes, and what they hide.

    The characters are read from the archived original here and rendered once — the
    stored finding carries boxes and no text (decision 9). Owner-scoped like everything
    else: another profile's résumé is not found, not forbidden (F1).
    """
    resume = get_resume(profile.id, session, resume_id)
    finding = _addressed_finding(resume, index)
    if resume is None or finding is None:
        return render(request, "not_found.html", user=user, status_code=404)
    page = finding_page(finding)
    if page is None or not is_locatable(str(finding.get("check"))):
        # A DOCX finding, or a check with no geometry to point at.
        return render(request, "not_found.html", user=user, status_code=404)
    if resume.file_bytes is None:
        # A CV saved from an attempt: say the file was not kept (F11.7).
        return render(
            request,
            "not_found.html",
            user=user,
            status_code=404,
            message=t("import.file_not_kept", user.ui_lang),
        )
    if not page_exists(resume.file_bytes, page):
        return render(request, "not_found.html", user=user, status_code=404)
    boxes = finding_boxes(finding)
    characters = (
        box_characters(resume.file_bytes, page_number=page, boxes=boxes)
        if characters_apply(str(finding.get("check")))
        else None
    )
    response = render(
        request,
        "import/finding.html",
        user=user,
        profile=profile,
        resume=resume,
        index=index,
        finding=finding_rows(resume.gate or {}, user.ui_lang)[index],
        characters=characters,
    )
    # The view can carry the document's hidden characters, so it is never cached.
    response.headers["Cache-Control"] = "no-store"
    return response


@router.get("/import/{resume_id}/findings/{index}/page.png")
def finding_page_png(
    resume_id: str,
    index: int,
    session: DbSession,
    profile: OwnProfile,
) -> Response:
    """The finding's page, boxes outlined in the severity colour, as a PNG (F5.1.1).

    Nothing is written to disk, the database or a log, and the response is never cached:
    it renders the user's own document, inside their own session.
    """
    resume = get_resume(profile.id, session, resume_id)
    finding = _addressed_finding(resume, index)
    if resume is None or finding is None:
        return Response(status_code=404)
    page = finding_page(finding)
    if page is None or not is_locatable(str(finding.get("check"))):
        return Response(status_code=404)
    if resume.file_bytes is None or not page_exists(resume.file_bytes, page):
        # An out-of-range page is not found, never a traceback (N6.6).
        return Response(status_code=404)
    png = render_page_png(
        resume.file_bytes,
        page_number=page,
        boxes=finding_boxes(finding),
        severity=str(finding.get("severity")),
    )
    return Response(content=png, media_type="image/png", headers={"Cache-Control": "no-store"})