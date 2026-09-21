"""A stored gate report, translated for a panel (PRD F5.1).

The upload screen and the report page show the same findings, so the translation
lives here rather than in either route: a finding is a count, a page number and a
class, and it reads the same on both screens. Nothing in here touches the document's
text — a detail sentence names pages, bands and counts (decision 9).
"""

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from src.i18n import t
from src.parse.gate import glyph_group

# Which stored checks carry a page number on a PDF; without one the finding came
# from a DOCX and its detail sentence has no page to name.
PAGE_CHECKS = {
    "contact_in_margin",
    "text_in_table",
    "invisible_text",
    "invisible_glyphs",
    "multi_column",
    "mojibake",
}


def document_kind(filename: str) -> str:
    return Path(filename).suffix.lower().lstrip(".")


def finding_detail(check: str, detail: Mapping[str, Any], lang: str, severity: str = "") -> str:
    """One finding's detail sentence. Page numbers, bands and counts only — never text."""
    variant = ""
    if check == "no_extractable_text":
        variant = "" if detail.get("pages") else "_docx"
    elif check == "multi_column":
        variant = "" if "gap_pt" in detail else "_docx"
    elif check == "invisible_glyphs":
        # The sentence says why it did not cap (info) or why it did (warning), and a
        # Word file has no page to name.
        variant = ("_warning" if severity == "warning" else "") + (
            "_docx" if detail.get("page") is None else ""
        )
    elif check in PAGE_CHECKS and detail.get("page") is None:
        variant = "_docx"
    fonts = [str(font) for font in detail.get("fonts", [])]
    first_pages = detail.get("first_pages") or {}
    gutter = list(detail.get("gutter") or [])
    categories = {str(key): int(value) for key, value in (detail.get("categories") or {}).items()}
    group = glyph_group(categories)
    values: dict[str, Any] = {
        "page": detail.get("page") if detail.get("page") is not None else "",
        "pages": ", ".join(str(value) for value in detail.get("pages", []))
        or t("common.none", lang),
        "band": t(f"gate.band.{detail.get('band', 'header')}", lang),
        "kinds": ", ".join(t(f"gate.kind.{kind}", lang) for kind in detail.get("kinds", [])),
        "words": detail.get("words", 0),
        "cells": detail.get("cells", 0),
        "tables": detail.get("tables", 0),
        "runs": detail.get("runs", 0),
        "white_runs": detail.get("white_runs", 0),
        "hidden_runs": detail.get("hidden_runs", 0),
        "chars": detail.get("chars", 0),
        # A class name in parentheses, or nothing when the glyphs disagree on one.
        "group": f"({t(f'gate.glyph_group.{group}', lang)})" if group else "",
        "gap_pt": detail.get("gap_pt", 0),
        "gutter_start": gutter[0] if len(gutter) == 2 else "",
        "gutter_end": gutter[1] if len(gutter) == 2 else "",
        "height_percent": round(float(detail.get("height_fraction") or 0) * 100),
        "columns": detail.get("columns", 0),
        "count": detail.get("count", 0),
        "markers": ", ".join(str(marker) for marker in detail.get("markers", [])),
        "fonts": ", ".join(
            f"{font} (p. {first_pages[font]})" if font in first_pages else font for font in fonts
        ),
    }
    return t(f"gate.detail.{check}{variant}", lang, **values)


def finding_rows(gate: Mapping[str, Any], lang: str) -> list[dict[str, str]]:
    """A stored gate report, translated for the template."""
    rows: list[dict[str, str]] = []
    for finding in gate.get("findings", []):
        check = str(finding.get("check"))
        detail = finding.get("detail") or {}
        severity = str(finding.get("severity"))
        rows.append(
            {
                "check": check,
                "severity": severity,
                "label": t(f"gate.check.{check}", lang),
                "severity_label": t(f"gate.severity.{severity}", lang),
                "detail": finding_detail(check, detail, lang, severity),
            }
        )
    return rows