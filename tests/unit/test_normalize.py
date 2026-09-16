"""Text folding, term matching and metric extraction."""

from src.normalize.metrics import extract_metrics
from src.normalize.text import fold, term_pattern
from src.normalize.vocabulary import match_text, resolve_terms

ALIASES = {
    "python": "python",
    "py": "python",
    "machine learning": "machine learning",
    "learning": "aprendizaje",
    "ml": "machine learning",
    "sql": "sql",
    "c++": "c++",
    "c": "c",
    "node.js": "node.js",
    "power bi": "power bi",
}


def test_accents_and_case_collide():
    assert fold("Análisis  de   Datos") == "analisis de datos"
    assert fold("APRENDIZAJE AUTOMÁTICO") == fold("aprendizaje automatico")


def test_term_boundaries_do_not_match_inside_longer_words():
    assert term_pattern("c").search(fold("curso de c++")) is None
    assert term_pattern("c").search(fold("programo en c")) is not None
    assert term_pattern("c++").search(fold("curso de c++")) is not None
    assert term_pattern("py").search(fold("python avanzado")) is None
    assert term_pattern("python").search(fold("python avanzado")) is not None


def test_multi_word_alias_consumes_its_span():
    """`machine learning` must not also report the separate skill `learning`."""
    found = match_text("Experiencia en machine learning y SQL", ALIASES)
    assert "machine learning" in found
    assert "aprendizaje" not in found


def test_matching_is_accent_insensitive_in_both_directions():
    aliases = {"aprendizaje automatico": "machine learning", "analisis de datos": "data analysis"}
    assert match_text("Hice un proyecto de aprendizaje automático", aliases) == ["machine learning"]
    assert match_text("Análisis de datos para ventas", aliases) == ["data analysis"]


def test_known_terms_resolve_and_unknown_ones_survive_for_review():
    canonical, unmatched = resolve_terms(["Py", "  SQL ", "Cobalto"], ALIASES)
    assert canonical == ["python", "sql"]
    assert unmatched == ["cobalto"]


def test_metrics_are_extracted_in_order_and_deduplicated():
    metrics = extract_metrics("Reduje 30% el tiempo en 6 meses y ahorré $1.2M; el 30% se mantuvo")
    assert metrics == ["30%", "6 meses", "$1.2M"]


def test_years_count_as_numeric_tokens():
    """A year is a number; F7's validator must find it in the source bullet too."""
    assert extract_metrics("Certificación obtenida en 2023") == ["2023"]
