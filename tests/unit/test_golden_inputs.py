"""The golden-set inputs (queue A.2, amended by resume §1–2).

Synthetic sheets, mappings and CV files only: the real sheet and the operator's
mapping hold personal data and no test reads them. Validation problems name the
sheet's keys and pair ids — never a mapped email or path.
"""


import pytest

from scripts import golden_inputs as inputs
from src.auth.accounts import create_account
from tests.golden_support import row, write_map, write_sheet

PASSWORD = "correct horse battery staple"  # noqa: S105 - synthetic fixture password
KNOWN_EMAIL = "persona2@example.com"
UNKNOWN_EMAIL = "cleo@example.com"


def test_every_problem_is_reported_at_once(session, tmp_path):
    """A.2: unmapped profile, unmapped CV, missing file and unknown user in one pass."""
    create_account(session, KNOWN_EMAIL, PASSWORD, "Ana")
    session.commit()
    sheet = write_sheet(
        tmp_path / "sheet.xlsx",
        [
            row(1, profile="Ana", cv_version="CV-1"),
            row(2, profile="Bea", cv_version="CV-2"),
            row(3, profile="Cleo", cv_version="CV-1"),
            row(4, profile="Ana", cv_version=""),
        ],
    )
    mapping = inputs.load_mapping(
        write_map(
            tmp_path / "map.toml",
            profiles={"Ana": KNOWN_EMAIL, "Cleo": UNKNOWN_EMAIL},
            cvs={"CV-1": str(tmp_path / "does-not-exist.pdf")},
        )
    )
    pairs = inputs.read_pairs(sheet, include_test=False)

    check = inputs.check_inputs(pairs, mapping, session)

    joined = "\n".join(check.problems)
    assert "profile 'Bea' has no entry in [profiles]" in joined
    assert "cv_version 'CV-2' has no entry in [cvs]" in joined
    assert "cv_version 'CV-1': the mapped CV file does not exist" in joined
    assert "profile 'Cleo': no user with the mapped email" in joined
    assert "blank cv_version in rows: 4" in joined
    assert not check.ok
    for secret in (KNOWN_EMAIL, UNKNOWN_EMAIL, str(tmp_path / "does-not-exist.pdf")):
        assert secret not in joined, "problems must never print mapping values"


def test_a_test_only_profile_needs_no_mapping_without_include_test(session, tmp_path):
    """Resume §2: without --include-test the test-only profile is not even read."""
    create_account(session, KNOWN_EMAIL, PASSWORD, "Ana")
    session.commit()
    cv = tmp_path / "cv.pdf"
    cv.write_bytes(b"%PDF- synthetic")
    sheet = write_sheet(
        tmp_path / "sheet.xlsx",
        [
            row(1, profile="Ana", cv_version="CV-1"),
            row(2, profile="Persona Demo 3", cv_version="CV-9", split="test"),
            row(3, profile="Persona Demo 3", cv_version="CV-9", split="test"),
        ],
    )
    mapping = inputs.load_mapping(
        write_map(tmp_path / "map.toml", profiles={"Ana": KNOWN_EMAIL}, cvs={"CV-1": str(cv)})
    )

    dev_only = inputs.read_pairs(sheet, include_test=False)
    assert [pair.pair_id for pair in dev_only] == ["1"]
    assert inputs.check_inputs(dev_only, mapping, session).ok

    with_test = inputs.read_pairs(sheet, include_test=True)
    problems = inputs.check_inputs(with_test, mapping, session).problems
    joined = "\n".join(problems)
    assert "profile 'Persona Demo 3' has no entry in [profiles]" in joined
    assert "cv_version 'CV-9' has no entry in [cvs]" in joined


