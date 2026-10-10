r"""The golden-set runner: one command per scorer (queue A.3).

Run it from the checkout whose scorer should be measured — it inserts the
current working directory at `sys.path[0]` and imports `src.*` from there, so a
worktree of `baseline-w2` measures the w2 scorer while this file stays where it
was written. Only APIs verified unchanged at `ebac5ca` (baseline-w2) with
`git show` are called:

- `load_document(filename, data) -> LoadedDocument`
- `extract_resume(session, text, *, known_names, model, options)`
- `build_draft(session, extraction, *, language_hint) -> ResumeDraft`
- `create_resume(profile_id, session, *, filename, data, sha256, track_id, gate, draft)`
- `diff_draft(profile_id, session, draft) -> MergePlan`
- `apply_merge(profile_id, session, *, resume_id, draft, plan, selections, track_name)`
- `Selections(roles, bullets, educations, certifications, skills)`
- `get_track(profile_id, session, track_id)` / `list_tracks(profile_id, session, *, active_only)`
- `analyze(profile_id, session, *, jd_text, company, title, gate, model, options, track)`
- `create_application(profile_id, session, *, jd_text, jd_hash, report, weights_version,
  prompt_versions, token_cost_usd, company, title, track_id, scan_readability, scan_boolean)`

Operator notes::

    # once: the baseline worktree, with its own .env (both gitignored there)
    git worktree add ..\atsker-w2 baseline-w2
    Copy-Item .env ..\atsker-w2\.env

    # w2 — baseline-w2's lock predates openpyxl; --with adds it for this run only
    cd ..\atsker-w2
    uv run --with openpyxl python ..\ATSker\scripts\golden_run.py --label w2 --wipe

    # w3
    cd ..\ATSker
    uv run python scripts\golden_run.py --label w3 --wipe
    uv run python scripts\golden_stats.py --runs <w2.csv> <w3.csv>

    # R.1 — one measurement, two runs over the same tracks: import, edit in the
    # app, then analyse as the database now holds them (nothing is imported)
    uv run python scripts\golden_run.py --label w4-lang --wipe
    # …type the English titles on the imported roles in the app, then:
    uv run python scripts\golden_run.py --label w4-lang-en --reuse

    # after the evaluation (the worktree holds a copy of .env)
    git worktree remove --force ..\atsker-w2

The dev database must be at `0009` for both runs; `0009` is additive, so the
baseline code runs on it. The CSVs land in `ATSker\fixtures\golden\runs\`
for both runs.

The runner never reads, copies or parses `.env` itself (resume §4): `src.config`
loads settings from the working directory like the app does, and a missing
database URL or OpenRouter key stops the run before anything else, because a
worktree needs its own `.env` (above). The production guard runs before any
connection is opened — there is no override flag.

Per-run behaviour (queue A.3): validate everything first and report every
problem at once; an optional `--wipe` removes the mapped profiles' career data
scoped by `profile_id` — users, profiles, the shared vocabulary and `llm_calls`
are kept and the profile row survives, blanked; each distinct
`(profile, cv_version)` is imported once through the normal pipeline with every
candidate accepted and the track named exactly `cv_version`; each in-scope pair
is analysed against that track and its application is persisted; the CSV is
written under a gitignored path. A failed import is reported per CV and the
pairs that need it are skipped; a failed analysis is reported per pair and its
row is skipped the same way, so one bad call cannot end the run. Without
`--include-test` the test split is neither validated, imported, analysed nor
written. The sheet is only ever read.

`--reuse` is the second half of one measurement (R.1): it imports nothing and
takes each pair's track to be the profile's one active track named `cv_version`,
exactly as the database stands now, so a bullet or an English title the operator
typed in the app between the two runs is what gets measured. No such track, or
more than one, skips the pair and says which — the runner never guesses. The flag
is mutually exclusive with `--wipe`, which is the run that has nothing to measure
yet. Which mode produced a row is written into the CSV, like the opened split.

A second model may be run for evaluation only (PRD §11, queue A.6): `--model` and
`--effort` are passed to every call the run makes, and `--model` is named and
confirmed before the first one because it may cost far more than the default. The
CSV reports what the calls were actually made with — model, effort and the
vocabulary hash — read back from the report rather than from the flags.
"""

import argparse
import csv
import hashlib
import re
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path

# The scorer measured is the checkout this runs from; `golden_inputs` and the
# scripts' own helpers come from the repository this file lives in.
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path.cwd()))

