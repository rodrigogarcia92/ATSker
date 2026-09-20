"""The F4.1 parse gate: deterministic geometry over `parse.pdf` output.

Findings carry structured details rather than prose, for two reasons: the UI
translates them through `i18n`, and the matched text of a contact block never
travels into a report, a log, or a model prompt (PRD 10).
"""

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from src.normalize.text import fold
from src.parse.docx import DocxText
from src.parse.pdf import DocumentText, PageText, Word

Severity = Literal["blocker", "warning", "info"]

# Gate arithmetic (PRD F4.1): any blocker caps at 40, any warning caps at 85, and
# the uncapped score is always reported alongside.
BLOCKER_CAP = 40
WARNING_CAP = 85

MARGIN_PT = 50.0
COLUMN_GAP_PT = 40.0
COLUMN_HEIGHT_FRACTION = 0.60
BULLET_IMAGE_MAX_HEIGHT_PT = 20.0
MAX_HEADING_LENGTH = 60

EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE = re.compile(r"(?<!\w)(?:\+\d{1,3}[\s.-]?)?(?:\(\d{1,4}\)[\s.-]?)?\d[\d\s.-]{6,}\d(?!\w)")
MOJIBAKE_MARKERS = ("Ã", "â€", "\ufffd")

_HEADINGS: dict[str, list[str]] = json.loads(
    (Path(__file__).parent / "section_headings.json").read_text(encoding="utf-8")
)
_FOLDED_HEADINGS = {fold(heading) for headings in _HEADINGS.values() for heading in headings}


@dataclass(frozen=True)
class Finding:
    check: str
    severity: Severity
    detail: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ParseReport:
    findings: tuple[Finding, ...] = ()

    @property
    def blockers(self) -> tuple[Finding, ...]:
        return tuple(finding for finding in self.findings if finding.severity == "blocker")

    @property
    def warnings(self) -> tuple[Finding, ...]:
        return tuple(finding for finding in self.findings if finding.severity == "warning")

    @property
    def infos(self) -> tuple[Finding, ...]:
        return tuple(finding for finding in self.findings if finding.severity == "info")

    @property
    def cap(self) -> int | None:
        if self.blockers:
            return BLOCKER_CAP
        if self.warnings:
            return WARNING_CAP
        return None

    @property
    def cap_reason(self) -> str | None:
        if self.blockers:
            return self.blockers[0].check
        if self.warnings:
            return self.warnings[0].check
        return None

    def to_dict(self) -> dict[str, object]:
        return {
            "cap": self.cap,
            "cap_reason": self.cap_reason,
            "findings": [
                {"check": f.check, "severity": f.severity, "detail": f.detail}
                for f in self.findings
            ],
        }


def apply_gate(uncapped: int, report: ParseReport) -> int:
    cap = report.cap
    return uncapped if cap is None else min(uncapped, cap)


# The DOCX gate answers the subset of F5.1 that needs no page geometry (decision 36).
# The panel names the rest, so that "no findings" cannot read as a clean bill of
# health (F5.1.1).
_DOCX_NOT_RUN = ("image_bullets", "non_embedded_fonts")


def checks_not_run(kind: str) -> tuple[str, ...]:
    """The F5.1 checks this file format cannot honestly answer."""
    return _DOCX_NOT_RUN if kind == "docx" else ()


def _overlaps(
    word_box: tuple[float, float, float, float], box: tuple[float, float, float, float]
) -> bool:
    return not (
        word_box[2] <= box[0]
        or word_box[0] >= box[2]
        or word_box[3] <= box[1]
        or word_box[1] >= box[3]
    )


def _vertical_extent(words, page_height: float) -> float:
    """Share of the page height the text on one side of a gutter reaches across.

    Extent, not ink: a column of thirty lines covers most of the page even though the
    glyph boxes themselves add up to a fraction of it.
    """
    if not words or page_height <= 0:
        return 0.0
    top = min(word.bbox[1] for word in words)
    bottom = max(word.bbox[3] for word in words)
    return (bottom - top) / page_height


@dataclass(frozen=True)
class _Gutter:
    """Where the columns separate, and how far down the page they run (F5.1.1)."""

    gap_pt: float
    x_range: tuple[float, float]
    height_fraction: float


