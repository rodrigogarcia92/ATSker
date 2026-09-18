"""The analysis pipeline and the report it produces (PRD F4, F8).

The provider is stubbed at `client._post`, so the whole milestone runs offline:
extraction, grading, the four sub-scores, the renormalised total, the cost ledger
and the page the user reads.
"""

import json
import re
from decimal import Decimal

import pytest

from src.analysis import analyze
from src.applications import create_application, get_application
from src.extract import client as extract_client
from src.extract.grading import grade_evidence
from src.extract.jd import extract_jd
from src.jd import StructuredJD, jd_hash
from src.models import Application, LlmCall
from src.score.weights import W1
from tests.conftest import login

POSTING = """
Analista de datos — Banco Demo (híbrido, Lima)
Buscamos un analista con 3 años de experiencia en Python y machine learning.
Imprescindible: título universitario.
"""

PROPOSAL = json.dumps(
    {
        "language": "es",
        "title": "Analista de datos",
        "seniority": "mid",
        "years_required": 3,
        "must_have": ["python"],
        "nice_to_have": ["machine learning"],
        "raw_keywords": ["reportes"],
        "hard_requirements": ["título universitario"],
        "location_policy": "hybrid_lima",
    }
)

COST_PER_CALL = "0.000123"


class Provider:
    """One extraction answer and one grading answer, each billed at the same rate."""

    def __init__(self, bullet_id: str, *, cost: str = COST_PER_CALL):
        self.calls: list[dict] = []
        self.cost = cost
        self.answers = {
            "JDProposal": PROPOSAL,
            "EvidenceGrading": json.dumps(
                {
                    "grades": [
                        {"index": 0, "level": 2, "bullet_id": bullet_id},
                        {"index": 1, "level": 0, "bullet_id": None},
                    ],
                    "note": "una nota",
                }
            ),
        }

    def __call__(self, payload: dict, api_key: str) -> dict:
        self.calls.append(payload)
        name = payload["response_format"]["json_schema"]["name"]
        return {
            "choices": [{"message": {"content": self.answers[name]}}],
            "usage": {"prompt_tokens": 2200, "completion_tokens": 140, "cost": self.cost},
        }


@pytest.fixture
def provider(monkeypatch, test_settings, career) -> Provider:
    stub = Provider(str(career.first_bullet.id))
    monkeypatch.setattr(extract_client, "_post", stub)
    return stub


def test_an_analysis_records_its_weights_prompts_and_cost(session, career, provider):
    analysis = analyze(career.first_profile.id, session, jd_text=POSTING, company="Banco Demo")
    score = analysis.report["score"]

    assert analysis.weights_version == "w1"
    assert score["unavailable"] == {"semantic": "embeddings_not_available"}
    assert "semantic" not in score["sub_scores"]
    assert sorted(score["sub_scores"]) == ["evidence", "experience", "keyword", "title"]
    assert sum(score["effective_weights"].values()) == pytest.approx(1.0)
    assert score["effective_weights_hash"].startswith("sha256:")
    assert score["effective_weights_hash"] != score["weights_hash"]
    assert analysis.prompt_versions == {
        "jd_extract": "jd_extract_v2",
        "evidence_grade": "evidence_grade_v2",
    }

    # Cost instrumentation is part of the milestone: the ledger rows exist and the
    # analysis carries what it actually spent.
    calls = session.query(LlmCall).order_by(LlmCall.id).all()
    assert [call.purpose for call in calls] == ["jd_extract", "evidence_grade"]
    assert all(call.prompt_tokens == 2200 and call.completion_tokens == 140 for call in calls)
    assert all(call.cost_usd == Decimal(COST_PER_CALL) for call in calls)
    assert analysis.cost_usd == 2 * Decimal(COST_PER_CALL)
    assert analysis.report["llm"]["cost_usd"] == str(2 * Decimal(COST_PER_CALL))

    # The citation is snapshotted with the text that was graded.
    graded = analysis.report["grades"]
    assert [grade["level"] for grade in graded] == [2, 0]
    assert graded[0]["bullet_text"] == career.first_bullet.text_es
    assert graded[1]["bullet_id"] is None

    application = create_application(
        career.first_profile.id,
        session,
        jd_text=POSTING,
        jd_hash=analysis.jd_hash,
        company=analysis.company,
        title=analysis.title,
        report=analysis.report,
        weights_version=analysis.weights_version,
        prompt_versions=analysis.prompt_versions,
        token_cost_usd=analysis.cost_usd,
    )

    assert application.jd_hash == jd_hash(POSTING)
    assert application.title == "Analista de datos"
    assert application.token_cost_usd == 2 * Decimal(COST_PER_CALL)
    assert application.prompt_versions["evidence_grade"] == "evidence_grade_v2"
    assert application.report["score"]["unavailable"] == {"semantic": "embeddings_not_available"}


def test_the_total_is_renormalised_over_the_four_available_components(session, career, provider):
    """Hand-computed: Σ(nominal weight × value) over the four, divided by 0.90."""
    analysis = analyze(career.first_profile.id, session, jd_text=POSTING)
    score = analysis.report["score"]
    values = {name: entry["value"] for name, entry in score["sub_scores"].items()}

    nominal = sum(getattr(W1, name) * value for name, value in values.items())
    expected = nominal / 0.90

    assert score["weighted"] == pytest.approx(expected)
    assert score["uncapped"] == round(100 * expected)
    assert score["capped"] == score["uncapped"], "no résumé document exists, so no cap applies"
    assert analysis.report["gate"] is None


