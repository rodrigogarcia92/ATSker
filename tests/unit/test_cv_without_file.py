"""A CV saved from an attempt has no file bytes (PRD F11.7, F11.10, migration 0018).

Every reader of `resumes.file_bytes` has to cope: the "show me where" views say the
file was not kept, the retry does not try to parse nothing, and the model accepts NULL.
"""

from src.models import Resume
from src.resumes import create_resume
from tests.conftest import login

FINDING = {
    "check": "invisible_text",
    "severity": "blocker",
    "detail": {"page": 1, "boxes": [[10, 10, 50, 20]]},
}


def _file_less_cv(session, career) -> Resume:
    resume = create_resume(
        career.first_profile.id,
        session,
        filename="attempt.docx",
        data=None,
        sha256="a" * 64,
        track_id=career.first_track.id,
        gate={"findings": [FINDING]},
        draft={"language": "es", "roles": []},
    )
    session.commit()
    return resume


def test_a_resume_row_accepts_no_file_bytes(session, career):
    resume = _file_less_cv(session, career)

    session.refresh(resume)

    assert resume.file_bytes is None
    assert resume.source_attempt_id is None


def test_show_me_where_says_the_file_was_not_kept(client, session, career):
    resume = _file_less_cv(session, career)
    login(client, "persona2@example.com")

    page = client.get(f"/import/{resume.id}/findings/0")
    image = client.get(f"/import/{resume.id}/findings/0/page.png")

    assert page.status_code == 404
    assert "no se conservó" in page.text
    assert image.status_code == 404


def test_retry_on_a_file_less_cv_goes_back_to_the_review(client, session, career):
    resume = _file_less_cv(session, career)
    resume.draft = None
    session.commit()
    login(client, "persona2@example.com")

    response = client.post(f"/import/{resume.id}/retry", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == f"/import/{resume.id}"
