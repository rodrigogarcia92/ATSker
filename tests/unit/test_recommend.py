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
        chosen_track_id=first.id,
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


def recommend_box(html: str) -> str | None:
    """The `recommend` checkbox's own tag, or None when the form does not draw it."""
    match = re.search(r"<input[^>]*name=\"recommend\"[^>]*>", html)
    return match.group(0) if match else None


def test_a_fresh_form_ticks_the_box_with_two_active_tracks(client, session, career, stub):
    """D.7.2: two tracks is a choice to make, so the default is on."""
    retire(session, career)
    make_track(session, career, "Uno", ["Python con resultados medibles"])
    make_track(session, career, "Dos", ["Reportes semanales"])
    login(client, career.first.email)

    box = recommend_box(client.get("/analyze").text)

    assert box is not None and "checked" in box


def selected_option(html: str, track_id) -> bool:
    """Whether the track select draws this track's `<option>` as selected."""
    match = re.search(rf"<option[^>]*value=\"{track_id}\"[^>]*>", html)
    return match is not None and "selected" in match.group(0)


def test_a_fresh_form_preselects_the_only_active_track_and_draws_no_box(
    client, session, career, stub
):
    """F7.1 (2026-10-04): one track is nothing to choose between, so it is chosen."""
    retire(session, career)
    only = make_track(session, career, "Único", ["Python con resultados medibles"])
    login(client, career.first.email)

    page = client.get("/analyze").text

    assert recommend_box(page) is None
    assert selected_option(page, only.id)


def test_the_prefilled_form_also_preselects_the_only_active_track(client, session, career, stub):
    retire(session, career)
    only = make_track(session, career, "Único", ["Python con resultados medibles"])
    login(client, career.first.email)
    posted = client.post("/analyze", data={"jd_text": POSTING}, follow_redirects=False)
    application = posted.headers["location"].rsplit("/", 1)[1]

    page = client.get(f"/analyze?application={application}").text

    assert selected_option(page, only.id)


def test_a_chosen_track_renders_the_box_unticked_disabled_with_its_hint(
    client, session, career, stub
):
    """F7.1: a re-rendered form with a track keeps the track; the box does not apply."""
    retire(session, career)
    first = make_track(session, career, "Uno", ["Python con resultados medibles"])
    make_track(session, career, "Dos", ["Reportes semanales"])
    login(client, career.first.email)

    page = client.post("/analyze", data={"jd_text": "  ", "track_id": str(first.id)}).text

    box = recommend_box(page)
    assert box is not None and "disabled" in box and "checked" not in box
    assert selected_option(page, first.id)
    assert "No aplica: elegiste un puesto." in page
    assert "hidden" not in re.search(r'<p id="recommend-na"[^>]*>', page).group(0)


def test_the_hint_for_no_track_shows_under_an_unticked_box(client, session, career, stub):
    retire(session, career)
    make_track(session, career, "Uno", ["Python con resultados medibles"])
    make_track(session, career, "Dos", ["Reportes semanales"])
    login(client, career.first.email)

    unticked = client.post("/analyze", data={"jd_text": "  ", "recommend": "off"}).text
    fresh = client.get("/analyze").text

    hint = "Sin puesto objetivo, al escribir la carta tendrás que elegir uno."
    assert hint in unticked and hint in fresh
    assert "hidden" not in re.search(r'<p id="recommend-off"[^>]*>', unticked).group(0)
    assert "hidden" in re.search(r'<p id="recommend-off"[^>]*>', fresh).group(0)


def test_the_form_script_follows_the_track_select(client, session, career, stub):
    """Markup test: choosing a track unchecks and disables the box, clearing re-checks it."""
    retire(session, career)
    make_track(session, career, "Uno", ["Python con resultados medibles"])
    make_track(session, career, "Dos", ["Reportes semanales"])
    login(client, career.first.email)

    page = client.get("/analyze").text
    script = page[page.index("// F7.1: \"Recomendar puesto\" follows") :]
    chosen, cleared = script.split("} else {", 1)

    assert "if (select.value) {" in chosen
    assert "box.checked = false;" in chosen and "box.disabled = true;" in chosen
    assert "box.disabled = false;" in cleared and "box.checked = true;" in cleared
    assert "addEventListener('change'" in script


def test_a_fresh_form_draws_no_box_without_tracks(client, session, career, stub):
    retire(session, career)
    login(client, career.first.email)

    assert recommend_box(client.get("/analyze").text) is None


