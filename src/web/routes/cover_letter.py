"""The cover letter for one analysis (PRD F8).

The page opens with the letter already assembled — the profile's common blocks and the
**track's** template — and the bridge's place marked. A GET never calls the provider.
"Autogenerar párrafo de interés" is one paid call on a POST that writes one bridge into
its own editable field; "Otra versión" writes a different one, up to five. Everything
else is deterministic: the full letter follows the bridge field in the browser, and
saving stores the text and the template it came from.
"""

import json
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from src.applications import get_application, save_application_letter
from src.extract.client import (
    CallOptions,
    NoModelConfigured,
    ProviderUnavailable,
    StructuredOutputError,
    model_configured,
)
from src.extract.generation import generate_letter_bridge_one
from src.generate.letters import (
    assemble_parts,
    banned_phrases,
    check_bridge,
    highlight_placeholders,
    letter_checklist,
    letter_settings_for,
    material_for_application,
    missing_blocks,
    sentences_in,
    unresolved_placeholders,
    voice_notes_for,
)
from src.generate.proposals import report_language
from src.generate.validators import Violation
from src.i18n import t
from src.letters import template_status, track_template
from src.tracks import get_track, list_tracks
from src.web.deps import DbSession, OwnProfile, SignedInUser
from src.web.templating import render

router = APIRouter()

# F8: five versions of the bridge per application. The hidden `previous` list carries
# the versions already shown, so it holds at most four when the fifth is requested.
MAX_VERSIONS = 5
MAX_PREVIOUS_LENGTH = 1200


def _material_text(material: dict[str, Any], *, limit: int = 40) -> str:
    """The person's material as prompt rows: bullets, then roles, then stories."""
    rows = [
        f"{identifier}\t{text}"
        for group in ("bullets", "roles", "stories")
        for identifier, text in list(material.get(group) or [])[:limit]
    ]
    return "\n".join(rows) if rows else "(none)"


def _repair(hard: list[Violation], soft: list[Violation]) -> str:
    """What the single retry says: the rules the first answer broke, by name."""
    broken = "; ".join(
        dict.fromkeys(
            f"{violation.message} ({violation.text})"
            if violation.rule in ("literal", "banned") and violation.text
            else violation.message
            for violation in [*hard, *soft]
        )
    )
    return (
        f"it broke these rules: {broken}. Fix exactly those: cite only the ids you were "
        "given, keep to four sentences and 90 words, use no banned phrase and no number "
        "that is not in the material or the posting or that the achievements paragraph "
        "already uses, and quote the posting verbatim for any company fact — or leave the "
        "company out."
    )


def _parse_previous(raw: str) -> list[str]:
    """The earlier bridge texts from the hidden field; anything else is a bad request."""
    try:
        data = json.loads(raw or "[]")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="malformed previous versions") from exc
    if (
        not isinstance(data, list)
        or len(data) >= MAX_VERSIONS
        or any(not isinstance(item, str) or len(item) > MAX_PREVIOUS_LENGTH for item in data)
    ):
        raise HTTPException(status_code=400, detail="malformed previous versions")
    return data


def _track_for(profile, session, application, requested: str | None):
    """The application's track, else an owned `?track=`; None means ask the user."""
    if application.track_id is not None:
        return get_track(profile.id, session, application.track_id)
    if requested:
        return get_track(profile.id, session, requested)
    return None


def _picker(request, user, profile, application, session):
    """No track: ask which one the letter is for. It does not change the analysis."""
    return render(
        request,
        "letters/letter.html",
        user=user,
        profile=profile,
        application=application,
        picker=True,
        track=None,
        tracks=list_tracks(profile.id, session, active_only=True),
    )


def _page(
    request,
    user,
    profile,
    application,
    session,
    track,
    *,
    on_get: bool = False,
    notice: str | None = None,
    generated: dict[str, Any] | None = None,
    bridge_field: str = "",
    previous: list[str] | None = None,
    bridge_failed: bool = False,
    error: str | None = None,
):
    """The letter, assembled. `generated` is the bridge a POST just wrote."""
    language = track.lang
    settings = letter_settings_for(profile.id, session, language)
    template = track_template(profile.id, session, track)
    status = template_status(profile.id, session, track)
    blocks_ok = settings is not None and len(missing_blocks(settings)) < 4
    template_ok = status in ("ready", "several")
    posting_language = report_language(application)
    marker = t("letters.bridge_marker", user.ui_lang)
    previous = previous or []

    context: dict[str, Any] = {
        "picker": False,
        "application": application,
        "track": track,
        "language": language,
        "posting_language": posting_language,
        "language_notice": posting_language != language,
        "blocks_ok": blocks_ok,
        "template_ok": template_ok,
        "several": status == "several",
        "ready": blocks_ok and template_ok,
        "notice": notice,
        "error": error,
        "bridge_failed": bridge_failed,
        "marker": marker,
        "previous": previous,
        "previous_json": json.dumps(previous, ensure_ascii=False),
        "versions": len(previous),
        "at_limit": len(previous) >= MAX_VERSIONS,
        "generated": generated,
        "bridge_field": bridge_field,
        "saved": application.letter_text,
    }
    if context["ready"]:
        parts = assemble_parts(
            settings=settings,
            template=template,
            application=application,
            language=language,
        )
        unresolved = parts["unresolved"]
        # A saved letter opens in edited mode; any POST re-render rebuilds from the blocks.
        edited = on_get and bool(application.letter_text)
        bridge = bridge_field
        full = (
            application.letter_text
            if edited
            else "\n\n".join(
                block for block in (parts["before"], bridge or marker, parts["after"]) if block
            )
        )
        checklist = None
        caption = None
        if generated is not None:
            checklist = letter_checklist(
                text=full,
                application=application,
                language=template.lang,
                unresolved=unresolved,
                facts_attributed=True,
                track_lang=language,
                bridge_text=bridge,
            )
            caption = "letters.check_caption_generated"
        elif edited:
            checklist = letter_checklist(
                text=full,
                application=application,
                language=template.lang,
                unresolved=unresolved_placeholders(full),
                facts_attributed=True,
                track_lang=language,
                banned_text=full,
            )
            caption = "letters.check_caption_saved"
        context.update(
            before=parts["before"],
            after=parts["after"],
            before_html=highlight_placeholders(parts["before"], unresolved),
            after_html=highlight_placeholders(parts["after"], unresolved),
            unresolved=unresolved,
            edited=edited,
            full_text=full,
            checklist=checklist,
            checklist_caption=caption,
        )
    return render(request, "letters/letter.html", user=user, profile=profile, **context)


