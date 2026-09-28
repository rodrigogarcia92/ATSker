"""Import letter settings and templates from a local JSON file (PRD F8, N8.2).

The operator keeps his letters in a file that is never committed; this CLI copies them
into one profile's rows. It is deliberately boring:

* **Dry run by default.** Without `--apply` it prints what would change and touches
  nothing.
* **`--apply` requires typing `IMPORT`**, because the file is personal data going into
  a shared database and a typo is not undoable.
* **A dev database is refused** unless `--prod` is given: the fragment below is the
  development host, and personal letters belong in the real one.
* Settings upsert by (profile, language); templates upsert by (profile, name, language).
  A `track_name` that matches no track links nothing and is listed for the operator.

    uv run python scripts/letters_import.py --email you@example.com --file letters.json
    uv run python scripts/letters_import.py --email you@example.com --file letters.json --apply
"""

import argparse
import json
import sys
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.auth.rate_limit import normalize
from src.config import get_settings
from src.db import session_scope
from src.letters import (
    create_letter,
    get_letter_settings,
    list_letters,
    save_letter_settings,
    update_letter,
)
from src.models import Track, User
from src.profiles import get_own_profile

# The development database's host fragment. Importing personal letters there is a
# mistake that a dry run would not catch, so it needs an explicit flag to override.
DEV_HOST_FRAGMENT = "REDACTED-PROD-ENDPOINT"


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


def database_host(database_url: str) -> str:
    """The host of a connection string, for the dev-database refusal."""
    return (urlparse(database_url).hostname or "").lower()


def refusal_reason(database_url: str, *, prod: bool) -> str | None:
    """Why this database must not be written to, or None when it may."""
    host = database_host(database_url)
    if DEV_HOST_FRAGMENT in host and not prod:
        return (
            f"refusing to import personal letters into the development database ({host}); "
            "pass --prod for the real one"
        )
    return None


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
        templates.append(
            {
                "entry": entry,
                "name": name,
                "lang": lang,
                "key": (name.lower(), lang),
                "updates": (name.lower(), lang) in existing,
                "track_id": track.id if track is not None else None,
                "unresolved_track": track_name if track_name and track is None else None,
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
    parser.add_argument("--prod", action="store_true", help="allow the development host")
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