def test_an_unticked_box_survives_a_re_render(client, session, career, stub):
    """D.7.2: the default never overrides a decision the user already made."""
    retire(session, career)
    make_track(session, career, "Uno", ["Python con resultados medibles"])
    make_track(session, career, "Dos", ["Reportes semanales"])
    login(client, career.first.email)

    page = client.post("/analyze", data={"jd_text": "  ", "recommend": "off"}).text

    box = recommend_box(page)
    assert box is not None and "checked" not in box, "the error came back, the untick too"


def test_an_unticked_box_with_two_tracks_runs_the_plain_analysis(client, session, career, stub):
    """D.7.2: unticked and no track chosen is the no-track analysis, not a ranking."""
    retire(session, career)
    make_track(session, career, "Uno", ["Python con resultados medibles"])
    make_track(session, career, "Dos", ["Reportes semanales"])
    login(client, career.first.email)

    posted = client.post(
        "/analyze", data={"jd_text": POSTING, "recommend": "off"}, follow_redirects=False
    )

    assert posted.status_code == 303
    page = client.get(posted.headers["location"]).text
    assert "Recomendación de puesto" not in page
    application = session.query(Application).one()
    assert "recommendation" not in application.report
    assert application.track_id is None
    assert stub.turns("EvidenceGrading") == 1


# D.7.3's tie fixture: two tracks that tie on Job Match, in the order the pre-rank
# puts them — "Zeta" leads because its shorter line scores the keywords higher, and
# the pre-rank is title + keywords. `BASE` and `PADDED` differ by four words nobody
# asked for, which is under the point of Job Match but enough to order the pre-rank.
BASE = "Analista de datos con Python y machine learning, reportes para dirección"
PADDED = BASE + " extra extra extra extra"
TIE_FIXTURE = {
    "Zeta": ["Python con resultados medibles", BASE],
    "Alfa": ["Python con resultados medibles", PADDED],
}
TIE_FILLERS = [
    "Reportes semanales para dirección",
    "Modelé el riesgo de crédito con Python",
    "Puse modelos de machine learning en producción",
    "Analista de datos con reportes",
]
TIE_OUTSIDE = ["Cuidé plantas y ordené la oficina", "Toqué la guitarra los domingos"]


def test_the_table_marks_the_track_that_was_stored(session, career, stub):
    """D.7.3: one ranking rule. On an exact Job Match tie, graded order decides, and
    the row the application was stored against is the row the table marks."""
    profile_id = career.first_profile.id
    retire(session, career)
    for name, texts in TIE_FIXTURE.items():
        make_track(session, career, name, texts)
    for index, text in enumerate(TIE_FILLERS):
        make_track(session, career, f"F{index}", [text])
    for index, text in enumerate(TIE_OUTSIDE):
        make_track(session, career, f"X{index}", [text])

    analysis = recommend(profile_id, session, jd_text=POSTING)

    payload = analysis.report["recommendation"]
    rows = payload["candidates"]
    assert [row["name"] for row in rows[:2]] == ["Zeta", "Alfa"], "a tie, and Zeta led"
    assert rows[0]["job_match"] == rows[1]["job_match"]
    assert payload["margin"] == 0, "the chosen row comes first, so the margin cannot be negative"
    assert [row["chosen"] for row in rows].count(True) == 1
    assert rows[0]["chosen"] is True
    assert rows[0]["track_id"] == analysis.report["track"]["id"], "the stored track is marked"
    assert [row["name"] for row in payload["not_graded"]] == ["X0", "X1"]


def test_the_payload_marks_the_chosen_track_and_nothing_without_one(session, career, stub):
    """D.7.3: the payload is told which row won; it does not rank a second time."""
    profile_id = career.first_profile.id
    retire(session, career)
    earlier = make_track(session, career, "Alfa", [f"Python {STRONG}"])
    later = make_track(session, career, "Zeta", [f"Python {STRONG}"])
    analysis = analyze(profile_id, session, jd_text=POSTING, track=later)
    analyses = [(earlier, analysis), (later, analysis)]

    tied = recommendation_payload(
        analyses,
        not_graded=(),
        company=None,
        cost_usd=Decimal("0"),
        chosen_track_id=later.id,
    )

    assert [row["name"] for row in tied["candidates"]] == ["Zeta", "Alfa"]
    assert [row["chosen"] for row in tied["candidates"]] == [True, False]
    assert tied["margin"] == 0

    unmarked = recommendation_payload(
        analyses, not_graded=(), company=None, cost_usd=Decimal("0")
    )

    assert [row["name"] for row in unmarked["candidates"]] == ["Alfa", "Zeta"]
    assert [row["chosen"] for row in unmarked["candidates"]] == [False, False]
    assert unmarked["margin"] == 0
