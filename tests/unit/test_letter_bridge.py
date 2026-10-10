"""F8.3: one bridge at a time — banned phrases, hard and soft rules, prompt v2.

`check_bridge` returns `(hard, soft)`: a hard failure means no paragraph, a soft one is
shown and marked. The provider is stubbed at `extract_client._post`; the user message and
the cache key are what the call tests read.
"""

import json
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from src.applications import create_application
from src.extract import client as extract_client
from src.extract.generation import generate_letter_bridge_one
from src.extract.prompts import LETTER_BRIDGE_V2
from src.generate.letters import (
    banned_in,
    banned_phrases,
    check_bridge,
    letter_checklist,
    sentences_in,
)
from src.generate.validators import LITERAL, PROVENANCE, Sources
from src.models import LlmCall

JD = "Analista de datos — Banco Demo 1\nBuscamos un analista con Python y SQL."
TITLE = "Analista de datos"
COMPANY = "Banco Demo 1"

# Three plain sentences that cite the user's bullet and say nothing the sources do not.
GOOD = (
    "El puesto pide Python y SQL para convertir datos en decisiones. "
    "Eso es lo que hago desde hace años. "
    "Me interesa Banco Demo 1 porque trabaja con datos de verdad."
)

TEMPLATE = SimpleNamespace(
    presentation="Soy Ana, analista de datos.",
    achievements="Reduje 30% el tiempo de reporte y pasé de 12 a 3 días.",
)


def sources(career) -> Sources:
    return Sources(bullets={str(career.first_bullet.id): career.first_bullet.text_es})


def bridge(career, **overrides) -> dict:
    output = {
        "angle": "impacto",
        "text": GOOD,
        "sources": [str(career.first_bullet.id)],
        "company_fact": None,
        "risk": None,
    }
    output.update(overrides)
    return output


def check(career, output, *, lang="es", template=TEMPLATE):
    return check_bridge(
        output,
        sources=sources(career),
        template=template,
        jd_text=JD,
        company=COMPANY,
        title=TITLE,
        lang=lang,
    )


# --- the banned phrases ---------------------------------------------------------------


def test_banned_in_finds_phrases_ignoring_case_and_accents():
    assert banned_in("Me apasiona el análisis de datos.", "es") == ["me apasiona"]
    assert banned_in("We LEVERAGE data daily.", "en") == ["leverage"]
    assert banned_in("En un mundo cada vez mas conectado, importa.", "es") == [
        "en un mundo cada vez más"
    ]
    assert banned_in("I’m passionate about it; in today’s fast-paced market.", "en") == [
        "in today's fast-paced",
        "passionate about",
    ]


def test_banned_in_matches_on_word_boundaries_only():
    assert banned_in("They leveraged the data and the leverager of it.", "en") == []
    assert banned_in("Un trabajo sinergético.", "es") == []
    assert banned_in("Una Sinergia   real.", "es") == ["sinergia"], "whitespace is folded"


def test_banned_in_reads_the_language_it_is_given():
    assert banned_in("me apasiona", "en") == []
    assert banned_in("leverage", "es") == []
    assert banned_in("leverage", "fr") == []
    assert "me apasiona" in banned_phrases("es") and "leverage" in banned_phrases("en")


def test_sentences_are_split_after_terminal_punctuation_ignoring_empty_parts():
    assert len(sentences_in("Uno. Dos! ¿Tres? Cuatro… Cinco.")) == 5
    assert len(sentences_in("  Una sola frase sin punto  ")) == 1
    assert sentences_in("") == []


# --- hard and soft rules --------------------------------------------------------------


def test_a_valid_bridge_has_no_violations(career):
    assert check(career, bridge(career)) == ([], [])


def test_citing_none_of_the_users_material_is_hard(career):
    hard, soft = check(career, bridge(career, sources=[]))

    assert [violation.rule for violation in hard] == [PROVENANCE]
    assert hard[0].message == "the bridge cites none of your material"
    assert soft == []


def test_an_id_that_was_never_supplied_is_hard(career):
    hard, _soft = check(career, bridge(career, sources=[str(career.first_bullet.id), "inventado"]))

    assert [violation.message for violation in hard] == ["inventado was not a supplied source"]


