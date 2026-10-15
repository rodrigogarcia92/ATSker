"""Shared setup for the F11 tests: CVs of a track, built from synthetic drafts.

A CV is a merged résumé row with a stored draft and gate (F11.1). `make_cv` stores one
the way the import flow leaves it, with `merged_at` set so it is analysable; the drafts
mirror the `career` fixture's role (Acme, Analista de datos) so unchanged bullets match
the master rows and a new one does not.
"""

import hashlib
from datetime import UTC, datetime, timedelta

from src.resumes import create_resume

EPOCH = datetime(2026, 1, 1, tzinfo=UTC)


def draft_dict(
    *bullets: str,
    language: str = "es",
    headline: str | None = "Analista de datos",
    summary: str | None = None,
    skills: tuple[str, ...] = (),
    employer: str = "Acme",
    title: str = "Analista de datos",
) -> dict:
    """A reviewed draft with one role holding `bullets`, in the file's order."""
    return {
        "language": language,
        "headline": headline,
        "summary": summary,
        "skills": list(skills),
        "roles": [
            {
                "employer": employer,
                "title": title,
                "start_date": None,
                "end_date": None,
                "bullets": [{"text": text, "chips": []} for text in bullets],
            }
        ],
        "educations": [],
        "certifications": [],
    }


def make_cv(
    session,
    profile,
    track,
    *,
    name: str = "cv.docx",
    draft: dict | None = None,
    gate: dict | None = None,
    age_days: int = 0,
    merged: bool = True,
    active: bool = True,
):
    """Store a CV; a larger `age_days` is an older one."""
    resume = create_resume(
        profile.id,
        session,
        filename=name,
        data=b"synthetic",
        sha256=hashlib.sha256(f"{name}:{age_days}".encode()).hexdigest(),
        track_id=track.id if track is not None else None,
        gate=gate,
        draft=draft if draft is not None else draft_dict(),
    )
    stamp = EPOCH - timedelta(days=age_days)
    resume.uploaded_at = stamp
    resume.merged_at = stamp if merged else None
    resume.active = active
    session.commit()
    return resume


def add_first_cv(session, career, **changes):
    """A CV of the first track holding its one master bullet, as an unchanged export would.

    The route tests that analyse a posting need a CV to analyse (F11.3); the provider
    stubs cite `career.first_bullet`, which this file carries unchanged.
    """
    changes.setdefault("draft", draft_dict(career.first_bullet.text_es))
    return make_cv(session, career.first_profile, career.first_track, **changes)


def analysis_form(session, career, **fields) -> dict:
    """The fields a POST /analyze needs: the first track and (made on first use) its CV."""
    from src.resumes import track_cvs

    if not track_cvs(career.first_profile.id, session, career.first_track.id):
        add_first_cv(session, career)
    return {"track_id": str(career.first_track.id), **fields}


def ensure_first_cv(request) -> None:
    """Give the first track a CV when the test is about to analyse (it asks for a provider
    stub, which `career` backs): the route tests post `/analyze`, which needs a CV (F11.3)."""
    wanted = {"provider", "stub"}
    if wanted & set(request.fixturenames) and "career" in request.fixturenames:
        add_first_cv(request.getfixturevalue("session"), request.getfixturevalue("career"))
