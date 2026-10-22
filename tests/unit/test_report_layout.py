"""§12.1's result page: the order of its sections and what opens by itself (queue U3).

The page is a reading order with disclosures. The tests read the HTML the way the rules
state it — section ids in sequence, closed `<details>` by default, one open only for a
blocker — and build their reports through the same fake provider the analysis tests use,
or store one by hand where a report needs a shape the pipeline would not produce today.
"""

import html
import re

import pytest

from src.extract import client as extract_client
from src.i18n import t
from src.models import Application
from tests.conftest import login
from tests.unit.cv_support import analysis_form, ensure_first_cv
from tests.unit.test_analysis import POSTING, Provider, store_flagged, text_of

SECTION_IDS = (
    "fit",
    "components",
    "recruiter",
    "requirements",
    "recommendations",
    "ats",
    "before",
    "trace",
)

DETAILS_TAG = re.compile(r"<details\b[^>]*>")


@pytest.fixture(autouse=True)
def _the_first_track_has_a_cv(request):
    """F11.3: an analysis is of a CV, so a test that runs one finds the first track's."""
    ensure_first_cv(request)



@pytest.fixture
def provider(monkeypatch, test_settings, career) -> Provider:
    stub = Provider(str(career.first_bullet.id))
    monkeypatch.setattr(extract_client, "_post", stub)
    return stub


def analysed_page(client, career) -> str:
    """A full analysis through the fake provider, with a track so every section shows."""
    login(client, career.first.email)
    posted = client.post(
        "/analyze",
        data={"jd_text": POSTING, "track_id": str(career.first_track.id)},
        follow_redirects=False,
    )
    assert posted.status_code == 303
    return client.get(posted.headers["location"]).text


def section(page: str, name: str) -> str:
    match = re.search(rf'<section id="{name}"[^>]*>.*?</section>', page, re.S)
    assert match, f"the page has a {name} section"
    return match.group(0)


def stored(session, career, *, severity="blocker", **changes):
    """A report stored by hand, so it carries exactly the keys a test names."""
    application = store_flagged(
        session, career.first_profile.id, capped=40, uncapped=62, cap=40, severity=severity
    )
    application.report = {**application.report, **changes}
    session.commit()
    return application


def test_the_sections_appear_in_the_approved_order(client, career, provider):
    page = analysed_page(client, career)

    positions = [page.index(f'id="{name}"') for name in SECTION_IDS]

    assert positions == sorted(positions), "§12.1's list, top to bottom"
    assert len(set(positions)) == len(SECTION_IDS)


def test_the_fit_definition_renders_in_both_languages(client, session, career, provider):
    login(client, career.first.email)
    posted = client.post(
        "/analyze", data=analysis_form(session, career, jd_text=POSTING), follow_redirects=False
    )
    url = posted.headers["location"]

    spanish = text_of(client.get(url).text)
    assert t("report.fit_definition", "es") in spanish
    assert "no es la probabilidad de ser contratado" in spanish

    career.first.ui_lang = "en"
    session.commit()
    english = text_of(client.get(url).text)
    assert t("report.fit_definition", "en") in english
    assert "not the probability of being hired" in english


EXPERIENCE = {
    "name": "experience",
    "value": 0.8,
    "matched": ["3.00 years"],
    "missing": [],
    "detail": {
        "held_years": 5.0,
        "relevant_years": 3.0,
        "required_years": 3.0,
        "relevant_roles": [{"id": "r1", "title": "Analista de riesgo", "weight": 1.0}],
        "tasks": [
            {"text": "Armar reportes mensuales", "level": 2, "bullet_id": None},
            {"text": "Desplegar modelos", "level": 0, "bullet_id": None},
        ],
    },
}


def test_the_experience_card_has_its_years_line_and_a_closed_detail(client, session, career):
    report = stored(session, career).report
    application = stored(
        session, career, score={**report["score"], "sub_scores": {"experience": EXPERIENCE}}
    )
    login(client, career.first.email)

    page = client.get(f"/applications/{application.id}").text
    components = section(page, "components")

    assert "3 años · 3 de 5" in text_of(components), "relevant years, then relevant of held"
    toggles = DETAILS_TAG.findall(components)
    assert len(toggles) == 2, "the colour legend's toggle, then Ver detalle"
    assert all(" open" not in tag for tag in toggles), "both start closed"
    detail = components[components.index("Ver detalle") :]
    assert "Ver detalle" in detail
    assert "Analista de riesgo (1.0)" in text_of(detail), "the relevant roles, with their weight"
    assert "Requeridos: 3 años" in text_of(detail)
    assert "Tareas de la oferta cubiertas: 1 de 2" in text_of(detail)


