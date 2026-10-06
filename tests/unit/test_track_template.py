"""F8 (2026-10-04): one letter template per track, its page, and Cartas by track.

"One per track" lives in code, not in the schema, so these tests hold the rule: saving
never makes a second row, choosing one unlinks the others without deleting them, and
nothing on these pages calls a model. Every id is the owner's: another profile's track
or template is a 404 on each route.
"""

import re

from sqlalchemy import select

from src.letters import (
    create_letter,
    get_letter,
    save_track_template,
    template_status,
    track_template,
    track_templates,
    use_template_for_track,
)
from src.models import LetterTemplate
from src.tracks import create_track, get_track, set_track_active, update_track
from tests.conftest import login


def linked_to(session, track) -> list[LetterTemplate]:
    return list(session.scalars(select(LetterTemplate).where(LetterTemplate.track_id == track.id)))


def link(session, profile_id, track, *, name="Vieja", presentation="Hola.", achievements="Logros."):
    """A template linked to the track, as the N8 data has them (possibly several)."""
    letter = create_letter(
        profile_id,
        session,
        name=name,
        applies_when="",
        presentation=presentation,
        achievements=achievements,
        lang=track.lang,
        track_id=track.id,
    )
    session.commit()
    return letter


# --- data access -------------------------------------------------------------------


def test_save_track_template_creates_once_then_updates_the_same_row(session, career):
    profile_id, track = career.first_profile.id, career.first_track

    first = save_track_template(
        profile_id, session, track, presentation=" Soy Ana. ", achievements="Logré 30%."
    )
    second = save_track_template(
        profile_id, session, track, presentation="Soy Ana, analista.", achievements="Logré 40%."
    )
    session.commit()

    assert second.id == first.id, "never a second template for the track"
    assert len(linked_to(session, track)) == 1
    assert (second.presentation, second.achievements) == ("Soy Ana, analista.", "Logré 40%.")
    assert second.track_id == track.id


def test_a_saved_template_follows_the_tracks_language_name_and_when_to_use(session, career):
    profile_id, track = career.first_profile.id, career.first_track
    save_track_template(profile_id, session, track, presentation="Hola.", achievements="Logros.")
    update_track(
        profile_id,
        session,
        track.id,
        name="Data Analyst",
        applies_when="Analytics roles",
        lang="en",
        headline_es=track.headline_es,
    )

    letter = save_track_template(
        profile_id, session, get_track(profile_id, session, track.id),
        presentation="Hello.", achievements="Results.",
    )

    assert (letter.lang, letter.name, letter.applies_when) == (
        "en",
        "Data Analyst",
        "Analytics roles",
    )


def test_save_track_template_refuses_another_profiles_track(session, career):
    saved = save_track_template(
        career.first_profile.id,
        session,
        career.second_track,
        presentation="x",
        achievements="y",
    )

    assert saved is None
    assert linked_to(session, career.second_track) == []


def test_several_linked_templates_give_a_stable_first_and_choosing_unlinks_the_rest(
    session, career
):
    profile_id, track = career.first_profile.id, career.first_track
    one = link(session, profile_id, track, name="A", presentation="Primera.")
    two = link(session, profile_id, track, name="B", presentation="Segunda.")

    listed = track_templates(profile_id, session, track)

    assert {letter.id for letter in listed} == {one.id, two.id}
    assert track_template(profile_id, session, track).id == listed[0].id
    assert track_template(profile_id, session, track).id == track_template(
        profile_id, session, track
    ).id, "the same one every time"

    chosen = use_template_for_track(profile_id, session, two.id, track)
    session.commit()

    assert chosen.id == two.id
    assert [letter.id for letter in linked_to(session, track)] == [two.id]
    assert get_letter(profile_id, session, one.id) is not None, "nothing is deleted"
    assert get_letter(profile_id, session, one.id).track_id is None
    assert get_letter(profile_id, session, one.id).presentation == "Primera."


def test_using_a_template_sets_its_language_to_the_tracks(session, career):
    profile_id, track = career.first_profile.id, career.first_track
    stray = create_letter(
        profile_id,
        session,
        name="Datos",
        applies_when="",
        presentation="x",
        achievements="y",
        lang="en",
    )

    use_template_for_track(profile_id, session, stray.id, track)

    assert (stray.track_id, stray.lang) == (track.id, track.lang)


