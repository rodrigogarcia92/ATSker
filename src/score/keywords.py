"""Keyword context (weight 0.15): the posting's terms, as a recruiter would search.

The question is F5.5.3's: *would a recruiter's search find this CV?* The set is
`must_have` ∪ `nice_to_have` ∪ `raw_keywords` (F5.5.2) — a posting that names SQL
as a requirement is asking for the term whether or not it repeats it in a keyword
list. Each term is folded and resolved to its canonical where the vocabulary has
one, so two spellings of one skill are one keyword and the first occurrence is the
name the report shows.

K2 (rule of `w5`, PRD F5.5.3) keeps the terms a search would actually be typed
for: 1–4 meaningful words, function words excluded in either language. A term is
present when every one of its meaningful words appears in one unit of the file —
headline, summary, skills list, one bullet, one role, education or certification —
with no order or adjacency required: a search matches words. The score is present
÷ kept, equal weight; there is no IDF and no BM25, so a skill the CV names once
counts as much as one it repeats, and a long requirement sentence cannot inflate
the set.

The document is `documents.track_document` read in the posting's language
(F5.5.1), because that is how a real ATS reads: the keyword search runs over the
file, skills section included.

The machine screen stays literal (F5.5.1): aliases count (`PowerBI` and `Power BI`
are the same thing spelled differently) and equivalents never do (Tableau is not
Power BI). A real ATS keyword filter does not know that two tools do the same
job; a human does — so there is no family lookup here or anywhere in `search/`.

K1 — BM25 over the same set, normalised against a synthetic all-terms document —
is kept as `keyword_context_k1` for reports stored under `w4` and for
`scripts/keyword_replay.py`: a stored report keeps the number it was saved with.
"""

from collections import Counter
from collections.abc import Mapping, Sequence
from math import log

from src.jd import StructuredJD
from src.normalize.text import fold
from src.score.aggregate import SubScore
from src.score.title import FUNCTION_WORDS

# The rule a `w5` report records beside its weights version.
KEYWORD_RULE = "K2"

# K1's BM25 parameters, reported in its own sub-score detail.
K1 = 1.5
B = 0.75


def _terms_of(jd: StructuredJD, aliases: Mapping[str, str] | None) -> list[tuple[str, str]]:
    """`(label, key)` for every term the posting asks for (F5.5.2).

    De-duplicated by the resolved key rather than by the words: `PowerBI` in a
    requirement and `Power BI` in the keywords are one term, and the first
    occurrence is what the report names.
    """
    seen: set[str] = set()
    terms: list[tuple[str, str]] = []
    for value in [*jd.must_have, *jd.nice_to_have, *jd.raw_keywords]:
        cleaned = fold(value)
        if not cleaned:
            continue
        key = (aliases or {}).get(cleaned, cleaned)
        if key in seen:
            continue
        seen.add(key)
        terms.append((value, key))
    return terms


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


def keyword_context_k1(
    jd: StructuredJD,
    texts: Sequence[str],
    *,
    aliases: Mapping[str, str] | None = None,
) -> SubScore:
    """K1 (`w4`): share of the terms the JD asks for that the document evidences,
    IDF-weighted.

    `texts` is the whole document, one unit at a time, in the posting's language
    (F5.5.1). Aliases are expanded on both sides — the same thing spelled
    differently counts — and never through a family: equivalents do not count.

    The normaliser is the BM25 ceiling for this query: the same term, once, in a
    document of the corpus's average length, where saturation reaches its IDF. That
    is what PRD F4.4 calls the synthetic all-terms document, expressed as the value
    such a document would attain — so a résumé that reaches every keyword scores
    exactly 1.0 and a partial one is comparable across postings of different sizes.
    """
    terms = _terms_of(jd, aliases)
    documents = [_tokens(text, aliases) for text in texts if text and text.strip()]
    detail: dict[str, object] = {"k1": K1, "b": B, "documents": len(documents)}

    if not terms:
        detail["reason"] = "no_keywords_in_jd"
        return SubScore("keyword", 1.0, matched=[], missing=[], detail=detail)
    if not documents:
        detail["reason"] = "no_bullets"
        return SubScore(
            "keyword", 0.0, matched=[], missing=[label for label, _ in terms], detail=detail
        )

    average_length = sum(len(document) for document in documents) / len(documents)
    detail["average_document_length"] = round(average_length, 3)

    matched: list[str] = []
    missing: list[str] = []
    numerator = 0.0
    denominator = 0.0

    for original, keyword in terms:
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


def _meaningful(term: str, aliases: Mapping[str, str] | None) -> list[str]:
    """The words a recruiter's search would use: aliases expanded, function words out.

    Duplicates go too — a term that repeats a word is still searched by its words,
    and `all of` over the same token twice is the same test as once.
    """
    words: list[str] = []
    for token in _tokens(term, aliases):
        if token in FUNCTION_WORDS or token in words:
            continue
        words.append(token)
    return words


def keyword_context(
    jd: StructuredJD,
    texts: Sequence[str],
    *,
    aliases: Mapping[str, str] | None = None,
) -> SubScore:
    """K2 (`w5`): present ÷ kept terms, equal weight, one unit per match (F5.5.3).

    Kept terms are the posting's terms with 1–4 meaningful words — a requirement
    sentence is not something a recruiter types, and a word like *de* is not what
    the search matches on. A term is present when every one of its meaningful words
    appears in one unit of `texts`; words split across two bullets satisfy nothing,
    because the search matches a document, not a corpus. The long items are
    reported in `detail["dropped"]` and never shown on the page.

    No kept term is a posting with nothing searchable: 1.0 with
    `no_keywords_in_jd`, as K1 does, so a posting that asks for nothing never
    penalises a CV.
    """
    kept: list[tuple[str, list[str]]] = []
    dropped: list[str] = []
    for label, key in _terms_of(jd, aliases):
        words = _meaningful(key, aliases)
        if 1 <= len(words) <= 4:
            kept.append((label, words))
        else:
            dropped.append(label)
    documents = [_tokens(text, aliases) for text in texts if text and text.strip()]
    detail: dict[str, object] = {
        "rule": KEYWORD_RULE,
        "dropped": dropped,
        "terms": len(kept),
        "present": 0,
        "documents": len(documents),
    }

    if not kept:
        detail["reason"] = "no_keywords_in_jd"
        return SubScore("keyword", 1.0, matched=[], missing=[], detail=detail)
    if not documents:
        detail["reason"] = "no_bullets"
        return SubScore(
            "keyword", 0.0, matched=[], missing=[label for label, _ in kept], detail=detail
        )

    units = [set(tokens) for tokens in documents]
    matched: list[str] = []
    missing: list[str] = []
    for label, words in kept:
        wanted = set(words)
        (matched if any(wanted <= unit for unit in units) else missing).append(label)
    detail["present"] = len(matched)
    return SubScore(
        "keyword",
        round(len(matched) / len(kept), 4),
        matched=matched,
        missing=missing,
        detail=detail,
    )
