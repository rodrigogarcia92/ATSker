"""The F4.1 parse gate: deterministic geometry over `parse.pdf` output.

Findings carry structured details rather than prose, for two reasons: the UI
translates them through `i18n`, and the matched text of a contact block never
travels into a report, a log, or a model prompt (PRD 10).
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from src.normalize.text import fold
from src.parse.pdf import DocumentText, PageText

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


def _column_gap(page: PageText) -> float | None:
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
            return gap
    return None


def _heading_lines(page: PageText) -> list[str]:
    found: list[str] = []
    for raw_line in page.text.splitlines():
        line = raw_line.strip().strip(":.").strip()
        if not line or len(line) > MAX_HEADING_LENGTH:
            continue
        if fold(line) in _FOLDED_HEADINGS:
            found.append(fold(line))
    return found


def check_document(document: DocumentText) -> ParseReport:
    """Run every F4.1 check. Deterministic: same bytes in, same findings out."""
    findings: list[Finding] = []

    empty_pages = [page.number for page in document.pages if page.char_count == 0]
    if empty_pages:
        findings.append(Finding("no_extractable_text", "blocker", {"pages": empty_pages}))

    for page in document.pages:
        # Words split "renglón@ejemplo.com | ++00 111 222 333" into separate tokens, so the
        # email and phone patterns are matched against the band's joined text.
        header = " ".join(word.text for word in page.words if word.bbox[1] < MARGIN_PT)
        footer = " ".join(
            word.text for word in page.words if word.bbox[3] > page.height - MARGIN_PT
        )
        for band, text in (("header", header), ("footer", footer)):
            if not text.strip():
                continue
            kinds = [
                kind
                for kind, pattern in (("email", EMAIL), ("phone", PHONE))
                if pattern.search(text)
            ]
            if kinds:
                findings.append(
                    Finding(
                        "contact_in_margin",
                        "blocker",
                        {"page": page.number, "band": band, "kinds": kinds},
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
                        {"page": page.number, "words": len(inside), "tables": len(page.tables)},
                    )
                )

        if page.white_words:
            findings.append(
                Finding(
                    "invisible_text",
                    "blocker",
                    {"page": page.number, "words": len(page.white_words)},
                )
            )

        gap = _column_gap(page)
        if gap is not None:
            findings.append(
                Finding("multi_column", "warning", {"page": page.number, "gap_pt": round(gap, 1)})
            )

        bullets = [
            image
            for image in page.images
            if (image[3] - image[1]) <= BULLET_IMAGE_MAX_HEIGHT_PT and image[0] < page.width / 2
        ]
        if bullets:
            findings.append(
                Finding("image_bullets", "info", {"page": page.number, "count": len(bullets)})
            )

    if not any(_heading_lines(page) for page in document.pages):
        findings.append(Finding("unrecognised_headings", "warning", {"headings_found": 0}))

    text = document.text
    markers = [marker for marker in MOJIBAKE_MARKERS if marker in text]
    if markers:
        findings.append(
            Finding(
                "mojibake",
                "warning",
                {"markers": markers, "count": sum(text.count(m) for m in markers)},
            )
        )

    fonts = sorted({font for page in document.pages for font in page.unembedded_fonts})
    if fonts:
        findings.append(Finding("non_embedded_fonts", "info", {"fonts": fonts}))

    return ParseReport(findings=tuple(findings))