def test_use_template_for_track_refuses_another_profiles_template_or_track(session, career):
    profile_id = career.first_profile.id

    assert use_template_for_track(
        profile_id, session, career.second_letter.id, career.first_track
    ) is None
    assert use_template_for_track(
        profile_id, session, career.first_letter.id, career.second_track
    ) is None
    assert career.first_letter.track_id is None
    assert career.second_letter.track_id is None


def test_the_four_statuses(session, career):
    profile_id, track = career.first_profile.id, career.first_track

    assert template_status(profile_id, session, track) == "missing", "no template"

    letter = link(session, profile_id, track, presentation="", achievements="Logros.")
    assert template_status(profile_id, session, track) == "missing", "an empty paragraph"

    letter.presentation = "Hola."
    session.commit()
    assert template_status(profile_id, session, track) == "ready"

    link(session, profile_id, track, name="Otra")
    assert template_status(profile_id, session, track) == "several"

    other = create_track(profile_id, session, name="Solo", applies_when="", lang="es")
    english = link(session, profile_id, other)
    english.lang = "en"
    session.commit()
    assert template_status(profile_id, session, other) == "other_lang"


# --- the track's letter page -------------------------------------------------------


def test_the_track_letter_page_renders_the_form_with_its_hints(client, career):
    login(client, career.first.email)

    page = client.get(f"/tracks/{career.first_track.id}/letter").text

    assert "Idioma de la carta: español" in page
    assert "≤ 70 palabras" in page
    assert "80–160 palabras, un solo párrafo, con un logro principal y sus números" in page
    assert "[PUESTO] / [ROLE]" in page, "the placeholder legend"
    assert 'name="presentation"' in page and 'name="achievements"' in page


def test_saving_the_track_letter_redirects_to_cartas_with_a_status_line(
    client, session, career
):
    login(client, career.first.email)
    url = f"/tracks/{career.first_track.id}/letter"

    saved = client.post(
        url, data={"presentation": "Soy Ana.", "achievements": "Logré 30%."}, follow_redirects=False
    )
    client.post(url, data={"presentation": "Soy Ana, otra vez.", "achievements": "Logré 30%."})

    assert saved.status_code == 303
    assert saved.headers["location"].startswith("/letters?notice=saved")
    session.expire_all()
    rows = linked_to(session, career.first_track)
    assert len(rows) == 1 and rows[0].presentation == "Soy Ana, otra vez."
    page = client.get(saved.headers["location"]).text
    assert "Carta de «Analista de datos» guardada." in page
    assert 'role="status"' in page


def test_a_status_line_for_a_track_that_is_not_yours_says_nothing(client, career):
    login(client, career.first.email)

    page = client.get(f"/letters?notice=saved&track={career.second_track.id}").text

    assert "guardada" not in page
    assert "Riesgo" not in page


def test_several_linked_templates_are_listed_with_usar_esta(client, session, career):
    profile_id, track = career.first_profile.id, career.first_track
    link(session, profile_id, track, name="A", presentation="Primera presentación.")
    second = link(session, profile_id, track, name="B", presentation="Segunda presentación.")
    login(client, career.first.email)

    page = client.get(f"/tracks/{track.id}/letter").text

    assert "Primera presentación." in page and "Segunda presentación." in page
    assert page.count("Usar esta") == 1, "the one in use has no button"
    chosen = [letter for letter in track_templates(profile_id, session, track)][-1]
    done = client.post(
        f"/tracks/{track.id}/letter/use",
        data={"template_id": str(chosen.id)},
        follow_redirects=False,
    )
    assert done.status_code == 303 and done.headers["location"].endswith("?chosen=1")
    session.expire_all()
    assert [letter.id for letter in linked_to(session, track)] == [chosen.id]
    assert "Las demás pasaron a «Sin línea»" in client.get(done.headers["location"]).text
    assert second.id is not None


