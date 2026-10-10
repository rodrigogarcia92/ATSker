"""F8 "Autogenerar": the common blocks by code, the track's template by one call.

The provider is stubbed. The common blocks never reach it (the model is patched to fail if
called); the template draft makes exactly one call, fills the two fields and stores nothing
until Guardar. The three validators and the shape rules (≤ 70 words, 80–160 words, one
paragraph) decide what is flagged beside each paragraph.
"""

import json
import re

import pytest
from sqlalchemy import func, select

from src.extract import client as extract_client
from src.extract import generation
from src.letters import get_letter_settings, save_letter_settings, track_template
from src.models import LetterSettings, LetterTemplate
from src.tracks import set_track_active
from tests.conftest import login

PRESENTATION = "Analista de datos con cinco años automatizando reportes para dirección."

# One paragraph, inside the 80–160 word window, grounded in the track's own bullet.
ACHIEVEMENTS = (
    "Reduje el tiempo de cierre un 30% automatizando los reportes con Python, y llevé "
    "el proceso manual que hacía dirección cada mes a una rutina que corre sola. El "
    "tablero que mantuve en producción sirvió para priorizar carteras y para explicar "
    "a negocio por qué la cobranza se movía como se movía, y el equipo de riesgo lo "
    "usó para decidir sin esperar el informe de fin de mes, con el mismo cierre que "
    "antes tardaba días y que ahora está listo el primer día hábil, sin rehacer nada "
    "a mano y sin depender de una sola persona para que salga."
)


class Provider:
    def __init__(self, payload: dict | None = None):
        self.calls: list[dict] = []
        self.payload = payload or {}

    def __call__(self, payload: dict, api_key: str) -> dict:
        self.calls.append(payload)
        return {
            "choices": [{"message": {"content": json.dumps(self.payload)}}],
            "usage": {"prompt_tokens": 900, "completion_tokens": 200, "cost": "0.000061"},
        }


@pytest.fixture
def provider(monkeypatch, test_settings, career) -> Provider:
    stub = Provider(
        {
            "presentation": {"text": PRESENTATION, "sources": [str(career.first_bullet.id)]},
            "achievements": {"text": ACHIEVEMENTS, "sources": [str(career.first_bullet.id)]},
        }
    )
    monkeypatch.setattr(extract_client, "_post", stub)
    return stub


def autogenerate_url(track) -> str:
    return f"/tracks/{track.id}/letter/autogenerate"


def letter_url(track) -> str:
    return f"/tracks/{track.id}/letter"


def textarea(page: str, name: str) -> str:
    match = re.search(rf'<textarea id="{name}"[^>]*>(.*?)</textarea>', page, re.S)
    assert match, f"the page has a {name} textarea"
    return match.group(1).strip()


def template_rows(session) -> int:
    return session.scalar(select(func.count()).select_from(LetterTemplate))


# --- the track's template: one paid call, nothing stored until Guardar -----------------


def test_a_get_renders_the_button_and_makes_no_call(client, career, provider):
    login(client, career.first.email)

    page = client.get(letter_url(career.first_track)).text

    assert provider.calls == [], "a GET never pays for a call"
    assert f'action="{autogenerate_url(career.first_track)}"' in page
    assert 'data-progress="letter"' in page


def test_the_post_makes_one_call_and_fills_the_fields_without_storing(
    client, session, career, provider
):
    login(client, career.first.email)
    before = template_rows(session)

    page = client.post(autogenerate_url(career.first_track)).text

    assert len(provider.calls) == 1
    assert textarea(page, "presentation") == PRESENTATION
    assert textarea(page, "achievements").startswith("Reduje el tiempo de cierre un 30%")
    assert "Coste: $0.000061" in page, "the cost of the call is shown"
    assert "todavía no se ha guardado nada" in page
    session.expire_all()
    assert template_rows(session) == before
    assert track_template(career.first_profile.id, session, career.first_track) is None


