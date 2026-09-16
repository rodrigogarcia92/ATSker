"""The F4.1 gate against PDFs built to fail.

Fixtures are generated rather than committed as binaries: a generator is readable,
diffable, and cannot smuggle anyone's real résumé into git (PRD 10).

Note that the check details carry counts and page numbers, never the matched text:
a contact block must not be echoed into a finding.
"""

from pathlib import Path

import pytest
from PIL import Image
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from src.parse.gate import BLOCKER_CAP, WARNING_CAP, check_document
from src.parse.pdf import read_pdf

WIDTH, HEIGHT = letter


def _draw_lines(
    pdf: canvas.Canvas, lines: list[tuple[float, float, str]], font: str = "Helvetica"
) -> None:
    pdf.setFont(font, 10)
    pdf.setFillColorRGB(0, 0, 0)
    for x, y, text in lines:
        pdf.drawString(x, y, text)


def build(tmp_path: Path, name: str, draw) -> Path:
    path = tmp_path / f"{name}.pdf"
    pdf = canvas.Canvas(str(path), pagesize=letter)
    draw(pdf)
    pdf.showPage()
    pdf.save()
    return path


def clean_body(pdf: canvas.Canvas) -> None:
    _draw_lines(
        pdf,
        [
            (60, HEIGHT - 80, "Experience"),
            (60, HEIGHT - 100, "Analista de datos, Banco Demo, 2022-2025"),
        ],
    )
    y = HEIGHT - 130
    for index in range(28):
        _draw_lines(pdf, [(60, y, f"Reduje el tiempo de cierre un {index + 1}% con Python y SQL")])
        y -= 20


def test_a_clean_single_column_document_passes(tmp_path):
    document = read_pdf(build(tmp_path, "clean", clean_body))

    report = check_document(document)

    assert report.blockers == ()
    assert report.warnings == ()
    assert report.cap is None


def test_a_page_with_no_text_is_a_blocker(tmp_path):
    document = read_pdf(build(tmp_path, "empty", lambda pdf: None))

    report = check_document(document)

    assert [finding.check for finding in report.blockers] == ["no_extractable_text"]
    assert report.cap == BLOCKER_CAP


def test_contact_details_in_the_header_are_a_blocker(tmp_path):
    def draw(pdf: canvas.Canvas) -> None:
        clean_body(pdf)
        _draw_lines(pdf, [(60, HEIGHT - 20, "persona@example.com | ++00 111 222 333")])

    report = check_document(read_pdf(build(tmp_path, "header", draw)))

    finding = next(f for f in report.blockers if f.check == "contact_in_margin")
    assert finding.detail["band"] == "header"
    assert finding.detail["kinds"] == ["email", "phone"]
    assert "persona@example.com" not in str(finding.detail)


def test_contact_details_in_the_footer_are_a_blocker(tmp_path):
    def draw(pdf: canvas.Canvas) -> None:
        clean_body(pdf)
        _draw_lines(pdf, [(60, 20, "persona@example.com")])

    finding = next(
        f
        for f in check_document(read_pdf(build(tmp_path, "footer", draw))).blockers
        if f.check == "contact_in_margin"
    )

    assert finding.detail["band"] == "footer"


def test_text_inside_a_drawn_table_is_a_blocker(tmp_path):
    def draw(pdf: canvas.Canvas) -> None:
        pdf.setFont("Helvetica", 10)
        pdf.drawString(60, HEIGHT - 80, "Experience")
        left, right, top, bottom = 60, 400, HEIGHT - 120, HEIGHT - 200
        pdf.rect(left, bottom, right - left, top - bottom, stroke=1, fill=0)
        pdf.line(left, (top + bottom) / 2, right, (top + bottom) / 2)
        pdf.line((left + right) / 2, top, (left + right) / 2, bottom)
        pdf.drawString(left + 10, top - 20, "Python")

    report = check_document(read_pdf(build(tmp_path, "table", draw)))

    assert "text_in_table" in [finding.check for finding in report.blockers]