def test_a_template_in_another_language_gets_an_alert(client, session, career):
    profile_id, track = career.first_profile.id, career.first_track
    letter = link(session, profile_id, track)
    letter.lang = "en"
    session.commit()
    login(client, career.first.email)

    page = client.get(f"/tracks/{track.id}/letter").text

    assert "Esta carta está en inglés y la línea en español: edítala o autogenérala." in page
    assert 'role="alert"' in page


def test_every_new_route_is_a_404_for_another_profiles_track_or_template(
    client, session, career
):
    login(client, career.first.email)
    foreign = career.second_track.id

    assert client.get(f"/tracks/{foreign}/letter").status_code == 404
    assert client.post(
        f"/tracks/{foreign}/letter", data={"presentation": "x", "achievements": "y"}
    ).status_code == 404
    assert client.post(
        f"/tracks/{foreign}/letter/use", data={"template_id": str(career.first_letter.id)}
    ).status_code == 404
    assert client.post(
        f"/tracks/{career.first_track.id}/letter/use",
        data={"template_id": str(career.second_letter.id)},
    ).status_code == 404
    assert client.post(
        f"/letters/{career.second_letter.id}/assign",
        data={"track_id": str(career.first_track.id)},
    ).status_code == 404
    assert client.post(
        f"/letters/{career.first_letter.id}/assign", data={"track_id": str(foreign)}
    ).status_code == 404
    session.expire_all()
    assert linked_to(session, career.second_track) == []
    assert get_letter(career.first_profile.id, session, career.first_letter.id).track_id is None


# --- Cartas ------------------------------------------------------------------------


def test_cartas_shows_three_sections_and_offers_crear_for_a_track_without_a_letter(
    client, session, career
):
    login(client, career.first.email)

    page = client.get("/letters").text

    assert page.index("Bloques comunes") < page.index("Carta por línea") < page.index(
        ">Sin línea<"
    )
    assert f'href="/tracks/{career.first_track.id}/letter"' in page
    assert "Crear carta" in page and "Falta" in page
    assert "Asignar a una línea" in page, "the old 'Datos' template can be assigned"


def test_cartas_marks_a_ready_track_and_collapses_inactive_ones(client, session, career):
    profile_id = career.first_profile.id
    save_track_template(
        profile_id, session, career.first_track, presentation="Hola.", achievements="Logros."
    )
    quiet = create_track(profile_id, session, name="Archivado", applies_when="", lang="es")
    set_track_active(profile_id, session, quiet.id, active=False)
    session.commit()
    login(client, career.first.email)

    page = client.get("/letters").text

    assert "✓ Lista" in page and "Editar carta" in page
    assert "Líneas inactivas (1)" in page
    assert page.index("Líneas inactivas") < page.index("Archivado")


def test_assigning_offers_only_active_tracks_of_the_templates_language(client, session, career):
    profile_id = career.first_profile.id
    create_track(profile_id, session, name="Data Analyst", applies_when="", lang="en")
    dormant = create_track(profile_id, session, name="Dormido", applies_when="", lang="es")
    set_track_active(profile_id, session, dormant.id, active=False)
    session.commit()
    login(client, career.first.email)

    page = client.get("/letters").text

    select = re.search(
        rf'<select id="assign-{career.first_letter.id}".*?</select>', page, re.DOTALL
    ).group(0)
    assert "Analista de datos" in select, "same language, active"
    assert "Data Analyst" not in select, "the other language is not offered"
    assert "Dormido" not in select, "an inactive track is not offered"


def test_a_template_with_no_track_in_its_language_says_so(client, session, career):
    letter = career.first_letter
    letter.lang = "en"
    session.commit()
    login(client, career.first.email)

    page = client.get("/letters").text

    assert "No hay líneas activas en inglés" in page
    assert f'id="assign-{letter.id}"' not in page


