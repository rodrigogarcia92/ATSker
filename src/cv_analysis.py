"""Analysis on a CV (PRD F11): the headline number describes a file.

A CV is a merged résumé of a track with its stored draft and readability findings
(F11.1). Analysing one is F10.3 steps 3–7 on that draft: the draft is matched to the
master database (a bullet that is the master's keeps its id, a new one gets a temporary
id and a snapshot), read in the posting's language the way an attempt is read, and
scored through `score_track` — the same path, so the two can never score differently.
There is no extraction call (the draft is stored) and no readability scan (the findings
are stored); the grading call is answered by the content-hash cache when the evidence is
one the cache has seen, and the gap prose is the only call an attempt skips.

The track stays the bank the advice draws on (F11.1): the master database is what the
ceiling, the requirement note and the recommendations compare the file with.
"""

import uuid

from sqlalchemy.orm import Session

from src.analysis import Analysis, Preparation, prepare, score_track
from src.attempt_track import build_ephemeral
from src.cv_context import cv_context
from src.extract.client import CallOptions
from src.ingest.draft import ResumeDraft
from src.models import Resume, Track
from src.parse.gate import ParseReport


def analyze_cv(
    profile_id: uuid.UUID,
    session: Session,
    *,
    jd_text: str,
    track: Track,
    resume: Resume,
    chosen: str,
    company: str | None = None,
    title: str | None = None,
    prepared: Preparation | None = None,
    model: str | None = None,
    options: CallOptions | None = None,
) -> Analysis:
    """Analyse one posting against one stored CV of `track` (F11.2).

    `prepared` is the extraction when somebody already made it ("Proponer línea" does,
    F11.6); without it the posting is extracted here (one cached call). `chosen` is
    `"latest"` or `"explicit"`, recorded in the report so a re-render can say how the
    CV was picked. The caller has already resolved the CV through `resolve_cv`, which is
    where ownership is decided; the draft it holds is the one scored.
    """
    if not resume.draft:
        raise ValueError("a CV without a draft cannot be analysed (F11.2)")
    if prepared is None:
        prepared = prepare(profile_id, session, jd_text=jd_text, model=model, options=options)

    draft = ResumeDraft.model_validate(resume.draft)
    ephemeral = build_ephemeral(
        profile_id, session, track=track, lang=prepared.jd.language, draft=draft
    )
    gate = ParseReport.from_dict(resume.gate) if resume.gate else None
    return score_track(
        profile_id,
        session,
        jd_text=jd_text,
        prepared=prepared,
        company=company,
        title=title,
        gate=gate,
        model=model,
        options=options,
        track=track,
        bullets=list(ephemeral.bullets),
        document=list(ephemeral.document),
        interpret=True,
        extra_roles=ephemeral.roles,
        cv=cv_context(resume, ephemeral, chosen=chosen),
    )
