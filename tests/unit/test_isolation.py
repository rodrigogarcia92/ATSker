"""Profile isolation between the two users (PRD F1).

The requirement is that user A gets 404 — not 403 — for user B's records by id, so
that the response says nothing about whether the id exists. The profile itself is
addressed as `/profile` without an id, so the records under test are the career
rows: roles, bullets, stories, letter templates, tracks and summaries.
"""

from src.tracks import track_bullets
from tests.conftest import login


def test_another_users_records_are_404_and_own_records_are_200(client, career):
    login(client, career.first.email)

    assert client.get(f"/roles/{career.first_role.id}").status_code == 200
    assert client.get(f"/roles/{career.second_role.id}").status_code == 404
    assert client.get(f"/bullets/{career.first_bullet.id}/edit").status_code == 200
    assert client.get(f"/bullets/{career.second_bullet.id}/edit").status_code == 404
    assert client.get(f"/stories/{career.first_story.id}").status_code == 200
    assert client.get(f"/stories/{career.second_story.id}").status_code == 404
    assert client.get(f"/letters/{career.first_letter.id}/edit").status_code == 200
    assert client.get(f"/letters/{career.second_letter.id}/edit").status_code == 404


def test_writes_against_another_users_records_are_refused(client, career):
    login(client, career.first.email)

    update = client.post(
        f"/stories/{career.second_story.id}",
        data={"title": "Robada", "body": "no debería guardarse"},
        follow_redirects=False,
    )
    delete = client.post(f"/stories/{career.second_story.id}/delete", follow_redirects=False)
    toggle = client.post(
        f"/bullets/{career.second_bullet.id}/active", data={}, follow_redirects=False
    )

    assert update.status_code == 404
    assert delete.status_code == 404
    assert toggle.status_code == 404


def test_unknown_and_malformed_ids_are_404(client, career):
    login(client, career.first.email)

    assert client.get("/roles/2f0c1c1e-0000-4000-8000-000000000000").status_code == 404
    assert client.get("/roles/not-a-uuid").status_code == 404
    assert client.get("/stories/not-a-uuid").status_code == 404


def test_anonymous_request_is_redirected_to_login(client, career):
    response = client.get(f"/roles/{career.first_role.id}", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_profile_page_shows_only_the_signed_in_user(client, career):
    login(client, career.first.email)

    page = client.get("/profile").text

    assert "Ana" in page
    assert "Bea" not in page


def test_another_users_track_is_404_on_every_route(client, session, career):
    """F4 adds a second addressable record; it answers exactly like the first (F1)."""
    login(client, career.first.email)
    track_id = career.second_track.id

    assert client.get(f"/tracks/{career.first_track.id}").status_code == 200
    assert client.get(f"/tracks/{track_id}").status_code == 404
    assert client.get(f"/tracks/{track_id}/edit").status_code == 404
    assert client.get(f"/tracks/{track_id}/bullets").status_code == 404
    assert client.post(f"/tracks/{track_id}", data={"name": "Robada"}).status_code == 404
    assert client.post(f"/tracks/{track_id}/clone", data={"name": "Copia"}).status_code == 404
    assert client.post(f"/tracks/{track_id}/active", data={"active": "off"}).status_code == 404
    assert (
        client.post(
            f"/tracks/{track_id}/bullets",
            data={"pick": str(career.second_bullet.id), "row": str(career.second_bullet.id)},
        ).status_code
        == 404
    )

    session.expire_all()
    assert career.second_track.name == "Riesgo"
    assert career.second_track.active is True
    assert [
        bullet.id
        for bullet in track_bullets(
            career.second_profile.id, session, career.second_track.id
        )
    ] == [career.second_bullet.id]


def test_another_users_summary_is_404_on_every_route(client, session, career):
    """F2.7's pool rows are addressed by id and answer like every other record (F1)."""
    login(client, career.first.email)
    summary_id = career.second_summary.id

    assert client.get(f"/summaries/{career.first_summary.id}").status_code == 200
    assert client.get(f"/summaries/{summary_id}").status_code == 404
    update = client.post(
        f"/summaries/{summary_id}",
        data={"text": "Robado", "lang": "es"},
        follow_redirects=False,
    )
    toggle = client.post(f"/summaries/{summary_id}/active", data={}, follow_redirects=False)

    assert update.status_code == 404
    assert toggle.status_code == 404

    session.expire_all()
    assert career.second_summary.text == "Modelos de riesgo en producción."
    assert career.second_summary.active is True