def test_the_prompt_carries_the_voice_notes_of_the_tracks_language(
    client, session, career, provider
):
    for lang, notes in (("es", "Tuteo, frases cortas."), ("en", "Formal, British.")):
        save_letter_settings(
            career.first_profile.id,
            session,
            lang=lang,
            header="x",
            greeting="x",
            closing="x",
            sign_off="x",
            voice_notes=notes,
        )
    session.commit()
    login(client, career.first.email)

    client.post(autogenerate_url(career.first_track))

    user_message = provider.calls[0]["messages"][1]["content"]
    assert "Tuteo, frases cortas." in user_message
    assert "Formal, British." not in user_message


def test_an_inactive_tracks_material_is_still_used(client, session, career, provider):
    set_track_active(career.first_profile.id, session, career.first_track.id, active=False)
    session.commit()
    login(client, career.first.email)

    page = client.post(autogenerate_url(career.first_track)).text

    assert len(provider.calls) == 1
    assert textarea(page, "presentation") == PRESENTATION


def test_an_invented_number_is_flagged_beside_its_paragraph_and_can_still_be_saved(
    client, session, career, provider
):
    provider.payload["presentation"] = {
        "text": "Analista que redujo el cierre un 40% con Python.",
        "sources": [str(career.first_bullet.id)],
    }
    login(client, career.first.email)

    page = client.post(autogenerate_url(career.first_track)).text

    assert "Un número o un nombre no aparece en la fuente citada." in page
    assert "<mark" in page and "40%" in page
    assert "Este párrafo no pasó una comprobación" in page
    assert textarea(page, "presentation") == "Analista que redujo el cierre un 40% con Python."
    # What the user saves is their text: it is not validated again.
    saved = client.post(
        letter_url(career.first_track),
        data={
            "presentation": "Analista que redujo el cierre un 40% con Python.",
            "achievements": ACHIEVEMENTS,
        },
        follow_redirects=False,
    )
    assert saved.status_code == 303
    session.expire_all()
    stored = track_template(career.first_profile.id, session, career.first_track)
    assert stored is not None and "40%" in stored.presentation


def test_the_shape_rules_are_flagged_too(client, career, provider):
    provider.payload["presentation"] = {
        "text": " ".join(["palabra"] * 71),
        "sources": [str(career.first_bullet.id)],
    }
    login(client, career.first.email)

    page = client.post(autogenerate_url(career.first_track)).text

    assert "El párrafo no tiene la extensión pedida." in page


def test_a_source_from_another_profile_is_flagged(client, career, provider):
    provider.payload["achievements"]["sources"] = [str(career.second_bullet.id)]
    login(client, career.first.email)

    page = client.post(autogenerate_url(career.first_track)).text

    assert "Cita una fuente que no existe o no es tuya." in page


def test_deshacer_keeps_what_the_fields_held_and_is_absent_when_they_were_empty(
    client, career, provider
):
    login(client, career.first.email)

    empty = client.post(autogenerate_url(career.first_track)).text
    filled = client.post(
        autogenerate_url(career.first_track),
        data={"presentation": "Mi presentación.", "achievements": "Mis logros."},
    ).text

    assert 'id="undo-draft"' not in empty
    assert 'id="undo-draft"' in filled
    assert 'data-presentation="Mi presentación."' in filled
    assert 'data-achievements="Mis logros."' in filled
    assert textarea(filled, "presentation") == PRESENTATION, "the draft replaced the field"
    assert "localStorage" not in filled and "sessionStorage" not in filled


def test_a_failed_call_says_so_and_leaves_the_fields_untouched(
    client, session, career, provider
):
    provider.payload = {}
    login(client, career.first.email)
    before = template_rows(session)

    page = client.post(
        autogenerate_url(career.first_track),
        data={"presentation": "Mi presentación.", "achievements": "Mis logros."},
    ).text

    assert "el modelo no respondió" in page.lower()
    assert textarea(page, "presentation") == "Mi presentación."
    assert textarea(page, "achievements") == "Mis logros."
    assert 'id="undo-draft"' not in page
    session.expire_all()
    assert template_rows(session) == before, "nothing was stored"


def test_another_profiles_track_is_a_404_and_makes_no_call(client, career, provider):
    login(client, career.first.email)

    assert client.post(autogenerate_url(career.second_track)).status_code == 404
    assert provider.calls == []


# --- the common blocks: defaults by code, no call, no write ----------------------------


