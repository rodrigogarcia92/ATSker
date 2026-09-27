"""F7.1's track recommendation: one posting, several tracks, one stored answer.

The provider is stubbed at `client._post` and answers by schema name, so the two
posting-level calls can be counted: the whole point of the stage is that they are
made once however many tracks are graded.
"""

import json
import re
from dataclasses import replace
from decimal import Decimal

import pytest

from src.analysis import analyze
from src.bullets import create_bullet
from src.extract import client as extract_client
from src.models import Application, LlmCall
from src.recommend import MAX_GRADED, recommend, recommendation_payload
from src.tracks import (
    create_track,
    get_track,
    list_tracks,
    set_track_active,
    set_track_bullets,
)
from tests.conftest import login
from tests.unit.test_analysis import POSTING, PROPOSAL, QUERIES

# The stub grades `python` by what the track's own bullets say: a line with this in
# it is demonstrated, one without it is only applied. That is how three tracks of the
# same career end up with three different scores without three fixtures.
STRONG = "con resultados medibles"

ID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


class Ranking:
    """The four calls an analysis makes, with the grading tied to the bullets sent."""

    def __init__(self):
        self.calls: list[dict] = []

    def turns(self, schema: str) -> int:
        return sum(
            1 for call in self.calls if call["response_format"]["json_schema"]["name"] == schema
        )

    def __call__(self, payload: dict, api_key: str) -> dict:
        self.calls.append(payload)
        name = payload["response_format"]["json_schema"]["name"]
        user = payload["messages"][1]["content"]
        if name == "JDProposal":
            answer: dict = json.loads(PROPOSAL)
        elif name == "BooleanQuerySet":
            answer = json.loads(QUERIES)
        elif name == "EvidenceGrading":
            found = ID.search(user)
            answer = {
                "grades": [
                    {
                        "index": 0,
                        # 2 to 3: never 1, or a must-have below the evidence bar would
                        # be a second gap and the interpretation stub answers one.
                        "level": max(2, min(3, 1 + user.count(STRONG))),
                        "basis": "direct",
                        "source": "bullet",
                        "evidence_id": found.group(0) if found else None,
                        "transfer_reason": None,
                    },
                    {"index": 1, "level": 0, "basis": "none", "source": None},
                ],
                "note": "",
            }
        elif name == "GapInterpretation":
            answer = {
                "gaps": [
                    {
                        "requirement": "machine learning",
                        "blocking": False,
                        "interpretation": "Mencionado sin una historia que lo demuestre.",
                    }
                ],
                "warning": {"text": "", "handling": ""},
                "not_found": "",
            }
        else:  # pragma: no cover - the analysis makes no other call
            raise AssertionError(f"unexpected call {name}")
        return {
            "choices": [{"message": {"content": json.dumps(answer)}}],
            "usage": {"prompt_tokens": 200, "completion_tokens": 20, "cost": "0.0001"},
        }


@pytest.fixture
def stub(monkeypatch, test_settings) -> Ranking:
    ranking = Ranking()
    monkeypatch.setattr(extract_client, "_post", ranking)
    return ranking


def make_track(session, career, name: str, texts: list[str], *, kind: str | None = None):
    """One track selecting one bullet per text, all under the career's own role."""
    track = create_track(
        career.first_profile.id,
        session,
        name=name,
        applies_when=f"Para {name}",
        lang="es",
        organisation_kind=kind,
    )
    ids = [
        create_bullet(
            career.first_profile.id,
            session,
            role_id=career.first_role.id,
            text_es=text,
            text_en=None,
            chips=["python"],
        ).id
        for text in texts
    ]
    set_track_bullets(career.first_profile.id, session, track.id, ids)
    session.commit()
    return track


def recommendation_of(analysis) -> dict:
    return analysis.report["recommendation"]


def retire(session, career) -> None:
    """The career fixture's own track: a recommendation test brings its own."""
    set_track_active(career.first_profile.id, session, career.first_track.id, active=False)
    session.commit()


