"""Interface strings — `t(key, lang)` (PRD 8).

No Babel, no gettext: at this scale a nested dict plus a lookup is the whole
mechanism. Document language is a separate variable and never consulted here.
"""

from src.i18n.strings import DEFAULT_LANG, LANGUAGES, STRINGS, t

__all__ = ["DEFAULT_LANG", "LANGUAGES", "STRINGS", "t"]
