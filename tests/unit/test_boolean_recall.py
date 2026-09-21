"""Scan B against known trees and known text (PRD F5.2).

No provider anywhere in this file: derivation is the model's job and evaluation is
arithmetic, so the rules are pinned here against text written by hand. The queries are
the ones the PRD prints.
"""

from src.extract.boolean import BooleanQuerySet
from src.search.boolean import SearchUnit, evaluate, match_terms, terms_of

ANA = [
    SearchUnit("bullet", "Reduje 30% el tiempo de reporte con Python", "b1"),
    SearchUnit("bullet", "Mantuve tableros de Power BI para 40 usuarios", "b2"),
    SearchUnit("role", "Analista de datos"),
    SearchUnit("education", "Universidad Nacional de Ingeniería Ingeniería de Sistemas"),
]


def queries(*items) -> list:
    return [item for item in items]


def query(label: str, expr: object):
    return BooleanQuerySet.model_validate({"queries": [{"label": label, "expr": expr}]}).queries[0]


def test_a_tree_of_and_or_and_not_is_evaluated_as_written():
    broad = query("broad", {"and": ["analista de datos", {"or": ["sql", "python"]}]})
    strict = query("strict", {"and": ["analista de datos", "sql"]})
    excluded = query("excluded", {"and": ["python", {"not": ["excel"]}]})
    ruled_out = query("ruled out", {"and": ["python", {"not": ["power bi"]}]})

    report = evaluate(queries(broad, strict, excluded, ruled_out), ANA, {})

    assert [result.passed for result in report.queries] == [True, False, True, False]
    assert report.passed == 2 and report.failed == 2


def test_the_failing_clause_is_named_the_way_the_panel_shows_it():
    strict = query("strict", {"and": ["python", "master data management"]})

    report = evaluate(queries(strict), ANA, {})

    result = report.queries[0]
    assert result.passed is False
    assert result.failing_term == "master data management"
    assert result.failing_kind == "missing", "no alias of this term appears in this track"


def test_a_failing_or_names_the_whole_group():
    """Naming one alternative would hide that neither of them is there."""
    narrow = query("narrow", {"and": ["python", {"or": ["sql", "r"]}]})

    report = evaluate(queries(narrow), ANA, {})

    assert report.queries[0].failing_term == "sql / r"
    assert report.queries[0].failing_kind == "missing"


def test_a_not_clause_says_the_term_is_there_rather_than_missing():
    excluded = query("excluded", {"and": ["python", {"not": ["Power BI"]}]})

    report = evaluate(queries(excluded), ANA, {})

    assert report.queries[0].failing_kind == "present"
    assert report.queries[0].failing_term == "Power BI", "the term as the query wrote it"


def test_a_clause_that_passed_says_which_bullet_satisfied_it():
    broad = query("broad", {"and": ["python", "tableros"]})

    report = evaluate(queries(broad), ANA, {})

    clauses = {clause.term: clause for clause in report.queries[0].clauses}
    assert clauses["python"].matched is True
    assert clauses["python"].bullet_id == "b1"
    assert clauses["python"].unit_text == "Reduje 30% el tiempo de reporte con Python"
    assert clauses["tableros"].bullet_id == "b2"
    assert report.queries[0].passed is True


def test_a_clause_found_outside_a_bullet_names_the_kind_it_found():
    role = query("role", {"and": ["analista de datos"]})

    report = evaluate(queries(role), ANA, {})

    clause = report.queries[0].clauses[0]
    assert clause.unit_kind == "role"
    assert clause.bullet_id is None
    assert clause.unit_text == "Analista de datos"


def test_terms_match_through_the_vocabularys_aliases():
    """The vocabulary is what a résumé is written in, so a query for `ml` finds one."""
    aliases = {"aprendizaje automatico": "machine learning", "ml": "machine learning"}
    units = [SearchUnit("bullet", "Modelé el riesgo con aprendizaje automático", "b1")]

    report = evaluate(queries(query("core", {"and": ["ml"]})), units, aliases)

    assert report.queries[0].passed is True


def test_accent_folding_makes_analisis_and_analisis_the_same_term():
    units = [SearchUnit("bullet", "Análisis de riesgo crediticio", "b1")]

    report = evaluate(queries(query("broad", {"and": ["analisis"]})), units, {})

    assert report.queries[0].passed is True


def test_a_longer_alias_consumes_its_span_so_the_same_words_answer_once():
    """Decision 6: `machine learning` must not also satisfy a clause for `learning`."""
    hits = match_terms(
        ["machine learning", "learning"],
        [SearchUnit("bullet", "Trabajé con machine learning en producción", "b1")],
        {},
    )

    assert set(hits) == {"machine learning"}


def test_a_node_with_nothing_in_it_constrains_nothing():
    empty = query("empty", {"and": []})

    report = evaluate(queries(empty), ANA, {})

    assert report.queries[0].passed is True
    assert report.queries[0].clauses == ()


def test_no_queries_or_no_text_is_reported_as_nothing_checked():
    assert evaluate([], ANA, {}).checked is False
    assert evaluate(queries(query("broad", {"and": ["python"]})), [], {}).checked is False


def test_the_report_serialises_every_query_and_clause():
    payload = evaluate(
        queries(query("broad", {"and": ["python", "cobol"]})), ANA, {}
    ).to_dict()

    assert payload["checked"] is True and payload["units"] == len(ANA)
    assert payload["passed"] == 0 and payload["failed"] == 1
    entry = payload["queries"][0]
    assert entry["label"] == "broad" and entry["passed"] is False
    assert entry["failing_term"] == "cobol"
    assert {clause["term"]: clause["matched"] for clause in entry["clauses"]} == {
        "python": True,
        "cobol": False,
    }
    assert "b1" in str(entry), "the citation travels with the clause"


def test_the_prds_own_example_tree_parses_and_evaluates():
    """The shape the specification prints, term for term."""
    payload = {
        "queries": [
            {"label": "broad", "expr": {"and": ["data analyst", {"or": ["sql", "python"]}]}},
            {
                "label": "core",
                "expr": {"and": ["mdm", "data governance", {"or": ["json schema", "api"]}]},
            },
            {
                "label": "strict",
                "expr": {"and": ["master data management", "data modeling", "sql", "english"]},
            },
        ]
    }
    parsed = BooleanQuerySet.model_validate(payload)
    units = [
        SearchUnit("bullet", "I built the data governance model and its JSON Schema", "b1"),
        SearchUnit("bullet", "Data analyst with SQL and Python", "b2"),
    ]

    report = evaluate(parsed.queries, units, {})

    assert [result.passed for result in report.queries] == [True, False, False]
    assert report.queries[0].passed is True
    assert report.queries[1].failing_term == "mdm", "the first clause that is not there"
    assert terms_of(parsed.queries[2].expr) == [
        "master data management",
        "data modeling",
        "sql",
        "english",
    ]