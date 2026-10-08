"""Generated prose (PRD F7.3): the provider calls, and only they leave this module.

Every function here makes at most one call, renders its prompt from the material the
caller already selected, and returns the parsed answer with its `Completion` — the
cost and the prompt version travel with it, exactly as grading's do. Nothing decides
whether the answer is *true*: that is `src.generate.validators`, run by the caller
against the same sources, and it is run again on accept.

On demand only: nothing here runs during an analysis, and nothing is stored. The
answer becomes a proposal that travels in a form until the user accepts it.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.extract import redaction
from src.extract.client import CallOptions, Completion, complete_json
from src.extract.prompts import (
    BULLET_REPHRASE_V1,
    KEYWORD_INFER_V1,
    LETTER_BLOCKS_V1,
    LETTER_BRIDGE_V2,
    STORY_BULLETS_V1,
    SUMMARY_V5,
    summarize_rows,
)
from src.jd import StructuredJD

GENERATE_SUMMARY = "generate_summary"
GENERATE_BULLET = "generate_bullet"
STORY_BULLETS = "story_bullets"
LETTER_BLOCKS = "letter_blocks"
LETTER_BRIDGE = "letter_bridge"
KEYWORD_INFER = "keyword_infer"


class SummaryOnly(BaseModel):
    """Tier 1's answer: a summary and the bullet ids it draws on. No skills list (F7.5)."""

    summary: str = Field(description="the summary text, in the posting's language")
    cites: list[str] = Field(
        description="the bullet ids the summary draws on, and summary:<id> for the base summary"
    )


class BulletRephrase(BaseModel):
    """Tier 3a's answer: one bullet, rewritten for the posting."""

    text: str = Field(description="the rewritten bullet, in the posting's language")
    cites: list[str] = Field(description="the id of the bullet this rewrites")


class StoryBulletDraft(BaseModel):
    text: str = Field(description="one CV bullet derived from the story")
    story_id: str = Field(description="the id of the story it came from")
    role_id: str = Field(description="the id of the role it belongs to")


class StoryBullets(BaseModel):
    """Tier 3b's answer: up to three bullets a story supports."""

    bullets: list[StoryBulletDraft] = Field(default_factory=list)


class LetterParagraph(BaseModel):
    """One reusable letter paragraph, with the ids it draws on (N8.3)."""

    text: str = Field(description="the paragraph, in the requested language")
    sources: list[str] = Field(description="the bullet, story or role ids it cites")


class LetterBlocks(BaseModel):
    """Tier 1's letter answer: presentation and achievements, each cited."""

    presentation: LetterParagraph
    achievements: LetterParagraph


class CompanyFact(BaseModel):
    """A company detail, with the posting line that says it (F8.4)."""

    text: str = Field(description="the fact, as the letter states it")
    jd_quote: str = Field(description="the verbatim posting line it comes from")


class LetterBridgeOne(BaseModel):
    """F8.3's answer: one bridge, its angle, its sources, and the risk line."""

    angle: str = Field(description="two or three words naming the angle")
    text: str = Field(description="three sentences ideally, four at most, at most 90 words")
    sources: list[str] = Field(description="the ids it draws on")
    company_fact: CompanyFact | None = None
    risk: str | None = None


class InferredKeyword(BaseModel):
    """One keyword the model judges highly probable, with what it rests on (F7.5)."""

    keyword: str = Field(description="one of the candidates, copied exactly")
    confidence: str = Field(description='"high" — anything less is omitted')
    supports: list[str] = Field(description="skill:<canonical> and bullet:<id> it rests on")
    reason: str = Field(description="one line: what the person holds that makes it probable")
    placement: str = Field(description="skills, existing_bullet or new_bullet")
    bullet_id: str | None = Field(default=None, description="for existing_bullet")
    role_id: str | None = Field(default=None, description="for new_bullet")
    draft: str | None = Field(default=None, description="the bullet's wording, if any")


class KeywordInference(BaseModel):
    """F7.5's answer: the probable keywords, and nothing else."""

    items: list[InferredKeyword] = Field(default_factory=list)


@dataclass(frozen=True)
class Proposal:
    """One generated answer, with what it cost and the prompt that produced it.

    `output` is the shape the validator and the form both read: for a summary
    `{"summary": {"text", "cites"}}`, for a bullet `{"text", "cites"}`, for
    story bullets `{"bullets": [{"text", "story_id", "role_id"}]}`.
    """

    kind: str
    output: dict[str, Any]
    completion: Completion


