"""One analysis (PRD F4): extraction, grading, the deterministic sub-scores, and
the report that is persisted as an application (F8).

This module exists because the two halves may not know about each other: `score/`
makes no network calls and `extract/` imports neither `score/` nor `parse/`
(PRD 5.1), so the composition lives here.

The four sub-scores are `w2` (PRD F5.5): `skills`, `experience`, `title`, `keywords`,
with semantic fit removed rather than deferred, so nothing is declared unavailable and
nothing is renormalised. The guard that refuses an undeclared omission stays in
`aggregate()` all the same.

An analysis of a track is scored against that track's selection and capped by the
résumé the track was built from, when there is one (F5.1). It also runs Scan B (F5.2):
one call derives the boolean queries a recruiter would run, and the deterministic
evaluator in `src.search` says which of them this track's text would be returned by.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from src.bullets import bullet_text, list_bullets
from src.education import list_educations
from src.extract.boolean import derive_boolean_queries
from src.extract.client import CallOptions, Completion
from src.extract.gaps import GapInput, interpret_gaps
from src.extract.grading import grade_evidence
from src.extract.jd import extract_jd
from src.extract.prompts import BOOLEAN_RECALL, EVIDENCE_GRADING, GAP_INTERPRETATION, JD_EXTRACTION
from src.jd import StructuredJD
from src.models import Bullet, Profile, Track
from src.parse.gate import ParseReport
from src.resumes import source_document_for_track
from src.roles import list_roles
from src.score.aggregate import SubScore, aggregate
from src.score.evidence import Level, evidence_coverage
from src.score.experience import experience_score
from src.score.gaps import Graded, detect_gaps, disqualifier_verdicts
from src.score.keywords import keyword_context
from src.score.title import title_alignment
from src.score.weights import W2
from src.search.boolean import RecallReport, evaluate
from src.search.sources import searchable_units
from src.stories import list_stories
from src.tracks import track_bullets
from src.vocabulary import alias_map


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
    recall: RecallReport = RecallReport()


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
    track: Track | None = None,
) -> Analysis:
    """Run the whole pipeline for one pasted posting.

    `gate` is the parse check of the résumé document the analysis is run against;
    it stays None until M2b stores résumé files, so today the score is never capped
    by a document. Nothing is persisted here except the model calls themselves —
    the caller writes the application.

    `track` narrows the evidence to that track's selection, in its order (F4), and
    lets its headline stand in for the profile's when the title is scored. Without
    a track the evidence is every active bullet, exactly as before: the same posting
    scored against two tracks must differ, and that difference must not come from a
    changed default.

    `options` exists for the model-selection experiment, which must bypass the
    content-hash cache to measure the judge rather than the cache.
    """
    profile = session.get(Profile, profile_id)
    if profile is None:
        raise RuntimeError("an analysis needs a profile that exists")

    roles = list_roles(profile_id, session, active_only=True)
    role_ids = {role.id for role in roles}
    if track is None:
        bullets = [
            bullet
            for bullet in list_bullets(profile_id, session, active_only=True)
            if bullet.role_id in role_ids
        ]
    else:
        # A bullet the user has since deactivated, or whose role was, is not evidence
        # even when a track still selects it — the same rule as the no-track path.
        bullets = [
            bullet
            for bullet in track_bullets(profile_id, session, track.id)
            if bullet.active and bullet.role_id in role_ids
        ]
        # F5.1: a track built from an upload is capped by the document that produced
        # it. No source document — or no track — means no gate and no cap, which is
        # also what an analysis against the master database has always been.
        if gate is None:
            source = source_document_for_track(profile_id, session, track.id)
            if source is not None and source.gate:
                gate = ParseReport.from_dict(source.gate)
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
    # F5.2's scan is its own provider call, so the same boundary applies: the reads
    # below happen after it, and the call starts with nothing held.
    session.commit()
    queries, recall_call = derive_boolean_queries(
        session, jd_text, model=model, options=options
    )
    recall = evaluate(
        queries.queries,
        searchable_units(
            profile_id,
            session,
            bullets=bullets,
            headline=(track.headline if track is not None else None) or profile.headline,
            summary=(track.summary if track is not None else None) or profile.summary,
            role_titles=[role.title for role in roles],
        ),
        alias_map(session),
    )

    sub_scores: dict[str, SubScore] = {
        "title": title_alignment(
            jd,
            headline=(track.headline if track is not None else None) or profile.headline,
            role_titles=[role.title for role in roles],
            aliases=aliases,
        ),
        "skills": evidence_coverage(
            [Level(entry.requirement, entry.level, entry.must_have) for entry in grading.levels]
        ),
        "keywords": keyword_context(
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
    score = aggregate(sub_scores, W2, gate=gate)

    texts = {str(bullet.id): bullet_text(bullet) for bullet in bullets}

    # N5 (PRD F6, F6.1): the gaps fall out of the grading above — deterministic and
    # free — and one call interprets them. The disqualifier verdicts are deterministic
    # too: only what the stored education rows decide, `unverified` otherwise.
    gaps = detect_gaps(
        [
            Graded(
                requirement=entry.requirement,
                level=entry.level,
                must_have=entry.must_have,
                bullet_id=entry.bullet_id,
                bullet_text=texts.get(entry.bullet_id or ""),
            )
            for entry in grading.levels
        ],
        must_have=jd.must_have,
        nice_to_have=jd.nice_to_have,
    )
    disqualifiers = disqualifier_verdicts(
        jd.hard_requirements, has_education=bool(list_educations(profile_id, session))
    )
    stories = list_stories(profile_id, session)
    # The reads above end before the provider call starts, like every other call here.
    session.commit()
    reading = interpret_gaps(
        session,
        [
            GapInput(gap.requirement, gap.level, gap.must_have, gap.bullet_text) for gap in gaps
        ],
        jd,
        standing_risks=profile.standing_risks,
        stories=stories,
        language=jd.language,
        known_names=[profile.display_name] if profile.display_name else None,
        model=model,
        options=options,
    )

    calls = (extraction, *grading.calls, recall_call, *reading.calls)
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
        # N5 (PRD F6): the gap analysis beside the grades it fell out of. The rows
        # are detection's, in F6.1's band order, with the interpretation's blocking
        # flag and one line merged in — the model never reorders and never adds.
        "gaps": {
            "gaps": [
                {
                    "requirement": gap.requirement,
                    "level": gap.level,
                    "must_have": gap.must_have,
                    "bullet_id": gap.bullet_id,
                    "bullet_text": gap.bullet_text,
                    "blocking": note.blocking,
                    "interpretation": note.interpretation,
                }
                for gap, note in zip(gaps, reading.notes, strict=True)
            ],
            "warning": {
                "text": reading.warning.text,
                "handling": reading.warning.handling,
            },
            "not_found": reading.not_found,
            "stories_used": len(stories),
        },
        # F6.1's disqualifiers, beside the score and never inside it (F5.5). The
        # verdict is `unverified` unless the stored education rows decide it.
        "disqualifiers": [
            {"requirement": entry.requirement, "verdict": entry.verdict}
            for entry in disqualifiers
        ],
        "gate": gate.to_dict() if gate is not None else None,
        # F5.2's recall is reported beside the score and never inside it: a recruiter's
        # query is a gate, like a disqualifier, not a percentage.
        "recall": recall.to_dict(),
        "score": score.to_dict(),
        "llm": _llm_section(calls, cost),
    }
    if track is not None:
        # Snapshotted like a citation: renaming the track must not rewrite what a
        # stored report says it was scored against.
        report["track"] = {"id": str(track.id), "name": track.name}

    return Analysis(
        report=report,
        prompt_versions={
            "jd_extract": JD_EXTRACTION.version,
            "evidence_grade": EVIDENCE_GRADING.version,
            "boolean_queries": BOOLEAN_RECALL.version,
            "gap_interpret": GAP_INTERPRETATION.version,
        },
        weights_version=score.weights_version,
        cost_usd=cost,
        jd_hash=jd.source_hash,
        title=(title or "").strip() or jd.title or None,
        company=(company or "").strip() or None,
        jd=jd,
        bullets=tuple(bullets),
        recall=recall,
    )
