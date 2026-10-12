"""Spanish and English interface strings.

`en` may lag `es`: a missing translation falls back to the default language and
then to the key itself, so a half-translated screen renders in Spanish rather
than showing an empty cell.
"""

from collections.abc import Sequence

DEFAULT_LANG = "es"
LANGUAGES = ("es", "en")

STRINGS: dict[str, dict[str, str]] = {
    "app.name": {"es": "ATSker", "en": "ATSker"},
    "app.tagline": {
        "es": "Evaluación de ajuste entre tu currículum y una oferta",
        "en": "How well your résumé matches a job posting",
    },
    # §12.8 landing (lane C)
    # The logged-out page at `/`: its copy is the approved mockup's
    # (`private_docs/design/v3/Landing.dc.html`), which follows §12.8 and the README. The
    # preview card is static sample data — no product image exists until N8.18 — so its
    # figures and terms are literals here, not a second report.
    "landing.announce": {
        "es": "La demo pública, gratis y sin registro, está en camino.",
        "en": "The public demo, free and without sign-up, is on its way.",
    },
    "landing.announce.link": {"es": "Ver el proyecto", "en": "See the project"},
    "landing.nav.label": {"es": "Secciones", "en": "Sections"},
    "landing.nav.gaps": {"es": "Brechas", "en": "Gaps"},
    "landing.nav.how": {"es": "Cómo funciona", "en": "How it works"},
    "landing.nav.privacy": {"es": "Privacidad", "en": "Privacy"},
    "landing.login": {"es": "Iniciar sesión", "en": "Log in"},
    "landing.demo": {"es": "Probar la demo", "en": "Try the demo"},
    "landing.hero.eyebrow": {
        "es": "Con IA · En español y en inglés",
        "en": "AI-powered · Spanish and English",
    },
    "landing.hero.headline": {
        "es": "Tú controlas tu CV. ATSker te ayuda a afinarlo para cada oferta.",
        "en": "You control your CV. ATSker helps you tune it for every job.",
    },
    "landing.hero.subline": {
        "es": (
            "Tu puntaje, sin caja negra. Tus brechas, a la vista. "
            "Consejos que puedes aplicar hoy."
        ),
        "en": "Your score, no black box. Your gaps, in plain sight. Advice you can apply today.",
    },
    "landing.github": {"es": "Ver en GitHub", "en": "See it on GitHub"},
    "landing.preview.role": {"es": "Analista de datos", "en": "Data analyst"},
    # The `{term}` placeholder is the highlighted word in each bullet; the template wraps
    # it in the §12.7 mark, so the sentence stays whole in one string.
    "landing.preview.bullet.one": {
        "es": (
            "Automaticé el reporte semanal de cobranzas con Python y {term}, "
            "reduciendo 30% el tiempo de cierre."
        ),
        "en": (
            "I automated the weekly collections report with Python and {term}, "
            "cutting close time by 30%."
        ),
    },
    "landing.preview.bullet.two": {
        "es": "{term} para el data mart de riesgo.",
        "en": "{term} for the risk data mart.",
    },
    "landing.preview.bullet.two.term": {
        "es": "Modelé un esquema dimensional",
        "en": "I modelled a dimensional schema",
    },
    "landing.preview.bullet.three": {
        "es": "Diseñé tableros en {term} para el equipo comercial.",
        "en": "I designed {term} dashboards for the sales team.",
    },
    "landing.preview.caption": {"es": "Ajuste general · ejemplo", "en": "Overall fit · example"},
    "landing.preview.sub.skills": {"es": "Habilidades", "en": "Skills"},
    "landing.preview.sub.experience": {"es": "Experiencia", "en": "Experience"},
    "landing.preview.sub.title": {"es": "Título", "en": "Title"},
    "landing.preview.sub.keywords": {"es": "Palabras", "en": "Keywords"},
    "landing.preview.sample": {"es": "Datos de ejemplo", "en": "Sample data"},
    "landing.gaps.divider": {"es": "El análisis de brechas", "en": "The gap analysis"},
    "landing.gaps.title": {
        "es": "Antes de postular, conoce tus brechas",
        "en": "Before you apply, know your gaps",
    },
    "landing.gaps.discard.title": {"es": "Lo que te descarta", "en": "What rules you out"},
    "landing.gaps.discard.body": {
        "es": "Los requisitos imprescindibles que tu CV no muestra, primero.",
        "en": "The must-have requirements your CV does not show, first.",
    },
    "landing.gaps.transfer.title": {"es": "Lo cubierto por transferencia", "en": "What transfers"},
    "landing.gaps.transfer.body": {
        "es": (
            "Lo que acreditas con una herramienta equivalente, y el argumento "
            "que conviene preparar."
        ),
        "en": "What you can prove with an equivalent tool, and the argument worth preparing.",
    },
    "landing.gaps.close.title": {
        "es": "Lo que puedes cerrar hoy",
        "en": "What you can close today",
    },
    "landing.gaps.close.body": {
        "es": (
            "Lo que tu material ya cubre y tu CV no dice, separado de lo que "
            "solo la experiencia cerrará."
        ),
        "en": (
            "What your material already covers and your CV does not say, apart "
            "from what only experience will close."
        ),
    },
    "landing.questions.ats.title": {
        "es": "¿El ATS puede leer tu CV?",
        "en": "Can the ATS read your CV?",
    },
    "landing.questions.ats.body": {
        "es": (
            "Texto oculto, contacto en el encabezado, tablas y columnas, cada "
            "uno con «muéstrame dónde»."
        ),
        "en": (
            "Hidden text, contact details in the header, tables and columns, "
            "each with “show me where”."
        ),
    },
    "landing.questions.recruiter.title": {
        "es": "¿Te encuentra el reclutador?",
        "en": "Will the recruiter find you?",
    },
    "landing.questions.recruiter.body": {
        "es": (
            "Las búsquedas que correría un reclutador, listas para copiar, con "
            "«apareces» o «no apareces»."
        ),
        "en": (
            "The searches a recruiter would run, ready to copy, with “you appear” "
            "or “you do not”."
        ),
    },
    "landing.what.divider": {"es": "Qué hace", "en": "What it does"},
    "landing.what.import.title": {"es": "Importa una vez", "en": "Import once"},
    "landing.what.import.body": {
        "es": "Revisas lo extraído antes de guardar nada.",
        "en": "You review what was extracted before anything is saved.",
    },
    "landing.what.tracks.title": {"es": "Líneas de carrera", "en": "Career tracks"},
    "landing.what.tracks.body": {
        "es": "La misma experiencia, para cada tipo de puesto.",
        "en": "The same experience, for each kind of role.",
    },
    "landing.what.report.title": {"es": "El informe", "en": "The report"},
    "landing.what.report.body": {
        "es": "De 0 a 100, en cuatro partes que un reclutador reconoce.",
        "en": "From 0 to 100, in four parts a recruiter recognises.",
    },
    "landing.what.ceiling.title": {
        "es": "Prueba el archivo que vas a enviar",
        "en": "Test the file you will send",
    },
    "landing.what.ceiling.body": {
        "es": "Compáralo con el techo de tu material.",
        "en": "Compare it with the ceiling of your material.",
    },
    "landing.what.writing.title": {
        "es": "Ayuda para escribir que no inventa",
        "en": "Writing help that does not invent",
    },
    "landing.what.writing.body": {
        "es": "Resumen y carta que citan lo que escribiste.",
        "en": "A summary and a letter that cite what you wrote.",
    },
    "landing.honest.eyebrow": {
        "es": "Con IA, honesto por diseño",
        "en": "AI-powered, honest by design",
    },
    "landing.honest.title": {
        "es": (
            "La IA lee tus documentos y evalúa tu evidencia; el código calcula "
            "el puntaje y revisa cada frase."
        ),
        "en": (
            "The AI reads your documents and assesses your evidence; the code "
            "computes the score and checks every sentence."
        ),
    },
    "landing.honest.provenance.title": {"es": "Procedencia", "en": "Provenance"},
    "landing.honest.provenance.body": {
        "es": "Cada frase cita un bullet, una historia o un resumen tuyo.",
        "en": "Every sentence cites a bullet, a story or a summary of yours.",
    },
    "landing.honest.literal.title": {"es": "Preservación literal", "en": "Literal preservation"},
    "landing.honest.literal.body": {
        "es": "Cada número, fecha y nombre propio está en esa fuente.",
        "en": "Every number, date and proper noun is in that source.",
    },
    "landing.honest.closure.title": {"es": "Cierre de habilidades", "en": "Skill closure"},
    "landing.honest.closure.body": {
        "es": "Solo nombra habilidades que tienes.",
        "en": "It only names skills you have.",
    },
    "landing.how.title": {"es": "Cómo funciona", "en": "How it works"},
    "landing.how.cv.title": {"es": "Tu CV", "en": "Your CV"},
    "landing.how.cv.body": {
        "es": "Lo subes una vez, en español o en inglés.",
        "en": "You upload it once, in Spanish or in English.",
    },
    "landing.how.posting.title": {"es": "La oferta", "en": "The posting"},
    "landing.how.posting.body": {
        "es": "Pegas el texto de cualquier aviso.",
        "en": "You paste the text of any posting.",
    },
    "landing.how.report.title": {"es": "El informe", "en": "The report"},
    "landing.how.report.body": {
        "es": "Puntaje, brechas y qué cambiar, en una página.",
        "en": "Score, gaps and what to change, on one page.",
    },
    "landing.privacy.title": {
        "es": "Privacidad, en palabras simples",
        "en": "Privacy, in plain words",
    },
    "landing.privacy.body": {
        "es": (
            "Tus datos se guardan en infraestructura gestionada en EE. UU. y pasan por un "
            "proveedor de modelos. Antes de enviar texto al modelo se quitan nombres, correos "
            "y teléfonos. Los registros guardan solo hashes e identificadores. Eliminar es "
            "eliminar."
        ),
        "en": (
            "Your data is stored on managed infrastructure in the United States and goes "
            "through a model provider. Names, e-mails and phone numbers are removed before "
            "text is sent to the model. Logs keep only hashes and identifiers. Deleting means "
            "deleting."
        ),
    },
    "landing.footer.note": {
        "es": "atsker · proyecto de portafolio de Rodrigo García Sánchez",
        "en": "atsker · a portfolio project by Rodrigo García Sánchez",
    },
    "landing.footer.github": {"es": "GitHub", "en": "GitHub"},
    # Shell — the 64px icon rail of §12.1: three groups, nine links, and the account
    # controls. Vocabulario is not a rail destination; Perfil links to it.
    "nav.dashboard": {"es": "Inicio", "en": "Home"},
    "nav.analyze": {"es": "Analizar", "en": "Analyse"},
    "nav.applications": {"es": "Historial", "en": "History"},
    "nav.import": {"es": "Importar CV", "en": "Import CV"},
    "nav.tracks": {"es": "Líneas de carrera", "en": "Tracks"},
    "nav.profile": {"es": "Perfil", "en": "Profile"},
    "nav.roles": {"es": "Experiencia", "en": "Experience"},
    "nav.stories": {"es": "Historias", "en": "Stories"},
    "nav.letters": {"es": "Cartas", "en": "Letters"},
    "nav.vocabulary": {"es": "Vocabulario", "en": "Vocabulary"},
    "nav.logout": {"es": "Salir", "en": "Log out"},
    "nav.language": {"es": "Idioma", "en": "Language"},
    "nav.group.apply": {"es": "Postular", "en": "Apply"},
    "nav.group.material": {"es": "Tu material", "en": "Your material"},
    "nav.group.account": {"es": "Cuenta", "en": "Account"},
    "nav.menu": {"es": "Menú", "en": "Menu"},
    "nav.main": {"es": "Principal", "en": "Main"},
    "nav.account": {"es": "Tu cuenta", "en": "Your account"},
    # Shared
    # §12.5: the shared proposal dialog.
    "dialog.close": {"es": "Cerrar", "en": "Close"},
    "dialog.loading": {"es": "Cargando…", "en": "Loading…"},
    "dialog.error": {
        "es": "No se pudo cargar ({detail}). Cierra e inténtalo de nuevo.",
        "en": "It could not be loaded ({detail}). Close it and try again.",
    },
    "dialog.confirm_close": {
        "es": "Hay una propuesta sin aceptar. ¿Cerrar de todos modos?",
        "en": "A proposal has not been accepted. Close anyway?",
    },
    "common.save":{"es": "Guardar", "en": "Save"},
    "common.create": {"es": "Crear", "en": "Create"},
    "common.cancel": {"es": "Cancelar", "en": "Cancel"},
    "common.edit": {"es": "Editar", "en": "Edit"},
    "common.delete": {"es": "Eliminar", "en": "Delete"},
    # F2.8: soft delete is renamed for what it does — the hide control reads Ocultar.
    "common.hide": {"es": "Ocultar", "en": "Hide"},
    "common.reactivate": {"es": "Reactivar", "en": "Reactivate"},
    "common.active": {"es": "activo", "en": "active"},
    "common.inactive": {"es": "inactivo", "en": "inactive"},
    "common.optional": {"es": "opcional", "en": "optional"},
    # The conjunction `join_list` puts before a list's last item: "a, b y c" in
    # Spanish, "a, b and c" in English. It is a word of the language, so it lives
    # with the strings rather than in the caller.
    "common.and": {"es": "y", "en": "and"},
    "common.none": {"es": "—", "en": "—"},
    # §12.1's score bands, presentation words for the three-stop scale. They name a
    # colour, never a scoring rule; the thresholds (75/50) live in `_ui.html`.
    "ui.band.strong": {"es": "Fuerte", "en": "Strong"},
    "ui.band.adequate": {"es": "Adecuado", "en": "Adequate"},
    "ui.band.weak": {"es": "Débil", "en": "Weak"},
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
    "dashboard.bullets": {"es": "Bullets activos", "en": "Active bullets"},
    "dashboard.stories": {"es": "Historias", "en": "Stories"},
    "dashboard.letters": {"es": "Plantillas de carta", "en": "Letter templates"},
    "dashboard.educations": {"es": "Formación", "en": "Education"},
    "dashboard.metrics": {"es": "Métricas detectadas", "en": "Detected metrics"},
    # F.1: the outcome habit. The window (14 days) is a presentation constant.
    "dashboard.stale": {
        "es": "{count} análisis de hace más de 14 días sin resultado",
        "en": "{count} analyses older than 14 days with no outcome",
    },
    "dashboard.next": {
        "es": "Sube tu currículum en PDF o Word: se extrae y lo revisas antes de "
        "guardar nada.",
        "en": "Upload your résumé as PDF or Word: it is extracted and you review it "
        "before anything is saved.",
    },
    "dashboard.empty": {
        "es": "Empieza por tu experiencia, o importa un currículum y revísalo.",
        "en": "Start with your experience, or import a résumé and review it.",
    },
    # Analysis (M5b) — the form, and the report the analysis leaves behind
    "analyze.title": {"es": "Analizar una oferta", "en": "Analyse a posting"},
    "analyze.intro": {
        "es": "Elige una línea de carrera y uno de sus CV, y pega la oferta. Se puntúa ese "
        "archivo: se extraen los requisitos, se contrastan con sus bullets y el informe "
        "queda guardado.",
        "en": "Choose a track and one of its CVs, and paste the posting. That file is "
        "scored: the requirements are extracted, graded against its bullets, and the "
        "report is kept.",
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
        "es": "No hay bullets activos: sin ellos no hay evidencia que citar y la "
        "cobertura será cero.",
        "en": "No active bullets: without them there is no evidence to cite and "
        "coverage will be zero.",
    },
    "applications.cv": {"es": "CV", "en": "CV"},
    "applications.cv_deleted": {"es": "eliminado", "en": "deleted"},
    "analyze.track": {"es": "Línea de carrera", "en": "Track"},
    "analyze.track_pick": {"es": "Elige una línea de carrera", "en": "Choose a track"},
    "analyze.track_hint": {
        "es": "La línea decide qué CV puedes elegir y de qué material sacan consejos las "
        "recomendaciones.",
        "en": "The track decides which CVs you can choose and which material the "
        "recommendations draw on.",
    },
    "analyze.need_track": {
        "es": "Elige una línea de carrera y uno de sus CV.",
        "en": "Choose a track and one of its CVs.",
    },
    "analyze.load_cvs": {"es": "Ver los CV de esta línea", "en": "Show this track's CVs"},
    # F11.3: the CV picker, its first option and the track with no CV.
    "analyze.cv": {"es": "CV", "en": "CV"},
    "analyze.cv_pick_track": {
        "es": "Elige una línea de carrera para ver sus CV.",
        "en": "Choose a track to see its CVs.",
    },
    "analyze.no_cv": {
        "es": "Esta línea de carrera no tiene ningún CV. Importa uno para poder analizar.",
        "en": "This track has no CV. Import one to be able to analyse.",
    },
    "analyze.no_cv_link": {
        "es": "Importar CV con esta línea",
        "en": "Import a CV into this track",
    },
    "analyze.cv_latest": {
        "es": "Último CV de la línea ({name})",
        "en": "Latest CV of the track ({name})",
    },
    "analyze.cv_option": {"es": "{name} — {date}", "en": "{name} — {date}"},
    "analyze.cv_hint": {
        "es": "Se puntúa este archivo, no toda la línea. «Último CV de la línea» se "
        "resuelve al analizar.",
        "en": "This file is scored, not the whole track. “Latest CV of the track” is "
        "resolved when you analyse.",
    },
    # F11.6: "Proponer línea", a cheap ranking before the analysis.
    "analyze.propose": {"es": "Proponer línea", "en": "Suggest a track"},
    "analyze.propose_prompt": {
        "es": "¿No sabes qué línea usar?",
        "en": "Not sure which track to use?",
    },
    "analyze.propose_hint": {
        "es": "Ordena tus líneas por el título y las palabras clave de su último CV. "
        "Extrae la oferta (una llamada que el análisis reutiliza); no puntúa evidencia.",
        "en": "Ranks your tracks by the title and keywords of their latest CV. It "
        "extracts the posting (one call the analysis reuses); it does not grade evidence.",
    },
    "analyze.propose_result": {
        "es": "Tus líneas, según su último CV",
        "en": "Your tracks, by their latest CV",
    },
    "analyze.propose_first": {"es": "Propuesta", "en": "Suggested"},
    "analyze.propose_title": {"es": "Título", "en": "Title"},
    "analyze.propose_keywords": {"es": "Palabras clave", "en": "Keywords"},
    "analyze.propose_estimate": {
        "es": "estimación sin evaluar tu evidencia",
        "en": "estimate without grading your evidence",
    },
    "analyze.propose_none": {
        "es": "Ninguna de tus líneas tiene un CV todavía.",
        "en": "None of your tracks has a CV yet.",
    },
    # Application history (F9)
    "applications.title": {"es": "Historial", "en": "History"},
    "applications.new": {"es": "Analizar una oferta", "en": "Analyse a posting"},
    "applications.intro": {
        "es": "Cada análisis queda guardado con su puntuación, su línea de carrera y su coste. "
        "Esta tabla es el conjunto de datos: con suficientes candidaturas dirá si las componentes "
        "predicen una respuesta.",
        "en": "Every analysis is kept with its score, its track and its cost. This table "
        "is the dataset: with enough applications it says whether the sub-scores "
        "predict a callback.",
    },
    "applications.weights_hint": {
        "es": "Dos puntuaciones con pesos distintos no son comparables: la versión va al "
        "lado del número.",
        "en": "Two scores under different weights are not comparable: the version sits "
        "beside the number.",
    },
    "applications.date": {"es": "Fecha", "en": "Date"},
    "applications.company": {"es": "Empresa", "en": "Company"},
    "applications.position": {"es": "Puesto", "en": "Role"},
    "applications.track": {"es": "Línea de carrera", "en": "Track"},
    "applications.score": {"es": "Ajuste", "en": "Fit"},
    "applications.outcome": {"es": "Resultado", "en": "Outcome"},
    "applications.outcome.no_reply": {"es": "Sin respuesta", "en": "No reply"},
    "applications.outcome.screen": {"es": "Criba", "en": "Screen"},
    "applications.outcome.interview": {"es": "Entrevista", "en": "Interview"},
    "applications.outcome.offer": {"es": "Oferta", "en": "Offer"},
    "applications.outcome.rejected": {"es": "Rechazado", "en": "Rejected"},
    # F9's remaining columns, beside the score: the four sub-scores, both scans, the
    # prompt versions and the cost. "—" when the analysis predates the field.
    "applications.readability": {"es": "Lectura", "en": "Readability"},
    "applications.boolean": {"es": "Búsqueda", "en": "Search"},
    "applications.prompts": {"es": "Prompts", "en": "Prompts"},
    "applications.prompts_count": {"es": "{count} versiones", "en": "{count} versions"},
    "applications.cost": {"es": "Coste", "en": "Cost"},
    # F.1: the history can be narrowed to the analyses still waiting on a result.
    "applications.filter.none": {"es": "Sin resultado", "en": "No outcome"},
    "applications.filtered": {"es": "Mostrando solo: {label}", "en": "Showing only: {label}"},
    "applications.filter_clear": {"es": "Ver todos", "en": "Show all"},
    "applications.scan.pass": {"es": "Sin hallazgos", "en": "No findings"},
    "applications.scan.capped": {"es": "≤ {cap}", "en": "≤ {cap}"},
    "applications.recall.pass": {"es": "Apareces", "en": "You appear"},
    "applications.recall.fail": {"es": "No apareces", "en": "You do not appear"},
    "applications.empty": {
        "es": "Todavía no hay análisis. Pega una oferta y aparecerá aquí.",
        "en": "No analyses yet. Paste a posting and it will appear here.",
    },
    # Scan B — boolean recall (F5.2)
    "recall.title": {"es": "¿Te encuentra el reclutador?", "en": "Will the recruiter find you?"},
    "recall.appears": {"es": "Apareces", "en": "You appear"},
    "recall.not_appears": {"es": "No apareces", "en": "You do not appear"},
    # The labels the derivation returns, shown in the reader's language (N6.6). A label
    # outside this set is shown as the model wrote it.
    "recall.label.broad": {"es": "amplia", "en": "broad"},
    "recall.label.strict": {"es": "estricta", "en": "strict"},
    "recall.label.core": {"es": "núcleo", "en": "core"},
    "recall.intro": {
        "es": "Las consultas que un reclutador escribiría en un ATS o en un portal, y si tu línea "
        "de carrera aparecería en sus resultados. No entra en el Ajuste general: una consulta es "
        "una puerta, no un porcentaje.",
        "en": "The queries a recruiter would type in an ATS or a job board, and whether "
        "your track would come back in the results. It does not enter the Job Match "
        "number: a query is a gate, not a percentage.",
    },
    "recall.summary": {
        "es": "Pasan {passed} de {total} consultas.",
        "en": "{passed} of {total} queries pass.",
    },
    "recall.pass": {"es": "Pasa", "en": "Pass"},
    "recall.fails": {"es": "Falla", "en": "Fails"},
    "recall.unlabelled": {"es": "Consulta", "en": "Query"},
    "recall.copy": {"es": "Copiar", "en": "Copy"},
    "recall.fail.missing": {
        "es": "Falla en «{term}»: no aparece ningún alias de este término en esta línea de "
        "carrera.",
        "en": "Fails on “{term}” — no alias of this term appears in this track.",
    },
    "recall.fail.present": {
        "es": "Falla en «{term}»: aparece en esta línea de carrera y la consulta lo excluye.",
        "en": "Fails on “{term}” — it appears in this track and the query excludes it.",
    },
    "recall.clause_met": {"es": "{term} — lo cumple {unit}", "en": "{term} — met by {unit}"},
    "recall.clause_missing": {"es": "{term} — no aparece", "en": "{term} — absent"},
    "recall.unit.bullet": {"es": "un bullet", "en": "a bullet"},
    "recall.unit.skill": {"es": "una habilidad", "en": "a skill"},
    "recall.unit.headline": {"es": "el titular", "en": "the headline"},
    "recall.unit.summary": {"es": "el resumen", "en": "the summary"},
    "recall.unit.role": {"es": "un puesto de tu experiencia", "en": "a role title"},
    "recall.unit.education": {"es": "tu formación", "en": "your education"},
    "recall.unit.certification": {"es": "una certificación", "en": "a certification"},
    "recall.empty": {
        "es": "No se derivaron consultas para esta oferta.",
        "en": "No queries were derived for this posting.",
    },
    # Report
    "report.title": {"es": "Informe", "en": "Report"},
    "report.analysed_on": {"es": "Analizado el", "en": "Analysed on"},
    "report.total": {"es": "Ajuste general", "en": "Overall fit"},
    "report.capped": {
        "es": "Limitado a {cap} por la comprobación de formato ({check}); sin límite "
        "sería {uncapped}.",
        "en": "Capped at {cap} by the format check ({check}); uncapped it would be "
        "{uncapped}.",
    },
    "report.cap_not_binding.blocker": {
        "es": "El documento tiene un bloqueante ({check}): hoy no resta puntos porque la "
        "puntuación ya está por debajo del límite, pero lo hará en cuanto la puntuación "
        "suba.",
        "en": "The document has a blocker ({check}): it is not costing points today "
        "because the score is already below the cap, but it will the moment the score "
        "rises.",
    },
    "report.cap_not_binding.warning": {
        "es": "El documento tiene un aviso ({check}): hoy no resta puntos porque la "
        "puntuación ya está por debajo del límite, pero lo hará en cuanto la puntuación "
        "suba.",
        "en": "The document has a warning ({check}): it is not costing points today "
        "because the score is already below the cap, but it will the moment the score "
        "rises.",
    },
    "report.renormalised": {
        "es": "Falta {missing}: el total se renormaliza sobre {available} de {total} "
        "componentes.",
        "en": "Missing {missing}: the total is renormalised over {available} of {total} "
        "components.",
    },
    # F10.2: the ceiling beside Job Match. A1 makes the high end wait for F7.4, so the
    # label is one number and "(estimado)" applies to the whole ceiling.
    "report.ceiling": {
        "es": "Techo con tu material: {value} (estimado)",
        "en": "Ceiling with your material: {value} (estimated)",
    },
    "report.ceiling_recalculated": {
        "es": "recalculado con tu material actual",
        "en": "recalculated with your current material",
    },
    "report.ceiling_no_cap": {
        "es": "(sin el límite de formato)",
        "en": "(without the format cap)",
    },
    "report.ceiling_sub": {"es": "techo {value}", "en": "ceiling {value}"},
    "report.ceiling_estimate": {"es": "estimado", "en": "estimated"},
    # A5: the remainder decomposed by source, so the sentence names what actually
    # holds each point out. Only the non-zero parts are shown.
    "report.ceiling.remaining": {
        "es": "Los {points} puntos restantes:",
        "en": "The remaining {points} points:",
    },
    "report.ceiling.no_evidence": {
        "es": "{points} requieren experiencia que ATSker no tiene registrada ({requirements})",
        "en": "{points} require experience ATSker has no record of ({requirements})",
    },
    "report.ceiling.experience": {
        "es": "{points} dependen de años de experiencia",
        "en": "{points} come from years of experience",
    },
    "report.ceiling.title": {"es": "{points} del título", "en": "{points} from the title"},
    "report.ceiling.keywords": {
        "es": "{points} de palabras clave que no figuran en tu material",
        "en": "{points} from keywords that are not in your material",
    },
    "report.ceiling.stronger_evidence": {
        "es": "{points} de evidencia más fuerte en requisitos que ya cubres",
        "en": "{points} from stronger evidence on requirements you already cover",
    },
    "report.ceiling.and": {"es": " y ", "en": " and "},
    # F10.1: the way into the attempt modal.
    "report.try_new_cv": {
        "es": "Probar nueva versión del CV",
        "en": "Try a new CV version",
    },
    "report.try_new_cv_note": {
        "es": "(.docx)",
        "en": "(.docx)",
    },
    # F10.3 (Run B): attempts — the upload limit, the status the modal polls, and the
    # list. `attempt.limit` is the stated reason the 11th upload is refused (409).
    "attempt.limit": {
        "es": "Este análisis ya tiene {max} intentos, que es el máximo.",
        "en": "This analysis already has {max} attempts, which is the maximum.",
    },
    "attempt.title": {"es": "Intento {n}", "en": "Attempt {n}"},
    "attempt.status.running": {"es": "En curso", "en": "Running"},
    "attempt.status.done": {"es": "Listo", "en": "Done"},
    "attempt.status.failed": {"es": "Fallido", "en": "Failed"},
    "attempt.score": {
        "es": "Ajuste {score} · techo {ceiling}",
        "en": "Fit {score} · ceiling {ceiling}",
    },
    "attempt.view_report": {
        "es": "Ver el informe completo",
        "en": "View the full report",
    },
    # F10.7 (C.3): the actions, the F9 history columns, and the merge hand-off.
    "applications.attempts": {"es": "{count} intentos", "en": "{count} attempts"},
    "applications.sent_attempt": {"es": "enviada: intento {n}", "en": "sent: attempt {n}"},
    "attempt.actions.sent": {"es": "Marcar como enviada", "en": "Mark as sent"},
    "attempt.actions.incorporate": {
        "es": "Incorporar a mi material…",
        "en": "Add to my material…",
    },
    "attempt.actions.discard": {"es": "Descartar", "en": "Discard"},
    "attempt.actions.letter": {
        "es": "Carta de presentación →",
        "en": "Cover letter →",
    },
    "attempt.sent_done": {"es": "Marcada como enviada", "en": "Marked as sent"},
    # F10.7 (V1): "Descartar" closes the modal and the report page says so.
    "attempt.discarded": {
        "es": "Intento {n} descartado; su informe queda en el historial.",
        "en": "Attempt {n} discarded; its report stays in the history.",
    },
    "attempt.discarded_tag": {"es": "descartado", "en": "discarded"},
    "attempt.notice_dismiss": {"es": "Cerrar aviso", "en": "Dismiss"},
    "attempt.incorporate.title": {
        "es": "Incorporar a mi material",
        "en": "Add to my material",
    },
    "attempt.incorporate.intro": {
        "es": "Esto es lo que el documento trae y tu base de datos no tiene. Nada se escribe "
        "hasta que confirmes, y ninguna línea se toca salvo que elijas una.",
        "en": "This is what the document brings that your database does not have. "
        "Nothing is written until you confirm, and no track is touched unless you "
        "choose one.",
    },
    "attempt.incorporate.none": {
        "es": "No hay nada nuevo que incorporar.",
        "en": "There is nothing new to add.",
    },
    "attempt.incorporate.bullets": {"es": "Bullets nuevos", "en": "New bullets"},
    "attempt.incorporate.changed": {"es": "Bullets cambiados", "en": "Changed bullets"},
    "attempt.incorporate.skills": {"es": "Habilidades nuevas", "en": "New skills"},
    "attempt.incorporate.destination": {"es": "Destino", "en": "Destination"},
    "attempt.incorporate.solo": {
        "es": "Solo mi material (ninguna línea)",
        "en": "Only my material (no track)",
    },
    "attempt.incorporate.este": {"es": "Esta línea", "en": "This track"},
    "attempt.incorporate.otro": {"es": "Otra línea", "en": "Another track"},
    "attempt.incorporate.nuevo": {"es": "Nueva línea", "en": "A new track"},
    "attempt.incorporate.new_name": {
        "es": "Nombre de la nueva línea",
        "en": "New track name",
    },
    "attempt.incorporate.confirm": {"es": "Incorporar", "en": "Add"},
    "attempt.incorporate.cancel": {"es": "Cancelar", "en": "Cancel"},
    "attempt.incorporated.title": {
        "es": "Incorporado a tu material",
        "en": "Added to your material",
    },
    "attempt.incorporated.counts": {
        "es": "Se crearon {bullets} bullets y se añadieron {skills} habilidades.",
        "en": "Created {bullets} bullets and added {skills} skills.",
    },
    "attempt.incorporated.nothing": {
        "es": "No había nada nuevo que escribir.",
        "en": "There was nothing new to write.",
    },
    "attempt.list": {"es": "Intentos", "en": "Attempts"},
    "attempt.none": {
        "es": "Todavía no hay intentos.",
        "en": "No attempts yet.",
    },
    # F10.1/F10.4 (Run C): the modal, the result's content order and its wording.
    "attempt.form.submit": {"es": "Probar este archivo", "en": "Test this file"},
    # F10.4: the button at the end of a result that reopens the upload area. At the limit
    # there is no button and `attempt.limit` stands in its place.
    "attempt.new": {
        "es": "Nuevo intento ({n} de {max})",
        "en": "New attempt ({n} of {max})",
    },
    "attempt.form.working": {
        "es": "Analizando tu documento… puede tardar hasta un minuto.",
        "en": "Analysing your document… this can take up to a minute.",
    },
    "attempt.form.confirm_close": {
        "es": "Hay un resultado sin guardar. ¿Cerrar igualmente?",
        "en": "There is an unsaved result. Close anyway?",
    },
    "attempt.form.error": {
        "es": "No se pudo subir el archivo: {detail}",
        "en": "The file could not be uploaded: {detail}",
    },
    "attempt.delta": {
        "es": "{delta} vs. análisis de la línea",
        "en": "{delta} vs. the posting analysis",
    },
    "attempt.delta_flat": {
        "es": "sin cambio significativo",
        "en": "no significant change",
    },
    "attempt.vs_previous": {
        "es": "vs. intento {n}",
        "en": "vs. attempt {n}",
    },
    "attempt.change.title": {"es": "Qué cambió", "en": "What changed"},
    "attempt.change.none_first": {
        "es": "Sin cambios respecto al análisis de la línea",
        "en": "No changes against the posting analysis",
    },
    "attempt.change.none_previous": {
        "es": "Sin cambios respecto al intento anterior",
        "en": "No changes against the previous attempt",
    },
    "attempt.change.score": {
        "es": "{name} {before} → {after}",
        "en": "{name} {before} → {after}",
    },
    "attempt.change.searches_found": {
        "es": "Búsquedas que ahora te devuelven: {items}",
        "en": "Searches that now return you: {items}",
    },
    "attempt.change.searches_lost": {
        "es": "Búsquedas que ya no te devuelven: {items}",
        "en": "Searches that no longer return you: {items}",
    },
    "attempt.change.gaps_closed": {"es": "Huecos cerrados: {items}", "en": "Gaps closed: {items}"},
    "attempt.change.gaps_opened": {"es": "Huecos abiertos: {items}", "en": "Gaps opened: {items}"},
    "attempt.change.findings_fixed": {
        "es": "Hallazgos de formato corregidos: {items}",
        "en": "Format findings fixed: {items}",
    },
    "attempt.change.findings_introduced": {
        "es": "Hallazgos de formato introducidos: {items}",
        "en": "Format findings introduced: {items}",
    },
    "attempt.flags.title": {
        "es": "Nuevo en este documento",
        "en": "New in this document",
    },
    "attempt.flags.none": {
        "es": "Nada nuevo: el documento dice lo que dice tu material.",
        "en": "Nothing new: the document says what your material says.",
    },
    "attempt.flags.skills": {
        "es": "Habilidades que tu material no tiene: {items}",
        "en": "Skills your material does not have: {items}",
    },
    "attempt.flags.claims": {
        "es": "Cifras, fechas o nombres sin respaldo: {items}",
        "en": "Figures, dates or names with no support: {items}",
    },
    "attempt.flags.titles": {
        "es": "Puestos que no están en tu material: {items}",
        "en": "Roles your material does not carry: {items}",
    },
    "attempt.flags.above_ceiling": {
        "es": "Este CV puntúa por encima de lo que tu material permite; revisa las "
        "afirmaciones nuevas.",
        "en": "This CV scores above what your material allows; check the new claims.",
    },
    "attempt.left.title": {"es": "Qué queda", "en": "What's left"},
    "attempt.left.none": {
        "es": "Nada pendiente: ya usaste lo que tu material ofrece para esta oferta.",
        "en": "Nothing pending: you already used what your material offers for this posting.",
    },
    "attempt.cost": {"es": "Coste {amount}", "en": "Cost {amount}"},
    "attempt.cost_reused": {
        "es": "sin costo (reutilizado)",
        "en": "no cost (reused)",
    },
    "attempt.sent": {"es": "Enviada", "en": "Sent"},
    # F10.6 (C.2): the readiness checklist, its message, and the personal target.
    "attempt.ready.title": {"es": "Listo para enviar", "en": "Ready to send"},
    "attempt.ready.message": {
        "es": "CV optimizado — lo que falta es experiencia que ATSker no tiene "
        "registrada: {gaps}.",
        "en": "Optimised CV — what is missing is experience ATSker has no record of: "
        "{gaps}.",
    },
    "attempt.ready.message_plain": {
        "es": "CV optimizado — nada más que ATSker pueda añadir con tu material.",
        "en": "Optimised CV — nothing more ATSker can add from your material.",
    },
    "attempt.ready.checklist": {"es": "Falta:", "en": "Missing:"},
    "attempt.ready.match_band": {
        "es": "El ajuste ({job_match}) no llega al techo ({ceiling_low}) dentro del "
        "margen de {band}.",
        "en": "The fit ({job_match}) does not reach the ceiling ({ceiling_low}) "
        "within the {band}-point band.",
    },
    "attempt.ready.match_target": {
        "es": "El ajuste ({job_match}) no llega a tu objetivo ({target}).",
        "en": "The fit ({job_match}) does not reach your target ({target}).",
    },
    "attempt.ready.readability": {
        "es": "El documento tiene bloqueantes de formato: {items}.",
        "en": "The document has format blockers: {items}.",
    },
    "attempt.ready.search": {
        "es": "Búsquedas que no te devuelven: {items}.",
        "en": "Searches that do not return you: {items}.",
    },
    "attempt.ready.advice": {
        "es": "Recomendaciones pendientes: {items}.",
        "en": "Advice still open: {items}.",
    },
    "attempt.ready.language": {
        "es": "El documento no está en el idioma de la oferta.",
        "en": "The document is not in the posting's language.",
    },
    "attempt.ready.target_label": {
        "es": "Tu objetivo (máximo {ceiling_high})",
        "en": "Your target (max {ceiling_high})",
    },
    "attempt.ready.target_save": {"es": "Guardar objetivo", "en": "Save target"},
    "attempt.ready.target_hint": {
        "es": "Se guarda en este análisis, no en el intento.",
        "en": "Saved on this analysis, not on the attempt.",
    },
    "attempt.ready.target_name": {"es": "Objetivo", "en": "Target"},
    "attempt.done_heading": {
        "es": "Intento {n} — informe completo",
        "en": "Attempt {n} — full report",
    },
    "attempt.back": {
        "es": "Volver al análisis",
        "en": "Back to the analysis",
    },
    "attempt.running": {
        "es": "Leyendo y puntuando el documento…",
        "en": "Reading and scoring the document…",
    },
    "report.cost_label": {"es": "Coste del análisis", "en": "Analysis cost"},
    "report.readability_capped": {
        "es": "El documento limita la puntuación: {check}.",
        "en": "The document caps the score: {check}.",
    },
    "report.track": {"es": "Línea de carrera: {name}", "en": "Track: {name}"},
    "report.no_track": {
        "es": "Sin línea: se puntuaron todos los bullets activos.",
        "en": "No track: every active bullet was scored.",
    },
    "report.sub_scores": {"es": "Componentes", "en": "Components"},
    # §12.1 item 3: the colour legend under Componentes, and the hidden word each term chip
    # carries beside its glyph.
    "report.legend.sample": {"es": "término", "en": "term"},
    "report.legend.found": {"es": "aparece en tu CV", "en": "appears in your CV"},
    "report.legend.missing": {"es": "falta en tu CV", "en": "missing from your CV"},
    "report.legend.toggle": {"es": "Cómo leer las marcas", "en": "How to read the marks"},
    "report.legend.scores": {
        "es": "Puntuaciones: «Fuerte» desde 75, «Adecuado» de 50 a 74, «Débil» por debajo "
        "de 50; cada segmento vale 20 puntos.",
        "en": "Scores: “Strong” from 75, “Adequate” 50 to 74, “Weak” below 50; each "
        "segment is worth 20 points.",
    },
    "report.legend.dashed": {
        "es": "Borde discontinuo con ✕: algo falta o necesita atención "
        "(un término que falta, una brecha decisiva, una advertencia).",
        "en": "Dashed outline with ✕: something is missing or needs attention "
        "(a missing term, a blocking gap, a warning).",
    },
    "report.legend.filled": {
        "es": "Fondo gris con ✓: está presente.",
        "en": "Grey fill with ✓: it is present.",
    },
    "report.divider.screens": {"es": "Las dos pantallas", "en": "The two screens"},
    "report.row.keywords": {"es": "{n} palabras clave", "en": "{n} keywords"},
    "report.row.keywords_one": {"es": "1 palabra clave", "en": "1 keyword"},
    "report.row.advice": {"es": "{n} recomendaciones", "en": "{n} recommendations"},
    "report.row.advice_none": {
        "es": "Sin recomendaciones para este análisis.",
        "en": "No recommendations for this analysis.",
    },
    "report.row.advice_one": {"es": "1 recomendación", "en": "1 recommendation"},
    "report.legend.severity": {
        "es": "Los iconos de octágono, triángulo y círculo son del análisis de legibilidad.",
        "en": "The octagon, triangle and circle icons are for the readability scan.",
    },
    "report.term.found": {"es": "encontrada", "en": "found"},
    "report.term.missing": {"es": "falta", "en": "missing"},
    # F7.1: the table the recommendation produces, above the components, with the
    # chosen track marked. The justification is a code-built line, not prose from a
    # model: the winner, the sub-score it leads on, and the track's own "when to use".
    "report.recommendation": {
        "es": "Recomendación de línea de carrera",
        "en": "Track recommendation",
    },
    "report.recommendation.intro": {
        "es": "La oferta puntuada contra cada línea de carrera candidata. La elegida es la que se "
        "guarda en esta aplicación.",
        "en": "The posting scored against each candidate track. The chosen one is what "
        "this application stores.",
    },
    "report.recommendation.track": {"es": "Línea", "en": "Track"},
    "report.recommendation.chosen": {"es": "Elegido", "en": "Chosen"},
    "report.recommendation.not_graded": {
        "es": "Sin evaluar: {names}",
        "en": "Not graded: {names}",
    },
    "report.recommendation.margin": {
        "es": "Margen sobre {runner_up}: {margin} puntos.",
        "en": "Margin over {runner_up}: {margin} points.",
    },
    "report.recommendation.tie_sub": {
        "es": "Lo que más las separa es {sub_score}: {delta} puntos.",
        "en": "The largest difference is {sub_score}: {delta} points.",
    },
    "report.recommendation.tie_organisation": {
        "es": "La empresa encaja con {track} por su tipo de organización.",
        "en": "The company matches {track} on its organisation kind.",
    },
    "report.recommendation.justification": {
        "es": "{track} lidera en {sub_score} (+{delta}) sobre {runner_up}. {applies_when}",
        "en": "{track} leads on {sub_score} (+{delta}) over {runner_up}. {applies_when}",
    },
    "report.recommendation.justification_single": {
        "es": "{track}. {applies_when}",
        "en": "{track}. {applies_when}",
    },
    "report.recommendation.cost": {
        "es": "Coste de recomendar: ${cost}",
        "en": "Cost of recommending: ${cost}",
    },
    "report.sub.title": {"es": "Alineación del título", "en": "Title alignment"},
    "report.sub.skills": {"es": "Habilidades", "en": "Skills"},
    "report.sub.keywords": {"es": "Palabras clave", "en": "Keywords"},
    "report.sub.experience": {"es": "Experiencia", "en": "Experience"},
    # `w1` reports keep their own component names: a stored report renders from its own
    # keys, and `evidence`/`keyword`/`semantic` are what its JSON says.
    "report.sub.evidence": {"es": "Cobertura de evidencia", "en": "Evidence coverage"},
    "report.sub.keyword": {"es": "Contexto de palabras clave", "en": "Keyword context"},
    "report.sub.semantic": {"es": "Ajuste semántico", "en": "Semantic fit"},
    # §12.1: no weights are shown on the report page, so there is no word for one. The
    # calculation version is what the page names instead.
    "report.calculation": {"es": "Cálculo", "en": "Calculation"},
    "report.model": {"es": "Modelo", "en": "Model"},
    "report.calls_cost": {"es": "Llamadas y coste", "en": "Calls and cost"},
    "report.evidence_language": {"es": "Idioma de la evidencia", "en": "Evidence language"},
    "report.analyse_another": {
        "es": "Analizar con otra línea",
        "en": "Analyse with another posting",
    },
    "report.job_match_caption": {
        "es": "Qué tan bien encaja este CV con lo que pide la oferta; no es la "
        "probabilidad de ser contratado.",
        "en": "How well this CV fits what the posting asks for; not the probability of "
        "being hired.",
    },
    "report.scan_readability_question": {
        "es": "¿El ATS lee bien tu CV?",
        "en": "Does the ATS read your CV correctly?",
    },
    # N6.6: the readability panel is always present; with no source document it says so
    # rather than disappearing, which read as a clean bill of health.
    "report.scan_no_document": {
        "es": "No se leyó ningún archivo en este análisis: la línea no tiene un CV subido.",
        "en": "No file was read for this analysis: the track has no uploaded CV.",
    },
    "report.requirements": {"es": "Requisitos y evidencia", "en": "Requirements and evidence"},
    "report.before_applying": {"es": "Antes de postular", "en": "Before applying"},
    "report.skills_split_total": {
        "es": "Habilidades {total} = {direct} directo + {transfer} transferible",
        "en": "Skills {total} = {direct} direct + {transfer} transfer",
    },
    # One-line captions for the sub-score cards. The three `w1` names are kept so a
    # stored report renders with a caption rather than a bare key.
    "report.sub_caption.skills": {
        "es": "Lo que demuestras de lo que la oferta pide.",
        "en": "What you demonstrate of what the posting asks for.",
    },
    "report.sub_caption.experience": {
        "es": "Años de experiencia pertinentes a este puesto.",
        "en": "Years of experience pertinent to this posting.",
    },
    "report.sub_caption.title": {
        "es": "Cuánto se acerca tu título al del puesto.",
        "en": "How close your title is to the posting's.",
    },
    "report.sub_caption.keywords": {
        "es": "Términos de la oferta presentes en tu CV.",
        "en": "Terms from the posting present in your CV.",
    },
    "report.sub_caption.evidence": {
        "es": "Cobertura de evidencia del informe almacenado.",
        "en": "Evidence coverage, as the stored report recorded it.",
    },
    "report.sub_caption.keyword": {
        "es": "Contexto de palabras clave del informe almacenado.",
        "en": "Keyword context, as the stored report recorded it.",
    },
    "report.sub_caption.semantic": {
        "es": "Ajuste semántico del informe almacenado.",
        "en": "Semantic fit, as the stored report recorded it.",
    },
    "report.disqualifiers": {"es": "Requisitos eliminatorios", "en": "Disqualifiers"},
    "report.disqualifiers_hint": {
        "es": "No entran en la puntuación: un requisito eliminatorio no es un porcentaje.",
        "en": "They do not enter the score: a disqualifier is not a percentage.",
    },
    "report.disqualifiers_unverified_hint": {
        "es": "ATSker no puede comprobar los sin verificar: confírmalos tú antes de "
        "enviar la candidatura.",
        "en": "ATSker cannot check the unverified ones: confirm them yourself before "
        "applying.",
    },
    "report.verdict.met": {"es": "cumple", "en": "met"},
    "report.verdict.unmet": {"es": "no cumple", "en": "unmet"},
    "report.verdict.unverified": {"es": "sin verificar", "en": "unverified"},
    "report.gaps": {"es": "Huecos", "en": "Gaps"},
    "report.gaps_all": {"es": "Ver el detalle ({count})", "en": "See the detail ({count})"},
    "report.gap_blocking": {"es": "bloqueante", "en": "blocking"},
    "report.came_close": {"es": "Se acercó", "en": "Came close"},
    "report.no_gaps": {
        "es": "Ningún requisito queda sin cubrir.",
        "en": "No requirement is left uncovered.",
    },
    "report.gap_warning": {"es": "Aviso:", "en": "Warning:"},
    "report.gap_handling": {"es": "Cómo afrontarlo:", "en": "Suggested handling:"},
    "report.no_stories_available": {
        "es": "No había historias disponibles para este análisis.",
        "en": "No stories were available for this analysis.",
    },
    "report.grades": {"es": "Requisitos evaluados", "en": "Graded requirements"},
    "report.grades_hint": {
        "es": "0 ausente · 1 mencionado · 2 aplicado · 3 demostrado. Cada nivel cita el "
        "bullet que lo sostiene.",
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
    "report.basis.direct": {"es": "directa", "en": "direct"},
    "report.basis.equivalent": {"es": "equivalente", "en": "equivalent"},
    "report.basis.transferable": {"es": "transferible", "en": "transferable"},
    "report.basis.none": {"es": "sin base", "en": "no basis"},
    "report.source.summary": {"es": "del resumen", "en": "from the summary"},
    "report.source.skills_list": {
        "es": "de la lista de habilidades",
        "en": "from the skills list",
    },
    "report.transfer_reason": {"es": "Por qué transfiere:", "en": "Why it transfers:"},
    "report.grade_clamped": {
        "es": "Nivel limitado a 1: el resumen y la lista de habilidades no prueban una "
        "tarea descrita.",
        "en": "Clamped to level 1: the summary and the skills list never prove a described task.",
    },
    "report.grade_downgraded": {
        "es": "Base bajada a transferible: sin familia compartida en el vocabulario.",
        "en": "Downgraded to transferable: no shared family in the vocabulary.",
    },
    "report.grade_inferred": {"es": "por familia", "en": "from family data"},
    "report.grade_fallback": {
        "es": "Evidencia en el idioma alternativo.",
        "en": "Fallback-language evidence.",
    },
    "report.skills_split": {
        "es": "{direct} directo + {transfer} transferible",
        "en": "{direct} direct + {transfer} transfer",
    },
    # N6.6: the tag is the relevant years in the interface's language; the line is the
    # split relevant-of-held, both trimmed to at most one decimal by the `years` filter.
    "report.experience_years_tag": {"es": "{years} años", "en": "{years} years"},
    "report.experience_years": {"es": "{relevant} de {held}", "en": "{relevant} of {held}"},
    "report.experience_roles": {"es": "Puestos contados", "en": "Counted roles"},
    "report.transfer_band": {"es": "Cubierto por transferencia", "en": "Covered by transfer"},
    "report.transfer_band_hint": {
        "es": "No son huecos: son las afirmaciones que más se cuestionarán. Prepara el "
        "argumento antes de la entrevista.",
        "en": "Not gaps: these are the claims most likely to be questioned. Prepare the "
        "argument before the interview.",
    },
    "report.alerts": {"es": "Alertas", "en": "Alerts"},
    "report.alert.over_seniority": {
        "es": "Tu seniority está por encima del pedido: riesgo salarial y de retención.",
        "en": "You are above the posting's seniority: salary and retention risk.",
    },
    "report.alert.under_seniority": {
        "es": "El aviso pide un nivel {jd_rung}; tu cargo actual no lo indica",
        "en": "The posting asks for {jd_rung}; your current title does not say so",
    },
    "report.alert.location": {
        "es": "Ubicación por confirmar: {requirement}",
        "en": "Location to confirm: {requirement}",
    },
    # F4.2 (A.9.3): a real screen reads the words that were sent, so a fallback is
    # worth saying out loud. `{items}` is the list of what fell back — bullets,
    # titles, headline, summary — joined by `join_list`, so three of them read
    # "bullets, titular y resumen" rather than "and … and". The language names are
    # the words a reader knows, never the stored codes.
    "report.alert.language_mismatch": {
        "es": "Este aviso está en {posting}; {items} solo existen en {other}. "
        "Un ATS real lee las palabras que envías: envía la versión en {posting}.",
        "en": "This posting is in {posting}; {items} exist only in {other}. "
        "A real ATS reads the words you send — send the {posting} version.",
    },
    # The parts, as they read inside that list: no leading space, no conjunction —
    # the join supplies both.
    "report.alert.language_bullets": {
        "es": "{n} de tus {m} bullets",
        "en": "{n} of your {m} bullets",
    },
    "report.alert.language_titles": {"es": "tus cargos", "en": "your titles"},
    "report.alert.language_headline": {"es": "tu titular", "en": "your headline"},
    "report.alert.language_summary": {"es": "tu resumen", "en": "your summary"},
    "lang.es": {"es": "español", "en": "Spanish"},
    "lang.en": {"es": "inglés", "en": "English"},
    # F7.2: the six deterministic rules, each one an edit the user can make now. The
    # stored item carries the ids and the numbers; the sentence is built here, so the
    # same report reads in either language.
    "report.advice": {"es": "Recomendaciones", "en": "Recommendations"},
    "report.advice.intro": {
        "es": "Cambios concretos, en orden de impacto, calculados sobre este informe y "
        "tus propios datos.",
        "en": "Concrete changes, in order of impact, computed from this report and your "
        "own data.",
    },
    "report.advice.promote_bullet": {
        "es": "Mueve este bullet a las tres primeras de la línea: demuestra {requirement} y está "
        "en la posición {position}, con material más débil por encima.",
        "en": "Move this bullet into the track's first three: it demonstrates "
        "{requirement} and it sits at position {position}, with weaker material above.",
    },
    "report.advice.add_bullet": {
        "es": "Añade este bullet a la línea: demuestra {canonical}, que la oferta pide y el "
        "análisis no encontró.",
        "en": "Add this bullet to the track: it demonstrates {canonical}, which the "
        "posting asks for and the analysis did not find.",
    },
    "report.advice.surface_skill": {
        "es": "Añade {canonical} a las habilidades de la línea: la oferta lo pide y tú lo tienes "
        "demostrado.",
        "en": "Add {canonical} to the track's skills: the posting asks for it and you "
        "have it evidenced.",
    },
    "report.advice.fix_query": {
        "es": "La búsqueda «{query}» no te devolvería, y tienes un bullet que dice {canonical}: "
        "inclúyela en la línea o usa sus palabras.",
        "en": "The search “{query}” would not return you, and you have a bullet that "
        "says {canonical}: add it to the track, or use its words.",
    },
    "report.advice.title_language": {
        "es": "Añade el título «{title}» en {language} a tu puesto «{role}»: una oferta "
        "en {language} lee el título que envías.",
        "en": "Add the {language} title “{title}” to your role “{role}”: a posting in "
        "{language} reads the title you send.",
    },
    "report.advice.title_headline": {
        "es": "Plantea un titular que nombre el puesto al que aplicas, si describe tu "
        "trabajo.",
        "en": "Consider a headline naming the role you apply for, if it describes your "
        "work.",
    },
    "report.advice.language": {
        "es": "Escribe en {language} {bullets} de tus {total_bullets} bullets y "
        "{titles} de tus cargos.",
        "en": "Write {bullets} of your {total_bullets} bullets and {titles} of your "
        "titles in {language}.",
    },
    # F10.3 step 6: the same items worded for a document, not for a track. Only the
    # kinds whose sentence mentions the track have a variant; the rest fall back.
    "report.advice.file.promote_bullet": {
        "es": "Mueve este bullet a las tres primeras de tu documento: demuestra "
        "{requirement} y está en la posición {position}, con material más débil por "
        "encima.",
        "en": "Move this bullet into your document's first three: it demonstrates "
        "{requirement} and it sits at position {position}, with weaker material above.",
    },
    "report.advice.file.add_bullet": {
        "es": "Añade este bullet a tu documento: demuestra {canonical}, que la oferta "
        "pide y el documento no muestra.",
        "en": "Add this bullet to your document: it demonstrates {canonical}, which the "
        "posting asks for and the document does not show.",
    },
    "report.advice.file.surface_skill": {
        "es": "Añade {canonical} a las habilidades de tu documento: la oferta lo pide y "
        "tú lo tienes demostrado.",
        "en": "Add {canonical} to your document's skills list: the posting asks for it "
        "and you have it evidenced.",
    },
    "report.advice.file.fix_query": {
        "es": "La búsqueda «{query}» no te devolvería, y tienes un bullet que dice "
        "{canonical}: inclúyela en tu documento o usa sus palabras.",
        "en": "The search “{query}” would not return you, and you have a bullet that "
        "says {canonical}: include it in your document, or use its words.",
    },
    "report.advice.file.language": {
        "es": "Escribe en {language} {bullets} de los {total_bullets} bullets de tu "
        "documento y {titles} de tus cargos.",
        "en": "Write {bullets} of your document's {total_bullets} bullets and {titles} "
        "of your titles in {language}.",
    },
    "report.advice.evidence": {"es": "Evidencia", "en": "Evidence"},
    # The source tag on every advice item: which of F7.2's rules produced it, in a word.
    "report.advice.tag.promote_bullet": {"es": "Promover", "en": "Promote"},
    "report.advice.tag.add_bullet": {"es": "Añadir", "en": "Add"},
    "report.advice.tag.surface_skill": {"es": "Habilidad", "en": "Skill"},
    "report.advice.tag.fix_query": {"es": "Búsqueda", "en": "Search"},
    "report.advice.tag.title_language": {"es": "Título", "en": "Title"},
    "report.advice.tag.title_headline": {"es": "Titular", "en": "Headline"},
    "report.advice.tag.language": {"es": "Idioma", "en": "Language"},
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
    # Removed: "report.weights_version" — the page names the calculation, never weights.
    "report.prompt_versions": {"es": "Versiones de prompt", "en": "Prompt versions"},
    "report.jd_hash": {"es": "Hash de la oferta", "en": "Posting hash"},
    "report.again": {"es": "Analizar otra oferta", "en": "Analyse another posting"},
    # F7.3's generated text: on demand, validated, shown as a diff, accepted by hand.
    "generate.propose_summary": {"es": "Proponer resumen", "en": "Propose summary"},
    "generate.saved": {
        "es": "Resumen guardado en tu material",
        "en": "Summary saved to your material",
    },
    "generate.no_track": {
        "es": "Elige una línea de carrera al analizar para proponer un resumen",
        "en": "Choose a track when you analyse to propose a summary",
    },
    # §12.5: what the pop-up says before the button, in words — opening it calls nothing.
    "generate.dialog.sends": {
        "es": "Se enviarán al modelo, sin tu nombre ni tus datos de contacto: la oferta tal "
        "como se extrajo, los bullets de «{track}» ({n}) y tus habilidades como contexto. "
        "Solo se propone el resumen.",
        "en": "Sent to the model, without your name or contact details: the posting as "
        "extracted, the bullets of “{track}” ({n}) and your skills as context. Only the "
        "summary is proposed.",
    },
    "generate.dialog.cost": {
        "es": "Es una llamada de pago al modelo, una sola por pulsación. Abrir esta ventana "
        "no cuesta nada.",
        "en": "It is one paid call to the model per press. Opening this window costs nothing.",
    },
    # §12.5: a failed proposal says which of three things went wrong.
    "generate.err.no_model": {
        "es": "El modelo no está configurado: no se puede proponer nada todavía.",
        "en": "No model is configured: nothing can be proposed yet.",
    },
    "generate.err.provider": {
        "es": "El proveedor del modelo no respondió; no se ha propuesto nada. Inténtalo de "
        "nuevo.",
        "en": "The model provider did not answer; nothing was proposed. Try again.",
    },
    "generate.err.unusable": {
        "es": "El modelo respondió, pero la respuesta no fue utilizable; no se ha propuesto "
        "nada. Inténtalo de nuevo.",
        "en": "The model answered, but the answer was not usable; nothing was proposed. "
        "Try again.",
    },
    # The provider call is a button on a POST, never a GET (F.0).
    "generate.run": {"es": "Generar propuesta", "en": "Generate proposal"},
    "generate.title": {"es": "Resumen propuesto", "en": "Proposed summary"},
    "generate.intro": {
        "es": "Una propuesta a partir de tu propio material. Nada se guarda hasta que "
        "aceptes, y al aceptar se vuelve a validar contra la base de datos.",
        "en": "A proposal built from your own material. Nothing is stored until you "
        "accept, and accepting validates it against the database again.",
    },
    "generate.current": {"es": "Ahora", "en": "Current"},
    "generate.proposed": {"es": "Propuesta", "en": "Proposed"},
    "generate.empty_summary": {
        "es": "— sin resumen en este idioma —",
        "en": "— no summary in this language —",
    },
    "generate.use_in_track": {
        "es": "Usar en esta línea: {name}",
        "en": "Use in this track: {name}",
    },
    "generate.check.title": {
        "es": "Título exacto de la oferta",
        "en": "Exact posting title",
    },
    "generate.check.skills": {
        "es": "Habilidades clave nombradas ({n})",
        "en": "Key skills named ({n})",
    },
    "generate.check.length": {
        "es": "Máximo 80 palabras ({n})",
        "en": "At most 80 words ({n})",
    },
    "generate.check.ok": {"es": "cumple", "en": "met"},
    "generate.check.fail": {"es": "no cumple", "en": "not met"},
    "generate.check.heading": {
        "es": "Reglas de estilo de la propuesta",
        "en": "The proposal's style rules",
    },
    "generate.check.note": {
        "es": "Si una regla no se cumple puedes aceptar la propuesta igualmente.",
        "en": "If a rule is not met you can still accept the proposal.",
    },
    "generate.base.track": {
        "es": "Basado en el resumen de tu línea «{name}»",
        "en": "Based on the summary of your track «{name}»",
    },
    "generate.base.cv": {
        "es": "Basado en el resumen de tu CV subido",
        "en": "Based on the summary of your uploaded CV",
    },
    "generate.base.other_language": {
        "es": "Basado en tu resumen en {other}, traducido",
        "en": "Based on your summary in {other}, translated",
    },
    "generate.base.none": {
        "es": "No había un resumen base: escrito desde tus bullets",
        "en": "There was no base summary: written from your bullets",
    },
    "generate.langname.es": {"es": "español", "en": "Spanish"},
    "generate.langname.en": {"es": "inglés", "en": "English"},
    "generate.title_note": {
        "es": "«{title}» es el título de la oferta; no figura entre los que has tenido.",
        "en": "«{title}» is the posting's title; it is not among the titles you have held.",
    },
    "generate.shortlist_short": {
        "es": "Habilidades clave que tu CV respalda directamente en esta oferta: {n}.",
        "en": "Key skills your CV directly backs for this posting: {n}.",
    },
    "generate.shortlist_related": {
        "es": "{n} de los requisitos de la oferta y {m} relacionadas que muestras.",
        "en": "{n} from the posting's requirements and {m} related ones you show.",
    },
    "generate.base.file": {
        "es": "Basado en el resumen de tu documento",
        "en": "Based on the summary of your document",
    },
    "generate.dialog.sends_file": {
        "es": "Se enviarán al modelo, sin tu nombre ni tus datos de contacto: la oferta tal "
        "como se extrajo, los bullets de tu documento ({n}) y las habilidades de tu documento "
        "y de tu material como contexto. Solo se propone el resumen.",
        "en": "Sent to the model, without your name or contact details: the posting as "
        "extracted, your document's bullets ({n}) and the skills in your document and your "
        "material as context. Only the summary is proposed.",
    },
    "generate.copy_only": {
        "es": "Pégalo en tu documento; no se guarda en tu material.",
        "en": "Paste it into your document; it is not saved to your material.",
    },
    "generate.rejected_copy": {
        "es": "Esta propuesta incluye algo que no consta en tu documento ni en tu material: "
        "revísalo antes de pegarla.",
        "en": "This proposal includes something that is not in your document or your material: "
        "check it before you paste it.",
    },
    "attempt.actions.summary": {
        "es": "Proponer resumen para este documento",
        "en": "Propose a summary for this document",
    },
    "generate.accept": {"es": "Aceptar", "en": "Accept"},
    "generate.back": {"es": "Volver al informe", "en": "Back to the report"},
    "generate.rejected": {
        "es": "La propuesta no pasó la validación y no se puede aceptar.",
        "en": "The proposal failed validation and cannot be accepted.",
    },
    "generate.rejected_editable": {
        "es": "La propuesta aún no pasa la validación: corrige el texto y vuelve a aceptar.",
        "en": "The proposal does not pass validation yet: edit the text and accept again.",
    },
    "generate.refused": {
        "es": "No se ha guardado nada: la propuesta enviada no pasó la validación.",
        "en": "Nothing was stored: the submitted proposal failed validation.",
    },
    "generate.failed": {
        "es": "El modelo no respondió; no se ha propuesto nada. Inténtalo de nuevo.",
        "en": "The model did not answer; nothing was proposed. Try again.",
    },
    "generate.violation.provenance": {
        "es": "Cita una fuente que no existe o no es tuya.",
        "en": "Cites a source that does not exist or is not yours.",
    },
    "generate.violation.literal": {
        "es": "Un número o un nombre no aparece en la fuente citada.",
        "en": "A number or a name does not appear in the cited source.",
    },
    "generate.violation.closure": {
        "es": "Nombra una habilidad que no está en tus datos o no está respaldada.",
        "en": "Names a skill that is not in your data or is not evidenced.",
    },
    "generate.violation.closure_missing": {
        "es": "Habilidades que no están en tus datos",
        "en": "Skills that are not in your data",
    },
    "generate.violation.closure_unevidenced": {
        "es": "Están en tus datos, pero no se muestran con nivel 2 o mejor en las viñetas "
        "que cita este resumen",
        "en": "In your data, but not shown at level 2 or better in the bullets this "
        "summary cites",
    },
    # Tier 3a: one bullet, rewritten for the posting it was cited for.
    "generate.rephrase": {"es": "Reformular para este aviso", "en": "Rephrase for this posting"},
    "generate.rephrase_title": {
        "es": "Reformular para este aviso",
        "en": "Rephrase for this posting",
    },
    "generate.rephrase_intro": {
        "es": "Una llamada por click. Aceptar guarda el texto nuevo como una revisión "
        "y conserva el anterior.",
        "en": "One call per click. Accepting stores the new text as a revision and "
        "keeps the previous one.",
    },
    "generate.current_bullet": {"es": "Bullet actual", "en": "Current bullet"},
    "generate.empty_bullet": {
        "es": "— este bullet no tiene texto en este idioma —",
        "en": "— this bullet has no text in this language —",
    },
    "generate.suggested_translation": {
        "es": "Sugerencia de traducción: este bullet no tiene texto en el idioma del aviso.",
        "en": "Suggested translation: this bullet has no text in the posting's language.",
    },
    # Tier 3b: up to three bullets a story supports, each reviewed before it exists.
    "generate.propose_bullets": {"es": "Proponer bullets", "en": "Propose bullets"},
    "generate.story_title": {
        "es": "Bullets propuestos desde la historia",
        "en": "Bullets proposed from the story",
    },
    "generate.story_intro": {
        "es": "Hasta tres bullets a partir de esta historia. Cada uno es una propuesta "
        "que revisas antes de que exista; aceptarlo crea un bullet con la historia como "
        "origen. La historia no cambia.",
        "en": "Up to three bullets from this story. Each is a proposal you review before "
        "it exists; accepting creates a bullet with the story as its source. The story "
        "does not change.",
    },
    "generate.bullet_text": {"es": "Texto del bullet", "en": "Bullet text"},
    "generate.role": {"es": "Puesto", "en": "Role"},
    "generate.chips": {"es": "Chips", "en": "Chips"},
    "generate.chips_hint": {
        "es": "Separados por comas. Un término que el vocabulario no conoce se guarda "
        "como pendiente, no se pierde.",
        "en": "Comma-separated. A term the vocabulary does not know is kept as pending, "
        "never lost.",
    },
    "generate.need_roles": {
        "es": "Necesitas al menos un puesto para que un bullet tenga dónde vivir.",
        "en": "You need at least one role for a bullet to live on.",
    },
    "generate.no_bullets": {
        "es": "El modelo no propuso ningún bullet para esta historia.",
        "en": "The model proposed no bullets for this story.",
    },

    # Profile
    "profile.title": {"es": "Perfil", "en": "Profile"},
    "profile.standing_risks": {"es": "Riesgos persistentes", "en": "Standing risks"},
    "profile.standing_risks_hint": {
        "es": "Uno por línea. Lo que puede jugar en contra en cualquier candidatura "
        "(p. ej. salir del sector público): el análisis de huecos los contrasta con "
        "cada oferta y avisa solo de los que muerden aquí.",
        "en": "One per line. What could work against any application (e.g. leaving "
        "the public sector): the gap analysis checks each against the posting and "
        "warns only about the ones that bite here.",
    },
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
    "roles.title": {"es": "Experiencia", "en": "Experience"},
    "roles.new": {"es": "Nuevo puesto", "en": "New role"},
    "roles.employer": {"es": "Empleador", "en": "Employer"},
    # F4.2: one title per language. The words "cargo" and "title" name the slots the
    # way the user fills them, and only one of the two has to be written.
    "roles.title_es": {"es": "Cargo (ES)", "en": "Cargo (ES)"},
    "roles.title_en": {"es": "Title (EN)", "en": "Title (EN)"},
    "roles.title_hint": {
        "es": "Una oferta en un idioma lee el título en ese idioma. Un ATS lee las "
        "palabras que envías, así que escribe el título en el idioma de la versión "
        "que envías; el otro puede quedar vacío.",
        "en": "A posting in one language reads that language's title. An ATS reads "
        "the words you send, so write the title in the language of the version you "
        "send; the other slot may stay empty.",
    },
    "roles.start": {"es": "Desde", "en": "From"},
    "roles.end": {"es": "Hasta", "en": "To"},
    "roles.present": {"es": "actualidad", "en": "present"},
    "roles.bullets": {"es": "bullets", "en": "bullets"},
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
    "tracks.title": {"es": "Líneas de carrera", "en": "Tracks"},
    "tracks.new": {"es": "Nueva línea de carrera", "en": "New track"},
    "tracks.intro": {
        "es": "Una línea de carrera es un rol al que apuntas, con una selección ordenada de tus "
        "bullets. No copia contenido: el mismo bullet sirve a varias.",
        "en": "A track is a target role with an ordered selection of your bullets. It copies "
        "no content: the same bullet serves several tracks.",
    },
    "tracks.name": {"es": "Nombre", "en": "Name"},
    "tracks.applies_when": {"es": "Cuándo usarlo", "en": "When to use it"},
    "tracks.applies_hint": {
        "es": "Lo lee el recomendador para elegir la línea de carrera ante una oferta.",
        "en": "The recommender reads this to pick a track for a posting.",
    },
    "tracks.lang": {"es": "Idioma", "en": "Language"},
    # F4.1/F8: the track's language is also the language of its cover letters.
    "tracks.letter_card": {"es": "Carta", "en": "Letter"},
    "tracks.lang_hint": {
        "es": "Las cartas de esta línea se escriben en este idioma.",
        "en": "This role's cover letters are written in this language.",
    },
    "tracks.lang_line": {
        "es": "Idioma: {code} · cartas en {name}",
        "en": "Language: {code} · letters in {name}",
    },
    "tracks.seniority": {"es": "Seniority objetivo", "en": "Target seniority"},
    "tracks.seniority_hint": {"es": "Opcional.", "en": "Optional."},
    "tracks.organisation_kind": {"es": "Tipo de organización", "en": "Organisation kind"},
    "tracks.organisation_kind_hint": {
        "es": "El tipo de empleador al que apuntas: corporativo, técnico, gobierno, ONG, "
        "educación… Opcional.",
        "en": "The kind of employer you are aiming at: corporate, technical, government, "
        "NGO, education… Optional.",
    },
    "tracks.specialisation": {"es": "Especialización", "en": "Specialisation"},
    "tracks.specialisation_hint": {
        "es": "El eje de la propia línea: riesgo, marketing, plataforma… Opcional.",
        "en": "The role's own axis: risk, marketing, platform… Optional.",
    },
    "tracks.headline_es": {"es": "Titular en español", "en": "Spanish headline"},
    "tracks.headline_en": {"es": "Titular en inglés", "en": "English headline"},
    "tracks.headline_hint": {
        "es": "Uno por idioma. Al analizar una oferta se lee el del idioma de la oferta, "
        "y si falta, el otro; sin ninguno se usa el titular del perfil.",
        "en": "One per language. An analysis reads the posting's language one and falls "
        "back to the other; with neither, the profile headline is used.",
    },
    "tracks.summary_es": {"es": "Resumen en español", "en": "Spanish summary"},
    "tracks.summary_en": {"es": "Resumen en inglés", "en": "English summary"},
    "tracks.summary_none": {"es": "— sin resumen —", "en": "— no summary —"},
    "tracks.summary_new": {
        "es": "O escribir uno nuevo (se guarda en el fondo común)",
        "en": "Or write a new one (it joins the pool)",
    },
    "tracks.summary_hint": {
        "es": "Uno por idioma, tomado del fondo común de resúmenes o escrito aquí: uno escrito "
        "nuevo entra en el fondo y puede reusarlo otra línea de carrera. La línea referencia el "
        "fondo; no guarda texto propio.",
        "en": "One per language, picked from the summary pool or written here: a written "
        "one joins the pool and can be reused by another track. The track references "
        "the pool; it stores no text of its own.",
    },
    "tracks.skills": {"es": "Habilidades", "en": "Skills"},
    "tracks.skills_hint": {
        "es": "Solo las de tu fondo común de habilidades, agrupadas por tipo. Una "
        "habilidad que ninguna importación o entrada manual listó no puede añadirse.",
        "en": "Only your skills pool, grouped by kind. A skill no upload or manual entry "
        "ever listed cannot be added.",
    },
    "tracks.skills_pool_empty": {
        "es": "Tu fondo de habilidades está vacío: importa un currículum o añade "
        "habilidades a un bullet.",
        "en": "Your skills pool is empty: import a résumé or add skills to a bullet.",
    },
    "tracks.skills_none": {"es": "Sin habilidades seleccionadas.", "en": "No skills selected."},
    "tracks.summaries_present": {"es": "Con resumen en: {langs}", "en": "Summary in: {langs}"},
    "tracks.summaries_absent": {"es": "Sin resumen todavía.", "en": "No summary yet."},
    "tracks.bullets": {"es": "bullets", "en": "bullets"},
    "tracks.empty": {
        "es": "Todavía no hay líneas de carrera. Crea la primera.",
        "en": "No tracks yet. Create the first one.",
    },
    "tracks.selection": {"es": "Bullets seleccionados", "en": "Selected bullets"},
    "tracks.selection_hint": {
        "es": "En este orden. El análisis puntúa solo estos bullets.",
        "en": "In this order. An analysis scores only these bullets.",
    },
    "tracks.no_bullets": {"es": "Sin bullets seleccionados.", "en": "No bullets selected yet."},
    "tracks.pick": {"es": "Elegir bullets", "en": "Pick bullets"},
    "tracks.pick_title": {"es": "Bullets de {name}", "en": "Bullets for {name}"},
    "tracks.pick_hint": {
        "es": "Marca los bullets y ordénalos con el número. Los que no lleven número van al "
        "final, en el orden en que aparecen.",
        "en": "Tick the bullets and order them with the number. Unnumbered ones go last, in "
        "the order they appear.",
    },
    "tracks.order": {"es": "Orden", "en": "Order"},
    "tracks.no_master_bullets": {
        "es": "No hay bullets activos en la base maestra.",
        "en": "No active bullets in the master database.",
    },
    "tracks.clone": {"es": "Clonar", "en": "Clone"},
    "tracks.clone_hint": {
        "es": "Copia los campos y la selección, con su orden.",
        "en": "Copies the fields and the selection, order included.",
    },
    "tracks.deactivate_hint": {
        "es": "Desactivar conserva la línea de carrera para los informes ya generados.",
        "en": "Deactivating keeps the track for reports already generated.",
    },
    # Summary pool (F2.7/F4.1)
    "summaries.edit": {"es": "Editar el resumen", "en": "Edit the summary"},
    "summaries.edit_hint": {
        "es": "Los resúmenes viven en un fondo común: editar aquí cambia el texto en todas las "
        "líneas de carrera que lo usen.",
        "en": "Summaries live in a shared pool: editing here changes the text in every "
        "track that uses it.",
    },
    "summaries.text": {"es": "Resumen", "en": "Summary"},
    "summaries.hand_written": {"es": "escrito a mano", "en": "written by hand"},
    "summaries.from_upload": {
        "es": "Viene de un currículum importado.",
        "en": "From an uploaded résumé.",
    },
    # Bullets
    "bullets.title": {"es": "Bullets", "en": "Bullets"},
    "bullets.new": {"es": "Nuevo bullet", "en": "New bullet"},
    "bullets.edit": {"es": "Editar bullet", "en": "Edit bullet"},
    "bullets.text_es": {"es": "Texto (ES)", "en": "Text (ES)"},
    "bullets.text_en": {"es": "Texto (EN)", "en": "Text (EN)"},
    "bullets.need_text": {
        "es": "Escribe el bullet en al menos un idioma.",
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
    "bullets.empty": {"es": "Sin bullets en este puesto.", "en": "No bullets in this role."},
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
    "stories.related_bullets": {"es": "Bullets relacionados", "en": "Related bullets"},
    "stories.related_hint": {
        "es": "Marca los bullets que esta historia respalda.",
        "en": "Tick the bullets this story backs up.",
    },
    "stories.empty": {"es": "Todavía no hay historias.", "en": "No stories yet."},
    "stories.linked": {"es": "{count} bullets enlazados", "en": "{count} linked bullets"},
    "stories.suggest": {"es": "Sugerir etiquetas", "en": "Suggest tags"},
    "stories.suggest_hint": {
        "es": "El modelo propone puesto, bullets y habilidades; tú confirmas antes de guardar.",
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

    # Letters
    "letters.title": {"es": "Cartas", "en": "Letters"},
    "letters.intro": {
        "es": "Una carta se arma con tus bloques comunes, la carta de cada línea y un párrafo de "
        "interés que se escribe para cada oferta.",
        "en": "A letter is made of your common blocks, each role's letter and a paragraph "
        "of interest written for each posting.",
    },
    "letters.name": {"es": "Nombre", "en": "Name"},
    "letters.applies_when": {"es": "Cuándo usarla", "en": "When to use it"},
    "letters.applies_when_hint": {
        "es": "Una nota para ti sobre cuándo servía esta carta.",
        "en": "A note for yourself about when this letter was meant for.",
    },
    "letters.presentation": {"es": "Párrafo de presentación", "en": "Presentation paragraph"},
    "letters.achievements": {"es": "Párrafo de logros", "en": "Achievements paragraph"},
    # F8 (2026-10-04): one template per track — Cartas by track, the track's own page.
    "letters.by_track_title": {"es": "Carta por línea", "en": "Letter per role"},
    "letters.by_track_hint": {
        "es": "Cada línea tiene una carta, escrita en el idioma de la línea.",
        "en": "Each role has one letter, written in the role's language.",
    },
    "letters.no_tracks": {
        "es": "Todavía no tienes líneas de carrera. Crea una y vuelve aquí para escribir su carta.",
        "en": "You have no target roles yet. Create one and come back to write its letter.",
    },
    "letters.status.ready": {"es": "Lista", "en": "Ready"},
    "letters.status.missing": {"es": "Falta", "en": "Missing"},
    "letters.status.several": {"es": "Varias: elige una", "en": "Several: choose one"},
    "letters.status.other_lang": {"es": "Otro idioma", "en": "Other language"},
    "letters.action.edit": {"es": "Editar carta", "en": "Edit letter"},
    "letters.action.create": {"es": "Crear carta", "en": "Create letter"},
    "letters.inactive_title": {"es": "Líneas inactivas", "en": "Inactive roles"},
    "letters.unlinked_title": {"es": "Sin línea", "en": "No role"},
    "letters.unlinked_hint": {
        "es": "Cartas de antes, sin línea: ninguna carta las usa. Asígnalas a una línea para "
        "usarlas.",
        "en": "Older letters with no role: no letter uses them. Assign one to a role to "
        "use it.",
    },
    "letters.unlinked_note": {
        "es": "Esta carta no está ligada a ninguna línea. Asígnala desde Cartas para usarla.",
        "en": "This letter is not linked to any role. Assign it from Letters to use it.",
    },
    "letters.view": {"es": "Ver", "en": "View"},
    "letters.assign": {"es": "Asignar a una línea", "en": "Assign to a role"},
    "letters.assign_label": {"es": "Línea para esta carta", "en": "Role for this letter"},
    "letters.assign_none": {
        "es": "No hay líneas activas en {name}: crea una para asignar esta carta.",
        "en": "There are no active roles in {name}: create one to assign this letter.",
    },
    "letters.notice.saved": {
        "es": "Carta de «{track}» guardada.",
        "en": "Letter for “{track}” saved.",
    },
    "letters.notice.assigned": {
        "es": "Carta asignada a «{track}».",
        "en": "Letter assigned to “{track}”.",
    },
    "letters.notice.assigned_moved": {
        "es": "Carta asignada a «{track}». La carta que tenía la línea pasó a «Sin línea».",
        "en": "Letter assigned to “{track}”. The letter the role had moved to “No role”.",
    },
    "letters.notice.chosen": {
        "es": "Carta elegida. Las demás pasaron a «Sin línea», sin borrarse.",
        "en": "Letter chosen. The others moved to “No role”, none deleted.",
    },
    "letters.track_letter_title": {"es": "Carta de la línea", "en": "Role letter"},
    "letters.track_letter_lang": {
        "es": "Idioma de la carta: {name}",
        "en": "Letter language: {name}",
    },
    "letters.track_letter_intro": {
        "es": "Presentación y logros de esta línea. Cada carta que escribas para ella parte de "
        "estos dos párrafos.",
        "en": "This role's presentation and achievements. Every letter you write for it "
        "starts from these two paragraphs.",
    },
    "letters.presentation_hint": {"es": "≤ 70 palabras", "en": "≤ 70 words"},
    "letters.achievements_hint": {
        "es": "80–160 palabras, un solo párrafo, con un logro principal y sus números",
        "en": "80–160 words, one paragraph, with one main achievement and its numbers",
    },
    "letters.other_lang_alert": {
        "es": "Esta carta está en {x} y la línea en {y}: edítala o autogenérala.",
        "en": "This letter is in {x} and the role is in {y}: edit it or autogenerate it.",
    },
    "letters.several_title": {
        "es": "Esta línea tiene varias cartas",
        "en": "This role has several letters",
    },
    "letters.several_hint": {
        "es": "Se usa la primera de la lista hasta que elijas. Las demás no se borran: pasan a "
        "«Sin línea».",
        "en": "The first in the list is used until you choose. The others are not deleted: "
        "they move to “No role”.",
    },
    "letters.in_use": {"es": "En uso", "en": "In use"},
    "letters.use_this": {"es": "Usar esta", "en": "Use this one"},
    # F8: the blocks every letter shares, written once per language.
    "letters.settings_title": {"es": "Bloques comunes", "en": "Common blocks"},
    "letters.settings_hint": {
        "es": "Lo que no cambia entre candidaturas: se escribe una vez por idioma y lo "
        "usan todas las cartas de ese idioma.",
        "en": "What does not change between applications: written once per language, "
        "used by every letter in that language.",
    },
    "letters.blocks_header": {
        "es": "Encabezado (nombre, contacto)",
        "en": "Header (name, contact)",
    },
    "letters.blocks_greeting": {"es": "Saludo", "en": "Greeting"},
    "letters.blocks_closing": {"es": "Cierre", "en": "Closing"},
    "letters.blocks_sign_off": {"es": "Firma", "en": "Sign-off"},
    "letters.blocks_voice": {"es": "Notas de voz", "en": "Voice notes"},
    "letters.blocks_voice_hint": {
        "es": "Registro, tuteo, lo que quieras que diga cada generación. Es dato, no "
        "código.",
        "en": "Register, formality, anything every generation should say. It is data, "
        "not code.",
    },
    "letters.save_blocks": {"es": "Guardar bloques", "en": "Save blocks"},
    # F8: the track's two reusable paragraphs; "Autogenerar" drafts them from its own material.
    # F8: "Autogenerar" — the common blocks by code, the track's template by one call.
    "letters.autogenerate": {"es": "Autogenerar", "en": "Autogenerate"},
    "letters.autogenerate_notice": {
        "es": "Revisa los campos y pulsa Guardar.",
        "en": "Review the fields and press Save.",
    },
    "letters.blocks_header_hint": {
        "es": "Añade tu teléfono o LinkedIn si quieres.",
        "en": "Add your phone or LinkedIn if you like.",
    },
    "letters.default.header": {"es": "{name}\n{email}", "en": "{name}\n{email}"},
    "letters.default.greeting": {
        "es": "Estimado equipo de selección de [EMPRESA]:",
        "en": "Dear [COMPANY] hiring team,",
    },
    "letters.default.closing": {
        "es": "Gracias por su tiempo y consideración. Quedo a disposición para conversar "
        "sobre el puesto de [PUESTO].",
        "en": "Thank you for your time and consideration. I would welcome the chance to "
        "talk about the [ROLE] position.",
    },
    "letters.default.sign_off": {
        "es": "Atentamente,\n{name}",
        "en": "Kind regards,\n{name}",
    },
    "letters.autogenerate_template_hint": {
        "es": "Una llamada de pago: redacta ambos párrafos con el material de esta línea. "
        "Reemplaza lo que hay en los campos y no se guarda nada hasta que pulses Guardar.",
        "en": "One paid call: drafts both paragraphs from this role's material. It replaces "
        "what is in the fields and nothing is saved until you press Save.",
    },
    "letters.draft_notice": {
        "es": "Borrador cargado en los campos. Revísalo y pulsa Guardar: todavía no se "
        "ha guardado nada.",
        "en": "Draft loaded into the fields. Review it and press Save: nothing has been "
        "saved yet.",
    },
    "letters.draft_violations": {
        "es": "Este párrafo no pasó una comprobación. Puedes editarlo y guardarlo: lo "
        "que guardes es tu texto.",
        "en": "This paragraph failed a check. You can edit and save it: what you save is "
        "your text.",
    },
    "letters.undo": {"es": "Deshacer", "en": "Undo"},
    "generate.violation.length": {
        "es": "El párrafo no tiene la extensión pedida.",
        "en": "The paragraph is not the requested length.",
    },
    "generate.violation.shape": {
        "es": "El párrafo de logros debe ser uno solo.",
        "en": "The achievements block must be one paragraph.",
    },
    # N8.4: the letter written for one application.
    "letters.letter_title": {"es": "Carta de presentación", "en": "Cover letter"},
    "letters.letter_intro": {
        "es": "La línea ya trae su carta. Escribe o autogenera el párrafo de interés de esta "
        "oferta, revisa la carta completa y guárdala.",
        "en": "The role already has its letter. Write or autogenerate the paragraph of "
        "interest for this posting, review the full letter and save it.",
    },
    "letters.letter_risk": {"es": "Riesgo", "en": "Risk"},
    "letters.picker_intro": {
        "es": "Este análisis no tiene línea de carrera. Elige la línea para la carta (no cambia "
        "el análisis).",
        "en": "This analysis has no target role. Choose the role for the letter (it does "
        "not change the analysis).",
    },
    "letters.picker_label": {"es": "Línea de carrera", "en": "Target role"},
    "letters.picker_submit": {"es": "Usar esta línea", "en": "Use this role"},
    "letters.picker_none": {
        "es": "No tienes líneas de carrera activas: crea una para escribir la carta.",
        "en": "You have no active target roles: create one to write the letter.",
    },
    "letters.language_notice": {
        "es": "Este aviso está en {x} y tu línea de carrera está en {y}; la carta va en {y}.",
        "en": "This posting is in {x} and your target role is in {y}; the letter is in {y}.",
    },
    "letters.need_blocks": {
        "es": "Faltan los bloques comunes en {name}.",
        "en": "The common blocks in {name} are missing.",
    },
    "letters.go_cartas": {"es": "Ir a Cartas", "en": "Go to Letters"},
    "letters.need_template": {
        "es": "La línea «{track}» no tiene carta en {name}.",
        "en": "The role “{track}” has no letter in {name}.",
    },
    "letters.create_track_letter": {
        "es": "Crear carta de la línea",
        "en": "Create the role's letter",
    },
    "letters.several_note": {
        "es": "Esta línea tiene varias cartas y se usa la primera. Elige una en Cartas:",
        "en": "This role has several letters and the first one is used. Choose one in Letters:",
    },
    "letters.preview_title": {"es": "Así se lee la carta", "en": "How the letter reads"},
    "letters.bridge_label": {"es": "Párrafo de interés", "en": "Paragraph of interest"},
    "letters.bridge_generate": {
        "es": "Autogenerar párrafo de interés",
        "en": "Autogenerate paragraph of interest",
    },
    "letters.bridge_another": {
        "es": "Otra versión ({n} de 5)",
        "en": "Another version ({n} of 5)",
    },
    "letters.bridge_another_plain": {"es": "Otra versión", "en": "Another version"},
    "letters.bridge_limit": {"es": "Llegaste a 5 versiones.", "en": "You reached 5 versions."},
    "letters.bridge_marker": {"es": "[párrafo de interés]", "en": "[paragraph of interest]"},
    "letters.bridge_version": {"es": "Versión {n} · {angle}", "en": "Version {n} · {angle}"},
    "letters.bridge_failed": {
        "es": "No se pudo escribir un párrafo que cumpla las reglas.",
        "en": "A paragraph that follows the rules could not be written.",
    },
    "letters.soft.sentences": {
        "es": "{n} frases: el máximo es 4.",
        "en": "{n} sentences: the maximum is 4.",
    },
    "letters.soft.words": {
        "es": "{n} palabras: el máximo es 90.",
        "en": "{n} words: the maximum is 90.",
    },
    "letters.soft.banned": {
        "es": "Usa una frase de plantilla: «{phrase}».",
        "en": "Uses a template phrase: “{phrase}”.",
    },
    "letters.full_label": {"es": "Carta completa", "en": "Full letter"},
    "letters.full_edited": {
        "es": "Editaste la carta completa; el párrafo ya no se actualiza aquí.",
        "en": "You edited the full letter; the paragraph no longer updates it here.",
    },
    "letters.reassemble": {"es": "Volver a montar", "en": "Reassemble"},
    "letters.check_caption_generated": {
        "es": "para el texto generado",
        "en": "for the generated text",
    },
    "letters.check_caption_saved": {
        "es": "para la carta guardada",
        "en": "for the saved letter",
    },
    "letters.letter_saved_notice": {"es": "Carta guardada.", "en": "Letter saved."},
    "letters.letter_save": {"es": "Guardar carta", "en": "Save letter"},
    # F8.5: the checklist, deterministic and beside the letter.
    "letters.check.placeholders": {
        "es": "Sin marcadores pendientes",
        "en": "No placeholders left",
    },
    "letters.check.title": {
        "es": "Aparece el título exacto del aviso",
        "en": "The posting's exact title appears",
    },
    "letters.check.company": {"es": "Se nombra la empresa", "en": "The company is named"},
    "letters.check.length": {"es": "Una página (≤ 420 palabras)", "en": "One page (≤ 420 words)"},
    "letters.check.facts": {
        "es": "Cada dato de la empresa está atribuido",
        "en": "Every company fact is attributed",
    },
    "letters.check.language": {
        "es": "El idioma de la carta es el de la línea",
        "en": "The letter's language is the role's",
    },
    "applications.letter_mark": {"es": "carta", "en": "letter"},
    "letters.check.banned": {
        "es": "Sin frases de plantilla de IA",
        "en": "No AI-template phrasing",
    },
    "letters.check.sentences": {
        "es": "El párrafo de interés tiene 4 frases o menos",
        "en": "The paragraph of interest has 4 sentences or fewer",
    },
    "report.letter_link": {"es": "Escribir la carta", "en": "Write the letter"},
    "letters.placeholders": {"es": "Marcadores", "en": "Placeholders"},
    "letters.placeholders_hint": {
        "es": "Se rellenan al montar la carta, en cualquiera de los dos idiomas: {list}.",
        "en": "Filled in when the letter is assembled, in either language: {list}.",
    },
    "letters.placeholder.role": {"es": "[PUESTO] / [ROLE]", "en": "[PUESTO] / [ROLE]"},
    "letters.placeholder.company": {"es": "[EMPRESA] / [COMPANY]", "en": "[EMPRESA] / [COMPANY]"},
    "letters.placeholder.area": {"es": "[ÁREA] / [AREA]", "en": "[ÁREA] / [AREA]"},
    "letters.placeholder.date": {"es": "[FECHA] / [DATE]", "en": "[FECHA] / [DATE]"},
    # F2.8: Eliminar is permanent. Every delete goes through a confirmation screen
    # that states its consequences in numbers before anything happens.
    "delete.title": {"es": "¿Eliminar para siempre?", "en": "Delete permanently?"},
    "delete.impact.resume": {
        "es": (
            "Se eliminarán el archivo del CV y su borrador. Aportó {bullets} bullets, que se "
            "conservan salvo que marques la casilla. {bullets_unknown} bullets tienen procedencia "
            "desconocida y la casilla nunca las elimina. {analyses} análisis hechos sobre este "
            "CV se conservan con el nombre del archivo, pero ya no se podrá volver a puntuar "
            "sobre él."
        ),
        "en": (
            "The archived CV file and its draft will be deleted. It contributed {bullets} "
            "bullets, which are kept unless you tick the box. {bullets_unknown} bullets have "
            "unknown provenance and the box never deletes those. {analyses} analyses made on "
            "this CV are kept with the file's name, but nothing can be scored on it again."
        ),
    },
    "delete.impact.role": {
        "es": (
            "Se eliminarán el puesto, sus {bullets} bullets y sus {revisions} revisiones. Quedan "
            "{stories} historias con el enlace al puesto vacío."
        ),
        "en": (
            "The role, its {bullets} bullets and their {revisions} revisions will be deleted. "
            "{stories} stories stay with the role link cleared."
        ),
    },
    "delete.impact.bullet": {
        "es": "El bullet está en {tracks} líneas y citado por {analyses} análisis; los análisis "
        "conservan su copia. Se eliminan además sus {story_links} enlaces a historias y sus "
        "{revisions} revisiones.",
        "en": (
            "The bullet is in {tracks} tracks and cited by {analyses} analyses; the analyses "
            "keep their copy. Its {story_links} story links and its {revisions} revisions go "
            "too."
        ),
    },
    "delete.impact.skill": {
        "es": "«{skill}» saldrá de tu pool y de {tracks} líneas. El vocabulario compartido no se "
        "toca.",
        "en": "“{skill}” leaves your pool and {tracks} tracks. The shared vocabulary is untouched.",
    },
    "delete.impact.summary": {
        "es": "Se eliminará el resumen del pool. {tracks} líneas pierden esa casilla.",
        "en": "The pool summary will be deleted. {tracks} tracks lose that slot.",
    },
    "delete.impact.track": {
        "es": "Se eliminarán la línea y su selección de {selection} bullets. {analyses} análisis "
        "conservan el nombre de la línea.",
        "en": (
            "The track and its selection of {selection} bullets will be deleted. {analyses} "
            "analyses keep the track name."
        ),
    },
    "delete.impact.story": {
        "es": "Se eliminarán la historia y sus {links} enlaces a bullets.",
        "en": "The story and its {links} bullet links will be deleted.",
    },
    "delete.impact.letter": {
        "es": "Se eliminará la plantilla.",
        "en": "The template will be deleted.",
    },
    "delete.impact.application": {
        "es": (
            "Se eliminará el análisis almacenado y sus {application_attempts} intentos. "
            "Los ficheros del golden set viven fuera de la base de datos."
        ),
        "en": (
            "The stored analysis and its {application_attempts} attempts will be deleted. "
            "Golden-set files live outside the database."
        ),
    },
    "delete.impact.everything": {
        "es": "Se eliminará todo lo del perfil: {resumes} CV, {roles} puestos, {bullets} bullets, "
        "{summaries} resúmenes, {tracks} líneas, {stories} historias, {letter_templates} "
        "plantillas, {applications} análisis, {application_attempts} intentos y {skills} "
        "habilidades del pool. Se vaciarán {ledger_redacted} respuestas personales del registro "
        "de modelos, conservando tokens y coste. Tu cuenta y tu fila de perfil se quedan, vacías.",
        "en": (
            "Everything in the profile goes: {resumes} CVs, {roles} roles, {bullets} bullets, "
            "{summaries} summaries, {tracks} tracks, {stories} stories, {letter_templates} "
            "templates, {applications} analyses, {application_attempts} attempts and {skills} "
            "pool skills. {ledger_redacted} personal answers in the model-call ledger are "
            "blanked, keeping tokens and cost. Your login and your profile row stay, blanked."
        ),
    },
    "delete.unattributable": {
        "es": (
            "{count} llamadas del registro se escribieron sin profile_id y no se pueden "
            "atribuir; para esas sigue siendo herramienta del operador "
            "`llm_costs.py purge --hash`."
        ),
        "en": (
            "{count} ledger rows were written before profile_id existed and cannot be "
            "attributed; the operator's `llm_costs.py purge --hash` remains the tool for "
            "those."
        ),
    },
    "delete.cv_option": {
        "es": "Eliminar también los bullets que solo aportó este CV.",
        "en": "Also delete the bullets only this CV contributed.",
    },
    "delete.typed_label": {
        "es": "Escribe ELIMINAR para confirmar.",
        "en": "Type ELIMINAR to confirm.",
    },
    "delete.typed_mismatch": {
        "es": "La palabra no coincide: escribe ELIMINAR.",
        "en": "The word does not match: type ELIMINAR.",
    },
    "profile.skills_pool": {"es": "Habilidades (pool)", "en": "Skills (pool)"},
    "profile.skills_none": {"es": "El pool está vacío.", "en": "The pool is empty."},
    "profile.delete_all": {"es": "Eliminar todo", "en": "Delete everything"},
    "profile.delete_all_hint": {
        "es": "Elimina todo lo del perfil: CV, puestos, bullets, resúmenes, líneas, historias, "
        "plantillas, análisis y las respuestas personales del registro de modelos. Tu cuenta y tu "
        "fila de perfil se quedan, vacías.",
        "en": (
            "Deletes everything in the profile: CVs, roles, bullets, summaries, tracks, "
            "stories, templates, analyses and the personal answers in the model-call ledger. "
            "Your login and your profile row stay, blanked."
        ),
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
    # F2.9: a chip the vocabulary does not know is kept on the bullet and labelled
    # with this, so the user can see it is stored and not yet counted.
    "vocabulary.pending": {
        "es": "pendiente de vocabulario",
        "en": "pending vocabulary",
    },
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
    # The drop zone states the formats and the size; this keeps the language note.
    "import.file_hint": {
        "es": "Tu CV puede estar en español o en inglés.",
        "en": "Your CV can be in Spanish or English.",
    },
    "import.track_hint": {
        "es": "La experiencia con la que piensas usar este currículum. Si lo dejas vacío, la "
        "importación crea una línea de carrera con el nombre del archivo.",
        "en": "The track you intend this résumé for. Leave it empty and the import "
        "creates a track named after the file.",
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
    "import.discard": {"es": "Ocultar", "en": "Hide"},
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
    # F5.1.1: the location view — the page with the finding's boxes outlined, and, for
    # the three checks where the characters are the only way to act, what each box says.
    "import.show_where": {"es": "Mostrarme dónde", "en": "Show me where"},
    "import.location_pdf_only": {
        "es": "La vista de ubicación solo está disponible para PDF.",
        "en": "The location view is only available for PDF.",
    },
    "import.location_title": {"es": "Dónde está", "en": "Where it is"},
    # F11.7: a CV saved from an attempt has no file, so there is no page to show.
    # F11.7: "Subir a esta línea", the CV an attempt becomes, and what to do next.
    "attempt.save_cv": {"es": "Subir a esta línea", "en": "Save to this track"},
    "attempt.save_cv.name": {
        "es": "Intento {n} — {title}",
        "en": "Attempt {n} — {title}",
    },
    "attempt.save_cv.title": {"es": "CV guardado en la línea", "en": "CV saved to the track"},
    "attempt.save_cv.done": {
        "es": "«{name}» es ahora un CV de la línea «{track}», el más reciente.",
        "en": "“{name}” is now a CV of the track “{track}”, the newest one.",
    },
    "attempt.save_cv.exists": {
        "es": "Este intento ya estaba guardado como CV de la línea «{track}»: «{name}».",
        "en": "This attempt was already saved as a CV of the track “{track}”: “{name}”.",
    },
    "attempt.save_cv.no_file": {
        "es": "El archivo no se conservó (los intentos nunca lo guardan). «Archivo original» "
        "lo dirá; si quieres verlo, impórtalo con Importar CV.",
        "en": "The file was not kept (attempts never store it). “Original file” will say so; "
        "to see it, import it with Import CV.",
    },
    "attempt.save_cv.incorporate": {
        "es": "Incorporar también su contenido a mi material",
        "en": "Also incorporate its content into my material",
    },
    "attempt.save_cv.incorporate_hint": {
        "es": "Guardar el CV no cambia tu material: eso es la revisión de siempre.",
        "en": "Saving the CV does not change your material: that is the usual review.",
    },
    "attempt.save_cv.analyse": {"es": "Analizar con este CV", "en": "Analyse with this CV"},
    "attempt.save_cv.analyse_hint": {
        "es": "Una nueva puntuación de la misma oferta (hasta 2 llamadas).",
        "en": "A new analysis of the same posting (up to 2 calls).",
    },
    "attempt.save_cv.unavailable": {
        "es": "Este intento no se puede subir a una línea: no está terminado, su borrador se "
        "descartó o la línea ya no existe.",
        "en": "This attempt cannot be saved to a track: it is not finished, its draft was "
        "discarded or the track no longer exists.",
    },
    "analyze.reanalyse_no_track": {
        "es": "Esta oferta se analizó sin línea de carrera: elige una línea y uno de sus CV.",
        "en": "This posting was analysed without a track: choose a track and one of its CVs.",
    },
    "import.file_not_kept": {
        "es": "Este CV se guardó desde un intento: el archivo no se conservó, así que no "
        "hay página que mostrar. Impórtalo con Importar CV si quieres verlo.",
        "en": "This CV was saved from an attempt: the file was not kept, so there is no "
        "page to show. Import it with Import CV if you want to see it.",
    },
    "import.location_hint": {
        "es": "Los recuadros marcan lo que el chequeo señaló. Se lee del archivo "
        "original al abrir esta página; no se guarda en ningún sitio.",
        "en": "The boxes mark what the check flagged. It is read from the original "
        "file when this page opens; it is stored nowhere.",
    },
    "import.location_characters": {
        "es": "Caracteres dentro de los recuadros",
        "en": "Characters inside the boxes",
    },
    "import.location_box": {"es": "Recuadro", "en": "Box"},
    "import.location_empty_box": {
        "es": "— sin caracteres legibles —",
        "en": "— no readable characters —",
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
        "anotación: la evidencia y la puntuación leen los bullets.",
        "en": "Canonical vocabulary names, comma-separated. Annotation only: evidence "
        "and scoring read the bullets.",
    },
    "import.roles": {"es": "Puestos", "en": "Roles"},
    "import.bullets_of": {"es": "Bullets", "en": "Bullets"},
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
        "es": "Los bullets de un puesto nuevo solo entran si el puesto entra.",
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
    "import.track_label": {"es": "Línea de carrera", "en": "Track"},
    "import.merge_track_hint": {
        "es": "El documento se guarda en una línea de carrera con este nombre. Si ya está "
        "asignado a una línea, se une a esa y este nombre no se usa.",
        "en": "The document is saved in a track with this name. If it is already "
        "assigned to one, it joins that track and this name is not used.",
    },
    "import.track_created": {
        "es": "Línea de carrera creada: {name}",
        "en": "Track created: {name}",
    },
    "import.track_view": {"es": "Ver la línea de carrera", "en": "View the track"},
    "import.track_join": {
        "es": "Los bullets de este documento se unirán a «{name}».",
        "en": "The bullets from this document will join «{name}».",
    },
    "import.track_joined": {
        "es": "Bullets añadidos a «{name}»: {count}.",
        "en": "Bullets added to «{name}»: {count}.",
    },
    "import.track_of_document": {
        "es": "Línea de carrera de este documento: {name}",
        "en": "This document's track: {name}",
    },
    "import.track_bullets_added": {
        "es": "Bullets unidos a la línea",
        "en": "Bullets joined to the track",
    },
    "import.track_skills_added": {
        "es": "Habilidades unidas a la línea",
        "en": "Skills joined to the track",
    },
    "import.track_headline_filled": {
        "es": "Titular: rellenado desde el documento.",
        "en": "Headline: filled in from this document.",
    },
    "import.track_headline_kept": {
        "es": "Titular: sin tocar, la línea de carrera ya tenía uno.",
        "en": "Headline: left alone, the track already had one.",
    },
    "import.headline_not_set": {
        "es": "Titular no establecido: {count} caracteres, límite {limit}",
        "en": "headline not set: {count} characters, limit {limit}",
    },
    "import.track_summary_filled": {
        "es": "Resumen: rellenado desde el documento.",
        "en": "Summary: filled in from this document.",
    },
    "import.track_summary_kept": {
        "es": "Resumen: sin tocar, la línea de carrera ya tenía uno.",
        "en": "Summary: left alone, the track already had one.",
    },
    "import.merge_submit": {"es": "Importar la selección", "en": "Import the selection"},
    # F4.2: the same CV in the other language, imported as a translation.
    "import.translate_offer": {
        "es": "Este CV parece la versión en el otro idioma de tu línea de carrera",
        "en": "This CV looks like the other-language version of your track",
    },
    "import.translate_offer_hint": {
        "es": "Importar como traducción rellena las columnas vacías de los bullets y "
        "el título que ya tienes en lugar de crear un currículum aparte.",
        "en": "Importing as a translation fills the empty columns of the bullets and "
        "the title you already have instead of creating a second résumé.",
    },
    "import.translate_submit": {
        "es": "Importar como traducción",
        "en": "Import as translation",
    },
    "import.translate_title": {
        "es": "Importar como traducción",
        "en": "Import as translation",
    },
    "import.translate_intro": {
        "es": "El documento está en {document} y tu línea de carrera está en {track}. Empareja "
        "los bullets que dicen lo mismo; lo que no empareje entra abajo como candidato nuevo.",
        "en": "The document is in {document} and your track is in {track}. Pair the "
        "bullets that say the same thing; whatever does not pair enters below as a new "
        "candidate.",
    },
    "import.translate_hint": {
        "es": "Nada existente se sobrescribe: una columna que ya tiene texto se "
        "conserva tal cual.",
        "en": "Nothing existing is overwritten: a column that already holds text keeps "
        "it as it is.",
    },
    "import.translate_pairs": {"es": "Bullets emparejados", "en": "Paired bullets"},
    "import.translate_pairs_hint": {
        "es": "Las dos columnas son el mismo bullet en cada idioma. Desmarca lo que no "
        "quieras escribir.",
        "en": "The two columns are the same bullet in each language. Untick whatever "
        "you do not want written.",
    },
    "import.translate_fills": {
        "es": "Rellena el texto en {language}.",
        "en": "Fills the {language} text.",
    },
    "import.translate_kept_hint": {
        "es": "Ya tiene texto en el otro idioma: se conserva, no se sobrescribe.",
        "en": "It already has the other language's text: it is kept, not overwritten.",
    },
    "import.translate_no_pairs": {
        "es": "Ningún bullet dice lo mismo en los dos idiomas.",
        "en": "No bullet says the same thing in both languages.",
    },
    "import.translate_new": {"es": "Entra como nuevo", "en": "Enters as new"},
    "import.translate_new_hint": {
        "es": "Los bullets sin pareja y los puestos que no coinciden siguen las reglas "
        "de F2.5.",
        "en": "Unpaired bullets and roles that do not match follow F2.5's rules.",
    },
    "import.translate_apply": {
        "es": "Aplicar la traducción",
        "en": "Apply the translation",
    },
    "import.translate_failed": {
        "es": "No se pudo emparejar los bullets: el modelo no devolvió una respuesta "
        "utilizable. Puedes importar el documento como una selección normal.",
        "en": "The bullets could not be paired: the model did not return a usable "
        "answer. You can import the document as an ordinary selection.",
    },
    "import.translations_filled": {
        "es": "Traducciones escritas",
        "en": "Translations filled",
    },
    "import.translations_kept": {
        "es": "Traducciones conservadas",
        "en": "Translations kept",
    },
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
    "import.bullets_created": {"es": "Bullets nuevos", "en": "Bullets created"},
    "import.bullets_updated": {"es": "Bullets actualizados", "en": "Bullets updated"},
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
    "import.go_roles": {"es": "Ver mi experiencia", "en": "See my experience"},
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
    "gate.check.image_bullets": {"es": "Bullets como imagen", "en": "Image-based bullets"},
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
        "es": "Página {page}: {count} bullets como imagen.",
        "en": "Page {page}: {count} bullets drawn as images.",
    },
    "gate.detail.non_embedded_fonts": {
        "es": "Fuentes sin incrustar: {fonts}.",
        "en": "Fonts without embedding: {fonts}.",
    },
    # §12.1's report layout (queue U3): the fit definition, the disclosure summaries and
    # the counts each one carries. Singular forms are `_one`; the template picks.
    "report.fit_definition": {
        "es": "Qué tan bien este CV cubre lo que pide la oferta; no es la probabilidad "
        "de ser contratado.",
        "en": "How well this CV fits what this posting asks for; not the probability of "
        "being hired.",
    },
    "report.see_detail": {"es": "Ver detalle", "en": "See detail"},
    "report.ceiling_exact": {"es": "exacto", "en": "exact"},
    "report.experience_required": {
        "es": "Requeridos: {required} años · relevantes: {relevant} · totales: {held}",
        "en": "Required: {required} years · relevant: {relevant} · total: {held}",
    },
    "report.experience_tasks": {
        "es": "Tareas de la oferta cubiertas: {covered} de {total}",
        "en": "Posting tasks covered: {covered} of {total}",
    },
    "recall.appear_summary": {
        "es": "Apareces en {passed} de {total} búsquedas",
        "en": "You appear in {passed} of {total} searches",
    },
    "report.ats.none": {"es": "Sin bloqueos", "en": "No blockers"},
    "report.ats.blockers_one": {"es": "1 bloqueo", "en": "1 blocker"},
    "report.ats.blockers": {"es": "{n} bloqueos", "en": "{n} blockers"},
    "report.ats.count_warning": {"es": "Avisos {n}", "en": "Warnings {n}"},
    "report.ats.count_info": {"es": "Informativos {n}", "en": "Info {n}"},
    "report.ats.count_not_run": {"es": "Sin ejecutar {n}", "en": "Not run {n}"},
    "report.ats.count_none": {"es": "Sin hallazgos", "en": "No findings"},
    "report.before.gaps_one": {"es": "{n} brecha decisiva", "en": "{n} decisive gap"},
    "report.before.gaps": {"es": "{n} brechas decisivas", "en": "{n} decisive gaps"},
    "report.before.warnings_one": {"es": "{n} advertencia", "en": "{n} warning"},
    "report.before.warnings": {"es": "{n} advertencias", "en": "{n} warnings"},
    "report.before.transfer_one": {
        "es": "{n} requisito cubierto por transferencia",
        "en": "{n} requirement covered by transfer",
    },
    "report.before.transfer": {
        "es": "{n} requisitos cubiertos por transferencia",
        "en": "{n} requirements covered by transfer",
    },
    "report.before.gaps_toggle": {"es": "Brechas", "en": "Gaps"},
    "report.before.gaps_order": {
        "es": "la más decisiva primero",
        "en": "most decisive first",
    },
    "report.before.warning_toggle": {"es": "Advertencia", "en": "Warning"},
    "report.before.no_warning": {"es": "Sin advertencias.", "en": "No warnings."},
    "report.before.no_transfer": {
        "es": "Ningún requisito se cubre por transferencia.",
        "en": "No requirement is covered by transfer.",
    },
    # §12.1 item 5 (queue U4): the requirements as buttons, with their summary.
    "report.req.n_one": {"es": "{n} requisito", "en": "{n} requirement"},
    "report.req.n": {"es": "{n} requisitos", "en": "{n} requirements"},
    "report.req.covered_one": {"es": "{n} cubierto", "en": "{n} covered"},
    "report.req.covered": {"es": "{n} cubiertos", "en": "{n} covered"},
    "report.req.gaps_one": {"es": "{n} brecha", "en": "{n} gap"},
    "report.req.gaps": {"es": "{n} brechas", "en": "{n} gaps"},
    "report.req.hint": {
        "es": "Toca uno para ver la evidencia.",
        "en": "Select one to see its evidence.",
    },
    "report.req.level_of": {"es": "nivel {level} de 3", "en": "level {level} of 3"},
    # F11.3/F11.8: which file an analysis scored, and the old analyses that scored a track.
    "report.cv": {"es": "CV analizado: {name}", "en": "Analysed CV: {name}"},
    "report.cv_deleted": {"es": "CV eliminado: {name}", "en": "CV deleted: {name}"},
    "report.cv_legacy": {
        "es": "Analizado sobre la línea (antes de elegir CV)",
        "en": "Analysed on the track (before choosing a CV)",
    },
    "report.cv_edited": {
        "es": "El CV se editó después de este análisis; las cifras son las de entonces.",
        "en": "The CV was edited after this analysis; the figures are the ones from then.",
    },
    "report.reanalyse_label": {"es": "Analizar con otro CV", "en": "Analyse with another CV"},
    "report.reanalyse": {"es": "Re-analizar", "en": "Re-analyse"},
    "report.reanalyse_hint": {
        "es": "re-analizar (hasta 2 llamadas)",
        "en": "re-analyse (up to 2 calls)",
    },
    # F11.5: the requirement note, and the section summary's count of them. "Estimado":
    # it is the Skills ceiling's rule, not a grade, and it never moves the score.
    "report.req.note": {
        "es": "Con tu material: nivel {level} (estimado) — bullet «{text}» de {role}, "
        "no está en este CV",
        "en": "With your material: level {level} (estimated) — bullet “{text}” from {role}, "
        "not in this CV",
    },
    "report.req.note_equivalent": {
        "es": "Con tu material: nivel {level} (estimado, equivalente) — bullet «{text}» de "
        "{role}, no está en este CV",
        "en": "With your material: level {level} (estimated, equivalent) — bullet “{text}” "
        "from {role}, not in this CV",
    },
    "report.req.could_rise_one": {
        "es": "{n} podría subir con tu material",
        "en": "{n} could rise with your material",
    },
    "report.req.could_rise": {
        "es": "{n} podrían subir con tu material",
        "en": "{n} could rise with your material",
    },
    # §12.1 item 6 (queue U5): the recommendations in one column, grouped under headings
    # with counts. `add_file` is the same group worded for a document (an attempt).
    "report.advice.group.promote": {"es": "Ordena tus bullets", "en": "Order your bullets"},
    "report.advice.group.add": {"es": "Añade a esta línea", "en": "Add to this track"},
    "report.advice.group.add_file": {
        "es": "Añade a tu documento",
        "en": "Add to your document",
    },
    "report.advice.group.skills": {"es": "Habilidades", "en": "Skills"},
    "report.advice.group.search": {"es": "Búsquedas y título", "en": "Searches and title"},
    "report.advice.group.language": {"es": "Idioma", "en": "Language"},
    "report.advice.group.other": {"es": "Otras", "en": "Other"},
    "report.advice.skills_card": {
        "es": "Añade a las habilidades de la línea: la oferta las pide y las tienes evidenciadas.",
        "en": "Add to the track's skills: the posting asks for them and you have them "
        "evidenced.",
    },
    "report.advice.file.skills_card": {
        "es": "Añade a las habilidades de tu documento: la oferta las pide y las tienes "
        "evidenciadas.",
        "en": "Add to your document's skills: the posting asks for them and you have them "
        "evidenced.",
    },
    "report.advice.chip_position": {"es": "{position} → top 3", "en": "{position} → top 3"},
    "report.advice.see_more": {"es": "Ver más", "en": "See more"},
    "report.advice.see_all": {"es": "Ver todas ({n})", "en": "See all ({n})"},
    # F7.5: the Keywords card. Every item names its basis and where it would go; the card
    # writes nothing, and says it is computed from the material as it is now.
    "report.keywords.title": {"es": "Palabras clave que faltan", "en": "Missing keywords"},
    "report.keywords.intro": {
        "es": "Palabras de la oferta que faltan en esta línea y dónde ponerlas, solo si es verdad.",
        "en": "Keywords from the posting that this track lacks, and where to put them, only if "
        "true.",
    },
    "report.keywords.intro_file": {
        "es": "Palabras de la oferta que faltan en tu documento y dónde ponerlas, solo si es "
        "verdad.",
        "en": "Keywords from the posting that your document lacks, and where to put them, only "
        "if true.",
    },
    "report.keywords.calculated": {
        "es": "calculado con tu material actual",
        "en": "calculated from your current material",
    },
    "report.keywords.basis.pool": {"es": "Lo tienes", "en": "You have it"},
    "report.keywords.basis.bullet": {
        "es": "Un bullet tuyo lo respalda",
        "en": "One of your bullets backs it",
    },
    "report.keywords.basis.equivalent": {"es": "Equivalente", "en": "Equivalent"},
    "report.keywords.basis.inferred": {
        "es": "Probable — solo si es verdad",
        "en": "Probable — only if true",
    },
    "report.keywords.priority.must_have": {"es": "Imprescindible", "en": "Must-have"},
    "report.keywords.priority.nice_to_have": {"es": "Deseable", "en": "Nice-to-have"},
    "report.keywords.priority.other": {"es": "Palabra clave", "en": "Keyword"},
    "report.keywords.where.skills": {"es": "Habilidades", "en": "Skills"},
    "report.keywords.where.skills_file": {
        "es": "Tu sección Habilidades",
        "en": "Your Skills section",
    },
    "report.keywords.where.bullet": {"es": "Un bullet tuyo", "en": "One of your bullets"},
    "report.keywords.hint.pool": {
        "es": "ya figura en tu material; añádela a tu lista de habilidades.",
        "en": "it is already in your material; add it to your skills list.",
    },
    "report.keywords.hint.pool_file": {
        "es": "ya figura en tu material; añádela a tu sección Habilidades.",
        "en": "it is already in your material; add it to your Skills section.",
    },
    "report.keywords.hint.bullet_use": {
        "es": "tu bullet «{text}» lo describe sin nombrarlo: usa la palabra de la oferta en él.",
        "en": "your bullet “{text}” describes it without naming it: use the posting's word "
        "in it.",
    },
    "report.keywords.hint.bullet_add": {
        "es": "tu bullet «{text}» ya lo dice; inclúyelo en esta línea.",
        "en": "your bullet “{text}” already says it; include it in this track.",
    },
    "report.keywords.hint.bullet_add_file": {
        "es": "tu bullet «{text}» ya lo dice; añádelo a tu documento.",
        "en": "your bullet “{text}” already says it; add it to your document.",
    },
    "report.keywords.hint.equivalent": {
        "es": "tienes {sibling}; añádela solo si de verdad la has usado.",
        "en": "you have {sibling}; add it only if you have really used it.",
    },
    "report.keywords.copy": {"es": "Copiar «{keyword}»", "en": "Copy “{keyword}”"},
    # F7.5 probable keywords: the button, and the pop-up behind it.
    "report.keywords.infer": {
        "es": "Sugerir más palabras clave probables",
        "en": "Suggest more probable keywords",
    },
    "report.keywords.infer_no_model": {
        "es": "Para sugerir más palabras clave hace falta un modelo configurado.",
        "en": "Suggesting more keywords needs a model to be configured.",
    },
    "report.keywords.infer_none": {
        "es": "No queda ninguna palabra clave sin respaldo que sugerir.",
        "en": "No keyword without backing is left to suggest.",
    },
    "keywords.infer.title": {
        "es": "Sugerir más palabras clave probables",
        "en": "Suggest more probable keywords",
    },
    "keywords.infer.sends": {
        "es": "Se enviarán al modelo, sin tu nombre ni tus datos de contacto: las palabras "
        "clave sin respaldo ({n}), tus habilidades, tus bullets y tus puestos. Solo propone lo "
        "muy probable y no escribe nada en tu material.",
        "en": "Sent to the model, without your name or contact details: the keywords with no "
        "backing ({n}), your skills, your bullets and your roles. It only proposes what is highly "
        "probable and writes nothing to your material.",
    },
    "keywords.infer.sends_file": {
        "es": "Se enviarán al modelo, sin tu nombre ni tus datos de contacto: las palabras "
        "clave de tu documento sin respaldo ({n}), tus habilidades, tus bullets y tus puestos. "
        "Solo propone lo muy probable y no escribe nada en tu material.",
        "en": "Sent to the model, without your name or contact details: the keywords of "
        "your document with no backing ({n}), your skills, your bullets and your roles. It only "
        "proposes what is highly probable and writes nothing to your material.",
    },
    "keywords.infer.cost": {
        "es": "Es una llamada de pago, una sola por pulsación; si tu material no cambió, "
        "repetirla no cuesta nada. Abrir esta ventana tampoco.",
        "en": "It is one paid call per press; if your material has not changed, repeating it "
        "costs nothing. Opening this window costs nothing either.",
    },
    "keywords.infer.run": {"es": "Generar", "en": "Generate"},
    "keywords.infer.none_left": {
        "es": "No queda ninguna palabra clave sin respaldo que sugerir.",
        "en": "No keyword without backing is left to suggest.",
    },
    "keywords.infer.empty": {
        "es": "El modelo no encontró ninguna palabra clave lo bastante probable.",
        "en": "The model found no keyword probable enough.",
    },
    "keywords.infer.rests_on": {"es": "Se apoya en:", "en": "Rests on:"},
    "keywords.infer.support.skill": {"es": "habilidad", "en": "skill"},
    "keywords.infer.support.bullet": {"es": "bullet", "en": "bullet"},
    "keywords.infer.where": {"es": "Dónde ponerla:", "en": "Where to put it:"},
    "keywords.infer.where.existing": {
        "es": "en tu bullet «{text}»",
        "en": "in your bullet “{text}”",
    },
    "keywords.infer.where.new": {
        "es": "un bullet nuevo en «{role}»",
        "en": "a new bullet under “{role}”",
    },
    "keywords.infer.draft": {"es": "Borrador", "en": "Draft"},
    "keywords.infer.copy_draft": {"es": "Copiar el borrador", "en": "Copy the draft"},
    "keywords.infer.dropped_one": {
        "es": "{n} sugerencia descartada por no poder comprobarse.",
        "en": "{n} suggestion dropped because it could not be checked.",
    },
    "keywords.infer.dropped": {
        "es": "{n} sugerencias descartadas por no poder comprobarse.",
        "en": "{n} suggestions dropped because they could not be checked.",
    },
    "keywords.infer.writes_nothing": {
        "es": "Nada de esto se guarda: edita tu propio archivo, y solo si es verdad.",
        "en": "None of this is saved: edit your own file, and only if it is true.",
    },
    "report.keywords.unsupported_one": {
        "es": "{n} palabra clave no tiene respaldo en tu material: está en tus brechas.",
        "en": "{n} keyword has no backing in your material: it is in your gaps.",
    },
    "report.keywords.unsupported": {
        "es": "{n} palabras clave no tienen respaldo en tu material: están en tus brechas.",
        "en": "{n} keywords have no backing in your material: they are in your gaps.",
    },
    # §12.1 item 10 (queue U6): the desktop action rail and the phone's bottom bar.
    "report.actions.label": {"es": "Acciones", "en": "Actions"},
    "report.actions.try_cv": {
        "es": "Probar nueva versión del CV",
        "en": "Try a new CV version",
    },
    "report.actions.try_cv_short": {"es": "Probar nuevo CV", "en": "Try a new CV"},
    "report.actions.letter": {
        "es": "Escribir carta de presentación",
        "en": "Write a cover letter",
    },
    "report.actions.letter_short": {"es": "Escribir carta", "en": "Write letter"},
    "report.on_this_page": {"es": "En esta página", "en": "On this page"},
    # §12.3 — the line under a paid form's button while the provider works. Honest
    # ranges and a live counter; no invented steps.
    "progress.analyze": {
        "es": "Analizando la oferta… suele tardar 20–40 s",
        "en": "Analysing the posting… usually takes 20–40 s",
    },
    "progress.import": {
        "es": "Leyendo tu CV… suele tardar 20–40 s",
        "en": "Reading your CV… usually takes 20–40 s",
    },
    "progress.generate": {
        "es": "Generando la propuesta… suele tardar 10–30 s",
        "en": "Writing the proposal… usually takes 10–30 s",
    },
    "progress.letter": {
        "es": "Escribiendo la carta… suele tardar 10–30 s",
        "en": "Writing the letter… usually takes 10–30 s",
    },
    # §12.4 — the document drop zone shared by Importar CV and the attempt modal.
    "dropzone.prompt": {
        "es": "Arrastra tu CV aquí o elige un archivo",
        "en": "Drop your CV here or choose a file",
    },
    "dropzone.formats": {
        "es": ".docx o .pdf · máx. {mb} MB",
        "en": ".docx or .pdf · max {mb} MB",
    },
    "dropzone.release": {"es": "Suelta para subir", "en": "Drop to upload"},
    "dropzone.change": {"es": "Cambiar", "en": "Change"},
    "dropzone.one_file": {"es": "Suelta un solo archivo", "en": "Drop a single file"},
    "dropzone.bad_type": {
        "es": "Solo se aceptan archivos .docx o .pdf",
        "en": "Only .docx or .pdf files are accepted",
    },
    "dropzone.too_big": {
        "es": "El archivo supera los {mb} MB",
        "en": "The file is larger than {mb} MB",
    },
}


def t(key: str, lang: str | None = None, **values: object) -> str:
    entry = STRINGS.get(key)
    if entry is None:
        return key
    text = entry.get(lang or DEFAULT_LANG) or entry.get(DEFAULT_LANG) or key
    return text.format(**values) if values else text


def join_list(items: Sequence[str], lang: str | None = None) -> str:
    """A list of phrases as a sentence reads it: `a`, `a y b`, `a, b y c` (PRD 8).

    The conjunction is the language's own word, so a caller that concatenates its
    own "and" is wrong in one of the two languages — the reason this exists rather
    than a template filter.
    """
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return f"{', '.join(items[:-1])} {t('common.and', lang)} {items[-1]}"
