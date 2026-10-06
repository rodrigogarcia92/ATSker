"""Generated text over HTTP (PRD F7.3): propose, show the diff, accept or refuse.

Nothing is generated during an analysis and nothing is stored until the user
accepts. A proposal travels in the form as JSON; the accept route validates it again
against the database's own sources, because form text is user input and F7.3's
validators are the reason the number on the page can be trusted.
"""

import json
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from src.applications import get_application
from src.bullets import bullet_text, get_bullet, suggest_skills
from src.extract.client import (
    CallOptions,
    NoModelConfigured,
    ProviderUnavailable,
    StructuredOutputError,
    model_configured,
)
from src.extract.generation import generate_bullet, generate_story_bullets, generate_summary
from src.generate.proposals import (
    accept_bullet,
    accept_story_bullet,
    accept_summary,
    check_bullet,
    check_story_bullet,
    check_summary,
    grades_of,
    pool_skills,
    report_language,
)
from src.generate.validators import Violation
from src.i18n import t
from src.jd import StructuredJD
from src.roles import get_role, list_roles
from src.stories import get_story
from src.summaries import get_summary
from src.tracks import get_track, track_bullets
from src.web.deps import DbSession, OwnProfile, SignedInUser
from src.web.forms import is_checked
from src.web.templating import render

router = APIRouter()

logger = logging.getLogger(__name__)

# PRD §12.5: a failed proposal says why, in one of three sentences, and the log line carries
# the error class and the purpose — never any text the model saw or said.
SUMMARY = "generate_summary"
BULLET = "generate_bullet"
STORY = "story_bullets"
PROVIDER_ERRORS = (NoModelConfigured, ProviderUnavailable, StructuredOutputError)


def _no_model(purpose: str, lang: str) -> str:
    """Nothing is configured to call: said before a call is attempted."""
    logger.warning("generation refused: purpose=%s error=NoModelConfigured", purpose)
    return t("generate.err.no_model", lang)


def _failed(exc: BaseException, purpose: str, lang: str) -> str:
    """Which of the three it was: no model, the provider, or an answer nobody can use."""
    logger.warning("generation failed: purpose=%s error=%s", purpose, type(exc).__name__)
    if isinstance(exc, NoModelConfigured):
        return t("generate.err.no_model", lang)
    if isinstance(exc, ProviderUnavailable):
        return t("generate.err.provider", lang)
    return t("generate.err.unusable", lang)


def _target(application_id: str, session, profile):
    """The application and the track a proposal would be written against."""
    application = get_application(profile.id, session, application_id)
    if application is None or application.track_id is None:
        return None, None
    return application, get_track(profile.id, session, application.track_id)


def _current(session, track, language: str) -> dict[str, Any]:
    """What the track holds in this language today — the other side of the diff."""
    slot = track.summary_en_id if language == "en" else track.summary_es_id
    summary = get_summary(track.profile_id, session, slot) if slot else None
    return {"summary": summary.text if summary is not None else None, "skills": list(track.skills)}


def _page(
    request,
    user,
    profile,
    application,
    track,
    session,
    *,
    proposal=None,
    violations: list[Violation] | None = None,
    error: str | None = None,
    retry: bool = False,
    refused: dict[str, Any] | None = None,
    dialog: bool = False,
):
    """The summary flow, as the full page or — with `dialog` — as the pop-up's partial.

    Both render `generate/_summary_body.html`; the page adds a heading and a way back, the
    partial is what the shared dialog (§12.5) loads into its body.
    """
    language = report_language(application)
    return render(
        request,
        "generate/_summary_body.html" if dialog else "generate/summary.html",
        user=user,
        profile=profile,
        application=application,
        track=track,
        language=language,
        dialog=dialog,
        proposal=proposal,
        proposal_json=(
            json.dumps(proposal.output, ensure_ascii=False) if proposal is not None else ""
        ),
        violations=violations or [],
        refused=refused,
        current=_current(session, track, language),
        bullet_count=len(track_bullets(profile.id, session, track.id)),
        # The call costs money, so it is a button on a POST, never a GET (F.0). After a
        # failure the same button comes back, except when no model is configured.
        run_url=(
            f"/applications/{application.id}/summary/generate"
            if proposal is None and refused is None and (error is None or retry)
            else None
        ),
        error=error,
    )


