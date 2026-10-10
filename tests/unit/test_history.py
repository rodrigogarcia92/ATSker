"""The application history table (PRD F9).

Every analysis is already persisted; this is the view over it — sortable server-side,
with the weights version beside each score, because two scores under different weights
are not comparable and the table must not pretend otherwise.
"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from src.applications import (
    OUTCOMES,
    list_applications,
    set_application_outcome,
    stale_application_count,
)
from src.models import Application
from tests.conftest import login


def application_fixture(
    profile_id,
    *,
    title: str,
    company: str,
    score: int | None,
    weights_version: str = "w2",
    outcome: str = "no_reply",
    created_at: datetime | None = None,
    track_id: uuid.UUID | None = None,
    track_name: str | None = None,
) -> Application:
    """One stored analysis with the parts the table reads."""
    report: dict = {"score": {"capped": score, "uncapped": score, "sub_scores": {}}}
    if track_name is not None:
        report["track"] = {"id": str(track_id or uuid.uuid4()), "name": track_name}
    return Application(
        profile_id=profile_id,
        company=company,
        title=title,
        jd_text="Una oferta",
        jd_hash=f"sha256:{uuid.uuid4().hex}",
        report=report,
        weights_version=weights_version,
        prompt_versions={},
        token_cost_usd=Decimal("0.000123"),
        outcome=outcome,
        created_at=created_at or datetime.now(UTC),
        track_id=track_id,
    )


@pytest.fixture
def history(session, career) -> list[Application]:
    """Three analyses of Ana's: two scored, one from before scores were comparable."""
    base = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)
    rows = [
        application_fixture(
            career.first_profile.id,
            title="Data Engineer",
            company="Globex",
            score=71,
            created_at=base + timedelta(days=2),
            track_id=career.first_track.id,
        ),
        application_fixture(
            career.first_profile.id,
            title="Analista de datos",
            company="Banco Demo 1",
            score=34,
            created_at=base + timedelta(days=1),
            outcome="interview",
        ),
        application_fixture(
            career.first_profile.id,
            title="Analista antiguo",
            company="Acme",
            score=None,
            weights_version="w1",
            created_at=base,
        ),
        # Someone else's analysis: never in this table.
        application_fixture(
            career.second_profile.id,
            title="Riesgo",
            company="Globex",
            score=99,
            created_at=base + timedelta(days=3),
        ),
    ]
    session.add_all(rows)
    session.commit()
    return rows


def ordered_titles(rows: list[dict]) -> list[str]:
    return [str(row["title"]) for row in rows]


def test_the_history_lists_every_analysis_newest_first(session, career, history):
    rows = list_applications(career.first_profile.id, session)

    assert ordered_titles(rows) == ["Data Engineer", "Analista de datos", "Analista antiguo"]
    assert all(row["company"] != "Riesgo" for row in rows), "another profile's row"


def test_a_score_is_shown_with_the_weights_it_was_computed_under(session, career, history):
    rows = {row["title"]: row for row in list_applications(career.first_profile.id, session)}

    assert rows["Data Engineer"]["score"] == 71
    assert rows["Data Engineer"]["weights_version"] == "w2"
    assert rows["Analista antiguo"]["score"] is None
    assert rows["Analista antiguo"]["weights_version"] == "w1", "a w1 report says so"
    assert rows["Data Engineer"]["track"] == career.first_track.name


def test_sorting_by_score_puts_an_unscored_analysis_last(session, career, history):
    profile_id = career.first_profile.id

    descending = list_applications(profile_id, session, sort="score", direction="desc")
    ascending = list_applications(profile_id, session, sort="score", direction="asc")

    assert ordered_titles(descending) == ["Data Engineer", "Analista de datos", "Analista antiguo"]
    assert ordered_titles(ascending) == ["Analista de datos", "Data Engineer", "Analista antiguo"]
    assert ordered_titles(ascending)[-1] == "Analista antiguo", "absent is not zero"


def test_sorting_by_company_and_by_track_and_by_outcome(session, career, history):
    profile_id = career.first_profile.id

    assert ordered_titles(
        list_applications(profile_id, session, sort="company", direction="asc")
    ) == [
        "Analista antiguo",
        "Analista de datos",
        "Data Engineer",
    ]
    assert ordered_titles(
        list_applications(profile_id, session, sort="track", direction="asc")
    ) == [
        "Analista antiguo",
        "Analista de datos",
        "Data Engineer",
    ], "no track sorts first, oldest first among them; the named track comes after"
    assert ordered_titles(
        list_applications(profile_id, session, sort="outcome", direction="desc")
    ) == ["Data Engineer", "Analista antiguo", "Analista de datos"], (
        "the stored value sorts, newest first inside a tie"
    )


