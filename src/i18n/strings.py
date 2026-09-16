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
    # Shell
    "nav.dashboard": {"es": "Panel", "en": "Dashboard"},
    "nav.profile": {"es": "Perfil", "en": "Profile"},
    "nav.roles": {"es": "Trayectoria", "en": "Experience"},
    "nav.stories": {"es": "Historias", "en": "Stories"},
    "nav.letters": {"es": "Cartas", "en": "Letters"},
    "nav.vocabulary": {"es": "Vocabulario", "en": "Vocabulary"},
    "nav.logout": {"es": "Salir", "en": "Log out"},
    "nav.language": {"es": "Idioma", "en": "Language"},
    # Shared
    "common.save": {"es": "Guardar", "en": "Save"},
    "common.create": {"es": "Crear", "en": "Create"},
    "common.cancel": {"es": "Cancelar", "en": "Cancel"},
    "common.edit": {"es": "Editar", "en": "Edit"},
    "common.delete": {"es": "Eliminar", "en": "Delete"},
    "common.deactivate": {"es": "Desactivar", "en": "Deactivate"},
    "common.reactivate": {"es": "Reactivar", "en": "Reactivate"},
    "common.active": {"es": "activo", "en": "active"},
    "common.inactive": {"es": "inactivo", "en": "inactive"},
    "common.optional": {"es": "opcional", "en": "optional"},
    "common.none": {"es": "—", "en": "—"},
    "common.back": {"es": "Volver", "en": "Back"},
    "common.empty": {"es": "Sin datos todavía.", "en": "Nothing here yet."},
    "common.not_found": {"es": "No encontrado.", "en": "Not found."},
    "common.required": {"es": "Obligatorio", "en": "Required"},
    # Login
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
    # Dashboard
    "dashboard.title": {"es": "Panel", "en": "Dashboard"},
    "dashboard.welcome": {"es": "Hola, {name}", "en": "Hello, {name}"},
    "dashboard.roles": {"es": "Puestos", "en": "Roles"},
    "dashboard.bullets": {"es": "Viñetas activas", "en": "Active bullets"},
    "dashboard.stories": {"es": "Historias", "en": "Stories"},
    "dashboard.letters": {"es": "Plantillas de carta", "en": "Letter templates"},
    "dashboard.educations": {"es": "Formación", "en": "Education"},
    "dashboard.metrics": {"es": "Métricas detectadas", "en": "Detected metrics"},
    "dashboard.empty": {
        "es": "Empieza por tu trayectoria: puestos y viñetas.",
        "en": "Start with your experience: roles and bullets.",
    },
    "dashboard.next": {
        "es": "La importación de PDF o Word llega en el siguiente paso.",
        "en": "PDF or Word import arrives in the next step.",
    },
    # Profile
    "profile.title": {"es": "Perfil", "en": "Profile"},
    "profile.display_name": {"es": "Nombre", "en": "Name"},
    "profile.headline": {"es": "Titular", "en": "Headline"},
    "profile.summary": {"es": "Resumen", "en": "Summary"},
    "profile.education": {"es": "Formación", "en": "Education"},
    "profile.institution": {"es": "Institución", "en": "Institution"},
    "profile.degree": {"es": "Título", "en": "Degree"},
    "profile.field": {"es": "Área", "en": "Field"},
    "profile.start": {"es": "Inicio", "en": "Start"},
    "profile.end": {"es": "Fin", "en": "End"},
    "profile.add_education": {"es": "Añadir formación", "en": "Add education"},
    "profile.no_education": {"es": "Sin formación registrada.", "en": "No education recorded."},
    "profile.vocabulary_hint": {
        "es": "El vocabulario compartido de habilidades se revisa en Vocabulario.",
        "en": "The shared skill vocabulary is reviewed under Vocabulary.",
    },
    # Roles
    "roles.title": {"es": "Trayectoria", "en": "Experience"},
    "roles.new": {"es": "Nuevo puesto", "en": "New role"},
    "roles.employer": {"es": "Empleador", "en": "Employer"},
    "roles.position": {"es": "Puesto", "en": "Job title"},
    "roles.start": {"es": "Desde", "en": "From"},
    "roles.end": {"es": "Hasta", "en": "To"},
    "roles.present": {"es": "actualidad", "en": "present"},
    "roles.bullets": {"es": "viñetas", "en": "bullets"},
    "roles.empty": {
        "es": "Todavía no hay puestos. Añade el primero.",
        "en": "No roles yet. Add the first one.",
    },
    "roles.dates_hint": {
        "es": "Formato AAAA-MM-DD. Deja «Hasta» vacío si sigues ahí.",
        "en": "Format YYYY-MM-DD. Leave “To” empty if you are still there.",
    },
    "roles.deactivate_hint": {
        "es": "Desactivar conserva el puesto para los informes ya generados.",
        "en": "Deactivating keeps the role for reports already generated.",
    },
    # Bullets
    "bullets.title": {"es": "Viñetas", "en": "Bullets"},
    "bullets.new": {"es": "Nueva viñeta", "en": "New bullet"},
    "bullets.edit": {"es": "Editar viñeta", "en": "Edit bullet"},
    "bullets.text_es": {"es": "Texto (ES)", "en": "Text (ES)"},
    "bullets.text_en": {"es": "Texto (EN)", "en": "Text (EN)"},
    "bullets.need_text": {
        "es": "Escribe la viñeta en al menos un idioma.",
        "en": "Write the bullet in at least one language.",
    },
    "bullets.skills": {"es": "Habilidades", "en": "Skills"},
    "bullets.skills_hint": {
        "es": "Separadas por comas. Se guardan como nombres canónicos del vocabulario; "
        "las desconocidas se registran para revisión.",
        "en": "Comma-separated. Stored as canonical vocabulary names; unknown ones are "
        "logged for review.",
    },
    "bullets.detect": {"es": "Detectar del texto", "en": "Detect from text"},
    "bullets.detected": {"es": "Detectadas: {names}", "en": "Detected: {names}"},
    "bullets.detected_none": {
        "es": "No se reconoció ninguna habilidad del vocabulario.",
        "en": "No vocabulary skills were recognised.",
    },
    "bullets.metrics": {"es": "Métricas", "en": "Metrics"},
    "bullets.metrics_none": {"es": "sin números", "en": "no numbers"},
    "bullets.empty": {"es": "Sin viñetas en este puesto.", "en": "No bullets in this role."},
    # Stories
    "stories.title": {"es": "Historias", "en": "Stories"},
    "stories.new": {"es": "Nueva historia", "en": "New story"},
    "stories.story_title": {"es": "Título", "en": "Title"},
    "stories.body": {"es": "Relato", "en": "Story"},
    "stories.body_hint": {
        "es": "Narrativa larga: situación, acción y resultado. No entra en el currículum.",
        "en": "Long form: situation, action, result. It never enters a résumé.",
    },
    "stories.role": {"es": "Puesto relacionado", "en": "Related role"},
    "stories.no_role": {"es": "sin puesto", "en": "no role"},
    "stories.tags": {"es": "Etiquetas", "en": "Tags"},
    "stories.lang": {"es": "Idioma", "en": "Language"},
    "stories.related_bullets": {"es": "Viñetas relacionadas", "en": "Related bullets"},
    "stories.related_hint": {
        "es": "Marca las viñetas que esta historia respalda.",
        "en": "Tick the bullets this story backs up.",
    },
    "stories.empty": {"es": "Todavía no hay historias.", "en": "No stories yet."},
    "stories.linked": {"es": "{count} viñetas enlazadas", "en": "{count} linked bullets"},
    "stories.suggest": {"es": "Sugerir etiquetas", "en": "Suggest tags"},
    "stories.suggest_hint": {
        "es": "El modelo propone puesto, viñetas y habilidades; tú confirmas antes de guardar.",
        "en": "The model proposes role, bullets and skills; you confirm before saving.",
    },
    "stories.suggest_no_model": {
        "es": "No hay modelo configurado (OPENROUTER_MODEL). Puedes etiquetar a mano.",
        "en": "No model is configured (OPENROUTER_MODEL). You can tag by hand.",
    },
    "stories.suggest_failed": {
        "es": "La sugerencia no se pudo completar. Nada se ha guardado.",
        "en": "The suggestion could not be completed. Nothing was saved.",
    },
    "stories.suggest_applied": {
        "es": "Propuesta cargada en el formulario. Revísala y guarda.",
        "en": "Proposal loaded into the form. Review it and save.",
    },
    "stories.delete_confirm": {
        "es": "¿Eliminar esta historia? No se puede deshacer.",
        "en": "Delete this story? This cannot be undone.",
    },
    # Letters
    "letters.title": {"es": "Plantillas de carta", "en": "Letter templates"},
    "letters.new": {"es": "Nueva plantilla", "en": "New template"},
    "letters.name": {"es": "Nombre", "en": "Name"},
    "letters.applies_when": {"es": "Cuándo usarla", "en": "When to use it"},
    "letters.applies_when_hint": {
        "es": "La selección de plantilla lee esta descripción; no hay taxonomía interna.",
        "en": "Template selection reads this description; there is no built-in taxonomy.",
    },
    "letters.presentation": {"es": "Párrafo de presentación", "en": "Presentation paragraph"},
    "letters.achievements": {"es": "Párrafo de logros", "en": "Achievements paragraph"},
    "letters.empty": {"es": "Todavía no hay plantillas.", "en": "No templates yet."},
    "letters.delete_confirm": {
        "es": "¿Eliminar esta plantilla?",
        "en": "Delete this template?",
    },
    # Vocabulary
    "vocabulary.title": {"es": "Vocabulario", "en": "Vocabulary"},
    "vocabulary.canonical": {"es": "Canónico", "en": "Canonical"},
    "vocabulary.aliases": {"es": "Alias", "en": "Aliases"},
    "vocabulary.lang_tags": {"es": "Idiomas", "en": "Languages"},
    "vocabulary.skills": {"es": "Habilidades", "en": "Skills"},
    "vocabulary.unmapped": {"es": "Términos sin mapear", "en": "Unmapped terms"},
    "vocabulary.seen": {"es": "veces", "en": "seen"},
    "vocabulary.unmapped_hint": {
        "es": "Un revisor humano promueve los alias aprobados; no hay expansión automática.",
        "en": "A human reviewer promotes approved aliases; there is no automatic expansion.",
    },
    "vocabulary.no_unmapped": {
        "es": "No hay términos pendientes.",
        "en": "No pending terms.",
    },
    "vocabulary.status": {"es": "Estado", "en": "Status"},
}


def t(key: str, lang: str | None = None, **values: object) -> str:
    entry = STRINGS.get(key)
    if entry is None:
        return key
    text = entry.get(lang or DEFAULT_LANG) or entry.get(DEFAULT_LANG) or key
    return text.format(**values) if values else text
