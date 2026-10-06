"""F7.5's probable keywords, on demand (queue K6).

One paid call, on a POST from a button, never on a GET: the pop-up opens free and the answer is
checked by guards that drop — and count — whatever cannot be verified. The fake provider is the
only one here. Nothing the call returns is stored: the application row, its scores and ceiling,
and the profile's skills are what they were before the press.
"""

import copy
import json
import re

import pytest

from src.extract import client as extract_client
from src.extract.prompts import KEYWORD_INFER_V1
from src.generate.validators import KeywordMaterial, validate_keyword_items
from src.i18n import t
from src.models import (
    Application,
    ApplicationAttempt,
    Bullet,
    LlmCall,
    Profile,
    Skill,
    Summary,
    Track,
)
from tests.conftest import login
from tests.unit.test_advice import bullet
from tests.unit.test_analysis import text_of
from tests.unit.test_keyword_advice import page_report

REASON = "La econometría es un método construido sobre la inferencia estadística."


class InferProvider:
    """Answers the one schema this call asks for, and counts how often it was asked."""

    def __init__(self, items: list[dict] | None = None):
        self.calls: list[dict] = []
        self.items = items if items is not None else []

    def __call__(self, payload: dict, api_key: str) -> dict:
        self.calls.append(payload)
        assert payload["response_format"]["json_schema"]["name"] == "KeywordInference"
        return {
            "choices": [{"message": {"content": json.dumps({"items": self.items})}}],
            "usage": {"prompt_tokens": 900, "completion_tokens": 80, "cost": "0.000050"},
        }


def item(keyword: str = "statistical inference", **changes) -> dict:
    base = {
        "keyword": keyword,
        "confidence": "high",
        "supports": ["skill:econometría"],
        "reason": REASON,
        "placement": "skills",
        "bullet_id": None,
        "role_id": None,
        "draft": None,
    }
    return {**base, **changes}


@pytest.fixture
def provider(monkeypatch, test_settings) -> InferProvider:
    stub = InferProvider([item()])
    monkeypatch.setattr(extract_client, "_post", stub)
    return stub


@pytest.fixture
def worked_case(session, career):
    """econometría in the pool; `statistical inference` and a tool missing from the document."""
    session.add_all(
        [
            Skill(canonical="econometría", aliases=["econometría", "econometria"]),
            Skill(canonical="statistical inference", aliases=["statistical inference"]),
            Skill(canonical="airflow", aliases=["airflow"], kind="tool"),
        ]
    )
    career.first_profile.skills = ["econometría"]
    session.commit()
    return page_report(
        session,
        career,
        ["statistical inference", "Airflow"],
        must=["statistical inference"],
        nice=["Airflow"],
    )


def urls(application) -> tuple[str, str, str]:
    base = f"/applications/{application.id}/keywords"
    return base, f"{base}/dialog", f"{base}/infer"


def popup(client, application, **form) -> str:
    return client.post(urls(application)[2], data={"dialog": "1", **form}).text


# --- the worked case and the guards, through the route -----------------------------


def test_the_worked_case_shows_statistical_inference_as_probable_citing_the_skill(
    client, career, worked_case, provider
):
    login(client, career.first.email)

    page = popup(client, worked_case)
    words = text_of(page)

    assert len(provider.calls) == 1
    assert "statistical inference" in words
    assert "Probable — solo si es verdad" in words, "labelled, never presented as fact"
    assert REASON in words
    assert "habilidad: econometría" in words, "what it rests on"
    assert "Habilidades" in words, "where it would go"
    assert "<html" not in page, "a partial for the dialog"


def test_a_tool_is_never_inferred_and_is_not_even_asked_about(
    client, career, worked_case, provider
):
    provider.items = [item(), item("Airflow", supports=["skill:econometría"])]
    login(client, career.first.email)

    page = popup(client, worked_case)

    sent = json.dumps(provider.calls[0])
    assert "statistical inference" in sent and "Airflow" not in sent, "the closed set has no tool"
    assert "Airflow" not in text_of(page).split("sugerencia")[0].replace("descartada", "")
    assert "1 sugerencia descartada por no poder comprobarse" in text_of(page)