def test_assigning_links_the_template_and_says_where_the_old_one_went(client, session, career):
    profile_id, track = career.first_profile.id, career.first_track
    incumbent = link(session, profile_id, track, name="Actual", presentation="La que ya estaba.")
    login(client, career.first.email)

    done = client.post(
        f"/letters/{career.first_letter.id}/assign",
        data={"track_id": str(track.id)},
        follow_redirects=False,
    )

    assert done.status_code == 303
    session.expire_all()
    assert [letter.id for letter in linked_to(session, track)] == [career.first_letter.id]
    assert get_letter(profile_id, session, incumbent.id).track_id is None
    page = client.get(done.headers["location"]).text
    assert "La carta que tenía la línea pasó a «Sin línea»" in page
    assert "La que ya estaba." in page, "the displaced template is listed under Sin línea"


def test_assigning_to_a_track_of_the_other_language_is_refused(client, session, career):
    english = create_track(
        career.first_profile.id, session, name="Data Analyst", applies_when="", lang="en"
    )
    session.commit()
    login(client, career.first.email)

    refused = client.post(
        f"/letters/{career.first_letter.id}/assign", data={"track_id": str(english.id)}
    )

    assert refused.status_code == 400
    session.expire_all()
    assert career.first_letter.track_id is None


def test_a_template_linked_to_a_track_is_edited_on_the_tracks_page(client, session, career):
    letter = link(session, career.first_profile.id, career.first_track)
    login(client, career.first.email)

    edit = client.get(f"/letters/{letter.id}/edit", follow_redirects=False)
    stale = client.post(
        f"/letters/{letter.id}",
        data={"name": "x", "applies_when": "x", "presentation": "x", "achievements": "x"},
        follow_redirects=False,
    )

    assert edit.status_code == 303
    assert edit.headers["location"] == f"/tracks/{career.first_track.id}/letter"
    assert stale.status_code == 303
    session.expire_all()
    assert get_letter(career.first_profile.id, session, letter.id).presentation == "Hola."


def test_the_form_for_an_unlinked_template_has_no_track_select_and_saving_keeps_it_unlinked(
    client, session, career
):
    login(client, career.first.email)
    letter = career.first_letter

    page = client.get(f"/letters/{letter.id}/edit").text
    saved = client.post(
        f"/letters/{letter.id}",
        data={
            "name": "Datos",
            "applies_when": "Nota",
            "presentation": "Nueva.",
            "achievements": "Logros.",
            "lang": "es",
            "track_id": str(career.first_track.id),
        },
        follow_redirects=False,
    )

    assert 'name="track_id"' not in page
    assert saved.status_code == 303
    session.expire_all()
    assert get_letter(career.first_profile.id, session, letter.id).track_id is None
    assert get_letter(career.first_profile.id, session, letter.id).presentation == "Nueva."


def test_new_template_routes_are_gone_and_inicio_links_to_cartas(client, career):
    login(client, career.first.email)

    assert client.get("/letters/new").status_code in (404, 405)
    assert client.post(
        "/letters",
        data={"name": "x", "applies_when": "x", "presentation": "x", "achievements": "x"},
    ).status_code in (404, 405)
    dashboard = client.get("/dashboard").text
    assert "/letters/new" not in dashboard
    assert re.search(r'<a href="/letters"[^>]*>\s*Cartas\s*</a>', dashboard)
    assert "Nueva plantilla" not in client.get("/letters").text


# --- Puestos objetivo --------------------------------------------------------------


def test_the_track_list_and_detail_show_the_letter_status_and_its_link(
    client, session, career
):
    profile_id, track = career.first_profile.id, career.first_track
    login(client, career.first.email)

    missing_list = client.get("/tracks").text
    missing_detail = client.get(f"/tracks/{track.id}").text
    long_text = "Presentación " + "larga " * 40
    save_track_template(profile_id, session, track, presentation=long_text, achievements="Logros.")
    session.commit()
    ready_list = client.get("/tracks").text
    ready_detail = client.get(f"/tracks/{track.id}").text

    assert "Carta:" in missing_list and "Falta" in missing_list
    assert "Crear carta" in missing_detail and "Falta" in missing_detail
    assert "✓ Lista" in ready_list
    assert "✓ Lista" in ready_detail and "Editar carta" in ready_detail
    assert f'href="/tracks/{track.id}/letter"' in ready_detail
    shown = long_text.strip()[:120]
    assert shown in ready_detail and long_text.strip()[:121] not in ready_detail