def test_an_unknown_sort_falls_back_to_the_default_view(session, career, history):
    rows = list_applications(
        career.first_profile.id, session, sort="drop table", direction="sideways"
    )

    assert ordered_titles(rows) == ["Data Engineer", "Analista de datos", "Analista antiguo"]


def test_the_track_column_uses_the_report_snapshot_after_the_track_is_gone(session, career):
    """A deleted track must not blank the column: the report recorded the name (F4)."""
    session.add(
        application_fixture(
            career.first_profile.id,
            title="Antiguo",
            company="Acme",
            score=50,
            track_name="Analista de datos",
        )
    )
    session.commit()

    rows = list_applications(career.first_profile.id, session)

    assert rows[0]["track"] == "Analista de datos"


def test_the_outcome_is_editable_and_only_the_five_values_are_outcomes(session, career, history):
    application = history[0]

    assert (
        set_application_outcome(career.first_profile.id, session, application.id, outcome="offer")
        is not None
    )
    session.commit()

    assert application.outcome == "offer"
    assert (
        set_application_outcome(career.first_profile.id, session, application.id, outcome="ghosted")
        is not None
    ), "the data layer takes what the route already validated"
    assert OUTCOMES == ("no_reply", "screen", "interview", "offer", "rejected")


def test_outcome_data_access_is_scoped_to_the_profile(session, career, history):
    other = [row for row in history if row.profile_id == career.second_profile.id][0]

    assert (
        set_application_outcome(career.first_profile.id, session, other.id, outcome="offer") is None
    )
    assert other.outcome == "no_reply"


def test_the_history_page_renders_the_table_and_its_links(client, session, career, history):
    login(client, career.first.email)

    page = client.get("/applications").text

    assert "Historial" in page
    assert "Data Engineer" in page and "Analista de datos" in page
    assert f'href="/applications/{history[0].id}"' in page, "each row links to its report"
    assert "71" in page and "w2" in page, "the score and the weights it was computed under"
    assert 'value="interview"' in page and "selected" in page
    assert "Sin respuesta" in page, "the outcome labels are the user's language"
    assert "Riesgo" not in page, "another profile's analysis is not in the table"
    assert "max-w-5xl" in page, "the history table uses the wider column (N6.6)"
    assert "max-w-full overflow-x-auto" in page, "the table scrolls inside its own box"
    assert "relative mt-6 max-w-full overflow-x-auto" in page, (
        "the sr-only label is positioned, not page-wide (F.0)"
    )


def test_the_history_carries_the_sub_scores_both_scans_prompts_and_cost(
    client, session, career, history
):
    """F9's remaining columns, each from the stored report and nothing else."""
    application = application_fixture(
        career.first_profile.id,
        title="Con todo",
        company="Banco Demo 1",
        score=71,
        created_at=datetime(2026, 9, 20, 15, 0, tzinfo=UTC),
    )
    application.report["score"]["sub_scores"] = {
        "skills": {"value": 0.82},
        "experience": {"value": 0.51},
        "title": {"value": 0.33},
        "keywords": {"value": 0.64},
    }
    application.scan_readability = {
        "cap": 40,
        "cap_reason": "invisible_text",
        "findings": [{"check": "invisible_text"}],
    }
    application.scan_boolean = {
        "checked": True,
        "queries": [{"passed": True}, {"passed": False}],
    }
    application.prompt_versions = {"jd_extract": "jd_extract_v2"}
    session.add(application)
    session.commit()

    rows = {row["title"]: row for row in list_applications(career.first_profile.id, session)}
    row = rows["Con todo"]
    assert row["sub_scores"] == {"skills": 82, "experience": 51, "title": 33, "keywords": 64}
    assert row["readability"] == {"cap": 40, "findings": 1}
    assert row["boolean"] == {"queries": 2, "passed": False}
    assert row["token_cost_usd"] == Decimal("0.000123")

    login(client, career.first.email)
    page = client.get("/applications").text
    assert "82" in page and "51" in page and "33" in page and "64" in page
    assert "≤ 40" in page, "the readability verdict is the cap it applied"
    assert "No apareces" in page, "one failing query makes the search verdict a no"
    assert "jd_extract=jd_extract_v2" in page
    assert "$0.000123" in page


def test_an_old_report_renders_a_dash_for_every_column_it_predates(session, career, history):
    """A `w1` analysis has no sub-scores, no scans and no prompt versions — and none
    of them renders as a zero."""
    rows = list_applications(career.first_profile.id, session)
    old = next(row for row in rows if row["title"] == "Analista antiguo")
    assert old["sub_scores"] == {
        "skills": None,
        "experience": None,
        "title": None,
        "keywords": None,
    }
    assert old["readability"] is None and old["boolean"] is None
    assert old["prompt_versions"] == {}


