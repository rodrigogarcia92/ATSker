"""The report's alert and advice sentences, built from the stored report (F4.2, F6.1, F7.2).

A stored report keeps the numbers and the ISO codes; the words are the reader's
language, so the sentence is built when the page renders, never when the analysis
ran. Two consumers: the report template, and the tests that pin the wording of a
list of one, two and three items and of each advice rule — which is why these are
functions and not template blocks.
"""

from collections.abc import Mapping

from src.i18n import t
from src.i18n.strings import STRINGS, join_list


def language_alert(alert: Mapping[str, object], lang: str) -> str:
    """The F4.2 sentence: which parts fell back to the other language, in order.

    The parts are joined by the language's conjunction (`join_list`): two read
    "1 de tus 1 bullets y tu titular", three "… bullets, tu titular y tu resumen".
    A report stored before F4.2 gained role titles has no `fallback_titles`, and
    reads exactly as it did.
    """
    parts: list[str] = []
    if alert.get("fallback_bullets"):
        parts.append(
            t(
                "report.alert.language_bullets",
                lang,
                n=alert.get("fallback_bullets"),
                m=alert.get("bullets"),
            )
        )
    if alert.get("fallback_titles"):
        parts.append(t("report.alert.language_titles", lang))
    if alert.get("fallback_headline"):
        parts.append(t("report.alert.language_headline", lang))
    if alert.get("fallback_summary"):
        parts.append(t("report.alert.language_summary", lang))
    if not parts:
        # A stored report whose alert carries no counts at all — an artefact rather
        # than a state this code writes. The sentence still has to read.
        parts.append(t("report.alert.language_bullets", lang, n=0, m=alert.get("bullets")))
    posting = str(alert.get("posting") or "")
    other = str(alert.get("other") or "")
    return t(
        "report.alert.language_mismatch",
        lang,
        items=join_list(parts, lang),
        posting=t(f"lang.{posting}", lang),
        other=t(f"lang.{other}", lang),
    )


def _points(value: object) -> str:
    """A remainder figure with at most one decimal and no trailing `.0`."""
    return f"{round(float(value or 0), 1):g}"


def _join_clauses(parts: list[str], lang: str) -> str:
    if len(parts) == 1:
        return parts[0]
    return ", ".join(parts[:-1]) + t("report.ceiling.and", lang) + parts[-1]


def ceiling_remainder(ceiling: Mapping[str, object], lang: str) -> str | None:
    """The ceiling's remainder as a sentence (PRD F10.2, A5).

    Built from `unreachable.by_source`, so each part names what actually holds those
    points out. Only non-zero parts are shown, and the "requieren experiencia" clause
    appears only when a requirement has no evidence at all.
    """
    source = ceiling.get("unreachable") or {}
    if not isinstance(source, Mapping):
        return None
    by = source.get("by_source") or {}
    requirements = source.get("requirements") or []
    by = by if isinstance(by, Mapping) else {}
    clauses: list[str] = []
    if by.get("no_evidence") and requirements:
        names = ", ".join(
            str(row.get("requirement") or "") for row in requirements if isinstance(row, Mapping)
        )
        clauses.append(
            t(
                "report.ceiling.no_evidence",
                lang,
                points=_points(by["no_evidence"]),
                requirements=names,
            )
        )
    tail = [
        t(key, lang, points=_points(by[field]))
        for field, key in (
            ("experience", "report.ceiling.experience"),
            ("title", "report.ceiling.title"),
            ("keywords", "report.ceiling.keywords"),
        )
        if by.get(field)
    ]
    if tail:
        clauses.append(_join_clauses(tail, lang))
    if by.get("stronger_evidence"):
        clauses.append(
            t(
                "report.ceiling.stronger_evidence",
                lang,
                points=_points(by["stronger_evidence"]),
            )
        )
    if not clauses:
        return None
    intro = t("report.ceiling.remaining", lang, points=_points(source.get("points")))
    return f"{intro} {'; '.join(clauses)}."


def advice_line(item: Mapping[str, object], lang: str, *, for_file: bool = False) -> str:
    """One F7.2 item as a sentence (PRD F7.2).

    The stored item names a language by its code — a report written under one
    interface language must read in the other — so the code is resolved here, with
    the words a reader knows ("inglés", "English"), never the ISO string.

    `for_file` picks the F10.3 wording for a document ("en tu documento") where the
    rule's sentence would otherwise speak of a track. A kind without a variant reads
    the base sentence, so the two cannot drift apart in silence.
    """
    values = dict(item.get("values") or {})
    code = values.get("language")
    if isinstance(code, str):
        values["language"] = t(f"lang.{code}", lang)
    kind = item.get("kind")
    key = f"report.advice.{kind}"
    if for_file and f"report.advice.file.{kind}" in STRINGS:
        key = f"report.advice.file.{kind}"
    return t(key, lang, **values)
