"""Spanish and English interface strings.

`en` may lag `es`: a missing translation falls back to the default language and
then to the key itself, so a half-translated screen renders in Spanish rather
than showing an empty cell.
"""

DEFAULT_LANG = "es"
LANGUAGES = ("es", "en")

STRINGS: dict[str, dict[str, str]] = {
    "app.name": {"es": "ATSker", "en": "ATSker"},
    "app.tagline": {
        "es": "Evaluación de encaje entre tu currículum y una oferta",
        "en": "How well your résumé matches a job posting",
    },
    "nav.dashboard": {"es": "Panel", "en": "Dashboard"},
    "nav.profile": {"es": "Perfil", "en": "Profile"},
    "nav.logout": {"es": "Salir", "en": "Log out"},
    "nav.language": {"es": "Idioma", "en": "Language"},
    "login.title": {"es": "Entrar", "en": "Sign in"},
    "login.email": {"es": "Correo", "en": "Email"},
    "login.password": {"es": "Contraseña", "en": "Password"},
    "login.submit": {"es": "Entrar", "en": "Sign in"},
    "login.invalid": {
        "es": "Correo o contraseña incorrectos.",
        "en": "Wrong email or password.",
    },
    "login.rate_limited": {
        "es": "Demasiados intentos fallidos. Prueba de nuevo en 15 minutos.",
        "en": "Too many failed attempts. Try again in 15 minutes.",
    },
    "dashboard.title": {"es": "Panel", "en": "Dashboard"},
    "dashboard.welcome": {"es": "Hola, {name}", "en": "Hello, {name}"},
    "dashboard.empty": {
        "es": "Todavía no hay currículums. La importación llega en el siguiente paso.",
        "en": "No résumés yet. Import arrives in the next step.",
    },
    "profile.title": {"es": "Perfil", "en": "Profile"},
    "profile.display_name": {"es": "Nombre", "en": "Name"},
    "profile.not_found": {"es": "Perfil no encontrado.", "en": "Profile not found."},
    "common.and": {"es": "y", "en": "and"},
}


def t(key: str, lang: str | None = None, **values: object) -> str:
    entry = STRINGS.get(key)
    if entry is None:
        return key
    text = entry.get(lang or DEFAULT_LANG) or entry.get(DEFAULT_LANG) or key
    return text.format(**values) if values else text
