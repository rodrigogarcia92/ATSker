"""The analysis pipeline and the report it produces (PRD F4, F8).

The provider is stubbed at `client._post`, so the whole milestone runs offline:
extraction, grading, the four sub-scores, the renormalised total, the cost ledger
and the page the user reads.
"""

import hashlib
import html
import json
import re
from datetime import date
from decimal import Decimal

import pytest

from src.analysis import analyze
from src.applications import create_application, get_application
from src.bullets import create_bullet, set_bullet_active, update_bullet
from src.extract import client as extract_client
from src.extract.client import CallOptions
from src.extract.grading import grade_evidence
from src.extract.jd import extract_jd
from src.jd import StructuredJD, jd_hash
from src.models import Application, LlmCall
from src.score.weights import W4
from src.summaries import create_summary
from src.tracks import create_track, set_track_bullets, update_track
from src.vocabulary import vocabulary_hash
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

# The recruiter's side of the posting (F5.2): a broad query Ana's profile answers, and
# a strict one it does not — `machine learning` is nowhere in her bullets.
QUERIES = json.dumps(
    {
        "queries": [
            {"label": "broad", "all_of": [["analista de datos"], ["python"]], "none_of": []},
            {
                "label": "strict",
                "all_of": [["python"], ["machine learning"]],
                "none_of": ["excel"],
            },
        ]
    }
)


