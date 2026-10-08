"""summary_v4: the exact title, three or four key skills, the CV's own summary (queue M3).

The shortlist and the checks are pure; the retry and the route run on a fake provider.
"""

import json
import uuid

import pytest

from src.extract import client as extract_client
from src.extract.prompts import SUMMARY_V3, SUMMARY_V4
from src.generate.summary_rules import (
    KeySkill,
    check_length,
    check_skills,
    check_title,
    key_skill_shortlist,
)
from src.summaries import create_summary
from src.tracks import get_track, set_track_summary
from tests.conftest import login
from tests.unit.test_generation import stored_application

ALIASES = {
    "sql": "sql",
    "python": "python",
    "tableau": "tableau",
    "power bi": "power bi",
    "excel": "excel",
    "airflow": "airflow",
}
POOL = frozenset(ALIASES.values())


def grade(requirement, level=3, basis="direct", must=True):
    return {"requirement": requirement, "level": level, "basis": basis, "must_have": must}


def report(must, nice, grades):
    return {"jd": {"must_have": must, "nice_to_have": nice}, "grades": grades}


# --- the shortlist -----------------------------------------------------------------


def test_the_shortlist_is_direct_level_two_in_pool_must_haves_first_at_most_four():
    rep = report(
        ["SQL", "Tableau", "Excel"],
        ["Python", "Airflow", "Power BI"],
        [
            grade("SQL"),
            grade("Tableau", level=1),
            grade("Excel", level=2),
            grade("Python", must=False),
            grade("Airflow", must=False),
            grade("Power BI", must=False),
        ],
    )

    shortlist = key_skill_shortlist(rep, POOL, ALIASES)

    assert [(s.wording, s.canonical) for s in shortlist] == [
        ("SQL", "sql"),
        ("Excel", "excel"),
        ("Python", "python"),
        ("Airflow", "airflow"),
    ]


def test_an_equivalent_or_transferable_credit_is_never_shortlisted():
    rep = report(
        ["SQL", "Tableau", "Excel"],
        [],
        [
            grade("SQL", basis="equivalent"),
            grade("Tableau", basis="transferable"),
            grade("Excel"),
        ],
    )

    assert [s.canonical for s in key_skill_shortlist(rep, POOL, ALIASES)] == ["excel"]


def test_a_skill_outside_the_pool_or_without_a_grade_is_not_shortlisted():
    rep = report(["SQL", "Tableau", "Mystery"], [], [grade("SQL"), grade("Tableau")])

    shortlist = key_skill_shortlist(rep, frozenset({"sql"}), ALIASES)

    assert [s.canonical for s in shortlist] == ["sql"]


# --- the checks --------------------------------------------------------------------


def test_the_title_check():
    title = "Analista de Datos"
    assert check_title("Analista de datos con SQL. Más texto.", title)["ok"], "case is ignored"
    assert check_title("Soy  ANALISTA   de datos con SQL.", title)["ok"], "whitespace is ignored"
    assert check_title("Analista de Datos.", title)["ok"]
    assert not check_title("Analista de datos.", "Analísta de datos")["ok"], "accents count"
    assert not check_title("Analista de dato con SQL.", title)["ok"]
    assert not check_title("Trabajo con SQL. Analista de datos senior.", title)["ok"], (
        "the first sentence only"
    )


def short(*names):
    return [KeySkill(name, name) for name in names]


def test_the_skill_check_counts_distinct_canonicals():
    five = short("sql", "python", "tableau", "excel", "airflow")

    def verdict(text, shortlist):
        return check_skills(text, shortlist, ALIASES)["ok"]

    assert not verdict("Uso sql y python.", five), "two is below three"
    assert not verdict("Uso sql.", five)
    assert verdict("Uso sql, python y tableau.", five)
    assert verdict("Uso sql, python, tableau y excel.", five)
    assert not verdict("Uso sql, python, tableau, excel y airflow.", five), "five is too many"
    assert not verdict("Uso sql, python y power bi.", five), "power bi is not on the shortlist"
    assert verdict("Uso sql y python.", short("sql", "python")), "a shortlist of two passes at two"
    assert not verdict("Uso sql.", short("sql", "python"))
    assert not verdict("Uso sql, python y tableau.", short("sql", "python"))


def test_the_length_check_counts_words_not_sentences():
    assert check_length(" ".join(["palabra"] * 80))["ok"]
    assert not check_length(" ".join(["palabra"] * 81))["ok"]
    assert check_length("Una. Dos. Tres. Cuatro. Cinco.")["ok"]


# --- the prompt --------------------------------------------------------------------


def test_the_v4_prompt_keeps_v3_defined_and_the_pool_as_context():
    assert SUMMARY_V4.version == "summary_v4" and SUMMARY_V3.version == "summary_v3"
    assert "Never return a list of skills" in SUMMARY_V4.system
    assert "exactly as given" in SUMMARY_V4.system
    assert "{pool}" in SUMMARY_V4.template and "{banned}" in SUMMARY_V4.template
    assert "{title}" not in SUMMARY_V4.system, "the variable data is in the user message"


