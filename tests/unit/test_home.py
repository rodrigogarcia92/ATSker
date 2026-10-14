"""§12.8's logged-in home: the three cards, the last report and the activity.

`src/web/home.py` is the view between the profile's own rows and `home.html`; these tests
read the page the route renders — with data and without — and pin the relative time the
state lines and the activity are built from.
"""

from datetime import UTC, datetime, timedelta

from src.i18n import t
from src.web.templating import relative_time
from tests.conftest import login
from tests.unit.cv_support import add_first_cv
from tests.unit.test_report_layout import stored


def aged(session, resume, *, days: int):
    """A CV uploaded `days` ago: the fixtures' own epoch is a fixed date, not today."""
    resume.uploaded_at = datetime.now(UTC) - timedelta(days=days)
    session.commit()
    return resume


def with_data(session, career):
    """One stored analysis of a CV, as the drive leaves it: a company, a title, a file."""
    application = stored(session, career)
    resume = aged(session, add_first_cv(session, career, name="CV_Ana_2026.docx"), days=4)
    application.company = "Globex"
    application.title = "Analista de datos"
    application.resume_id = resume.id
    application.report = {**application.report, "cv": {"filename": resume.filename}}
    session.commit()
    return application, resume


def test_the_home_names_the_three_ways_to_continue(client, career):
    login(client, career.first.email)

    page = client.get("/").text

    assert t("home.title", "es") in page
    assert t("home.greeting", "es", name=career.first_profile.display_name) in page
    for href, key in (
        ("/dashboard", "home.card.dashboard"),
        ("/import", "home.card.import"),
        ("/analyze", "home.card.analyze"),
    ):
        assert f'href="{href}"' in page, f"the card leads to {href}"
        assert t(key, "es") in page
    assert 'class="home-card home-card-primary"' in page, "the posting card is the forest one"


def test_the_cards_state_lines_come_from_the_profiles_own_data(client, session, career):
    _application, resume = with_data(session, career)
    login(client, career.first.email)

    page = client.get("/").text

    assert t("home.card.dashboard.label", "es") in page and "Globex" in page
    assert "Último: hace 4 días" in page
    assert t("home.card.analyze.line", "es") in page, "one track, in the singular"
    assert t("home.card.analyze.cv", "es", name=resume.filename) in page


def test_the_home_shows_a_score_in_its_band_colour(client, session, career):
    """Design v3 §4, amended: the score colours apply to any score the home shows."""
    with_data(session, career)
    login(client, career.first.email)

    page = client.get("/").text

    # The stored report scores 40/100 — the Débil band.
    assert page.count('<span class="band-number-weak">40</span>') == 2, (
        "the panel card's number and the last report's own"
    )


def test_the_last_report_leads_to_its_own_page_with_its_file(client, session, career):
    application, resume = with_data(session, career)
    login(client, career.first.email)

    page = client.get("/").text

    assert f'href="/applications/{application.id}"' in page
    assert t("home.continue.title", "es") in page
    assert "Analista de datos · Globex" in page
    assert resume.filename in page


def test_the_activity_lists_the_analysis_and_the_import_newest_first(client, session, career):
    with_data(session, career)
    login(client, career.first.email)

    page = client.get("/").text

    analysed = t("home.activity.analysis", "es", subject="Analista de datos")
    imported = t("home.activity.import", "es", filename="CV_Ana_2026.docx")

    assert analysed in page and imported in page
    assert page.index(analysed) < page.index(imported), (
        "the analysis just happened; the CV came days ago"
    )


def test_a_profile_without_data_sees_the_cards_and_their_empty_states(client, career):
    """§12.2's *Primeros pasos* is not built: a new profile sees the cards, not a wizard."""
    login(client, career.first.email)

    page = client.get("/").text

    for key in (
        "home.card.dashboard.empty",
        "home.card.import.empty",
        "home.continue.empty",
        "home.activity.empty",
    ):
        assert t(key, "es") in page, key
    # The career fixture's one track: the card counts lines, and it has one.
    assert t("home.card.analyze.line", "es") in page
    assert "CV más reciente" not in page, "there is no CV to name"


def test_relative_time_reads_minutes_hours_days_and_then_the_date():
    now = datetime.now(UTC)

    assert relative_time(now - timedelta(minutes=1), "es") == "hace 1 minuto"
    assert relative_time(now - timedelta(minutes=5), "es") == "hace 5 minutos"
    assert relative_time(now - timedelta(hours=2), "es") == "hace 2 horas"
    assert relative_time(now - timedelta(hours=1), "en") == "1 hour ago"
    assert relative_time(now - timedelta(days=1), "es") == "hace 1 día"
    assert relative_time(now - timedelta(days=4), "es") == "hace 4 días"
    assert relative_time(now - timedelta(days=9), "es") == (
        now - timedelta(days=9)
    ).strftime("%Y-%m-%d"), "after a week the date itself"
    assert relative_time(None, "es") == "", "no timestamp, no sentence"
