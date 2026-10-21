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

import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from functools import partial
from typing import cast

from sqlalchemy.orm import Session

from src.advice import edit_advice
from src.cv_context import CvContext, cv_document
from src.documents import (
    DocumentUnit,
    document_bullets,
    document_headline,
    document_skills_list,
    document_summary,
    master_data,
    track_document,
)
from src.education import list_educations
from src.extract.boolean import BooleanQuery, BooleanQuerySet, derive_boolean_queries
from src.extract.client import (
    CallOptions,
    Completion,
    NoModelConfigured,
    ProviderUnavailable,
    StructuredOutputError,
)
from src.extract.gaps import GapInput, GapViolation, interpret_gaps
from src.extract.grading import grade_evidence
from src.extract.jd import extract_jd
from src.extract.prompts import (
    BOOLEAN_RECALL_V2,
    EVIDENCE_GRADING_V4,
    GAP_INTERPRETATION,
    JD_EXTRACTION_V3,
)
from src.jd import StructuredJD
from src.models import Bullet, Profile, Role, Track
from src.normalize.vocabulary import match_text
from src.parse.gate import ParseReport
from src.resumes import source_document_for_track
from src.roles import list_roles, role_title
from src.score.aggregate import SubScore, aggregate
from src.score.ceiling import compute_ceiling, requirement_notes
from src.score.evidence import Level, evidence_coverage
from src.score.experience import CitedLevel, RoleSpan, relevant_experience_score
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
    # Every call this analysis made, for F7.1's recommendation: one posting scored
    # against six tracks shows what all of them cost, not only the winner's.
    calls: tuple[Completion, ...] = ()
    # The recruiter's derivation this analysis scored against — F7.1 reads it off the
    # first track and hands the same answer to the rest.
    queries: BooleanQuerySet | None = None


def llm_section(
    calls: Sequence[Completion], cost: Decimal, *, wall_ms: int | None = None
) -> dict[str, object]:
    """The cost ledger for this analysis, as it will be shown on the report page.

    F12.4: every call names the milliseconds it took (0 for a cache hit, which made
    no request), and `wall_ms` is what the whole analysis took — less than the sum of
    the calls once two of them run beside each other.
    """
    return {
        "cost_usd": str(cost),
        "calls": [
            {
                "purpose": call.purpose,
                "prompt_version": call.prompt_version,
                "model": call.model,
                "reasoning_effort": call.reasoning_effort,
                "cached": call.cached,
                "prompt_tokens": call.prompt_tokens,
                "completion_tokens": call.completion_tokens,
                "cost_usd": str(call.cost_usd),
                "fingerprint": call.fingerprint,
                "ledger_error": call.ledger_error,
                "latency_ms": call.latency_ms,
            }
            for call in calls
        ],
        "wall_ms": wall_ms,
    }


def _recall_payload(recall: RecallReport, queries: Sequence[BooleanQuery]) -> dict[str, object]:
    """The evaluator's report, plus the recruiter's spelling of each query (A.9.2).

    `src.search.evaluate` decides pass/fail over the tree and never sees the flat
    query, so the two halves meet here, in the order the queries were derived. A report
    stored before this existed has no `query_text`, and its entries keep none.
    """
    payload = recall.to_dict()
    entries = cast("list[dict[str, object]]", payload["queries"])
    # `evaluate` reports no queries when there was nothing to search, so the entries
    # can legitimately be the shorter side here.
    for entry, query in zip(entries, queries, strict=False):
        entry["query_text"] = query.query_text
        # F10.3: the tree itself, so an attempt re-evaluates the same queries against
        # the file at no cost — re-deriving them would be a second model call.
        entry["all_of"] = [list(group) for group in query.all_of]
        entry["none_of"] = list(query.none_of)
    return payload


@dataclass(frozen=True)
class Preparation:
    """What every track of one posting shares (PRD F7.1): the extraction.

    A recommendation scores one posting against several tracks, and two of its calls
    are about the posting alone: the extraction, made here, and the recruiter's
    queries, derived from the posting's text beside it (F12.2). Both travel here so
    that no caller derives them a second time, and `score_track` records the calls
    once, in the order the report has always listed them.
    """

    jd: StructuredJD
    extraction: Completion
    aliases: dict[str, str]
    vocabulary_hash: str
    today: date
    # F12.2: the recruiter's queries. None only when the caller asked for the
    # extraction alone (`derive_queries=False`) or the preparation came from a stored
    # report that predates the query trees; `score_track` then derives them as before.
    queries: BooleanQuerySet | None = None
    recall_call: Completion | None = None
    # F12.4: when this preparation started, so the report can say how long the calls
    # took from the first read to the last one. Never stored as such.
    started: float = field(default_factory=time.perf_counter)


