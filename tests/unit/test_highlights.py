"""The highlight map (§12.7) over hand-written reports.

No provider and no database: the map is arithmetic over a stored report, so every case
below is a report dict built by hand and a pane rendered from a synthetic draft. The
sections and keys asserted here are the ones the report items and the marks will share.
"""

import pytest

from src.cv_context import draft_digest
from src.highlights import (
    COMPONENTS,
    RECOMMENDATIONS,
    RECRUITER,
    REQUIREMENTS,
    STRONG,
    WEAK,
    build_highlight_map,
    draft_is_current,
    render_cv,
)

ALIASES = {"postgres": "sql", "sql": "sql", "bi": "power bi", "power bi": "power bi"}

BULLET_0 = "Reduje 30% el tiempo de reporte con Postgres"
POSTGRES = (36, 44)  # where `Postgres` sits in BULLET_0
SUMMARY = "Analista de datos con foco en reportes."

DRAFT: dict = {
    "language": "es",
    "headline": "Analista de datos",
    "summary": SUMMARY,
    "skills": ["Python", "SQL"],
    "roles": [
        {
            "employer": "Globex",
            "title": "Analista de datos",
            "start_date": "2021-03",
            "end_date": "2024-01",
            "bullets": [
                {"text": BULLET_0, "chips": ["sql"]},
                {"text": "Mantuve tableros de Power BI", "chips": ["power bi"]},
            ],
        },
        {
            "employer": "Banco Andino",
            "title": "Analista de riesgo",
            "start_date": "2019-01",
            "end_date": "2021-02",
            "bullets": [{"text": "Automaticé informes mensuales", "chips": []}],
        },
    ],
    "educations": [
        {"institution": "Universidad Nacional", "award": "Ingeniería", "field": "Sistemas"}
    ],
    "certifications": [{"name": "Certificado Power BI", "issuer": "Microsoft"}],
}

SNAPSHOTS = [
    {"id": "b0", "temporary": True, "role_id": "r0", "text": BULLET_0, "ordinal": 0},
    {
        "id": "b1",
        "temporary": True,
        "role_id": "r0",
        "text": "Mantuve tableros de Power BI",
        "ordinal": 1,
    },
    {
        "id": "b2",
        "temporary": True,
        "role_id": "r1",
        "text": "Automaticé informes mensuales",
        "ordinal": 2,
    },
]


def make_report(**overrides: object) -> dict:
    """A stored CV report with nothing marked, unless the case says otherwise."""
    report: dict = {
        "cv": {
            "resume_id": "cv-1",
            "filename": "cv.docx",
            "chosen": "explicit",
            "draft_sha": draft_digest(DRAFT),
            "matched_ids": [],
            "represented_ids": [],
        },
        "bullets": [dict(row) for row in SNAPSHOTS],
        "role_matching": [
            {"file_title": "Analista de datos", "matched_role_id": "r0", "by": "employer_title"},
            {"file_title": "Analista de riesgo", "matched_role_id": "r1", "by": "employer_start"},
        ],
        "grades": [],
        "recall": {"queries": []},
        "advice": [],
        "score": {"sub_scores": {}},
    }
    report.update(overrides)
    return report


def grade(**overrides: object) -> dict:
    row: dict = {
        "requirement": "Excel",
        "must_have": True,
        "level": 3,
        "basis": "direct",
        "source": "bullet",
        "bullet_id": "b0",
    }
    row.update(overrides)
    return row


def marks_of(report: dict, draft: dict | None = None) -> list:
    return build_highlight_map(report, render_cv(draft if draft is not None else DRAFT), ALIASES)


