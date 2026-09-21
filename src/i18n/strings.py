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
    "nav.analyze": {"es": "Analizar", "en": "Analyse"},
    "nav.import": {"es": "Importar", "en": "Import"},
    "nav.tracks": {"es": "Puestos objetivo", "en": "Tracks"},
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
    "common.ledger_unrecorded": {
        "es": "El modelo respondió, pero la llamada no se pudo registrar en la base de "
        "datos: no aparecerá en el coste y la caché no la reutilizará.",
        "en": "The model answered, but the call could not be recorded in the database: "
        "it will not appear in the cost and the cache will not reuse it.",
    },
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
    "dashboard.next": {
        "es": "Sube tu currículum en PDF o Word: se extrae y lo revisas antes de "
        "guardar nada.",
        "en": "Upload your résumé as PDF or Word: it is extracted and you review it "
        "before anything is saved.",
    },
    "dashboard.empty": {
        "es": "Empieza por tu trayectoria, o importa un currículum y revísalo.",
        "en": "Start with your experience, or import a résumé and review it.",
    },
    # Analysis (M5b) — the form, and the report the analysis leaves behind
    "analyze.title": {"es": "Analizar una oferta", "en": "Analyse a posting"},
    "analyze.intro": {
        "es": "Pega el texto de la oferta. Se extraen los requisitos, se contrastan "
        "con tus viñetas y el informe queda guardado.",
        "en": "Paste the posting. Its requirements are extracted, graded against your "
        "bullets, and the report is kept.",
    },
    "analyze.jd": {"es": "Descripción del puesto", "en": "Job description"},
    "analyze.jd_hint": {
        "es": "El texto completo, tal como se publica. El idioma del puesto decide el "
        "idioma de la salida, nunca el de la interfaz.",
        "en": "The full text, as published. The posting's language decides the language "
        "of the output, never the interface's.",
    },
    "analyze.company": {"es": "Empresa (opcional)", "en": "Company (optional)"},
    "analyze.role_title": {"es": "Puesto (opcional)", "en": "Role (optional)"},
    "analyze.optional_hint": {
        "es": "Si dejas el puesto vacío se usa el título que extraiga el análisis.",
        "en": "Leave the role empty to use the title the analysis extracts.",
    },
    "analyze.submit": {"es": "Analizar", "en": "Analyse"},
    "analyze.need_text": {"es": "Pega el texto de la oferta.", "en": "Paste the posting text."},
    "analyze.no_model": {
        "es": "No hay modelo configurado (OPENROUTER_MODEL). El análisis no puede "
        "ejecutarse todavía.",
        "en": "No model is configured (OPENROUTER_MODEL). The analysis cannot run yet.",
    },
    "analyze.failed": {
        "es": "El análisis no se pudo completar; no se ha guardado ningún informe.",
        "en": "The analysis could not be completed; no report was saved.",
    },
    "analyze.need_bullets": {
        "es": "No hay viñetas activas: sin ellas no hay evidencia que citar y la "
        "cobertura será cero.",
        "en": "No active bullets: without them there is no evidence to cite and "
        "coverage will be zero.",
    },
    "analyze.track": {"es": "Puesto objetivo (opcional)", "en": "Track (optional)"},
    "analyze.track_none": {
        "es": "Sin puesto objetivo: todas las viñetas activas",
        "en": "No track: every active bullet",
    },
    "analyze.track_hint": {
        "es": "Con un puesto objetivo, la puntuación usa solo sus viñetas y, si lo "
        "tiene, su titular.",
        "en": "With a track, the score uses only its bullets and, when set, its headline.",
    },
    # Report
    "report.title": {"es": "Informe", "en": "Report"},
    "report.analysed_on": {"es": "Analizado el", "en": "Analysed on"},
    "report.total": {"es": "Encaje total", "en": "Overall fit"},
    "report.capped": {
        "es": "Limitado a {cap} por la comprobación de formato ({check}); sin límite "
        "sería {uncapped}.",
        "en": "Capped at {cap} by the format check ({check}); uncapped it would be "
        "{uncapped}.",
    },
    "report.renormalised": {
        "es": "Falta {missing}: el total se renormaliza sobre {available} de {total} "
        "componentes.",
        "en": "Missing {missing}: the total is renormalised over {available} of {total} "
        "components.",
    },
    "report.cost_label": {"es": "Coste del análisis", "en": "Analysis cost"},
    "report.readability_capped": {
        "es": "El documento limita la puntuación: {check}.",
        "en": "The document caps the score: {check}.",
    },
    "report.track": {"es": "Puesto objetivo: {name}", "en": "Track: {name}"},
    "report.no_track": {
        "es": "Sin puesto objetivo: se puntuaron todas las viñetas activas.",
        "en": "No track: every active bullet was scored.",
    },
    "report.sub_scores": {"es": "Componentes", "en": "Components"},
    "report.sub.title": {"es": "Alineación del título", "en": "Title alignment"},
    "report.sub.skills": {"es": "Habilidades", "en": "Skills"},
    "report.sub.keywords": {"es": "Palabras clave", "en": "Keywords"},
    "report.sub.experience": {"es": "Experiencia", "en": "Experience"},
    # `w1` reports keep their own component names: a stored report renders from its own
    # keys, and `evidence`/`keyword`/`semantic` are what its JSON says.
    "report.sub.evidence": {"es": "Cobertura de evidencia", "en": "Evidence coverage"},
    "report.sub.keyword": {"es": "Contexto de palabras clave", "en": "Keyword context"},
    "report.sub.semantic": {"es": "Encaje semántico", "en": "Semantic fit"},
    "report.weight": {"es": "peso", "en": "weight"},
    "report.disqualifiers": {"es": "Requisitos eliminatorios", "en": "Disqualifiers"},
    "report.disqualifiers_hint": {
        "es": "No entran en la puntuación: un requisito eliminatorio no es un porcentaje.",
        "en": "They do not enter the score: a disqualifier is not a percentage.",
    },
    "report.grades": {"es": "Requisitos evaluados", "en": "Graded requirements"},
    "report.grades_hint": {
        "es": "0 ausente · 1 mencionado · 2 aplicado · 3 demostrado. Cada nivel cita la "
        "viñeta que lo sostiene.",
        "en": "0 absent · 1 mentioned · 2 applied · 3 demonstrated. Every level cites "
        "the bullet that supports it.",
    },
    "report.must_have": {"es": "Imprescindible", "en": "Must-have"},
    "report.nice_to_have": {"es": "Deseable", "en": "Nice-to-have"},
    "report.level_label": {"es": "Nivel", "en": "Level"},
    "report.level.0": {"es": "Ausente", "en": "Absent"},
    "report.level.1": {"es": "Mencionado", "en": "Mentioned"},
    "report.level.2": {"es": "Aplicado", "en": "Applied"},
    "report.level.3": {"es": "Demostrado", "en": "Demonstrated"},
    "report.no_citation": {
        "es": "Sin cita: nada en tu perfil lo respalda.",
        "en": "No citation: nothing in your profile supports it.",
    },
    "report.no_grades": {
        "es": "La oferta no produjo requisitos que evaluar.",
        "en": "The posting produced no requirements to grade.",
    },
    "report.jd_fields": {"es": "Campos extraídos", "en": "Extracted fields"},
    "report.language": {"es": "Idioma", "en": "Language"},
    "report.seniority": {"es": "Seniority", "en": "Seniority"},
    "report.years": {"es": "Años pedidos", "en": "Years asked"},
    "report.keywords": {"es": "Palabras clave", "en": "Keywords"},
    "report.audit": {"es": "Trazabilidad", "en": "Traceability"},
    "report.tokens": {
        "es": "{prompt} + {completion} tokens",
        "en": "{prompt} + {completion} tokens",
    },
    "report.from_cache": {"es": "desde caché", "en": "from cache"},
    "report.fresh_call": {"es": "llamada nueva", "en": "fresh call"},
    "report.weights_version": {"es": "Pesos", "en": "Weights"},
    "report.prompt_versions": {"es": "Versiones de prompt", "en": "Prompt versions"},
    "report.jd_hash": {"es": "Hash de la oferta", "en": "Posting hash"},
    "report.again": {"es": "Analizar otra oferta", "en": "Analyse another posting"},
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
    # Tracks (N2)
    "tracks.title": {"es": "Puestos objetivo", "en": "Tracks"},
    "tracks.new": {"es": "Nuevo puesto objetivo", "en": "New track"},
    "tracks.intro": {
        "es": "Un puesto objetivo es un rol al que apuntas, con una selección "
        "ordenada de tus viñetas. No copia contenido: la misma viñeta sirve a varios.",
        "en": "A track is a target role with an ordered selection of your bullets. It copies "
        "no content: the same bullet serves several tracks.",
    },
    "tracks.name": {"es": "Nombre", "en": "Name"},
    "tracks.applies_when": {"es": "Cuándo usarlo", "en": "When to use it"},
    "tracks.applies_hint": {
        "es": "Lo lee el recomendador para elegir el puesto objetivo ante una oferta.",
        "en": "The recommender reads this to pick a track for a posting.",
    },
    "tracks.lang": {"es": "Idioma", "en": "Language"},
    "tracks.seniority": {"es": "Seniority objetivo", "en": "Target seniority"},
    "tracks.seniority_hint": {"es": "Opcional.", "en": "Optional."},
    "tracks.headline": {"es": "Titular", "en": "Headline"},
    "tracks.headline_hint": {
        "es": "Si lo rellenas, sustituye al titular del perfil al puntuar el encaje de "
        "puesto.",
        "en": "When set, it replaces the profile headline when scoring title alignment.",
    },
    "tracks.summary": {"es": "Resumen", "en": "Summary"},
    "tracks.bullets": {"es": "viñetas", "en": "bullets"},
    "tracks.empty": {
        "es": "Todavía no hay puestos objetivo. Crea el primero.",
        "en": "No tracks yet. Create the first one.",
    },
    "tracks.selection": {"es": "Viñetas seleccionadas", "en": "Selected bullets"},
    "tracks.selection_hint": {
        "es": "En este orden. El análisis puntúa solo estas viñetas.",
        "en": "In this order. An analysis scores only these bullets.",
    },
    "tracks.no_bullets": {"es": "Sin viñetas seleccionadas.", "en": "No bullets selected yet."},
    "tracks.pick": {"es": "Elegir viñetas", "en": "Pick bullets"},
    "tracks.pick_title": {"es": "Viñetas de {name}", "en": "Bullets for {name}"},
    "tracks.pick_hint": {
        "es": "Marca las viñetas y ordénalas con el número. Las que no lleven número van al "
        "final, en el orden en que aparecen.",
        "en": "Tick the bullets and order them with the number. Unnumbered ones go last, in "
        "the order they appear.",
    },
    "tracks.order": {"es": "Orden", "en": "Order"},
    "tracks.no_master_bullets": {
        "es": "No hay viñetas activas en la base maestra.",
        "en": "No active bullets in the master database.",
    },
    "tracks.clone": {"es": "Clonar", "en": "Clone"},
    "tracks.clone_hint": {
        "es": "Copia los campos y la selección, con su orden.",
        "en": "Copies the fields and the selection, order included.",
    },
    "tracks.deactivate_hint": {
        "es": "Desactivar conserva el puesto objetivo para los informes ya generados.",
        "en": "Deactivating keeps the track for reports already generated.",
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
    "vocabulary.kind": {"es": "Tipo", "en": "Kind"},
    "kind.technical": {"es": "Técnica", "en": "Technical"},
    "kind.tool": {"es": "Herramienta", "en": "Tool"},
    "kind.domain": {"es": "Dominio", "en": "Domain"},
    "kind.soft": {"es": "Blanda", "en": "Soft"},
    "kind.experience": {"es": "Experiencia", "en": "Experience"},
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
    # Import (N1) — gate findings, review, diff, merge
    "import.title": {"es": "Importar un currículum", "en": "Import a résumé"},
    "import.intro": {
        "es": "Sube un PDF o un Word. Primero verás lo que un ATS puede leer del "
        "documento, después el borrador extraído, que puedes corregir antes de que "
        "se guarde nada.",
        "en": "Upload a PDF or Word file. You first see what an ATS can read from the "
        "document, then the extracted draft, which you can correct before anything "
        "is stored.",
    },
    "import.file": {"es": "Archivo", "en": "File"},
    "import.file_hint": {
        "es": "PDF o DOCX, en español o inglés, hasta 10 MB.",
        "en": "PDF or DOCX, Spanish or English, up to 10 MB.",
    },
    "import.track": {"es": "Puesto objetivo (opcional)", "en": "Target track (optional)"},
    "import.track_hint": {
        "es": "La trayectoria con la que piensas usar este currículum. Puedes "
        "dejarlo vacío y asignarlo después.",
        "en": "The track you intend this résumé for. Leave it empty and assign it later.",
    },
    "import.submit": {"es": "Importar", "en": "Import"},
    "import.no_file": {"es": "Elige un archivo.", "en": "Choose a file."},
    "import.too_large": {
        "es": "El archivo supera los 10 MB.",
        "en": "The file is larger than 10 MB.",
    },
    "import.unsupported": {
        "es": "Solo se aceptan PDF o DOCX.",
        "en": "Only PDF or DOCX are accepted.",
    },
    "import.unreadable": {
        "es": "El archivo no se pudo leer: puede estar dañado o no ser realmente ese "
        "formato.",
        "en": "The file could not be read: it may be damaged or not really that format.",
    },
    "import.no_text": {
        "es": "El documento no tiene texto que un ATS pueda leer. No hay nada que "
        "extraer y no se ha guardado nada.",
        "en": "The document has no text an ATS can read. There is nothing to extract "
        "and nothing was stored.",
    },
    "import.no_model": {
        "es": "No hay modelo configurado (OPENROUTER_MODEL): los hallazgos de formato "
        "se muestran igual, pero la extracción no puede ejecutarse.",
        "en": "No model is configured (OPENROUTER_MODEL): the format findings are "
        "still shown, but the extraction cannot run.",
    },
    "import.failed": {
        "es": "La extracción no se pudo completar; el documento queda guardado para "
        "reintentarla.",
        "en": "The extraction could not be completed; the document is kept so you can "
        "retry it.",
    },
    "import.empty_extraction": {
        "es": "Entraron {characters} caracteres y no volvió nada: el documento se leyó, "
        "pero no se pudo interpretar. Reintenta la extracción sobre el archivo "
        "guardado.",
        "en": "{characters} characters went in and nothing came back: the document was "
        "read but could not be parsed. Retry the extraction on the stored file.",
    },
    "import.extraction_failed": {
        "es": "La extracción de este documento falló y no hay borrador. El archivo y "
        "sus hallazgos están guardados; puedes reintentar la extracción sin volver a "
        "subirlo.",
        "en": "This document's extraction failed and it has no draft. The file and its "
        "findings are stored; you can retry the extraction without uploading it again.",
    },
    "import.retry": {"es": "Reintentar la extracción", "en": "Retry the extraction"},
    "import.uploads": {"es": "Importaciones", "en": "Uploads"},
    "import.none_yet": {
        "es": "Todavía no has subido ningún currículum.",
        "en": "No résumé has been uploaded yet.",
    },
    "import.uploaded_at": {"es": "Subido el", "en": "Uploaded"},
    "import.view": {"es": "Ver", "en": "View"},
    "import.review_link": {"es": "Revisar", "en": "Review"},
    "import.discard": {"es": "Descartar", "en": "Discard"},
    "import.status.pending": {"es": "En revisión", "en": "In review"},
    "import.status.merged": {"es": "Importado", "en": "Merged"},
    "import.status.discarded": {"es": "Descartado", "en": "Discarded"},
    "import.findings": {"es": "Lectura del documento", "en": "Document readability"},
    "import.findings_hint": {
        "es": "Lo que un ATS encuentra antes de que nadie lea el contenido.",
        "en": "What an ATS finds before anyone reads the content.",
    },
    "import.no_findings": {
        "es": "Sin hallazgos: el documento se lee correctamente.",
        "en": "No findings: the document reads correctly.",
    },
    "import.gate_hint": {
        "es": "Un bloqueante limita la puntuación a 40; un aviso, a 85.",
        "en": "A blocker caps the score at 40; a warning caps it at 85.",
    },
    "import.no_findings_docx": {
        "es": "Sin hallazgos en las comprobaciones que un DOCX puede responder; abajo "
        "se listan las que no se ejecutaron.",
        "en": "No findings in the checks a DOCX can answer; the ones that did not run "
        "are listed below.",
    },
    "import.not_run_title": {
        "es": "No se ejecutaron para este formato",
        "en": "Not run for this format",
    },
    "import.not_run_hint": {
        "es": "Word no tiene geometría de página: sin estas comprobaciones, «sin "
        "hallazgos» no significa que el documento esté limpio.",
        "en": "A Word file has no page geometry: without these checks, \u201cno "
        "findings\u201d does not mean the document is clean.",
    },
    "import.review_title": {"es": "Revisar la extracción", "en": "Review the extraction"},
    "import.review_hint": {
        "es": "Nada de esto se ha guardado todavía: la base de datos cambia solo "
        "cuando confirmes la comparación. Corrige aquí lo que el extractor leyó mal.",
        "en": "None of this is stored yet: the database changes only when you confirm "
        "the diff. Fix here whatever the extractor read wrong.",
    },
    "import.headline": {"es": "Titular", "en": "Headline"},
    "import.summary": {"es": "Resumen", "en": "Summary"},
    "import.skills": {"es": "Habilidades", "en": "Skills"},
    "import.skills_hint": {
        "es": "Nombres canónicos del vocabulario, separados por comas. Solo son "
        "anotación: la evidencia y la puntuación leen las viñetas.",
        "en": "Canonical vocabulary names, comma-separated. Annotation only: evidence "
        "and scoring read the bullets.",
    },
    "import.roles": {"es": "Puestos", "en": "Roles"},
    "import.bullets_of": {"es": "Viñetas", "en": "Bullets"},
    "import.employer": {"es": "Empleador", "en": "Employer"},
    "import.position": {"es": "Puesto", "en": "Job title"},
    "import.start": {"es": "Desde", "en": "From"},
    "import.end": {"es": "Hasta", "en": "To"},
    "import.educations": {"es": "Formación", "en": "Education"},
    "import.credentials": {
        "es": "Formación y certificaciones",
        "en": "Education and certifications",
    },
    "import.kind": {"es": "Tipo", "en": "Type"},
    "import.kind.education": {"es": "Formación", "en": "Education"},
    "import.kind.certification": {"es": "Certificación", "en": "Certification"},
    "import.name_award": {"es": "Nombre o título", "en": "Name or award"},
    "import.institution_issuer": {"es": "Institución o emisor", "en": "Institution or issuer"},
    "import.only_education": {"es": "solo formación", "en": "education only"},
    "import.only_certification": {"es": "solo certificación", "en": "certification only"},
    "import.certifications": {"es": "Certificaciones", "en": "Certifications"},
    "import.field": {"es": "Área", "en": "Field"},
    "import.issued": {"es": "Emitido", "en": "Issued"},
    "import.expiry": {"es": "Caduca", "en": "Expires"},
    "import.credential_id": {"es": "ID de credencial", "en": "Credential ID"},
    "import.credential_url": {"es": "URL de credencial", "en": "Credential URL"},
    "import.needs_review": {"es": "Por revisar", "en": "Needs review"},
    "import.needs_review_hint": {
        "es": "Ni una regla ni el modelo lo tenían claro: decide tú si es formación "
        "o certificación.",
        "en": "Neither a rule nor the model was sure: you decide whether this is "
        "education or a certification.",
    },
    "import.remove_hint": {
        "es": "Vaciar el nombre de un puesto o de una entrada la descarta.",
        "en": "Clearing a role's name or an entry's name discards it.",
    },
    "import.to_diff": {"es": "Comparar con mis datos", "en": "Compare with my data"},
    "import.merge_title": {"es": "Comparar antes de importar", "en": "Compare before importing"},
    "import.merge_intro": {
        "es": "Cada candidato está etiquetado: nuevo, cambia o sin cambios. Marca lo "
        "que quieres importar; lo que ya existe no se sobrescribe sin que lo pidas.",
        "en": "Every candidate is labelled: new, changed or unchanged. Tick what you "
        "want to import; nothing that already exists is overwritten unless you ask.",
    },
    "import.count_new": {"es": "nuevos", "en": "new"},
    "import.count_changed": {"es": "cambian", "en": "changed"},
    "import.count_unchanged": {"es": "sin cambios", "en": "unchanged"},
    "import.label.new": {"es": "Nuevo", "en": "New"},
    "import.label.changed": {"es": "Cambia", "en": "Changed"},
    "import.label.unchanged": {"es": "Sin cambios", "en": "Unchanged"},
    "import.reactivates": {"es": "reactivar", "en": "reactivate"},
    "import.dates_changed": {"es": "fechas", "en": "dates"},
    "import.old_text": {"es": "Antes", "en": "Before"},
    "import.change.institution": {"es": "institución", "en": "institution"},
    "import.change.award": {"es": "título", "en": "award"},
    "import.change.field": {"es": "área", "en": "field"},
    "import.change.dates": {"es": "fechas", "en": "dates"},
    "import.change.name": {"es": "nombre", "en": "name"},
    "import.change.issuer": {"es": "emisor", "en": "issuer"},
    "import.change.credential": {"es": "credencial", "en": "credential"},
    "import.changes": {"es": "Cambia: {fields}", "en": "Changes: {fields}"},
    "import.role_children_hint": {
        "es": "Las viñetas de un puesto nuevo solo entran si el puesto entra.",
        "en": "A new role's bullets come in only if the role does.",
    },
    "import.merge_candidates": {"es": "Candidatos comparados", "en": "Compared items"},
    "import.nothing_to_merge": {
        "es": "Esta versión coincide con lo que ya tienes: no hay nada que fusionar. Se "
        "compararon {compared} elementos y ninguno es nuevo ni cambia.",
        "en": "This version matches what you already have: there is nothing to merge. "
        "{compared} items were compared and none is new or changed.",
    },
    "import.nothing_compared": {
        "es": "No se extrajo nada que comparar: la extracción no produjo ningún "
        "candidato. Revisa el documento o reintenta la extracción.",
        "en": "Nothing was extracted to compare: the extraction produced no candidate "
        "at all. Check the document, or retry the extraction.",
    },
    "import.merged_nothing": {
        "es": "La fusión no escribió nada: tu base de datos queda como estaba.",
        "en": "The merge wrote nothing: your database is unchanged.",
    },
    "import.track_label": {"es": "Puesto objetivo", "en": "Track"},
    "import.track_create": {
        "es": "Crear un puesto objetivo con estas viñetas",
        "en": "Create a track with these bullets",
    },
    "import.merge_track_hint": {
        "es": "Sin marcar, la importación no crea ningún puesto objetivo. Se guarda con "
        "las viñetas del documento y puedes cambiarle el nombre después.",
        "en": "Left unticked, the import creates no track. It is saved with the "
        "document's bullets and you can rename it later.",
    },
    "import.track_created": {"es": "Puesto objetivo creado: {name}", "en": "Track created: {name}"},
    "import.track_view": {"es": "Ver el puesto objetivo", "en": "View the track"},
    "import.merge_submit": {"es": "Importar la selección", "en": "Import the selection"},
    "import.merged_title": {"es": "Importación aplicada", "en": "Import applied"},
    "import.merged_at": {"es": "Importado el", "en": "Merged on"},
    "import.merged_intro": {
        "es": "Lo revisado ya está en tu base de datos. Los informes guardados siguen "
        "citando el texto que se evaluó.",
        "en": "What you reviewed is now in your database. Stored reports still cite "
        "the text they graded.",
    },
    "import.roles_created": {"es": "Puestos nuevos", "en": "Roles created"},
    "import.roles_updated": {"es": "Puestos actualizados", "en": "Roles updated"},
    "import.bullets_created": {"es": "Viñetas nuevas", "en": "Bullets created"},
    "import.bullets_updated": {"es": "Viñetas actualizadas", "en": "Bullets updated"},
    "import.educations_created": {"es": "Formación añadida", "en": "Education added"},
    "import.educations_updated": {"es": "Formación actualizada", "en": "Education updated"},
    "import.certifications_created": {
        "es": "Certificaciones añadidas",
        "en": "Certifications added",
    },
    "import.certifications_updated": {
        "es": "Certificaciones actualizadas",
        "en": "Certifications updated",
    },
    "import.skills_added": {"es": "Habilidades añadidas", "en": "Skills added"},
    "import.skipped": {"es": "Omitidos", "en": "Skipped"},
    "import.skipped_hint": {
        "es": "Omitidos: sin el puesto al que pertenecen, o sin el dato obligatorio "
        "(institución o nombre).",
        "en": "Skipped: either their role was not imported, or a required value "
        "(institution or name) is missing.",
    },
    "import.reviewed_content": {"es": "Lo que traía el documento", "en": "What the document held"},
    "import.go_roles": {"es": "Ver mi trayectoria", "en": "See my experience"},
    "import.go_back": {"es": "Volver a importaciones", "en": "Back to uploads"},
    # Gate findings (F5.1) — labels and details. Findings never echo document text.
    "gate.severity.blocker": {"es": "Bloqueante", "en": "Blocker"},
    "gate.severity.warning": {"es": "Aviso", "en": "Warning"},
    "gate.severity.info": {"es": "Info", "en": "Info"},
    "gate.check.no_extractable_text": {"es": "Sin texto extraíble", "en": "No extractable text"},
    "gate.check.contact_in_margin": {
        "es": "Datos de contacto en cabecera o pie",
        "en": "Contact details in header or footer",
    },
    "gate.check.text_in_table": {"es": "Texto dentro de tablas", "en": "Text inside tables"},
    "gate.check.invisible_text": {"es": "Texto invisible", "en": "Invisible text"},
    "gate.check.invisible_glyphs": {"es": "Glifos invisibles", "en": "Invisible glyphs"},
    "gate.check.multi_column": {"es": "Cuerpo a varias columnas", "en": "Multi-column body"},
    "gate.check.unrecognised_headings": {
        "es": "Encabezados de sección no reconocidos",
        "en": "Unrecognised section headings",
    },
    "gate.check.mojibake": {"es": "Caracteres mal codificados", "en": "Mojibake"},
    "gate.check.image_bullets": {"es": "Viñetas como imagen", "en": "Image-based bullets"},
    "gate.check.non_embedded_fonts": {
        "es": "Fuentes no incrustadas",
        "en": "Non-embedded fonts",
    },
    "gate.band.header": {"es": "cabecera", "en": "header"},
    "gate.band.footer": {"es": "pie", "en": "footer"},
    "gate.kind.email": {"es": "correo", "en": "email"},
    "gate.kind.phone": {"es": "teléfono", "en": "phone"},
    "gate.detail.no_extractable_text": {
        "es": "Páginas sin texto: {pages}.",
        "en": "Pages without text: {pages}.",
    },
    "gate.detail.no_extractable_text_docx": {
        "es": "El documento no contiene texto que un ATS pueda leer.",
        "en": "The document contains no text an ATS can read.",
    },
    "gate.detail.contact_in_margin": {
        "es": "Página {page}: datos de contacto en la {band} ({kinds}).",
        "en": "Page {page}: contact details in the {band} ({kinds}).",
    },
    "gate.detail.contact_in_margin_docx": {
        "es": "Datos de contacto en la {band} ({kinds}).",
        "en": "Contact details in the {band} ({kinds}).",
    },
    "gate.detail.text_in_table": {
        "es": "Página {page}: {words} palabras dentro de {tables} tablas.",
        "en": "Page {page}: {words} words inside {tables} tables.",
    },
    "gate.detail.text_in_table_docx": {
        "es": "{cells} celdas con texto en {tables} tablas.",
        "en": "{cells} cells with text across {tables} tables.",
    },
    "gate.detail.invisible_text": {
        "es": "Página {page}: {words} palabras invisibles.",
        "en": "Page {page}: {words} invisible words.",
    },
    "gate.detail.invisible_text_docx": {
        "es": "{runs} fragmentos con texto legible para un ATS: {white_runs} en blanco y "
        "{hidden_runs} ocultos.",
        "en": "{runs} runs carrying text an ATS would index: {white_runs} painted white "
        "and {hidden_runs} hidden.",
    },
    "gate.detail.invisible_glyphs": {
        "es": "Página {page}: {chars} caracteres invisibles {group}, típicos de una "
        "exportación de plantilla — no afectan a cómo un ATS lee este documento.",
        "en": "Page {page}: {chars} invisible characters {group}, typical of a "
        "résumé-builder export — they do not affect how an ATS reads this document.",
    },
    "gate.detail.invisible_glyphs_warning": {
        "es": "Página {page}: {chars} caracteres invisibles {group} — más de lo que "
        "produce una exportación de plantilla; revisa que el documento no oculte nada.",
        "en": "Page {page}: {chars} invisible characters {group} — more than a "
        "résumé-builder export produces; check that the document hides nothing.",
    },
    "gate.detail.invisible_glyphs_docx": {
        "es": "{chars} caracteres invisibles {group} entre el texto en blanco y el "
        "oculto, típicos de una exportación de plantilla — no afectan a cómo un ATS lee "
        "este documento.",
        "en": "{chars} invisible characters {group} across the white and hidden runs, "
        "typical of a builder export — they do not affect how an ATS reads this document.",
    },
    "gate.detail.invisible_glyphs_warning_docx": {
        "es": "{chars} caracteres invisibles {group} entre el texto en blanco y el "
        "oculto — más de lo que produce una exportación de plantilla; revisa que el "
        "documento no oculte nada.",
        "en": "{chars} invisible characters {group} across the white and hidden runs — "
        "more than a builder export produces; check that the document hides nothing.",
    },
    "gate.glyph_group.punctuation": {"es": "de puntuación", "en": "punctuation"},
    "gate.glyph_group.symbol": {"es": "de símbolo", "en": "symbol"},
    "gate.glyph_group.space": {"es": "de espacio", "en": "space"},
    "gate.glyph_group.format": {"es": "de formato", "en": "format"},
    "gate.detail.multi_column": {
        "es": "Página {page}: dos columnas con {gap_pt} pt entre ellas (x {gutter_start}–"
        "{gutter_end}; {height_percent} % de la altura).",
        "en": "Page {page}: two columns with a {gap_pt} pt gutter (x {gutter_start}–"
        "{gutter_end}; {height_percent}% of the page height).",
    },
    "gate.detail.multi_column_docx": {
        "es": "{columns} columnas declaradas en el documento.",
        "en": "{columns} columns declared in the document.",
    },
    "gate.detail.unrecognised_headings": {
        "es": "No se encontró ningún encabezado canónico en español ni en inglés.",
        "en": "No canonical Spanish or English heading was found.",
    },
    "gate.detail.mojibake": {
        "es": "Página {page}: {count} marcas de codificación ({markers}).",
        "en": "Page {page}: {count} encoding marks ({markers}).",
    },
    "gate.detail.mojibake_docx": {
        "es": "{count} marcas de codificación ({markers}).",
        "en": "{count} encoding marks ({markers}).",
    },
    "gate.detail.image_bullets": {
        "es": "Página {page}: {count} viñetas como imagen.",
        "en": "Page {page}: {count} bullets drawn as images.",
    },
    "gate.detail.non_embedded_fonts": {
        "es": "Fuentes sin incrustar: {fonts}.",
        "en": "Fonts without embedding: {fonts}.",
    },
}


def t(key: str, lang: str | None = None, **values: object) -> str:
    entry = STRINGS.get(key)
    if entry is None:
        return key
    text = entry.get(lang or DEFAULT_LANG) or entry.get(DEFAULT_LANG) or key
    return text.format(**values) if values else text
