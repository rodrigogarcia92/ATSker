"""Reading a PDF into the geometry the gate reasons about.

Everything the gate needs is extracted once, here, so the checks themselves are
pure functions over dataclasses and can be tested without touching a file.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Any

import pdfplumber

BBox = tuple[float, float, float, float]  # x0, top, x1, bottom

# Colourspaces in which 1.0 — or CMYK 0,0,0,0 — is the white point. An ICC profile
# means whatever its profile says, and a /Separation or /DeviceN ink reports the
# *tint* of the ink here: without the space, a full tint of any ink, black included,
# reads as white. That misread was measured on 2026-09-20, so only these are trusted.
_WHITE_SPACES = frozenset({"DeviceGray", "DeviceRGB", "DeviceCMYK", "CalGray", "CalRGB"})


@dataclass(frozen=True)
class Word:
    text: str
    bbox: BBox
    fontname: str
    color: Any  # pdfplumber's non_stroking_color: float, RGB, CMYK or None
    space: str | None = None  # the colourspace the colour was resolved in


@dataclass(frozen=True)
class PageText:
    number: int
    width: float
    height: float
    words: list[Word]
    char_count: int
    text: str
    tables: list[BBox] = field(default_factory=list)
    images: list[BBox] = field(default_factory=list)
    fonts: list[str] = field(default_factory=list)
    unembedded_fonts: list[str] = field(default_factory=list)
    # F5.1.2: the gate has to read what the hidden glyphs say before it can judge
    # them, so the words travel in memory. They never reach a finding's detail.
    white_words: list[Word] = field(default_factory=list)


@dataclass(frozen=True)
class DocumentText:
    pages: list[PageText]

    @property
    def text(self) -> str:
        return "\n".join(page.text for page in self.pages)


def is_white(color: Any, space: str | None = None) -> bool:
    """True when the non-stroking colour is white.

    `space` is the colourspace name when the caller knows it — chars carry one. With
    a known space only `_WHITE_SPACES` are trusted; shaped objects carry no name, so
    there the value is all this can read and a spot ink at full tint stays ambiguous.
    """
    if space is not None and space not in _WHITE_SPACES:
        return False
    if color is None:
        return False
    if isinstance(color, (int, float)):
        return float(color) == 1.0
    if isinstance(color, (list, tuple)):
        values = [float(value) for value in color]
        if len(values) == 1:
            return values[0] == 1.0
        if len(values) == 3:
            return all(value == 1.0 for value in values)
        if len(values) == 4:
            return all(value == 0.0 for value in values)
    return False


def _font_name(raw: Any) -> str:
    return str(raw or "unknown").lstrip("/")


def _unembedded_fonts(page: Any) -> list[str]:
    """Fonts whose descriptor carries no FontFile — best effort, reported as `info` only.

    The base-14 fonts a Word export usually relies on have no FontDescriptor at all,
    which is exactly the non-embedded case; a resolved Type0 font reaches its
    descriptor through DescendantFonts.
    """
    names: list[str] = []
    try:
        resources = page.page_obj.resources
        fonts = resources.get("Font") if resources else None
        fonts = fonts.resolve() if hasattr(fonts, "resolve") else fonts
    except Exception:
        return names
    if not fonts:
        return names
    try:
        for raw in fonts.values():
            font = raw.resolve() if hasattr(raw, "resolve") else raw
            candidates = [font]
            descendants = font.get("DescendantFonts") if hasattr(font, "get") else None
            descendants = descendants.resolve() if hasattr(descendants, "resolve") else descendants
            if descendants:
                candidates.extend(
                    item.resolve() if hasattr(item, "resolve") else item for item in descendants
                )
            embedded = False
            for candidate in candidates:
                descriptor = candidate.get("FontDescriptor") if hasattr(candidate, "get") else None
                descriptor = descriptor.resolve() if hasattr(descriptor, "resolve") else descriptor
                if descriptor and any(
                    key in descriptor for key in ("FontFile", "FontFile2", "FontFile3")
                ):
                    embedded = True
                    break
            if not embedded:
                names.append(_font_name(font.get("BaseFont") if hasattr(font, "get") else None))
    except Exception:
        return []
    return sorted(set(names))


def _covers(outer: BBox, inner: BBox) -> bool:
    return (
        outer[0] <= inner[0]
        and outer[1] <= inner[1]
        and outer[2] >= inner[2]
        and outer[3] >= inner[3]
    )


def _invisible_white(word: Word, backgrounds: list[tuple[BBox, Any]]) -> bool:
    """A white glyph counts as invisible only where the background is white too.

    White text over a dark banner is perfectly readable; reporting it would cap a
    clean document at 40. A background made of an image cannot be read here, so a
    glyph over one is conservatively left out of the finding.
    """
    if not is_white(word.color, word.space):
        return False
    return all(not _covers(box, word.bbox) or is_white(color) for box, color in backgrounds)


def read_pdf(source: str | Path | IO[bytes]) -> DocumentText:
    """Word-level geometry for every page, plus the structures the checks need."""
    pages: list[PageText] = []
    with pdfplumber.open(source) as pdf:
        for number, page in enumerate(pdf.pages, start=1):
            words = [
                Word(
                    text=str(item["text"]),
                    bbox=(item["x0"], item["top"], item["x1"], item["bottom"]),
                    fontname=str(item.get("fontname") or ""),
                    color=item.get("non_stroking_color"),
                    space=item.get("ncs"),
                )
                for item in page.extract_words(
                    extra_attrs=["fontname", "non_stroking_color", "ncs"]
                )
            ]
            try:
                tables = [tuple(table.bbox) for table in page.find_tables()]
            except Exception:
                tables = []
            images = [
                (image["x0"], image["top"], image["x1"], image["bottom"]) for image in page.images
            ]
            # What can sit under a glyph: filled shapes and images. Their colours are
            # the only background signal a PDF text layer exposes; images report none.
            backgrounds: list[tuple[BBox, Any]] = [
                (
                    (shape["x0"], shape["top"], shape["x1"], shape["bottom"]),
                    shape.get("non_stroking_color"),
                )
                for shape in (*page.rects, *page.curves)
                if shape.get("fill")
            ]
            backgrounds += [
                ((image["x0"], image["top"], image["x1"], image["bottom"]), None)
                for image in page.images
            ]
            text = page.extract_text() or ""
            pages.append(
                PageText(
                    number=number,
                    width=float(page.width),
                    height=float(page.height),
                    words=words,
                    char_count=len(page.chars),
                    text=text,
                    tables=tables,
                    images=images,
                    fonts=sorted({word.fontname for word in words if word.fontname}),
                    unembedded_fonts=_unembedded_fonts(page),
                    white_words=[
                        word for word in words if _invisible_white(word, backgrounds)
                    ],
                )
            )
    return DocumentText(pages=pages)