def leading(analysis, skills: float):
    """The same report with a bigger Skills number, for a close-call fixture."""
    report = dict(analysis.report)
    score = dict(report["score"])
    sub_scores = {name: dict(value) for name, value in score["sub_scores"].items()}
    sub_scores["skills"]["value"] = min(1.0, float(sub_scores["skills"]["value"]) + skills)
    score["sub_scores"] = sub_scores
    score["weighted"] = score["weighted"] + 0.40 * skills
    score["uncapped"] = round(100 * score["weighted"])
    score["capped"] = min(score["uncapped"], score["cap"] or score["uncapped"])
    report["score"] = score
    return replace(analysis, report=report)


def test_three_tracks_are_ranked_with_a_margin(session, career, stub):
    """The strongest track wins, the table is ordered, and the margin is a number."""
    profile_id = career.first_profile.id
    retire(session, career)
    strong = make_track(session, career, "Fuerte", [f"Python {STRONG}", f"Análisis {STRONG}"])
    middle = make_track(session, career, "Media", [f"Python {STRONG}", "Reportes semanales"])
    weak = make_track(
        session, career, "Débil", ["Cuidé plantas y ordené la oficina", "Toqué la guitarra"]
    )

    analysis = recommend(profile_id, session, jd_text=POSTING, company="Banco Demo")

    payload = recommendation_of(analysis)
    rows = payload["candidates"]
    assert [row["name"] for row in rows][0] == "Fuerte"
    assert [row["chosen"] for row in rows] == [True, False, False]
    assert [row["job_match"] for row in rows] == sorted(
        (row["job_match"] for row in rows), reverse=True
    )
    assert payload["margin"] == rows[0]["job_match"] - rows[1]["job_match"] > 0
    # The winner's own analysis is what is stored, and the report says which track.
    assert analysis.report["track"]["name"] == "Fuerte"
    assert analysis.report["score"]["capped"] == rows[0]["job_match"]
    assert set(name for name in (strong.name, middle.name, weak.name)) == {
        row["name"] for row in rows
    }
    assert stub.turns("EvidenceGrading") == 3, "one grading call per graded track"


def close_call_fixture(session, career, stub):
    """Two real tracks four points apart, so the tie-break has something to say."""
    profile_id = career.first_profile.id
    retire(session, career)
    first = make_track(session, career, "Primero", [f"Python {STRONG}"], kind="banco")
    second = make_track(session, career, "Segundo", ["Reportes y tableros"], kind="consultora")
    analysis = analyze(profile_id, session, jd_text=POSTING, track=first)
    return first, second, analysis


def test_a_margin_under_five_names_the_sub_score_that_decided_it(session, career, stub):
    """F7.1: under five points the report names the sub-score that did it."""
    first, second, analysis = close_call_fixture(session, career, stub)
    # +0.10 of Skills is +4 points of Job Match: the difference is small and known.
    payload = recommendation_payload(
        [(first, leading(analysis, 0.10)), (second, analysis)],
        not_graded=(),
        company=None,
        cost_usd=Decimal("0"),
    )

    assert payload["margin"] == 4 < 5
    assert payload["tie_break"] == {
        "sub_score": "skills",
        "delta": 10,
        "organisation_track": None,
    }
    assert payload["justification"]["sub_score"] == "skills"
    assert payload["justification"]["delta"] == 10
    assert payload["justification"]["track"] == "Primero"
    assert payload["justification"]["runner_up"] == "Segundo"
    assert payload["candidates"][0]["chosen"] is True


def test_a_wide_margin_names_no_tie_break(session, career, stub):
    first, second, analysis = close_call_fixture(session, career, stub)
    payload = recommendation_payload(
        [(first, leading(analysis, 0.30)), (second, analysis)],
        not_graded=(),
        company=None,
        cost_usd=Decimal("0"),
    )

    assert payload["margin"] == 12
    assert payload["tie_break"] is None
    assert payload["justification"]["delta"] == 30


