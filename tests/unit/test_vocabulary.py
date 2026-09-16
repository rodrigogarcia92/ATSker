"""Vocabulary behaviour: seeding, alias lookup, and promotion as the only growth path."""

import json
from pathlib import Path

from src.normalize.text import fold
from src.vocabulary import alias_map, list_unmapped, log_unmapped, promote_alias, seed_vocabulary

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
