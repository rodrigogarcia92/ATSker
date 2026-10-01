"""Bullet matching and the ephemeral track (PRD F10.3 step 3, A4, B.2).

An unchanged export must produce exactly the document the analysis scored; a new or
changed bullet must get a temporary id and carry its own text snapshot, so the file's
wording is what the attempt is graded on.
"""

import uuid
from decimal import Decimal

from src.applications import create_application
from src.attempt_track import ephemeral_track
from src.documents import track_document
from src.ingest.draft import DraftBullet, DraftRole, ResumeDraft


def _application(profile_id, session, track_id):
    application = create_application(
        profile_id,
        session,
        jd_text="Una oferta",
        jd_hash=f"sha256:{uuid.uuid4().hex}",
        report={"jd": {"language": "es"}},
        weights_version="w4",
        prompt_versions={},
        token_cost_usd=Decimal("0"),
        title="Puesto",
        track_id=track_id,
    )
    session.commit()
    return application


def _draft(career, *, bullet_text: str | None = None) -> ResumeDraft:
    return ResumeDraft(
        language="es",
        headline="Analista de datos",
        summary=None,
        skills=[],
        roles=[
            DraftRole(
                employer="Acme",
                title="Analista de datos",
                bullets=[DraftBullet(text=bullet_text or career.first_bullet.text_es)],
            )
        ],
    )


def test_an_unchanged_export_is_the_track_document(session, career):
    application = _application(career.first_profile.id, session, career.first_track.id)

    result = ephemeral_track(
        career.first_profile.id, session, application=application, draft=_draft(career)
    )

    expected = track_document(career.first_profile.id, session, career.first_track, "es")
    assert result.document == tuple(expected)
    assert [snapshot.temporary for snapshot in result.snapshots] == [False]
    assert result.snapshots[0].id == str(career.first_bullet.id)


def test_a_reworded_bullet_gets_a_temporary_id_and_its_snapshot(session, career):
    application = _application(career.first_profile.id, session, career.first_track.id)
    reworded = f"{career.first_bullet.text_es} y SQL"

    result = ephemeral_track(
        career.first_profile.id,
        session,
        application=application,
        draft=_draft(career, bullet_text=reworded),
    )

    snapshot = result.snapshots[0]
    assert snapshot.temporary is True
    assert snapshot.text == reworded
    assert snapshot.id != str(career.first_bullet.id)

    unit = next(unit for unit in result.document if unit.kind == "bullet")
    assert unit.source_id == snapshot.id
    assert unit.text == reworded
