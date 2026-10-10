"""Import letter settings and templates from a local JSON file (PRD F8, N8.2).

The operator keeps his letters in a file that is never committed; this CLI copies them
into one profile's rows. It is deliberately boring:

* **Dry run by default.** Without `--apply` it prints what would change and touches
  nothing.
* **`--apply` requires typing `IMPORT`**, because the file is personal data going into
  a shared database and a typo is not undoable.
* **The production database is refused** unless `--prod` is given. The production host is
  recognised by `PROD_DB_HOST_FRAGMENT` (see `scripts/_prod_guard.py`), and an unset
  variable refuses every non-local database. A dev import needs no flag.
* Settings upsert by (profile, language); templates upsert by (profile, name, language).
* **One template per track (F8).** A template whose `track_name` matches a track is linked
  to it, in the track's language, when that track has no template yet. Otherwise it is
  imported **unlinked** and listed for the operator: the track already has one, another
  template of this file claimed the track, the template's language is not the track's, or
  the `track_name` matches no track. A template with no `track_name` is unlinked. An
  existing link is never replaced; the user picks with "Usar esta" on Cartas.

    uv run python scripts/letters_import.py --email you@example.com --file letters.json
    uv run python scripts/letters_import.py --email you@example.com --file letters.json --apply
"""

import argparse
import json
import sys
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select
from sqlalchemy.orm import Session

from scripts import _prod_guard
from src.auth.rate_limit import normalize
from src.config import get_settings
from src.db import session_scope
from src.letters import (
    create_letter,
    get_letter_settings,
    list_letters,
    save_letter_settings,
    track_templates,
    update_letter,
)
from src.models import Track, User
from src.profiles import get_own_profile


class ImportRefused(RuntimeError):
    """The import must not run: wrong database, bad payload, or no confirmation."""