@pytest.fixture
def no_model(monkeypatch, test_settings):
    """The provider and the generation entry point both fail loudly if reached."""

    def refuse(*_args, **_kwargs):
        raise AssertionError("the common blocks never call a model")

    monkeypatch.setattr(extract_client, "_post", refuse)
    monkeypatch.setattr(generation, "complete_json", refuse)


def card(page: str, lang: str) -> str:
    match = re.search(
        rf'<form method="post" action="/letters/settings"[^>]*>\s*<input type="hidden" '
        rf'name="lang" value="{lang}">.*?</form>',
        page,
        re.S,
    )
    assert match, f"the {lang} card"
    return match.group(0)


def field(block: str, name: str) -> str:
    """The value of one card field, a <textarea> or an <input>, by its id prefix."""
    prefix = name.replace("_", "-")
    textarea_match = re.search(rf'<textarea id="{prefix}-\w+"[^>]*>(.*?)</textarea>', block, re.S)
    if textarea_match:
        return textarea_match.group(1).strip()
    return re.search(rf'<input id="{prefix}-\w+" name="\w+" value="(.*?)"', block).group(1)


def test_autogenerate_fills_the_empty_blocks_with_the_defaults(client, session, career, no_model):
    login(client, career.first.email)
    rows_before = session.scalar(select(func.count()).select_from(LetterSettings))

    page = client.post("/letters/settings/autogenerate", data={"lang": "es"}).text

    spanish = card(page, "es")
    assert field(spanish, "header") == "Ana\npersona2@example.com"
    assert field(spanish, "greeting") == "Estimado equipo de selección de [EMPRESA]:"
    assert field(spanish, "closing").endswith("conversar sobre el puesto de [PUESTO].")
    assert field(spanish, "sign_off") == "Atentamente,\nAna"
    assert field(spanish, "voice") == "", "voice notes are never generated"
    assert "Revisa los campos y pulsa Guardar." in page
    assert "Añade tu teléfono o LinkedIn si quieres." in page
    assert session.scalar(select(func.count()).select_from(LetterSettings)) == rows_before
    assert get_letter_settings(career.first_profile.id, session, "es") is None


def test_autogenerate_writes_the_english_card_in_english(client, career, no_model):
    login(client, career.first.email)

    page = client.post("/letters/settings/autogenerate", data={"lang": "en"}).text

    english = card(page, "en")
    assert field(english, "greeting") == "Dear [COMPANY] hiring team,"
    assert field(english, "sign_off") == "Kind regards,\nAna"
    assert field(card(page, "es"), "greeting") == "", "the other card is untouched"


def test_autogenerate_keeps_what_the_user_wrote(client, session, career, no_model):
    login(client, career.first.email)

    page = client.post(
        "/letters/settings/autogenerate",
        data={
            "lang": "es",
            "header": "Ana Pérez\n+52 55 0000",
            "greeting": "Hola equipo,",
            "voice_notes": "Tuteo.",
        },
    ).text

    spanish = card(page, "es")
    assert field(spanish, "header") == "Ana Pérez\n+52 55 0000"
    assert field(spanish, "greeting") == "Hola equipo,"
    assert field(spanish, "voice") == "Tuteo."
    assert field(spanish, "closing").startswith("Gracias por su tiempo"), "empty ones are filled"


def test_autogenerate_refuses_an_unknown_language(client, career, no_model):
    login(client, career.first.email)

    assert client.post("/letters/settings/autogenerate", data={"lang": "fr"}).status_code == 400


def test_each_card_has_an_autogenerate_button_that_posts_to_the_route(client, career, no_model):
    login(client, career.first.email)

    page = client.get("/letters").text

    assert page.count('formaction="/letters/settings/autogenerate"') == 2


# --- the N8.3 pages are gone -----------------------------------------------------------


def test_the_propose_routes_are_gone(client, career, provider):
    login(client, career.first.email)
    letter_id = career.first_letter.id

    assert client.get(f"/letters/{letter_id}/propose").status_code in (404, 405)
    assert client.post(f"/letters/{letter_id}/propose").status_code in (404, 405)
    accepted = client.post(f"/letters/{letter_id}/propose/accept", data={"payload": "{}"})
    assert accepted.status_code in (404, 405)
    assert provider.calls == []
