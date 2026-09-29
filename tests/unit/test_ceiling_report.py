"""The ceiling on the report page (PRD F10.2, A1/A10).

The report shows the ceiling beside Job Match and each sub-score's own ceiling, in
both interface languages; a master-data change makes the page recompute it and say so;
and rendering the page makes no model call.
"""

import pytest

from src.extract import client as extract_client
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


def test_the_unreachable_requirements_are_named(client, session, career, provider):
    """The posting's `machine learning` is held by no bullet, so it stays a gap."""
    url = _analyze(client, career)

    page = text_of(client.get(url).text)

    assert "puntos restantes requieren experiencia que ATSker no tiene registrada" in page
    assert "machine learning" in page


def test_the_try_new_cv_button_is_present_and_disabled(client, session, career, provider):
    url = _analyze(client, career)

    raw = client.get(url).text

    assert "Probar nueva versión del CV" in raw
    assert ".docx" in raw and "próximamente" in raw
    assert "disabled" in raw


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
