"""The reviewed draft: dates, skill constraint, and the certification split (F2.3).

Classification is deterministic first — the model only decides what no rule can —
and every ambiguous entry is flagged for the review screen rather than guessed at.
"""

from datetime import date

import pytest

from src.extract.resume import ExtractedCredential, ExtractedRole, ResumeExtraction
from src.ingest.draft import build_draft, classify_credential, parse_partial_date
from src.vocabulary import list_unmapped


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2021", date(2021, 1, 1)),
        ("2021-06", date(2021, 6, 1)),
        ("2021-06-15", date(2021, 6, 15)),
        (" 2019-12 ", date(2019, 12, 1)),
        ("junio 2021", None),
        ("2021-13", None),
        ("", None),
        (None, None),
    ],
)
def test_partial_dates_parse_or_refuse(raw, expected):
    """A date the parser cannot read is None — shown empty for the user, never guessed."""
    assert parse_partial_date(raw) == expected


def credential(**values) -> ExtractedCredential:
    return ExtractedCredential(**{"name": "Algo", "issuer": "Alguien", **values})


@pytest.mark.parametrize(
    ("entry", "kind", "review"),
    [
        # A credential id or url is a certification, whoever issued it.
        (
            credential(name="Data Analytics", issuer="Google", credential_url="https://x"),
            "certification",
            False,
        ),
        (
            credential(name="Data Analytics", issuer="Google", credential_id="ABC-123"),
            "certification",
            False,
        ),
        # A certificate word in the name wins over an academic issuer.
        (
            credential(
                name="Professional Certificate in Data Science",
                issuer="Universidad de Lima",
            ),
            "certification",
            False,
        ),
        # An issuer that is not academic is a certification.
        (credential(name="Scrum Master", issuer="Scrum Alliance"), "certification", False),
        # An academic issuer is education when no certification signal fires.
        (
            credential(
                name="Bachiller en Ingeniería de Sistemas",
                issuer="Universidad Nacional de Ingeniería",
            ),
            "education",
            False,
        ),
        # Nothing deterministic: the model's own kind decides and a human reviews it.
        (credential(name="Bachiller", issuer="", kind="education"), "education", True),
        (
            credential(name="Curso de liderazgo", issuer="", kind="certification"),
            "certification",
            True,
        ),
        (credential(name="Curso de liderazgo", issuer="", kind="unsure"), "education", True),
    ],
)
def test_certification_classification_is_deterministic_first(entry, kind, review):
    assert classify_credential(entry) == (kind, review)


def test_the_name_rule_beats_an_academic_issuer():
    """A university can issue a certificate; the words in the name decide."""
    entry = credential(name="Certificado de Especialización", issuer="Universidad de Lima")

    assert classify_credential(entry) == ("certification", False)


def test_build_draft_constrains_skills_and_logs_the_unknowns(session, vocabulary):
    extraction = ResumeExtraction(
        language="es",
        skills=["Python", "cobalto", "python", "machine learning"],
    )

    draft = build_draft(session, extraction)

    assert draft.skills == ["python", "machine learning"]
    assert [term.term for term in list_unmapped(session)] == ["cobalto"]


def test_bullet_chips_are_matched_from_the_bullet_text_itself(session, vocabulary):
    extraction = ResumeExtraction(
        roles=[
            ExtractedRole(
                employer="Acme",
                title="Analista",
                bullets=[
                    "Modelos de machine learning en producción",
                    "Informes con Python",
                ],
            )
        ]
    )

    draft = build_draft(session, extraction)

    bullets = draft.roles[0].bullets
    assert bullets[0].chips == ["machine learning"], "the longer alias consumes its span"
    assert bullets[1].chips == ["python"]


def test_build_draft_normalises_dates_and_drops_empty_roles(session):
    extraction = ResumeExtraction(
        language="en",
        roles=[
            ExtractedRole(
                employer="  Acme  ", title=" Analyst ", start_date="2021-03", end_date=""
            ),
            ExtractedRole(employer="", title="", bullets=["Suelta"]),
        ],
    )

    draft = build_draft(session, extraction)

    assert draft.language == "en"
    assert len(draft.roles) == 1
    role = draft.roles[0]
    assert (role.employer, role.title) == ("Acme", "Analyst")
    assert role.start_date == "2021-03-01"
    assert role.end_date is None


def test_build_draft_splits_credentials_and_keeps_the_review_flag(session):
    extraction = ResumeExtraction(
        credentials=[
            credential(name="Bachiller", issuer="Universidad Nacional", kind="education"),
            credential(name="Scrum Master", issuer="Scrum Alliance"),
            credential(name="Curso de liderazgo", issuer="", kind="unsure"),
        ]
    )

    draft = build_draft(session, extraction)

    assert [entry.institution for entry in draft.educations] == ["Universidad Nacional", ""]
    assert [entry.needs_review for entry in draft.educations] == [False, True]
    assert [entry.name for entry in draft.certifications] == ["Scrum Master"]
    assert draft.educations[1].award == "Curso de liderazgo"


def test_build_draft_drops_entries_without_a_name(session):
    extraction = ResumeExtraction(credentials=[credential(name="   ", issuer="Universidad X")])

    draft = build_draft(session, extraction)

    assert draft.educations == [] and draft.certifications == []