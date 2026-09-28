"""The cover letter for one analysis (PRD F8, N8.4).

One paid call chooses a template and writes three bridges; everything after that is
assembly, and assembly is deterministic. The page renders every candidate-template ×
surviving-variant combination so switching between them is a swap in the browser, not
another call. Saving stores the text and the template it came from.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from src.applications import get_application, save_application_letter
from src.extract.client import (
    CallOptions,
    NoModelConfigured,
    ProviderUnavailable,
    StructuredOutputError,
    model_configured,
)
from src.extract.generation import generate_letter_bridge
from src.generate.letters import (
    assemble_letter,
    check_variants,
    highlight_placeholders,
    letter_candidates,
    letter_checklist,
    letter_settings_for,
    material_for_application,
    numbers_in,
)
from src.generate.proposals import report_language
from src.generate.validators import Violation
from src.i18n import t
from src.web.deps import DbSession, OwnProfile, SignedInUser
from src.web.templating import render

router = APIRouter()

# What a repair retry says: the same rules, named as the failure the checker saw.
_REPAIR = (
    "cite only the ids you were given, keep every variant to 2-4 sentences and at most "
    "90 words, use no number that is not in the material or the posting, and quote the "
    "posting verbatim for any company fact — or leave the company out."
)


def _material_text(material: dict[str, Any], *, limit: int = 40) -> str:
    """The person's material as prompt rows: bullets, then roles, then stories."""
    rows = [
        f"{identifier}\t{text}"
        for group in ("bullets", "roles", "stories")
        for identifier, text in list(material.get(group) or [])[:limit]
    ]
    return "\n".join(rows) if rows else "(none)"


def _options(
    application,
    settings,
    candidates,
    output: dict[str, Any],
) -> list[dict[str, Any]]:
    """Every template × variant, assembled — no further call (F8.4's UI)."""
    language = report_language(application)
    options: list[dict[str, Any]] = []
    for template in candidates:
        forbidden = numbers_in(template.achievements)
        for index, variant in enumerate(output.get("variants") or []):
            assembled = assemble_letter(
                settings=settings,
                template=template,
                bridge_text=variant["text"],
                application=application,
                language=language,
            )
            options.append(
                {
                    "key": f"{template.id}:{index}",
                    "checklist": letter_checklist(
                        text=assembled["text"],
                        application=application,
                        language=language,
                        unresolved=assembled["unresolved"],
                        facts_attributed=(
                            variant.get("company_fact") is None
                            or bool((variant.get("company_fact") or {}).get("jd_quote"))
                        ),
                    ),
                    "template_id": str(template.id),
                    "template_name": template.name,
                    "index": index,
                    "angle": variant.get("angle") or "",
                    "variant_text": variant["text"],
                    "sources": variant.get("sources") or [],
                    "company_fact": variant.get("company_fact"),
                    "warning": sorted(numbers_in(variant["text"]) & forbidden),
                    "letter_text": assembled["text"],
                    "highlighted": highlight_placeholders(
                        assembled["text"], assembled["unresolved"]
                    ),
                    "unresolved": assembled["unresolved"],
                    "default": str(template.id) == str(output.get("template_id")) and index == 0,
                }
            )
    return options


def _page(
    request,
    user,
    profile,
    application,
    session,
    *,
    bridge: dict[str, Any] | None = None,
    options: list[dict[str, Any]] | None = None,
    violations: list[Violation] | None = None,
    error: str | None = None,
    cost: str | None = None,
):
    language = report_language(application)
    settings = letter_settings_for(profile.id, session, language)
    candidates = letter_candidates(profile.id, session, application, language)
    if error is None:
        # The page says what is missing before any call is offered (F8, N8.4).
        if settings is None:
            error = t("letters.letter_no_settings", user.ui_lang)
        elif not candidates:
            error = t("letters.letter_no_candidates", user.ui_lang)
    run_url = (
        f"/applications/{application.id}/letter/generate"
        if bridge is None and error is None and candidates and settings is not None
        else None
    )
    return render(
        request,
        "letters/letter.html",
        user=user,
        profile=profile,
        application=application,
        language=language,
        settings=settings,
        candidates=candidates,
        saved=application.letter_text,
        bridge=bridge,
        options=options or [],
        violations=violations or [],
        run_url=run_url,
        cost=cost,
        error=error,
    )


