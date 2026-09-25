"""Vocabulary behaviour: seeding, alias lookup, and promotion as the only growth path."""

import json
from pathlib import Path

from src.normalize.text import fold
from src.vocabulary import (
    SKILL_KINDS,
    alias_map,
    list_unmapped,
    log_unmapped,
    promote_alias,
    seed_vocabulary,
    vocabulary_hash,
)
from tests.conftest import login

SEED_FILE = Path(__file__).resolve().parents[2] / "src" / "normalize" / "skills_seed.json"


def test_seed_file_is_internally_consistent():
    """The seed is data, so its invariants are checked rather than trusted."""
    entries = json.loads(SEED_FILE.read_text(encoding="utf-8"))
    canonicals = [entry["canonical"] for entry in entries]
    aliases = [alias for entry in entries for alias in entry["aliases"]]

    assert len(entries) >= 60
    assert len(canonicals) == len(set(canonicals))
    assert not set(canonicals) & set(aliases)
    assert len(aliases) == len(set(aliases))
    assert all(value == value.lower() for value in canonicals + aliases)
    assert all(set(entry["lang_tags"]) <= {"es", "en"} and entry["lang_tags"] for entry in entries)
    folded = [fold(value) for value in canonicals + aliases]
    assert len(folded) == len(set(folded)), "aliases must not collide after folding"
    # Every entry carries a kind, and every kind is in use — `experience` is what
    # makes a posting's "fieldwork" a first-class canonical like `python` (F3).
    assert all(entry.get("kind") in SKILL_KINDS for entry in entries)
    assert {entry["kind"] for entry in entries} == set(SKILL_KINDS)


def test_seeding_is_idempotent_and_never_drops_a_promoted_alias(session):
    entries = [
        {"canonical": "python", "aliases": ["python", "py"], "lang_tags": ["es", "en"]},
        {"canonical": "power bi", "aliases": ["power bi"], "lang_tags": ["es", "en"]},
    ]

    first = seed_vocabulary(session, entries)
    promote_alias(session, "power bi", "powerbi")
    second = seed_vocabulary(session, entries)

    assert first == {"created": 2, "enriched": 0, "total": 2}
    assert second == {"created": 0, "enriched": 0, "total": 2}
    assert "powerbi" in alias_map(session)


def test_seeding_stamps_kind_and_a_later_seed_corrects_it(session):
    from sqlalchemy import select

    from src.models import Skill

    entry = {
        "canonical": "fieldwork",
        "aliases": ["trabajo de campo"],
        "lang_tags": ["es", "en"],
        "kind": "experience",
    }

    seed_vocabulary(session, [entry])
    skill = session.scalar(select(Skill).where(Skill.canonical == "fieldwork"))
    assert skill.kind == "experience"

    # A kind is seed data: re-running the seed corrects it (this is how the 140
    # pre-N1 rows get their real kinds after migration 0004).
    seed_vocabulary(session, [{**entry, "kind": "domain"}])
    assert skill.kind == "domain"


def test_seeding_fills_a_family_but_never_overwrites_one_a_human_set(session):
    """F5.4.1: families are data the operator reviews — the seed may fill the
    empty ones and stops there, so a reviewed grouping survives every re-seed."""
    from sqlalchemy import select

    from src.models import Skill

    entry = {
        "canonical": "power bi",
        "aliases": ["powerbi"],
        "lang_tags": ["es", "en"],
        "kind": "tool",
        "family": "bi_tool",
    }

    seed_vocabulary(session, [entry])
    skill = session.scalar(select(Skill).where(Skill.canonical == "power bi"))
    assert skill.family == "bi_tool"

    skill.family = "bi_suite_reviewed"
    seed_vocabulary(session, [entry])

    assert skill.family == "bi_suite_reviewed", "a family somebody set is never overwritten"


def test_the_vocabulary_page_shows_each_skills_kind(client, session, two_accounts):
    from src.models import Skill

    session.add(
        Skill(
            canonical="fieldwork",
            aliases=["trabajo de campo"],
            lang_tags=["es"],
            kind="experience",
        )
    )
    session.commit()

    login(client, two_accounts[0][0].email)
    page = client.get("/vocabulary")

    assert "fieldwork" in page.text
    assert "Experiencia" in page.text


def test_canonical_is_its_own_alias_and_accents_fold(session):
    seed_vocabulary(
        session,
        [
            {
                "canonical": "machine learning",
                "aliases": ["aprendizaje automático"],
                "lang_tags": ["es"],
            }
        ],
    )

    mapping = alias_map(session)
    assert mapping["machine learning"] == "machine learning"
    assert mapping["aprendizaje automatico"] == "machine learning"


def test_unmapped_terms_accumulate_and_promotion_marks_them(session):
    log_unmapped(session, ["cobalto", "reactor"])
    log_unmapped(session, ["cobalto"])

    terms = {term.term: term for term in list_unmapped(session)}
    assert terms["cobalto"].seen_count == 2
    assert terms["reactor"].seen_count == 1

    promote_alias(session, "machine learning", "cobalto")

    assert {term.term: term.status for term in list_unmapped(session)}["cobalto"] == "promoted"


def test_a_new_canonical_can_be_created_by_promotion(session):
    skill = promote_alias(session, "Power BI", "powerbi")

    assert skill.canonical == "power bi"
    assert "powerbi" in skill.aliases
    assert skill.lang_tags == ["es", "en"]


def test_two_identical_vocabularies_hash_the_same_and_an_added_alias_changes_it(session):
    """F3.1: the hash names the vocabulary a report used, so it must be a pure
    function of its content — not of insertion order — and must see an alias."""
    from src.models import Skill

    entries = [
        {"canonical": "python", "aliases": ["py"], "lang_tags": ["es", "en"]},
        {"canonical": "excel", "aliases": ["hojas de calculo"], "lang_tags": ["es", "en"]},
    ]
    seed_vocabulary(session, entries)
    first = vocabulary_hash(session)
    assert first.startswith("sha256:")

    session.query(Skill).delete()
    seed_vocabulary(session, list(reversed(entries)))
    assert vocabulary_hash(session) == first, "two identical vocabularies hash the same"

    promote_alias(session, "python", "python3")
    assert vocabulary_hash(session) != first, "an added alias changes the hash"
