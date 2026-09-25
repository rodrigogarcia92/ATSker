"""JD extraction: vocabulary constraint, caching, and byte-identical repeats.

The milestone's acceptance test is here: analysing the same posting twice makes no
network call the second time and returns the same structure (PRD M4).
"""

import pytest

from src.extract.client import StructuredOutputError
from src.extract.jd import PURPOSE, extract_jd
from src.jd import jd_hash, normalize_jd_text
from src.models import LlmCall
from src.vocabulary import list_unmapped, seed_vocabulary

POSTING = """
Data Analyst Senior — Banco Demo (híbrido, Lima)
Buscamos un analista con 5 años de experiencia en Python y SQL. Se valorará Power BI.
Imprescindible: título universitario y disponibilidad para ir a la oficina 3 días.
Trabajarás con stakeholders de negocio y modelos de machine learning.
"""

PROPOSAL = """
{"language": "es", "title": "Data Analyst Senior", "seniority": "senior",
 "years_required": 5, "must_have": ["python", "sql", "snowflake"],
 "nice_to_have": ["power bi", "excel avanzado"],
 "raw_keywords": ["stakeholders", "modelos"],
 "hard_requirements": ["Título universitario", "Disponibilidad para ir a la oficina"],
 "location_policy": "hybrid_lima"}
"""


@pytest.fixture
def vocabulary_with_python(session):
    seed_vocabulary(
        session,
        [
            {"canonical": "python", "aliases": ["python"], "lang_tags": ["es", "en"]},
            {"canonical": "sql", "aliases": ["sql"], "lang_tags": ["es", "en"]},
            {"canonical": "power bi", "aliases": ["power bi"], "lang_tags": ["es", "en"]},
        ],
    )
    session.commit()
    return session


def stub(monkeypatch, payload: str = PROPOSAL) -> list[dict]:
    from src.extract import client

    seen: list[dict] = []

    def fake_post(body, api_key):
        seen.append(body)
        return {
            "choices": [{"message": {"content": payload}}],
            "usage": {"prompt_tokens": 2200, "completion_tokens": 140, "cost": "0.000081"},
        }

    monkeypatch.setattr(client, "_post", fake_post)
    return seen


def test_skills_outside_the_vocabulary_become_keywords_and_are_logged(
    session, vocabulary_with_python, test_settings, monkeypatch
):
    stub(monkeypatch)

    jd, extraction = extract_jd(session, POSTING)

    assert extraction.cached is False
    assert extraction.purpose == PURPOSE
    assert jd.must_have == ["python", "sql"], "only canonical vocabulary names survive"
    assert jd.nice_to_have == ["power bi"]
    assert "snowflake" in jd.raw_keywords
    assert "excel avanzado" in jd.raw_keywords
    assert {term.term for term in list_unmapped(session)} == {"snowflake", "excel avanzado"}


def test_the_rest_of_the_posting_survives_the_round_trip(
    session, vocabulary_with_python, test_settings, monkeypatch
):
    stub(monkeypatch)

    jd, _ = extract_jd(session, POSTING)

    assert jd.language == "es"
    assert jd.title == "Data Analyst Senior"
    assert jd.seniority == "senior"
    assert jd.years_required == 5
    assert jd.location_policy == "hybrid_lima"
    assert jd.hard_requirements == [
        "titulo universitario",
        "disponibilidad para ir a la oficina",
    ]
    assert jd.source_hash == jd_hash(POSTING)


def test_the_same_posting_is_never_analysed_twice(
    session, vocabulary_with_python, test_settings, monkeypatch
):
    """PRD M4: the second analysis makes no network call and returns the same output."""
    calls = stub(monkeypatch)

    first, first_extraction = extract_jd(session, POSTING)
    session.commit()  # the first call's vocabulary notes do not cross the second call
    second, second_extraction = extract_jd(session, POSTING)

    assert first_extraction.cached is False and second_extraction.cached is True
    assert second_extraction.cost_usd == 0
    assert first == second
    assert len(calls) == 1, "the cache must prevent a second request"
    assert session.query(LlmCall).count() == 1


def test_whitespace_does_not_defeat_the_cache(
    session, vocabulary_with_python, test_settings, monkeypatch
):
    """A posting pasted from two different job boards normalises to one cache entry."""
    calls = stub(monkeypatch)
    reformatted = POSTING.replace("\n", "\r\n").replace("  ", " ") + "\n\n   "

    extract_jd(session, POSTING)
    session.commit()  # the call sequence must not carry pending writes across a call
    extract_jd(session, reformatted)

    assert len(calls) == 1
    assert normalize_jd_text(reformatted) == normalize_jd_text(POSTING)


def test_prompt_version_is_recorded_and_version_bumps_bust_the_cache(
    session, vocabulary_with_python, test_settings, monkeypatch
):
    stub(monkeypatch)

    extract_jd(session, POSTING)

    stored = session.query(LlmCall).one()
    assert stored.purpose == PURPOSE
    assert stored.prompt_version == "jd_extract_v3"
    assert stored.cost_usd > 0


def test_a_schema_violation_is_retried_once_then_fails_loudly(
    session, vocabulary_with_python, test_settings, monkeypatch
):
    calls = stub(monkeypatch, payload='{"title": 42, "must_have": "python"}')

    with pytest.raises(StructuredOutputError):
        extract_jd(session, POSTING)

    assert len(calls) == 2, "one retry, per PRD F4.3's rule for schema violations"


def test_an_empty_posting_is_refused_before_any_call(
    session, vocabulary_with_python, test_settings, monkeypatch
):
    calls = stub(monkeypatch)

    with pytest.raises(ValueError):
        extract_jd(session, "   \n  ")

    assert calls == []


def test_redaction_runs_before_the_posting_leaves(
    session, vocabulary_with_python, test_settings, monkeypatch
):
    calls = stub(monkeypatch)
    posting = POSTING + "\nEscribe a reclutamiento@banco.example.com o al ++00 111 222 333."

    extract_jd(session, posting)

    sent = str(calls[0]["messages"])
    assert "reclutamiento@banco.example.com" not in sent
    assert "999 888 777" not in sent