def _jd_block(jd: StructuredJD) -> str:
    """The posting as a few labelled lines — the fields the summary must answer to."""
    rows = [
        f"title: {jd.title}",
        f"seniority: {jd.seniority}",
        f"must_have: {', '.join(jd.must_have) or '(none)'}",
        f"nice_to_have: {', '.join(jd.nice_to_have) or '(none)'}",
        f"keywords: {', '.join(jd.raw_keywords) or '(none)'}",
    ]
    if jd.responsibilities:
        rows.append(f"responsibilities: {'; '.join(jd.responsibilities)}")
    return "\n".join(rows)


def _grades_block(grades: Sequence[Mapping[str, Any]]) -> str:
    rows = [
        f"{grade.get('requirement', '')}\t{grade.get('level', 0)}\t"
        f"{'must' if grade.get('must_have') else 'nice'}"
        for grade in grades
    ]
    return summarize_rows(rows)


def _redacted(text: str, known_names: Sequence[str] | None) -> str:
    """Nothing leaves for the provider with a name, an e-mail or a phone in it (PRD 10)."""
    return redaction.redact(text, known_names=known_names or None)


class BaseLike(Protocol):
    """The summary a proposal follows (`generate.proposals.BaseSummary`)."""

    text: str
    summary_id: str
    origin: str


def _base_block(base: BaseLike | None, language: str, known_names: Sequence[str] | None) -> str:
    if base is None:
        return "(none) — there is no base summary; write it from the bullets."
    note = (
        f"This base is in another language: translate it into {language} as you improve it.\n"
        if base.origin == "other_language"
        else ""
    )
    return f"{note}id: summary:{base.summary_id}\n{_redacted(base.text, known_names)}"


def _retry_block(retry: tuple[str, Sequence[str]] | None) -> str:
    if retry is None:
        return ""
    previous, failed = retry
    return (
        "\n\nYour previous answer broke these rules: "
        + "; ".join(failed)
        + f".\nThe previous text was:\n{previous}\nWrite it again so every rule holds."
    )


def _shortlist_row(row: Sequence[str]) -> str:
    """One shortlist line: the wording, and where the skill comes from when that is known."""
    wording, step = row[0], (row[2] if len(row) > 2 else "")
    return f"{wording}	{step}" if step else wording


def generate_summary(
    session: Session,
    *,
    jd: StructuredJD,
    bullets: Sequence[tuple[str, str]],
    track_skills: Sequence[str],
    pool: Sequence[str],
    grades: Sequence[Mapping[str, Any]],
    language: str,
    title: str = "",
    base: BaseLike | None = None,
    shortlist: Sequence[tuple[str, ...]] = (),
    banned: Sequence[str] = (),
    retry: tuple[str, Sequence[str]] | None = None,
    known_names: Sequence[str] | None = None,
    model: str | None = None,
    options: CallOptions | None = None,
) -> Proposal:
    """One call: the summary for one application (F7.3, Tier 1; `summary_v5`).

    `title` is the posting's, to be opened with verbatim; `shortlist` is (wording,
    canonical[, step]) rows that code chose, the step being `posting` or `related`; `base` is
    the summary to follow and improve.
    `retry` is (the previous text, the failed rules) for the one second call. The track's
    skills and the pool go in as context for skill closure, never as output: the answer is
    a summary and its citations, and accepting it never touches the track's skills.
    """
    bullet_rows = summarize_rows(
        [f"{bullet_id}	{_redacted(text, known_names)}" for bullet_id, text in bullets]
    )
    completion = complete_json(
        session,
        purpose=GENERATE_SUMMARY,
        prompt_version=SUMMARY_V5.version,
        system=SUMMARY_V5.render_system(),
        user=SUMMARY_V5.render(
            lang=language,
            title=title or "(none)",
            shortlist=summarize_rows([_shortlist_row(row) for row in shortlist]),
            base=_base_block(base, language, known_names),
            jd=_jd_block(jd),
            bullets=bullet_rows,
            grades=_grades_block(grades),
            track_skills=summarize_rows(list(track_skills)),
            pool=summarize_rows(list(pool)),
            banned="\n".join(f"- {phrase}" for phrase in banned) or "(none)",
            retry=_retry_block(retry),
        ),
        schema=SummaryOnly,
        model=model,
        options=options,
    )
    answer = SummaryOnly.model_validate(completion.data)
    return Proposal(
        kind="summary",
        output={"summary": {"text": answer.summary.strip(), "cites": list(answer.cites)}},
        completion=completion,
    )


