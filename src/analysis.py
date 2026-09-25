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

from src.documents import (
    DocumentUnit,
    document_bullets,
    document_headline,
    document_skills_list,
    document_summary,
    track_document,
)
from src.education import list_educations
from src.extract.boolean import derive_boolean_queries
from src.extract.client import CallOptions, Completion
from src.extract.gaps import GapInput, interpret_gaps
from src.extract.grading import grade_evidence
from src.extract.jd import extract_jd
from src.extract.prompts import (
    BOOLEAN_RECALL,
    EVIDENCE_GRADING_V4,
    GAP_INTERPRETATION,
    JD_EXTRACTION,
)
from src.jd import StructuredJD
from src.models import Bullet, Profile, Track
from src.normalize.vocabulary import match_text
from src.parse.gate import ParseReport
from src.resumes import source_document_for_track
from src.roles import list_roles
from src.score.aggregate import SubScore, aggregate
from src.score.evidence import Level, evidence_coverage
from src.score.experience import experience_score
from src.score.gaps import Graded, detect_gaps, disqualifier_verdicts, location_requirements
from src.score.keywords import keyword_context
from src.score.title import title_alignment
from src.score.weights import W4
from src.search.boolean import RecallReport, evaluate
from src.search.sources import searchable_units
from src.stories import list_stories
from src.vocabulary import alias_map, vocabulary_hash


