"""Template rendering with the interface language and the current user injected."""

from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.templating import Jinja2Templates

from src.config import get_settings
from src.i18n import DEFAULT_LANG, t
from src.models import User
from src.normalize.text import fold
from src.web.alerts import advice_line, language_alert

_TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
_TEMPLATES.env.globals["t"] = t
_TEMPLATES.env.globals["app_name"] = t("app.name", DEFAULT_LANG)
# The report's F4.2 sentence: built from the stored alert and the reader's language,
# so the two languages' list wording lives in one testable place.
_TEMPLATES.env.globals["language_alert"] = language_alert
# F7.2's advice lines: the stored item is ids and numbers, the sentence is the page's.
_TEMPLATES.env.globals["advice_line"] = advice_line
# `fold` (lowercase, unaccented) is how the data compares terms, so a template that
# matches a typed chip against a stored term must fold both sides the same way
# (F2.9's pending terms, which the user may have typed with capitals or accents).
_TEMPLATES.env.filters["fold"] = fold


def short_years(value: object) -> str:
    """Years with at most one decimal and no trailing `.0` (N6.6).

    `3.0` reads as "3", `2.5` as "2.5" — a rounded figure the reader can trust at a
    glance, and never the "0.00 de 0.00" the report used to print.
    """
    text = f"{float(value):.1f}"  # type: ignore[arg-type]
    return text[:-2] if text.endswith(".0") else text


# The report's Experience card shows years in the interface's language and trimmed.
_TEMPLATES.env.filters["years"] = short_years


def render(
    request: Request,
    template: str,
    *,
    user: User | None = None,
    lang: str | None = None,
    status_code: int = 200,
    **context: Any,
):
    """The interface language comes from the user's preference, never the document."""
    preference = user.ui_lang if user is not None else None
    language = lang or preference or get_settings().ui_default_lang
    return _TEMPLATES.TemplateResponse(
        request,
        template,
        {"user": user, "lang": language, **context},
        status_code=status_code,
    )
