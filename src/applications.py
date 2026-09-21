"""Data access for analyses (PRD F8).

`profile_id` comes first and ownership is part of the query, never a check after
the fact: another profile's report is simply not found.
"""

import uuid
from decimal import Decimal

from sqlalchemy.orm import Session

from src.models import Application
from src.scoping import owned_row


def create_application(
    profile_id: uuid.UUID,
    session: Session,
    *,
    jd_text: str,
    jd_hash: str,
    report: dict,
    weights_version: str,
    prompt_versions: dict,
    token_cost_usd: Decimal,
    company: str | None = None,
    title: str | None = None,
    track_id: uuid.UUID | None = None,
) -> Application:
    """Persist one analysis. The schema exists from the first real application (F8)."""
    application = Application(
        profile_id=profile_id,
        company=company,
        title=title,
        jd_text=jd_text,
        jd_hash=jd_hash,
        report=report,
        weights_version=weights_version,
        prompt_versions=prompt_versions,
        token_cost_usd=token_cost_usd,
        track_id=track_id,
    )
    session.add(application)
    session.flush()
    return application


def get_application(
    profile_id: uuid.UUID, session: Session, application_id: str | uuid.UUID
) -> Application | None:
    return owned_row(Application, session, profile_id, application_id)
