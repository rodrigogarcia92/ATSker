"""The CV pane's render data (§12.7).

`src.highlights` says which words of the pane each report item rests on; this module is
the web layer's view of it. An HTML `<mark>` cannot nest, so one `<mark>` per distinct
span carries every key and section (S3a's contract), and the pane prints the element's
text with those spans cut into plain and marked segments. It also counts the marks per
report section — the phone's "Ver en mi CV (N)" links and the legend read them — and says
whether the offsets still describe the stored draft (decision 5: a CV edited after the
analysis is drawn without marks).

Each segment also carries its `key@section` pairs (§12.7's `data-key`), which is what the
page's script matches a mark against a report item with: one span can carry two sections,
so the pair — not the two lists — is what says which mark belongs to which section.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from src.highlights import (
    COMPONENTS,
    RECOMMENDATIONS,
    RECRUITER,
    REQUIREMENTS,
    WEAK,
    Mark,
    build_highlight_map,
    draft_is_current,
    render_cv,
)

# §12.1's order of the blocks that cite the CV pane; the legend's default and the phone's
# links follow it.
SECTION_ORDER = (COMPONENTS, RECRUITER, REQUIREMENTS, RECOMMENDATIONS)


@dataclass(frozen=True)
class Segment:
    """A run of an element's text: plain, or the span of one `<mark>`."""

    text: str
    marked: bool
    weak: bool
    keys: tuple[str, ...]
    sections: tuple[str, ...]
    # `key@section`, in the order the marks were resolved: the page's `data-key`, and the
    # same string a report item carries.
    pairs: tuple[str, ...]


@dataclass(frozen=True)
class ElementView:
    id: str
    kind: str
    text: str
    segments: tuple[Segment, ...]


@dataclass(frozen=True)
class _Span:
    start: int
    end: int
    keys: tuple[str, ...]
    sections: tuple[str, ...]
    pairs: tuple[str, ...]
    weak: bool


def pane_view(
    report: Mapping[str, object], draft: Mapping[str, object], aliases: Mapping[str, str]
) -> dict:
    """Everything the CV pane and the phone's links need, from the stored report alone.

    `elements` keeps every element `render_cv` produced (an empty-text bullet is skipped
    when printed but stays in the coordinate frame, S3a's note). `current` is
    `draft_is_current`: without it the pane renders with no marks at all. `counts` is the
    number of highlighted spans per section, `total` across all of them, and
    `default_section` the first section §12.1's order that has any (for the legend, until
    S3c tracks the one on screen).
    """
    elements = render_cv(draft)
    current = draft_is_current(report, draft)
    marks = build_highlight_map(report, elements, aliases) if current else []
    by_element: dict[str, list[Mark]] = {}
    for mark in marks:
        by_element.setdefault(mark.element, []).append(mark)

    # Counts are distinct keys per section — the items a section cites, not the spans their
    # marks were cut into: one cited bullet is one mark even when the resolver split it.
    keys: dict[str, set[str]] = {name: set() for name in SECTION_ORDER}
    for mark in marks:
        if mark.section in keys:
            keys[mark.section].add(mark.key)

    views: list[ElementView] = []
    total = 0
    for element in elements:
        spans = _spans(by_element.get(element.id, ()))
        total += len(spans)
        views.append(
            ElementView(
                element.id,
                element.kind,
                element.text,
                _segments(element.text, spans),
            )
        )

    return {
        "counts": {name: len(found) for name, found in keys.items()},
        "elements": tuple(views),
        "current": current,
        "total": total,
        "default_section": next(
            (name for name in SECTION_ORDER if keys[name]), COMPONENTS
        ),
    }


def _spans(marks: Sequence[Mark]) -> list[_Span]:
    """The marks on one element, merged so each span carries every key and section.

    S3a guarantees disjoint-or-identical spans per element, so grouping by `(start, end)`
    yields spans that neither overlap nor split. A span is *weak* only when every mark on
    it is: one strong mark is enough for the fill, and the underline is what marks the
    weaker evidence.
    """
    grouped: dict[tuple[int, int], list[Mark]] = {}
    for mark in marks:
        grouped.setdefault((mark.start, mark.end), []).append(mark)
    spans: list[_Span] = []
    for (start, end), group in sorted(grouped.items()):
        keys: list[str] = []
        sections: list[str] = []
        pairs: list[str] = []
        for mark in group:
            if mark.key not in keys:
                keys.append(mark.key)
            if mark.section not in sections:
                sections.append(mark.section)
            pair = f"{mark.key}@{mark.section}"
            if pair not in pairs:
                pairs.append(pair)
        spans.append(
            _Span(
                start,
                end,
                tuple(keys),
                tuple(sections),
                tuple(pairs),
                all(mark.strength == WEAK for mark in group),
            )
        )
    return spans


def _segments(text: str, spans: Sequence[_Span]) -> tuple[Segment, ...]:
    """`text` cut into plain runs and marked spans, in order."""
    segments: list[Segment] = []
    cursor = 0
    for span in spans:
        start = max(0, min(span.start, len(text)))
        end = max(start, min(span.end, len(text)))
        if start > cursor:
            segments.append(Segment(text[cursor:start], False, False, (), (), ()))
        if end > start:
            segments.append(
                Segment(text[start:end], True, span.weak, span.keys, span.sections, span.pairs)
            )
        cursor = max(cursor, end)
    if cursor < len(text):
        segments.append(Segment(text[cursor:], False, False, (), (), ()))
    return tuple(segments)
