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
    Element,
    Mark,
    build_highlight_map,
    draft_is_current,
    keyword_spans,
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
    report: Mapping[str, object],
    draft: Mapping[str, object],
    aliases: Mapping[str, str],
    jd_text: str = "",
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
        "jd": jd_view(report, jd_text, elements if current else (), aliases),
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


@dataclass(frozen=True)
class JdSegment:
    """A run of the posting's text: plain (`number` 0), or one keyword's occurrence.

    `context` says what the analysis found for the keyword, for the mark's tooltip: the CV line
    that carries a matched keyword, or nothing when it is missing (and for plain text).
    """

    text: str
    number: int
    matched: bool
    context: str = ""


def jd_view(
    report: Mapping[str, object],
    jd_text: str,
    elements: Sequence[Element],
    aliases: Mapping[str, str],
) -> dict:
    """The JD view's data (§12.7): the posting cut into segments, each keyword marked.

    The keywords are the ones the score's keyword sub-score listed, matched first. Each one's
    occurrences in the posting are marked by the scoring matcher: a matched keyword as
    evidence (a fill), a missing one as a gap (a dashed underline). A matched keyword's
    `context` is the first CV line the same matcher finds it in, so its mark can say where
    it is; a missing one has no context.
    """
    score = report.get("score")
    sub_scores = score.get("sub_scores") if isinstance(score, Mapping) else None
    block = sub_scores.get("keywords") if isinstance(sub_scores, Mapping) else None
    matched = _terms(block, "matched")
    missing = _terms(block, "missing")
    listed = [(term, True) for term in matched] + [(term, False) for term in missing]
    if not listed:
        return {"segments": (), "matched": 0, "missing": 0}

    numbers = {term: index for index, (term, _) in enumerate(listed, start=1)}
    status = dict(listed)
    found = _evidence(matched, elements, aliases)
    spans = keyword_spans(jd_text, [term for term, _ in listed], aliases)
    segments: list[JdSegment] = []
    cursor = 0
    for start, end, term in sorted(spans):
        if start > cursor:
            segments.append(JdSegment(jd_text[cursor:start], 0, False))
        segments.append(
            JdSegment(
                jd_text[start:end], numbers[term], status[term], found.get(term, "")
            )
        )
        cursor = end
    if cursor < len(jd_text):
        segments.append(JdSegment(jd_text[cursor:], 0, False))
    return {
        "segments": tuple(segments),
        "matched": len(matched),
        "missing": len(missing),
    }


def _terms(block: object, key: str) -> list[str]:
    """The keyword labels under `key`, as the stored report holds them; anything else is none."""
    values = block.get(key) if isinstance(block, Mapping) else None
    if not isinstance(values, list):
        return []
    return [value for value in values if isinstance(value, str) and value]


def _evidence(
    terms: Sequence[str], elements: Sequence[Element], aliases: Mapping[str, str]
) -> dict[str, str]:
    """For each term, the first element's text that the matcher finds it in."""
    found: dict[str, str] = {}
    if not terms:
        return found
    for element in elements:
        for _, _, term in keyword_spans(element.text, terms, aliases):
            found.setdefault(term, element.text)
    return found
