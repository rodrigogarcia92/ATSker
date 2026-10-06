"""The three validators every generated sentence must pass (PRD F7.3).

Generated text is the one place ATSker writes new words, so the rules that keep the
words true are enforced by code, never trusted to the prompt: every item cites a
stored source, every number and proper noun in the item exists in that source, and
every skill it names exists in the user's own data — and a summary's prose, unlike
its skills block, names only skills evidenced at level 2 or better on the track's bullets.

Pure: the vocabulary and the sources are handed in, so the rules are testable
without a provider or a database. `session` and `profile_id` are accepted because
the caller's sources were built owner-scoped (`profile_id` first, F1); the
validator never widens them.
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from src.normalize.text import fold, term_pattern
from src.normalize.vocabulary import ambiguous_aliases, match_text

PROVENANCE = "provenance"
LITERAL = "literal"
# Rule 3 reports two different failures, and the proposal page tells them apart.
# `CLOSURE` stays as the name of the group.
CLOSURE = "closure"
CLOSURE_MISSING = "closure_missing"
CLOSURE_UNEVIDENCED = "closure_unevidenced"
CLOSURE_RULES = (CLOSURE_MISSING, CLOSURE_UNEVIDENCED)

# A short function-word list, both languages: words that begin a sentence or a title
# without being a proper noun. Everything else capitalised mid-sentence is treated as
# a name — the conservative direction, since a false positive asks the user to check.
FUNCTION_WORDS = frozenset(
    {
        # Spanish
        "el", "la", "los", "las", "un", "una", "unos", "unas", "y", "o", "de", "del",
        "en", "con", "sin", "por", "para", "que", "como", "más", "mas", "se", "su",
        "sus", "al", "lo", "es", "son", "fue", "mi", "mis", "tu", "tus", "este",
        "esta", "estos", "estas", "no", "sí", "si", "cada", "muy", "entre", "sobre",
        "desde", "hasta", "durante", "cuando", "donde", "además", "ademas", "también",
        "tambien", "pero", "porque", "todo", "toda", "todos", "todas",
        # English
        "the", "a", "an", "and", "or", "of", "in", "on", "at", "to", "for", "with",
        "without", "that", "this", "these", "those", "as", "by", "from", "into",
        "over", "under", "is", "are", "was", "were", "be", "been", "my", "our",
        "your", "their", "its", "it", "he", "she", "they", "we", "you", "i", "not",
        "but", "when", "where", "while", "also", "more", "most", "each", "every",
        "all", "some", "very", "than", "then", "there", "here", "so", "if",
    }
)

_NUMBER = re.compile(r"\S*\d\S*")
_NUMBER_IN_TEXT = re.compile(r"\d[\d.,]*%?")
_WORD = re.compile(r"[^\W\d_]+(?:['’\-][^\W\d_]+)*", re.UNICODE)
_SENTENCE_END = frozenset(".!?;\n")
# A number token is trimmed of the punctuation that merely abuts it: "30%." is the
# number `30%` at the end of a sentence, not a different claim from the source's "30%".
_TRAILING = ".,;:!?)]}\"'”’…"
_LEADING = "([{\"'“‘"


@dataclass(frozen=True)
class Violation:
    """One rule broken, with the offending text so the interface can highlight it."""

    rule: str
    item: str
    text: str
    message: str
    span: tuple[int, int] | None = None


@dataclass(frozen=True)
class Sources:
    """What the provider was given, and what an output may therefore claim.

    Built by the caller with `profile_id` first (F1), so an id that is not here is not
    this profile's — the provenance rule needs no second lookup to refuse it.
    """

    bullets: Mapping[str, str] = field(default_factory=dict)
    stories: Mapping[str, str] = field(default_factory=dict)
    roles: Mapping[str, str] = field(default_factory=dict)
    skills: frozenset[str] = frozenset()
    aliases: Mapping[str, str] = field(default_factory=dict)
    # Titles the user holds (track headlines, role titles). A summary may name them;
    # they support proper nouns only, never a number.
    titles: tuple[str, ...] = ()

    @property
    def ids(self) -> set[str]:
        return {*self.bullets, *self.stories, *self.roles}

    def text_of(self, source_id: str) -> str:
        for table in (self.bullets, self.stories, self.roles):
            if source_id in table:
                return table[source_id]
        return ""


def _text_and_cites(output: Mapping[str, Any], kind: str) -> list[tuple[str, str, list[str]]]:
    """(name, text, cited ids) for every item the output carries, whatever its shape."""
    if kind == "summary":
        summary = output.get("summary") or {}
        cites = [str(value) for value in summary.get("cites") or []]
        return [("summary", str(summary.get("text") or ""), cites)]
    if kind == "bullet":
        cites = [str(value) for value in output.get("cites") or []]
        return [("bullet", str(output.get("text") or ""), cites)]
    if kind == "story_bullets":
        items: list[tuple[str, str, list[str]]] = []
        for index, bullet in enumerate(output.get("bullets") or []):
            cites = [
                str(value)
                for value in (bullet.get("story_id"), bullet.get("role_id"))
                if value
            ]
            items.append((f"bullet {index + 1}", str(bullet.get("text") or ""), cites))
        return items
    if kind == "letter_blocks":
        # F8's reusable paragraphs: a presentation and an achievements paragraph, each
        # citing the bullet, story or role ids it draws on (N8.3).
        items = []
        for name in ("presentation", "achievements"):
            paragraph = output.get(name) or {}
            items.append(
                (
                    name,
                    str(paragraph.get("text") or ""),
                    [str(value) for value in paragraph.get("sources") or []],
                )
            )
        return items
    raise ValueError(f"unknown generation kind {kind!r}")


def _grade_parts(grade: Any) -> tuple[int, str | None]:
    if isinstance(grade, Mapping):
        return int(grade.get("level") or 0), (
            str(grade["evidence_id"]) if grade.get("evidence_id") else None
        )
    return int(getattr(grade, "level", 0) or 0), (
        str(getattr(grade, "evidence_id", None)) if getattr(grade, "evidence_id", None) else None
    )


def _number_key(token: str) -> str:
    """A number token's identity: `30%`, `30`, `30.` and `30+` are the same claim.

    Thousands separators and a trailing decimal point are formatting, not data; the
    percent sign is dropped so `30%` and `30` compare equal — a source that says `30`
    supports an output that says `30%` — and a trailing `+` ("10+ years") is the number
    it lower-bounds.
    """
    return fold(token).replace("%", "").replace(",", "").rstrip(".+")


@dataclass(frozen=True)
class _SourceTokens:
    words: frozenset[str]
    numbers: frozenset[str]


def _source_tokens(text: str) -> _SourceTokens:
    """The cited sources as whole tokens — never substrings (F.0)."""
    folded = fold(text)
    return _SourceTokens(
        words=frozenset(_WORD.findall(folded)),
        numbers=frozenset(_number_key(match.group()) for match in _NUMBER_IN_TEXT.finditer(folded)),
    )


def _token_found(token: str, source: _SourceTokens) -> bool:
    """Whether a protected token is one of the source's own tokens.

    A token with a digit is a number and matches by numeric identity (`30` matches
    `30%`, `3` does not); anything else must be present word for word, so `Ban` does
    not match `Banco`.
    """
    folded = fold(token)
    if any(char.isdigit() for char in folded):
        return _number_key(folded) in source.numbers
    words = _WORD.findall(folded)
    return bool(words) and all(word in source.words for word in words)


def unsupported_claims(
    text: str, corpus: str, aliases: Mapping[str, str], *, skip_ambiguous: bool = False
) -> list[str]:
    """Tokens in `text` that `corpus` does not support (F10.5's flags).

    F7.3's literal-preservation extractor, reused: numbers, mid-sentence proper nouns
    and vocabulary aliases in the file that appear nowhere in the user's stored
    bullets, stories or roles. Pure — the caller supplies the corpus (A5: nothing is
    read from a network here).
    """
    source = _source_tokens(corpus)
    found: list[str] = []
    if skip_ambiguous:
        ambiguous = ambiguous_aliases()
        aliases = {alias: name for alias, name in aliases.items() if alias not in ambiguous}
    for token, _start, _end in _protected_tokens(text, aliases):
        if token not in found and not _token_found(token, source):
            found.append(token)
    return found


def _protected_tokens(text: str, aliases: Mapping[str, str]) -> list[tuple[str, int, int]]:
    """(token, start, end) for numbers, proper nouns and vocabulary aliases.

    A capitalised word at a sentence start, or a function word, is not a name; a
    proper noun that is not in the sources is a fabrication, and so is a number the
    sources do not contain. Alias matches are protected because a skill's words are a
    claim like any other.
    """
    tokens: list[tuple[str, int, int]] = []
    seen: set[tuple[int, int]] = set()

    def add(token: str, start: int, end: int) -> None:
        if (start, end) not in seen and token.strip():
            seen.add((start, end))
            tokens.append((token, start, end))

    for match in _NUMBER.finditer(text):
        token, start, end = match.group(), match.start(), match.end()
        while token and token[-1] in _TRAILING:
            token, end = token[:-1], end - 1
        while token and token[0] in _LEADING:
            token, start = token[1:], start + 1
        add(token, start, end)
    for match in _WORD.finditer(text):
        word = match.group()
        if not word[:1].isupper():
            continue
        if fold(word) in FUNCTION_WORDS:
            continue
        gap = text[: match.start()]
        before = gap.rstrip()
        # A line break ends a sentence as a full stop does: `rstrip` would otherwise
        # swallow the "\n" that `_SENTENCE_END` lists.
        if not before or before[-1] in _SENTENCE_END or "\n" in gap[len(before) :]:
            continue
        add(word, match.start(), match.end())
    for alias in sorted(aliases, key=len, reverse=True):
        for match in term_pattern(alias).finditer(fold(text)):
            add(alias, match.start(), match.end())
    return sorted(tokens, key=lambda item: item[1])


def validate(
    output: Mapping[str, Any],
    *,
    sources: Sources,
    profile_id: Any,
    session: Any,
    kind: str,
    grades: Sequence[Any] | None = None,
) -> list[Violation]:
    """The three rules of F7.3, in order; an empty list means the output may be shown.

    `profile_id` and `session` say whose output this is; the sources were built from
    that profile, so a citation outside them is a citation of somebody else's row and
    fails provenance without another query.
    """
    del profile_id, session  # ownership lives in the sources the caller built (F1)
    items = _text_and_cites(output, kind)
    violations: list[Violation] = []

    # 1 — Provenance.
    for name, _text, cites in items:
        if not cites:
            violations.append(
                Violation(PROVENANCE, name, "", "the item cites no source")
            )
        for cite in cites:
            if cite not in sources.ids:
                violations.append(
                    Violation(PROVENANCE, name, cite, f"{cite} was not a supplied source")
                )

    # 2 — Literal preservation: numbers and mid-sentence proper nouns. A vocabulary
    # alias is a skill, and rule 3 owns skills. A summary may also name a title the
    # user holds (a track headline, a role title), so those words support its names.
    titled = _source_tokens(" ".join(sources.titles)) if kind == "summary" else None
    for name, text, cites in items:
        source = _source_tokens(" ".join(sources.text_of(cite) for cite in cites))
        if titled is not None:
            source = _SourceTokens(words=source.words | titled.words, numbers=source.numbers)
        for token, start, end in _protected_tokens(text, {}):
            if not _token_found(token, source):
                violations.append(
                    Violation(
                        LITERAL,
                        name,
                        text[start:end],
                        f"{token!r} does not appear in the cited sources",
                        (start, end),
                    )
                )

    # 3 — Skill closure. A summary's skills block only has to exist in the user's data;
    # its prose must also be evidenced at level 2 or better (F7.3). Other kinds have no
    # skills block, so every skill their text names must exist in the user's data.
    all_text = " ".join(text for _name, text, _cites in items)
    # "Evidenced" is in the bullets the summary cites (F7.3: "in the selected bullets"),
    # not in every bullet that was graded.
    cited = {cite for _name, _text, cites in items for cite in cites}
    evidenced_bullets = {
        evidence_id
        for grade in (grades or [])
        for level, evidence_id in [_grade_parts(grade)]
        if level >= 2 and evidence_id and (kind != "summary" or evidence_id in cited)
    }
    evidenced_canonicals: set[str] = set()
    for bullet_id, bullet_text in sources.bullets.items():
        if bullet_id in evidenced_bullets:
            evidenced_canonicals.update(
                match_text(bullet_text, sources.aliases, skip_ambiguous=True)
            )

    named_in_text = (
        match_text(all_text, sources.aliases, skip_ambiguous=True) if sources.aliases else []
    )
    listed = [str(name) for name in output.get("skills") or [] if name] if kind == "summary" else []
    reported: set[str] = set()
    for canonical in [*listed, *named_in_text]:
        if canonical not in sources.skills and canonical not in reported:
            reported.add(canonical)
            violations.append(
                Violation(
                    CLOSURE_MISSING,
                    kind,
                    canonical,
                    f"{canonical!r} is not in this profile's data",
                )
            )
    if kind == "summary":
        for canonical in named_in_text:
            if (
                canonical in sources.skills
                and canonical not in evidenced_canonicals
                and canonical not in reported
            ):
                reported.add(canonical)
                violations.append(
                    Violation(
                        CLOSURE_UNEVIDENCED,
                        kind,
                        canonical,
                        f"{canonical!r} is not evidenced at level 2 or better in the "
                        "bullets this summary cites",
                    )
                )
    return violations


# --- F7.5: the probable-keywords answer ---------------------------------------------

PLACEMENTS = ("skills", "existing_bullet", "new_bullet")


@dataclass(frozen=True)
class KeywordMaterial:
    """What the keyword inference was given, and so what its answer may claim (F7.5).

    Built by the caller from the profile's own rows, so an id that is not here is somebody
    else's row or no row at all. `canonicals` maps each candidate, as sent, to the canonical
    the vocabulary gives it — or `None` for a phrase the vocabulary does not know, which is
    allowed — and `kinds` gives that canonical's kind.
    """

    candidates: tuple[str, ...]
    canonicals: Mapping[str, str | None]
    kinds: Mapping[str, str]
    skills: frozenset[str]
    bullets: Mapping[str, str]
    roles: Mapping[str, str]
    aliases: Mapping[str, str] = field(default_factory=dict)


def _id_or_none(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text if text and text.lower() not in {"null", "none"} else None


def _keyword_item_ok(item: Mapping[str, Any], material: KeywordMaterial) -> dict[str, Any] | None:
    """The item, normalised, when every guard of F7.5 holds; otherwise `None`."""
    keyword = str(item.get("keyword") or "")
    # 1 — closed candidate set: verbatim, never a term the model brought.
    if keyword not in material.candidates:
        return None
    # 2 — only what the model itself marked highly probable.
    if str(item.get("confidence") or "").strip().lower() != "high":
        return None
    # 5 — a named tool is never inferred; a phrase the vocabulary does not know may be.
    canonical = material.canonicals.get(keyword)
    if canonical is not None and material.kinds.get(canonical) == "tool":
        return None
    reason = str(item.get("reason") or "").strip()
    if not reason:
        return None

    # 3 — provenance: something is cited, and every id is one that was sent.
    supports = [str(value) for value in item.get("supports") or [] if str(value).strip()]
    if not supports:
        return None
    cited_text: list[str] = []
    for support in supports:
        kind, _, name = support.partition(":")
        if kind == "skill" and name in material.skills:
            cited_text.append(name)
        elif kind == "bullet" and name in material.bullets:
            cited_text.append(material.bullets[name])
        else:
            return None
    placement = str(item.get("placement") or "")
    if placement not in PLACEMENTS:
        return None
    bullet_id, role_id = _id_or_none(item.get("bullet_id")), _id_or_none(item.get("role_id"))
    if bullet_id is not None and bullet_id not in material.bullets:
        return None
    if role_id is not None and role_id not in material.roles:
        return None
    if placement == "existing_bullet" and bullet_id is None:
        return None
    if placement == "new_bullet" and role_id is None:
        return None
    if placement == "skills":
        bullet_id = role_id = None
    elif placement == "existing_bullet":
        role_id = None
    else:
        bullet_id = None

    # 4 — literal preservation (F7.3): the draft may add the keyword and nothing else new.
    draft = _id_or_none(item.get("draft"))
    if draft is not None:
        corpus = [*cited_text, keyword]
        if bullet_id is not None:
            corpus.append(material.bullets[bullet_id])
        if role_id is not None:
            corpus.append(material.roles[role_id])
        if unsupported_claims(draft, " ".join(corpus), material.aliases, skip_ambiguous=True):
            return None
    return {
        "keyword": keyword,
        "canonical": canonical,
        "confidence": "high",
        "supports": supports,
        "reason": reason,
        "placement": placement,
        "bullet_id": bullet_id,
        "role_id": role_id,
        "draft": draft,
    }


def validate_keyword_items(
    items: Sequence[Mapping[str, Any]], material: KeywordMaterial
) -> tuple[list[dict[str, Any]], int]:
    """F7.5's guards over the model's items: `(items that may be shown, how many dropped)`.

    An item that breaks a guard is dropped, never weakened until it passes — and counted, so
    the page can say how many suggestions could not be checked. A keyword offered twice
    counts once. Run after the call and again on render: the answer is data from a model,
    and the material it was checked against is the user's own.
    """
    kept: list[dict[str, Any]] = []
    seen: set[str] = set()
    dropped = 0
    for item in items:
        checked = _keyword_item_ok(item, material)
        if checked is None or checked["keyword"] in seen:
            dropped += 1
            continue
        seen.add(checked["keyword"])
        kept.append(checked)
    return kept, dropped