def generate_bullet(
    session: Session,
    *,
    bullet_id: str,
    texts: Mapping[str, str],
    requirements: Sequence[str],
    jd_title: str,
    language: str,
    known_names: Sequence[str] | None = None,
    model: str | None = None,
    options: CallOptions | None = None,
) -> Proposal:
    """One call: rephrase one bullet for this posting (F7.3, Tier 3a)."""
    lines = [f"{lang}: {_redacted(text, known_names)}" for lang, text in texts.items() if text]
    posting = "\n".join([f"title: {jd_title}", *[f"cited for: {text}" for text in requirements]])
    completion = complete_json(
        session,
        purpose=GENERATE_BULLET,
        prompt_version=BULLET_REPHRASE_V1.version,
        system=BULLET_REPHRASE_V1.render_system(),
        user=BULLET_REPHRASE_V1.render(
            posting=posting,
            bullet=f"{bullet_id}\n" + summarize_rows(lines),
            lang=language,
        ),
        schema=BulletRephrase,
        model=model,
        options=options,
    )
    answer = BulletRephrase.model_validate(completion.data)
    return Proposal(
        kind="bullet",
        output={"text": answer.text.strip(), "cites": list(answer.cites)},
        completion=completion,
    )


def generate_story_bullets(
    session: Session,
    *,
    story_id: str,
    body: str,
    roles: Sequence[tuple[str, str]],
    language: str,
    known_names: Sequence[str] | None = None,
    model: str | None = None,
    options: CallOptions | None = None,
) -> Proposal:
    """One call: up to three bullets a story supports (F7.3, Tier 3b)."""
    completion = complete_json(
        session,
        purpose=STORY_BULLETS,
        prompt_version=STORY_BULLETS_V1.version,
        system=STORY_BULLETS_V1.render_system(),
        user=STORY_BULLETS_V1.render(
            story=f"{story_id}\n{_redacted(body, known_names)}",
            roles=summarize_rows(
                [f"{role_id}\t{title or '(untitled)'}" for role_id, title in roles]
            ),
            lang=language,
        ),
        schema=StoryBullets,
        model=model,
        options=options,
    )
    answer = StoryBullets.model_validate(completion.data)
    return Proposal(
        kind="story_bullets",
        output={
            "bullets": [
                {"text": draft.text.strip(), "story_id": draft.story_id, "role_id": draft.role_id}
                for draft in answer.bullets
            ]
        },
        completion=completion,
    )


def generate_letter_blocks(
    session: Session,
    *,
    bullets: Sequence[tuple[str, str]],
    roles: Sequence[tuple[str, str]],
    summary: str | None,
    stories: Sequence[tuple[str, str]],
    voice_notes: str,
    language: str,
    known_names: Sequence[str] | None = None,
    model: str | None = None,
    options: CallOptions | None = None,
) -> Proposal:
    """One call: a template's presentation and achievements (PRD F8, N8.3).

    The material is the track's own: its bullets in order, its roles, its summary in
    the template's language, and the profile's stories. Nothing else may be cited.
    """
    completion = complete_json(
        session,
        purpose=LETTER_BLOCKS,
        prompt_version=LETTER_BLOCKS_V1.version,
        system=LETTER_BLOCKS_V1.render_system(),
        user=LETTER_BLOCKS_V1.render(
            lang=language,
            bullets=summarize_rows(
                [f"{bullet_id}\t{_redacted(text, known_names)}" for bullet_id, text in bullets]
            ),
            roles=summarize_rows([f"{role_id}\t{title}" for role_id, title in roles]),
            summary=summarize_rows([_redacted(summary, known_names)] if summary else []),
            stories=summarize_rows(
                [
                    f"{story_id}\t{_redacted(text, known_names)}"
                    for story_id, text in stories
                ]
            ),
            voice_notes=voice_notes.strip() or "(none)",
        ),
        schema=LetterBlocks,
        model=model,
        options=options,
    )
    answer = LetterBlocks.model_validate(completion.data)
    return Proposal(
        kind="letter_blocks",
        output={
            "presentation": {
                "text": answer.presentation.text.strip(),
                "sources": list(answer.presentation.sources),
            },
            "achievements": {
                "text": answer.achievements.text.strip(),
                "sources": list(answer.achievements.sources),
            },
        },
        completion=completion,
    )