@router.get("/applications/{application_id}/summary")
def propose_summary(
    application_id: str,
    request: Request,
    user: SignedInUser,
    session: DbSession,
    profile: OwnProfile,
    dialog: str | None = None,
):
    """The Tier-1 page, or with `?dialog=1` the pop-up's partial. Neither calls the provider.

    A GET renders what will be sent and the button; the provider call is the POST (F.0).
    """
    application, track = _target(application_id, session, profile)
    if application is None or track is None:
        return render(request, "not_found.html", user=user, status_code=404)
    popup = dialog == "1"
    if not model_configured():
        return _page(
            request,
            user,
            profile,
            application,
            track,
            session,
            error=_no_model(SUMMARY, user.ui_lang),
            dialog=popup,
        )
    return _page(request, user, profile, application, track, session, dialog=popup)


@router.post("/applications/{application_id}/summary/generate")
def generate_summary_proposal(
    application_id: str,
    request: Request,
    user: SignedInUser,
    session: DbSession,
    profile: OwnProfile,
    dialog: Annotated[str | None, Form()] = None,
):
    """One paid call, on demand: the Tier-1 proposal for this application (F7.3).

    With `dialog=1` the answer is the pop-up's partial; without it, the full page.
    """
    application, track = _target(application_id, session, profile)
    if application is None or track is None:
        return render(request, "not_found.html", user=user, status_code=404)
    popup = dialog == "1"
    if not model_configured():
        return _page(
            request,
            user,
            profile,
            application,
            track,
            session,
            error=_no_model(SUMMARY, user.ui_lang),
            dialog=popup,
        )

    language = report_language(application)
    # Everything the prompt needs is read first, then the reads are ended: a live
    # transaction must not be held across the provider call (the client refuses).
    jd = StructuredJD.model_validate(application.report.get("jd") or {})
    bullets = [
        (str(bullet.id), bullet_text(bullet, language))
        for bullet in track_bullets(profile.id, session, track.id)
    ]
    track_skills = list(track.skills)
    pool = list(pool_skills(profile.id, session))
    grades = grades_of(application)
    session.commit()
    try:
        proposal = generate_summary(
            session,
            jd=jd,
            bullets=bullets,
            track_skills=track_skills,
            pool=pool,
            grades=grades,
            language=language,
            options=CallOptions(profile_id=profile.id),
        )
    except PROVIDER_ERRORS as exc:
        # A paid call that failed is still paid; keep the ledger and report plainly.
        session.commit()
        return _page(
            request,
            user,
            profile,
            application,
            track,
            session,
            error=_failed(exc, SUMMARY, user.ui_lang),
            retry=not isinstance(exc, NoModelConfigured),
            dialog=popup,
        )

    session.commit()
    violations = check_summary(profile.id, session, application, track, proposal.output)
    return _page(
        request,
        user,
        profile,
        application,
        track,
        session,
        proposal=proposal,
        violations=violations,
        dialog=popup,
    )


