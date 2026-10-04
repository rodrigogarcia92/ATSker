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
        "es": "Evaluación de encaje entre tu currículum y una oferta",
        "en": "How well your résumé matches a job posting",
    },
    # Shell — the 64px icon rail of §12.1: three groups, nine links, and the account
    # controls. Vocabulario is not a rail destination; Perfil links to it.
    "nav.dashboard": {"es": "Inicio", "en": "Home"},
    "nav.analyze": {"es": "Analizar", "en": "Analyse"},
    "nav.applications": {"es": "Historial", "en": "History"},
    "nav.import": {"es": "Importar CV", "en": "Import CV"},
    "nav.tracks": {"es": "Puestos objetivo", "en": "Tracks"},
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
    # Shared
    "common.save": {"es": "Guardar", "en": "Save"},
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
        "es": "Pega el texto de la oferta. Se extraen los requisitos, se contrastan "
        "con tus bullets y el informe queda guardado.",
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
        "es": "No hay bullets activos: sin ellos no hay evidencia que citar y la "
        "cobertura será cero.",
        "en": "No active bullets: without them there is no evidence to cite and "
        "coverage will be zero.",
    },
    "analyze.track": {"es": "Puesto objetivo (opcional)", "en": "Track (optional)"},
    "analyze.track_none": {
        "es": "Sin puesto objetivo: todos los bullets activos",
        "en": "No track: every active bullet",
    },
    "analyze.track_hint": {
        "es": "Con un puesto objetivo, la puntuación usa solo sus bullets y, si lo "
        "tiene, su titular.",
        "en": "With a track, the score uses only its bullets and, when set, its headline.",
    },
    # F7.1: the recommendation, for the user who has not decided which track to apply
    # with. It only acts when no track is chosen.
    "analyze.recommend": {"es": "Recomendar puesto", "en": "Recommend a track"},
    "analyze.recommend_hint": {
        "es": "Puntúa la oferta contra tus puestos objetivo, hasta seis, y te dice "
        "cuál gana y por qué. Solo se usa si no eliges un puesto arriba.",
        "en": "Scores the posting against up to six of your tracks and says which one "
        "wins and why. Used only when no track is chosen above.",
    },
    "analyze.recommend_na": {
        "es": "No aplica: elegiste un puesto.",
        "en": "Not applicable: you chose a track.",
    },
    "analyze.recommend_off": {
        "es": "Sin puesto objetivo, al escribir la carta tendrás que elegir uno.",
        "en": "Without a target role, you'll pick one when you write the cover letter.",
    },
    # Application history (F9)
    "applications.title": {"es": "Historial", "en": "History"},
    "applications.new": {"es": "Analizar una oferta", "en": "Analyse a posting"},
    "applications.intro": {
        "es": "Cada análisis queda guardado con su puntuación, su puesto objetivo y su "
        "coste. Esta tabla es el conjunto de datos: con suficientes candidaturas dirá si "
        "las componentes predicen una respuesta.",
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
    "applications.track": {"es": "Puesto objetivo", "en": "Track"},
    "applications.score": {"es": "Encaje", "en": "Fit"},
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
        "es": "Las consultas que un reclutador escribiría en un ATS o en un portal, y "
        "si tu puesto objetivo aparecería en sus resultados. No entra en el Ajuste "
        "general: una consulta es una puerta, no un porcentaje.",
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
        "es": "Falla en «{term}»: no aparece ningún alias de este término en este puesto "
        "objetivo.",
        "en": "Fails on “{term}” — no alias of this term appears in this track.",
    },
    "recall.fail.present": {
        "es": "Falla en «{term}»: aparece en este puesto objetivo y la consulta lo "
        "excluye.",
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
        "es": "Encaje {score} · techo {ceiling}",
        "en": "Match {score} · ceiling {ceiling}",
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
        "es": "Esto es lo que el documento trae y tu base de datos no tiene. Nada se "
        "escribe hasta que confirmes, y ningún puesto se toca salvo que elijas uno.",
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
        "es": "Solo mi material (ningún puesto)",
        "en": "Only my material (no track)",
    },
    "attempt.incorporate.este": {"es": "Este puesto", "en": "This track"},
    "attempt.incorporate.otro": {"es": "Otro puesto", "en": "Another track"},
    "attempt.incorporate.nuevo": {"es": "Nuevo puesto", "en": "A new track"},
    "attempt.incorporate.new_name": {
        "es": "Nombre del nuevo puesto",
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
    # it states `attempt.limit`, which already says the maximum is reached.
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
        "es": "{delta} vs. análisis del puesto",
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
        "es": "Sin cambios respecto al análisis del puesto",
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
        "es": "El encaje ({job_match}) no llega al techo ({ceiling_low}) dentro del "
        "margen de {band}.",
        "en": "The match ({job_match}) does not reach the ceiling ({ceiling_low}) "
        "within the {band}-point band.",
    },
    "attempt.ready.match_target": {
        "es": "El encaje ({job_match}) no llega a tu objetivo ({target}).",
        "en": "The match ({job_match}) does not reach your target ({target}).",
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
    "report.track": {"es": "Puesto objetivo: {name}", "en": "Track: {name}"},
    "report.no_track": {
        "es": "Sin puesto objetivo: se puntuaron todos los bullets activos.",
        "en": "No track: every active bullet was scored.",
    },
    "report.sub_scores": {"es": "Componentes", "en": "Components"},
    # F7.1: the table the recommendation produces, above the components, with the
    # chosen track marked. The justification is a code-built line, not prose from a
    # model: the winner, the sub-score it leads on, and the track's own "when to use".
    "report.recommendation": {
        "es": "Recomendación de puesto",
        "en": "Track recommendation",
    },
    "report.recommendation.intro": {
        "es": "La oferta puntuada contra cada puesto objetivo candidato. La elegida es "
        "la que se guarda en esta aplicación.",
        "en": "The posting scored against each candidate track. The chosen one is what "
        "this application stores.",
    },
    "report.recommendation.track": {"es": "Puesto", "en": "Track"},
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
    "report.sub.semantic": {"es": "Encaje semántico", "en": "Semantic fit"},
    # §12.1: no weights are shown on the report page, so there is no word for one. The
    # calculation version is what the page names instead.
    "report.calculation": {"es": "Cálculo", "en": "Calculation"},
    "report.model": {"es": "Modelo", "en": "Model"},
    "report.calls_cost": {"es": "Llamadas y coste", "en": "Calls and cost"},
    "report.evidence_language": {"es": "Idioma de la evidencia", "en": "Evidence language"},
    "report.analyse_another": {
        "es": "Analizar con otro puesto",
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
        "es": "No se leyó ningún archivo en este análisis: el puesto no tiene un CV subido.",
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
        "es": "Encaje semántico del informe almacenado.",
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
        "es": "0 ausente · 1 mencionado · 2 aplicado · 3 demostrado. Cada nivel cita la "
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
        "es": "Mueve este bullet a las tres primeras del puesto: demuestra {requirement} "
        "y está en la posición {position}, con material más débil por encima.",
        "en": "Move this bullet into the track's first three: it demonstrates "
        "{requirement} and it sits at position {position}, with weaker material above.",
    },
    "report.advice.add_bullet": {
        "es": "Añade este bullet al puesto: demuestra {canonical}, que la oferta pide y "
        "el análisis no encontró.",
        "en": "Add this bullet to the track: it demonstrates {canonical}, which the "
        "posting asks for and the analysis did not find.",
    },
    "report.advice.surface_skill": {
        "es": "Añade {canonical} a las habilidades del puesto: la oferta lo pide y tú "
        "lo tienes demostrado.",
        "en": "Add {canonical} to the track's skills: the posting asks for it and you "
        "have it evidenced.",
    },
    "report.advice.fix_query": {
        "es": "La búsqueda «{query}» no te devolvería, y tienes un bullet que dice "
        "{canonical}: inclúyela en el puesto o usa sus palabras.",
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
    "generate.propose_summary": {
        "es": "Proponer resumen y habilidades",
        "en": "Propose a summary and skills",
    },
    # The provider call is a button on a POST, never a GET (F.0).
    "generate.run": {"es": "Generar propuesta", "en": "Generate proposal"},
    "generate.title": {
        "es": "Resumen y habilidades propuestos",
        "en": "Proposed summary and skills",
    },
    "generate.intro": {
        "es": "Una propuesta a partir de tu propio material. Nada se guarda hasta que "
        "aceptes, y al aceptar se vuelve a validar contra la base de datos.",
        "en": "A proposal built from your own material. Nothing is stored until you "
        "accept, and accepting validates it against the database again.",
    },
    "generate.current": {"es": "Ahora", "en": "Current"},
    "generate.proposed": {"es": "Propuesta", "en": "Proposed"},
    "generate.skills": {"es": "Habilidades", "en": "Skills"},
    "generate.empty_summary": {
        "es": "— sin resumen en este idioma —",
        "en": "— no summary in this language —",
    },
    "generate.use_in_track": {
        "es": "Usar en este puesto: {name}",
        "en": "Use in this track: {name}",
    },
    "generate.accept": {"es": "Aceptar", "en": "Accept"},
    "generate.back": {"es": "Volver al informe", "en": "Back to the report"},
    "generate.rejected": {
        "es": "La propuesta no pasó la validación y no se puede aceptar.",
        "en": "The proposal failed validation and cannot be accepted.",
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
    "tracks.title": {"es": "Puestos objetivo", "en": "Tracks"},
    "tracks.new": {"es": "Nuevo puesto objetivo", "en": "New track"},
    "tracks.intro": {
        "es": "Un puesto objetivo es un rol al que apuntas, con una selección "
        "ordenada de tus bullets. No copia contenido: el mismo bullet sirve a varios.",
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
    # F4.1/F8: the track's language is also the language of its cover letters.
    "tracks.lang_hint": {
        "es": "Las cartas de este puesto se escriben en este idioma.",
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
        "es": "El eje del propio puesto: riesgo, marketing, plataforma… Opcional.",
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
        "es": "Uno por idioma, tomado del fondo común de resúmenes o escrito aquí: uno "
        "escrito nuevo entra en el fondo y puede reusarlo otro puesto objetivo. El "
        "puesto referencia el fondo; no guarda texto propio.",
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
        "es": "Todavía no hay puestos objetivo. Crea el primero.",
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
        "es": "Desactivar conserva el puesto objetivo para los informes ya generados.",
        "en": "Deactivating keeps the track for reports already generated.",
    },
    # Summary pool (F2.7/F4.1)
    "summaries.edit": {"es": "Editar el resumen", "en": "Edit the summary"},
    "summaries.edit_hint": {
        "es": "Los resúmenes viven en un fondo común: editar aquí cambia el texto en "
        "todos los puestos objetivo que lo usen.",
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
    # N8.2: the blocks every letter shares, and the template's optional track link.
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
    "letters.templates_title": {"es": "Plantillas", "en": "Templates"},
    "letters.group_unlinked": {"es": "Sin puesto objetivo", "en": "No track"},
    "letters.track_link": {"es": "Puesto objetivo (opcional)", "en": "Track (optional)"},
    "letters.track_none": {"es": "— sin puesto —", "en": "— no track —"},
    # N8.3: the two reusable paragraphs, proposed from the track's own material.
    "letters.propose": {
        "es": "Proponer presentación y logros",
        "en": "Propose presentation and achievements",
    },
    "letters.propose_title": {
        "es": "Presentación y logros propuestos",
        "en": "Proposed presentation and achievements",
    },
    "letters.propose_intro": {
        "es": "Dos párrafos escritos a partir del material del puesto objetivo. Nada se "
        "guarda hasta que aceptes, y al aceptar se vuelve a validar.",
        "en": "Two paragraphs written from the track's own material. Nothing is stored "
        "until you accept, and accepting validates them again.",
    },
    "letters.propose_no_track": {
        "es": "Esta plantilla no está ligada a un puesto objetivo: sin uno no hay "
        "material del que escribir.",
        "en": "This template is not linked to a track: without one there is no material "
        "to write from.",
    },
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
        "es": "Una llamada para elegir plantilla y escribir tres puentes; el montaje es "
        "determinista y cambiar de plantilla o variante no vuelve a llamar al modelo.",
        "en": "One call to choose a template and write three bridges; assembly is "
        "deterministic, and switching template or variant does not call the model again.",
    },
    "letters.letter_no_candidates": {
        "es": "No hay plantillas en el idioma del aviso: créalas en Cartas.",
        "en": "No templates in the posting's language: create them in Letters.",
    },
    "letters.letter_no_settings": {
        "es": "Faltan los bloques comunes de ese idioma: escríbelos en Cartas.",
        "en": "The common blocks for that language are missing: write them in Letters.",
    },
    "letters.letter_reason": {"es": "Elegida porque", "en": "Chosen because"},
    "letters.letter_runner_up": {"es": "Alternativa", "en": "Runner-up"},
    "letters.letter_risk": {"es": "Riesgo", "en": "Risk"},
    "letters.letter_template": {"es": "Plantilla", "en": "Template"},
    "letters.letter_variant": {"es": "Variante", "en": "Variant"},
    "letters.letter_repeat_warning": {
        "es": "Repite un número del párrafo de logros de esta plantilla.",
        "en": "Repeats a number from this template's achievements paragraph.",
    },
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
        "es": "El idioma de la carta es el del aviso",
        "en": "The letter's language is the posting's",
    },
    "applications.letter_mark": {"es": "carta", "en": "letter"},
    "letters.letter_saved": {"es": "Carta guardada", "en": "Saved letter"},
    "letters.letter_missing_candidates_note": {
        "es": "Solo sobrevivieron {count} variantes; no se rellenan hasta tres.",
        "en": "Only {count} variants survived; three are never padded.",
    },
    "report.letter": {"es": "Carta de presentación", "en": "Cover letter"},
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
            "Se eliminarán el archivo del CV y su borrador. Aportó {bullets} balas, que se "
            "conservan salvo que marques la casilla. {bullets_unknown} balas tienen procedencia "
            "desconocida y la casilla nunca las elimina."
        ),
        "en": (
            "The archived CV file and its draft will be deleted. It contributed {bullets} "
            "bullets, which are kept unless you tick the box. {bullets_unknown} bullets have "
            "unknown provenance and the box never deletes those."
        ),
    },
    "delete.impact.role": {
        "es": (
            "Se eliminarán el puesto, sus {bullets} balas y sus {revisions} revisiones. Quedan "
            "{stories} historias con el enlace al puesto vacío."
        ),
        "en": (
            "The role, its {bullets} bullets and their {revisions} revisions will be deleted. "
            "{stories} stories stay with the role link cleared."
        ),
    },
    "delete.impact.bullet": {
        "es": (
            "La bala está en {tracks} pistas y citada por {analyses} análisis; los análisis "
            "conservan su copia. Se eliminan además sus {story_links} enlaces a historias y sus "
            "{revisions} revisiones."
        ),
        "en": (
            "The bullet is in {tracks} tracks and cited by {analyses} analyses; the analyses "
            "keep their copy. Its {story_links} story links and its {revisions} revisions go "
            "too."
        ),
    },
    "delete.impact.skill": {
        "es": (
            "«{skill}» saldrá de tu pool y de {tracks} pistas. El vocabulario compartido no "
            "se toca."
        ),
        "en": "“{skill}” leaves your pool and {tracks} tracks. The shared vocabulary is untouched.",
    },
    "delete.impact.summary": {
        "es": "Se eliminará el resumen del pool. {tracks} pistas pierden esa casilla.",
        "en": "The pool summary will be deleted. {tracks} tracks lose that slot.",
    },
    "delete.impact.track": {
        "es": (
            "Se eliminarán la pista y su selección de {selection} balas. {analyses} análisis "
            "conservan el nombre de la pista."
        ),
        "en": (
            "The track and its selection of {selection} bullets will be deleted. {analyses} "
            "analyses keep the track name."
        ),
    },
    "delete.impact.story": {
        "es": "Se eliminarán la historia y sus {links} enlaces a balas.",
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
        "es": (
            "Se eliminará todo lo del perfil: {resumes} CV, {roles} puestos, {bullets} balas, "
            "{summaries} resúmenes, {tracks} pistas, {stories} historias, {letter_templates} "
            "plantillas, {applications} análisis, {application_attempts} intentos y {skills} "
            "habilidades del pool. Se vaciarán {ledger_redacted} respuestas personales del "
            "registro de modelos, conservando tokens y coste. Tu cuenta y tu fila de perfil se "
            "quedan, vacías."
        ),
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
        "es": "Eliminar también las balas que solo aportó este CV.",
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
        "es": (
            "Elimina todo lo del perfil: CV, puestos, balas, resúmenes, pistas, historias, "
            "plantillas, análisis y las respuestas personales del registro de modelos. Tu "
            "cuenta y tu fila de perfil se quedan, vacías."
        ),
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
    "import.track": {"es": "Puesto objetivo (opcional)", "en": "Target track (optional)"},
    "import.track_hint": {
        "es": "La experiencia con la que piensas usar este currículum. Si lo dejas "
        "vacío, la importación crea un puesto objetivo con el nombre del archivo.",
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
    "import.track_label": {"es": "Puesto objetivo", "en": "Track"},
    "import.merge_track_hint": {
        "es": "El documento se guarda en un puesto objetivo con este nombre. Si ya está "
        "asignado a un puesto, se une a ese y este nombre no se usa.",
        "en": "The document is saved in a track with this name. If it is already "
        "assigned to one, it joins that track and this name is not used.",
    },
    "import.track_created": {"es": "Puesto objetivo creado: {name}", "en": "Track created: {name}"},
    "import.track_view": {"es": "Ver el puesto objetivo", "en": "View the track"},
    "import.track_join": {
        "es": "Los bullets de este documento se unirán a «{name}».",
        "en": "The bullets from this document will join «{name}».",
    },
    "import.track_joined": {
        "es": "Bullets añadidos a «{name}»: {count}.",
        "en": "Bullets added to «{name}»: {count}.",
    },
    "import.track_of_document": {
        "es": "Puesto objetivo de este documento: {name}",
        "en": "This document's track: {name}",
    },
    "import.track_bullets_added": {
        "es": "Bullets unidos al puesto",
        "en": "Bullets joined to the track",
    },
    "import.track_skills_added": {
        "es": "Habilidades unidas al puesto",
        "en": "Skills joined to the track",
    },
    "import.track_headline_filled": {
        "es": "Titular: rellenado desde el documento.",
        "en": "Headline: filled in from this document.",
    },
    "import.track_headline_kept": {
        "es": "Titular: sin tocar, el puesto objetivo ya tenía uno.",
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
        "es": "Resumen: sin tocar, el puesto objetivo ya tenía uno.",
        "en": "Summary: left alone, the track already had one.",
    },
    "import.merge_submit": {"es": "Importar la selección", "en": "Import the selection"},
    # F4.2: the same CV in the other language, imported as a translation.
    "import.translate_offer": {
        "es": "Este CV parece la versión en el otro idioma de tu puesto objetivo",
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
        "es": "El documento está en {document} y tu puesto objetivo está en {track}. "
        "Empareja los bullets que dicen lo mismo; lo que no empareje entra abajo como "
        "candidato nuevo.",
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
    # §12.1 item 6 (queue U5): the recommendations in one column, grouped under headings
    # with counts. `add_file` is the same group worded for a document (an attempt).
    "report.advice.group.promote": {"es": "Ordena tus bullets", "en": "Order your bullets"},
    "report.advice.group.add": {"es": "Añade a este puesto", "en": "Add to this track"},
    "report.advice.group.add_file": {
        "es": "Añade a tu documento",
        "en": "Add to your document",
    },
    "report.advice.group.skills": {"es": "Habilidades", "en": "Skills"},
    "report.advice.group.search": {"es": "Búsquedas y título", "en": "Searches and title"},
    "report.advice.group.language": {"es": "Idioma", "en": "Language"},
    "report.advice.group.other": {"es": "Otras", "en": "Other"},
    "report.advice.skills_card": {
        "es": "Añade a las habilidades del puesto: la oferta las pide y las tienes "
        "evidenciadas.",
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