def test_white_text_is_a_blocker_even_though_it_extracts(tmp_path):
    hidden = "python sql machine learning kubernetes terraform"

    def draw(pdf: canvas.Canvas) -> None:
        clean_body(pdf)
        # Drawn directly: the line helper resets the fill colour, which is the point here.
        pdf.setFillColorRGB(1, 1, 1)
        pdf.setFont("Helvetica", 10)
        pdf.drawString(60, HEIGHT - 300, hidden)

    report = check_document(read_pdf(build(tmp_path, "invisible", draw)))

    finding = next(f for f in report.blockers if f.check == "invisible_text")
    assert finding.detail["words"] > 0
    assert hidden not in str(finding.detail)


def test_a_two_column_body_warns_but_does_not_block(tmp_path):
    def draw(pdf: canvas.Canvas) -> None:
        pdf.setFont("Helvetica", 10)
        pdf.drawString(60, HEIGHT - 80, "Experience")
        y = HEIGHT - 110
        while y > 80:
            pdf.drawString(60, y, "Automaticé el reporte mensual con Python")
            pdf.drawString(340, y, "Mantuve tableros de Power BI para 40 usuarios")
            y -= 18

    report = check_document(read_pdf(build(tmp_path, "columns", draw)))

    assert [finding.check for finding in report.warnings] == ["multi_column"]
    assert report.blockers == ()
    assert report.cap == WARNING_CAP


def test_missing_section_headings_warn(tmp_path):
    def draw(pdf: canvas.Canvas) -> None:
        _draw_lines(
            pdf,
            [(60, HEIGHT - 80, "Analista de datos, Banco Demo, 2022-2025")]
            + [(60, HEIGHT - 120 - index * 20, f"Viñeta número {index}") for index in range(20)],
        )

    report = check_document(read_pdf(build(tmp_path, "noheadings", draw)))

    assert "unrecognised_headings" in [finding.check for finding in report.warnings]


def test_mojibake_warns(tmp_path):
    def draw(pdf: canvas.Canvas) -> None:
        clean_body(pdf)
        _draw_lines(pdf, [(60, HEIGHT - 260, "Ã©xito con el cliente")])

    report = check_document(read_pdf(build(tmp_path, "mojibake", draw)))

    finding = next(f for f in report.warnings if f.check == "mojibake")
    assert "Ã" in finding.detail["markers"]


def test_image_bullets_and_unembedded_fonts_are_information_only(tmp_path):
    icon = tmp_path / "bullet.png"
    Image.new("RGB", (6, 6), (0, 0, 0)).save(icon)

    def draw(pdf: canvas.Canvas) -> None:
        clean_body(pdf)
        pdf.drawImage(str(icon), 40, HEIGHT - 300, width=6, height=6)

    report = check_document(read_pdf(build(tmp_path, "bullets", draw)))

    checks = [finding.check for finding in report.infos]
    assert "image_bullets" in checks
    assert "non_embedded_fonts" in checks
    assert report.blockers == () and report.warnings == ()
    assert report.cap is None, "info findings must not cap the score"


def test_gate_arithmetic_caps_blockers_at_40_and_warnings_at_85(tmp_path):
    from src.parse.gate import Finding, ParseReport, apply_gate

    blocker = ParseReport(findings=(Finding("no_extractable_text", "blocker", {}),))
    warning = ParseReport(findings=(Finding("mojibake", "warning", {}),))
    both = ParseReport(
        findings=(Finding("mojibake", "warning", {}), Finding("invisible_text", "blocker", {}))
    )
    clean = ParseReport()

    assert apply_gate(92, blocker) == 40
    assert apply_gate(92, warning) == 85
    assert apply_gate(92, both) == 40
    assert apply_gate(92, clean) == 92
    assert apply_gate(30, both) == 30, "the cap lowers a score, it never raises one"


def test_two_runs_of_the_same_bytes_produce_the_same_findings(tmp_path):
    path = build(tmp_path, "stable", clean_body)

    first = check_document(read_pdf(path)).to_dict()
    second = check_document(read_pdf(path)).to_dict()

    assert first == second


@pytest.mark.parametrize("severity", ["blocker", "warning"])
def test_report_dict_exposes_the_cap_reason(tmp_path, severity):
    from src.parse.gate import Finding, ParseReport

    report = ParseReport(findings=(Finding("mojibake", severity, {}),))

    assert report.to_dict()["cap_reason"] == "mojibake"