@router.post("/applications/{application_id}/summary/accept")
def accept_summary_proposal(
    application_id: str,
    request: Request,
    user: SignedInUser,
    session: DbSession,
    profile: OwnProfile,
    payload: Annotated[str, Form()],
    use_in_track: Annotated[str | None, Form()] = None,
    dialog: Annotated[str | None, Form()] = None,
):
    """Accept a proposal: re-validate against the database, then write it (F7.3).

    Only the summary's text and citations are read from the form: a `skills` field an
    older page may still post is ignored, and the track's skills are never written. From
    the pop-up (`dialog=1`) the answer is a redirect to the report with a status line.
    """
    application, track = _target(application_id, session, profile)
    if application is None or track is None:
        return render(request, "not_found.html", user=user, status_code=404)
    try:
        data = json.loads(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="malformed proposal") from exc

    _, violations = accept_summary(
        profile.id,
        session,
        application,
        track,
        text=str((data.get("summary") or {}).get("text") or ""),
        cites=list((data.get("summary") or {}).get("cites") or []),
        use_in_track=is_checked(use_in_track),
    )
    if violations:
        # Refused: shown with the rule that failed, and nothing was written.
        return _page(
            request,
            user,
            profile,
            application,
            track,
            session,
            violations=violations,
            refused=data,
            error=t("generate.refused", user.ui_lang),
        )

    session.commit()
    if dialog == "1":
        return RedirectResponse(f"/applications/{application.id}?summary_saved=1", status_code=303)
    return RedirectResponse(f"/tracks/{track.id}", status_code=303)


# --- N7.3: Tier 3a, one bullet rephrased for this posting --------------------------


def _bullet_target(application_id: str, bullet_id: str, session, profile):
    """The application and the bullet a rephrase would rewrite."""
    application = get_application(profile.id, session, application_id)
    bullet = get_bullet(profile.id, session, bullet_id)
    if application is None or bullet is None:
        return None, None
    return application, bullet


def _bullet_current(bullet, language: str) -> str:
    return (bullet.text_es if language == "es" else bullet.text_en) or ""


def _bullet_page(
    request,
    user,
    profile,
    application,
    bullet,
    language: str,
    *,
    proposal=None,
    violations: list[Violation] | None = None,
    error: str | None = None,
    refused: dict[str, Any] | None = None,
):
    return render(
        request,
        "generate/bullet.html",
        user=user,
        profile=profile,
        application=application,
        bullet=bullet,
        language=language,
        proposal=proposal,
        proposal_json=(
            json.dumps(proposal.output, ensure_ascii=False) if proposal is not None else ""
        ),
        violations=violations or [],
        refused=refused,
        current_text=_bullet_current(bullet, language),
        is_translation=not _bullet_current(bullet, language).strip(),
        run_url=(
            f"/applications/{application.id}/bullets/{bullet.id}/rephrase/generate"
            if proposal is None and refused is None and error is None
            else None
        ),
        error=error,
    )


@router.get("/applications/{application_id}/bullets/{bullet_id}/rephrase")
def propose_bullet(
    application_id: str,
    bullet_id: str,
    request: Request,
    user: SignedInUser,
    session: DbSession,
    profile: OwnProfile,
):
    """The Tier-3a page. A GET renders the button; the provider call is the POST (F.0)."""
    application, bullet = _bullet_target(application_id, bullet_id, session, profile)
    if application is None or bullet is None:
        return render(request, "not_found.html", user=user, status_code=404)
    language = report_language(application)
    if not model_configured():
        return _bullet_page(
            request,
            user,
            profile,
            application,
            bullet,
            language,
            error=_no_model(BULLET, user.ui_lang),
        )
    return _bullet_page(request, user, profile, application, bullet, language)