def test_a_draft_with_an_invented_number_is_dropped_and_counted(
    client, session, career, worked_case, provider
):
    base = bullet(session, career, "Automaticé reportes mensuales de riesgo")
    good = item(
        supports=["skill:econometría", f"bullet:{base.id}"],
        placement="existing_bullet",
        bullet_id=str(base.id),
        draft="Automaticé reportes mensuales de riesgo con statistical inference.",
    )
    provider.items = [good]
    login(client, career.first.email)
    assert "reportes mensuales de riesgo con statistical inference" in text_of(
        popup(client, worked_case)
    )

    provider.calls.clear()
    session.query(LlmCall).delete()
    session.commit()
    provider.items = [{**good, "draft": "Automaticé 12 reportes con statistical inference."}]
    page = popup(client, worked_case)

    assert len(provider.calls) == 1
    assert "12 reportes" not in page, "the invented number is never shown"
    assert "1 sugerencia descartada por no poder comprobarse." in text_of(page)


@pytest.mark.parametrize(
    "bad",
    [
        item("some other term"),
        item(confidence="medium"),
        item(supports=[]),
        item(supports=["skill:not-in-the-pool"]),
        item(supports=["bullet:00000000-0000-0000-0000-000000000000"]),
        item(placement="existing_bullet", bullet_id="00000000-0000-0000-0000-000000000000"),
        item(placement="new_bullet", role_id=None),
        item(reason=""),
    ],
)
def test_every_other_guard_drops_and_counts(client, career, worked_case, provider, bad):
    provider.items = [bad]
    login(client, career.first.email)

    words = text_of(popup(client, worked_case))

    assert "Probable — solo si es verdad" not in words
    assert "1 sugerencia descartada por no poder comprobarse." in words
    assert "El modelo no encontró ninguna palabra clave lo bastante probable." in words


# --- free to open, one paid call per material --------------------------------------


def test_opening_the_dialog_and_the_report_make_no_provider_call(
    client, career, worked_case, provider
):
    login(client, career.first.email)
    base, dialog, _run = urls(worked_case)

    opened = client.get(dialog)
    page = client.get(base)
    report = client.get(f"/applications/{worked_case.id}")

    assert opened.status_code == page.status_code == report.status_code == 200
    assert provider.calls == []
    words = text_of(opened.text)
    assert "1 palabras clave sin respaldo" in words or "las 1 palabras clave" in words
    assert "una llamada de pago" in words.lower() and "no cuesta nada" in words
    form = re.search(r'<form method="post" action="([^"]*)"[^>]*>', opened.text)
    assert form.group(1) == urls(worked_case)[2] and "data-dialog-form" in form.group(0)
    assert "Generar" in words
    assert "<html" in page.text and "Generar" in text_of(page.text), "the no-JS page"


def test_pressing_the_button_twice_is_one_paid_call(client, session, career, worked_case, provider):
    login(client, career.first.email)

    first = popup(client, worked_case)
    second = popup(client, worked_case)

    assert len(provider.calls) == 1, "the second press is served from the cache"
    assert text_of(first) == text_of(second)
    assert session.query(LlmCall).filter_by(purpose="keyword_infer").count() == 1


def test_the_application_its_scores_and_the_profiles_material_are_untouched(
    client, session, career, worked_case, provider
):
    def snapshot():
        session.expire_all()
        application = session.get(Application, worked_case.id)
        profile = session.get(Profile, career.first_profile.id)
        track = session.get(Track, career.first_track.id)
        return (
            json.dumps(application.report, sort_keys=True, default=str),
            application.weights_version,
            str(application.token_cost_usd),
            application.job_match if hasattr(application, "job_match") else None,
            list(profile.skills),
            list(track.skills),
            session.query(Skill).count(),
            session.query(Summary).count(),
            session.query(Bullet).count(),
        )

    before = snapshot()
    login(client, career.first.email)
    popup(client, worked_case)
    client.get(urls(worked_case)[1])
    client.get(f"/applications/{worked_case.id}")

    assert snapshot() == before
    report = session.get(Application, worked_case.id).report
    assert "statistical inference" in report["score"]["sub_scores"]["keywords"]["missing"]