def test_an_invented_number_is_hard(career):
    hard, _soft = check(
        career, bridge(career, text="El puesto pide Python. Logré un 77% más de velocidad.")
    )

    assert any(violation.rule == LITERAL and "77%" in violation.text for violation in hard)


def test_a_number_from_the_achievements_paragraph_is_hard(career):
    template = SimpleNamespace(presentation="x", achievements="Reduje 30% el tiempo.")
    hard, _soft = check(
        career,
        bridge(career, text="Automaticé un 30% del reporte con Python."),
        template=template,
    )

    repeated = [v for v in hard if v.message.startswith("repeats a number")]
    assert len(repeated) == 1 and repeated[0].text == "30"


def test_an_unattributed_company_fact_is_hard(career):
    invented = {"text": "Banco Demo 1 es líder regional", "jd_quote": "es líder regional"}
    attributed = {"text": "Banco Demo 1", "jd_quote": "Analista de datos — Banco Demo 1"}

    bad_hard, _ = check(career, bridge(career, company_fact=invented))
    good_hard, _ = check(career, bridge(career, company_fact=attributed))

    assert [violation.item for violation in bad_hard] == ["company_fact"]
    assert good_hard == []


def test_more_than_four_sentences_is_soft(career):
    text = "Python y SQL. Datos. Reportes. Tableros. Decisiones."

    hard, soft = check(career, bridge(career, text=text))

    assert hard == []
    assert [violation.message for violation in soft] == ["5 sentences, over 4"]


def test_more_than_ninety_words_is_soft(career):
    text = "El puesto pide Python y SQL " + " ".join(["datos"] * 90) + "."

    hard, soft = check(career, bridge(career, text=text))

    assert hard == []
    assert any(violation.message.endswith("words, over 90") for violation in soft)


def test_a_banned_phrase_is_soft_and_names_the_phrase(career):
    text = "El puesto pide Python y SQL. Me apasiona el análisis. Es lo que hago."

    hard, soft = check(career, bridge(career, text=text))

    assert hard == []
    assert [(violation.rule, violation.text) for violation in soft] == [("banned", "me apasiona")]


def test_the_banned_list_follows_the_language_of_the_check(career):
    text = "The role asks for Python and SQL. We leverage data."

    _hard, soft_en = check(career, bridge(career, text=text), lang="en")
    _hard, soft_es = check(career, bridge(career, text=text), lang="es")

    assert [violation.text for violation in soft_en] == ["leverage"]
    assert soft_es == []


# --- the call -------------------------------------------------------------------------


class Provider:
    def __init__(self, payload: dict):
        self.calls: list[dict] = []
        self.payload = payload

    def __call__(self, payload: dict, api_key: str) -> dict:
        self.calls.append(payload)
        return {
            "choices": [{"message": {"content": json.dumps(self.payload)}}],
            "usage": {"prompt_tokens": 1500, "completion_tokens": 400, "cost": "0.000120"},
        }


@pytest.fixture
def provider(monkeypatch, test_settings, career) -> Provider:
    stub = Provider(
        {
            "angle": "impacto",
            "text": GOOD,
            "sources": [str(career.first_bullet.id)],
            "company_fact": None,
            "risk": "Salto hacia banca privada.",
        }
    )
    monkeypatch.setattr(extract_client, "_post", stub)
    return stub


def call(session, previous, **overrides):
    arguments = {
        "jd_text": JD,
        "company": COMPANY,
        "title": TITLE,
        "template": TEMPLATE,
        "material": "bullet-1\tReduje el tiempo de reporte",
        "voice_notes": "Tuteo.",
        "language": "es",
        "banned": banned_phrases("es"),
        "previous": previous,
    }
    arguments.update(overrides)
    return generate_letter_bridge_one(session, **arguments)


