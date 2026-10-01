"""The ceiling on the report page (PRD F10.2, A1/A10).

The report shows the ceiling beside Job Match and each sub-score's own ceiling, in
both interface languages; a master-data change makes the page recompute it and say so;
and rendering the page makes no model call.
"""

import pytest

from src.extract import client as extract_client
from src.i18n import t
from src.models import Application
from tests.conftest import login
from tests.unit.test_analysis import POSTING, Provider, text_of


@pytest.fixture
def provider(monkeypatch, test_settings, career) -> Provider:
    stub = Provider(str(career.first_bullet.id))
    monkeypatch.setattr(extract_client, "_post", stub)
    return stub


def _analyze(client, career) -> str:
    login(client, career.first.email)
    posted = client.post(
        "/analyze",
        data={"jd_text": POSTING, "track_id": str(career.first_track.id)},
        follow_redirects=False,
    )
    assert posted.status_code == 303
    return posted.headers["location"]


def test_the_ceiling_is_shown_beside_job_match_in_both_languages(
    client, session, career, provider
):
    url = _analyze(client, career)

    spanish = text_of(client.get(url).text)
    assert "Techo con tu material:" in spanish, "the label A1 fixes"
    assert "(estimado)" in spanish

    career.first.ui_lang = "en"
    session.commit()
    english = text_of(client.get(url).text)
    assert "Ceiling with your material:" in english
    assert "(estimated)" in english


def test_every_sub_score_shows_its_own_ceiling(client, session, career, provider):
    url = _analyze(client, career)

    page = text_of(client.get(url).text)

    assert page.count("techo ") >= 4, "one ceiling per sub-score card"


def test_the_remainder_attributes_each_part_to_its_source(client, session, career, provider):
    """A5: the sentence names the requirement with no evidence, never the whole gap."""
    url = _analyze(client, career)

    page = text_of(client.get(url).text)

    assert "puntos restantes:" in page
    assert "requieren experiencia que ATSker no tiene registrada (machine learning)" in page
    assert "dependen de años de experiencia" in page
    assert "de evidencia más fuerte en requisitos que ya cubres" in page


def test_the_try_new_cv_button_opens_the_attempt_modal(client, session, career, provider):
    """C.1: the button is live and the modal it opens is on the page."""
    url = _analyze(client, career)

    raw = client.get(url).text

    assert "Probar nueva versión del CV" in raw
    assert ".docx" in raw
    assert 'id="attempt-open"' in raw
    assert "<dialog id=\"attempt-modal\"" in raw
    assert 'action="' in raw and "/attempts" in raw


def test_the_live_try_new_cv_button_carries_no_coming_soon_note(client, session, career, provider):
    """C.6: the button is enabled, so neither language says it is coming."""
    url = _analyze(client, career)

    page = client.get(url).text.lower()

    assert "próximamente" not in page
    assert "coming soon" not in page
    assert t("report.try_new_cv_note", "es") == "(.docx)"
    assert t("report.try_new_cv_note", "en") == "(.docx)"


def test_the_modal_script_checks_response_ok_before_a_result(client, session, career, provider):
    """C.6: a 404/500/502 HTML page is an error line, never a result or `unsaved`."""
    url = _analyze(client, career)

    page = client.get(url).text
    marker = 'const modal = document.getElementById("attempt-modal")'
    script = page.split(marker, 1)[1].split("</script>", 1)[0]
    poll = script.split("function startPoll", 1)[1].split("function setBusy", 1)[0]
    submit = script.split('form.addEventListener("submit"', 1)[1]

    assert "response.ok" in poll, "a non-OK poll stops and shows the error"
    assert "stopPoll()" in poll.split("response.ok", 1)[1].split("return", 1)[0]
    assert "response.ok" in submit, "a non-OK submit never reaches #attempt-status"
    assert submit.index("response.ok") < submit.index("status.innerHTML")


def test_a_master_change_recomputes_the_ceiling_on_view(client, session, career, provider):
    url = _analyze(client, career)

    first = text_of(client.get(url).text)
    assert "recalculado con tu material actual" not in first, "the stored ceiling stands"

    career.first_bullet.skills = [*career.first_bullet.skills, "sql"]
    session.commit()

    recomputed = text_of(client.get(url).text)
    assert "recalculado con tu material actual" in recomputed


def test_viewing_the_report_makes_no_model_call(client, session, career, provider):
    url = _analyze(client, career)
    before = len(provider.calls)

    response = client.get(url)

    assert response.status_code == 200
    assert len(provider.calls) == before, "the ceiling is deterministic and offline"


def test_an_unknown_weights_version_shows_no_ceiling(client, session, career, provider):
    """A5 fix 2: a w2 report is not re-scored under w4's rules, so nothing renders."""
    url = _analyze(client, career)
    application = session.query(Application).one()
    report = dict(application.report)
    report.pop("ceiling", None)
    score = dict(report["score"])
    score["weights_version"] = "w2"
    report["score"] = score
    application.report = report
    session.commit()

    page = text_of(client.get(url).text)

    assert "Techo con tu material" not in page
    assert "puntos restantes" not in page


def test_a_capped_report_says_the_ceiling_ignores_the_format_cap(
    client, session, career, provider
):
    """A5 fix 3: a ceiling above a capped Job Match must not read as a contradiction."""
    url = _analyze(client, career)
    application = session.query(Application).one()
    report = dict(application.report)
    score = dict(report["score"])
    score.update({"capped": 40, "uncapped": 62, "cap": 40, "cap_reason": "contact_in_margin"})
    report["score"] = score
    application.report = report
    session.commit()

    page = text_of(client.get(url).text)

    assert "Techo con tu material" in page
    assert "(sin el límite de formato)" in page


def test_an_uncapped_report_has_no_cap_note(client, session, career, provider):
    url = _analyze(client, career)

    page = text_of(client.get(url).text)

    assert "Techo con tu material" in page
    assert "(sin el límite de formato)" not in page


def test_an_older_report_recomputes_its_ceiling_on_view(client, session, career, provider):
    """A10: a report stored before the ceiling existed has none, so the page computes
    one on view and says it did."""
    url = _analyze(client, career)
    application = session.query(Application).one()
    report = dict(application.report)
    report.pop("ceiling", None)
    application.report = report
    session.commit()

    page = text_of(client.get(url).text)

    assert "Techo con tu material" in page, "computed on view"
    assert "recalculado con tu material actual" in page