def test_the_ledger_row_is_a_personal_purpose_and_eliminar_todo_blanks_it(
    client, session, career, worked_case, provider
):
    login(client, career.first.email)
    popup(client, worked_case)
    row = session.query(LlmCall).filter_by(purpose="keyword_infer").one()
    assert row.prompt_version == "keyword_infer_v1" and row.response_json

    client.post("/profile/delete", data={"confirm_word": "ELIMINAR"}, follow_redirects=False)

    session.expire_all()
    blanked = session.get(LlmCall, row.id)
    assert blanked.response_json == {} and blanked.degenerate is True
    assert blanked.prompt_tokens == 900, "tokens and cost are kept"


# --- what the call is built from ---------------------------------------------------


def test_the_prompt_keeps_the_rules_in_the_system_message_and_the_data_in_the_user_message(
    client, session, career, worked_case, provider
):
    bullet(session, career, "Escribí a ana.garcia@example.com sobre modelos", ["econometría"])
    login(client, career.first.email)

    popup(client, worked_case)

    sent = provider.calls[0]
    system = next(m["content"] for m in sent["messages"] if m["role"] == "system")
    user = next(m["content"] for m in sent["messages"] if m["role"] == "user")
    assert system == KEYWORD_INFER_V1.system and "highly probable" in system
    assert "Airflow" not in system and "{candidates}" not in system, (
        "data stays in the user message"
    )
    assert "statistical inference" in user and "econometría" in user
    assert "me apasiona" in user, "F8's banned-phrase data travels with the call"
    assert "ana.garcia@example.com" not in json.dumps(sent), "redacted like every call"
    assert KEYWORD_INFER_V1.version == "keyword_infer_v1"


def test_the_system_message_states_the_guards_the_code_enforces():
    rules = KEYWORD_INFER_V1.system

    for rule in (
        "highly probable",
        "econometrics",
        "copying the keyword exactly",
        "Never propose a named software product",
        "no number",
        "no marketing phrases",
    ):
        assert rule in rules, rule


# --- failures, ownership, wording --------------------------------------------------