def _in_own_session(bind, work: Callable[[Session], object]) -> object:
    """One provider call on a session of the calling thread's own (F12.2).

    A `Session` is not shared across threads, and `complete_json` refuses to run
    inside a transaction the caller owns: this session starts empty, commits what the
    call wrote (its unmapped-term notes) and closes here, in the same thread.
    """
    with Session(bind=bind) as worker:
        try:
            value = work(worker)
        except Exception:
            worker.rollback()
            raise
        worker.commit()
        return value


def prepare(
    profile_id: uuid.UUID,
    session: Session,
    *,
    jd_text: str,
    model: str | None = None,
    options: CallOptions | None = None,
    derive_queries: bool = True,
) -> Preparation:
    """Extract the posting and derive the recruiter's queries, once (F7.1, F12.2).

    Transaction boundaries are the unit of work's: the reads end before each provider
    call (`client.complete_json` refuses to run inside a transaction). The queries
    need only the posting's text, so they run while the posting is extracted — two
    threads, two sessions, one wall time instead of two.

    `derive_queries=False` is for the caller that only wants the posting: "Proponer
    línea" (F11.6) ranks tracks on it and has never paid for a derivation.
    """
    started = time.perf_counter()
    profile = session.get(Profile, profile_id)
    if profile is None:
        raise RuntimeError("an analysis needs a profile that exists")
    aliases = alias_map(session)
    # The vocabulary this report was scored against (F3.1), read with the alias map
    # it produced: a vocabulary change moves scores, so two reports must be able to
    # say whether they saw the same words before the scorer is blamed.
    vocab_hash = vocabulary_hash(session)
    today = date.today()

    session.commit()
    bind = session.get_bind()
    jd_work = partial(extract_jd, text=jd_text, model=model, options=options)
    queries_work = partial(
        derive_boolean_queries, jd_text=jd_text, model=model, options=options
    )
    jd_failure: Exception | None = None
    queries_failure: Exception | None = None
    queries: BooleanQuerySet | None = None
    recall_call: Completion | None = None
    with ThreadPoolExecutor(max_workers=2) as pool:
        jd_future = pool.submit(_in_own_session, bind, jd_work)
        queries_future = (
            pool.submit(_in_own_session, bind, queries_work) if derive_queries else None
        )
        # Both results are awaited even when one call fails: the other is a paid
        # call, and leaving it running would orphan its answer and its ledger row.
        try:
            jd, extraction = cast("tuple[StructuredJD, Completion]", jd_future.result())
        except Exception as exc:
            jd_failure = exc
        if queries_future is not None:
            try:
                queries, recall_call = cast(
                    "tuple[BooleanQuerySet, Completion]", queries_future.result()
                )
            except Exception as exc:
                queries_failure = exc
    # The extraction's failure is the one that propagates first, as when the calls
    # ran one after another; either exception is re-raised unchanged.
    if jd_failure is not None:
        raise jd_failure
    if queries_failure is not None:
        raise queries_failure
    return Preparation(
        jd=jd,
        extraction=extraction,
        aliases=aliases,
        vocabulary_hash=vocab_hash,
        today=today,
        queries=queries,
        recall_call=recall_call,
        started=started,
    )


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
    notes: str = "inline",
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

    The two halves are named so that F7.1's recommendation can run the first once and
    the second per track; a single analysis is still exactly the same two steps in the
    same order, which is what keeps every stored report comparable with the ones this
    produced before the split.
    """
    prepared = prepare(profile_id, session, jd_text=jd_text, model=model, options=options)
    return score_track(
        profile_id,
        session,
        jd_text=jd_text,
        prepared=prepared,
        company=company,
        title=title,
        gate=gate,
        model=model,
        options=options,
        track=track,
        notes=notes,
    )


def score_track(
    profile_id: uuid.UUID,
    session: Session,
    *,
    jd_text: str,
    prepared: Preparation,
    company: str | None = None,
    title: str | None = None,
    gate: ParseReport | None = None,
    model: str | None = None,
    options: CallOptions | None = None,
    track: Track | None = None,
    queries: BooleanQuerySet | None = None,
    bullets: Sequence[Bullet] | None = None,
    document: Sequence[DocumentUnit] | None = None,
    notes: str = "inline",
    extra_roles: Sequence[Role] = (),
    cv: CvContext | None = None,
) -> Analysis:
    """One track's analysis of a prepared posting: document, grading, score, gaps.

    `queries` is the recruiter's derivation when somebody else already made it — F7.1
    derives it once and hands the same answer to every candidate track. Without one,
    the preparation's own is used (F12.2); only a preparation that carries none of
    them derives it here, after the grading call, where an analysis always did.

    `bullets` and `document` override the evidence and the text read (F10's ephemeral
    track, A4): an attempt scores a file instead of a track, through this same path, so
    the two can never score differently. `notes` says when the prose about the gaps is
    paid for (F12.3): `"inline"` in this run; `"deferred"` for the interface's analysis,
    which is stored with `gaps.notes_status = "pending"` and filled by the report's own
    POST; `"none"` for an attempt, which detects gaps and never interprets them.
    `extra_roles` are the file's jobs that match no master role (a transient `Role`,
    never stored): their bullets' citations count in Experience like any other role's.
    The analysis passes none.

    `cv` marks the file as a stored CV (F11): the readability cap is the file's own gate
    and is never borrowed from the track's latest upload, the F4.2 alert compares the
    file's language with the posting's, the ceiling's fingerprint reads the master
    bullets the file carries, and the report records which CV it scored. Scoring itself
    is unchanged — what is scored is the file.
    """
    profile = session.get(Profile, profile_id)
    if profile is None:
        raise RuntimeError("an analysis needs a profile that exists")
    if notes not in ("inline", "deferred", "none"):
        raise ValueError(f"unknown notes mode {notes!r}")

    jd = prepared.jd
    roles = list_roles(profile_id, session, active_only=True)
    # The evidence and the document are one decision (F5.5.1): the same bullets,
    # read through the same rule — active, under an active role, the track's
    # selection or every one of them.
    if bullets is None:
        bullets = document_bullets(profile_id, session, track)
    if track is not None and cv is None:
        # F5.1: a track built from an upload is capped by the document that produced
        # it. No source document — or no track — means no gate and no cap, which is
        # also what an analysis against the master database has always been. A CV
        # carries its own findings (F11.2): another upload's never cap it.
        if gate is None:
            source = source_document_for_track(profile_id, session, track.id)
            if source is not None and source.gate:
                gate = ParseReport.from_dict(source.gate)
    aliases = prepared.aliases
    vocab_hash = prepared.vocabulary_hash
    today = prepared.today

    # The document as one reader sees it, in the posting's language (F4.1): what the
    # keyword scan runs over, what the title sub-score reads its headline from, and
    # where a citation's snapshot comes from. The reads end before the next call.
    if document is None:
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
    # F12.2: the derivation travels with the preparation, made beside the extraction;
    # F7.1 passes the first track's answer to the rest; an attempt passes the stored
    # report's. Only a preparation that has no queries at all — one built from a
    # report that predates the trees — derives them here, after the grading call.
    recall_call: Completion | None = None
    if queries is None:
        queries = prepared.queries
        recall_call = prepared.recall_call
    if queries is None:
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
            # F4.2: the title a reader of this posting sees — the posting's language,
            # the other one as the fallback. `role.title` stays what it was, the
            # primary language's title.
            roles=[
                (role_title(role, jd.language)[0], role.start_date, role.end_date)
                for role in roles
            ],
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
        "experience": relevant_experience_score(
            jd.years_required,
            [
                RoleSpan(
                    id=str(role.id),
                    title=role.title,
                    start_date=role.start_date,
                    end_date=role.end_date,
                    bullet_ids=tuple(
                        str(bullet.id) for bullet in bullets if bullet.role_id == role.id
                    ),
                )
                for role in [*roles, *extra_roles]
            ],
            [
                CitedLevel(
                    level=entry.level,
                    basis=entry.basis,
                    bullet_id=entry.evidence_id,
                    text=entry.requirement,
                )
                for entry in grading.levels
            ],
            [
                # A described task is the thing itself, never a transfer of it.
                CitedLevel(
                    level=entry.level,
                    basis="direct",
                    bullet_id=entry.evidence_id,
                    text=entry.task,
                )
                for entry in grading.task_levels
            ],
            split=W4.experience_split,
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
    # F4.2 (A.9.3): what the document had to read in the other language. A real screen
    # matches the words in the file, so a fallback is worth saying out loud — and the
    # alert is not part of the score, like every other alert here. Role titles carry a
    # language each since 2026-09-27, so they are counted beside the bullets.
    title_units = [unit for unit in document if unit.kind == "role"]
    language: dict[str, object] = {
        "posting": jd.language,
        "other": "en" if jd.language == "es" else "es",
        "fallback_headline": any(unit.fallback for unit in document if unit.kind == "headline"),
        "fallback_summary": any(unit.fallback for unit in document if unit.kind == "summary"),
        "fallback_bullets": sum(1 for unit in bullet_units.values() if unit.fallback),
        "bullets": len(bullet_units),
        "fallback_titles": sum(1 for unit in title_units if unit.fallback),
        "titles": len(title_units),
    }
    if cv is not None:
        # F4.2 on a file (STOP 0, decision 1): the recruiter reads the CV's own words,
        # so the alert compares the file's language with the posting's. A file in the
        # posting's language raises none; one in the other language is entirely
        # "the other language", and the counts say how much of it there is.
        wrong = cv.language != jd.language
        roles_in_file = len(cv.role_matching)
        language.update(
            {
                "file": cv.language,
                "fallback_headline": wrong and document_headline(document) is not None,
                "fallback_summary": wrong and summary_unit is not None,
                "fallback_bullets": len(bullet_units) if wrong else 0,
                "titles": roles_in_file,
                "fallback_titles": roles_in_file if wrong else 0,
            }
        )
    if (
        language["fallback_headline"]
        or language["fallback_summary"]
        or language["fallback_bullets"]
        or language["fallback_titles"]
    ):
        alerts.append({"kind": "language_mismatch", **language})
    stories = list_stories(profile_id, session)
    # The reads above end before the provider call starts, like every other call here.
    session.commit()
    # F10.3: an attempt detects its gaps but does not pay for the prose about them —
    # `notes` is "none" there, and the report carries the bands with empty wording.
    # F12.3: the interface's analysis stores the bands the same way and its report's own
    # POST pays for the prose, so the user reads the score before the notes exist.
    reading = None
    if notes == "inline":
        reading = interpret_gaps(
            session,
            [
                GapInput(gap.requirement, gap.level, gap.must_have, gap.bullet_text)
                for gap in gaps
            ],
            jd,
            standing_risks=profile.standing_risks,
            stories=stories,
            language=jd.language,
            known_names=[profile.display_name] if profile.display_name else None,
            model=model,
            options=options,
        )
    gap_notes: list[object] = list(reading.notes) if reading is not None else [None] * len(gaps)

    calls = (
        prepared.extraction,
        *grading.calls,
        *([recall_call] if recall_call is not None else []),
        *([*reading.calls] if reading is not None else []),
    )
    cost = sum((call.cost_usd for call in calls), Decimal("0"))

    gaps_block: dict[str, object] = {
        "gaps": [
            {
                "requirement": gap.requirement,
                "level": gap.level,
                "must_have": gap.must_have,
                "bullet_id": gap.bullet_id,
                "bullet_text": gap.bullet_text,
                "blocking": bool(getattr(note, "blocking", False)),
                "interpretation": str(getattr(note, "interpretation", "")),
            }
            for gap, note in zip(gaps, gap_notes, strict=True)
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
            "text": reading.warning.text if reading is not None else "",
            "handling": reading.warning.handling if reading is not None else "",
        },
        "alerts": alerts,
        "not_found": reading.not_found if reading is not None else "",
        "stories_used": len(stories),
    }
    if notes == "deferred":
        # F12.3: the report is stored as soon as the score exists; the page's own POST
        # fills the notes in and moves this to "ready" (or "failed", which offers a
        # retry). A report stored before F12 has its notes and no status at all.
        gaps_block["notes_status"] = "pending"

    report: dict[str, object] = {
        "jd": jd.model_dump(mode="json"),
        # F4.2 (A.9.3): what the document read, and how much of it had to fall back to
        # the other language — the counts the language alert names.
        "language": language,
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
        "gaps": gaps_block,
        # F6.1's disqualifiers, beside the score and never inside it (F5.5). The
        # verdict is `unverified` unless the stored education rows decide it.
        "disqualifiers": [
            {"requirement": entry.requirement, "verdict": entry.verdict}
            for entry in disqualifiers
        ],
        "gate": gate.to_dict() if gate is not None else None,
        # F5.2's recall is reported beside the score and never inside it: a recruiter's
        # query is a gate, like a disqualifier, not a percentage.
        "recall": _recall_payload(recall, queries.queries),
        "score": score.to_dict(),
        # F12.4: from the preparation's first read to this line — what the user waited
        # for, never the sum of the calls (the first two overlap).
        "llm": llm_section(
            calls,
            cost,
            wall_ms=round((time.perf_counter() - prepared.started) * 1000),
        ),
    }
    if cv is not None:
        # F11.3: which file this is, and how it was read (F10.3 step 3's snapshots).
        report["cv"] = cv.header()
        report["bullets"] = [dict(row) for row in cv.snapshots]
        report["role_matching"] = [dict(row) for row in cv.role_matching]
    # F7.2: the six edit rules, computed from the report just built and the user's own
    # rows — deterministic, free, and made no provider call, so this runs after the
    # last one. A stored report keeps the items; the sentences are the page's.
    report["advice"] = [
        item.to_dict()
        for item in edit_advice(profile_id, session, report=report, track=track)
    ]
    if track is not None:
        # Snapshotted like a citation: renaming the track must not rewrite what a
        # stored report says it was scored against.
        report["track"] = {"id": str(track.id), "name": track.name}
    # F10.2/A10: the ceiling from the user's own material, computed here so the report
    # carries it. The page recomputes it only when the fingerprint below has moved. An
    # attempt replaces this with the analysis's own ceiling (F10.3, `run_pipeline`).
    master = master_data(profile_id, session, track)
    report["ceiling"] = compute_ceiling(
        jd,
        report=report,
        document_texts=[unit.text for unit in document],
        master=master,
        aliases=aliases,
        # A CV's fingerprint reads the master ids the file carries: a temporary bullet
        # gets a new id every run and would make every view look "recomputed".
        track_bullet_ids=(
            list(cv.matched_ids)
            if cv is not None
            else [
                unit.source_id
                for unit in document
                if unit.kind == "bullet" and unit.source_id is not None
            ]
        ),
        today=today,
    )
    if cv is not None:
        # F11.5: what the user's material outside this CV would raise, by the Skills
        # ceiling's own rule. Beside the score, never in it.
        report["requirement_notes"] = requirement_notes(
            cast("list[dict[str, object]]", report["grades"]),
            master,
            aliases,
            cv.represented_ids,
            jd.language,
        )

    return Analysis(
        report=report,
        prompt_versions={
            "jd_extract": JD_EXTRACTION_V3.version,
            "evidence_grade": EVIDENCE_GRADING_V4.version,
            "boolean_queries": BOOLEAN_RECALL_V2.version,
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
        calls=calls,
        queries=queries,
    )


def interpret_stored_gaps(
    profile_id: uuid.UUID,
    session: Session,
    report: Mapping[str, object],
) -> dict[str, object] | None:
    """Fill a stored report's deferred gap notes, as its analysis would have (F12.3).

    Returns the `gaps` block to store, or None when there is nothing to pay for: the
    notes are already there (`"ready"`), or the report is one no POST ever fills — an
    attempt's, which never interpreted its gaps (F10.3), or one stored before F12,
    which keeps the notes it was saved with.

    The call is the one `score_track` makes inline, from the same stored rows, the same
    profile material and the same prompt version, so its content hash is the one the
    analysis would have written: a second analysis of the same posting and CV pays for
    the notes once (F12.6.3). A provider or schema failure comes back as `"failed"` and
    the page offers a retry; it is never raised at the caller, which has no better
    answer than the retry the block already names.
    """
    gaps_block = report.get("gaps")
    if not isinstance(gaps_block, Mapping):
        return None
    if gaps_block.get("notes_status") not in ("pending", "failed"):
        return None
    profile = session.get(Profile, profile_id)
    if profile is None:
        raise RuntimeError("an analysis needs a profile that exists")
    rows = [dict(row) for row in gaps_block.get("gaps") or []]
    inputs = [
        GapInput(
            str(row.get("requirement") or ""),
            int(row.get("level") or 0),
            bool(row.get("must_have")),
            cast("str | None", row.get("bullet_text")),
        )
        for row in rows
    ]
    jd = StructuredJD(**cast("dict[str, object]", report["jd"]))
    stories = list_stories(profile_id, session)
    # The reads end before the provider call, as everywhere else.
    session.commit()
    block: dict[str, object] = {**gaps_block, "gaps": rows}
    try:
        reading = interpret_gaps(
            session,
            inputs,
            jd,
            standing_risks=profile.standing_risks,
            stories=stories,
            language=jd.language,
            known_names=[profile.display_name] if profile.display_name else None,
            options=CallOptions(profile_id=profile_id),
        )
    except (NoModelConfigured, ProviderUnavailable, StructuredOutputError, GapViolation):
        block["notes_status"] = "failed"
        return block
    for row, note in zip(rows, reading.notes, strict=True):
        row["blocking"] = note.blocking
        row["interpretation"] = note.interpretation
    block["warning"] = {"text": reading.warning.text, "handling": reading.warning.handling}
    block["not_found"] = reading.not_found
    block["notes_status"] = "ready"
    return block


def preparation_from_report(
    report: Mapping[str, object],
    session: Session,
    *,
    extraction,
) -> Preparation:
    """Reuse a stored report's posting, without extracting it again (F10.3).

    `extraction` is the call that *did* happen — an attempt's own résumé extraction —
    so the report's ledger names what was paid for. The recruiter's queries travel
    too, with no call of their own: the derivation was paid for by the analysis.
    """
    jd = StructuredJD(**report["jd"])  # type: ignore[arg-type]
    return Preparation(
        jd=jd,
        extraction=extraction,
        aliases=alias_map(session),
        vocabulary_hash=vocabulary_hash(session),
        today=date.today(),
        queries=queries_from_report(report),
    )


def queries_from_report(report: Mapping[str, object]) -> BooleanQuerySet | None:
    """The recruiter's queries a stored report carries, or None when it predates them.

    F10.3 reuses the analysis's queries at no cost; a report stored before the trees
    were recorded returns None, and the caller derives them (a call) as before.
    """
    recall = report.get("recall") or {}
    rows = recall.get("queries") if isinstance(recall, Mapping) else None
    if not rows:
        return None
    queries: list[BooleanQuery] = []
    for row in rows:
        if not isinstance(row, Mapping) or "all_of" not in row:
            return None
        queries.append(
            BooleanQuery(
                label=str(row.get("label") or ""),
                all_of=[list(group) for group in row["all_of"]],
                none_of=[str(term) for term in (row.get("none_of") or [])],
            )
        )
    return BooleanQuerySet(queries=queries)


def ceiling_for_report(
    profile_id: uuid.UUID,
    session: Session,
    *,
    report: dict[str, object],
    track: Track | None,
    today: date | None = None,
) -> dict[str, object] | None:
    """Recompute a stored report's ceiling from the current master data (A10).

    None when the report predates the four `w4` sub-scores, so the page renders no
    ceiling rather than a wrong one. Deterministic and offline: it reads the database
    and calls no provider.
    """
    score = report.get("score")
    sub_scores = (score or {}).get("sub_scores") if isinstance(score, Mapping) else None
    jd_dict = report.get("jd")
    if not isinstance(sub_scores, Mapping) or not isinstance(jd_dict, Mapping):
        return None
    if not {"skills", "experience", "title", "keywords"} <= set(sub_scores):
        return None
    jd = StructuredJD(**jd_dict)
    if report.get("cv") is not None:
        # F11.4: a CV analysis's ceiling is the whole master against the file, which is
        # rebuilt from the stored draft. A file that is gone or changed has no ceiling
        # to recompute, and the caller keeps the stored one.
        rebuilt = cv_document(profile_id, session, report=report, track=track, lang=jd.language)
        if rebuilt is None:
            return None
        document, matched_ids = rebuilt
    else:
        document = track_document(profile_id, session, track, jd.language)
        matched_ids = [
            unit.source_id
            for unit in document
            if unit.kind == "bullet" and unit.source_id is not None
        ]
    return compute_ceiling(
        jd,
        report=report,
        document_texts=[unit.text for unit in document],
        master=master_data(profile_id, session, track),
        aliases=alias_map(session),
        track_bullet_ids=matched_ids,
        today=today or date.today(),
    )


def shown_ceiling(
    profile_id: uuid.UUID,
    session: Session,
    *,
    report: dict[str, object],
    track: Track | None,
) -> tuple[dict[str, object] | None, bool]:
    """The analysis's ceiling as its page shows it, and whether it was recomputed (A10).

    The stored ceiling stands while its fingerprint matches the master data now; once
    that moved, the current one replaces it. An attempt reads this too (F10.2/F10.3): the
    ceiling is the analysis's, never one derived from the file's own grades.
    """
    stored = report.get("ceiling")
    current = ceiling_for_report(profile_id, session, report=report, track=track)
    if current is None and report.get("cv") is not None and isinstance(stored, dict):
        return stored, False  # the CV is gone or was edited: what was computed stands
    if isinstance(stored, dict) and current and stored.get("fingerprint") == current.get(
        "fingerprint"
    ):
        return stored, False
    return current, current is not None