def test_sorting_arrives_from_the_url_and_an_unknown_column_does_not_raise(client, career, history):
    login(client, career.first.email)

    by_score = client.get("/applications?sort=score&dir=asc").text
    unknown = client.get("/applications?sort=nonsense&dir=asc")

    assert by_score.index("Analista de datos") < by_score.index("Data Engineer")
    assert unknown.status_code == 200
    assert "Data Engineer" in unknown.text


def test_the_outcome_route_stores_the_value_it_was_given(client, session, career, history):
    login(client, career.first.email)
    application = history[0]

    posted = client.post(
        f"/applications/{application.id}/outcome",
        data={"outcome": "screen"},
        follow_redirects=False,
    )

    assert posted.status_code == 303
    assert posted.headers["location"] == "/applications"
    session.expire_all()
    assert application.outcome == "screen"


def test_the_outcome_route_refuses_anything_else_and_another_profiles_row(
    client, session, career, history
):
    login(client, career.first.email)
    mine = history[0]
    theirs = [row for row in history if row.profile_id == career.second_profile.id][0]

    unknown = client.post(
        f"/applications/{mine.id}/outcome", data={"outcome": "ghosted"}, follow_redirects=False
    )
    foreign = client.post(
        f"/applications/{theirs.id}/outcome", data={"outcome": "offer"}, follow_redirects=False
    )

    assert unknown.status_code == 400
    assert foreign.status_code == 404
    session.expire_all()
    assert mine.outcome == "no_reply" and theirs.outcome == "no_reply"


def test_the_nav_reaches_the_history(client, career, history):
    login(client, career.first.email)

    page = client.get("/dashboard").text

    assert '<a href="/applications"' in page
    assert page.index('href="/analyze"') < page.index('href="/applications"')
    assert page.index('href="/applications"') < page.index('href="/import"')


# --- F.1: the outcome nudge and its filter -----------------------------------------


def aged(days: int) -> datetime:
    return datetime.now(UTC) - timedelta(days=days)


def test_the_stale_count_sees_only_old_unanswered_rows(session, career):
    session.add_all(
        [
            application_fixture(
                career.first_profile.id,
                title="Vieja sin resultado",
                company="Acme",
                score=50,
                created_at=aged(30),
            ),
            application_fixture(
                career.first_profile.id,
                title="Reciente sin resultado",
                company="Acme",
                score=50,
                created_at=aged(2),
            ),
            application_fixture(
                career.first_profile.id,
                title="Vieja con entrevista",
                company="Acme",
                score=50,
                outcome="interview",
                created_at=aged(30),
            ),
            application_fixture(
                career.second_profile.id,
                title="De la otra persona",
                company="Globex",
                score=50,
                created_at=aged(30),
            ),
        ]
    )
    session.commit()

    assert stale_application_count(career.first_profile.id, session) == 1
    assert stale_application_count(career.second_profile.id, session) == 1, "owner-scoped"


def test_the_history_filter_narrows_to_no_outcome_or_one_value(session, career, history):
    profile_id = career.first_profile.id

    none = list_applications(profile_id, session, outcome="none")
    assert [row["title"] for row in none] == ["Data Engineer", "Analista antiguo"]

    interview = list_applications(profile_id, session, outcome="interview")
    assert [row["title"] for row in interview] == ["Analista de datos"]

    unknown = list_applications(profile_id, session, outcome="ghosted")
    assert len(unknown) == 3, "an unknown value is ignored, not an empty table"


def test_the_filter_arrives_from_the_url_and_survives_a_sort(client, career, history):
    login(client, career.first.email)

    filtered = client.get("/applications?outcome=none&sort=date&dir=asc").text

    interview = next(row for row in history if row.outcome == "interview")
    assert f'href="/applications/{interview.id}"' not in filtered, (
        "an interview is not waiting on a result"
    )
    for row in history:
        if row.profile_id == career.first_profile.id and row.outcome == "no_reply":
            assert f'href="/applications/{row.id}"' in filtered
    assert "Mostrando solo" in filtered
    assert "outcome=none" in filtered, "the sort links keep the filter"


def test_the_dashboard_nudges_about_the_old_unanswered_analyses(client, session, career):
    login(client, career.first.email)
    assert "sin resultado" not in client.get("/dashboard").text, "nothing stale yet"

    session.add(
        application_fixture(
            career.first_profile.id,
            title="Vieja sin resultado",
            company="Acme",
            score=50,
            created_at=aged(30),
        )
    )
    session.commit()

    page = client.get("/dashboard").text

    assert "1 análisis de hace más de 14 días sin resultado" in page
    assert "/applications?outcome=none&sort=date&dir=asc" in page