def test_a_report_without_experience_detail_gets_the_card_without_the_toggle(
    client, session, career
):
    report = stored(session, career).report
    old = {
        "name": "experience",
        "value": 0.5,
        "matched": [],
        "missing": ["1.50 years"],
        "detail": {"held_years": 1.5, "required_years": 3, "deficit_years": 1.5},
    }
    application = stored(
        session, career, score={**report["score"], "sub_scores": {"experience": old}}
    )
    login(client, career.first.email)

    page = client.get(f"/applications/{application.id}").text

    components = section(page, "components")
    assert len(DETAILS_TAG.findall(components)) == 1, "only the colour legend's toggle"
    assert "Ver detalle" not in components


def test_each_recruiter_search_is_one_closed_details_with_its_query_and_verdict(
    client, career, provider
):
    page = analysed_page(client, career)
    recruiter = section(page, "recruiter")

    toggles = DETAILS_TAG.findall(recruiter)
    summaries = re.findall(r"<summary>(.*?)</summary>", recruiter, re.S)

    assert len(toggles) == 2 == len(summaries), "one toggle per derived query"
    assert all(" open" not in tag for tag in toggles), "none starts open"
    words = [text_of(summary) for summary in summaries]
    assert '"analista de datos" AND python' in html.unescape(text_of(summaries[0]))
    assert any("No apareces" in text for text in words), "the failing search says so"
    assert any("Apareces" in text and "No apareces" not in text for text in words)
    assert "Apareces en 1 de 2 búsquedas" in text_of(recruiter)


def blocker_page(client, session, career, severity):
    application = stored(session, career, severity=severity)
    login(client, career.first.email)
    return client.get(f"/applications/{application.id}").text


def test_the_ats_details_is_open_exactly_when_the_report_has_a_blocker(client, session, career):
    with_blocker = section(blocker_page(client, session, career, "blocker"), "ats")
    first_toggle = DETAILS_TAG.search(with_blocker).group(0)
    assert " open" in first_toggle, "a blocker opens its own section"
    assert "1 bloqueo" in text_of(with_blocker)

    without = section(blocker_page(client, session, career, "warning"), "ats")
    second_toggle = DETAILS_TAG.search(without).group(0)
    assert " open" not in second_toggle, "no blocker, so closed"
    assert "Sin bloqueos" in text_of(without)
    assert "Avisos 1" in text_of(without), "the warning is counted in the summary"


GAPS = {
    "gaps": [
        {
            "requirement": "dbt",
            "must_have": False,
            "level": 0,
            "blocking": False,
            "interpretation": "Ningún bullet lo menciona.",
        },
        {
            "requirement": "airflow",
            "must_have": False,
            "level": 0,
            "blocking": False,
            "interpretation": "Ningún bullet lo menciona.",
        },
    ],
    "warning": {"text": "Salto desde el sector público", "handling": "Abre con un resultado."},
    "alerts": [],
    "covered_by_transfer": [
        {
            "requirement": "snowflake",
            "must_have": True,
            "level": 2,
            "transfer_reason": "Usas BigQuery.",
            "bullet_text": "Modelé datos en BigQuery.",
        }
    ],
    "stories_used": [],
    "not_found": "",
}


def test_before_applying_has_one_summary_line_and_three_closed_toggles(client, session, career):
    application = stored(session, career, gaps=GAPS)
    login(client, career.first.email)

    page = client.get(f"/applications/{application.id}").text
    before = section(page, "before")

    toggles = DETAILS_TAG.findall(before)
    assert len(toggles) == 3 and all(" open" not in tag for tag in toggles)
    text = text_of(before)
    assert "2 brechas decisivas · 1 advertencia · 1 requisito cubierto por transferencia" in text
    for label, count in (("Brechas", 2), ("Advertencia", 1), ("Cubierto por transferencia", 1)):
        assert f"{label} · {count}" in text, f"{label} shows how many it holds"
    assert "Usas BigQuery." in text and "Abre con un resultado." in text


def test_an_empty_group_still_renders_its_toggle_with_zero_and_a_line(client, session, career):
    empty = {**GAPS, "gaps": [], "warning": {"text": "", "handling": ""}, "covered_by_transfer": []}
    application = stored(session, career, gaps=empty)
    login(client, career.first.email)

    before = section(client.get(f"/applications/{application.id}").text, "before")

    assert len(DETAILS_TAG.findall(before)) == 3, "the toggles stay"
    text = text_of(before)
    assert "0 brechas decisivas · 0 advertencias · 0 requisitos cubiertos por transferencia" in text
    for label in ("Brechas", "Advertencia", "Cubierto por transferencia"):
        assert f"{label} · 0" in text
    assert t("report.no_gaps", "es") in text
    assert t("report.before.no_warning", "es") in text
    assert t("report.before.no_transfer", "es") in text