def _box(bbox: tuple[float, float, float, float]) -> list[float]:
    """A bounding box rounded for storage: a location, not a measurement."""
    return [round(float(value), 1) for value in bbox]


def _matched_words(words: list[Word], pattern: re.Pattern[str]) -> list[Word]:
    """The words a pattern's matches cover, against the band's joined text.

    Words split "renglón@ejemplo.com | ++00 111 222 333" into separate tokens, so the
    patterns run against the joined text and the offsets map each match back to the
    words that carry it.
    """
    parts: list[str] = []
    spans: list[tuple[int, int]] = []
    position = 0
    for word in words:
        if parts:
            position += 1  # the space the join inserts
        parts.append(word.text)
        spans.append((position, position + len(word.text)))
        position += len(word.text)
    text = " ".join(parts)

    found: set[int] = set()
    for match in pattern.finditer(text):
        for index, (start, end) in enumerate(spans):
            if start < match.end() and end > match.start():
                found.add(index)
    return [words[index] for index in sorted(found)]


def _column_gap(page: PageText) -> _Gutter | None:
    """Approximation of the bimodal x-midpoint histogram: an empty vertical gutter.

    The gutter must be at least 40pt wide and both sides must carry text over at
    least 60% of the page height, which is what distinguishes a two-column layout
    from a wide table or a right-aligned date column.
    """
    if len(page.words) < 20:
        return None
    spans = sorted((word.bbox[0], word.bbox[2]) for word in page.words)
    merged: list[list[float]] = []
    for start, end in spans:
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    for left, right in zip(merged, merged[1:], strict=False):
        gap = right[0] - left[1]
        if gap < COLUMN_GAP_PT:
            continue
        left_words = [word for word in page.words if word.bbox[2] <= left[1]]
        right_words = [word for word in page.words if word.bbox[0] >= right[0]]
        if (
            _vertical_extent(left_words, page.height) >= COLUMN_HEIGHT_FRACTION
            and _vertical_extent(right_words, page.height) >= COLUMN_HEIGHT_FRACTION
        ):
            both = [*left_words, *right_words]
            top = min(word.bbox[1] for word in both)
            bottom = max(word.bbox[3] for word in both)
            return _Gutter(
                gap_pt=round(gap, 1),
                x_range=(round(left[1], 1), round(right[0], 1)),
                height_fraction=round((bottom - top) / page.height, 2),
            )
    return None


def _heading_lines_from(lines: Iterable[str]) -> list[str]:
    found: list[str] = []
    for raw_line in lines:
        line = raw_line.strip().strip(":.").strip()
        if not line or len(line) > MAX_HEADING_LENGTH:
            continue
        if fold(line) in _FOLDED_HEADINGS:
            found.append(fold(line))
    return found


def _heading_lines(page: PageText) -> list[str]:
    return _heading_lines_from(page.text.splitlines())