def test_the_organisation_axis_breaks_the_tie_when_the_company_names_it(session, career, stub):
    first, second, analysis = close_call_fixture(session, career, stub)

    payload = recommendation_payload(
        [(first, leading(analysis, 0.10)), (second, analysis)],
        not_graded=(),
        company="Banco Demo, Lima",
        cost_usd=Decimal("0"),
    )

    assert payload["margin"] < 5
    assert payload["tie_break"]["organisation_track"] == "Primero"


def test_only_six_tracks_are_graded_and_the_rest_are_listed(session, career, stub):
    """F7.1's cap: the six with the highest title + keywords, chosen without a model."""
    profile_id = career.first_profile.id
    retire(session, career)
    words = [
        "Analista de datos con Python y machine learning, reportes para dirección",
        "Analista de datos con Python y machine learning",
        "Analista de datos con Python",
        "Analista de datos y reportes",
        "Python y machine learning",
        "Reportes para dirección",
        "Cuidé plantas y ordené la oficina",
        "Toqué la guitarra los domingos",
    ]
    for index, text in enumerate(words):
        make_track(session, career, f"Puesto {index}", [text])

    analysis = recommend(profile_id, session, jd_text=POSTING)

    payload = recommendation_of(analysis)
    assert len(payload["candidates"]) == MAX_GRADED
    assert [row["name"] for row in payload["not_graded"]] == ["Puesto 6", "Puesto 7"]
    assert stub.turns("EvidenceGrading") == MAX_GRADED
    assert len(list_tracks(profile_id, session, active_only=True)) == 8


def test_the_posting_is_extracted_and_its_queries_derived_once(session, career, stub):
    """F7.1: two of the calls are about the posting, so three tracks cost three more."""
    profile_id = career.first_profile.id
    retire(session, career)
    for name in ("Uno", "Dos", "Tres"):
        make_track(session, career, name, [f"Python {STRONG} para {name}"])

    recommend(profile_id, session, jd_text=POSTING)

    assert stub.turns("JDProposal") == 1
    assert stub.turns("BooleanQuerySet") == 1
    assert stub.turns("EvidenceGrading") == 3
    purposes = [call.purpose for call in session.query(LlmCall).order_by(LlmCall.id)]
    assert purposes.count("jd_extract") == 1
    assert purposes.count("boolean_queries") == 1


def test_the_cost_is_the_sum_of_every_candidate_call(session, career, stub):
    """D.7.1: the total is the calls the report lists, each counted once.

    Three tracks make eight calls — one extraction, one derivation, and a grading and
    a gap interpretation each — but the two repeat gap interpretations are cache hits
    at $0, so the request costs $0.0006, not $0.0001 per listed call.
    """
    profile_id = career.first_profile.id
    retire(session, career)
    for name in ("Uno", "Dos", "Tres"):
        make_track(session, career, name, [f"Python {STRONG} para {name}"])

    analysis = recommend(profile_id, session, jd_text=POSTING)

    reported = analysis.report["llm"]["calls"]
    purposes = [call["purpose"] for call in reported]
    assert purposes.count("evidence_grade") == 3
    assert len(purposes) == 8
    assert analysis.cost_usd == sum(
        (Decimal(call["cost_usd"]) for call in reported), Decimal("0")
    ), "the number is the listed calls, never a per-candidate sum"
    assert analysis.cost_usd == Decimal("0.0006")
    assert analysis.report["llm"]["cost_usd"] == str(analysis.cost_usd)
    assert analysis.report["recommendation"]["cost_usd"] == str(analysis.cost_usd)


