"""Argon2id password hashing.

The dummy hash exists so that a login for an unknown username costs the same as a
login for a known one; skipping the work would leak which emails have accounts.
"""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_hasher = PasswordHasher()  # argon2-cffi defaults to Argon2id

DUMMY_HASH = _hasher.hash("atsker-nonexistent-account")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
