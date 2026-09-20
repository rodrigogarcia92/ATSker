"""Reading a DOCX into the text and structures the gate can check.

python-docx parses the same XML an ATS parses, so the checks here are exactly the
subset of F5.1 that exists without page geometry: an empty document, contact
details parked in headers or footers, text inside tables, runs painted white or
hidden with `w:vanish`, sections declared as multi-column, unrecognised headings
and mojibake.

The checks that need word bounding boxes — measuring a column gutter, spotting
image bullets, resolving embedded fonts — stay PDF-only: inventing a fake page
geometry for a format that has none would be a finding that means nothing.
"""

from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Any

from docx import Document
from docx.oxml.ns import qn
from docx.shared import RGBColor
from docx.table import Table
from docx.text.paragraph import Paragraph

WHITE = RGBColor(0xFF, 0xFF, 0xFF)


@dataclass(frozen=True)
class DocxText:
    """Body lines in document order (table rows inlined), plus what the gate reads.

    `body` carries table rows as ` | `-joined lines so the text handed to the model
    keeps the document's reading order; `tables` holds each table's non-empty cell
    texts for the check itself.
    """

    body: list[str] = field(default_factory=list)
    tables: list[list[str]] = field(default_factory=list)
    headers: list[str] = field(default_factory=list)
    footers: list[str] = field(default_factory=list)
    columns: int = 1
    white_runs: list[str] = field(default_factory=list)
    hidden_runs: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(
            line for line in [*self.body, *self.headers, *self.footers] if line.strip()
        )


def _iter_blocks(document: Any) -> Iterator[Paragraph | Table]:
    """Body paragraphs and tables in the order they were written."""
    for child in document.element.body.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, document)
        elif child.tag == qn("w:tbl"):
            yield Table(child, document)


def _note_colours(paragraph: Paragraph, *, white: list[str], hidden: list[str]) -> None:
    for run in paragraph.runs:
        text = run.text.strip()
        if not text:
            continue
        if run.font.color is not None and run.font.color.rgb == WHITE:
            white.append(text)
        if run.font.hidden:
            hidden.append(text)


def _section_columns(document: Any) -> int:
    """The widest column count any section declares; 1 when none does.

    A section may declare several `w:cols` elements (the default one plus the real
    declaration), so every one is read and the widest wins.
    """
    columns = 1
    for section in document.sections:
        for cols in section._sectPr.findall(qn("w:cols")):
            raw = cols.get(qn("w:num"))
            if raw and raw.isdigit():
                columns = max(columns, int(raw))
    return columns


def _margin_lines(document: Any, attribute: str) -> list[str]:
    """Unique paragraph texts of every section's header or footer, in order."""
    seen: list[str] = []
    for section in document.sections:
        container = getattr(section, attribute)
        for paragraph in container.paragraphs:
            text = paragraph.text.strip()
            if text and text not in seen:
                seen.append(text)
    return seen


def read_docx(source: str | Path | IO[bytes]) -> DocxText:
    """Text, tables and invisibility signals for a .docx file."""
    document = Document(source)
    body: list[str] = []
    tables: list[list[str]] = []
    white: list[str] = []
    hidden: list[str] = []

    for block in _iter_blocks(document):
        if isinstance(block, Table):
            cells: list[str] = []
            for row in block.rows:
                row_cells = [cell.text.strip() for cell in row.cells]
                cells.extend(row_cells)
                body.append(" | ".join(cell for cell in row_cells if cell))
                for cell in row.cells:
                    for paragraph in cell.paragraphs:
                        _note_colours(paragraph, white=white, hidden=hidden)
            tables.append([cell for cell in cells if cell])
        else:
            text = block.text.strip()
            if text:
                body.append(text)
            _note_colours(block, white=white, hidden=hidden)

    return DocxText(
        body=body,
        tables=tables,
        headers=_margin_lines(document, "header"),
        footers=_margin_lines(document, "footer"),
        columns=_section_columns(document),
        white_runs=white,
        hidden_runs=hidden,
    )