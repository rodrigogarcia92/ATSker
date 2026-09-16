"""Template rendering with the interface language and the current user injected."""

from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.templating import Jinja2Templates

from src.config import get_settings
from src.i18n import DEFAULT_LANG, t
from src.models import User

_TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
_TEMPLATES.env.globals["t"] = t
_TEMPLATES.env.globals["app_name"] = t("app.name", DEFAULT_LANG)


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
