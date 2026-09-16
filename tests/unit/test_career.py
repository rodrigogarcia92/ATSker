"""Career-data behaviour: chips, metrics, soft delete, linking, isolation."""

from src.bullets import get_bullet, list_bullets, set_bullet_active
from src.roles import list_roles, set_role_active
from src.stories import linked_bullet_ids, set_linked_bullets
from src.vocabulary import list_unmapped
from tests.conftest import login


def test_saving_a_bullet_resolves_chips_and_extracts_metrics(session, career):
    bullet = career.first_bullet

    assert bullet.skills == ["python"]
    assert bullet.metrics == ["30%"]
    assert [term.term for term in list_unmapped(session)] == ["cobalto"]


def test_deactivating_a_bullet_hides_it_from_active_lists_but_keeps_the_row(session, career):
    profile_id, bullet_id = career.first_profile.id, career.first_bullet.id

    set_bullet_active(profile_id, session, bullet_id, active=False)

    assert list_bullets(profile_id, session, active_only=True) == []
    assert get_bullet(profile_id, session, bullet_id) is not None
    assert len(list_bullets(profile_id, session, active_only=False)) == 1


def test_deactivating_a_role_keeps_it_for_historical_reports(session, career):
    profile_id, role_id = career.first_profile.id, career.first_role.id

    set_role_active(profile_id, session, role_id, active=False)

    assert list_roles(profile_id, session, active_only=True) == []
    assert [role.id for role in list_roles(profile_id, session, active_only=False)] == [role_id]


def test_linking_a_story_to_another_profiles_bullet_is_ignored(session, career):
    """A link must never widen access: the bullet belongs to the other account."""
    linked = set_linked_bullets(
        career.first_profile.id, session, career.first_story.id, [career.second_bullet.id]
    )

    assert linked == []
    assert linked_bullet_ids(career.first_profile.id, session, career.first_story.id) == []


def test_data_access_returns_nothing_across_profiles(session, career):
    other = career.second_profile.id
    first = career.first_profile.id

    assert get_bullet(other, session, career.first_bullet.id) is None
    assert [bullet.id for bullet in list_bullets(other, session)] == [career.second_bullet.id]
    assert career.first_bullet.id not in {bullet.id for bullet in list_bullets(other, session)}
    assert get_bullet(first, session, career.first_bullet.id) is not None
    assert get_bullet(first, session, career.second_bullet.id) is None


def test_pages_render_own_data_and_404_for_another_profile(client, career):
    login(client, career.first.email)

    assert client.get(f"/roles/{career.first_role.id}").status_code == 200
    assert client.get(f"/roles/{career.second_role.id}").status_code == 404
    assert client.get(f"/bullets/{career.first_bullet.id}/edit").status_code == 200
    assert client.get(f"/bullets/{career.second_bullet.id}/edit").status_code == 404
    assert client.get(f"/stories/{career.first_story.id}").status_code == 200
    assert client.get(f"/stories/{career.second_story.id}").status_code == 404
    assert client.get(f"/letters/{career.first_letter.id}/edit").status_code == 200
    assert client.get(f"/letters/{career.second_letter.id}/edit").status_code == 404


def test_create_edit_and_delete_round_trip_through_the_browser(client, career):
    login(client, career.first.email)

    created = client.post(
        "/roles",
        data={"title": "Consultora", "employer": "Initech", "start_date": "2021-03-01"},
        follow_redirects=False,
    )
    assert created.status_code == 303
    role_url = created.headers["location"]

    detail = client.get(role_url)
    assert "Consultora" in detail.text and "Initech" in detail.text

    bullet = client.post(
        f"{role_url}/bullets",
        data={"text_es": "Automaticé 12 informes con SQL", "chips": "sql, reactor"},
        follow_redirects=False,
    )
    assert bullet.status_code == 303
    assert "12 informes" in client.get(role_url, follow_redirects=True).text

    letter = client.post(
        "/letters",
        data={
            "name": "Consultoría",
            "applies_when": "Para consultoría de datos",
            "presentation": "Me presento.",
            "achievements": "Logros.",
        },
        follow_redirects=False,
    )
    assert letter.status_code == 303
    letter_id = letter.headers["location"].split("/")[2]

    assert client.post(f"/letters/{letter_id}/delete", follow_redirects=False).status_code == 303
    assert client.get(f"/letters/{letter_id}/edit").status_code == 404


def test_bullet_needs_text_in_at_least_one_language(client, career):
    login(client, career.first.email)

    response = client.post(
        f"/roles/{career.first_role.id}/bullets",
        data={"text_es": "   ", "text_en": "", "chips": ""},
        follow_redirects=False,
    )

    assert response.status_code == 422


def test_detect_button_fills_chips_from_the_typed_text(client, career):
    login(client, career.first.email)

    response = client.post(
        "/bullets/detect",
        data={
            "role_id": str(career.first_role.id),
            "text_es": "Modelos de machine learning en producción",
            "chips": "",
        },
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert "machine learning" in response.text


def test_deactivated_roles_stay_visible_on_the_list_page(client, career):
    login(client, career.first.email)

    client.post(f"/roles/{career.first_role.id}/active", data={}, follow_redirects=False)

    page = client.get("/roles")
    assert "Analista de datos" in page.text
    assert "inactivo" in page.text