@router.get("/applications/{application_id}/letter")
def application_letter(
    application_id: str,
    request: Request,
    user: SignedInUser,
    session: DbSession,
    profile: OwnProfile,
    track: str | None = None,
    saved: str | None = None,
):
    """The letter page. A GET renders; the provider call is the POST (F8)."""
    application = get_application(profile.id, session, application_id)
    if application is None:
        return render(request, "not_found.html", user=user, status_code=404)
    chosen = _track_for(profile, session, application, track)
    if chosen is None:
        return _picker(request, user, profile, application, session)
    notice = t("letters.letter_saved_notice", user.ui_lang) if saved == "1" else None
    return _page(request, user, profile, application, session, chosen, on_get=True, notice=notice)


@router.post("/applications/{application_id}/letter/generate")
def application_letter_generate(
    application_id: str,
    request: Request,
    user: SignedInUser,
    session: DbSession,
    profile: OwnProfile,
    track_id: Annotated[str | None, Form()] = None,
    previous: Annotated[str, Form()] = "[]",
    bridge: Annotated[str, Form()] = "",
):
    """One paid call writes one bridge; one retry when any rule fails (F8.3)."""
    application = get_application(profile.id, session, application_id)
    if application is None:
        return render(request, "not_found.html", user=user, status_code=404)
    earlier = _parse_previous(previous)
    track = _track_for(profile, session, application, track_id)
    if track is None:
        raise HTTPException(status_code=404)

    def page(**extra):
        return _page(
            request, user, profile, application, session, track,
            previous=earlier, bridge_field=bridge, **extra,
        )

    language = track.lang
    settings = letter_settings_for(profile.id, session, language)
    template = track_template(profile.id, session, track)
    status = template_status(profile.id, session, track)
    if settings is None or len(missing_blocks(settings)) == 4 or status not in ("ready", "several"):
        return page()  # the page names what is missing and links to the fix; no call
    if not model_configured():
        return page(error=t("analyze.no_model", user.ui_lang))

    # Everything the prompt reads is computed first; the reads end before the call.
    material, sources = material_for_application(profile.id, session, application, language)
    material_text = _material_text(material)
    voice_notes = voice_notes_for(profile.id, session, language)
    banned = banned_phrases(language)
    session.commit()

    cost = Decimal(0)
    proposal = None
    hard: list[Violation] = []
    soft: list[Violation] = []
    # One retry, then report: a failing bridge is never weakened until it passes (F8.3).
    for attempt in range(2):
        try:
            proposal = generate_letter_bridge_one(
                session,
                jd_text=application.jd_text,
                company=application.company,
                title=application.title,
                template=template,
                material=material_text,
                voice_notes=voice_notes,
                language=language,
                banned=banned,
                previous=earlier,
                repair=_repair(hard, soft) if attempt else None,
                options=CallOptions(profile_id=profile.id),
            )
        except (NoModelConfigured, ProviderUnavailable, StructuredOutputError):
            session.commit()
            return page(error=t("generate.failed", user.ui_lang))
        cost += Decimal(str(proposal.completion.cost_usd))
        hard, soft = check_bridge(
            proposal.output,
            sources=sources,
            template=template,
            jd_text=application.jd_text,
            company=application.company,
            title=application.title,
            lang=language,
        )
        if not hard and not soft:
            break
    session.commit()

    if hard or proposal is None:
        return page(bridge_failed=True)
    text = proposal.output["text"]
    shown = [*earlier, text]
    return _page(
        request,
        user,
        profile,
        application,
        session,
        track,
        previous=shown,
        bridge_field=text,
        generated={
            "version": len(shown),
            "angle": proposal.output["angle"],
            "risk": proposal.output["risk"],
            # The soft failures the page marks: the counts are localised in the template.
            "sentences": len(sentences_in(text)),
            "words": len(text.split()),
            "banned": [violation.text for violation in soft if violation.rule == "banned"],
            "cost": f"{cost:.6f}",
        },
    )


@router.post("/applications/{application_id}/letter/save")
def application_letter_save(
    application_id: str,
    request: Request,
    user: SignedInUser,
    session: DbSession,
    profile: OwnProfile,
    text: Annotated[str, Form()] = "",
    track_id: Annotated[str | None, Form()] = None,
):
    """Store the letter that was sent (F8.5): the text and the template it came from."""
    application = get_application(profile.id, session, application_id)
    if application is None:
        return render(request, "not_found.html", user=user, status_code=404)
    track = _track_for(profile, session, application, track_id)
    template = track_template(profile.id, session, track) if track is not None else None
    save_application_letter(
        profile.id,
        session,
        application_id,
        text=text,
        template_id=template.id if template is not None else None,
    )
    session.commit()
    suffix = f"&track={track.id}" if track is not None else ""
    return RedirectResponse(
        f"/applications/{application_id}/letter?saved=1{suffix}", status_code=303
    )
