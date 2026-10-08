"""What a failed generation says, and what it logs (PRD §12.5).

A failed proposal names which of three things went wrong — no model is configured, the
provider did not answer, or the answer was not usable — instead of one generic sentence. The
log line carries the error class and the purpose, never any text the model saw or said.
Shared by every route that makes a paid generation call on demand.
"""

import logging

from src.extract.client import NoModelConfigured, ProviderUnavailable, StructuredOutputError
from src.i18n import t

logger = logging.getLogger(__name__)

SUMMARY = "generate_summary"
BULLET = "generate_bullet"
STORY = "story_bullets"
KEYWORDS = "keyword_infer"
PROVIDER_ERRORS = (NoModelConfigured, ProviderUnavailable, StructuredOutputError)


def no_model(purpose: str, lang: str) -> str:
    """Nothing is configured to call: said before a call is attempted."""
    logger.warning("generation refused: purpose=%s error=NoModelConfigured", purpose)
    return t("generate.err.no_model", lang)


def failed(exc: BaseException, purpose: str, lang: str) -> str:
    """Which of the three it was: no model, the provider, or an answer nobody can use."""
    logger.warning("generation failed: purpose=%s error=%s", purpose, type(exc).__name__)
    if isinstance(exc, NoModelConfigured):
        return t("generate.err.no_model", lang)
    if isinstance(exc, ProviderUnavailable):
        return t("generate.err.provider", lang)
    return t("generate.err.unusable", lang)
