"""Track recommendation (PRD F7.1): one posting, several tracks, one answer.

Two of an analysis's calls are about the posting alone — the extraction and the
recruiter's queries — so they are made once, by `analysis.prepare`, and the first
candidate's derivation is reused by the rest. Everything track-specific is the
analysis the app already runs, once per candidate: `analysis.score_track` is that
call, and a recommendation is a loop over it, not a second pipeline.

The ranking is arithmetic on the numbers the scorer produced. Nothing here calls a
model to decide something code can decide: the pre-ranking that picks which six
tracks are graded at all is a title + keywords computation, and the tie-break names
the sub-score that actually differed.
"""

import uuid
from collections.abc import Sequence
from dataclasses import replace
from decimal import Decimal

from sqlalchemy.orm import Session

from src.analysis import Analysis, llm_section, prepare, score_track
from src.documents import document_headline, track_document
from src.extract.client import CallOptions, Completion
from src.jd import StructuredJD
from src.models import Track
from src.normalize.text import fold
from src.roles import list_roles, role_title
from src.score.aggregate import SUB_SCORES
from src.score.keywords import keyword_context
from src.score.title import title_alignment
from src.tracks import list_tracks

# F7.1: "At most six active tracks are graded; with more, the six with the highest
# title + keywords sub-scores (no model call) are graded and the rest are listed as
# 'not graded'."
MAX_GRADED = 6

# F7.1: "when the margin is under 5 points, the report names the sub-score with the
# largest difference between the two".
CLOSE_MARGIN = 5

# The report page shows a sub-score as a percentage out of 100 (PRD 12.1), and the
# recommendation table is part of that page: same scale, same numbers.
SCALE = 100

# The two calls an analysis makes about the posting rather than about a track (F7.1):
# the extraction and the recruiter's queries. They are made once and read by every
# candidate, so they are shared, and both the total and the rows have to say so once.
SHARED_PURPOSES = ("jd_extract", "boolean_queries")


def _pre_rank(
    profile_id: uuid.UUID,
    session: Session,
    *,
    jd: StructuredJD,
    aliases: dict[str, str],
    tracks: Sequence[Track],
) -> list[tuple[float, Track]]:
    """(title + keywords, track) for every track, with no model call (F7.1).

    The two sub-scores that need no provider: the title is word overlap against the
    track's own headline and its titles, and the keywords are the same BM25 the
    report uses. They are the ranking F7.1 chose for "more tracks than we will grade"
    — cheap, and about the posting's own words.
    """
    roles = list_roles(profile_id, session, active_only=True)
    ranked: list[tuple[float, Track]] = []
    for track in tracks:
        document = track_document(profile_id, session, track, jd.language)
        title = title_alignment(
            jd,
            headline=document_headline(document),
            roles=[
                (role_title(role, jd.language)[0], role.start_date, role.end_date)
                for role in roles
            ],
            aliases=aliases,
        )
        keywords = keyword_context(jd, [unit.text for unit in document], aliases=aliases)
        ranked.append((title.value + keywords.value, track))
    return ranked


def candidate_tracks(
    profile_id: uuid.UUID,
    session: Session,
    *,
    jd: StructuredJD,
    aliases: dict[str, str],
) -> tuple[tuple[Track, ...], tuple[Track, ...]]:
    """(the tracks to grade, the tracks listed as not graded)."""
    tracks = list_tracks(profile_id, session, active_only=True)
    if len(tracks) <= MAX_GRADED:
        return tuple(tracks), ()
    ranked = sorted(
        _pre_rank(profile_id, session, jd=jd, aliases=aliases, tracks=tracks),
        key=lambda pair: (-pair[0], pair[1].name),
    )
    return (
        tuple(track for _, track in ranked[:MAX_GRADED]),
        tuple(track for _, track in ranked[MAX_GRADED:]),
    )


def _own_cost(analysis: Analysis) -> Decimal:
    """What this candidate alone cost: its calls, without the posting's own two.

    `Analysis.cost_usd` includes the extraction — one call, made once, whatever the
    number of candidates — so a row that carried it would count the same call once
    per track, exactly as the total used to (D.7.1). A row's number is its grading and
    its gap interpretation; the posting-level calls are reported once, by
    `recommendation_payload`'s `shared_cost_usd`.
    """
    return sum(
        (call.cost_usd for call in analysis.calls if call.purpose not in SHARED_PURPOSES),
        Decimal("0"),
    )


def _row(track: Track, analysis: Analysis) -> dict[str, object]:
    score = analysis.report["score"]
    return {
        "track_id": str(track.id),
        "name": track.name,
        "job_match": int(score["capped"]),
        "sub_scores": {
            name: round(float(sub["value"]) * SCALE)
            for name, sub in score["sub_scores"].items()
        },
        "cost_usd": str(_own_cost(analysis)),
        "applies_when": track.applies_when,
        "organisation_kind": track.organisation_kind,
        "chosen": False,
    }


def _differences(left: dict[str, object], right: dict[str, object]) -> dict[str, int]:
    left_scores = left.get("sub_scores") or {}
    right_scores = right.get("sub_scores") or {}
    return {
        name: abs(int(left_scores.get(name, 0)) - int(right_scores.get(name, 0)))
        for name in SUB_SCORES
    }


def _largest(differences: dict[str, int]) -> str:
    """The sub-score with the largest difference, ties resolved by F5.5's order."""
    return max(SUB_SCORES, key=lambda name: differences.get(name, 0))