import golden_inputs  # noqa: E402
from sqlalchemy import MetaData, Table, delete, inspect, or_, select  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from src.analysis import analyze  # noqa: E402
from src.applications import create_application  # noqa: E402
from src.config import get_settings  # noqa: E402
from src.db import normalized_url, session_scope  # noqa: E402
from src.extract.client import (  # noqa: E402
    CallOptions,
    NoModelConfigured,
    ProviderUnavailable,
    StructuredOutputError,
)
from src.extract.resume import EmptyExtraction, extract_resume  # noqa: E402
from src.ingest.documents import load_document  # noqa: E402
from src.ingest.draft import build_draft  # noqa: E402
from src.ingest.merge import Selections, apply_merge, diff_draft  # noqa: E402
from src.models import (  # noqa: E402
    Application,
    Bullet,
    BulletRevision,
    Certification,
    Education,
    LetterTemplate,
    Profile,
    Resume,
    Role,
    Story,
    StoryBullet,
    Track,
    TrackBullet,
)
from src.resumes import create_resume  # noqa: E402
from src.tracks import list_tracks  # noqa: E402

# The endpoint the operator's production database lives on. Matching the host is
# the whole guard: no flag, no environment variable and no override can turn it
# off (queue A.3 step 1).
PRODUCTION_HOST_MARK = "REDACTED-PROD-ENDPOINT"


def resolve_database_host() -> str:
    """The host of the URL exactly as `src.db` resolves it, or "" when there is none."""
    settings = get_settings()
    if settings.database_url is None:
        return ""
    raw = normalized_url(settings.database_url.get_secret_value())
    try:
        return make_url(raw).host or ""
    except Exception:  # noqa: BLE001 - an unparseable URL fails later at engine creation
        return ""


def configuration_error() -> str | None:
    """Resume §4: nothing starts without the two secrets `src.config` reads."""
    settings = get_settings()
    missing = []
    if not settings.database_url or not settings.database_url.get_secret_value().strip():
        missing.append("DATABASE_URL")
    key = settings.openrouter_api_key
    if not key or not key.get_secret_value().strip():
        missing.append("OPENROUTER_API_KEY")
    if not missing:
        return None
    return (
        f"missing configuration: {', '.join(missing)} — a worktree needs its own .env "
        "(see the operator notes in this script's docstring)"
    )


def accept_everything(plan) -> Selections:
    """Every candidate in the plan, by index — the runner is the reviewer (A.3 step 3)."""
    return Selections(
        roles=frozenset(range(len(plan.roles))),
        bullets=frozenset(
            (role_index, bullet_index)
            for role_index, role in enumerate(plan.roles)
            for bullet_index, _ in enumerate(role.bullets)
        ),
        educations=frozenset(range(len(plan.educations))),
        certifications=frozenset(range(len(plan.certifications))),
        skills=frozenset(range(len(plan.skills))),
    )


def wipe_profile(session: Session, profile_id: uuid.UUID) -> dict[str, int]:
    """Queue A.3 step 2: one profile's career data, scoped by `profile_id`, never wider.

    Schema-adaptive on purpose: both runs share one database at `0009`, which has
    tables the w2 checkout's models do not know (`summaries`) — those are deleted
    by reflection when the table exists and skipped when it does not. The row
    counts returned are what the operator is shown.
    """
    counts: dict[str, int] = {}

    def drop(name: str, statement) -> None:
        counts[name] = session.execute(statement).rowcount

    bullet_ids = select(Bullet.id).where(Bullet.profile_id == profile_id)
    story_ids = select(Story.id).where(Story.profile_id == profile_id)
    track_ids = select(Track.id).where(Track.profile_id == profile_id)

    # Revisions and link rows first: SQLite in tests enforces no foreign keys, so
    # order is what keeps the wipe correct on both databases.
    drop(
        "bullet_revisions",
        delete(BulletRevision).where(BulletRevision.bullet_id.in_(bullet_ids)),
    )
    drop(
        "story_bullet",
        delete(StoryBullet).where(
            or_(StoryBullet.story_id.in_(story_ids), StoryBullet.bullet_id.in_(bullet_ids))
        ),
    )
    drop(
        "track_bullets",
        delete(TrackBullet).where(
            or_(TrackBullet.track_id.in_(track_ids), TrackBullet.bullet_id.in_(bullet_ids))
        ),
    )
    drop("applications", delete(Application).where(Application.profile_id == profile_id))
    drop("resumes", delete(Resume).where(Resume.profile_id == profile_id))
    drop("bullets", delete(Bullet).where(Bullet.profile_id == profile_id))
    drop("roles", delete(Role).where(Role.profile_id == profile_id))
    drop("educations", delete(Education).where(Education.profile_id == profile_id))
    drop("certifications", delete(Certification).where(Certification.profile_id == profile_id))
    drop("stories", delete(Story).where(Story.profile_id == profile_id))
    drop(
        "letter_templates",
        delete(LetterTemplate).where(LetterTemplate.profile_id == profile_id),
    )
    drop("tracks", delete(Track).where(Track.profile_id == profile_id))

    # Reflection runs on the session's own connection: a separate checkout from
    # the pool would be reset (rolled back) on return, taking the deletes above
    # with it, and on Neon it would also open a connection the run does not need.
    bind = session.connection()
    if "summaries" in inspect(bind).get_table_names():
        summaries = Table("summaries", MetaData(), autoload_with=bind)
        counts["summaries"] = session.execute(
            delete(summaries).where(summaries.c.profile_id == profile_id)
        ).rowcount

    # The profile row and the login survive; the personal fields on the row go.
    profile = session.get(Profile, profile_id)
    if profile is not None:
        columns = {column.name for column in Profile.__table__.columns}
        blanks = {"headline": None, "summary": None, "skills": [], "standing_risks": []}
        for name, value in blanks.items():
            if name in columns:
                setattr(profile, name, value)
        counts["profile_blanked"] = 1
    return counts


