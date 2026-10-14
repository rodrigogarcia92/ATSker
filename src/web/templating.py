"""Template rendering with the interface language and the current user injected."""

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.templating import Jinja2Templates

from src.config import get_settings
from src.i18n import DEFAULT_LANG, t
from src.models import User
from src.normalize.text import fold
from src.web.alerts import advice_layout, advice_line, language_alert

_TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
_TEMPLATES.env.globals["t"] = t
_TEMPLATES.env.globals["app_name"] = t("app.name", DEFAULT_LANG)
# The report's F4.2 sentence: built from the stored alert and the reader's language,
# so the two languages' list wording lives in one testable place.
_TEMPLATES.env.globals["language_alert"] = language_alert
# F7.2's advice lines: the stored item is ids and numbers, the sentence is the page's.
_TEMPLATES.env.globals["advice_line"] = advice_line
# U5: the same items, grouped and split at the first three.
_TEMPLATES.env.globals["advice_layout"] = advice_layout
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

# The scorer writes its matched/missing tags in English (`3.00 years`) and is frozen,
# so the display localises the one shape it produces (F.0).
_YEARS_TERM = re.compile(r"^(\d+(?:[.,]\d+)?)\s*years?$", re.IGNORECASE)


def localised_term(value: object, lang: str = DEFAULT_LANG) -> str:
    """A sub-score's matched/missing term, in the reader's language (F.0)."""
    text = str(value)
    match = _YEARS_TERM.match(text.strip())
    if match is None:
        return text
    years = short_years(match.group(1).replace(",", "."))
    return t("report.experience_years_tag", lang, years=years)


_TEMPLATES.env.filters["localised_term"] = localised_term


def relative_time(value: object, lang: str = DEFAULT_LANG) -> str:
    """A moment as its rough distance from now (§12.8's state lines and activity).

    Minutes, then hours, then days; after a week it gives way to the date itself, so
    nothing ever reads "hace 39 días". A missing timestamp is the empty string, never a
    "hace 0 minutos". The clock is read here, not passed in: this is presentation, and
    the value it formats is the one the row carries.
    """
    if not isinstance(value, datetime):
        return ""
    moment = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    minutes = int((datetime.now(UTC) - moment).total_seconds() // 60)
    if minutes < 60:
        count = max(1, minutes)
        return t("time.minute" if count == 1 else "time.minutes", lang, n=count)
    if minutes < 60 * 24:
        count = minutes // 60
        return t("time.hour" if count == 1 else "time.hours", lang, n=count)
    days = minutes // (60 * 24)
    if days < 7:
        return t("time.day" if days == 1 else "time.days", lang, n=days)
    return moment.strftime("%Y-%m-%d")


_TEMPLATES.env.filters["relative_time"] = relative_time


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