def rich_report() -> dict:
    """One report that exercises every source at once, for the overlap invariant."""
    return make_report(
        grades=[
            grade(requirement="Postgres"),
            grade(requirement="Excel", bullet_id="b2"),
            grade(requirement="reportes", source="summary", bullet_id=None),
        ],
        recall={
            "queries": [
                {
                    "label": "SQL + reportes",
                    "passed": True,
                    "clauses": [
                        {"term": "SQL", "matched": True, "unit_kind": "bullet", "bullet_id": "b0"}
                    ],
                }
            ]
        },
        advice=[{"kind": "promote_bullet", "bullet_id": "b1", "values": {}}],
        score={
            "sub_scores": {
                "keywords": {"matched": ["SQL", "Power BI"]},
                "title": {"matched": ["analista", "datos"]},
                "experience": {
                    "detail": {
                        "relevant_roles": [
                            {"id": "r0", "title": "Analista de datos", "weight": 1.0}
                        ]
                    }
                },
            }
        },
    )


# --- the pane's text -------------------------------------------------------------------


def test_render_cv_gives_the_panes_text_stable_ids_in_the_files_order():
    elements = render_cv(DRAFT)
    assert [element.id for element in elements] == [
        "headline",
        "summary",
        "role:0",
        "role:0:bullet:0",
        "role:0:bullet:1",
        "role:1",
        "role:1:bullet:0",
        "skills",
        "education:0",
        "certification:0",
    ]
    assert elements[0].kind == "headline" and elements[0].text == "Analista de datos"
    assert elements[2].text == "Analista de datos — Globex (2021-03 – 2024-01)"
    assert elements[3].text == BULLET_0
    assert elements[7].text == "Python, SQL"
    assert elements[8].text == "Universidad Nacional Ingeniería Sistemas"
    assert elements[9].text == "Certificado Power BI Microsoft"


def test_render_cv_keeps_an_empty_bullet_so_the_file_wide_ordinal_stays_aligned():
    draft = {
        "roles": [
            {"employer": "Globex", "title": "Analista", "bullets": [{"text": ""}, {"text": "SQL"}]}
        ]
    }
    elements = render_cv(draft)
    assert [element.id for element in elements] == ["role:0", "role:0:bullet:0", "role:0:bullet:1"]
    assert elements[1].text == ""


def test_render_cv_of_an_empty_draft_has_no_elements():
    assert render_cv({}) == []


# --- keywords --------------------------------------------------------------------------


def test_a_matched_keyword_marks_a_span_that_is_an_alias_of_it():
    report = make_report(score={"sub_scores": {"keywords": {"matched": ["SQL"]}}})
    marks = [m for m in marks_of(report) if m.key == "keyword:SQL"]
    assert [(m.element, m.start, m.end) for m in marks] == [
        ("role:0:bullet:0", *POSTGRES),
        ("skills", 8, 11),
    ]
    assert BULLET_0[POSTGRES[0] : POSTGRES[1]] == "Postgres"
    assert all(m.section == COMPONENTS and m.strength == STRONG for m in marks)


def test_the_longest_alias_consumes_its_span():
    report = make_report(score={"sub_scores": {"keywords": {"matched": ["Power BI"]}}})
    elements = render_cv(DRAFT)
    texts = {element.id: element.text for element in elements}
    marks = marks_of(report)
    for element_id in ("role:0:bullet:1", "certification:0"):
        spans = [m for m in marks if m.element == element_id]
        assert len(spans) == 1  # `bi` inside `Power BI` did not mark a second span
        assert texts[element_id][spans[0].start : spans[0].end] == "Power BI"


# --- title -----------------------------------------------------------------------------


def test_title_words_are_marked_in_the_headline_and_the_role_titles_only():
    report = make_report(score={"sub_scores": {"title": {"matched": ["analista", "datos"]}}})
    marks = marks_of(report)
    assert {m.element for m in marks} == {"headline", "role:0", "role:1"}
    assert all(m.key == "title" and m.section == COMPONENTS for m in marks)
    assert [(m.start, m.end) for m in marks if m.element == "headline"] == [(0, 8), (12, 17)]
    assert [(m.start, m.end) for m in marks if m.element == "role:1"] == [(0, 8)]


# --- experience ------------------------------------------------------------------------


