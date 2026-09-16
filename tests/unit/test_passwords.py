"""Argon2id hashing, as required by PRD F1."""

from src.auth.passwords import hash_password, verify_password


def test_hash_is_argon2id_and_verifies_its_password_only():
    password_hash = hash_password("correct horse battery staple")

    assert password_hash.startswith("$argon2id$")
    assert verify_password(password_hash, "correct horse battery staple") is True
    assert verify_password(password_hash, "correct horse battery stapler") is False


def test_malformed_hash_is_rejected_without_raising():
    assert verify_password("not-a-hash", "anything") is False
