"""Keyword context (weight 0.15): BM25 over the JD's raw keywords against the document.

The document is `documents.track_document` read in the posting's language
(F5.5.1) — headline, summary, skills list, bullets, role titles, education and
certifications — because that is how a real ATS reads: the keyword search runs
over the file, skills section included.

The machine screen stays literal (F5.5.1): aliases count (`PowerBI` and `Power BI`
are the same thing spelled differently) and equivalents never do (Tableau is not
Power BI). A real ATS keyword filter does not know that two tools do the same
job; a human does — so there is no family lookup here or anywhere in `search/`.
Normalised against a synthetic document that contains every query term, so the
result is comparable between postings of different keyword counts. Standard BM25
parameters (k1=1.5, b=0.75) are used and reported in the sub-score detail rather
than left implicit.
"""

from collections import Counter
from collections.abc import Mapping, Sequence
from math import log

from src.jd import StructuredJD
from src.normalize.text import fold
from src.score.aggregate import SubScore

K1 = 1.5
B = 0.75


def _tokens(text: str, aliases: Mapping[str, str] | None) -> list[str]:
    tokens: list[str] = []
    for raw in fold(text).split():
        token = raw.strip(".,;:()[]{}|/")
        if not token:
            continue
        canonical = (aliases or {}).get(token)
        tokens.extend(canonical.split() if canonical else [token])
    return tokens


def _idf(document_frequency: int, total_documents: int) -> float:
    return log(1 + (total_documents - document_frequency + 0.5) / (document_frequency + 0.5))


def _term_score(
    term: str,
    document: Sequence[str],
    *,
    average_length: float,
    idf: float,
) -> float:
    if not document or average_length <= 0:
        return 0.0
    frequency = Counter(document)[term]
    if not frequency:
        return 0.0
    length_norm = K1 * (1 - B + B * len(document) / average_length)
    return idf * (frequency * (K1 + 1)) / (frequency + length_norm)


def keyword_context(
    jd: StructuredJD,
    texts: Sequence[str],
    *,
    aliases: Mapping[str, str] | None = None,
) -> SubScore:
    """Share of the JD's keywords the document evidences, IDF-weighted.

    `texts` is the whole document, one unit at a time, in the posting's language
    (F5.5.1). Aliases are expanded on both sides — the same thing spelled
    differently counts — and never through a family: equivalents do not count.

    The normaliser is the BM25 ceiling for this query: the same term, once, in a
    document of the corpus's average length, where saturation reaches its IDF. That
    is what PRD F4.4 calls the synthetic all-terms document, expressed as the value
    such a document would attain — so a résumé that reaches every keyword scores
    exactly 1.0 and a partial one is comparable across postings of different sizes.
    """
    keywords = [fold(keyword) for keyword in jd.raw_keywords if keyword.strip()]
    documents = [_tokens(text, aliases) for text in texts if text and text.strip()]
    detail: dict[str, object] = {"k1": K1, "b": B, "documents": len(documents)}

    if not keywords:
        detail["reason"] = "no_keywords_in_jd"
        return SubScore("keyword", 1.0, matched=[], missing=[], detail=detail)
    if not documents:
        detail["reason"] = "no_bullets"
        return SubScore("keyword", 0.0, matched=[], missing=list(jd.raw_keywords), detail=detail)

    average_length = sum(len(document) for document in documents) / len(documents)
    detail["average_document_length"] = round(average_length, 3)

    matched: list[str] = []
    missing: list[str] = []
    numerator = 0.0
    denominator = 0.0

    for original, keyword in zip(jd.raw_keywords, keywords, strict=True):
        keyword_score = 0.0
        for part in _tokens(keyword, aliases):
            document_frequency = sum(1 for document in documents if part in document)
            idf = _idf(document_frequency, len(documents))
            keyword_score += max(
                _term_score(part, document, average_length=average_length, idf=idf)
                for document in documents
            )
            denominator += idf
        numerator += keyword_score
        (matched if keyword_score > 0 else missing).append(original)

    value = 0.0 if denominator <= 0 else max(0.0, min(1.0, numerator / denominator))
    return SubScore(
        name="keyword",
        value=round(value, 4),
        matched=matched,
        missing=missing,
        detail=detail,
    )
