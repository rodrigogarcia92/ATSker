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
from dataclasses import dataclass

from sqlalchemy.orm import Session

from src.analysis import Analysis, Preparation, prepare, score_track
from src.attempt_track import build_ephemeral
from src.cv_context import cv_context
from src.documents import document_headline
from src.extract.client import CallOptions
from src.ingest.draft import ResumeDraft
from src.models import Resume, Track
from src.parse.gate import ParseReport
from src.resumes import latest_cv
from src.roles import list_roles, role_title
from src.score.keywords import keyword_context
from src.score.title import title_alignment
from src.tracks import list_tracks


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


@dataclass(frozen=True)
class TrackProposal:
    """One track's cheap score on its latest CV (F11.6): Title and Keywords, 0 to 1."""

    track: Track
    resume: Resume
    title: float
    keywords: float

    @property
    def total(self) -> float:
        return self.title + self.keywords


def rank_tracks(
    profile_id: uuid.UUID, session: Session, *, prepared: Preparation
) -> list[TrackProposal]:
    """Rank the active tracks that have a CV by Title + Keywords on their latest CV.

    F7.1's pre-ranking, moved from the track's whole material to the file (F11.6): the
    two `w4` sub-scores that need no provider, so there is no grading call and the answer
    is the same every time. A track without a CV is not ranked — it cannot be analysed.
    The tie-break is the track's name.
    """
    jd = prepared.jd
    roles = list_roles(profile_id, session, active_only=True)
    ranked: list[TrackProposal] = []
    for track in list_tracks(profile_id, session, active_only=True):
        resume = latest_cv(profile_id, session, track.id)
        if resume is None or not resume.draft:
            continue
        ephemeral = build_ephemeral(
            profile_id,
            session,
            track=track,
            lang=jd.language,
            draft=ResumeDraft.model_validate(resume.draft),
        )
        document = ephemeral.document
        title = title_alignment(
            jd,
            headline=document_headline(document),
            roles=[
                (role_title(role, jd.language)[0], role.start_date, role.end_date)
                for role in roles
            ],
            aliases=prepared.aliases,
        )
        keywords = keyword_context(jd, [unit.text for unit in document], aliases=prepared.aliases)
        ranked.append(TrackProposal(track, resume, title.value, keywords.value))
    return sorted(ranked, key=lambda row: (-row.total, row.track.name))