def test_relevant_roles_headers_are_marked_and_a_transfer_is_weak():
    report = make_report(
        score={
            "sub_scores": {
                "experience": {
                    "detail": {
                        "relevant_roles": [
                            {"id": "r0", "title": "Analista de datos", "weight": 1.0},
                            {"id": "r1", "title": "Analista de riesgo", "weight": 0.5},
                        ]
                    }
                }
            }
        }
    )
    by_element = {m.element: m for m in marks_of(report)}
    assert by_element["role:0"].key == "role:r0" and by_element["role:0"].strength == STRONG
    assert (by_element["role:0"].start, by_element["role:0"].end) == (
        0,
        len("Analista de datos — Globex (2021-03 – 2024-01)"),
    )
    assert by_element["role:1"].key == "role:r1" and by_element["role:1"].strength == WEAK


def test_a_file_only_role_is_paired_with_its_relevant_id_by_position():
    report = make_report(
        role_matching=[
            {"file_title": "Analista de datos", "matched_role_id": "r0", "by": "employer_title"},
            {"file_title": "Analista de riesgo", "matched_role_id": None, "by": "file_only"},
        ],
        score={
            "sub_scores": {
                "experience": {
                    "detail": {
                        "relevant_roles": [
                            {"id": "r0", "title": "Analista de datos", "weight": 1.0},
                            {"id": "transient", "title": "Analista de riesgo", "weight": 1.0},
                        ]
                    }
                }
            }
        },
    )
    marks = marks_of(report)
    assert {m.key for m in marks} == {"role:r0", "role:transient"}
    assert {m.element for m in marks} == {"role:0", "role:1"}


# --- requirements ----------------------------------------------------------------------


def test_every_cited_bullet_of_a_requirement_is_marked_whole():
    report = make_report(grades=[grade()])
    marks = [m for m in marks_of(report) if m.element == "role:0:bullet:0"]
    assert [(m.start, m.end, m.section, m.key, m.strength) for m in marks] == [
        (0, len(BULLET_0), REQUIREMENTS, "requirement:0", STRONG)
    ]


def test_a_requirement_marks_its_own_term_inside_the_cited_bullet():
    report = make_report(
        grades=[grade(requirement="Postgres")],
        score={"sub_scores": {"keywords": {"matched": ["SQL"]}}},
    )
    marks = [m for m in marks_of(report) if m.element == "role:0:bullet:0"]
    assert sorted((m.start, m.end, m.key) for m in marks) == [
        (0, 36, "requirement:0"),
        (36, 44, "keyword:SQL"),
        (36, 44, "requirement:0"),
    ]


def test_a_nested_span_with_the_same_key_merges_back_into_one_mark():
    report = make_report(grades=[grade(requirement="Postgres")])
    marks = [m for m in marks_of(report) if m.element == "role:0:bullet:0"]
    assert [(m.start, m.end, m.key) for m in marks] == [(0, len(BULLET_0), "requirement:0")]


@pytest.mark.parametrize(
    ("level", "basis", "strength"),
    [
        (3, "direct", STRONG),
        (3, "equivalent", WEAK),
        (2, "transferable", WEAK),
        (1, "direct", WEAK),
    ],
)
def test_level_one_and_non_direct_evidence_is_weak(level: int, basis: str, strength: str):
    report = make_report(grades=[grade(level=level, basis=basis)])
    marks = [m for m in marks_of(report) if m.element == "role:0:bullet:0"]
    assert marks and all(m.strength == strength for m in marks)


def test_a_summary_citation_marks_the_summary():
    report = make_report(grades=[grade(requirement="Excel", source="summary", bullet_id=None)])
    marks = [m for m in marks_of(report) if m.element == "summary"]
    assert [(m.start, m.end, m.section, m.key) for m in marks] == [
        (0, len(SUMMARY), REQUIREMENTS, "requirement:0")
    ]


def test_a_skills_list_citation_marks_the_skills_line():
    report = make_report(grades=[grade(requirement="Excel", source="skills_list", bullet_id=None)])
    assert [m.element for m in marks_of(report)] == ["skills"]


def test_two_requirements_citing_one_bullet_share_the_span_with_two_keys():
    report = make_report(grades=[grade(requirement="Excel"), grade(requirement="PowerPoint")])
    marks = [m for m in marks_of(report) if m.element == "role:0:bullet:0"]
    assert [(m.start, m.end) for m in marks] == [(0, len(BULLET_0)), (0, len(BULLET_0))]
    assert {m.key for m in marks} == {"requirement:0", "requirement:1"}


