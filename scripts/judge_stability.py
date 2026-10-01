"""Measure the judge-stability band on stored analyses (PRD §9, F10.4, A3).

`STABILITY_BAND` in `src/score/weights.py` is the number of Job Match points inside
which two gradings of the same posting read as *sin cambio significativo*. It is
data, provisional until this script measures it.

For each stored analysis the script re-grades the same posting `--repeats` times,
**bypassing the content-hash cache** (a cached re-run measures the cache, not the
judge), rebuilds Job Match with only the Skills sub-score moving, and prints the max
|Δ| per analysis and overall. The operator runs it on dev and sets the constant.

The calls are paid, so the script refuses to run against the production host unless
`--prod` is given, and asks for confirmation before spending anything.

    uv run python scripts/judge_stability.py --pairs 12 --repeats 5
"""

import argparse
import sys
from collections.abc import Callable, Sequence
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from src.config import get_settings  # noqa: E402
from src.db import session_scope  # noqa: E402
from src.documents import (  # noqa: E402
    document_bullets,
    document_skills_list,
    document_summary,
    track_document,
)
from src.extract.client import CallOptions  # noqa: E402
from src.extract.grading import grade_evidence  # noqa: E402
from src.jd import StructuredJD  # noqa: E402
from src.models import Application, Profile  # noqa: E402
from src.score.aggregate import SubScore, aggregate  # noqa: E402
from src.score.evidence import Level, evidence_coverage  # noqa: E402
from src.score.weights import STABILITY_BAND, W4, WeightSet  # noqa: E402
from src.tracks import get_track  # noqa: E402

# The Neon production branch (A3). Named here, never read from a variable that could
# be printed: a URL carries credentials and this script must not echo one.
PROD_HOST = "REDACTED-PROD-ENDPOINT"

DEFAULT_REPEATS = 5


def is_prod(database_url: str | None) -> bool:
    return bool(database_url) and PROD_HOST in (database_url or "")


def check_target(database_url: str | None, *, allow_prod: bool) -> None:
    """Refuse the production host unless the operator opted in with `--prod`."""
    if not database_url:
        raise SystemExit("DATABASE_URL is not set; point it at the development branch.")
    if is_prod(database_url) and not allow_prod:
        raise SystemExit(
            f"refusing the production host ({PROD_HOST}); pass --prod to measure it "
            "deliberately."
        )


def confirm(
    question: str,
    *,
    assume_yes: bool = False,
    input_fn: Callable[[str], str] = input,
) -> bool:
    """Ask before spending money; `--yes` skips the prompt."""
    if assume_yes:
        return True
    answer = input_fn(f"{question} [y/N] ").strip().lower()
    return answer in ("y", "yes", "s", "sí", "si")


def _total(report: dict, levels: Sequence[Level], weights: WeightSet) -> int:
    """Job Match with only the Skills sub-score replaced by a repeat's grading."""
    recorded = report["score"]["sub_scores"]
    sub_scores = {
        name: SubScore(name=name, value=float(entry["value"]))
        for name, entry in recorded.items()
        if name != "skills"
    }
    sub_scores["skills"] = evidence_coverage(levels, basis_credit=weights.basis_credit)
    return aggregate(sub_scores, weights).uncapped


def measure_application(
    session: Session,
    application: Application,
    *,
    repeats: int,
    model: str,
    weights: WeightSet = W4,
    today: date | None = None,
) -> dict[str, object]:
    """Re-grade one stored analysis `repeats` times and report the spread."""
    report = application.report or {}
    jd = StructuredJD(**report["jd"])
    track = (
        get_track(application.profile_id, session, application.track_id)
        if application.track_id
        else None
    )
    bullets = document_bullets(application.profile_id, session, track)
    document = track_document(application.profile_id, session, track, jd.language)
    profile = session.get(Profile, application.profile_id)
    options = CallOptions(bypass_cache=True, profile_id=application.profile_id)
    references = [str(grade["requirement"]) for grade in report["grades"]]

    totals: list[int] = []
    for _ in range(repeats):
        session.commit()
        grading = grade_evidence(
            session,
            jd,
            bullets,
            basis_credit=weights.basis_credit,
            summary_text=document_summary(document),
            skills_text=document_skills_list(document),
            language=jd.language,
            model=model,
            known_names=[profile.display_name] if profile and profile.display_name else None,
            options=options,
        )
        if [str(entry.requirement) for entry in grading.levels] != references:
            # A different requirement set would make the totals incomparable.
            raise RuntimeError(f"{application.id}: the repeat graded a different posting")
        levels = [
            Level(entry.requirement, entry.level, entry.must_have, entry.basis)
            for entry in grading.levels
        ]
        totals.append(_total(report, levels, weights))

    return {
        "application": str(application.id),
        "totals": totals,
        "max_delta": max(totals) - min(totals) if totals else 0,
    }


def measure(
    session: Session,
    applications: Sequence[Application],
    *,
    repeats: int,
    model: str,
    weights: WeightSet = W4,
) -> dict[str, object]:
    pairs = [
        measure_application(session, application, repeats=repeats, model=model, weights=weights)
        for application in applications
    ]
    overall = max((int(pair["max_delta"]) for pair in pairs), default=0)
    return {
        "pairs": pairs,
        "overall_max_delta": overall,
        "band": STABILITY_BAND,
        "repeats": repeats,
    }


def _stored_analyses(session: Session, limit: int) -> list[Application]:
    """Stored analyses with the w4 sub-scores and the shapes the re-grade reads."""
    rows = list(
        session.scalars(select(Application).order_by(Application.created_at.desc()))
    )
    usable = []
    for application in rows:
        report = application.report or {}
        sub_scores = (report.get("score") or {}).get("sub_scores") or {}
        if isinstance(report.get("jd"), dict) and report.get("grades") and "skills" in sub_scores:
            usable.append(application)
        if limit and len(usable) >= limit:
            break
    return usable


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Judge-stability band (PRD §9, F10.4)")
    parser.add_argument("--pairs", type=int, default=12, help="how many stored analyses")
    parser.add_argument("--repeats", type=int, default=DEFAULT_REPEATS)
    parser.add_argument(
        "--model", default="", help="model id; default: the one each stored run used"
    )
    parser.add_argument("--prod", action="store_true", help="allow the production host")
    parser.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    args = parser.parse_args(argv)

    settings = get_settings()
    database_url = (
        settings.database_url.get_secret_value() if settings.database_url is not None else None
    )
    check_target(database_url, allow_prod=args.prod)

    with session_scope() as session:
        applications = _stored_analyses(session, args.pairs)
        if not applications:
            print("no stored analysis has the shape this script needs; nothing to do.")
            return 0
        per_run = args.repeats
        calls = len(applications) * per_run
        question = f"This makes about {calls} paid grading calls. Continue?"
        if not confirm(question, assume_yes=args.yes):
            print("cancelled; nothing was called.")
            return 1
        results = []
        for application in applications:
            runs = (application.report or {}).get("llm", {}).get("calls") or [{}]
            model = args.model or str(runs[0].get("model") or "")
            results.append(
                measure_application(
                    session, application, repeats=per_run, model=model
                )
            )
    overall = max((int(pair["max_delta"]) for pair in results), default=0)
    for pair in results:
        print(f"{pair['application']}: max |Δ Job Match| = {pair['max_delta']}  {pair['totals']}")
    print(f"overall max |Δ Job Match| = {overall}; STABILITY_BAND is {STABILITY_BAND}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