def test_a_second_analysis_of_the_same_pair_makes_no_call_and_costs_nothing(
    session, career, provider
):
    first = analyze(career.first_profile.id, session, jd_text=POSTING)
    second = analyze(career.first_profile.id, session, jd_text=POSTING)

    assert len(provider.calls) == 2, "one extraction and one grading call, once"
    assert session.query(LlmCall).count() == 2
    assert first.cost_usd == 2 * Decimal(COST_PER_CALL)
    assert second.cost_usd == 0
    assert all(call["cached"] is True for call in second.report["llm"]["calls"])


def messages_for(provider: Provider, schema_name: str) -> list[list[dict]]:
    return [
        call["messages"]
        for call in provider.calls
        if call["response_format"]["json_schema"]["name"] == schema_name
    ]


def text_of(html: str) -> str:
    """What the reader sees: tags removed, whitespace collapsed."""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def test_the_invariant_prompt_prefix_is_byte_identical_across_postings(
    session, career, provider
):
    """The rubric and the vocabulary are the stable prefix; only the data varies.

    Providers price a cached prefix at a fraction of fresh input, which only pays
    if the prefix is byte-identical and comes first.
    """
    extract_jd(session, POSTING)
    extract_jd(session, "Otro puesto distinto, en otra empresa.")

    first, second = messages_for(provider, "JDProposal")[:2]
    assert first[0]["role"] == "system"
    assert first[0]["content"] == second[0]["content"]
    assert "python" in first[0]["content"], "the vocabulary block is the prefix"
    assert "python" not in first[1]["content"], "only the posting varies"

    jd = extract_jd(session, POSTING)[0]
    other = StructuredJD(
        title="Otro puesto", must_have=["machine learning"], nice_to_have=["python"]
    )
    grade_evidence(session, jd, [career.first_bullet])
    grade_evidence(session, other, [career.first_bullet])

    first, second = messages_for(provider, "EvidenceGrading")[:2]
    assert first[0]["content"] == second[0]["content"]
    assert "0 absent" in first[0]["content"], "the rubric is the prefix"
    assert first[1]["content"] != second[1]["content"], "only the requirements vary"


def test_the_report_page_shows_the_total_its_cost_and_the_renormalisation_line(
    client, session, career, provider
):
    login(client, career.first.email)

    posted = client.post(
        "/analyze",
        data={"jd_text": POSTING, "company": "Banco Demo", "title": ""},
        follow_redirects=False,
    )

    assert posted.status_code == 303
    page = text_of(client.get(posted.headers["location"]).text)
    application = session.query(Application).one()
    score = application.report["score"]

    assert application.profile_id == career.first_profile.id
    assert "Banco Demo" in page
    assert f"{score['capped']} / 100" in page
    assert "se renormaliza sobre 4 de 5 componentes" in page
    assert "Encaje semántico" in page and "no disponible" in page
    assert "$0.000246" in page, "the cost of the analysis that produced the report"
    assert "jd_extract_v2" in page
    assert career.first_bullet.text_es in page, "the citation is shown"
    disqualifier = application.report["jd"]["hard_requirements"][0]
    assert disqualifier in page, "disqualifiers are reported separately"
    assert "Sin cita" in page


def test_another_profiles_report_is_404(client, session, career, provider):
    other = create_application(
        career.second_profile.id,
        session,
        jd_text="Puesto ajeno",
        jd_hash="sha256:0",
        report={},
        weights_version="w1",
        prompt_versions={},
        token_cost_usd=Decimal("0"),
    )
    session.commit()

    login(client, career.first.email)

    assert client.get(f"/applications/{other.id}").status_code == 404
    assert client.get("/applications/not-a-uuid").status_code == 404
    assert get_application(career.second_profile.id, session, other.id) is not None


def test_analysis_without_a_model_says_so_and_saves_nothing(client, session, career, monkeypatch):
    from src.config import get_settings

    monkeypatch.delenv("OPENROUTER_MODEL")
    get_settings.cache_clear()
    try:
        login(client, career.first.email)
        response = client.post("/analyze", data={"jd_text": POSTING})
    finally:
        get_settings.cache_clear()

    assert response.status_code == 200
    assert "OPENROUTER_MODEL" in response.text
    assert session.query(Application).count() == 0


def test_an_empty_posting_is_refused_before_any_call(client, session, career, provider):
    login(client, career.first.email)

    response = client.post("/analyze", data={"jd_text": "   "})

    assert response.status_code == 200
    assert "Pega el texto de la oferta" in response.text
    assert provider.calls == []
    assert session.query(Application).count() == 0


def test_a_provider_failure_is_reported_and_the_ledger_keeps_what_was_spent(
    client, session, career, monkeypatch
):
    """Extraction succeeded, grading could not be reached: no report, but a paid call."""
    import httpx

    stub = Provider(str(career.first_bullet.id))
    original = stub.__call__

    def failing(payload, api_key):
        if payload["response_format"]["json_schema"]["name"] == "EvidenceGrading":
            raise httpx.ConnectError("provider unreachable")
        return original(payload, api_key)

    monkeypatch.setattr(extract_client, "_post", failing)

    login(client, career.first.email)
    response = client.post("/analyze", data={"jd_text": POSTING})

    assert response.status_code == 200
    assert "no se pudo completar" in text_of(response.text)
    assert session.query(Application).count() == 0
    assert [call.purpose for call in session.query(LlmCall).all()] == ["jd_extract"]