def import_cv(
    session: Session,
    user,
    profile: Profile,
    cv_path: Path,
    track_name: str,
    *,
    model: str | None = None,
    options: CallOptions | None = None,
) -> tuple[bool, str]:
    """One CV through the normal pipeline, every candidate accepted (A.3 step 3).

    The track takes the sheet's `cv_version` verbatim so both runs name their
    tracks the same. The transaction rule holds: every provider call starts with
    nothing held. `model`/`options` are the evaluation run's second model (A.6):
    every call it makes is billed and recorded under that model.
    """
    data = cv_path.read_bytes()
    loaded = load_document(cv_path.name, data)
    if not loaded.text.strip():
        return False, "no text an ATS could read"
    session.commit()  # release the reads before the provider call
    try:
        extraction, completion = extract_resume(
            session,
            loaded.text,
            known_names=[profile.display_name] if profile.display_name else None,
            model=model,
            options=options,
        )
    except (ProviderUnavailable, StructuredOutputError, EmptyExtraction, NoModelConfigured) as fail:
        session.commit()  # whatever was paid for stays in the ledger
        return False, f"{type(fail).__name__}: {fail}"
    draft = build_draft(session, extraction, language_hint=user.ui_lang)
    resume = create_resume(
        profile.id,
        session,
        filename=cv_path.name,
        data=data,
        sha256=hashlib.sha256(data).hexdigest(),
        gate=loaded.gate.to_dict(),
        draft=draft.model_dump(mode="json"),
    )
    session.commit()
    plan = diff_draft(profile.id, session, draft)
    apply_merge(
        profile.id,
        session,
        resume_id=resume.id,
        draft=draft,
        plan=plan,
        selections=accept_everything(plan),
        track_name=track_name,
    )
    session.commit()
    return True, "merged" + (" (ledger unrecorded)" if completion.ledger_error else "")


def csv_row(
    pair,
    analysis,
    application,
    track_name: str,
    commit: str,
    sub_score_names: tuple[str, ...],
) -> dict[str, object]:
    """One CSV row from one analysis, sub-scores read generically (queue A.3 step 5).

    `skills_direct`/`skills_transfer` come from the skills sub-score's detail when
    the scorer computes the split — w3 does (F5.5.1) and w2 does not, so a w2 run
    leaves both blank rather than inventing a split its scorer never made.
    """
    score = analysis.report["score"]
    sub_scores = score["sub_scores"]
    skills_detail = (sub_scores.get("skills") or {}).get("detail", {})
    calls = analysis.report["llm"]["calls"]
    row: dict[str, object] = {
        "pair_id": pair.pair_id,
        "profile": pair.profile,
        "split": pair.split,
        "lang": pair.lang,
        "track": track_name,
        "weights_version": analysis.weights_version,
        # F3.1: the vocabulary the report was scored against. Blank for a scorer
        # that predates the hash, and the stats say so rather than assume one.
        "vocabulary_hash": analysis.report.get("vocabulary_hash") or "",
        "score": score["capped"],
        "uncapped": score["uncapped"],
        "cap": "" if score["cap"] is None else score["cap"],
    }
    for name in sub_score_names:
        row[name] = round(sub_scores[name]["value"], 4)
    row["skills_direct"] = skills_detail.get("direct", "")
    row["skills_transfer"] = skills_detail.get("transfer", "")
    row["cost_usd"] = str(analysis.cost_usd)
    row["cached_calls"] = sum(1 for call in calls if call["cached"])
    # What the calls were actually made with, not what the flags asked for: the
    # model falls back to the environment's and the effort to the setting's, and
    # distinct values are joined so a mixed run is visible rather than averaged.
    row["model"] = ";".join(sorted({str(call["model"]) for call in calls}))
    row["reasoning_effort"] = ";".join(
        sorted({str(call.get("reasoning_effort") or "") for call in calls} - {""})
    )
    row["application_id"] = str(application.id)
    row["commit"] = commit
    return row