def test_the_three_failures_say_which_it_was(client, career, worked_case, monkeypatch, provider):
    login(client, career.first.email)

    monkeypatch.setattr("src.web.routes.keywords.model_configured", lambda: False)
    no_model = text_of(popup(client, worked_case))
    assert t("generate.err.no_model", "es") in no_model and "Generar" not in no_model
    monkeypatch.undo()

    import httpx

    def down(payload, api_key):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(extract_client, "_post", down)
    assert t("generate.err.provider", "es") in text_of(popup(client, worked_case))

    monkeypatch.setattr(
        extract_client,
        "_post",
        lambda payload, api_key: {
            "choices": [{"message": {"content": "not json"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "cost": "0"},
        },
    )
    assert t("generate.err.unusable", "es") in text_of(popup(client, worked_case))


def test_a_foreign_application_or_attempt_is_a_404_everywhere(
    client, session, career, worked_case, provider
):
    attempt = ApplicationAttempt(
        application_id=worked_case.id,
        profile_id=career.first_profile.id,
        attempt_no=1,
        status="done",
        file_format="docx",
        report=worked_case.report,
        weights_version="w4",
        prompt_versions={},
        token_cost_usd=0,
    )
    session.add(attempt)
    session.commit()
    login(client, career.second.email)
    base, dialog, run = urls(worked_case)

    assert client.get(base).status_code == 404
    assert client.get(dialog).status_code == 404
    assert client.post(run, data={"dialog": "1"}).status_code == 404
    assert client.get(f"{dialog}?attempt={attempt.id}").status_code == 404
    assert provider.calls == []

    login(client, career.first.email)
    other = page_report(session, career, ["x"])
    assert (
        client.get(f"/applications/{other.id}/keywords/dialog?attempt={attempt.id}").status_code
        == 404
    )


def test_the_report_offers_the_button_or_says_why_not(
    client, session, career, worked_case, monkeypatch
):
    login(client, career.first.email)

    page = client.get(f"/applications/{worked_case.id}").text
    button = re.search(
        r"<button[^>]*data-dialog-url=\"([^\"]*keywords[^\"]*)\"[^>]*>(.*?)</button>", page, re.S
    )
    assert button and button.group(1) == f"/applications/{worked_case.id}/keywords/dialog"
    assert text_of(button.group(2)) == "Sugerir más palabras clave probables"
    link = re.search(r'<a href="([^"]*)"[^>]*data-dialog-fallback[^>]*>Sugerir', page)
    assert link and link.group(1) == f"/applications/{worked_case.id}/keywords"

    monkeypatch.setattr("src.web.routes.analyze.model_configured", lambda: False)
    off = text_of(client.get(f"/applications/{worked_case.id}").text)
    assert "Para sugerir más palabras clave hace falta un modelo configurado." in off
    monkeypatch.undo()

    covered = page_report(session, career, ["econometría"], must=["econometría"])
    none = text_of(client.get(f"/applications/{covered.id}").text)
    assert "No queda ninguna palabra clave sin respaldo que sugerir." in none
    assert "Sugerir más palabras clave probables" not in none


def test_an_attempt_words_the_pop_up_for_the_document(
    client, session, career, worked_case, provider
):
    attempt = ApplicationAttempt(
        application_id=worked_case.id,
        profile_id=career.first_profile.id,
        attempt_no=1,
        status="done",
        file_format="docx",
        report=copy.deepcopy(worked_case.report),
        weights_version="w4",
        prompt_versions={},
        token_cost_usd=0,
    )
    session.add(attempt)
    session.commit()
    login(client, career.first.email)

    report = client.get(f"/applications/{worked_case.id}/attempts/{attempt.id}/report").text
    opened = client.get(urls(worked_case)[1] + f"?attempt={attempt.id}").text
    answered = client.post(
        urls(worked_case)[2], data={"dialog": "1", "attempt": str(attempt.id)}
    ).text

    assert (
        f'data-dialog-url="/applications/{worked_case.id}/keywords/dialog?attempt={attempt.id}"'
        in report
    )
    assert '<dialog id="proposal-dialog"' in report and 'id="attempt-modal"' not in report
    assert "de tu documento" in text_of(opened) and f'name="attempt" value="{attempt.id}"' in opened
    assert "Tu sección Habilidades" in text_of(answered)


# --- the validator, directly -------------------------------------------------------


def material(**changes) -> KeywordMaterial:
    base = {
        "candidates": ("statistical inference", "Airflow", "forecasting"),
        "canonicals": {
            "statistical inference": "statistical inference",
            "Airflow": "airflow",
            "forecasting": None,
        },
        "kinds": {"statistical inference": "technical", "airflow": "tool"},
        "skills": frozenset({"econometría"}),
        "bullets": {"b1": "Modelé series temporales"},
        "roles": {"r1": "Analista"},
        "aliases": {"statistical inference": "statistical inference", "airflow": "airflow"},
    }
    return KeywordMaterial(**{**base, **changes})


def test_the_validator_drops_a_named_tool_but_allows_a_phrase_the_vocabulary_does_not_know():
    kept, dropped = validate_keyword_items(
        [item("Airflow"), item("forecasting", supports=["bullet:b1"])], material()
    )

    assert [entry["keyword"] for entry in kept] == ["forecasting"]
    assert kept[0]["canonical"] is None and dropped == 1


def test_the_validator_keeps_a_good_new_bullet_and_counts_a_duplicate_once():
    good = item(
        placement="new_bullet",
        role_id="r1",
        supports=["skill:econometría", "bullet:b1"],
        draft="Modelé series temporales aplicando statistical inference.",
    )

    kept, dropped = validate_keyword_items([good, good], material())

    assert len(kept) == 1 and dropped == 1
    assert kept[0]["role_id"] == "r1" and kept[0]["bullet_id"] is None
    assert kept[0]["confidence"] == "high"


def test_the_validator_drops_a_draft_naming_a_skill_the_sources_do_not():
    kept, dropped = validate_keyword_items(
        [
            item(
                placement="existing_bullet",
                bullet_id="b1",
                supports=["bullet:b1"],
                draft="Modelé series temporales con Airflow y statistical inference.",
            )
        ],
        material(),
    )

    assert kept == [] and dropped == 1