def load_payload(path: Path) -> dict[str, Any]:
    """The JSON file, shape-checked just enough to fail loudly and early."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ImportRefused(f"{path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ImportRefused("the file must be a JSON object")
    for key in ("settings", "templates"):
        value = payload.get(key, [])
        if not isinstance(value, list):
            raise ImportRefused(f"{key!r} must be a list")
        for entry in value:
            if not isinstance(entry, dict):
                raise ImportRefused(f"{key!r} entries must be objects")
    return payload


def refusal_reason(database_url: str, *, prod: bool) -> str | None:
    """Why this database must not be written to, or None when it may (see `_prod_guard`)."""
    return _prod_guard.refusal_reason(database_url, allow_prod=prod)


def _decide_link(
    profile_id: Any,
    session: Session,
    track: Track | None,
    *,
    lang: str,
    current: Any,
    claimed: set[Any],
) -> tuple[bool, str | None]:
    """Whether this template may take its track, and why not when it may not (F8).

    A track keeps the template it has: the import links only to a track with none, or to the
    one template the track already has when it is this very row being updated.
    """
    if track is None:
        return False, None  # no `track_name`, or no such track: the caller lists the latter
    if track.lang != lang:
        return False, (
            f"template is in {lang.upper()} and track {track.name!r} is in "
            f"{track.lang.upper()}; imported unlinked"
        )
    linked = track_templates(profile_id, session, track)
    already_has_another = any(current is None or letter.id != current.id for letter in linked)
    if already_has_another or track.id in claimed:
        return False, f"track {track.name!r} already has a template; imported unlinked"
    return True, None


def plan_import(session: Session, profile_id: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """What would change, resolved against the database — computed without writing."""
    tracks = {
        track.name.strip().lower(): track
        for track in session.scalars(select(Track).where(Track.profile_id == profile_id))
    }
    existing = {
        (letter.name.strip().lower(), letter.lang): letter
        for letter in list_letters(profile_id, session)
    }
    # Tracks that end up with a template from this file, so two entries never share one.
    claimed: set[Any] = set()
    settings = [
        {
            "entry": entry,
            "lang": str(entry.get("lang") or "es")[:5],
            "exists": get_letter_settings(
                profile_id, session, str(entry.get("lang") or "es")
            )
            is not None,
        }
        for entry in payload.get("settings", [])
    ]
    templates = []
    for entry in payload.get("templates", []):
        name = str(entry.get("name") or "").strip()
        lang = str(entry.get("lang") or "es")[:5]
        track_name = str(entry.get("track_name") or "").strip()
        track = tracks.get(track_name.lower()) if track_name else None
        current = existing.get((name.lower(), lang))
        link, note = _decide_link(
            profile_id, session, track, lang=lang, current=current, claimed=claimed
        )
        if link:
            claimed.add(track.id)
        templates.append(
            {
                "entry": entry,
                "name": name,
                "lang": lang,
                "key": (name.lower(), lang),
                "updates": current is not None,
                "track_id": track.id if link else None,
                "track_name": track_name,
                "unresolved_track": track_name if track_name and track is None else None,
                "note": note,
            }
        )
    return {"settings": settings, "templates": templates}


def apply_import(session: Session, profile_id: Any, plan: dict[str, Any]) -> dict[str, int]:
    """Write the plan: settings upserted, templates created or updated."""
    counts = {"settings": 0, "templates_created": 0, "templates_updated": 0}
    for row in plan["settings"]:
        entry = row["entry"]
        save_letter_settings(
            profile_id,
            session,
            lang=row["lang"],
            header=str(entry.get("header") or ""),
            greeting=str(entry.get("greeting") or ""),
            closing=str(entry.get("closing") or ""),
            sign_off=str(entry.get("sign_off") or ""),
            voice_notes=str(entry.get("voice_notes") or ""),
        )
        counts["settings"] += 1
    for row in plan["templates"]:
        entry = row["entry"]
        if row["updates"]:
            letter = next(
                letter
                for letter in list_letters(profile_id, session)
                if (letter.name.strip().lower(), letter.lang) == row["key"]
            )
            update_letter(
                profile_id,
                session,
                letter.id,
                name=row["name"],
                applies_when=str(entry.get("applies_when") or ""),
                presentation=str(entry.get("presentation") or ""),
                achievements=str(entry.get("achievements") or ""),
                lang=row["lang"],
                track_id=row["track_id"],
            )
            counts["templates_updated"] += 1
        else:
            create_letter(
                profile_id,
                session,
                name=row["name"],
                applies_when=str(entry.get("applies_when") or ""),
                presentation=str(entry.get("presentation") or ""),
                achievements=str(entry.get("achievements") or ""),
                lang=row["lang"],
                track_id=row["track_id"],
            )
            counts["templates_created"] += 1
    return counts


def _print_plan(plan: dict[str, Any]) -> None:
    for row in plan["settings"]:
        action = "update" if row["exists"] else "create"
        print(f"settings {row['lang']}: {action}")
    for row in plan["templates"]:
        action = "update" if row["updates"] else "create"
        link = f"track={row['track_id']}" if row["track_id"] else "no track"
        print(f"template {row['name']!r} ({row['lang']}): {action}, {link}")
        if row["unresolved_track"]:
            print(f"  ! no track named {row['unresolved_track']!r}: left unlinked")
        if row["note"]:
            print(f"  ! {row['note']}")


def _resolve_profile(session: Session, email: str):
    user = session.scalar(select(User).where(User.email == normalize(email)))
    if user is None:
        raise ImportRefused(f"no account for {email!r}")
    profile = get_own_profile(session, user)
    if profile is None:
        raise ImportRefused(f"{email!r} has no profile")
    return profile


def main(
    argv: Sequence[str] | None = None,
    *,
    confirm: Callable[[str], str] = input,
    scope: Callable[[], Iterator[Session]] = session_scope,
) -> int:
    parser = argparse.ArgumentParser(description="Import letter settings and templates.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--file", required=True, help="local JSON file, never committed")
    parser.add_argument("--apply", action="store_true", help="write; otherwise dry run")
    parser.add_argument("--prod", action="store_true", help="allow the production host")
    args = parser.parse_args(argv)

    payload = load_payload(Path(args.file))
    settings = get_settings()
    url = settings.database_url.get_secret_value() if settings.database_url else ""
    reason = refusal_reason(url, prod=args.prod)
    if reason is not None:
        print(reason, file=sys.stderr)
        return 3

    with scope() as session:
        profile = _resolve_profile(session, args.email)
        plan = plan_import(session, profile.id, payload)
        _print_plan(plan)
        if not args.apply:
            print("dry run: nothing written (pass --apply)")
            return 0
        if confirm("Type IMPORT to apply: ").strip() != "IMPORT":
            print("not applied", file=sys.stderr)
            return 2
        counts = apply_import(session, profile.id, plan)

    print(
        f"settings {counts['settings']}, "
        f"templates created {counts['templates_created']}, "
        f"updated {counts['templates_updated']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