def find_track(
    profile: Profile, session: Session, cv_version: str
) -> tuple[Track | None, str | None]:
    """The profile's one active track named `cv_version`, or why there is none (R.1).

    Active only, and matched by the exact name: a `--reuse` run measures the track
    the operator would see in the app, and two candidates are a question for the
    operator — picking one by sort order would decide the measurement for them.
    """
    matches = [
        track
        for track in list_tracks(profile.id, session, active_only=True)
        if track.name == cv_version
    ]
    if not matches:
        return None, f"no active track named {cv_version!r}"
    if len(matches) > 1:
        return None, (
            f"{len(matches)} active tracks named {cv_version!r} — rename or deactivate one"
        )
    return matches[0], None


def write_csv(
    path: Path,
    rows: list[dict[str, object]],
    sub_score_names: tuple[str, ...],
    comments: tuple[str, ...] = (),
) -> None:
    """The CSV, with one `#` line per annotation above the header (A.3 step 5).

    Two annotations exist and both belong before the rows they describe: the test
    split being opened, and a `--reuse` run saying its rows came from the tracks as
    they were found rather than from an import (R.1). `golden_stats.read_run`
    skips every `#` line, so a reader that tolerates one tolerates both.
    """
    header = (
        golden_inputs.COLUMNS_BEFORE_SUB_SCORES
        + sub_score_names
        + golden_inputs.COLUMNS_AFTER_SUB_SCORES
    )
    with path.open("w", newline="", encoding="utf-8") as handle:
        for comment in comments:
            handle.write(comment + "\n")
        writer = csv.DictWriter(handle, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)


def current_commit() -> str:
    """`git rev-parse HEAD` of the working directory — the scorer this run measured."""
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=Path.cwd(), check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


# A label names the scorer being measured, not a filename: `w3`, `w4`, `w4-vocab`.
LABEL_PATTERN = re.compile(r"^w\d+(-[a-z0-9]+)*$")


