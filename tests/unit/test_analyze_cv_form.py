"""The analysis form on a CV (PRD F11.3, F11.6): track → CV → posting.

F11.11 criteria 3 ("Último CV de la línea" resolves at submit), 6 (no GET calls the
provider; "Proponer línea" makes at most one call and none on repeat) and 8 (a foreign
`resume_id` is a 404), plus the form's own behaviour.
"""

import re

import pytest

from src.applications import create_application
from src.extract import client as extract_client
from src.models import Application, LlmCall
from src.recommend import recommend
from src.tracks import create_track, set_track_bullets
from tests.conftest import login
from tests.unit.attempt_support import POSTING, AttemptProvider
from tests.unit.cv_support import draft_dict, make_cv


@pytest.fixture
def provider(monkeypatch, test_settings, career) -> AttemptProvider:
    stub = AttemptProvider(bullet_id=str(career.first_bullet.id))
    monkeypatch.setattr(extract_client, "_post", stub)
    return stub


def own(career) -> dict:
    return draft_dict(career.first_bullet.text_es)


def second_track(session, career, name: str = "BI Analyst"):
    track = create_track(
        career.first_profile.id, session, name=name, applies_when="BI", lang="en"
    )
    set_track_bullets(career.first_profile.id, session, track.id, [career.first_bullet.id])
    session.commit()
    return track


def post(client, career, **data):
    return client.post(
        "/analyze",
        data={"jd_text": POSTING, "track_id": str(career.first_track.id), **data},
        follow_redirects=False,
    )


def options(html: str, name: str) -> list[tuple[str, str]]:
    """`(value, text)` of each `<option>` inside the `<select name=...>`."""
    select = re.search(rf'<select[^>]*name="{name}"[^>]*>(.*?)</select>', html, re.S)
    assert select, f"no <select name={name}>"
    return [
        (value, re.sub(r"\s+", " ", text).strip())
        for value, text in re.findall(
            r'<option value="([^"]*)"[^>]*>(.*?)</option>', select.group(1), re.S
        )
    ]


# --- the form ------------------------------------------------------------------------


def test_the_form_asks_for_a_track_then_a_cv_and_has_no_recommend_box(
    client, session, career, provider
):
    older = make_cv(session, career.first_profile, career.first_track, name="a.docx",
                    age_days=5, draft=own(career))
    newer = make_cv(session, career.first_profile, career.first_track, name="b.docx",
                    age_days=1, draft=own(career))
    login(client, career.first.email)

    page = client.get("/analyze").text

    assert 'name="recommend"' not in page, "the checkbox is gone (F11.3)"
    track_at, cv_at, posting_at = (
        page.index(f'name="{name}"') for name in ("track_id", "resume_id", "jd_text")
    )
    assert track_at < cv_at < posting_at, "track, then CV, then the posting"
    cvs = options(page, "resume_id")
    assert cvs[0] == ("latest", "Último CV de la línea (b.docx)")
    assert [value for value, _text in cvs[1:]] == [str(newer.id), str(older.id)], "newest first"
    assert "2025-12-31" in cvs[1][1] or "2026-01-01" in cvs[1][1]
    assert "b.docx" in cvs[1][1] and "a.docx" in cvs[2][1]
    assert provider.calls == []


def test_one_active_track_is_preselected(client, session, career, provider):
    login(client, career.first.email)

    page = client.get("/analyze").text

    track = options(page, "track_id")
    assert track[0][0] == str(career.first_track.id), "nothing to choose between"
    assert re.search(rf'<option value="{career.first_track.id}"[^>]*selected', page)


def test_several_tracks_start_on_a_prompt_and_show_no_cv_list_yet(
    client, session, career, provider
):
    second_track(session, career)
    login(client, career.first.email)

    page = client.get("/analyze").text

    assert options(page, "track_id")[0][0] == "", "choose a track first"
    assert 'name="resume_id"' not in page
    assert "Elige una línea de carrera para ver sus CV" in page


def test_a_track_with_no_cv_says_so_and_links_to_import_with_that_track(
    client, session, career, provider
):
    login(client, career.first.email)

    page = client.get("/analyze").text

    assert "no tiene ningún CV" in page
    assert f'href="/import?track_id={career.first_track.id}"' in page
    assert 'name="resume_id"' not in page


def test_the_import_page_preselects_the_track_it_is_linked_with(
    client, session, career, provider
):
    login(client, career.first.email)

    page = client.get(f"/import?track_id={career.first_track.id}").text

    assert re.search(rf'<option value="{career.first_track.id}"[^>]*selected', page)


