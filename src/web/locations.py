"""Where a word-level finding sits, rendered from the archived original (PRD F5.1.1).

The stored finding keeps page numbers and bounding boxes and nothing else (decision 9),
so the only way to show the user which words a check flagged is to reopen the document
they uploaded and read it back **inside their own authenticated session**. Nothing here
writes a file, a row or a log line: the boxes are drawn in memory into a PNG, and the
characters of a hidden or mis-encoded word are read from the same bytes at request time
and rendered once.

`pdfplumber` owns both halves — `page.to_image()` rasterises the page, `within_bbox()`
reads the characters a box encloses — and its own dependencies carry the imaging, so no
new one is added.

Rasterising goes through PDFium (pypdfium2, under pdfplumber), which is **not
thread-safe**: the CV pane asks for page 1 and page 2 at the same time, FastAPI runs the
two handlers in its thread pool, and a concurrent load can fail with a spurious *Data
format error*. Every rasterisation therefore takes `_PDFIUM_LOCK`, and the PNG is kept in
a small per-process cache so a reload — or the pane's second page — is not rendered twice.
"""

import hashlib
import io
import threading
from collections import OrderedDict
from collections.abc import Mapping, Sequence
from typing import Any

import pdfplumber

from src.parse.gate import BOX_CHECKS, CHARACTER_CHECKS

# §12.1's severity palette, drawn as outlines and never fills: an outlined box marks
# the spot, and the tag on the panel carries the meaning.
SEVERITY_COLOURS: dict[str, tuple[int, int, int]] = {
    "blocker": (244, 114, 182),  # #f472b6
    "warning": (167, 139, 250),  # #a78bfa
    "info": (148, 163, 184),  # #94a3b8
}
DEFAULT_COLOUR = SEVERITY_COLOURS["info"]

# The page is rendered at 110 dpi: legible on a phone at a fraction of the original
# file's size, and cheap enough to build per request.
RESOLUTION = 110

# Stored boxes are rounded to 0.1pt (`gate._box`); `within_bbox` keeps only objects
# fully inside, so a hair of padding is what makes the box enclose its own glyph again.
BOX_PAD_PT = 1.0

# PDFium is one library in one process and its docs forbid calling it from two threads at
# once. This lock serialises the rasterisers; pdfminer-only work (`page_exists`,
# `page_count`'s page count, `box_characters`) never touches PDFium and does not take it.
_PDFIUM_LOCK = threading.Lock()

# The rendered pages, most recently used last. The key carries the file's digest — never
# the bytes — with the page, the resolution, the boxes' geometry and the colour, so a
# reload or the pane's second page does not rasterise again and two different views of one
# page never collide. The value is only the PNG: small, per process, capped.
PAGE_CACHE_SIZE = 32
_PAGE_CACHE: OrderedDict[tuple[Any, ...], bytes] = OrderedDict()
# Guards the cache's get/move/set/evict across FastAPI's worker threads — never the
# drawing: a slow page must not hold up a cache hit for another one.
_CACHE_LOCK = threading.Lock()


def finding_page(finding: Mapping[str, Any]) -> int | None:
    """The 1-based page a finding names, or None when the format has none (DOCX)."""
    detail = finding.get("detail") or {}
    page = detail.get("page")
    try:
        return int(page) if page is not None else None
    except (TypeError, ValueError):
        return None


def finding_boxes(finding: Mapping[str, Any]) -> list[tuple[float, float, float, float]]:
    """The bounding boxes the finding's detail carries, each as `(x0, top, x1, bottom)`."""
    detail = finding.get("detail") or {}
    boxes: list[tuple[float, float, float, float]] = []
    for box in detail.get("boxes") or []:
        try:
            x0, top, x1, bottom = (float(value) for value in box)
        except (TypeError, ValueError):
            continue
        if x1 > x0 and bottom > top:
            boxes.append((x0, top, x1, bottom))
    return boxes


def is_locatable(check: str) -> bool:
    """A finding of a check whose detail carries boxes on a PDF (F5.1.1's table)."""
    return check in BOX_CHECKS


def characters_apply(check: str) -> bool:
    """The three checks where seeing the characters is the only way to act (F5.1.1)."""
    return check in CHARACTER_CHECKS


