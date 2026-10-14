"""§12.1 item 3: the colour legend under Componentes (queue K1).

A dashed outline marks a missing term in the four cards and also a blocking gap, a warning
and an alert, so one always-visible line says what a filled and a dashed term mean (design v3
§4: shape and mark, no purple). Every term chip
carries its glyph and a visually hidden word: colour is never the only signal. The legend
appears once on a page, in the analysis and in an attempt's full report alike.
"""

import re

from src.extract import client as extract_client
from src.models import ApplicationAttempt
from tests.conftest import login
from tests.unit.attempt_support import AttemptProvider, analyzed_application, resume_payload
from tests.unit.test_analysis import text_of
from tests.unit.test_ingest_routes import DOCX_TYPE, docx_bytes
from tests.unit.test_report_layout import SECTION_IDS, section, stored

KEYWORDS = {
    "name": "keywords",
    "value": 0.5,
    "matched": ["python"],
    "missing": ["airflow"],
}


def page_with_terms(client, session, career) -> str:
    report = stored(session, career).report
    application = stored(
        session, career, score={**report["score"], "sub_scores": {"keywords": KEYWORDS}}
    )
    login(client, career.first.email)
    return client.get(f"/applications/{application.id}").text


def test_the_legend_line_and_its_closed_toggle_sit_under_the_components_heading(
    client, session, career
):
    page = page_with_terms(client, session, career)
    components = section(page, "components")

    legend = re.search(r"<p[^>]*data-legend[^>]*>.*?</p>", components, re.S)
    assert legend, "the line is always visible, not inside a toggle"
    words = text_of(legend.group(0))
    assert "✓" in words and "aparece en tu CV" in words
    assert "✕" in words and "falta en tu CV" in words
    assert "chip-missing" in legend.group(0), "the missing sample is dashed-outlined"
    assert components.index("data-legend") < components.index("grid-cols-2"), "above the cards"

    toggle = re.search(
        r'<details class="disclosure[^"]*">\s*<summary[^>]*>(.*?)</summary>(.*?)</details>',
        components,
        re.S,
    )
    assert toggle and "Cómo leer las marcas" in text_of(toggle.group(1))
    assert " open" not in toggle.group(0).split(">")[0], "closed by default"
    lines = re.findall(r"<li>(.*?)</li>", toggle.group(2), re.S)
    assert len(lines) == 5
    body = text_of(toggle.group(2))
    assert "75" in body and "50" in body and "discontinuo" in body and "Fondo gris" in body
    assert "ocre" in body and "solo mencionado" in body, "the level-1 state is in the legend"
    assert "octágono" in body


def test_a_missing_chip_has_its_glyph_and_hidden_word_and_a_found_chip_has_its_own(
    client, session, career
):
    components = section(page_with_terms(client, session, career), "components")

    missing = re.search(
        r'chip chip-missing"><span aria-hidden="true">✕</span> airflow(.*?)</span></span>',
        components,
        re.S,
    )
    assert missing, "the glyph is aria-hidden and sits in the chip"
    assert 'class="sr-only"' in missing.group(0) and "falta" in missing.group(1)

    found = re.search(
        r'class="chip"><span aria-hidden="true">✓</span> python(.*?)</span></span>',
        components,
        re.S,
    )
    assert found, "a matched chip carries ✓"
    assert 'class="sr-only"' in found.group(0) and "encontrada" in found.group(1)


SKILLS_LEVELS = {
    "name": "skills",
    "value": 0.4,
    "matched": ["python (L2, direct)"],
    "missing": ["excel (L1)", "airflow (L0)"],
    "detail": {"direct": 0.3, "transfer": 0.1},
}


def test_a_level_one_term_is_mentioned_with_the_ochre_chip_and_never_missing(
    client, session, career
):
    """§12.1 item 3, amended 2026-10-13: level 1 — the skills list or the summary names it,
    no bullet shows it — is *mentioned*, not missing: the ochre outline and the word, no ✕.
    Level 0 keeps the dashed missing chip. The report is stored by hand so both appear."""
    report = stored(session, career).report
    application = stored(
        session, career, score={**report["score"], "sub_scores": {"skills": SKILLS_LEVELS}}
    )
    login(client, career.first.email)

    components = section(client.get(f"/applications/{application.id}").text, "components")

    mentioned = re.search(
        r'class="chip chip-mentioned"><span aria-hidden="true">~</span> excel '
        r"<span>solo mencionado</span></span>",
        components,
        re.S,
    )
    assert mentioned, "level 1 wears ~ and the words, and drops its (L1)"
    assert "(L1)" not in components
    assert "✕</span> excel" not in components, "a mentioned term is never a missing one"

    missing = re.search(
        r'chip chip-missing"><span aria-hidden="true">✕</span> airflow(.*?)</span></span>',
        components,
        re.S,
    )
    assert missing, "level 0 keeps the dashed ✕"
    assert "falta" in text_of(missing.group(0))


def test_the_legend_comes_in_english_too(client, session, career):
    career.first.ui_lang = "en"
    session.commit()
    components = section(page_with_terms(client, session, career), "components")

    words = text_of(components)
    assert "appears in your CV" in words and "missing from your CV" in words
    assert "How to read the marks" in words
    assert "(found)" in words and "(missing)" in words


def test_the_legend_appears_once_in_an_attempts_full_report(
    client, session, career, monkeypatch, test_settings
):
    stub = AttemptProvider(
        bullet_id=str(career.first_bullet.id),
        resume=resume_payload(career.first_bullet.text_es),
    )
    monkeypatch.setattr(extract_client, "_post", stub)
    login(client, career.first.email)
    application, _analysis = analyzed_application(session, career, stub)
    client.post(
        f"/applications/{application.id}/attempts",
        files={
            "file": ("cv.docx", docx_bytes("Experiencia", career.first_bullet.text_es), DOCX_TYPE)
        },
        follow_redirects=False,
    )
    attempt = session.query(ApplicationAttempt).one()

    raw = client.get(f"/applications/{application.id}/attempts/{attempt.id}/report").text

    assert raw.count("data-legend") == 1
    assert raw.count("Cómo leer las marcas") == 1
    assert SECTION_IDS[1] in raw
