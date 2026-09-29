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
