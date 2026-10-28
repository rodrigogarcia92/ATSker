"""The JD view's data (§12.7): the posting cut around the keywords the analysis counted."""

from src.web.cv_pane import jd_view

POSTING = "Buscamos SQL y Python.\nKubernetes es deseable. SQL otra vez."
REPORT = {"score": {"sub_scores": {"keywords": {"matched": ["SQL"], "missing": ["Kubernetes"]}}}}


def test_the_posting_reads_back_exactly_with_each_keyword_marked():
    view = jd_view(REPORT, POSTING, (), {})

    assert "".join(segment.text for segment in view["segments"]) == POSTING
    marked = [
        (segment.text, segment.number, segment.matched)
        for segment in view["segments"]
        if segment.number
    ]
    assert marked == [("SQL", 1, True), ("Kubernetes", 2, False), ("SQL", 1, True)]
    assert (view["matched"], view["missing"]) == (1, 1)
    terms = [segment.term for segment in view["segments"] if segment.number]
    assert terms == ["SQL", "Kubernetes", "SQL"]


def test_a_matched_keyword_carries_the_cv_line_that_has_it():
    class Element:
        def __init__(self, text):
            self.text = text

    view = jd_view(REPORT, POSTING, [Element("Escribí consultas en SQL")], {})

    contexts = [segment.context for segment in view["segments"] if segment.number]
    assert contexts == ["Escribí consultas en SQL", "", "Escribí consultas en SQL"]


def test_a_report_without_keywords_marks_nothing():
    view = jd_view({}, POSTING, (), {})

    assert view == {"segments": (), "matched": 0, "missing": 0}
