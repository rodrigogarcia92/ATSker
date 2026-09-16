"""Create an ATSker account (PRD F1).

The password is typed at a prompt, never passed as an argument: an argument would
land in shell history and in the process list, and PRD 10 rules that out.
"""

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from src.auth.accounts import MIN_PASSWORD_LENGTH, create_account  # noqa: E402
from src.auth.rate_limit import normalize  # noqa: E402
from src.db import session_scope  # noqa: E402
from src.models import User  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Create an ATSker account.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", help="display name; defaults to the email's local part")
    parser.add_argument("--lang", default="es", choices=("es", "en"))
    args = parser.parse_args()

    email = normalize(args.email)
    password = getpass.getpass(f"Password for {email}: ")
    if len(password) < MIN_PASSWORD_LENGTH:
        print(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.", file=sys.stderr)
        return 1
    if password != getpass.getpass("Repeat password: "):
        print("Passwords do not match.", file=sys.stderr)
        return 1

    with session_scope() as session:
        if session.scalar(select(User).where(User.email == email)) is not None:
            print(f"{email} already exists.", file=sys.stderr)
            return 1
        display_name = args.name or email.split("@")[0]
        create_account(session, email, password, display_name, args.lang)

    print(f"Created {email}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
