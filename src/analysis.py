"""One analysis (PRD F4): extraction, grading, the deterministic sub-scores, and
the report that is persisted as an application (F8).

This module exists because the two halves may not know about each other: `score/`
makes no network calls and `extract/` imports neither `score/` nor `parse/`
(PRD 5.1), so the composition lives here.

Until M9 supplies embeddings, the semantic sub-score cannot be computed. The total
is renormalised over the four that exist, and the omission, its reason and the
effective weights are recorded in the report (state doc §4, option A).
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from src.bullets import bullet_text, list_bullets
from src.extract.client import CallOptions, Completion
from src.extract.grading import grade_evidence
from src.extract.jd import extract_jd
from src.extract.prompts import EVIDENCE_GRADING, JD_EXTRACTION
from src.jd import StructuredJD
from src.models import Bullet, Profile
from src.parse.gate import ParseReport
from src.roles import list_roles
from src.score.aggregate import SubScore, aggregate
from src.score.evidence import Level, evidence_coverage
from src.score.experience import experience_score
from src.score.keywords import keyword_context
from src.score.title import title_alignment
from src.score.weights import W1
from src.vocabulary import alias_map

# The reason recorded in every report while the semantic sub-score does not exist.
UNAVAILABLE_UNTIL_M9 = {"semantic": "embeddings_not_available"}


@dataclass(frozen=True)
class Analysis:
    """What one analysis produced, before it is written to `applications` (F8).

    `jd` and `bullets` are the inputs the judge saw; the model-selection experiment
    re-runs the judge against them to measure stability without re-running
    extraction.
    """

    report: dict[str, object]
    prompt_versions: dict[str, str]
    weights_version: str
    cost_usd: Decimal
    jd_hash: str
    title: str | None
    company: str | None
    jd: StructuredJD
    bullets: tuple[Bullet, ...]


def _llm_section(calls: Sequence[Completion], cost: Decimal) -> dict[str, object]:
    """The cost ledger for this analysis, as it will be shown on the report page."""
    return {
        "cost_usd": str(cost),
        "calls": [
            {
                "purpose": call.purpose,
                "prompt_version": call.prompt_version,
                "model": call.model,
                "cached": call.cached,
                "prompt_tokens": call.prompt_tokens,
                "completion_tokens": call.completion_tokens,
                "cost_usd": str(call.cost_usd),
                "fingerprint": call.fingerprint,
                "ledger_error": call.ledger_error,
            }
            for call in calls
        ],
    }


def analyze(
    profile_id: uuid.UUID,
    session: Session,
    *,
    jd_text: str,
    company: str | None = None,
    title: str | None = None,
    gate: ParseReport | None = None,
    model: str | None = None,
    options: CallOptions | None = None,
) -> Analysis:
    """Run the whole pipeline for one pasted posting.

    `gate` is the parse check of the résumé document the analysis is run against;
    it stays None until M2b stores résumé files, so today the score is never capped
    by a document. Nothing is persisted here except the model calls themselves —
    the caller writes the application.

    `options` exists for the model-selection experiment, which must bypass the
    content-hash cache to measure the judge rather than the cache.
    """
    profile = session.get(Profile, profile_id)
    if profile is None:
        raise RuntimeError("an analysis needs a profile that exists")

    roles = list_roles(profile_id, session, active_only=True)
    role_ids = {role.id for role in roles}
    bullets = [
        bullet
        for bullet in list_bullets(profile_id, session, active_only=True)
        if bullet.role_id in role_ids
    ]
    aliases = alias_map(session)
    today = date.today()

    # Transaction boundaries are the unit of work's: release the profile, role and
    # bullet reads before each provider call (client.complete_json refuses to run
    # inside a transaction, which is the connection the database kills).
    session.commit()
    jd, extraction = extract_jd(session, jd_text, model=model, options=options)
    # The extraction just wrote its unmapped-term notes; the grading call must not
    # carry them across the network either.
    session.commit()
    grading = grade_evidence(
        session,
        jd,
        bullets,
        language=jd.language,
        model=model,
        known_names=[profile.display_name] if profile.display_name else None,
        options=options,
    )

    sub_scores: dict[str, SubScore] = {
        "title": title_alignment(
            jd,
            headline=profile.headline,
            role_titles=[role.title for role in roles],
            aliases=aliases,
        ),
        "evidence": evidence_coverage(
            [Level(entry.requirement, entry.level, entry.must_have) for entry in grading.levels]
        ),
        "keyword": keyword_context(
            jd, [bullet_text(bullet) for bullet in bullets], aliases=aliases
        ),
        "experience": experience_score(
            jd,
            [
                (role.start_date, role.end_date or today)
                for role in roles
                if role.start_date is not None
            ],
            today=today,
        ),
    }
    score = aggregate(sub_scores, W1, gate=gate, unavailable=UNAVAILABLE_UNTIL_M9)

    texts = {str(bullet.id): bullet_text(bullet) for bullet in bullets}
    calls = (extraction, *grading.calls)
    cost = sum((call.cost_usd for call in calls), Decimal("0"))

    report: dict[str, object] = {
        "jd": jd.model_dump(mode="json"),
        "grades": [
            {
                "requirement": entry.requirement,
                "must_have": entry.must_have,
                "level": entry.level,
                "bullet_id": entry.bullet_id,
                # Snapshotted: the report must still show what was graded after
                # the bullet is edited or deactivated.
                "bullet_text": texts.get(entry.bullet_id or ""),
            }
            for entry in grading.levels
        ],
        "grading_note": grading.note,
        "gate": gate.to_dict() if gate is not None else None,
        "score": score.to_dict(),
        "llm": _llm_section(calls, cost),
    }

    return Analysis(
        report=report,
        prompt_versions={
            "jd_extract": JD_EXTRACTION.version,
            "evidence_grade": EVIDENCE_GRADING.version,
        },
        weights_version=score.weights_version,
        cost_usd=cost,
        jd_hash=jd.source_hash,
        title=(title or "").strip() or jd.title or None,
        company=(company or "").strip() or None,
        jd=jd,
        bullets=tuple(bullets),
    )