def test_the_cv_partial_follows_the_track_and_calls_no_provider(
    client, session, career, provider
):
    other = second_track(session, career)
    make_cv(session, career.first_profile, career.first_track, name="mine.docx", draft=own(career))
    make_cv(session, career.first_profile, other, name="bi.docx", draft=own(career))
    login(client, career.first.email)

    first = client.get(f"/analyze/cvs?track_id={career.first_track.id}").text
    again = client.get(f"/analyze/cvs?track_id={other.id}").text
    none = client.get("/analyze/cvs?track_id=").text

    assert "mine.docx" in first and "bi.docx" not in first
    assert "bi.docx" in again and "mine.docx" not in again
    assert "<html" not in first, "a partial, not a page"
    assert 'id="cv-picker"' in none and 'name="resume_id"' not in none
    assert provider.calls == []


def test_the_cv_partial_of_another_profiles_track_is_a_404(client, session, career, provider):
    login(client, career.first.email)

    assert client.get(f"/analyze/cvs?track_id={career.second_track.id}").status_code == 404
    assert client.get(f"/analyze?track_id={career.second_track.id}").status_code == 404
    assert provider.calls == []


def test_choosing_the_track_without_script_keeps_the_posting(client, session, career, provider):
    other = second_track(session, career)
    make_cv(session, career.first_profile, other, name="bi.docx", draft=own(career))
    login(client, career.first.email)

    page = client.post(
        "/analyze/track",
        data={"jd_text": "Una oferta que no quiero perder", "track_id": str(other.id)},
    ).text

    assert "Una oferta que no quiero perder" in page
    assert "bi.docx" in page and re.search(rf'<option value="{other.id}"[^>]*selected', page)
    assert provider.calls == []


# --- submitting ----------------------------------------------------------------------


def test_latest_resolves_to_the_newest_cv_at_submit(client, session, career, provider):
    """F11.11 criterion 3."""
    older = make_cv(session, career.first_profile, career.first_track, name="old.docx",
                    age_days=9, draft=own(career))
    login(client, career.first.email)

    first = post(client, career, resume_id="latest")
    newer = make_cv(session, career.first_profile, career.first_track, name="new.docx",
                    age_days=1, draft=own(career))
    second = post(client, career, resume_id="latest")

    assert first.status_code == second.status_code == 303
    applications = session.query(Application).order_by(Application.created_at).all()
    assert [a.resume_id for a in applications] == [older.id, newer.id]
    assert applications[1].report["cv"] == {
        **applications[1].report["cv"], "filename": "new.docx", "chosen": "latest",
    }


def test_an_explicit_cv_is_scored_and_recorded(client, session, career, provider):
    old = make_cv(session, career.first_profile, career.first_track, name="old.docx",
                  age_days=9, draft=own(career))
    make_cv(session, career.first_profile, career.first_track, name="new.docx", age_days=1,
            draft=own(career))
    login(client, career.first.email)

    response = post(client, career, resume_id=str(old.id))

    application = session.query(Application).one()
    assert response.status_code == 303
    assert application.resume_id == old.id and application.track_id == career.first_track.id
    assert application.report["cv"]["chosen"] == "explicit"
    assert application.report["cv"]["filename"] == "old.docx"


def test_the_stored_report_says_how_long_storing_took(client, session, career, provider):
    """R13.3: `save` is added after the commit — the one wait the pipeline cannot see."""
    make_cv(session, career.first_profile, career.first_track, draft=own(career))
    login(client, career.first.email)

    assert post(client, career, resume_id="latest").status_code == 303

    steps = session.query(Application).one().report["llm"]["steps_ms"]
    assert isinstance(steps["save"], int) and steps["save"] >= 0
    assert steps["notes"] == 0, "the interface pays for the gap prose after storing"


def test_a_cv_analysis_makes_no_extraction_call(client, session, career, provider):
    make_cv(session, career.first_profile, career.first_track, draft=own(career))
    login(client, career.first.email)

    post(client, career, resume_id="latest")

    assert provider.calls_for("ResumeExtraction") == []
    assert len(provider.calls_for("EvidenceGrading")) == 1


def test_a_foreign_resume_id_is_a_404_and_calls_nothing(client, session, career, provider):
    """F11.11 criterion 8: form, URL or selector."""
    theirs = make_cv(session, career.second_profile, career.second_track, name="theirs.docx")
    login(client, career.first.email)

    response = post(client, career, resume_id=str(theirs.id))

    assert response.status_code == 404
    assert provider.calls == []
    assert session.query(Application).count() == 0


def test_a_cv_of_another_track_is_a_404_too(client, session, career, provider):
    other = second_track(session, career)
    elsewhere = make_cv(session, career.first_profile, other, name="bi.docx", draft=own(career))
    make_cv(session, career.first_profile, career.first_track, draft=own(career))
    login(client, career.first.email)

    response = post(client, career, resume_id=str(elsewhere.id))

    assert response.status_code == 404
    assert provider.calls == []


