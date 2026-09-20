"""Reset an ATSker account's password (PRD F1).

Argon2id is one-way by design: a forgotten password cannot be read back, only
replaced. Deleting the account is the wrong remedy — it would take the profile,
its roles, bullets, stories, letter templates and tracks with it — so the row is
updated in place.

The new password is typed at a prompt, never passed as an argument: an argument
would land in shell history and in the process list, and PRD §10 rules that out.

Failed-login rows for the account are cleared at the same time, because a
forgotten password usually means several failed attempts, and the 5-per-15-minute
limit would otherwise lock out the password that was just set.

    uv run python scripts/reset_password.py --list
    uv run python scripts/reset_password.py --email you@example.com
"""

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete, select  # noqa: E402

from src.auth.accounts import MIN_PASSWORD_LENGTH  # noqa: E402
from src.auth.passwords import hash_password  # noqa: E402
from src.auth.rate_limit import normalize  # noqa: E402
from src.db import session_scope  # noqa: E402
from src.models import LoginAttempt, Profile, User  # noqa: E402


def list_accounts() -> int:
    with session_scope() as session:
        users = session.scalars(select(User).order_by(User.created_at)).all()
        if not users:
            print("No accounts exist on this database.")
            return 0
        for user in users:
            profile = session.scalar(select(Profile).where(Profile.user_id == user.id))
            name = profile.display_name if profile is not None else "(no profile)"
            print(f"{user.email}\t{name}\t{user.ui_lang}")
    return 0


def reset(email: str) -> int:
    address = normalize(email)

    with session_scope() as session:
        user = session.scalar(select(User).where(User.email == address))
        if user is None:
            print(f"{address} does not exist on this database.", file=sys.stderr)
            return 1

    password = getpass.getpass(f"New password for {address}: ")
    if len(password) < MIN_PASSWORD_LENGTH:
        print(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.", file=sys.stderr)
        return 1
    if password != getpass.getpass("Repeat password: "):
        print("Passwords do not match.", file=sys.stderr)
        return 1

    with session_scope() as session:
        user = session.scalar(select(User).where(User.email == address))
        if user is None:  # deleted between the check and here; say so rather than crash
            print(f"{address} does not exist on this database.", file=sys.stderr)
            return 1
        user.password_hash = hash_password(password)
        cleared = session.execute(
            delete(LoginAttempt).where(LoginAttempt.username == address)
        ).rowcount

    print(f"Password reset for {address}. Cleared {cleared} failed-login row(s).")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset an ATSker account password.")
    parser.add_argument("--email", help="the account to reset")
    parser.add_argument("--list", action="store_true", help="list accounts and exit")
    args = parser.parse_args()

    if args.list:
        return list_accounts()
    if not args.email:
        parser.error("--email is required unless --list is given")
    return reset(args.email)


if __name__ == "__main__":
    raise SystemExit(main())
