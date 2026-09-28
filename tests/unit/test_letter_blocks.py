"""N8.3: proposing a template's presentation and achievements.

The provider is stubbed: the shape rules (≤ 70 words, 80–160 words, one paragraph) and
the three validators are what the tests exercise.
"""

import json

import pytest

from src.extract import client as extract_client
from src.letters import create_letter, get_letter
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


def linked_letter(session, career, *, track=True):
    letter = create_letter(
        career.first_profile.id,
        session,
        name="Corporativo",
        applies_when="Banca",
        presentation="Viejo.",
        achievements="Viejo logro.",
        lang="es",
        track_id=career.first_track.id if track else None,
    )
    session.commit()
    return letter


def url(letter) -> str:
    return f"/letters/{letter.id}/propose"


def payload(career, *, presentation: str = PRESENTATION, achievements: str = ACHIEVEMENTS) -> str:
    return json.dumps(
        {
            "presentation": {"text": presentation, "sources": [str(career.first_bullet.id)]},
            "achievements": {"text": achievements, "sources": [str(career.first_bullet.id)]},
        }
    )


def test_a_get_renders_the_button_and_makes_no_call(client, session, career, provider):
    letter = linked_letter(session, career)
    login(client, career.first.email)

    page = client.get(url(letter)).text

    assert provider.calls == [], "a GET never pays for a call"
    assert f'action="{url(letter)}"' in page


def test_the_post_proposes_the_two_paragraphs(client, session, career, provider):
    letter = linked_letter(session, career)
    login(client, career.first.email)

    page = client.post(url(letter)).text

    assert len(provider.calls) == 1
    assert PRESENTATION in page and "Reduje el tiempo de cierre un 30%" in page
    assert f'action="{url(letter)}/accept"' in page
    assert "Coste" in page, "the cost of the call is shown"


def test_another_profiles_letter_is_a_404(client, session, career, provider):
    letter = linked_letter(session, career)
    login(client, career.second.email)

    assert client.get(url(letter)).status_code == 404
    assert client.post(url(letter)).status_code == 404
    refused = client.post(f"{url(letter)}/accept", data={"payload": payload(career)})
    assert refused.status_code == 404


def test_a_template_without_a_track_has_no_button(client, session, career, provider):
    letter = linked_letter(session, career, track=False)
    login(client, career.first.email)

    page = client.get(url(letter)).text
    posted = client.post(url(letter)).text

    assert f'action="{url(letter)}"' not in page, "no track, no material, no button"
    assert "no está ligada a un puesto objetivo" in page
    assert provider.calls == []
    assert "no está ligada a un puesto objetivo" in posted


def test_an_invented_number_is_refused_and_cannot_be_accepted(client, session, career, provider):
    provider.payload["presentation"] = {
        "text": "Analista que redujo el cierre un 40% con Python.",
        "sources": [str(career.first_bullet.id)],
    }
    letter = linked_letter(session, career)
    login(client, career.first.email)

    page = client.post(url(letter)).text

    assert "40%" in page
    assert f'action="{url(letter)}/accept"' not in page, "a failed proposal is not acceptable"


def test_a_source_from_another_profile_is_refused(client, session, career, provider):
    provider.payload["achievements"]["sources"] = [str(career.second_bullet.id)]
    letter = linked_letter(session, career)
    login(client, career.first.email)

    page = client.post(url(letter)).text

    assert "no pasó la validación" in page
    assert f'action="{url(letter)}/accept"' not in page


def test_an_over_long_presentation_is_refused(client, session, career, provider):
    provider.payload["presentation"] = {
        "text": " ".join(["palabra"] * 71),
        "sources": [str(career.first_bullet.id)],
    }
    letter = linked_letter(session, career)
    login(client, career.first.email)

    assert "no pasó la validación" in client.post(url(letter)).text


def test_accepting_writes_the_blocks(client, session, career, provider):
    letter = linked_letter(session, career)
    login(client, career.first.email)

    accepted = client.post(
        f"{url(letter)}/accept", data={"payload": payload(career)}, follow_redirects=False
    )

    assert accepted.status_code == 303
    session.expire_all()
    saved = get_letter(career.first_profile.id, session, letter.id)
    assert saved is not None
    assert saved.presentation == PRESENTATION
    assert saved.achievements == ACHIEVEMENTS
    assert saved.track_id == career.first_track.id, "the link is untouched"


def test_a_tampered_accept_is_refused(client, session, career, provider):
    letter = linked_letter(session, career)
    login(client, career.first.email)
    tampered = json.dumps(
        {
            "presentation": {"text": "Con Kubernetes.", "sources": [str(career.first_bullet.id)]},
            "achievements": {"text": ACHIEVEMENTS, "sources": [str(career.first_bullet.id)]},
        }
    )

    refused = client.post(f"{url(letter)}/accept", data={"payload": tampered})

    assert refused.status_code == 200
    session.expire_all()
    saved = get_letter(career.first_profile.id, session, letter.id)
    assert saved is not None and saved.presentation == "Viejo.", "nothing was written"