def render_page_png(
    data: bytes,
    *,
    page_number: int,
    boxes: Sequence[tuple[float, float, float, float]],
    severity: str,
) -> bytes:
    """The finding's page with each box outlined, as PNG bytes.

    The first page is `page_number=1`. The page is rasterised in memory; the boxes are
    drawn as outlines in the severity's colour, never filled, so the flagged words stay
    readable underneath. A render identical to one already made is served from
    `_PAGE_CACHE`; everything else goes through `_draw_page`, which owns the PDFium lock.
    The cache's own lookup and store each take `_CACHE_LOCK`; the drawing happens with
    neither lock held, so a slow page never holds up a cache hit for another one. Two
    threads may therefore draw the same missing page at once: the second store overwrites
    the first with identical bytes.
    """
    key = (hashlib.sha256(data).hexdigest(), page_number, RESOLUTION, tuple(boxes), severity)
    with _CACHE_LOCK:
        cached = _PAGE_CACHE.get(key)
        if cached is not None:
            _PAGE_CACHE.move_to_end(key)
            return cached
    png = _draw_page(data, page_number=page_number, boxes=boxes, severity=severity)
    with _CACHE_LOCK:
        _PAGE_CACHE[key] = png
        while len(_PAGE_CACHE) > PAGE_CACHE_SIZE:
            _PAGE_CACHE.popitem(last=False)
    return png


def _draw_page(
    data: bytes,
    *,
    page_number: int,
    boxes: Sequence[tuple[float, float, float, float]],
    severity: str,
) -> bytes:
    """Rasterise one page, one at a time: the only place that calls PDFium."""
    colour = SEVERITY_COLOURS.get(severity, DEFAULT_COLOUR)
    with _PDFIUM_LOCK:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            page = pdf.pages[page_number - 1]
            image = page.to_image(resolution=RESOLUTION)
            width, height = float(page.width), float(page.height)
            for x0, top, x1, bottom in boxes:
                box = (
                    _clamp(x0, width),
                    _clamp(top, height),
                    _clamp(x1, width),
                    _clamp(bottom, height),
                )
                image.draw_rect(box, stroke=colour, stroke_width=2, fill=None)
            buffer = io.BytesIO()
            image.annotated.save(buffer, format="PNG")
    return buffer.getvalue()


def box_characters(
    data: bytes,
    *,
    page_number: int,
    boxes: Sequence[tuple[float, float, float, float]],
) -> list[str]:
    """The characters each box encloses, read from the original at request time.

    Returned in the same order as `boxes`, one string per box and an empty string when a
    box encloses nothing. This text is rendered and then dropped: it is never stored,
    logged or sent anywhere (decision 9).
    """
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        page = pdf.pages[page_number - 1]
        width, height = float(page.width), float(page.height)
        readings: list[str] = []
        for x0, top, x1, bottom in boxes:
            # The stored box was rounded to 0.1pt, which can shave a glyph's own box by
            # a hair and leave `within_bbox` — which keeps only fully-contained objects —
            # returning nothing. A one-point pad widens it back past the rounding without
            # reaching the next word.
            crop = (
                _clamp(x0 - BOX_PAD_PT, width),
                _clamp(top - BOX_PAD_PT, height),
                _clamp(x1 + BOX_PAD_PT, width),
                _clamp(bottom + BOX_PAD_PT, height),
            )
            try:
                chars = page.within_bbox(crop).chars
            except (ValueError, TypeError):  # pragma: no cover - a degenerate box
                readings.append("")
                continue
            readings.append("".join(str(char.get("text", "")) for char in chars).strip())
    return readings


def page_count(data: bytes) -> int:
    """How many pages the archived file has, 0 when it will not open (N6.6).

    The CV pane's Archivo original view reads this to list the original's pages; a file
    that is not a PDF (a DOCX, F11) has none, and one that will not open is treated the
    same rather than raising.
    """
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            return len(pdf.pages)
    except Exception:  # noqa: BLE001 - any parse failure means "no pages to show"
        return 0


def page_exists(data: bytes, page_number: int) -> bool:
    """Whether the archived file really has a page `page_number` (N6.6).

    A stored finding names a page; the file is the only authority on whether that page
    exists. A file that will not open is not a page either — the route answers 404
    rather than a 500.
    """
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            return 1 <= page_number <= len(pdf.pages)
    except Exception:  # noqa: BLE001 - any parse failure means "no such page here"
        return False


def _clamp(value: float, limit: float) -> float:
    return min(max(value, 0.0), limit)