def test_garbage_ids_are_a_404_not_a_500(client, session, career, provider):
    make_cv(session, career.first_profile, career.first_track, draft=own(career))
    login(client, career.first.email)

    assert post(client, career, resume_id="not-an-id").status_code == 404
    assert client.post("/analyze", data={"jd_text": POSTING, "track_id": "nope"}).status_code == 404
    assert provider.calls == []


def test_a_track_with_no_cv_cannot_be_analysed(client, session, career, provider):
    login(client, career.first.email)

    response = post(client, career, resume_id="latest")

    assert response.status_code == 200
    assert "no tiene ningún CV" in response.text
    assert provider.calls == [] and session.query(Application).count() == 0


def test_no_track_is_not_an_analysis_any_more(client, session, career, provider):
    make_cv(session, career.first_profile, career.first_track, draft=own(career))
    login(client, career.first.email)

    response = client.post("/analyze", data={"jd_text": POSTING}, follow_redirects=False)

    assert response.status_code == 200
    assert "Elige una línea de carrera" in response.text
    assert provider.calls == [] and session.query(Application).count() == 0


def test_a_blank_posting_is_refused_before_anything_else(client, session, career, provider):
    login(client, career.first.email)

    response = client.post("/analyze", data={"jd_text": "   "})

    assert response.status_code == 200 and "Pega el texto de la oferta" in response.text
    assert provider.calls == []


# --- GETs never pay ------------------------------------------------------------------


def test_no_get_calls_the_provider(client, session, career, provider):
    """F11.11 criterion 6, first half."""
    make_cv(session, career.first_profile, career.first_track, draft=own(career))
    login(client, career.first.email)
    response = post(client, career)
    location = response.headers["location"]
    calls = len(provider.calls)

    for url in (
        "/analyze",
        f"/analyze?track_id={career.first_track.id}",
        f"/analyze/cvs?track_id={career.first_track.id}",
        f"/analyze?application={location.rsplit('/', 1)[1]}",
        location,
        "/applications",
    ):
        assert client.get(url).status_code == 200, url
    assert len(provider.calls) == calls


# --- "Proponer línea" ----------------------------------------------------------------


def test_propose_ranks_the_tracks_by_their_latest_cv_with_one_cached_call(
    client, session, career, provider
):
    """F11.11 criterion 6, second half: at most the JD extraction, none on repeat."""
    other = second_track(session, career)
    make_cv(session, career.first_profile, career.first_track, name="datos.docx",
            draft=own(career))
    make_cv(session, career.first_profile, other, name="bi.docx",
            draft=draft_dict("Armé tableros ejecutivos", headline="BI Analyst"))
    login(client, career.first.email)

    first = client.post("/analyze/propose-track", data={"jd_text": POSTING})
    extraction = len(provider.calls_for("JDProposal"))
    calls = len(provider.calls)
    again = client.post("/analyze/propose-track", data={"jd_text": POSTING})

    assert first.status_code == again.status_code == 200
    assert extraction == 1 and len(provider.calls) == calls, "none on repeat"
    assert [c["response_format"]["json_schema"]["name"] for c in provider.calls] == ["JDProposal"]
    page = first.text
    assert "estimación sin evaluar tu evidencia" in page
    assert "Título" in page and "Palabras clave" in page
    box = re.search(r'id="track-proposal".*?</div>', page, re.S).group(0)
    assert "datos.docx" in box and "bi.docx" in box
    assert box.index("Analista de datos") < box.index("BI Analyst"), "the better title leads"
    assert re.search(rf'<option value="{career.first_track.id}"[^>]*selected', page)
    assert session.query(Application).count() == 0, "a ranking is not an analysis"


def test_propose_without_any_cv_says_so(client, session, career, provider):
    second_track(session, career)
    login(client, career.first.email)

    page = client.post("/analyze/propose-track", data={"jd_text": POSTING}).text

    assert "Ninguna de tus líneas tiene un CV" in page


def test_propose_needs_the_posting(client, session, career, provider):
    second_track(session, career)
    login(client, career.first.email)

    page = client.post("/analyze/propose-track", data={"jd_text": " "}).text

    assert "Pega el texto de la oferta" in page and provider.calls == []


# --- stored recommendations still render ----------------------------------------------


def test_a_report_stored_with_a_recommendation_still_renders_it(
    client, session, career, provider
):
    analysis = recommend(career.first_profile.id, session, jd_text=POSTING)
    application = create_application(
        career.first_profile.id, session, jd_text=POSTING, jd_hash=analysis.jd_hash,
        report=analysis.report, weights_version=analysis.weights_version,
        prompt_versions=analysis.prompt_versions, token_cost_usd=analysis.cost_usd,
        track_id=career.first_track.id,
    )
    session.commit()
    login(client, career.first.email)

    page = client.get(f"/applications/{application.id}").text

    assert "Recomendación de línea de carrera" in page
    assert session.query(LlmCall).count() > 0