@router.post("/applications/{application_id}/bullets/{bullet_id}/rephrase/generate")
def generate_bullet_proposal(
    application_id: str,
    bullet_id: str,
    request: Request,
    user: SignedInUser,
    session: DbSession,
    profile: OwnProfile,
):
    """One paid call, on demand: this bullet rewritten for this posting (F7.3, Tier 3a)."""
    application, bullet = _bullet_target(application_id, bullet_id, session, profile)
    if application is None or bullet is None:
        return render(request, "not_found.html", user=user, status_code=404)
    language = report_language(application)
    if not model_configured():
        return _bullet_page(
            request,
            user,
            profile,
            application,
            bullet,
            language,
            error=_no_model(BULLET, user.ui_lang),
        )

    # Everything the prompt reads is computed first; the reads end before the call.
    requirements = [
        str(grade.get("requirement"))
        for grade in (application.report.get("grades") or [])
        if str(grade.get("bullet_id")) == str(bullet.id)
    ]
    texts = {lang: text for lang, text in (("es", bullet.text_es), ("en", bullet.text_en)) if text}
    jd_title = str((application.report.get("jd") or {}).get("title") or "")
    session.commit()
    try:
        proposal = generate_bullet(
            session,
            bullet_id=str(bullet.id),
            texts=texts,
            requirements=requirements,
            jd_title=jd_title,
            language=language,
            options=CallOptions(profile_id=profile.id),
        )
    except PROVIDER_ERRORS as exc:
        session.commit()
        return _bullet_page(
            request,
            user,
            profile,
            application,
            bullet,
            language,
            error=_failed(exc, BULLET, user.ui_lang),
        )

    session.commit()
    violations = check_bullet(profile.id, session, bullet, proposal.output)
    return _bullet_page(
        request,
        user,
        profile,
        application,
        bullet,
        language,
        proposal=proposal,
        violations=violations,
    )


@router.post("/applications/{application_id}/bullets/{bullet_id}/rephrase/accept")
def accept_bullet_proposal(
    application_id: str,
    bullet_id: str,
    request: Request,
    user: SignedInUser,
    session: DbSession,
    profile: OwnProfile,
    payload: Annotated[str, Form()],
):
    """Accept a rephrase: re-validate, then revise the one language column (F7.3)."""
    application, bullet = _bullet_target(application_id, bullet_id, session, profile)
    if application is None or bullet is None:
        return render(request, "not_found.html", user=user, status_code=404)
    try:
        data = json.loads(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="malformed proposal") from exc

    language = report_language(application)
    _, violations = accept_bullet(
        profile.id,
        session,
        bullet.id,
        text=str(data.get("text") or ""),
        cites=list(data.get("cites") or []),
        language=language,
    )
    if violations:
        return _bullet_page(
            request,
            user,
            profile,
            application,
            bullet,
            language,
            violations=violations,
            refused={"text": str(data.get("text") or ""), "cites": list(data.get("cites") or [])},
            error=t("generate.refused", user.ui_lang),
        )

    session.commit()
    return RedirectResponse(f"/applications/{application.id}", status_code=303)


# --- N7.4: Tier 3b, bullets a story supports ---------------------------------------


def _role_text(role) -> str:
    return " ".join(part for part in (role.title_es, role.title_en) if part)


def _story_roles(story, session, profile):
    """The story's own role when it has one, otherwise the roles to choose from."""
    if story.role_id is not None:
        linked = get_role(profile.id, session, story.role_id)
        return [linked] if linked is not None else []
    return list_roles(profile.id, session, active_only=True)


def _story_language(story, lang: str | None) -> str:
    return (lang or story.lang or "es")[:5]


def _story_page(
    request,
    user,
    profile,
    story,
    roles,
    language: str,
    *,
    candidates: list[dict[str, Any]] | None = None,
    error: str | None = None,
):
    return render(
        request,
        "generate/story.html",
        user=user,
        profile=profile,
        story=story,
        roles=roles,
        language=language,
        candidates=candidates or [],
        run_url=(
            f"/stories/{story.id}/bullets/generate"
            if not candidates and error is None
            else None
        ),
        error=error,
    )


@router.get("/stories/{story_id}/bullets")
def propose_story_bullets(
    story_id: str,
    request: Request,
    user: SignedInUser,
    session: DbSession,
    profile: OwnProfile,
    lang: str | None = None,
):
    """The Tier-3b page. A GET renders the button; the provider call is the POST (F.0)."""
    story = get_story(profile.id, session, story_id)
    if story is None:
        return render(request, "not_found.html", user=user, status_code=404)
    language = _story_language(story, lang)
    roles = _story_roles(story, session, profile)
    if not roles:
        return _story_page(
            request,
            user,
            profile,
            story,
            roles,
            language,
            error=t("generate.need_roles", user.ui_lang),
        )
    if not model_configured():
        return _story_page(
            request, user, profile, story, roles, language, error=_no_model(STORY, user.ui_lang)
        )
    return _story_page(request, user, profile, story, roles, language)


