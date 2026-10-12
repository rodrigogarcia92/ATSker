"""§12.7: the report on a CV — the two-pane page, the CV pane's marks and the fragment.

The pane's text is `src.highlights.render_cv`'s, its marks are the highlight map's, and
`src.web.cv_pane.pane_view` is the view between them. These tests read the page the route
renders (two panes with a CV, the single column without one) and the fragment the tablet
drawer and the phone sheet fetch, and pin the view's own rules — a weak mark, and no marks
at all once the draft has moved on (decision 5).
"""

import re

import pytest

from src.applications import get_application
from src.extract import client as extract_client
from src.i18n import t
from src.resumes import get_resume
from src.web.cv_pane import pane_view
from tests.conftest import login
from tests.unit.cv_support import ensure_first_cv
from tests.unit.test_analysis import POSTING, Provider, text_of
from tests.unit.test_report_layout import stored


@pytest.fixture(autouse=True)
def _the_first_track_has_a_cv(request):
    """F11.3: an analysis is of a CV, so a test that runs one finds the first track's."""
    ensure_first_cv(request)


@pytest.fixture
def provider(monkeypatch, test_settings, career) -> Provider:
    stub = Provider(str(career.first_bullet.id))
    monkeypatch.setattr(extract_client, "_post", stub)
    return stub


def analysed(client, career) -> tuple[str, str]:
    """An analysis through the fake provider: its id and the page it renders."""
    login(client, career.first.email)
    posted = client.post(
        "/analyze",
        data={"jd_text": POSTING, "track_id": str(career.first_track.id)},
        follow_redirects=False,
    )
    url = posted.headers["location"]
    return url.rsplit("/", 1)[1], client.get(url).text


def part(page: str, tag: str, marker: str) -> str:
    match = re.search(rf"<{tag}\b[^>]*{marker}[^>]*>.*?</{tag}>", page, re.S)
    assert match, f"the page has its {marker}"
    return match.group(0)


# --- the view between the map and the template ---


GRADE = {"requirement": "SQL", "source": "bullet", "bullet_id": "b1"}
DRAFT = {"roles": [{"title": "Analista", "bullets": [{"text": "Usé SQL a diario"}]}]}
BULLETS = [{"id": "b1", "ordinal": 0}]


def test_a_level_one_citation_is_a_weak_span():
    report = {
        "cv": {},
        "bullets": BULLETS,
        "grades": [{**GRADE, "level": 1, "basis": "direct"}],
    }

    view = pane_view(report, DRAFT, {})

    weak = [seg for el in view["elements"] for seg in el.segments if seg.marked and seg.weak]
    assert weak, "level 1 is weaker evidence, drawn as a dashed underline"
    assert view["counts"]["requirements"] == 1, "one cited requirement is one mark"
    assert view["default_section"] == "requirements"


def test_a_direct_high_level_citation_is_strong():
    report = {
        "cv": {},
        "bullets": BULLETS,
        "grades": [{**GRADE, "level": 3, "basis": "direct"}],
    }

    view = pane_view(report, DRAFT, {})

    marked = [seg for el in view["elements"] for seg in el.segments if seg.marked]
    assert marked and all(not seg.weak for seg in marked)
    assert marked[0].keys == ("requirement:0",)


def test_a_draft_that_moved_since_the_analysis_draws_no_marks():
    report = {
        "cv": {"draft_sha": "sha256:not-the-draft"},
        "bullets": [{"id": "b1", "ordinal": 0}],
        "grades": [{"requirement": "SQL", "level": 3, "source": "bullet", "bullet_id": "b1"}],
    }
    draft = {"roles": [{"bullets": [{"text": "Usé SQL a diario"}]}]}

    view = pane_view(report, draft, {})

    assert view["current"] is False
    assert view["total"] == 0


# --- the page the route renders ---


def test_a_cv_analysis_renders_two_panes(client, career, provider):
    _id, page = analysed(client, career)

    assert "data-cv-pane" in page
    assert "min-[1280px]:grid-cols-[minmax(0,45fr)_minmax(0,55fr)]" in page
    assert 'id="cv-view-text"' in page and 'id="cv-view-file"' in page, "the two views"
    assert 'id="cv-drawer"' in page and 'id="cv-sheet"' in page


def test_the_pane_prints_the_draft_with_static_marks(client, career, provider):
    _id, page = analysed(client, career)
    pane = part(page, "section", "data-cv-pane")

    assert "Analista de datos" in text_of(pane), "the stored draft as text"
    assert '<mark class="hl' in pane
    assert 'data-key="' in pane and 'data-section="' in pane
    assert "data-active" not in pane, "no JavaScript state: every mark is the base tone"
    assert "Mostrando:" in pane, "the section legend names what the sheet shows"


def test_every_section_with_marks_gets_a_phone_link(client, career, provider):
    _id, page = analysed(client, career)

    assert re.search(r"Ver en mi CV \(\d+\)", page), "the phone's way back to the CV"
    assert 'data-cv-sheet="requirements"' in page


def test_the_phone_bar_carries_the_three_short_buttons(client, career, provider):
    _id, page = analysed(client, career)
    bar = part(page, "div", 'id="action-bar"')

    assert t("report.actions.try_cv_bar", "es") in bar
    assert t("report.actions.letter_bar", "es") in bar
    assert t("report.actions.summary_bar", "es") in bar


def test_the_original_view_says_a_docx_has_no_page_image(client, career, provider):
    _id, page = analysed(client, career)

    assert t("report.cv_pane.no_pages", "es") in page


# --- what stays the single column ---


def test_an_old_stored_report_keeps_the_single_column(client, session, career):
    application = stored(session, career)
    login(client, career.first.email)

    page = client.get(f"/applications/{application.id}").text

    assert "max-w-[760px]" in page
    assert "data-cv-pane" not in page
    assert 'aria-label="Acciones"' in page, "the rail is still there for an old report"


def test_a_deleted_cv_falls_back_to_the_single_column_with_the_name(
    client, session, career, provider
):
    application_id, _page = analysed(client, career)
    application = get_application(career.first_profile.id, session, application_id)
    application.resume_id = None  # F11.3: deleting the CV nulls the FK
    session.commit()

    page = client.get(f"/applications/{application_id}").text

    assert "data-cv-pane" not in page
    assert "CV eliminado:" in page


def test_a_cv_edited_after_the_analysis_keeps_two_panes_without_marks(
    client, session, career, provider
):
    application_id, _page = analysed(client, career)
    application = get_application(career.first_profile.id, session, application_id)
    resume = get_resume(career.first_profile.id, session, str(application.resume_id))
    resume.draft = {**resume.draft, "headline": "Otro titular"}
    session.commit()

    page = client.get(f"/applications/{application_id}").text

    assert "data-cv-pane" in page, "the panes stay"
    assert '<mark class="hl' not in part(page, "section", "data-cv-pane")
    assert t("report.cv_edited", "es") in page


# --- the fragment the drawer and the sheet fetch ---


def test_the_cv_fragment_serves_the_legend_and_the_sheet(client, career, provider):
    application_id, _page = analysed(client, career)

    response = client.get(f"/applications/{application_id}/cv")

    assert response.status_code == 200
    assert "data-cv-pane" in response.text
    assert '<mark class="hl' in response.text
    assert 'id="cv-view-text"' not in response.text, "no toolbar or toggle in the fragment"


def test_the_cv_fragment_is_404_for_a_report_without_a_cv(client, session, career):
    application = stored(session, career)
    login(client, career.first.email)

    assert client.get(f"/applications/{application.id}/cv").status_code == 404