@router.get("/applications/{application_id}/letter")
def application_letter(
    application_id: str,
    request: Request,
    user: SignedInUser,
    session: DbSession,
    profile: OwnProfile,
):
    """The letter page. A GET renders; the provider call is the POST (F8)."""
    application = get_application(profile.id, session, application_id)
    if application is None:
        return render(request, "not_found.html", user=user, status_code=404)
    return _page(request, user, profile, application, session)


@router.post("/applications/{application_id}/letter/generate")
def application_letter_generate(
    application_id: str,
    request: Request,
    user: SignedInUser,
    session: DbSession,
    profile: OwnProfile,
):
    """One paid call: choose a template and write three bridges, then assemble (N8.4)."""
    application = get_application(profile.id, session, application_id)
    if application is None:
        return render(request, "not_found.html", user=user, status_code=404)
    language = report_language(application)
    settings = letter_settings_for(profile.id, session, language)
    candidates = letter_candidates(profile.id, session, application, language)
    if settings is None or not candidates:
        key = (
            "letters.letter_no_settings"
            if settings is None
            else "letters.letter_no_candidates"
        )
        return _page(
            request,
            user,
            profile,
            application,
            session,
            error=t(key, user.ui_lang),
        )
    if not model_configured():
        return _page(
            request, user, profile, application, session, error=t("analyze.no_model", user.ui_lang)
        )

    material, sources = material_for_application(profile.id, session, application, language)
    material_text = _material_text(material)
    templates_payload = [
        {
            "id": str(letter.id),
            "name": letter.name,
            "applies_when": letter.applies_when,
            "achievements": letter.achievements,
        }
        for letter in candidates
    ]
    voice_notes = settings.voice_notes
    session.commit()

    proposal = None
    violations: list[Violation] = []
    survivors: list[dict[str, Any]] = []
    # One retry, then report: a failure is never weakened until it passes (F8).
    for attempt in range(2):
        try:
            proposal = generate_letter_bridge(
                session,
                jd_text=application.jd_text,
                company=application.company,
                title=application.title,
                templates=templates_payload,
                material=material_text,
                voice_notes=voice_notes,
                language=language,
                repair=_REPAIR if attempt else None,
                options=CallOptions(profile_id=profile.id),
            )
        except (NoModelConfigured, ProviderUnavailable, StructuredOutputError):
            session.commit()
            return _page(
                request,
                user,
                profile,
                application,
                session,
                error=t("generate.failed", user.ui_lang),
            )
        chosen = next(
            (
                letter
                for letter in candidates
                if str(letter.id) == str(proposal.output.get("template_id"))
            ),
            candidates[0],
        )
        survivors, violations = check_variants(
            proposal.output,
            sources=sources,
            candidates=candidates,
            jd_text=application.jd_text,
            company=application.company,
            title=application.title,
            achievements_text=chosen.achievements,
        )
        if not violations or attempt == 1:
            break

    session.commit()
    if proposal is None:
        return _page(
            request, user, profile, application, session, error=t("generate.failed", user.ui_lang)
        )
    output = {**proposal.output, "variants": survivors}
    options = _options(application, settings, candidates, output) if survivors else []
    return _page(
        request,
        user,
        profile,
        application,
        session,
        bridge=output,
        options=options,
        violations=violations,
        cost=f"{proposal.completion.cost_usd}",
    )


@router.post("/applications/{application_id}/letter/save")
def application_letter_save(
    application_id: str,
    request: Request,
    user: SignedInUser,
    session: DbSession,
    profile: OwnProfile,
    text: Annotated[str, Form()] = "",
    template_id: Annotated[str | None, Form()] = None,
):
    """Store the letter that was sent (F8.5): the text and the template it came from."""
    letter = save_application_letter(
        profile.id, session, application_id, text=text, template_id=template_id
    )
    if letter is None:
        return render(request, "not_found.html", user=user, status_code=404)
    session.commit()
    return RedirectResponse(f"/applications/{application_id}/letter", status_code=303)