class Provider:
    """One extraction answer and one grading answer, each billed at the same rate."""

    def __init__(self, bullet_id: str, *, cost: str = COST_PER_CALL):
        self.calls: list[dict] = []
        self.cost = cost
        self.answers = {
            "JDProposal": PROPOSAL,
            "BooleanQuerySet": QUERIES,
            "EvidenceGrading": json.dumps(
                {
                    "grades": [
                        {
                            "index": 0,
                            "level": 2,
                            "basis": "direct",
                            "source": "bullet",
                            "evidence_id": bullet_id,
                            "transfer_reason": None,
                        },
                        {"index": 1, "level": 0, "basis": "none", "source": None},
                    ],
                    "note": "una nota",
                }
            ),
            # The one gap the grading above leaves (machine learning, nice-to-have,
            # level 0), explained in order — the call may not add or reorder gaps.
            "GapInterpretation": json.dumps(
                {
                    "gaps": [
                        {
                            "requirement": "machine learning",
                            "blocking": False,
                            "interpretation": "Machine learning está mencionado sin "
                            "una historia que lo demuestre.",
                        }
                    ],
                    "warning": {
                        "text": "Salto hacia banca privada",
                        "handling": "Llévalo como transferencia de método analítico.",
                    },
                    "not_found": "No hay historias sobre despliegue de modelos.",
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

    assert analysis.weights_version == "w4"
    assert analysis.report["vocabulary_hash"] == vocabulary_hash(session), (
        "the report records the vocabulary it was scored against (F3.1)"
    )
    assert score["unavailable"] == {}, "w3 declares nothing missing"
    assert "semantic" not in score["sub_scores"]
    assert list(score["sub_scores"]) == ["skills", "experience", "title", "keywords"]
    assert sum(score["effective_weights"].values()) == pytest.approx(1.0)
    assert score["effective_weights_hash"].startswith("sha256:")
    assert score["weights_hash"] == W4.config_hash(), (
        "the config hash covers the four weights and the basis credits"
    )
    assert score["effective_weights"] == {
        "skills": 0.40,
        "experience": 0.25,
        "title": 0.20,
        "keywords": 0.15,
    }, "nothing is renormalised under w3"
    assert analysis.prompt_versions == {
        "jd_extract": "jd_extract_v3",
        "evidence_grade": "evidence_grade_v4",
        "boolean_queries": "boolean_recall_v2",
        "gap_interpret": "gap_interpret_v1",
    }

    # Cost instrumentation is part of the milestone: the ledger rows exist and the
    # analysis carries what it actually spent — four calls since N5's gap analysis.
    calls = session.query(LlmCall).order_by(LlmCall.id).all()
    assert [call.purpose for call in calls] == [
        "jd_extract",
        "evidence_grade",
        "boolean_queries",
        "gap_interpret",
    ]
    assert all(call.prompt_tokens == 2200 and call.completion_tokens == 140 for call in calls)
    assert all(call.cost_usd == Decimal(COST_PER_CALL) for call in calls)
    assert analysis.cost_usd == 4 * Decimal(COST_PER_CALL)
    assert analysis.report["llm"]["cost_usd"] == str(4 * Decimal(COST_PER_CALL))

    # The citation is snapshotted with the text that was graded, and the row says
    # which source it came from and on what basis (F5.4.1).
    graded = analysis.report["grades"]
    assert [grade["level"] for grade in graded] == [2, 0]
    assert graded[0]["bullet_text"] == career.first_bullet.text_es
    assert graded[1]["bullet_id"] is None
    assert graded[0]["basis"] == "direct" and graded[0]["source"] == "bullet"
    assert graded[0]["fallback"] is False

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
    assert application.token_cost_usd == 4 * Decimal(COST_PER_CALL)
    assert application.prompt_versions["evidence_grade"] == "evidence_grade_v4"
    assert application.report["score"]["unavailable"] == {}


def test_a_refused_equivalence_is_listed_for_family_review(session, career, provider):
    """F5.5.2: a basis the family data could not confirm is not a silent
    downgrade — the pair lands in `report["family_candidates"]`, which is what
    `scripts/vocabulary.py families-review` counts for the operator."""
    provider.answers["EvidenceGrading"] = json.dumps(
        {
            "grades": [
                {"index": 0, "level": 0, "basis": "none", "source": None},
                {
                    "index": 1,
                    "level": 2,
                    "basis": "equivalent",
                    "source": "bullet",
                    "evidence_id": str(career.first_bullet.id),
                    "transfer_reason": "Mismo trabajo, otro dominio.",
                },
            ],
            "note": "",
        }
    )
    # The gap the grading above leaves is now python (must-have, level 0), so the
    # interpretation stub has to answer about that one.
    provider.answers["GapInterpretation"] = json.dumps(
        {
            "gaps": [
                {
                    "requirement": "python",
                    "blocking": True,
                    "interpretation": "Sin Python no hay candidatura.",
                }
            ],
            "warning": {"text": "Nada", "handling": "Nada"},
            "not_found": "No hay nada.",
        }
    )

    analysis = analyze(career.first_profile.id, session, jd_text=POSTING)

    assert analysis.report["family_candidates"] == [
        {"requirement": "machine learning", "cited": "python"}
    ]
    assert analysis.report["grades"][1]["downgraded"] is True
    assert analysis.report["grades"][1]["basis"] == "transferable"


def test_the_report_shows_relevant_years_the_roles_and_the_tasks(client, session, career, provider):
    """F5.5.2: Experience says what it counted — relevant years against total, the
    roles that made them relevant, and the posting's tasks with their level."""
    career.first_role.start_date = date(2020, 1, 1)
    provider.answers["JDProposal"] = json.dumps(
        {
            **json.loads(PROPOSAL),
            "responsibilities": ["Preparar los reportes", "Coordinar al equipo"],
        }
    )
    provider.answers["EvidenceGrading"] = json.dumps(
        {
            "grades": [
                {
                    "index": 0,
                    "level": 3,
                    "basis": "direct",
                    "source": "bullet",
                    "evidence_id": str(career.first_bullet.id),
                    "transfer_reason": None,
                },
                {"index": 1, "level": 0, "basis": "none", "source": None},
            ],
            "task_grades": [
                {
                    "index": 0,
                    "level": 2,
                    "source": "bullet",
                    "evidence_id": str(career.first_bullet.id),
                },
                {"index": 1, "level": 0, "source": None, "evidence_id": None},
            ],
            "note": "",
        }
    )
    session.commit()
    login(client, career.first.email)

    posted = client.post("/analyze", data={"jd_text": POSTING}, follow_redirects=False)

    assert posted.status_code == 303
    detail = session.query(Application).one().report["score"]["sub_scores"]["experience"]["detail"]
    assert detail["tasks"] == [
        {
            "text": "Preparar los reportes",
            "level": 2,
            "bullet_id": str(career.first_bullet.id),
        },
        {"text": "Coordinar al equipo", "level": 0, "bullet_id": None},
    ]
    assert [entry["id"] for entry in detail["relevant_roles"]] == [str(career.first_role.id)]
    assert detail["relevant_years"] == detail["held_years"] > 0

    page = text_of(client.get(posted.headers["location"]).text)
    assert "Años relevantes" in page
    assert "Puestos contados" in page
    assert "Preparar los reportes" in page


def test_sub_scores_are_shown_as_integers_out_of_100(client, session, career, provider):
    """PRD §12.1: what sits under a sub-score is a percentage, never a fraction —
    the page shows 29, not 0.29. The stored value is untouched."""
    login(client, career.first.email)
    posted = client.post("/analyze", data={"jd_text": POSTING}, follow_redirects=False)

    application = session.query(Application).one()
    raw = client.get(posted.headers["location"]).text
    for name, entry in application.report["score"]["sub_scores"].items():
        shown = f"{entry['value'] * 100:.0f}"
        assert f">{shown}</span>" in raw, f"{name} renders {shown}, not {entry['value']}"
        assert f">{entry['value']:.2f}</span>" not in raw, "a sub-score is never a fraction"

    skills = application.report["score"]["sub_scores"]["skills"]["detail"]
    page = text_of(raw)
    assert f"{skills['direct'] * 100:.0f} directo" in page
    assert f"{skills['transfer'] * 100:.0f} transferible" in page


def test_the_total_is_the_hand_computed_weighted_sum_of_the_four(session, career, provider):
    """PRD F5.5.1: Σ(w3 weight × value) over four components, nothing renormalised."""
    analysis = analyze(career.first_profile.id, session, jd_text=POSTING)
    score = analysis.report["score"]
    values = {name: entry["value"] for name, entry in score["sub_scores"].items()}

    expected = sum(getattr(W4, name) * value for name, value in values.items())

    assert score["weighted"] == pytest.approx(expected)
    assert score["uncapped"] == round(100 * expected)
    assert score["capped"] == score["uncapped"], "no résumé document exists, so no cap applies"
    assert analysis.report["gate"] is None


def test_a_second_analysis_of_the_same_pair_makes_no_call_and_costs_nothing(
    session, career, provider
):
    first = analyze(career.first_profile.id, session, jd_text=POSTING)
    second = analyze(career.first_profile.id, session, jd_text=POSTING)

    assert len(provider.calls) == 4, "extraction, grading, the boolean queries and the gaps, once"
    assert session.query(LlmCall).count() == 4
    assert first.cost_usd == 4 * Decimal(COST_PER_CALL)
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
    grade_evidence(session, jd, [career.first_bullet], basis_credit=W4.basis_credit)
    grade_evidence(session, other, [career.first_bullet], basis_credit=W4.basis_credit)

    first, second = messages_for(provider, "EvidenceGrading")[:2]
    assert first[0]["content"] == second[0]["content"]
    assert "0 absent" in first[0]["content"], "the rubric is the prefix"
    assert first[1]["content"] != second[1]["content"], "only the requirements vary"


def test_the_report_page_shows_the_total_its_cost_and_its_components(
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
    assert "se renormaliza" not in page, "w2 has nothing to renormalise"
    assert "Habilidades" in page and "Palabras clave" in page
    assert "Encaje semántico" not in page
    assert "$0.000492" in page, "the cost of the analysis that produced the report"
    assert "jd_extract_v3" in page
    assert career.first_bullet.text_es in page, "the citation is shown"
    disqualifier = application.report["jd"]["hard_requirements"][0]
    assert disqualifier in page, "disqualifiers are reported separately"
    assert "Sin cita" in page


def test_the_report_page_renders_the_gap_summary_and_the_detail(client, session, career, provider):
    """F6's two views: a summary of the headline problems, expandable to every gap."""
    login(client, career.first.email)

    posted = client.post(
        "/analyze", data={"jd_text": POSTING, "company": "Banco Demo"}, follow_redirects=False
    )

    page = text_of(client.get(posted.headers["location"]).text)
    rows = session.query(Application).one().report["gaps"]["gaps"]
    assert [row["requirement"] for row in rows] == ["machine learning"]
    assert rows[0]["level"] == 0 and rows[0]["must_have"] is False

    # The summary view: the interpretation line, with the blocking flag when set.
    assert "Machine learning está mencionado sin una historia que lo demuestre." in page
    # The detailed list behind it: level, weight class, requirement text.
    assert "Ver el detalle (1)" in page
    assert "machine learning" in page
    assert "Deseable · Nivel 0" in page
    assert "Salto hacia banca privada" in page, "the single warning, with its handling"
    assert "Llévalo como transferencia de método analítico." in page
    assert "No hay historias sobre despliegue de modelos." in page
    # Extraction folds hard requirements, so compare against what is stored.
    application = session.query(Application).one()
    assert application.report["disqualifiers"] == [
        {"requirement": application.report["jd"]["hard_requirements"][0], "verdict": "unmet"}
    ], "the degree ask, answered by the empty education rows"
    assert application.report["disqualifiers"][0]["requirement"] in page
    assert "no cumple" in page
    assert "No había historias disponibles" not in page, "the story table was not empty"


def test_the_report_page_says_when_no_stories_were_available(
    client, session, career, provider, monkeypatch
):
    """F6.1: the table may legitimately be empty, and the output says so."""
    monkeypatch.setattr("src.analysis.list_stories", lambda *args, **kwargs: [])
    login(client, career.first.email)

    posted = client.post("/analyze", data={"jd_text": POSTING}, follow_redirects=False)

    application = session.query(Application).one()
    assert application.report["gaps"]["stories_used"] == 0
    page = text_of(client.get(posted.headers["location"]).text)
    assert "No había historias disponibles para este análisis." in page


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


# --- The cap banner: it speaks only when the cap lowered the score -----------


def flagged_report(*, capped: int, uncapped: int, cap: int, severity: str) -> dict:
    """A stored report whose document carried one format finding of `severity`."""
    check = "contact_in_margin"
    return {
        "jd": {
            "language": "es",
            "title": "Analista de datos",
            "seniority": "mid",
            "years_required": 3,
            "must_have": ["python"],
            "nice_to_have": ["machine learning"],
            "raw_keywords": ["reportes"],
            "hard_requirements": ["título universitario"],
            "location_policy": "hybrid_lima",
        },
        "grades": [],
        "grading_note": None,
        "gate": {
            "cap": cap,
            "cap_reason": check,
            "findings": [
                {
                    "check": check,
                    "severity": severity,
                    "detail": {"page": 1, "band": "header", "kinds": ["email"]},
                }
            ],
        },
        "recall": {"checked": False, "queries": []},
        "score": {
            "weights_version": "w2",
            "weights_hash": "sha256:0",
            "weighted": uncapped / 100,
            "uncapped": uncapped,
            "capped": capped,
            "cap": cap,
            "cap_reason": check,
            "unavailable": {},
            "effective_weights": {
                "skills": 0.40,
                "experience": 0.25,
                "title": 0.20,
                "keywords": 0.15,
            },
            "effective_weights_hash": "sha256:0",
            "sub_scores": {},
        },
        "llm": {"cost_usd": "0", "calls": []},
    }


def store_flagged(session, profile_id, *, capped, uncapped, cap, severity):
    report = flagged_report(capped=capped, uncapped=uncapped, cap=cap, severity=severity)
    application = create_application(
        profile_id,
        session,
        jd_text="Oferta de ejemplo",
        jd_hash=f"sha256:flagged-{capped}-{uncapped}-{severity}",
        report=report,
        weights_version="w2",
        prompt_versions={"jd_extract": "jd_extract_v2"},
        token_cost_usd=Decimal("0"),
        scan_readability=report["gate"],
    )
    session.commit()
    return application


def test_the_cap_banner_names_both_numbers_when_the_cap_binds(client, session, career):
    application = store_flagged(
        session, career.first_profile.id, capped=40, uncapped=62, cap=40, severity="blocker"
    )
    login(client, career.first.email)

    page = text_of(client.get(f"/applications/{application.id}").text)

    assert "Limitado a 40" in page
    assert "sin límite sería 62" in page
    assert "El documento limita la puntuación" in page, "the findings line restates a binding cap"


@pytest.mark.parametrize(
    "cap, severity, sentence",
    [(40, "blocker", "tiene un bloqueante"), (85, "warning", "tiene un aviso")],
)
def test_a_flagged_document_below_the_cap_says_so_instead_of_the_banner(
    client, session, career, cap, severity, sentence
):
    """A real run showed «Limitado a 40 … sin límite sería 29» on a score of 29: the
    cap was 40, `min(29, 40)` is 29, and nothing was capped."""
    application = store_flagged(
        session, career.first_profile.id, capped=29, uncapped=29, cap=cap, severity=severity
    )
    login(client, career.first.email)

    page = text_of(client.get(f"/applications/{application.id}").text)

    assert sentence in page
    assert "hoy no resta puntos" in page
    assert "Limitado a" not in page, "the banner never fires when the cap does not bind"
    assert "El documento limita la puntuación" not in page


def test_analysis_without_a_model_says_so_and_saves_nothing(client, session, career, monkeypatch):
    from src.config import get_settings

    # An empty value, not a deleted one: a developer's .env would otherwise supply
    # a real model and the test would leave for the network.
    monkeypatch.setenv("OPENROUTER_MODEL", "")
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


# --- Per-track analysis (PRD F4) --------------------------------------------


def grading_message(provider: Provider) -> str:
    """What the judge was given: the requirements and the bullets it may cite."""
    return messages_for(provider, "EvidenceGrading")[0][1]["content"]


def test_a_tracks_analysis_scores_only_its_selected_bullets(session, career, provider):
    """F4: the selection is the evidence, and a bullet outside it is not sent."""
    outside = create_bullet(
        career.first_profile.id,
        session,
        role_id=career.first_role.id,
        text_es="Coordiné reuniones semanales del equipo",
        text_en=None,
    )
    session.commit()

    analysis = analyze(
        career.first_profile.id, session, jd_text=POSTING, track=career.first_track
    )

    supplied = grading_message(provider)
    assert str(career.first_bullet.id) in supplied
    assert str(outside.id) not in supplied
    assert outside.text_es not in supplied
    assert analysis.report["track"] == {
        "id": str(career.first_track.id),
        "name": career.first_track.name,
    }
    assert analysis.report["gate"] is None, "a track with no source document is not capped"


def test_the_same_posting_scores_differently_against_two_tracks(session, career, provider):
    """N2's acceptance criterion: two tracks, one posting, two answers."""
    profile_id = career.first_profile.id
    with_keyword = create_bullet(
        profile_id,
        session,
        role_id=career.first_role.id,
        text_es="Armé los reportes mensuales para el comité",
        text_en=None,
    )
    without_keyword = create_bullet(
        profile_id,
        session,
        role_id=career.first_role.id,
        text_es="Coordiné la agenda del equipo",
        text_en=None,
    )
    narrow = create_track(profile_id, session, name="Con reportes", lang="es")
    broad = create_track(profile_id, session, name="Sin reportes", lang="es")
    set_track_bullets(profile_id, session, narrow.id, [career.first_bullet.id, with_keyword.id])
    set_track_bullets(profile_id, session, broad.id, [career.first_bullet.id, without_keyword.id])
    session.commit()

    first = analyze(profile_id, session, jd_text=POSTING, track=narrow)
    second = analyze(profile_id, session, jd_text=POSTING, track=broad)

    # F5.5.2 widened the keyword set to every term the posting asks for, so a track
    # that answers the must-have is no longer a zero — what must hold is that only
    # the narrow track evidences the posting's own keyword.
    assert (
        first.report["score"]["sub_scores"]["keywords"]["value"]
        > second.report["score"]["sub_scores"]["keywords"]["value"]
    )
    assert first.report["score"]["capped"] > second.report["score"]["capped"]
    assert second.report["llm"]["calls"][1]["cached"] is False, "the judge really was re-run"
    assert first.report["track"]["name"] == "Con reportes"
    assert second.report["track"]["name"] == "Sin reportes"


def test_a_tracks_headline_replaces_the_profiles_for_title_alignment(session, career, provider):
    profile_id = career.first_profile.id
    career.first_profile.headline = "Camarero de eventos"
    provider.answers["JDProposal"] = json.dumps(
        {**json.loads(PROPOSAL), "title": "Data Scientist"}
    )
    track = create_track(
        profile_id, session, name="Data Scientist", lang="en", headline_en="Data Scientist"
    )
    set_track_bullets(profile_id, session, track.id, [career.first_bullet.id])
    session.commit()

    without = analyze(profile_id, session, jd_text=POSTING)
    with_track = analyze(profile_id, session, jd_text=POSTING, track=track)

    assert without.report["score"]["sub_scores"]["title"]["value"] == 0.0
    assert with_track.report["score"]["sub_scores"]["title"]["value"] == 1.0


def test_an_analysis_without_a_track_uses_every_active_bullet(session, career, provider):
    """The no-track path is unchanged: no track recorded, no selection applied."""
    extra = create_bullet(
        career.first_profile.id,
        session,
        role_id=career.first_role.id,
        text_es="Otra viñeta activa",
        text_en=None,
    )
    session.commit()

    analysis = analyze(career.first_profile.id, session, jd_text=POSTING)

    supplied = grading_message(provider)
    assert str(career.first_bullet.id) in supplied
    assert str(extra.id) in supplied
    assert "track" not in analysis.report


def test_a_deactivated_bullet_is_not_evidence_even_when_a_track_still_selects_it(
    session, career, provider
):
    profile_id = career.first_profile.id
    live = create_bullet(
        profile_id, session, role_id=career.first_role.id, text_es="Viñeta viva", text_en=None
    )
    track = create_track(profile_id, session, name="Con una desactivada", lang="es")
    set_track_bullets(profile_id, session, track.id, [live.id, career.first_bullet.id])
    set_bullet_active(profile_id, session, career.first_bullet.id, active=False)
    provider.answers["EvidenceGrading"] = json.dumps(
        {
            "grades": [
                {
                    "index": 0,
                    "level": 2,
                    "basis": "direct",
                    "source": "bullet",
                    "evidence_id": str(live.id),
                    "transfer_reason": None,
                },
                {"index": 1, "level": 0, "basis": "none", "source": None},
            ],
            "note": "una nota",
        }
    )
    session.commit()

    analyze(profile_id, session, jd_text=POSTING, track=track)

    supplied = grading_message(provider)
    assert str(live.id) in supplied
    assert str(career.first_bullet.id) not in supplied


def test_the_analysis_form_records_the_track_and_the_report_names_it(
    client, session, career, provider
):
    login(client, career.first.email)

    form = client.get("/analyze").text
    posted = client.post(
        "/analyze",
        data={
            "jd_text": POSTING,
            "company": "Banco Demo",
            "title": "",
            "track_id": str(career.first_track.id),
        },
        follow_redirects=False,
    )

    assert f'value="{career.first_track.id}"' in form
    assert "Analista de datos — Puestos de analista de datos" in form
    assert posted.status_code == 303
    application = session.query(Application).one()
    assert application.track_id == career.first_track.id
    assert application.report["track"]["name"] == "Analista de datos"
    assert "Puesto objetivo: Analista de datos" in text_of(
        client.get(posted.headers["location"]).text
    )


def test_an_analysis_without_a_track_saves_no_track_and_says_so(client, session, career, provider):
    login(client, career.first.email)

    posted = client.post(
        "/analyze", data={"jd_text": POSTING, "company": "Banco Demo", "title": ""},
        follow_redirects=False,
    )

    application = session.query(Application).one()
    assert application.track_id is None
    page = text_of(client.get(posted.headers["location"]).text)
    assert "Sin puesto objetivo: se puntuaron todas las viñetas activas." in page


def test_a_track_from_another_profile_is_refused_by_the_form(client, session, career, provider):
    login(client, career.first.email)

    response = client.post(
        "/analyze", data={"jd_text": POSTING, "track_id": str(career.second_track.id)}
    )

    assert response.status_code == 404
    assert provider.calls == []
    assert session.query(Application).count() == 0


def test_the_summary_and_the_skills_list_count_for_keywords(session, career, provider):
    """F5.5.1: the keyword search runs over the file — summary and skills section
    included — in the posting's language."""
    profile_id = career.first_profile.id
    career.first_profile.skills = ["python"]
    summary = create_summary(
        profile_id, session, text="Cinco años de gobierno de datos.", lang="es"
    )
    update_track(
        profile_id,
        session,
        career.first_track.id,
        name=career.first_track.name,
        applies_when=career.first_track.applies_when,
        lang="es",
        headline_es=career.first_track.headline_es,
        summary_es_id=summary.id,
        skills=["python"],
    )
    provider.answers["JDProposal"] = json.dumps(
        {**json.loads(PROPOSAL), "raw_keywords": ["gobierno de datos"]}
    )
    session.commit()

    analysis = analyze(profile_id, session, jd_text=POSTING, track=career.first_track)

    keywords = analysis.report["score"]["sub_scores"]["keywords"]
    assert "gobierno de datos" in keywords["matched"], "the summary counted"
    assert keywords["value"] > 0, "a keyword found only in the summary is not lost"


def test_the_alerts_beside_the_warning_flag_over_seniority_and_location(
    session, career, provider
):
    """F6.1: two risks that never enter the number — beside the single warning,
    never inside the gap list."""
    profile_id = career.first_profile.id
    career.first_profile.headline = "Data scientist senior"
    provider.answers["JDProposal"] = json.dumps(
        {**json.loads(PROPOSAL), "hard_requirements": ["Presencial en Lima"]}
    )
    session.commit()

    analysis = analyze(profile_id, session, jd_text=POSTING)

    alerts = analysis.report["gaps"]["alerts"]
    assert {"kind": "over_seniority"} in alerts
    # Extraction folds hard requirements, so the alert carries the stored text.
    assert {
        "kind": "location",
        "requirement": "presencial en lima",
        "verdict": "unverified",
    } in alerts
    assert all(
        gap["requirement"] != "Presencial en Lima" for gap in analysis.report["gaps"]["gaps"]
    ), "the alert is not a gap"


def test_a_seniority_gap_below_the_posting_alerts_with_both_rungs(session, career, provider):
    """F5.5.2: the posting asks for a level the current title does not name — the
    alert carries both rungs, and the number is overlap only."""
    profile_id = career.first_profile.id
    career.first_profile.headline = "Junior analyst"
    provider.answers["JDProposal"] = json.dumps({**json.loads(PROPOSAL), "seniority": "senior"})
    session.commit()

    analysis = analyze(profile_id, session, jd_text=POSTING)

    alerts = analysis.report["gaps"]["alerts"]
    assert {"kind": "under_seniority", "jd_rung": "senior", "user_rung": "junior"} in alerts
    assert analysis.report["score"]["sub_scores"]["title"]["value"] == 1.0


def test_an_english_posting_against_a_spanish_only_track_alerts_the_language_gap(
    session, career, provider
):
    """F4.2 (A.9.3): a screen matches the words in the file, so the report says which
    ones were not there."""
    provider.answers["JDProposal"] = json.dumps({**json.loads(PROPOSAL), "language": "en"})

    analysis = analyze(
        career.first_profile.id, session, jd_text=POSTING, track=career.first_track
    )

    assert analysis.report["language"] == {
        "posting": "en",
        "other": "es",
        "fallback_headline": True,
        "fallback_summary": False,
        "fallback_bullets": 1,
        "bullets": 1,
    }
    alerts = analysis.report["gaps"]["alerts"]
    language_alerts = [alert for alert in alerts if alert["kind"] == "language_mismatch"]
    assert len(language_alerts) == 1, "one alert, beside seniority and location"
    assert language_alerts[0]["fallback_bullets"] == 1
    assert "language" not in analysis.report["score"], "it is beside the score, not in it"


def test_a_track_in_the_postings_language_raises_no_language_alert(session, career, provider):
    """Nothing fell back, so there is nothing to say."""
    provider.answers["JDProposal"] = json.dumps({**json.loads(PROPOSAL), "language": "en"})
    profile_id = career.first_profile.id
    update_track(
        profile_id,
        session,
        career.first_track.id,
        name=career.first_track.name,
        headline_es="Analista de datos",
        headline_en="Data analyst",
    )
    update_bullet(
        profile_id,
        session,
        career.first_bullet.id,
        text_es="Reduje 30% el tiempo de reporte con Python",
        text_en="Cut reporting time by 30% with Python",
        chips=["python", "cobalto"],
    )
    session.commit()

    analysis = analyze(profile_id, session, jd_text=POSTING, track=career.first_track)

    assert analysis.report["language"] == {
        "posting": "en",
        "other": "es",
        "fallback_headline": False,
        "fallback_summary": False,
        "fallback_bullets": 0,
        "bullets": 1,
    }
    assert [
        alert for alert in analysis.report["gaps"]["alerts"] if alert["kind"] == "language_mismatch"
    ] == []


def test_the_report_page_names_the_language_gap(client, session, career, provider):
    """F4.2 (A.9.3): the alert, in the reader's own language and words."""
    provider.answers["JDProposal"] = json.dumps({**json.loads(PROPOSAL), "language": "en"})
    login(client, career.first.email)

    posted = client.post(
        "/analyze",
        data={"jd_text": POSTING, "track_id": str(career.first_track.id)},
        follow_redirects=False,
    )

    page = text_of(client.get(posted.headers["location"]).text)

    assert "Este aviso está en inglés" in page
    assert "1 de tus 1 bullets y tu titular solo existen en español" in page
    assert "Un ATS real lee las palabras que envías" in page


def w3_report() -> dict:
    """A stored w3 report with the whole F5.4.1/F6.1 furniture."""
    return {
        "jd": {
            "language": "es",
            "title": "Analista de datos",
            "seniority": "mid",
            "years_required": 3,
            "must_have": ["python", "power bi"],
            "nice_to_have": [],
            "raw_keywords": [],
            "hard_requirements": [],
            "location_policy": None,
        },
        "grades": [
            {
                "requirement": "python",
                "must_have": True,
                "level": 3,
                "basis": "direct",
                "source": "bullet",
                "bullet_id": "b1",
                "bullet_text": "Automaticé reportes con Python",
                "transfer_reason": None,
                "clamped": False,
                "downgraded": False,
                "fallback": False,
            },
            {
                "requirement": "power bi",
                "must_have": True,
                "level": 3,
                "basis": "equivalent",
                "source": "summary",
                "bullet_id": None,
                "bullet_text": "Cinco años de gobierno de datos.",
                "transfer_reason": "Tableau hace el mismo trabajo, intercambiable en semanas.",
                "clamped": True,
                "downgraded": False,
                "fallback": True,
            },
        ],
        "grading_note": "",
        "gate": None,
        "score": {
            "weights_version": "w3",
            "weights_hash": "sha256:0",
            "weighted": 0.72,
            "uncapped": 72,
            "capped": 72,
            "cap": None,
            "cap_reason": None,
            "unavailable": {},
            "effective_weights": {
                "skills": 0.40,
                "experience": 0.25,
                "title": 0.20,
                "keywords": 0.15,
            },
            "effective_weights_hash": "sha256:0",
            "sub_scores": {
                "skills": {
                    "name": "skills",
                    "value": 0.72,
                    "matched": ["python (L3, direct)"],
                    "missing": [],
                    "detail": {"direct": 0.55, "transfer": 0.17},
                },
            },
        },
        "gaps": {
            "gaps": [],
            "covered_by_transfer": [
                {
                    "requirement": "power bi",
                    "level": 3,
                    "must_have": True,
                    "bullet_id": None,
                    "bullet_text": "Cinco años de gobierno de datos.",
                    "transfer_reason": "Tableau hace el mismo trabajo, intercambiable en semanas.",
                }
            ],
            "warning": {"text": "Salto de sector", "handling": "Encuádralo."},
            "alerts": [{"kind": "over_seniority"}],
            "not_found": "",
            "stories_used": 1,
        },
        "disqualifiers": [],
        "recall": {"checked": False, "queries": [], "units": 0, "passed": 0, "failed": 0},
        "llm": {"cost_usd": "0", "calls": []},
    }


def test_the_report_page_shows_the_split_the_basis_column_and_the_transfer_band(
    session, career, client
):
    """F5.5.1/F6.1 on the page: the split, the basis column with its marks, and the
    covered-by-transfer band with its reason."""
    report = w3_report()
    application = create_application(
        career.first_profile.id,
        session,
        jd_text="Una oferta",
        jd_hash="sha256:w3-page",
        report=report,
        weights_version="w3",
        prompt_versions={"evidence_grade": "evidence_grade_v3"},
        token_cost_usd=Decimal("0"),
    )
    session.commit()
    login(client, career.first.email)

    page = text_of(client.get(f"/applications/{application.id}").text)

    assert "55 directo + 17 transferible" in page, "the split, and how much rests on transfer"
    assert "equivalente" in page, "the basis column"
    assert "de la lista de habilidades" not in page
    assert "del resumen" in page, "a summary citation is labelled as such"
    assert "Por qué transfiere: Tableau hace el mismo trabajo" in page
    assert "Nivel limitado a 1" in page, "the clamp says so"
    assert "Evidencia en el idioma alternativo" in page, "so does a fallback"
    assert "Cubierto por transferencia" in page
    assert "Alertas" in page and "seniority" in page


def test_a_stored_w2_report_renders_from_its_own_keys_without_the_w3_furniture(
    session, career, client
):
    """w3 changed what three sub-scores read and how Skills is shown; a stored w2
    report keeps its own shape and none of the new furniture appears on it."""
    report = {
        "jd": {
            "language": "es",
            "title": "Analista de datos",
            "seniority": "mid",
            "years_required": None,
            "must_have": ["python"],
            "nice_to_have": [],
            "raw_keywords": [],
            "hard_requirements": [],
            "location_policy": None,
        },
        "grades": [
            {
                "requirement": "python",
                "must_have": True,
                "level": 2,
                "bullet_id": "b1",
                "bullet_text": "Automaticé reportes con Python",
            }
        ],
        "grading_note": "",
        "gate": None,
        "score": {
            "weights_version": "w2",
            "weights_hash": "sha256:aaa",
            "weighted": 0.5,
            "uncapped": 50,
            "capped": 50,
            "cap": None,
            "cap_reason": None,
            "unavailable": {},
            "effective_weights": {
                "skills": 0.40,
                "experience": 0.25,
                "title": 0.20,
                "keywords": 0.15,
            },
            "effective_weights_hash": "sha256:aaa",
            "sub_scores": {
                "skills": {
                    "name": "skills",
                    "value": 0.6667,
                    "matched": ["python (L2)"],
                    "missing": [],
                    "detail": {},
                },
            },
        },
        "llm": {"cost_usd": "0", "calls": []},
    }
    application = create_application(
        career.first_profile.id,
        session,
        jd_text="Una oferta",
        jd_hash="sha256:w2-render",
        report=report,
        weights_version="w2",
        prompt_versions={"evidence_grade": "evidence_grade_v2"},
        token_cost_usd=Decimal("0"),
    )
    session.commit()
    login(client, career.first.email)

    page = text_of(client.get(f"/applications/{application.id}").text)

    assert "50 / 100" in page
    assert "Habilidades" in page and "python (L2)" in page
    assert "w2" in page
    assert "directo" not in page, "the split is w3's, and this report predates it"
    assert "Cubierto por transferencia" not in page
    assert "equivalente" not in page


def test_a_stored_w1_report_still_renders_from_its_own_keys(session, career, client):
    """N3 renames the components; a report written before that keeps its own names."""
    w1_report = {
        "jd": {"title": "Analista de datos", "language": "es", "must_have": [], "nice_to_have": [],
               "raw_keywords": [], "hard_requirements": [], "seniority": "mid"},
        "grades": [],
        "grading_note": "",
        "gate": None,
        "score": {
            "weights_version": "w1",
            "weights_hash": "sha256:aaa",
            "weighted": 0.68,
            "uncapped": 68,
            "capped": 68,
            "cap": None,
            "cap_reason": None,
            "unavailable": {"semantic": "embeddings_not_available"},
            "effective_weights": {
                "title": 0.2222, "evidence": 0.3889, "keyword": 0.1667, "experience": 0.2222,
            },
            "effective_weights_hash": "sha256:bbb",
            "sub_scores": {
                "title": {"name": "title", "value": 1.0, "matched": ["analista"], "missing": []},
                "evidence": {"name": "evidence", "value": 0.5, "matched": [], "missing": []},
                "keyword": {
                    "name": "keyword",
                    "value": 0.0,
                    "matched": [],
                    "missing": ["reportes"],
                },
                "experience": {"name": "experience", "value": 0.25, "matched": [], "missing": []},
            },
        },
        "llm": {"cost_usd": "0", "calls": []},
    }
    application = create_application(
        career.first_profile.id,
        session,
        jd_text="Una oferta antigua",
        jd_hash="sha256:old",
        report=w1_report,
        weights_version="w1",
        prompt_versions={"jd_extract": "jd_extract_v2"},
        token_cost_usd=Decimal("0"),
    )
    session.commit()
    login(client, career.first.email)

    page = text_of(client.get(f"/applications/{application.id}").text)

    assert "68 / 100" in page
    assert "Cobertura de evidencia" in page, "the report's own component names"
    assert "Contexto de palabras clave" in page
    assert "renormaliza sobre 4 de 5 componentes" in page
    assert "Encaje semántico" in page
    assert "Habilidades" not in page, "the current names are not imposed on a stored report"
    assert "w1" in page


def test_two_identical_runs_produce_identical_reports(session, career, provider):
    """PRD §9 stability: the same input, twice, with the cache bypassed.

    Bypassed on purpose — a cached re-run measures the cache, not the analysis — and
    that is also what makes the two reports comparable: an uncached run that cost
    nothing would differ from one that was paid for, in the ledger section alone.
    """
    options = CallOptions(bypass_cache=True)

    first = analyze(career.first_profile.id, session, jd_text=POSTING, options=options)
    second = analyze(career.first_profile.id, session, jd_text=POSTING, options=options)

    def digest(report: dict) -> str:
        return hashlib.sha256(
            json.dumps(report, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()

    assert digest(first.report) == digest(second.report)
    assert first.report["score"] == second.report["score"]
    assert first.report["grades"] == second.report["grades"]
    assert "date" not in json.dumps(first.report["score"]), "no clock inside the score"


# --- Scan B: boolean recall (PRD F5.2) ---------------------------------------


def test_the_recall_names_the_clause_that_would_exclude_the_track(session, career, provider):
    """N4's criterion: a track missing a must-have term fails the narrow query, named."""
    analysis = analyze(career.first_profile.id, session, jd_text=POSTING)
    recall = analysis.report["recall"]

    assert recall["checked"] is True
    assert recall["passed"] == 1 and recall["failed"] == 1

    broad, strict = recall["queries"]
    assert broad["label"] == "broad" and broad["passed"] is True
    assert strict["passed"] is False
    assert strict["failing_kind"] == "missing"
    assert strict["failing_term"] == "machine learning"
    assert str(career.first_bullet.id) in str(broad["clauses"]), "the citation travels"
    # A.9.2: the report carries the line the user pastes into the ATS.
    assert broad["query_text"] == '"analista de datos" AND python'
    assert strict["query_text"] == 'python AND "machine learning" AND NOT excel'


def test_the_boolean_scan_does_not_change_the_job_match_number(
    session, career, provider, monkeypatch
):
    """F5.2: recall is a gate beside the score, never a term in it."""
    # The stub provider, not the developer's .env: without it this test made three
    # real calls per run and only passed when the network answered.
    with_scan = analyze(career.first_profile.id, session, jd_text=POSTING)
    baseline = with_scan.report["score"]

    # The same analysis with the derivation answering nothing at all.
    import src.extract.boolean as boolean_module

    def no_queries(session_, jd_text, *, model=None, options=None):
        completion = with_scan.report["llm"]["calls"][-1]
        from src.extract.client import Completion

        return (
            boolean_module.BooleanQuerySet(),
            Completion(
                data={"queries": []},
                cached=True,
                prompt_tokens=0,
                completion_tokens=0,
                cost_usd=Decimal("0"),
                purpose="boolean_queries",
                prompt_version="boolean_recall_v2",
                model=completion["model"],
            ),
        )

    monkeypatch.setattr(boolean_module, "derive_boolean_queries", no_queries)
    import src.analysis as analysis_module

    monkeypatch.setattr(analysis_module, "derive_boolean_queries", no_queries)
    without_scan = analyze(career.first_profile.id, session, jd_text=POSTING)

    assert without_scan.report["recall"]["checked"] is False
    assert without_scan.report["score"]["capped"] == baseline["capped"]
    assert without_scan.report["score"]["uncapped"] == baseline["uncapped"]
    assert without_scan.report["score"]["sub_scores"] == baseline["sub_scores"]


def test_the_report_page_shows_the_recall_panel(client, session, career, provider):
    login(client, career.first.email)
    posted = client.post("/analyze", data={"jd_text": POSTING}, follow_redirects=False)
    application = session.query(Application).one()

    page = text_of(client.get(posted.headers["location"]).text)

    assert application.scan_boolean is not None
    assert application.scan_boolean["failed"] == 1
    assert "Recuperación booleana" in page
    assert "Falla en «machine learning»" in page
    assert "no aparece ningún alias de este término" in page
    assert "No entra en el Encaje total" in page, "the panel says it is not part of the score"
    assert "Pasan 1 de 2 consultas" in page
    # A.9.2: the recruiter's line, to paste, and the control that copies it.
    assert '"analista de datos" AND python' in html.unescape(page)
    assert "Copiar" in page


def test_a_stored_recall_without_query_text_still_renders(client, session, career, provider):
    """A.9.2: the field is new; a report stored without it renders from its clauses."""
    login(client, career.first.email)
    posted = client.post("/analyze", data={"jd_text": POSTING}, follow_redirects=False)
    application = session.query(Application).one()

    application.scan_boolean = {
        **application.scan_boolean,
        "queries": [
            {key: value for key, value in query.items() if key != "query_text"}
            for query in application.scan_boolean["queries"]
        ],
    }
    session.commit()

    page = text_of(client.get(posted.headers["location"]).text)

    assert "Recuperación booleana" in page and "Falla en «machine learning»" in page
    assert "Copiar" not in page, "an old report has nothing to copy"
