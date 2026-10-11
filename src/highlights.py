"""The highlight map (§12.7): which words of the CV pane each report item rests on.

The pane shows the stored draft as text, and every report item that cites the CV — a
matched keyword, a title word, a relevant role, a requirement's evidence, a search
clause, an advice bullet — points at a span of that text. This module builds those
spans from the stored report alone: deterministic, no model call, no network, no
database, and no import from `web`.

`render_cv` is the one function that produces the pane's text: its elements are both
what the template prints and the coordinate system every offset is measured in. The
matching is scoring's own — `search.boolean`'s alias groups and `normalize.text`'s
term pattern, longest alias first with spans consumed — so a mark and a matched term
cannot disagree. The one difference is the fold: scoring folds a whole unit, while a
mark must say where in the *original* text a folded match landed (§6.8), so
`_fold_spans` folds character by character and keeps the map.

Sections are the report's own blocks (§12.1): `components` (the four sub-score cards),
`recruiter`, `requirements`, `recommendations`. A mark's `section` is what the pane's
`data-active` lights; its `key` is what a report item shares with its marks.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from src.cv_context import draft_digest
from src.normalize.text import fold, term_pattern
from src.search.boolean import alias_groups

# §12.1's report blocks that cite the CV pane. `components` is the four sub-score
# cards: Palabras clave, Título, Experiencia, Habilidades.
COMPONENTS = "components"
RECRUITER = "recruiter"
REQUIREMENTS = "requirements"
RECOMMENDATIONS = "recommendations"

# The two tones §12.7 draws: a fill, or a dashed underline for weaker evidence.
STRONG = "strong"
WEAK = "weak"

# The bases that count as the requirement's own evidence rather than a transfer to it.
DIRECT = "direct"


@dataclass(frozen=True)
class Element:
    """One piece of the CV pane: the text the pane prints and the offsets' frame.

    `id` is stable across renders (`headline`, `summary`, `role:0`,
    `role:0:bullet:2`, `skills`, `education:0`, …), so a mark names it and the template
    anchors to it.
    """

    id: str
    kind: str  # headline | summary | role | bullet | skills | education | certification
    text: str


@dataclass(frozen=True)
class Mark:
    """One highlighted span: `[start, end)` of `element`'s text, and why.

    `section` is the report block that lights it, `key` the item it belongs to (the
    report renders the same key), `strength` the tone. Two marks may cover the same
    span with different keys — an HTML `<mark>` cannot nest, so the renderer draws one
    mark per distinct span and carries every key on it.
    """

    element: str
    start: int
    end: int
    section: str
    key: str
    strength: str


def render_cv(draft: Mapping[str, object]) -> list[Element]:
    """The stored draft as the pane's text, in the file's order (§12.7).

    Headline, summary, roles and their bullets, skills, education, certifications —
    the pane's own order, which is not `documents.track_document`'s (that one is the
    reader's). Every draft bullet gets an element even when its text is empty: the
    report's snapshots carry a file-wide `ordinal` over *every* bullet, so a mark
    finds a cited bullet through the same count only if nothing is skipped here.
    """
    elements: list[Element] = []
    headline = _text(draft.get("headline"))
    if headline:
        elements.append(Element("headline", "headline", headline))
    summary = _text(draft.get("summary"))
    if summary:
        elements.append(Element("summary", "summary", summary))
    for role_index, role in enumerate(_rows(draft.get("roles"))):
        elements.append(Element(f"role:{role_index}", "role", _role_header(role)))
        for bullet_index, bullet in enumerate(_rows(role.get("bullets"))):
            elements.append(
                Element(
                    f"role:{role_index}:bullet:{bullet_index}",
                    "bullet",
                    _text(bullet.get("text")),
                )
            )
    skills = [name for name in (_text(value) for value in _strings(draft.get("skills"))) if name]
    if skills:
        elements.append(Element("skills", "skills", ", ".join(skills)))
    for index, entry in enumerate(_rows(draft.get("educations"))):
        text = _joined(entry, ("institution", "award", "field"))
        if text:
            elements.append(Element(f"education:{index}", "education", text))
    for index, entry in enumerate(_rows(draft.get("certifications"))):
        text = _joined(entry, ("name", "issuer"))
        if text:
            elements.append(Element(f"certification:{index}", "certification", text))
    return elements


def draft_is_current(report: Mapping[str, object], draft: Mapping[str, object]) -> bool:
    """Whether the pane's offsets still describe the stored draft (decision 5).

    False when the report is not a CV analysis, or when the draft stored beside it has
    changed since it was scored: the caller then renders the CV without marks rather
    than drawing stale offsets over new text. A report whose header carries no digest
    is accepted, exactly as `cv_context.cv_document` accepts it.
    """
    header = report.get("cv")
    if not isinstance(header, Mapping):
        return False
    stored = _text(header.get("draft_sha"))
    return not (stored and draft_digest(draft) != stored)


def build_highlight_map(
    report: Mapping[str, object],
    elements: Sequence[Element],
    aliases: Mapping[str, str],
) -> list[Mark]:
    """Every mark the stored report implies, split and merged so the pane can render it.

    `report` is the stored analysis (its `score`, `grades`, `bullets`, `recall`,
    `advice` and `role_matching`), `elements` is `render_cv`'s list, and `aliases` is
    the vocabulary's alias→canonical map — the same one scoring reads.
    """
    groups = alias_groups(dict(aliases))
    order = {element.id: index for index, element in enumerate(elements)}
    raw: list[Mark] = [
        *_keyword_marks(report, elements, aliases, groups),
        *_title_marks(report, elements),
        *_role_marks(report, elements),
        *_requirement_marks(report, elements, aliases, groups),
        *_clause_marks(report, elements, aliases, groups),
        *_advice_marks(report, elements),
    ]
    return _resolve_overlaps(raw, order)


def _keyword_marks(
    report: Mapping[str, object],
    elements: Sequence[Element],
    aliases: Mapping[str, str],
    groups: Mapping[str, tuple[str, ...]],
) -> list[Mark]:
    """Each matched keyword's span, wherever the CV writes it (§12.7's components row)."""
    terms = _strings(_dig(report, "score", "sub_scores", "keywords").get("matched"))
    if not terms:
        return []
    marks: list[Mark] = []
    for element in elements:
        for start, end, term in _alias_spans(element.text, terms, aliases, groups):
            marks.append(Mark(element.id, start, end, COMPONENTS, f"keyword:{term}", STRONG))
    return marks


def _title_marks(report: Mapping[str, object], elements: Sequence[Element]) -> list[Mark]:
    """The matched words, in the headline and the role titles only (§12.7's Title row)."""
    tokens = _strings(_dig(report, "score", "sub_scores", "title").get("matched"))
    if not tokens:
        return []
    marks: list[Mark] = []
    for element in elements:
        if element.kind not in ("headline", "role"):
            continue
        for start, end, _ in _alias_spans(element.text, tokens, {}, {}):
            marks.append(Mark(element.id, start, end, COMPONENTS, "title", STRONG))
    return marks


def _role_marks(report: Mapping[str, object], elements: Sequence[Element]) -> list[Mark]:
    """The relevant roles' headers (§12.7's Experience row).

    The Experience detail names roles by their master id, which the draft does not
    carry; `role_matching` is what ties a file role to that id, and a file-only role
    (matched by nothing) is paired by position — both lists follow the file's order.
    A half-weighted role rests on a transfer, so its header is weaker evidence.
    """
    detail = _dig(report, "score", "sub_scores", "experience", "detail")
    relevant = _rows(detail.get("relevant_roles"))
    roles = [element for element in elements if element.kind == "role"]
    if not relevant or not roles:
        return []
    matching = _rows(report.get("role_matching"))
    index_of: dict[str, int] = {}
    matched_ids: set[str] = set()
    for index, row in enumerate(matching):
        matched = _text(row.get("matched_role_id"))
        if matched:
            index_of[matched] = index
            matched_ids.add(matched)
    file_only = [
        index for index, row in enumerate(matching) if not _text(row.get("matched_role_id"))
    ]
    unmatched = [
        value
        for value in (_text(entry.get("id")) for entry in relevant)
        if value and value not in matched_ids
    ]
    for slot, role_id in enumerate(unmatched):
        if slot < len(file_only):
            index_of[role_id] = file_only[slot]
    marks: list[Mark] = []
    for entry in relevant:
        role_id = _text(entry.get("id"))
        index = index_of.get(role_id)
        if index is None or index >= len(roles):
            continue
        weight = _number(entry.get("weight"), 1.0)
        strength = WEAK if weight < 1.0 else STRONG
        element = roles[index]
        marks.append(
            Mark(element.id, 0, len(element.text), COMPONENTS, f"role:{role_id}", strength)
        )
    return marks


def _requirement_marks(
    report: Mapping[str, object],
    elements: Sequence[Element],
    aliases: Mapping[str, str],
    groups: Mapping[str, tuple[str, ...]],
) -> list[Mark]:
    """Per requirement: its cited evidence, and the requirement's term inside it.

    The evidence is a bullet (found through the snapshot's file-wide `ordinal`), the
    summary or the skills list; the whole cited element is marked, and the requirement's
    own term within it too when the CV writes it. A level-1 or non-direct grade is
    weaker evidence (§12.7's Requisitos y evidencia row).
    """
    by_kind = {element.kind: element for element in elements}
    bullets = [element for element in elements if element.kind == "bullet"]
    ordinals = _ordinals(report)
    marks: list[Mark] = []
    for index, grade in enumerate(_rows(report.get("grades"))):
        source = _text(grade.get("source")) or "bullet"
        element: Element | None = None
        if source == "summary":
            element = by_kind.get("summary")
        elif source == "skills_list":
            element = by_kind.get("skills")
        else:
            ordinal = ordinals.get(_text(grade.get("bullet_id")))
            if ordinal is not None and 0 <= ordinal < len(bullets):
                element = bullets[ordinal]
        if element is None:
            continue
        key = f"requirement:{index}"
        strength = _strength(grade)
        marks.append(Mark(element.id, 0, len(element.text), REQUIREMENTS, key, strength))
        for start, end, _ in _alias_spans(
            element.text, [_text(grade.get("requirement"))], aliases, groups
        ):
            marks.append(Mark(element.id, start, end, REQUIREMENTS, key, strength))
    return marks


def _clause_marks(
    report: Mapping[str, object],
    elements: Sequence[Element],
    aliases: Mapping[str, str],
    groups: Mapping[str, tuple[str, ...]],
) -> list[Mark]:
    """Per query, the span that satisfied each passing clause (§12.7's recruiter row).

    The evaluator matched each term in a unit of the document; the pane may not carry
    that unit's text (a fallback to the other language, or a bullet the file rewrote),
    so the term is looked up in the pane's own text, in element order, and its span is
    consumed — the same "one phrase answers one clause" rule scoring applies (decision 6).
    """
    marks: list[Mark] = []
    for query in _rows(_dig(report, "recall").get("queries")):
        key = f"query:{_text(query.get('label'))}"
        consumed: dict[str, list[tuple[int, int]]] = {element.id: [] for element in elements}
        for clause in _rows(query.get("clauses")):
            if not clause.get("matched"):
                continue
            term = _text(clause.get("term"))
            if not term:
                continue
            hit = _first_match(elements, term, aliases, groups, consumed)
            if hit is None:
                continue
            element, start, end = hit
            marks.append(Mark(element.id, start, end, RECRUITER, key, STRONG))
    return marks


def _first_match(
    elements: Sequence[Element],
    term: str,
    aliases: Mapping[str, str],
    groups: Mapping[str, tuple[str, ...]],
    consumed: dict[str, list[tuple[int, int]]],
) -> tuple[Element, int, int] | None:
    """The first unconsumed occurrence of any alias of `term` (decision 6's rule).

    Longest alias first, then element order — `match_terms`' own walk — so a clause marks
    the same word scoring found. The span is consumed so the next clause cannot reuse it.
    """
    phrases = sorted(_phrases(term, aliases, groups), key=len, reverse=True)
    for phrase in phrases:
        if not phrase:
            continue
        pattern = term_pattern(phrase)
        for element in elements:
            folded, spans = _fold_spans(element.text)
            taken = consumed[element.id]
            for match in pattern.finditer(folded):
                start, end = spans[match.start()][0], spans[match.end() - 1][1]
                if any(start < taken_end and taken_start < end for taken_start, taken_end in taken):
                    continue
                taken.append((start, end))
                return element, start, end
    return None


def _advice_marks(report: Mapping[str, object], elements: Sequence[Element]) -> list[Mark]:
    """The bullets an advice item names (§12.7's Recomendaciones row).

    Only what the stored report keeps can be marked: the F7.5 keywords card is computed
    at view time and names bullets too, but nothing of it is in `report["advice"]`.
    """
    ordinals = _ordinals(report)
    bullets = [element for element in elements if element.kind == "bullet"]
    marks: list[Mark] = []
    for index, item in enumerate(_rows(report.get("advice"))):
        bullet_id = _text(item.get("bullet_id"))
        ordinal = ordinals.get(bullet_id)
        if not bullet_id or ordinal is None or not 0 <= ordinal < len(bullets):
            continue
        element = bullets[ordinal]
        marks.append(
            Mark(element.id, 0, len(element.text), RECOMMENDATIONS, f"advice:{index}", STRONG)
        )
    return marks


def _resolve_overlaps(marks: Sequence[Mark], order: Mapping[str, int]) -> list[Mark]:
    """Split and merge the marks so no two partly overlap (what the pane can render).

    Two marks over the same span are one span with two keys — an HTML `<mark>` cannot
    nest — so each element's marks are cut at their own boundaries and every piece keeps
    one mark per covering (section, key, strength); adjacent pieces with the same
    covering set merge back. The result is deterministic.
    """
    unique = sorted(set(marks), key=_sort_key(order))
    resolved: list[Mark] = []
    for element_id in dict.fromkeys(mark.element for mark in unique):
        group = [mark for mark in unique if mark.element == element_id]
        edges = sorted({mark.start for mark in group} | {mark.end for mark in group})
        runs: list[tuple[int, int, tuple[tuple[str, str, str], ...]]] = []
        for start, end in zip(edges, edges[1:], strict=False):
            covering = tuple(
                sorted(
                    {
                        (mark.section, mark.key, mark.strength)
                        for mark in group
                        if mark.start <= start and end <= mark.end
                    }
                )
            )
            if runs and runs[-1][2] == covering and runs[-1][1] == start:
                runs[-1] = (runs[-1][0], end, covering)
            else:
                runs.append((start, end, covering))
        for start, end, covering in runs:
            for section, key, strength in covering:
                resolved.append(Mark(element_id, start, end, section, key, strength))
    return sorted(resolved, key=_sort_key(order))


def _sort_key(order: Mapping[str, int]):
    def key(mark: Mark) -> tuple[int, int, int, str, str, str]:
        return (
            order.get(mark.element, len(order)),
            mark.start,
            mark.end,
            mark.section,
            mark.key,
            mark.strength,
        )

    return key


def _strength(grade: Mapping[str, object]) -> str:
    """§12.7's tone: level 1, or anything but the requirement's own direct evidence."""
    level = _integer(grade.get("level"))
    basis = _text(grade.get("basis"))
    return WEAK if level == 1 or basis != DIRECT else STRONG


def _alias_spans(
    text: str,
    terms: Sequence[str],
    aliases: Mapping[str, str],
    groups: Mapping[str, tuple[str, ...]],
    consumed: list[tuple[int, int]] | None = None,
) -> list[tuple[int, int, str]]:
    """Every non-overlapping alias occurrence in `text`, longest alias first.

    The same rule as `search.boolean.match_terms` (decision 6), reported as offsets in
    the original text: `machine learning` consumes its span so a later `learning` cannot
    answer twice. `consumed` is shared by the caller when one query's clauses must not
    reuse a span.
    """
    if not text or not terms:
        return []
    folded, spans = _fold_spans(text)
    taken = consumed if consumed is not None else []
    found: list[tuple[int, int, str]] = []
    candidates = sorted(
        ((alias, term) for term in terms for alias in _phrases(term, aliases, groups)),
        key=lambda pair: len(pair[0]),
        reverse=True,
    )
    for alias, term in candidates:
        if not alias:
            continue
        pattern = term_pattern(alias)
        for match in pattern.finditer(folded):
            start, end = spans[match.start()][0], spans[match.end() - 1][1]
            if any(start < taken_end and taken_start < end for taken_start, taken_end in taken):
                continue
            taken.append((start, end))
            found.append((start, end, term))
    return found


def _phrases(
    term: str, aliases: Mapping[str, str], groups: Mapping[str, tuple[str, ...]]
) -> tuple[str, ...]:
    """The phrases that count as this term: its vocabulary aliases when it has any."""
    key = fold(term)
    canonical = aliases.get(key)
    return groups.get(canonical, (key,)) if canonical else (key,)


def _fold_spans(text: str) -> tuple[str, list[tuple[int, int]]]:
    """`normalize.text.fold`'s output, plus the original span of each folded character.

    Marks are offsets into the pane's text, so the fold the matcher runs on must say
    where a match landed; `fold` alone cannot, because NFKD decomposition and
    whitespace collapsing both move characters. Whitespace runs collapse to one space
    and the ends are stripped, exactly as `fold` does.
    """
    pieces: list[str] = []
    spans: list[tuple[int, int]] = []
    for index, char in enumerate(text):
        decomposed = unicodedata.normalize("NFKD", char)
        kept = "".join(ch for ch in decomposed if not unicodedata.combining(ch)).lower()
        for piece in kept:
            pieces.append(piece)
            spans.append((index, index + 1))
    folded: list[str] = []
    mapped: list[tuple[int, int]] = []
    run: tuple[int, int] | None = None
    for piece, span in zip(pieces, spans, strict=True):
        if piece.isspace():
            run = (run[0], span[1]) if run is not None else span
            continue
        if run is not None:
            folded.append(" ")
            mapped.append(run)
            run = None
        folded.append(piece)
        mapped.append(span)
    return "".join(folded), mapped


def _role_header(role: Mapping[str, object]) -> str:
    """One role line: title and employer, with the dates the file carries."""
    parts = [part for part in (_text(role.get("title")), _text(role.get("employer"))) if part]
    header = " — ".join(parts)
    start, end = _text(role.get("start_date")), _text(role.get("end_date"))
    if not start and not end:
        return header
    dates = f"{start} – {end}" if start and end else (start or end)
    return f"{header} ({dates})" if header else dates


def _joined(entry: Mapping[str, object], keys: Sequence[str]) -> str:
    return " ".join(part for part in (_text(entry.get(key)) for key in keys) if part)


def _dig(source: Mapping[str, object], *keys: str) -> Mapping[str, object]:
    """The nested mapping at `keys`, or an empty one — a stored report may lack it."""
    node: object = source
    for key in keys:
        if not isinstance(node, Mapping):
            return {}
        node = node.get(key)
    return node if isinstance(node, Mapping) else {}


def _rows(value: object) -> list[Mapping[str, object]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [row for row in value if isinstance(row, Mapping)]


def _strings(value: object) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [item for item in value if isinstance(item, str)]


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _integer(value: object) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return 0


def _ordinals(report: Mapping[str, object]) -> dict[str, int]:
    """Snapshot id → the bullet's file-wide ordinal, for rows that carry one."""
    found: dict[str, int] = {}
    for row in _rows(report.get("bullets")):
        ordinal = _optional_int(row.get("ordinal"))
        if ordinal is not None:
            found[_text(row.get("id"))] = ordinal
    return found


def _optional_int(value: object) -> int | None:
    """An ordinal, or None when the report does not carry one (never a silent 0)."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _number(value: object, fallback: float) -> float:
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return fallback