def run_label(value: str) -> str:
    if not LABEL_PATTERN.match(value):
        raise argparse.ArgumentTypeError(
            "a label is w<digits> with optional -<lowercase letters or digits> groups: "
            "w3, w4, w4-vocab"
        )
    return value


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the golden set against this checkout.")
    parser.add_argument("--label", required=True, type=run_label)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--wipe", action="store_true")
    mode.add_argument(
        "--reuse",
        action="store_true",
        help="analyse the tracks as the database holds them now (R.1): nothing is "
        "imported, and each pair needs one active track named after its cv_version",
    )
    parser.add_argument("--include-test", action="store_true")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="skip the typed confirmations (YES for --model, DELETE before a wipe)",
    )
    parser.add_argument(
        "--model",
        default=None,
        metavar="OPENROUTER_ID",
        help="a second model, for evaluation only (PRD §11): it is confirmed before "
        "the first call because it may cost far more than the default",
    )
    parser.add_argument(
        "--effort",
        choices=("low", "medium", "high"),
        default=None,
        help="reasoning effort for every call this run makes",
    )
    parser.add_argument("--sheet", type=Path, default=golden_inputs.DEFAULT_SHEET)
    parser.add_argument("--map", dest="map_path", type=Path, default=golden_inputs.DEFAULT_MAP)
    parser.add_argument("--out", type=Path, default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    out_path = args.out or golden_inputs.DEFAULT_RUNS_DIR / f"{args.label}-{stamp}.csv"

    problem = configuration_error()
    if problem is not None:
        print(problem)
        return 2
    host = resolve_database_host()
    if PRODUCTION_HOST_MARK in host:
        print(f"refusing to run: the database host is the production endpoint ({host})")
        return 2
    if not golden_inputs.output_is_ignored(out_path):
        print(f"refusing to write outside a gitignored path: {out_path}")
        return 2

    options = CallOptions(reasoning_effort=args.effort) if args.effort else None
    if args.model:
        # A second model is billed at its own price and may cost far more than the
        # default, so it is named and confirmed before anything is spent (PRD §11).
        print(f"model: {args.model} · reasoning effort: {args.effort or 'provider default'}")
        if not args.yes:
            answer = input("type YES to run this model: ")
            if answer.strip() != "YES":
                print("aborted: no call was made")
                return 1

    try:
        pairs = golden_inputs.read_pairs(args.sheet, include_test=args.include_test)
        mapping = golden_inputs.load_mapping(args.map_path)
    except (golden_inputs.SheetError, golden_inputs.MappingFileError) as failure:
        print(str(failure))
        return 2

    with session_scope() as session:
        check = golden_inputs.check_inputs(pairs, mapping, session)
        if not check.ok:
            for entry in check.problems:
                print(entry)
            return 3

        # In first-appearance order, so runs and reports read the same both times.
        wanted = list(dict.fromkeys((pair.profile, pair.cv_version) for pair in pairs))
        profiles = {name: check.profiles[name] for name, _ in wanted}

        if args.wipe:
            print(f"database host: {host}")
            if not args.yes:
                answer = input("type DELETE to wipe the mapped profiles' career data: ")
                if answer.strip() != "DELETE":
                    print("aborted: nothing was wiped")
                    return 1
            totals: dict[str, int] = {}
            for name in dict.fromkeys(pair.profile for pair in pairs):
                for table, count in wipe_profile(session, check.profiles[name].id).items():
                    totals[table] = totals.get(table, 0) + count
            session.commit()
            print("wiped: " + ", ".join(f"{table}={count}" for table, count in totals.items()))

        imported: dict[tuple[str, str], bool] = {}
        if args.reuse:
            # The operator's edits in the app are the input this run measures, so
            # nothing here may touch the career data (R.1).
            print("reuse: analysing the tracks as they are; nothing imported")
        else:
            for name, cv_version in wanted:
                ok, message = import_cv(
                    session,
                    check.users[name],
                    profiles[name],
                    check.files[cv_version],
                    cv_version,
                    model=args.model,
                    options=options,
                )
                imported[(name, cv_version)] = ok
                print(f"import {name} / {cv_version}: {message}")

        commit = current_commit()
        rows: list[dict[str, object]] = []
        sub_score_names: tuple[str, ...] = ()
        for pair in pairs:
            if not args.reuse and not imported.get((pair.profile, pair.cv_version)):
                print(f"pair {pair.pair_id}: skipped, its CV was not imported")
                continue
            profile = profiles[pair.profile]
            track, why_not = find_track(profile, session, pair.cv_version)
            if track is None:
                print(f"pair {pair.pair_id}: skipped, {why_not}")
                continue
            try:
                analysis = analyze(
                    profile.id,
                    session,
                    jd_text=pair.jd,
                    track=track,
                    model=args.model,
                    options=options,
                )
            except (ProviderUnavailable, StructuredOutputError, NoModelConfigured) as failure:
                session.commit()  # what was paid for stays in the ledger
                print(f"pair {pair.pair_id}: analysis failed: {type(failure).__name__}: {failure}")
                continue
            application = create_application(
                profile.id,
                session,
                jd_text=pair.jd,
                jd_hash=analysis.jd_hash,
                company=analysis.company,
                title=analysis.title,
                report=analysis.report,
                weights_version=analysis.weights_version,
                prompt_versions=analysis.prompt_versions,
                token_cost_usd=analysis.cost_usd,
                track_id=track.id,
                scan_readability=analysis.report.get("gate"),
                scan_boolean=analysis.report.get("recall"),
            )
            session.commit()
            if not sub_score_names:
                sub_score_names = tuple(analysis.report["score"]["sub_scores"])
            row = csv_row(pair, analysis, application, pair.cv_version, commit, sub_score_names)
            rows.append(row)

    comments: list[str] = []
    if args.reuse:
        comments.append("# reuse: tracks analysed as found in the database, no import")
    if args.include_test:
        opened = datetime.now().isoformat(timespec="minutes")
        comments.append(f"# test split opened {opened}")
    write_csv(out_path, rows, sub_score_names, tuple(comments))
    print(f"wrote {len(rows)} rows to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
