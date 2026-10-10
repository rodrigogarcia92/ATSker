"""Ingest documents: the DOCX path and the loader (PRD F2.1/F2.2).

Fixtures are generated with python-docx for the same reason the adversarial PDFs
are generated: a binary fixture cannot be reviewed and could smuggle a real résumé
into git. Every finding carries counts, never the text it matched.
"""

from io import BytesIO

import pytest
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import RGBColor

from src.ingest.documents import (
    UnreadableDocument,
    UnsupportedDocument,
    load_document,
    normalize_document_text,
)
from src.parse.docx import read_docx
from src.parse.gate import BLOCKER_CAP, WARNING_CAP, check_docx

CLEAN_LINES = (
    "Experiencia",
    "Analista de datos, Banco Demo 1, 2022-2025",
    "Reduje el tiempo de cierre un 30% con Python y SQL",
    "Formación",
    "Bachiller en Ingeniería de Sistemas",
)


def build(*paragraphs: str) -> bytes:
    document = Document()
    for text in paragraphs:
        document.add_paragraph(text)
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def report_for(*paragraphs: str):
    return check_docx(read_docx(BytesIO(build(*paragraphs))))


def test_a_clean_document_produces_no_findings():
    report = report_for(*CLEAN_LINES)

    assert report.blockers == ()
    assert report.warnings == ()
    assert report.cap is None


def test_a_document_without_text_is_a_blocker():
    report = report_for()

    assert [finding.check for finding in report.blockers] == ["no_extractable_text"]
    assert report.cap == BLOCKER_CAP


def test_contact_details_in_a_header_are_a_blocker():
    document = Document()
    document.add_paragraph("Experiencia")
    document.sections[0].header.paragraphs[0].text = "persona2@example.com | +00 111 222 333"
    buffer = BytesIO()
    document.save(buffer)

    report = check_docx(read_docx(BytesIO(buffer.getvalue())))

    finding = next(f for f in report.blockers if f.check == "contact_in_margin")
    assert finding.detail["band"] == "header"
    assert finding.detail["kinds"] == ["email", "phone"]
    assert "persona2@example.com" not in str(finding.detail)


def test_text_inside_a_table_is_a_blocker():
    document = Document()
    document.add_paragraph("Experiencia")
    table = document.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "Python"
    table.cell(0, 1).text = "SQL"
    buffer = BytesIO()
    document.save(buffer)

    report = check_docx(read_docx(BytesIO(buffer.getvalue())))

    finding = next(f for f in report.blockers if f.check == "text_in_table")
    assert finding.detail == {"tables": 1, "cells": 2}
    assert finding.detail.get("cells") is not None


@pytest.mark.parametrize("hidden", [False, True])
def test_white_and_hidden_runs_are_invisible_text(hidden: bool):
    document = Document()
    document.add_paragraph("Experiencia")
    run = document.add_paragraph().add_run("python sql machine learning")
    if hidden:
        run.font.hidden = True
    else:
        run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
    buffer = BytesIO()
    document.save(buffer)

    report = check_docx(read_docx(BytesIO(buffer.getvalue())))

    finding = next(f for f in report.blockers if f.check == "invisible_text")
    assert finding.detail["runs"] == 1


def test_declared_columns_warn_but_do_not_block():
    document = Document()
    document.add_paragraph("Experiencia")
    section = document.sections[0]
    cols = section._sectPr.find(qn("w:cols"))
    if cols is None:
        cols = OxmlElement("w:cols")
        section._sectPr.append(cols)
    cols.set(qn("w:num"), "2")
    buffer = BytesIO()
    document.save(buffer)

    report = check_docx(read_docx(BytesIO(buffer.getvalue())))

    finding = next(f for f in report.warnings if f.check == "multi_column")
    assert finding.detail["columns"] == 2
    assert report.cap == WARNING_CAP


def test_missing_section_headings_warn():
    report = report_for("Analista de datos, Banco Demo 1", "Reduje el cierre un 30%")

    assert "unrecognised_headings" in [finding.check for finding in report.warnings]


def test_mojibake_warns():
    report = report_for(*CLEAN_LINES, "Ã©xito con el cliente")

    finding = next(f for f in report.warnings if f.check == "mojibake")
    assert "Ã" in finding.detail["markers"]


def test_load_document_reads_a_docx_into_lines():
    loaded = load_document("cv.docx", build(*CLEAN_LINES))

    assert loaded.kind == "docx"
    assert "Analista de datos, Banco Demo 1" in loaded.text
    assert loaded.gate.blockers == ()


def test_load_document_refuses_other_formats_by_name():
    with pytest.raises(UnsupportedDocument):
        load_document("cv.txt", b"plain text")


def test_load_document_names_unreadable_bytes():
    with pytest.raises(UnreadableDocument):
        load_document("cv.docx", b"not really a zip file")


def test_normalize_document_text_keeps_lines_and_collapses_spaces():
    text = "Experiencia\r\n  Analista   de\u00a0datos \n\n  Reduje 30%  \r\n"

    assert normalize_document_text(text) == "Experiencia\nAnalista de datos\nReduje 30%"

def test_an_inert_white_run_is_a_glyph_finding_and_not_a_blocker():
    """F5.1.2 on the DOCX side: a builder's separator is not hidden content."""
    document = Document()
    document.add_paragraph("Experiencia")
    run = document.add_paragraph().add_run("·")
    run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
    buffer = BytesIO()
    document.save(buffer)

    report = check_docx(read_docx(BytesIO(buffer.getvalue())))

    finding = next(f for f in report.findings if f.check == "invisible_glyphs")
    assert finding.severity == "info"
    assert finding.detail["runs"] == 1
    assert finding.detail["white_runs"] == 1 and finding.detail["hidden_runs"] == 0
    assert finding.detail["chars"] == 1
    assert report.cap is None


def test_a_hidden_word_and_a_white_separator_are_reported_apart():
    """A `w:vanish` run and a white run are different fixes, so they are counted apart."""
    document = Document()
    document.add_paragraph("Experiencia")
    word = document.add_paragraph().add_run("kubernetes")
    word.font.hidden = True
    separator = document.add_paragraph().add_run("—")
    separator.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
    buffer = BytesIO()
    document.save(buffer)

    report = check_docx(read_docx(BytesIO(buffer.getvalue())))

    finding = next(f for f in report.blockers if f.check == "invisible_text")
    assert finding.detail == {"runs": 1, "white_runs": 0, "hidden_runs": 1}
    assert "invisible_glyphs" not in [f.check for f in report.findings]
    assert report.cap == BLOCKER_CAP
