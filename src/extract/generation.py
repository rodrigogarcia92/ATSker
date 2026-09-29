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
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.extract import redaction
from src.extract.client import CallOptions, Completion, complete_json
from src.extract.prompts import (
    BULLET_REPHRASE_V1,
    STORY_BULLETS_V1,
    SUMMARY_SKILLS_V1,
    summarize_rows,
)
from src.jd import StructuredJD

GENERATE_SUMMARY = "generate_summary"
GENERATE_BULLET = "generate_bullet"
STORY_BULLETS = "story_bullets"


class SummarySkills(BaseModel):
    """Tier 1's answer: a summary and the skills block, both grounded in the bullets."""

    summary: str = Field(description="the summary text, in the posting's language")
    cites: list[str] = Field(description="the bullet ids the summary draws on")
    skills: list[str] = Field(description="canonicals, ordered for this posting")


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


@dataclass(frozen=True)
class Proposal:
    """One generated answer, with what it cost and the prompt that produced it.

    `output` is the shape the validator and the form both read: for a summary
    `{"summary": {"text", "cites"}, "skills"}`, for a bullet `{"text", "cites"}`, for
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


def generate_summary(
    session: Session,
    *,
    jd: StructuredJD,
    bullets: Sequence[tuple[str, str]],
    track_skills: Sequence[str],
    pool: Sequence[str],
    grades: Sequence[Mapping[str, Any]],
    language: str,
    known_names: Sequence[str] | None = None,
    model: str | None = None,
    options: CallOptions | None = None,
) -> Proposal:
    """One call: the summary and the skills block for one application (F7.3, Tier 1)."""
    bullet_rows = summarize_rows(
        [f"{bullet_id}\t{_redacted(text, known_names)}" for bullet_id, text in bullets]
    )
    completion = complete_json(
        session,
        purpose=GENERATE_SUMMARY,
        prompt_version=SUMMARY_SKILLS_V1.version,
        system=SUMMARY_SKILLS_V1.render_system(),
        user=SUMMARY_SKILLS_V1.render(
            lang=language,
            jd=_jd_block(jd),
            bullets=bullet_rows,
            grades=_grades_block(grades),
            track_skills=summarize_rows(list(track_skills)),
            pool=summarize_rows(list(pool)),
        ),
        schema=SummarySkills,
        model=model,
        options=options,
    )
    answer = SummarySkills.model_validate(completion.data)
    return Proposal(
        kind="summary",
        output={
            "summary": {"text": answer.summary.strip(), "cites": list(answer.cites)},
            "skills": list(answer.skills),
        },
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