@dataclass(frozen=True)
class Analysis:
    """What one analysis produced, before it is written to `applications` (F8).

    `jd`, `bullets` and `document` are the inputs the judge saw; the model-selection
    experiment re-runs the judge against them to measure stability without
    re-running extraction.
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
    document: tuple[DocumentUnit, ...] = ()
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
    # The evidence and the document are one decision (F5.5.1): the same bullets,
    # read through the same rule — active, under an active role, the track's
    # selection or every one of them.
    bullets = document_bullets(profile_id, session, track)
    if track is not None:
        # F5.1: a track built from an upload is capped by the document that produced
        # it. No source document — or no track — means no gate and no cap, which is
        # also what an analysis against the master database has always been.
        if gate is None:
            source = source_document_for_track(profile_id, session, track.id)
            if source is not None and source.gate:
                gate = ParseReport.from_dict(source.gate)
    aliases = alias_map(session)
    # The vocabulary this report was scored against (F3.1), read with the alias map
    # it produced: a vocabulary change moves scores, so two reports must be able to
    # say whether they saw the same words before the scorer is blamed.
    vocab_hash = vocabulary_hash(session)
    today = date.today()

    # Transaction boundaries are the unit of work's: release the profile, role and
    # bullet reads before each provider call (client.complete_json refuses to run
    # inside a transaction, which is the connection the database kills).
    session.commit()
    jd, extraction = extract_jd(session, jd_text, model=model, options=options)
    # The extraction just wrote its unmapped-term notes; the grading call must not
    # carry them across the network either.
    session.commit()
    # The document as one reader sees it, in the posting's language (F4.1): what the
    # keyword scan runs over, what the title sub-score reads its headline from, and
    # where a citation's snapshot comes from. Only the extraction can say which
    # language that is, so it is built here and read before the next call.
    document = track_document(profile_id, session, track, jd.language)
    session.commit()
    grading = grade_evidence(
        session,
        jd,
        bullets,
        basis_credit=W4.basis_credit,
        summary_text=document_summary(document),
        skills_text=document_skills_list(document),
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
        searchable_units(document),
        alias_map(session),
    )

    sub_scores: dict[str, SubScore] = {
        "title": title_alignment(
            jd,
            headline=document_headline(document),
            roles=[(role.title, role.start_date, role.end_date) for role in roles],
            aliases=aliases,
        ),
        "skills": evidence_coverage(
            [
                Level(entry.requirement, entry.level, entry.must_have, entry.basis)
                for entry in grading.levels
            ],
            basis_credit=W4.basis_credit,
        ),
        "keywords": keyword_context(jd, [unit.text for unit in document], aliases=aliases),
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
    score = aggregate(sub_scores, W4, gate=gate)

    # The snapshot (F5.4): what each citation showed, in the language it was shown
    # in, taken from the same document the judge read. Old report rows call this
    # `bullet_text` whatever the source; the row's `source` names which it was.
    bullet_units = {unit.source_id: unit for unit in document if unit.kind == "bullet"}
    summary_unit = next((unit for unit in document if unit.kind == "summary"), None)
    skills_line = document_skills_list(document)

    def citation(entry) -> tuple[str | None, bool]:
        """(the cited text, whether it is a language fallback) for one requirement."""
        if entry.source == "summary":
            return (summary_unit.text, summary_unit.fallback) if summary_unit else (None, False)
        if entry.source == "skills_list":
            return skills_line, False
        unit = bullet_units.get(entry.evidence_id or "")
        return (unit.text, unit.fallback) if unit is not None else (None, False)

    grades: list[dict[str, object]] = []
    graded_inputs: list[Graded] = []
    family_candidates: list[dict[str, object]] = []
    for entry in grading.levels:
        cited_text, cited_fallback = citation(entry)
        grades.append(
            {
                "requirement": entry.requirement,
                "must_have": entry.must_have,
                "level": entry.level,
                "basis": entry.basis,
                "source": entry.source,
                "bullet_id": entry.evidence_id,
                "bullet_text": cited_text,
                "transfer_reason": entry.transfer_reason,
                "clamped": entry.clamped,
                "downgraded": entry.downgraded,
                "inferred": entry.inferred,
                "fallback": cited_fallback,
            }
        )
        if entry.downgraded:
            # F5.5.2's family review list: every equivalence the data refused,
            # with the skills the citation actually named. These pairs are what
            # `scripts/vocabulary.py families-review` puts in front of the
            # operator, so a frequently claimed equivalence can become a family.
            family_candidates.append(
                {
                    "requirement": entry.requirement,
                    "cited": ", ".join(sorted(match_text(cited_text or "", aliases))),
                }
            )
        graded_inputs.append(
            Graded(
                requirement=entry.requirement,
                level=entry.level,
                must_have=entry.must_have,
                bullet_id=entry.evidence_id,
                bullet_text=cited_text,
                basis=entry.basis,
                transfer_reason=entry.transfer_reason,
            )
        )

    # N5 (PRD F6, F6.1): the gaps fall out of the grading above — deterministic and
    # free — and one call interprets them. The disqualifier verdicts are deterministic
    # too: only what the stored education rows decide, `unverified` otherwise. F6.1's
    # fifth band is listed, not interpreted: it is not a gap, and its `transfer_reason`
    # is already the argument to prepare.
    detected = detect_gaps(graded_inputs, must_have=jd.must_have, nice_to_have=jd.nice_to_have)
    gaps = [gap for gap in detected if not gap.covered_by_transfer]
    covered = [gap for gap in detected if gap.covered_by_transfer]
    disqualifiers = disqualifier_verdicts(
        jd.hard_requirements, has_education=bool(list_educations(profile_id, session))
    )
    # F6.1's alerts beside the single warning, never in the score: a seniority
    # mismatch in either direction from the Title detail (F5.5.2) — above (salary,
    # retention) and below (the posting asks for a level the current title does not
    # name) — and the hard requirements that concern location, with their verdicts.
    alerts: list[dict[str, object]] = []
    title_detail = sub_scores["title"].detail
    if title_detail.get("seniority_above"):
        # The key is `over_seniority` because stored reports use it.
        alerts.append({"kind": "over_seniority"})
    if title_detail.get("seniority_below"):
        alerts.append(
            {
                "kind": "under_seniority",
                "jd_rung": title_detail["jd_rung"],
                "user_rung": title_detail["user_rung"],
            }
        )
    alerts.extend(
        {"kind": "location", "requirement": entry.requirement, "verdict": entry.verdict}
        for entry in location_requirements(disqualifiers)
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
        # F3.1: the vocabulary the run read, beside the score it produced.
        "vocabulary_hash": vocab_hash,
        # `bullet_text` is the citation's snapshot under its historical name — a
        # bullet's text, a summary's text or the skills list, as the row's `source`
        # says. Snapshotted so the report still shows what was graded after the
        # source is edited or deactivated.
        "grades": grades,
        "grading_note": grading.note,
        # F5.5.2: the equivalences the family data refused, for review (B.6's
        # page and `scripts/vocabulary.py families-review` read this list).
        "family_candidates": family_candidates,
        # N5 (PRD F6): the gap analysis beside the grades it fell out of. The rows
        # are detection's, in F6.1's band order, with the interpretation's blocking
        # flag and one line merged in — the model never reorders and never adds.
        # F6.1's fifth band and its alerts sit beside them, never inside the list.
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
            "covered_by_transfer": [
                {
                    "requirement": gap.requirement,
                    "level": gap.level,
                    "must_have": gap.must_have,
                    "bullet_id": gap.bullet_id,
                    "bullet_text": gap.bullet_text,
                    "transfer_reason": gap.transfer_reason,
                }
                for gap in covered
            ],
            "warning": {
                "text": reading.warning.text,
                "handling": reading.warning.handling,
            },
            "alerts": alerts,
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
            "evidence_grade": EVIDENCE_GRADING_V4.version,
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
        document=tuple(document),
        recall=recall,
    )