def test_the_call_sends_the_previous_texts_and_the_banned_list(session, provider):
    proposal = call(session, ["Primera versión escrita.", "Segunda versión escrita."])

    message = provider.calls[0]["messages"][1]["content"]
    assert "Previous versions — write something different:" in message
    assert "1. Primera versión escrita." in message and "2. Segunda versión escrita." in message
    assert "- me apasiona" in message and "- sinergia" in message
    assert "leverage" not in message, "only the language's own list is sent"
    assert "Soy Ana, analista de datos." in message, "the track's presentation is the style"
    assert "Reduje 30%" in message, "and so are its achievements"
    assert "Tuteo." in message and TITLE in message and "Write in es." in message
    assert proposal.kind == "letter_bridge"
    assert proposal.output["text"] == GOOD
    assert proposal.output["risk"] == "Salto hacia banca privada."
    assert proposal.output["sources"] and proposal.output["company_fact"] is None


def test_no_previous_versions_says_none(session, provider):
    call(session, [])

    message = provider.calls[0]["messages"][1]["content"]
    assert "Previous versions — write something different:\n(none)" in message


def test_the_call_is_logged_under_prompt_v2(session, provider):
    call(session, [])

    row = session.scalars(select(LlmCall)).one()
    assert (row.purpose, row.prompt_version) == ("letter_bridge", "letter_bridge_v2")
    assert LETTER_BRIDGE_V2.version == "letter_bridge_v2"
    assert row.cost_usd == Decimal("0.000120")


def test_different_previous_lists_are_different_cache_keys(session, provider):
    call(session, [])
    call(session, [])
    assert len(provider.calls) == 1, "the same input is served from the cache"

    call(session, ["Una versión anterior."])
    call(session, ["Una versión anterior.", "Otra más."])

    assert len(provider.calls) == 3, "each new list of previous texts is a fresh call"


def test_repair_turns_the_call_into_a_fresh_one_naming_the_rule(session, provider):
    call(session, [])
    call(session, [], repair="use no banned phrase")

    assert len(provider.calls) == 2
    assert "Your previous answer was unusable: use no banned phrase" in (
        provider.calls[1]["messages"][1]["content"]
    )


# --- the checklist --------------------------------------------------------------------


def application_for(career, session):
    application = create_application(
        career.first_profile.id,
        session,
        jd_text=JD,
        jd_hash="sha256:bridge",
        company=COMPANY,
        title=TITLE,
        report={"jd": {"language": "es", "title": TITLE}, "score": {}, "llm": {"calls": []}},
        weights_version="w4",
        prompt_versions={},
        token_cost_usd=Decimal(0),
        track_id=career.first_track.id,
    )
    session.commit()
    return application


def items(application, **overrides) -> dict:
    arguments = {
        "text": f"Estimado equipo de {COMPANY}. {TITLE}. {GOOD}",
        "application": application,
        "language": "es",
        "unresolved": [],
        "facts_attributed": True,
        "track_lang": "es",
        "bridge_text": GOOD,
    }
    arguments.update(overrides)
    return {item["key"]: item for item in letter_checklist(**arguments)}


def test_the_checklist_reports_banned_phrases_and_sentences(session, career):
    application = application_for(career, session)
    clean = items(application)
    bad_text = "Python y SQL. Me apasiona esto. Tres. Cuatro. Cinco."
    dirty = items(application, bridge_text=bad_text)

    assert clean["banned"]["ok"] and clean["sentences"]["ok"]
    assert dirty["banned"]["ok"] is False and dirty["banned"]["detail"] == "me apasiona"
    assert dirty["sentences"]["ok"] is False and dirty["sentences"]["detail"] == "5 / 4"


def test_the_language_check_compares_the_letter_with_the_tracks(session, career):
    application = application_for(career, session)

    assert items(application, language="es", track_lang="es")["language"]["ok"] is True
    assert items(application, language="en", track_lang="es")["language"]["ok"] is False


def test_the_checklist_keeps_its_earlier_items_in_order(session, career):
    application = application_for(career, session)

    keys = [item["key"] for item in letter_checklist(
        text="x",
        application=application,
        language="es",
        unresolved=[],
        facts_attributed=True,
    )]

    assert keys == [
        "placeholders", "title", "company", "length", "facts", "language", "banned", "sentences"
    ]