def check_document(document: DocumentText) -> ParseReport:
    """Run every F4.1 check. Deterministic: same bytes in, same findings out."""
    findings: list[Finding] = []

    empty_pages = [page.number for page in document.pages if page.char_count == 0]
    if empty_pages:
        findings.append(Finding("no_extractable_text", "blocker", {"pages": empty_pages}))

    for page in document.pages:
        # Words split "renglón@ejemplo.com | ++00 111 222 333" into separate tokens, so
        # the patterns run against each band's joined text (F5.1.1 wants the boxes of
        # the words they matched, so the offsets map back to words).
        for band, band_words in (
            ("header", [word for word in page.words if word.bbox[1] < MARGIN_PT]),
            ("footer", [word for word in page.words if word.bbox[3] > page.height - MARGIN_PT]),
        ):
            kinds: list[str] = []
            matched: list[Word] = []
            for kind, pattern in (("email", EMAIL), ("phone", PHONE)):
                hits = _matched_words(band_words, pattern)
                if hits:
                    kinds.append(kind)
                    matched.extend(hits)
            if kinds:
                findings.append(
                    Finding(
                        "contact_in_margin",
                        "blocker",
                        {
                            "page": page.number,
                            "band": band,
                            "kinds": kinds,
                            "boxes": [
                                _box(bbox) for bbox in sorted({word.bbox for word in matched})
                            ],
                        },
                    )
                )

        if page.tables:
            inside = [
                word
                for word in page.words
                if any(_overlaps(word.bbox, table) for table in page.tables)
            ]
            if inside:
                findings.append(
                    Finding(
                        "text_in_table",
                        "blocker",
                        {
                            "page": page.number,
                            "words": len(inside),
                            "tables": len(page.tables),
                            "boxes": [_box(word.bbox) for word in inside],
                            "table_boxes": [_box(table) for table in page.tables],
                        },
                    )
                )

        if page.white_boxes:
            findings.append(
                Finding(
                    "invisible_text",
                    "blocker",
                    {
                        "page": page.number,
                        "words": len(page.white_boxes),
                        "boxes": [_box(bbox) for bbox in page.white_boxes],
                    },
                )
            )

        gutter = _column_gap(page)
        if gutter is not None:
            findings.append(
                Finding(
                    "multi_column",
                    "warning",
                    {
                        "page": page.number,
                        "gap_pt": gutter.gap_pt,
                        "gutter": list(gutter.x_range),
                        "height_fraction": gutter.height_fraction,
                    },
                )
            )

        bullets = [
            image
            for image in page.images
            if (image[3] - image[1]) <= BULLET_IMAGE_MAX_HEIGHT_PT and image[0] < page.width / 2
        ]
        if bullets:
            findings.append(
                Finding(
                    "image_bullets",
                    "info",
                    {
                        "page": page.number,
                        "count": len(bullets),
                        "boxes": [_box(bbox) for bbox in bullets],
                    },
                )
            )

    if not any(_heading_lines(page) for page in document.pages):
        findings.append(Finding("unrecognised_headings", "warning", {"headings_found": 0}))

    for page in document.pages:
        markers = [marker for marker in MOJIBAKE_MARKERS if marker in page.text]
        if not markers:
            continue
        boxes = [word.bbox for word in page.words if any(marker in word.text for marker in markers)]
        findings.append(
            Finding(
                "mojibake",
                "warning",
                {
                    "page": page.number,
                    "markers": markers,
                    "count": sum(page.text.count(marker) for marker in markers),
                    "boxes": [_box(bbox) for bbox in boxes],
                },
            )
        )

    first_page: dict[str, int] = {}
    for page in document.pages:
        for font in page.unembedded_fonts:
            first_page.setdefault(font, page.number)
    if first_page:
        findings.append(
            Finding(
                "non_embedded_fonts",
                "info",
                {"fonts": sorted(first_page), "first_pages": first_page},
            )
        )

    return ParseReport(findings=tuple(findings))


def check_docx(document: DocxText) -> ParseReport:
    """The F5.1 checks a Word file can honestly answer (`parse.docx` explains which).

    Same severities as the PDF path and the same gate arithmetic, so a .docx and a
    PDF carrying the same defect cap a score identically.
    """
    findings: list[Finding] = []

    if not document.text.strip():
        findings.append(Finding("no_extractable_text", "blocker", {}))

    for band, lines in (("header", document.headers), ("footer", document.footers)):
        text = " ".join(lines)
        if not text.strip():
            continue
        kinds = [
            kind
            for kind, pattern in (("email", EMAIL), ("phone", PHONE))
            if pattern.search(text)
        ]
        if kinds:
            findings.append(
                Finding("contact_in_margin", "blocker", {"band": band, "kinds": kinds})
            )

    populated = [table for table in document.tables if table]
    if populated:
        findings.append(
            Finding(
                "text_in_table",
                "blocker",
                {"tables": len(populated), "cells": sum(len(table) for table in populated)},
            )
        )

    invisible = [*document.white_runs, *document.hidden_runs]
    if invisible:
        findings.append(Finding("invisible_text", "blocker", {"runs": len(invisible)}))

    if document.columns > 1:
        findings.append(Finding("multi_column", "warning", {"columns": document.columns}))

    if not _heading_lines_from(document.text.splitlines()):
        findings.append(Finding("unrecognised_headings", "warning", {"headings_found": 0}))

    text = document.text
    markers = [marker for marker in MOJIBAKE_MARKERS if marker in text]
    if markers:
        findings.append(
            Finding(
                "mojibake",
                "warning",
                {"markers": markers, "count": sum(text.count(marker) for marker in markers)},
            )
        )

    return ParseReport(findings=tuple(findings))
