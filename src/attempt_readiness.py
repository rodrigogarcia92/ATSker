"""Readiness (PRD F10.6, as amended by A1): "CV optimizado", or what is missing.

Deterministic and free: every condition is read off the attempt's own report, so the
checklist and the numbers it names can never disagree, and nothing here calls a model.
The F7.4 condition is **omitted** until F7.4 exists (A1); the rest of the spec's list is
checked in the order it states them.

The personal target lives on the application (`applications.target_match`, migration
`0015`), never on the attempt: it is the user's own stopping point for that posting and
survives later attempts. It is capped at the ceiling's high end, because a target above
what the material allows is not attainable and would read as a promise ATSker cannot
keep.
"""

from collections.abc import Mapping

from src.score.weights import STABILITY_BAND

# F7.2's rules 1-4: the edits that are still worth making. The title and language
# rules (5-7) are advisory, not readiness conditions (F10.6).
OPEN_ADVICE_KINDS = ("promote_bullet", "add_bullet", "surface_skill", "fix_query")

# The recruiter searches F10.6 names. `strict` is deliberately absent: a narrow query
# that fails is information, not a blocker.
REQUIRED_SEARCH_LABELS = ("broad", "core")


def cap_target(target: int | None, ceiling_high: int | None) -> int | None:
    """The target never exceeds what the user's own material allows (F10.6)."""
    if target is None:
        return None
    if ceiling_high is None:
        return target
    return max(0, min(int(target), int(ceiling_high)))


def readiness(
    report: Mapping[str, object],
    *,
    target: int | None,
    band: int = STABILITY_BAND,
) -> dict[str, object]:
    """The F10.6 checklist for one attempt report, with the failing conditions named."""
    score = report.get("score") or {}
    ceiling = report.get("ceiling") or {}
    job_match = score.get("capped") if isinstance(score, Mapping) else None
    low = ceiling.get("low") if isinstance(ceiling, Mapping) else None
    high = ceiling.get("high") if isinstance(ceiling, Mapping) else None
    capped_target = cap_target(target, high)

    within_band = (
        job_match is not None and low is not None and int(job_match) >= int(low) - band
    )
    at_target = (
        job_match is not None and capped_target is not None and int(job_match) >= capped_target
    )

    gate = report.get("gate") or {}
    findings = gate.get("findings") if isinstance(gate, Mapping) else None
    blockers = sorted(
        {
            str(row.get("check") or "")
            for row in (findings or [])
            if isinstance(row, Mapping) and row.get("severity") == "blocker"
        }
    )

    recall = report.get("recall") or {}
    queries = recall.get("queries") if isinstance(recall, Mapping) else None
    required = [
        (str(row.get("label") or ""), bool(row.get("passed")))
        for row in (queries or [])
        if isinstance(row, Mapping) and str(row.get("label") or "") in REQUIRED_SEARCH_LABELS
    ]
    failing_searches = sorted(label for label, passed in required if not passed)

    advice = report.get("advice") or []
    open_advice = sorted(
        {
            str(item.get("kind") or "")
            for item in advice
            if isinstance(item, Mapping) and str(item.get("kind") or "") in OPEN_ADVICE_KINDS
        }
    )

    gaps = report.get("gaps") or {}
    alerts = gaps.get("alerts") if isinstance(gaps, Mapping) else None
    wrong_language = any(
        isinstance(alert, Mapping) and alert.get("kind") == "language_mismatch"
        for alert in (alerts or [])
    )

    checks = [
        {
            "key": "match",
            "ok": within_band or at_target,
            "job_match": job_match,
            "ceiling_low": low,
            "target": capped_target,
            "band": band,
        },
        {"key": "readability", "ok": not blockers, "blockers": blockers},
        {"key": "search", "ok": not failing_searches, "failing": failing_searches},
        {"key": "advice", "ok": not open_advice, "open": open_advice},
        {"key": "language", "ok": not wrong_language},
    ]
    unreachable = ceiling.get("unreachable") if isinstance(ceiling, Mapping) else None
    return {
        "ready": bool(job_match is not None and all(check["ok"] for check in checks)),
        "checks": checks,
        "target": capped_target,
        "ceiling_high": high,
        "unreachable": (unreachable or {}).get("requirements") or [],
    }