def test_blank_cv_version_lists_the_pair_ids_in_one_error(session, tmp_path):
    """Resume §2: one validation error naming every affected pair_id."""
    create_account(session, KNOWN_EMAIL, PASSWORD, "Ana")
    session.commit()
    cv = tmp_path / "cv.pdf"
    cv.write_bytes(b"%PDF- synthetic")
    sheet = write_sheet(
        tmp_path / "sheet.xlsx",
        [
            row("3", cv_version=""),
            row("5", cv_version="CV-1"),
            row("7", cv_version="  "),
        ],
    )
    mapping = inputs.load_mapping(
        write_map(tmp_path / "map.toml", profiles={"Ana": KNOWN_EMAIL}, cvs={"CV-1": str(cv)})
    )

    problems = inputs.check_inputs(
        inputs.read_pairs(sheet, include_test=False), mapping, session
    ).problems

    assert problems == ("blank cv_version in rows: 3, 7",)


def test_mapping_entries_no_in_scope_row_uses_are_ignored(session, tmp_path):
    """Resume §2: unused entries are not checked against the database or the disk."""
    create_account(session, KNOWN_EMAIL, PASSWORD, "Ana")
    session.commit()
    cv = tmp_path / "cv.pdf"
    cv.write_bytes(b"%PDF- synthetic")
    sheet = write_sheet(tmp_path / "sheet.xlsx", [row(1)])
    mapping = inputs.load_mapping(
        write_map(
            tmp_path / "map.toml",
            profiles={"Ana": KNOWN_EMAIL, "Ghost": "ghost@example.com"},
            cvs={"CV-1": str(cv), "Ghost CV": str(tmp_path / "ghost.pdf")},
        )
    )

    assert inputs.check_inputs(
        inputs.read_pairs(sheet, include_test=False), mapping, session
    ).ok


def test_columns_are_found_by_header_name_not_position(tmp_path):
    """Resume §1: the sheet has more columns than the runner uses, in the operator's order."""
    columns = (
        "bucket",
        "pair_id",
        "rater",
        "JD",
        "profile",
        "score_direct_only",
        "score",
        "lang",
        "split",
        "cv_version",
        "outcome",
    )
    sheet = write_sheet(
        tmp_path / "sheet.xlsx",
        [
            {
                "pair_id": 7,
                "JD": "a posting",
                "bucket": "strong",
                "score": 4.25,
                "score_direct_only": 3.0,
                "profile": "Ana",
                "lang": "en",
                "split": "dev",
                "cv_version": "CV v2",
                "rater": "rater_v2",
                "outcome": "interview",
            }
        ],
        columns=columns,
    )

    (pair,) = inputs.read_pairs(sheet, include_test=False)

    assert pair.pair_id == "7", "a numeric pair_id is read as text"
    assert pair.jd == "a posting"
    assert pair.bucket == "strong"
    assert pair.score == 4.25
    assert pair.score_direct_only == 3.0
    assert pair.profile == "Ana"
    assert pair.lang == "en"
    assert pair.split == "dev"
    assert pair.cv_version == "CV v2"


def test_missing_columns_are_named_together(tmp_path):
    sheet = write_sheet(
        tmp_path / "sheet.xlsx",
        [row(1)],
        columns=("pair_id", "JD", "bucket", "score", "profile", "split"),
    )

    with pytest.raises(inputs.SheetError) as failure:
        inputs.read_pairs(sheet, include_test=False)

    message = str(failure.value)
    assert "score_direct_only" in message
    assert "lang" in message
    assert "cv_version" in message


def test_a_missing_sheet_is_an_error(tmp_path):
    with pytest.raises(inputs.SheetError, match="sheet not found"):
        inputs.read_pairs(tmp_path / "nope.xlsx", include_test=False)


def test_a_missing_or_malformed_mapping_is_an_error_that_quotes_nothing(tmp_path):
    with pytest.raises(inputs.MappingFileError, match="mapping file not found"):
        inputs.load_mapping(tmp_path / "nope.toml")

    broken = tmp_path / "broken.toml"
    broken.write_text('[profiles]\n"Ana" = "SECRET-VALUE\n', encoding="utf-8")

    with pytest.raises(inputs.MappingFileError, match="not valid TOML") as failure:
        inputs.load_mapping(broken)

    assert "SECRET-VALUE" not in str(failure.value)
