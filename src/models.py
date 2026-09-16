"""SQLAlchemy models.

Column types are dialect-neutral (`Uuid`, not `postgresql.UUID`) so that tests can
create the same schema in SQLite and stay offline. PostgreSQL is the only dialect
that runs in production; the migration is the authority on the real DDL.

Tables land with the milestone that first writes them. `applications` (PRD F8)
arrives with M5/M6, when the report shape it stores actually exists — nothing can
be captured before then because nothing generates a report yet.
"""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Uuid, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


# SQLite refuses AUTOINCREMENT on BIGINT primary keys; PostgreSQL has no such
# complaint. This variant keeps the model creatable in both.
_BigInt = BigInteger().with_variant(Integer, "sqlite")


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    ui_lang: Mapped[str] = mapped_column(String(5), default="es")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Profile(Base):
    __tablename__ = "profiles"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )
    display_name: Mapped[str] = mapped_column(String(200))


class LoginAttempt(Base):
    """Failed logins, for the per-username rate limit (PRD F1).

    Kept in the database rather than in process memory: Cloud Run runs up to two
    instances and scales to zero, so an in-memory counter would be both wrong and
    forgetful. Rows are deleted on a successful login and aged out by query window.
    """

    __tablename__ = "login_attempts"

    id: Mapped[int] = mapped_column(_BigInt, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(320), index=True)
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