# --- the recruiter's queries -----------------------------------------------------------


def test_a_recall_clause_marks_the_span_that_satisfied_it():
    report = make_report(
        recall={
            "queries": [
                {
                    "label": "SQL + reportes",
                    "passed": True,
                    "clauses": [
                        {
                            "term": "SQL",
                            "matched": True,
                            "unit_kind": "bullet",
                            "bullet_id": "b0",
                            "unit_text": BULLET_0,
                        }
                    ],
                }
            ]
        }
    )
    marks = [m for m in marks_of(report) if m.section == RECRUITER]
    assert [(m.element, m.start, m.end, m.key, m.strength) for m in marks] == [
        ("role:0:bullet:0", *POSTGRES, "query:SQL + reportes", STRONG)
    ]


def test_a_clause_consumes_its_span_so_the_next_clause_cannot_reuse_it():
    draft = {
        "roles": [
            {"employer": "Globex", "title": "Analista", "bullets": [{"text": "Power BI y BI"}]}
        ]
    }
    report = make_report(
        recall={
            "queries": [
                {
                    "label": "BI",
                    "passed": True,
                    "clauses": [
                        {"term": "Power BI", "matched": True},
                        {"term": "BI", "matched": True},
                    ],
                }
            ]
        }
    )
    marks = [m for m in marks_of(report, draft) if m.section == RECRUITER]
    assert [(m.start, m.end) for m in marks] == [(0, 8), (11, 13)]


def test_a_clause_that_did_not_match_is_not_marked():
    report = make_report(
        recall={
            "queries": [
                {"label": "q", "passed": False, "clauses": [{"term": "Excel", "matched": False}]}
            ]
        }
    )
    assert marks_of(report) == []


# --- recommendations -------------------------------------------------------------------


def test_advice_marks_the_bullet_it_names():
    report = make_report(advice=[{"kind": "promote_bullet", "bullet_id": "b2", "values": {}}])
    assert [
        (m.element, m.start, m.end, m.section, m.key, m.strength) for m in marks_of(report)
    ] == [
        (
            "role:1:bullet:0",
            0,
            len("Automaticé informes mensuales"),
            RECOMMENDATIONS,
            "advice:0",
            STRONG,
        )
    ]


def test_advice_for_a_bullet_outside_the_file_marks_nothing():
    report = make_report(advice=[{"kind": "add_bullet", "bullet_id": "not-in-the-file"}])
    assert marks_of(report) == []


# --- the rendering invariant and the edges ---------------------------------------------


def test_no_two_marks_partly_overlap():
    elements = render_cv(DRAFT)
    marks = build_highlight_map(rich_report(), elements, ALIASES)
    for element in elements:
        spans = [(m.start, m.end) for m in marks if m.element == element.id]
        for index, (start, end) in enumerate(spans):
            assert 0 <= start < end <= len(element.text)
            for other_start, other_end in spans[index + 1 :]:
                same = (start, end) == (other_start, other_end)
                assert same or end <= other_start or other_end <= start


def test_the_map_is_deterministic():
    elements = render_cv(DRAFT)
    first = build_highlight_map(rich_report(), elements, ALIASES)
    assert first == build_highlight_map(rich_report(), elements, ALIASES)
    assert first  # the rich report does produce marks


def test_a_report_without_a_cv_or_a_score_yields_no_marks():
    assert build_highlight_map({}, render_cv(DRAFT), ALIASES) == []


def test_draft_is_current_reads_the_stored_digest():
    assert draft_is_current(make_report(), DRAFT) is True
    assert draft_is_current(make_report(), {**DRAFT, "headline": "Otra cosa"}) is False
    assert draft_is_current({"cv": {"draft_sha": "sha256:0000"}}, DRAFT) is False
    assert draft_is_current({}, DRAFT) is False
    # A header without a digest is accepted, exactly as `cv_context.cv_document` accepts it.
    assert draft_is_current({"cv": {"resume_id": "cv-1"}}, DRAFT) is True