def test_traceability_is_last_and_closed(client, career, provider):
    page = analysed_page(client, career)

    trace = section(page, "trace")

    assert " open" not in DETAILS_TAG.search(trace).group(0)
    assert page.index('id="trace"') > page.index('id="before"')
    assert "Trazabilidad" in text_of(trace)


def test_an_old_stored_report_still_renders(client, session, career):
    """A report from before F10 has no `ceiling`, no experience detail and no gaps."""
    application = stored(session, career, severity="warning")
    login(client, career.first.email)

    response = client.get(f"/applications/{application.id}")

    assert response.status_code == 200
    for name in ("fit", "components", "requirements", "ats", "before", "trace"):
        assert f'id="{name}"' in response.text


def test_the_keywords_line_says_present_over_kept_for_a_w5_report(
    client, session, career, provider
):
    """F5.5.3: the number is present ÷ kept terms, and the line under it says so."""
    page = analysed_page(client, career)
    application = session.query(Application).order_by(Application.created_at.desc()).first()
    keywords = application.report["score"]["sub_scores"]["keywords"]
    detail = keywords["detail"]

    assert detail["rule"] == "K2"
    components = text_of(section(page, "components"))
    assert "Términos que un reclutador buscaría y que tu CV contiene:" in components
    assert f"{detail['present']} de {detail['terms']}." in components


def test_a_w4_report_keeps_the_keywords_line_it_was_shown_with(client, session, career, provider):
    analysed_page(client, career)
    application = session.query(Application).order_by(Application.created_at.desc()).first()
    report = dict(application.report)
    score = dict(report["score"])
    score["weights_version"] = "w4"
    sub_scores = dict(score["sub_scores"])
    keywords = dict(sub_scores["keywords"])
    keywords["detail"] = {
        key: value for key, value in keywords["detail"].items() if key != "rule"
    }
    sub_scores["keywords"] = keywords
    score["sub_scores"] = sub_scores
    report["score"] = score
    application.report = report
    session.commit()

    page = client.get(f"/applications/{application.id}").text
    components = text_of(section(page, "components"))

    assert "Términos de la oferta presentes en tu CV." in components
    assert "un reclutador buscaría" not in components


def test_the_page_stores_nothing_about_what_was_opened(client, career, provider):
    page = analysed_page(client, career)

    assert "localStorage" not in page and "sessionStorage" not in page
    assert "document.cookie" not in page


# --- V5: "Ajuste general" and the warning count (§12.1) ---


def test_the_score_is_called_ajuste_general_in_the_section_the_header_and_the_nav(
    client, career, provider
):
    page = analysed_page(client, career)

    assert "Encaje total" not in text_of(page)
    assert "Ajuste general" in text_of(section(page, "fit"))
    # §12.7: a CV report drops §12.1 item 10's rail, and its jump links move to the header.
    rail = re.search(r'<aside\b[^>]*aria-label="Acciones"', page)
    assert rail is None, "no action rail on a CV report"
    nav = re.search(r"<nav\b[^>]*aria-label=\"En esta página\".*?</nav>", page, re.S).group(0)
    assert re.search(r'href="#fit"[^>]*>\s*Ajuste general\s*<', nav), "and its jump link"
    assert t("report.total", "en") == "Overall fit", "the key keeps its name; English is unchanged"


def test_one_warning_and_two_alerts_count_as_one_warning(client, session, career):
    alerts = [
        {"kind": "over_seniority"},
        {"kind": "location", "requirement": "Presencial en Lima", "verdict": "unverified"},
    ]
    gaps = {**GAPS, "alerts": alerts}
    application = stored(session, career, gaps=gaps)
    login(client, career.first.email)

    before = section(client.get(f"/applications/{application.id}").text, "before")

    text = text_of(before)
    assert "Advertencia · 1" in text
    assert "1 advertencia" in text and "3 advertencias" not in text
    assert "Advertencia · 3" not in text
    # The alerts are still inside the toggle.
    toggle = [block for block in before.split("<details") if "Advertencia" in block][0]
    assert "Salto desde el sector público" in text_of(toggle)
    assert text_of(toggle).count("Presencial en Lima") == 1


def test_alerts_without_a_warning_count_zero_and_say_there_is_no_warning(
    client, session, career
):
    gaps = {
        **GAPS,
        "warning": {"text": "", "handling": ""},
        "alerts": [{"kind": "over_seniority"}],
    }
    application = stored(session, career, gaps=gaps)
    login(client, career.first.email)

    text = text_of(section(client.get(f"/applications/{application.id}").text, "before"))

    assert "Advertencia · 0" in text
    assert t("report.before.no_warning", "es") in text