def test_the_shared_extraction_is_counted_once(session, career, stub):
    """D.7.1: the posting's own call is one call, however many tracks were graded."""
    profile_id = career.first_profile.id
    retire(session, career)
    for name in ("Uno", "Dos", "Tres"):
        make_track(session, career, name, [f"Python {STRONG} para {name}"])

    analysis = recommend(profile_id, session, jd_text=POSTING)

    reported = analysis.report["llm"]["calls"]
    extraction = [call for call in reported if call["purpose"] == "jd_extract"]
    assert len(extraction) == 1
    others = sum(
        (Decimal(call["cost_usd"]) for call in reported if call["purpose"] != "jd_extract"),
        Decimal("0"),
    )
    assert analysis.cost_usd - others == Decimal(extraction[0]["cost_usd"])


def test_the_rows_and_the_shared_cost_add_up_to_the_total(session, career, stub):
    """D.7.1: a row is its own calls; the posting's two are reported once, apart."""
    profile_id = career.first_profile.id
    retire(session, career)
    for name in ("Uno", "Dos", "Tres"):
        make_track(session, career, name, [f"Python {STRONG} para {name}"])

    analysis = recommend(profile_id, session, jd_text=POSTING)

    payload = analysis.report["recommendation"]
    rows = sum((Decimal(row["cost_usd"]) for row in payload["candidates"]), Decimal("0"))
    assert Decimal(payload["shared_cost_usd"]) == Decimal("0.0002"), "extraction + queries"
    assert rows + Decimal(payload["shared_cost_usd"]) == Decimal(payload["cost_usd"])
    assert payload["cost_usd"] == str(analysis.cost_usd)


def test_a_single_track_analysis_is_unchanged(session, career, stub):
    """The refactor's promise: same calls, same order, no recommendation."""
    track = make_track(session, career, "Solo", [f"Python {STRONG}"])

    analysis = analyze(career.first_profile.id, session, jd_text=POSTING, track=track)

    assert "recommendation" not in analysis.report
    assert [call["purpose"] for call in analysis.report["llm"]["calls"]] == [
        "jd_extract",
        "evidence_grade",
        "boolean_queries",
        "gap_interpret",
    ]
    assert stub.turns("EvidenceGrading") == 1


def test_a_recommendation_without_tracks_is_a_no_track_analysis(session, career, stub):
    """A ticked box and nothing to choose between is not an error."""
    retire(session, career)
    analysis = recommend(career.first_profile.id, session, jd_text=POSTING)

    payload = recommendation_of(analysis)
    assert payload["candidates"] == []
    assert payload["margin"] is None and payload["tie_break"] is None
    assert payload["justification"] is None
    assert "track" not in analysis.report


def test_the_route_recommends_and_stores_the_winner(client, session, career, stub):
    """F7.1 over HTTP: no track chosen, the box ticked, the winner stored."""
    profile_id = career.first_profile.id
    retire(session, career)
    winner = make_track(
        session, career, "Fuerte", [f"Python {STRONG}", f"Análisis {STRONG}"]
    )
    make_track(session, career, "Débil", ["Reportes semanales"])
    login(client, career.first.email)

    posted = client.post(
        "/analyze",
        data={"jd_text": POSTING, "company": "Banco Demo", "recommend": "on"},
        follow_redirects=False,
    )

    assert posted.status_code == 303
    page = client.get(posted.headers["location"]).text
    assert "Recomendación de puesto" in page
    assert "Elegido" in page
    assert "Fuerte" in page
    application = session.query(Application).one()
    assert application.track_id == winner.id
    assert application.report["recommendation"]["margin"] is not None
    assert get_track(profile_id, session, application.track_id).name == "Fuerte"


def test_the_route_without_the_box_analyses_without_a_track(client, session, career, stub):
    """Unticked, the page is the analysis the app has always produced."""
    make_track(session, career, "Fuerte", [f"Python {STRONG}", f"Análisis {STRONG}"])
    login(client, career.first.email)

    posted = client.post(
        "/analyze", data={"jd_text": POSTING, "recommend": "off"}, follow_redirects=False
    )

    assert posted.status_code == 303
    page = client.get(posted.headers["location"]).text
    assert "Recomendación de puesto" not in page
    assert stub.turns("EvidenceGrading") == 1