@router.post("/stories/{story_id}/bullets/generate")
def generate_story_bullets_proposal(
    story_id: str,
    request: Request,
    user: SignedInUser,
    session: DbSession,
    profile: OwnProfile,
    lang: Annotated[str, Form()] = "",
):
    """One paid call, on demand: up to three bullets this story supports (F7.3, Tier 3b)."""
    story = get_story(profile.id, session, story_id)
    if story is None:
        return render(request, "not_found.html", user=user, status_code=404)
    language = _story_language(story, lang or None)
    roles = _story_roles(story, session, profile)
    if not roles:
        return _story_page(
            request,
            user,
            profile,
            story,
            roles,
            language,
            error=t("generate.need_roles", user.ui_lang),
        )
    if not model_configured():
        return _story_page(
            request, user, profile, story, roles, language, error=_no_model(STORY, user.ui_lang)
        )

    # reads first, then the call; nothing is stored until a candidate is accepted.
    pairs = [(str(role.id), _role_text(role)) for role in roles]
    body = story.body
    session.commit()
    try:
        proposal = generate_story_bullets(
            session,
            story_id=str(story.id),
            body=body,
            roles=pairs,
            language=language,
            options=CallOptions(profile_id=profile.id),
        )
    except PROVIDER_ERRORS as exc:
        session.commit()
        return _story_page(
            request, user, profile, story, roles, language, error=_failed(exc, STORY, user.ui_lang)
        )

    session.commit()
    names = {str(role.id): _role_text(role) for role in roles}
    candidates = []
    for draft in proposal.output.get("bullets") or []:
        violations = check_story_bullet(
            profile.id, session, story, roles, {"bullets": [draft]}
        )
        candidates.append(
            {
                "text": draft["text"],
                "role_id": draft["role_id"],
                "role_name": names.get(str(draft["role_id"]), ""),
                "chips": ", ".join(suggest_skills(profile.id, session, draft["text"])),
                "violations": violations,
            }
        )
    return _story_page(request, user, profile, story, roles, language, candidates=candidates)


@router.post("/stories/{story_id}/bullets/accept")
def accept_story_bullet_proposal(
    story_id: str,
    request: Request,
    user: SignedInUser,
    session: DbSession,
    profile: OwnProfile,
    text: Annotated[str, Form()],
    role_id: Annotated[str, Form()],
    chips: Annotated[str, Form()] = "",
    lang: Annotated[str, Form()] = "",
):
    """Accept one story-derived bullet: validate again, then create it on the role.

    The bullet stores `source_story_id` (PRD 3) and joins no track. The role is
    owner-scoped, so another profile's role is a 404 rather than a refusal.
    """
    story = get_story(profile.id, session, story_id)
    role = get_role(profile.id, session, role_id)
    if story is None or role is None:
        return render(request, "not_found.html", user=user, status_code=404)
    language = _story_language(story, lang or None)
    chip_list = [chip.strip() for chip in chips.split(",") if chip.strip()]

    _, violations = accept_story_bullet(
        profile.id,
        session,
        story_id=story.id,
        role_id=role.id,
        text=text,
        language=language,
        chips=chip_list,
    )
    if violations:
        return _story_page(
            request,
            user,
            profile,
            story,
            [role],
            language,
            candidates=[
                {
                    "text": text,
                    "role_id": str(role.id),
                    "role_name": _role_text(role),
                    "chips": chips,
                    "violations": violations,
                }
            ],
            error=t("generate.refused", user.ui_lang),
        )

    session.commit()
    return RedirectResponse(f"/stories/{story.id}", status_code=303)