# --- the route, on a fake provider -------------------------------------------------


class Queue:
    """Answers each SummaryOnly call from a list, in order, and keeps every payload."""

    def __init__(self, *texts, cites):
        self.texts = list(texts)
        self.cites = cites
        self.calls: list[dict] = []

    def __call__(self, payload, api_key):
        self.calls.append(payload)
        text = self.texts[min(len(self.calls), len(self.texts)) - 1]
        body = {"summary": text, "cites": self.cites}
        return {
            "choices": [{"message": {"content": json.dumps(body)}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 40, "cost": "0.00001"},
        }

    def user(self, index=-1) -> str:
        return self.calls[index]["messages"][-1]["content"]


GOOD = "Analista de datos que automatizó el reporte con Python."
NO_TITLE = "Automaticé el reporte con Python."


@pytest.fixture
def queue(monkeypatch, test_settings, career):
    def make(*texts):
        stub = Queue(*texts, cites=[str(career.first_bullet.id)])
        monkeypatch.setattr(extract_client, "_post", stub)
        return stub

    return make


def generate(client, application):
    return client.post(f"/applications/{application.id}/summary/generate", data={"dialog": "1"})


def test_a_passing_first_answer_makes_exactly_one_call(client, session, career, queue):
    stub = queue(GOOD)
    application = stored_application(session, career)
    login(client, career.first.email)

    generate(client, application)

    assert len(stub.calls) == 1
    assert "Analista de datos" in stub.user(), "the title travels in the user message"


def test_a_failed_title_makes_one_retry_that_names_the_rule(client, session, career, queue):
    stub = queue(NO_TITLE, GOOD)
    application = stored_application(session, career)
    login(client, career.first.email)

    page = generate(client, application).text

    assert len(stub.calls) == 2
    assert "title exactly as given" in stub.user(1) and NO_TITLE in stub.user(1)
    assert "broke these rules" not in stub.user(0)
    assert GOOD in page, "the second answer satisfies more rules and is shown"


def test_never_a_third_call_and_a_tie_keeps_the_second(client, session, career, queue):
    stub = queue(NO_TITLE, "Reporte automático con Python, sin título.")
    application = stored_application(session, career)
    login(client, career.first.email)

    page = generate(client, application).text

    assert len(stub.calls) == 2
    assert "Reporte automático con Python, sin título." in page


def test_both_calls_are_in_the_ledger(client, session, career, queue):
    from src.models import LlmCall

    queue(NO_TITLE, GOOD)
    application = stored_application(session, career)
    login(client, career.first.email)

    generate(client, application)

    rows = session.query(LlmCall).filter_by(purpose="generate_summary").all()
    assert [row.prompt_version for row in rows] == ["summary_v5", "summary_v5"]


def test_the_prompt_receives_the_base_and_says_when_there_is_none(client, session, career, queue):
    stub = queue(GOOD)
    application = stored_application(session, career)
    login(client, career.first.email)

    generate(client, application)
    assert "no base summary" in stub.user()

    pid = career.first_profile.id
    base = create_summary(pid, session, text="Analista con más de ocho años.", lang="es")
    set_track_summary(pid, session, career.first_track.id, lang="es", summary_id=base.id)
    session.commit()
    stub2 = queue(GOOD)
    generate(client, application)
    assert f"summary:{base.id}" in stub2.user() and "ocho años" in stub2.user()
    assert "translate it" not in stub2.user()


def test_a_base_in_the_other_language_is_to_be_translated(client, session, career, queue):
    pid = career.first_profile.id
    base = create_summary(pid, session, text="Data analyst with eight years.", lang="en")
    set_track_summary(pid, session, career.first_track.id, lang="en", summary_id=base.id)
    stub = queue(GOOD)
    application = stored_application(session, career)
    login(client, career.first.email)

    generate(client, application)

    assert "translate it into es" in stub.user()


def test_accepting_leaves_the_tracks_skills_untouched(client, session, career, queue):
    queue(GOOD)
    application = stored_application(session, career)
    login(client, career.first.email)
    before = list(get_track(career.first_profile.id, session, career.first_track.id).skills)

    accepted = client.post(
        f"/applications/{application.id}/summary/accept",
        data={
            "payload": json.dumps(
                {"summary": {"text": GOOD, "cites": [str(career.first_bullet.id)]}}
            ),
            "use_in_track": "on",
        },
        follow_redirects=False,
    )

    assert accepted.status_code == 303
    session.expire_all()
    assert list(get_track(career.first_profile.id, session, career.first_track.id).skills) == before


def test_a_get_makes_no_provider_call_and_a_foreign_application_is_a_404(
    client, session, career, queue
):
    stub = queue(GOOD)
    application = stored_application(session, career)
    login(client, career.second.email)

    foreign = client.get(f"/applications/{application.id}/summary?dialog=1")
    foreign_post = generate(client, application)
    missing = client.get(f"/applications/{uuid.uuid4()}/summary")

    assert foreign.status_code == foreign_post.status_code == missing.status_code == 404
    assert stub.calls == []
