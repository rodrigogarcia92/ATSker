"""What a CV analysis knows about its file (PRD F11.2–F11.4).

A CV is a stored draft read the way an attempt reads a file (F10.3 step 4). The scorer
takes this context next to the document: the ids of the master bullets the file
carries (the ceiling's fingerprint and F7.2's "not in the CV" read them), how the file
was read (snapshots and role matching, which the report keeps) and the file's language
(the F4.2 alert compares it with the posting's).

`cv_document` rebuilds the same document from the stored draft at view time, so the
ceiling can be re-checked against today's master data without a model call.
"""

import hashlib
import json
import uuid
from collections.abc import Mapping
from dataclasses import dataclass

from sqlalchemy.orm import Session

from src.attempt_track import EphemeralTrack, build_ephemeral
from src.documents import DocumentUnit
from src.ingest.draft import ResumeDraft
from src.models import Resume, Track
from src.scoping import owned_row

CHOSEN_VALUES = ("latest", "explicit")


def draft_digest(draft: Mapping[str, object]) -> str:
    """A short, stable hash of a stored draft.

    The report keeps it beside the CV it scored: marks on the CV pane are offsets into
    that draft, so a draft edited afterwards must not be drawn over with stale offsets
    (decision 5 of STOP 0).
    """
    encoded = json.dumps(draft, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CvContext:
    """The CV an analysis scores: who it is, how it was read, what it carries."""

    resume_id: str
    filename: str
    chosen: str
    draft_sha: str
    # The file's own language (`draft.language`), not the language it was read in.
    language: str
    # Master bullet ids the file carries unchanged, in the file's order; the ceiling's
    # fingerprint reads these (a temporary id changes on every run).
    matched_ids: tuple[str, ...]
    # Those plus the master bullets a reworded file bullet stands for: "in the CV" for
    # F7.2 and F11.5, so a reworded bullet is not advised as missing.
    represented_ids: tuple[str, ...]
    snapshots: tuple[dict[str, object], ...]
    role_matching: tuple[dict[str, object], ...]

    def header(self) -> dict[str, object]:
        """The report's `cv` block: the file name survives a deleted CV (F11.3)."""
        return {
            "resume_id": self.resume_id,
            "filename": self.filename,
            "chosen": self.chosen,
            "draft_sha": self.draft_sha,
        }


def cv_context(resume: Resume, ephemeral: EphemeralTrack, *, chosen: str) -> CvContext:
    """The context for `resume` once its draft has been read as `ephemeral`."""
    draft = ResumeDraft.model_validate(resume.draft)
    return CvContext(
        resume_id=str(resume.id),
        filename=resume.filename,
        chosen=chosen if chosen in CHOSEN_VALUES else "explicit",
        draft_sha=draft_digest(resume.draft or {}),
        language=draft.language or "es",
        matched_ids=tuple(row.id for row in ephemeral.snapshots if not row.temporary),
        represented_ids=ephemeral.represented_ids,
        snapshots=tuple(row.to_dict() for row in ephemeral.snapshots),
        role_matching=tuple(dict(row) for row in ephemeral.role_matching),
    )


def cv_document(
    profile_id: uuid.UUID,
    session: Session,
    *,
    report: Mapping[str, object],
    track: Track | None,
    lang: str,
) -> tuple[list[DocumentUnit], list[str]] | None:
    """The document and master-matched ids of a CV report's file, as read now.

    None when the report is not a CV analysis, or when its file is no longer what was
    scored: the résumé is gone, has no draft, or its draft changed since (the digest
    differs). The caller then keeps the stored ceiling as it is.
    """
    header = report.get("cv")
    if not isinstance(header, Mapping):
        return None
    resume = owned_row(Resume, session, profile_id, str(header.get("resume_id") or ""))
    if resume is None or not resume.draft:
        return None
    stored = header.get("draft_sha")
    if stored and draft_digest(resume.draft) != stored:
        return None
    ephemeral = build_ephemeral(
        profile_id, session, track=track, lang=lang, draft=ResumeDraft.model_validate(resume.draft)
    )
    return list(ephemeral.document), [row.id for row in ephemeral.snapshots if not row.temporary]