def _organisation_track(company: str | None, rows: Sequence[dict[str, object]]) -> str | None:
    """The track whose `organisation_kind` the company field names (F7.1)."""
    if not company:
        return None
    haystack = fold(company)
    for row in rows:
        kind = row.get("organisation_kind")
        if kind and fold(str(kind)) in haystack:
            return str(row["name"])
    return None


def recommendation_payload(
    analyses: Sequence[tuple[Track, Analysis]],
    *,
    not_graded: Sequence[Track],
    company: str | None,
    cost_usd: Decimal,
) -> dict[str, object]:
    """F7.1's payload — the report's `recommendation`, and what the page's table shows.

    Public because it is the stored shape: the page renders it, the tests pin it, and
    the pair (candidates, tie-break) is the feature's whole answer.
    """
    rows = [_row(track, analysis) for track, analysis in analyses]
    # The rows add up to the total minus what the posting's own calls cost: counted
    # once here, never once per candidate (F7.1, PRD 7).
    shared_cost = cost_usd - sum((Decimal(str(row["cost_usd"])) for row in rows), Decimal("0"))
    ordered = sorted(rows, key=lambda row: (-int(row["job_match"]), str(row["name"])))
    if ordered:
        # The winner is the first highest — the analyses' own order breaks a tie, and
        # `sorted` keeps exactly that order among equal scores.
        ordered[0]["chosen"] = True
    winner = ordered[0] if ordered else None
    runner_up = ordered[1] if len(ordered) > 1 else None

    margin: int | None = None
    tie_break: dict[str, object] | None = None
    justification: dict[str, object] | None = None
    if winner is not None and runner_up is not None:
        margin = int(winner["job_match"]) - int(runner_up["job_match"])
        differences = _differences(winner, runner_up)
        if margin < CLOSE_MARGIN:
            best = _largest(differences)
            tie_break = {
                "sub_score": best,
                "delta": differences[best],
                "organisation_track": _organisation_track(company, [winner, runner_up]),
            }
        justification = {
            "track": winner["name"],
            "runner_up": runner_up["name"],
            "sub_score": _largest(differences),
            "delta": differences[_largest(differences)],
            "applies_when": winner["applies_when"],
        }
    elif winner is not None:
        justification = {
            "track": winner["name"],
            "runner_up": None,
            "sub_score": None,
            "delta": None,
            "applies_when": winner["applies_when"],
        }

    return {
        "candidates": ordered,
        "not_graded": [{"track_id": str(track.id), "name": track.name} for track in not_graded],
        "margin": margin,
        "tie_break": tie_break,
        "justification": justification,
        # `cost_usd` is the whole request; the rows are each candidate's own calls and
        # this is the posting's two, so rows + shared = cost, with nothing counted
        # twice (F7.1, PRD 7).
        "cost_usd": str(cost_usd),
        "shared_cost_usd": str(shared_cost),
    }


def recommend(
    profile_id: uuid.UUID,
    session: Session,
    *,
    jd_text: str,
    company: str | None = None,
    title: str | None = None,
    model: str | None = None,
    options: CallOptions | None = None,
) -> Analysis:
    """Score one posting against every candidate track and return the winner (F7.1).

    The winner's analysis is the one the caller stores, with the recommendation added
    to its report and the cost of *all* the calls it took to choose it: the same
    posting against six tracks is one request, and hiding five of its calls would
    make the ledger disagree with the page.

    With no active track at all there is nothing to recommend between, so this is an
    ordinary no-track analysis with an empty recommendation — a checked box is not an
    error, and the score is still the one the app has always produced.
    """
    prepared = prepare(profile_id, session, jd_text=jd_text, model=model, options=options)
    graded, not_graded = candidate_tracks(
        profile_id, session, jd=prepared.jd, aliases=prepared.aliases
    )

    analyses: list[tuple[Track, Analysis]] = []
    queries = None
    for track in graded:
        analysis = score_track(
            profile_id,
            session,
            jd_text=jd_text,
            prepared=prepared,
            company=company,
            title=title,
            model=model,
            options=options,
            track=track,
            queries=queries,
        )
        # F7.1: the recruiter's queries are about the posting, so the first track's
        # answer is every other track's too — one derivation for the whole request.
        queries = analysis.queries
        analyses.append((track, analysis))

    if not analyses:
        analysis = score_track(
            profile_id,
            session,
            jd_text=jd_text,
            prepared=prepared,
            company=company,
            title=title,
            model=model,
            options=options,
        )
        report = dict(analysis.report)
        report["recommendation"] = recommendation_payload(
            (), not_graded=not_graded, company=company, cost_usd=analysis.cost_usd
        )
        return replace(analysis, report=report)

    # The audit lists every call the request made, in the order they were made. The
    # extraction and the derivation are one call each — the same objects in every
    # candidate's list — so the merge counts them once, and the cost is the sum of
    # what it lists. Adding up the candidates' own `cost_usd` would count the shared
    # extraction once per graded track (D.7.1); a cached call costs $0 and is listed.
    calls: list[Completion] = []
    seen: set[int] = set()
    for _, analysis in analyses:
        for call in analysis.calls:
            if id(call) in seen:
                continue
            seen.add(id(call))
            calls.append(call)
    cost = sum((call.cost_usd for call in calls), Decimal("0"))

    chosen = max(
        range(len(analyses)),
        key=lambda index: (analyses[index][1].report["score"]["capped"], -index),
    )
    winner = analyses[chosen][1]
    report = dict(winner.report)
    report["recommendation"] = recommendation_payload(
        analyses, not_graded=not_graded, company=company, cost_usd=cost
    )
    report["llm"] = llm_section(calls, cost)
    return replace(winner, report=report, cost_usd=cost)