def generate_letter_bridge_one(
    session: Session,
    *,
    jd_text: str,
    company: str | None,
    title: str | None,
    template: Any,
    material: str,
    voice_notes: str,
    language: str,
    banned: Sequence[str],
    previous: Sequence[str],
    known_names: Sequence[str] | None = None,
    repair: str | None = None,
    model: str | None = None,
    options: CallOptions | None = None,
) -> Proposal:
    """One call: one bridge for one application (PRD F8.3).

    `template` is the track's (its `presentation` and `achievements` are the style
    reference); `material` is the person's own evidence, strongest first. The previous
    versions are part of the user message, so each "Otra versión" is a new input and a
    new cache key. `repair` turns the same call into the single retry.
    """
    body = LETTER_BRIDGE_V2.render(
        posting=_redacted(jd_text, known_names),
        company=company or "(none)",
        title=title or "(none)",
        presentation=template.presentation.strip() or "(none)",
        achievements=template.achievements.strip() or "(none)",
        material=material,
        voice_notes=voice_notes.strip() or "(none)",
        banned="\n".join(f"- {phrase}" for phrase in banned) or "(none)",
        previous="\n".join(f"{index}. {text}" for index, text in enumerate(previous, 1))
        or "(none)",
        lang=language,
    )
    if repair:
        body = f"{body}\n\nYour previous answer was unusable: {repair}"
    completion = complete_json(
        session,
        purpose=LETTER_BRIDGE,
        prompt_version=LETTER_BRIDGE_V2.version,
        system=LETTER_BRIDGE_V2.render_system(),
        user=body,
        schema=LetterBridgeOne,
        model=model,
        options=options,
    )
    answer = LetterBridgeOne.model_validate(completion.data)
    return Proposal(
        kind="letter_bridge",
        output={
            "angle": answer.angle.strip(),
            "text": answer.text.strip(),
            "sources": list(answer.sources),
            "company_fact": (
                {
                    "text": answer.company_fact.text.strip(),
                    "jd_quote": answer.company_fact.jd_quote,
                }
                if answer.company_fact is not None
                else None
            ),
            "risk": (answer.risk or "").strip() or None,
        },
        completion=completion,
    )


def generate_keyword_inference(
    session: Session,
    *,
    candidates: Sequence[str],
    pool: Sequence[str],
    bullets: Sequence[tuple[str, str]],
    roles: Sequence[tuple[str, str]],
    banned: Sequence[str],
    language: str,
    known_names: Sequence[str] | None = None,
    model: str | None = None,
    options: CallOptions | None = None,
) -> Proposal:
    """One call: which of the leftover keywords are highly probable for this person (F7.5).

    Purpose `keyword_infer`, redacted like every call and cached by content hash, so the
    same material asks the provider once. The answer is raw: `generate.validators` decides
    which items may be shown, and nothing here is stored.
    """
    completion = complete_json(
        session,
        purpose=KEYWORD_INFER,
        prompt_version=KEYWORD_INFER_V1.version,
        system=KEYWORD_INFER_V1.render_system(),
        user=KEYWORD_INFER_V1.render(
            lang=language,
            candidates=summarize_rows(list(candidates)),
            pool=summarize_rows(list(pool)),
            bullets=summarize_rows(
                [f"{bullet_id}\t{_redacted(text, known_names)}" for bullet_id, text in bullets]
            ),
            roles=summarize_rows(
                [f"{role_id}\t{_redacted(title, known_names)}" for role_id, title in roles]
            ),
            banned="\n".join(f"- {phrase}" for phrase in banned) or "(none)",
        ),
        schema=KeywordInference,
        model=model,
        options=options,
    )
    answer = KeywordInference.model_validate(completion.data)
    return Proposal(
        kind="keyword_infer",
        output={
            "items": [
                {
                    "keyword": item.keyword,
                    "confidence": item.confidence,
                    "supports": list(item.supports),
                    "reason": item.reason.strip(),
                    "placement": item.placement,
                    "bullet_id": item.bullet_id,
                    "role_id": item.role_id,
                    "draft": (item.draft or "").strip() or None,
                }
                for item in answer.items
            ]
        },
        completion=completion,
    )
