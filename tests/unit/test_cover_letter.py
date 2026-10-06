"""F8: the cover letter for one analysis — template already loaded, one bridge at a time.

The provider is stubbed at `extract_client._post`. A GET makes no call; the generate POST
makes one (two with a retry); everything else — assembly, the saved letter, the checklist —
is deterministic. The track decides the template and the language of the letter.
"""

import json
import re
from decimal import Decimal

import pytest

from src.applications import create_application, get_application
from src.extract import client as extract_client
from src.letters import save_letter_settings, save_track_template
from tests.conftest import login

JD = "Analista de datos — Banco Demo\nBuscamos un analista con Python y SQL."

# Two plain sentences that cite the user's bullet and say nothing the sources do not.
BRIDGE = (
    "El puesto pide Python y SQL para convertir datos en decisiones, y eso es "
    "exactamente lo que hago. Banco Demo trabaja con carteras que se mueven rápido, "
    "y eso me interesa."
)

HEADER = "Ana\npersona@example.com"
PRESENTATION = "Me presento: analista de datos."
ACHIEVEMENTS = "Automaticé el reporte mensual un 30% con Python y SQL."
MARKER = "[párrafo de interés]"


class Provider:
    """Answers each call with the next payload; the last one repeats."""

    def __init__(self, *payloads: dict):
        self.calls: list[dict] = []
        self.payloads = list(payloads)

    def __call__(self, payload: dict, api_key: str) -> dict:
        self.calls.append(payload)
        answer = self.payloads[min(len(self.calls), len(self.payloads)) - 1]
        return {
            "choices": [{"message": {"content": json.dumps(answer)}}],
            "usage": {"prompt_tokens": 1500, "completion_tokens": 400, "cost": "0.000120"},
        }


def bridge_payload(career, text: str = BRIDGE, **overrides) -> dict:
    payload = {
        "angle": "impacto",
        "text": text,
        "sources": [str(career.first_bullet.id)],
        "company_fact": {"text": "Banco Demo", "jd_quote": "Analista de datos — Banco Demo"},
        "risk": "Salto hacia banca privada.",
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def provider(monkeypatch, test_settings, career) -> Provider:
    stub = Provider(bridge_payload(career))
    monkeypatch.setattr(extract_client, "_post", stub)
    return stub


def stored_application(
    session, career, *, language: str = "es", track: bool = True, title: str = "Analista de datos"
):
    application = create_application(
        career.first_profile.id,
        session,
        jd_text=JD,
        jd_hash="sha256:letter-bridge",
        company="Banco Demo",
        title=title,
        report={
            "jd": {"language": language, "title": title},
            "grades": [
                {"requirement": "python", "level": 3, "bullet_id": str(career.first_bullet.id)}
            ],
            "score": {},
            "llm": {"calls": []},
        },
        weights_version="w4",
        prompt_versions={},
        token_cost_usd=Decimal(0),
        track_id=career.first_track.id if track else None,
    )
    session.commit()
    return application


def ready(session, career, *, language: str = "es", track: bool = True):
    """Common blocks and the track's template, and an application on that track."""
    save_letter_settings(
        career.first_profile.id,
        session,
        lang="es",
        header=HEADER,
        greeting="Estimado equipo,",
        closing="Quedo a su disposición.",
        sign_off="Ana",
        voice_notes="Tuteo.",
    )
    template = save_track_template(
        career.first_profile.id,
        session,
        career.first_track,
        presentation=PRESENTATION,
        achievements=ACHIEVEMENTS,
    )
    session.commit()
    return stored_application(session, career, language=language, track=track), template


def url(application) -> str:
    return f"/applications/{application.id}/letter"


def field(page: str, name: str) -> str:
    match = re.search(rf'<textarea id="{name}"[^>]*>(.*?)</textarea>', page, re.S)
    assert match, f"the page has a {name} textarea"
    return match.group(1).strip()


def data_attribute(page: str, name: str) -> str:
    match = re.search(rf'data-{name}="(.*?)"', page, re.S)
    assert match, f"data-{name} is rendered"
    return match.group(1).replace("&#34;", '"').replace("&amp;", "&")


def generate(client, application, *, previous="[]", track=None, bridge=""):
    data = {"previous": previous, "bridge": bridge}
    if track is not None:
        data["track_id"] = str(track.id)
    return client.post(f"{url(application)}/generate", data=data)


# --- the page, assembled, with no call ---------------------------------------------------


def test_a_get_makes_no_call_and_renders_the_assembled_letter(client, session, career, provider):
    application, _template = ready(session, career)
    login(client, career.first.email)

    page = client.get(url(application)).text

    assert provider.calls == []
    before = data_attribute(page, "before")
    assert HEADER in before and PRESENTATION in before and ACHIEVEMENTS in before
    assert "Estimado equipo," in before
    assert "Quedo a su disposición." in data_attribute(page, "after")
    assert MARKER in page, "the bridge's place is marked"
    assert f'action="{url(application)}/generate"' in page
    assert "Autogenerar párrafo de interés" in page
    assert field(page, "bridge-text") == ""
    full = field(page, "letter-text")
    assert full.index(PRESENTATION) < full.index(MARKER) < full.index("Quedo a su disposición.")


def test_the_letter_is_assembled_in_the_tracks_language_with_its_date(
    client, session, career, provider
):
    application, _template = ready(session, career)
    login(client, career.first.email)

    page = client.get(url(application)).text

    assert re.search(r"\d{1,2} de \w+ de \d{4}", data_attribute(page, "before"))


# --- which track -------------------------------------------------------------------------


def test_an_application_without_a_track_renders_the_picker(client, session, career, provider):
    application, _template = ready(session, career, track=False)
    login(client, career.first.email)

    page = client.get(url(application)).text

    assert "Este análisis no tiene línea de carrera. Elige la línea para la carta" in page
    assert "no cambia el análisis" in page
    assert 'method="get"' in page and f'value="{career.first_track.id}"' in page
    assert f'action="{url(application)}/generate"' not in page
    assert provider.calls == []


def test_an_owned_track_param_renders_the_letter_and_a_foreign_one_the_picker(
    client, session, career, provider
):
    application, _template = ready(session, career, track=False)
    login(client, career.first.email)

    own = client.get(f"{url(application)}?track={career.first_track.id}").text
    foreign = client.get(f"{url(application)}?track={career.second_track.id}")

    assert PRESENTATION in data_attribute(own, "before")
    assert foreign.status_code == 200
    assert "Elige la línea para la carta" in foreign.text
    assert "Riesgo" not in foreign.text, "another profile's track is not leaked"
    assert str(career.second_track.id) not in foreign.text


def test_the_chosen_track_is_the_one_the_letter_is_written_for(client, session, career, provider):
    application, _template = ready(session, career, track=False)
    login(client, career.first.email)

    page = generate(client, application, track=career.first_track).text

    assert len(provider.calls) == 1
    assert "Banco Demo" in field(page, "letter-text")
    assert f'name="track_id" value="{career.first_track.id}"' in page


def test_generating_for_a_foreign_or_missing_track_is_a_404(client, session, career, provider):
    application, _template = ready(session, career, track=False)
    login(client, career.first.email)

    assert generate(client, application, track=career.second_track).status_code == 404
    assert generate(client, application).status_code == 404
    assert provider.calls == []


# --- what is missing is fixed from here ---------------------------------------------------


def test_no_common_blocks_links_to_cartas_and_offers_no_call(client, session, career, provider):
    save_track_template(
        career.first_profile.id, session, career.first_track,
        presentation=PRESENTATION, achievements=ACHIEVEMENTS,
    )
    application = stored_application(session, career)
    login(client, career.first.email)

    page = client.get(url(application)).text
    posted = generate(client, application).text

    assert "Faltan los bloques comunes en español." in page
    assert 'href="/letters"' in page and "Ir a Cartas" in page
    assert f'action="{url(application)}/generate"' not in page
    assert "Faltan los bloques comunes en español." in posted
    assert provider.calls == []


def test_no_template_links_to_the_tracks_letter_and_offers_no_call(
    client, session, career, provider
):
    save_letter_settings(
        career.first_profile.id, session, lang="es",
        header=HEADER, greeting="Hola,", closing="Gracias.", sign_off="Ana",
    )
    application = stored_application(session, career)
    login(client, career.first.email)

    page = client.get(url(application)).text
    posted = generate(client, application).text

    assert "La línea «Analista de datos» no tiene carta en español." in page
    assert f'href="/tracks/{career.first_track.id}/letter"' in page
    assert "Crear carta de la línea" in page
    assert f'action="{url(application)}/generate"' not in page
    assert "no tiene carta en español" in posted
    assert provider.calls == []


def test_a_template_in_another_language_is_treated_as_missing(client, session, career, provider):
    application, template = ready(session, career)
    template.lang = "en"
    session.commit()
    login(client, career.first.email)

    page = client.get(url(application)).text

    assert "no tiene carta en español" in page
    assert f'action="{url(application)}/generate"' not in page


def test_several_templates_use_the_first_and_link_to_cartas(client, session, career, provider):
    from src.letters import create_letter

    application, _template = ready(session, career)
    create_letter(
        career.first_profile.id, session, name="Otra", applies_when="", presentation="Otra.",
        achievements="Otros logros.", lang="es", track_id=career.first_track.id,
    )
    session.commit()
    login(client, career.first.email)

    page = client.get(url(application)).text

    assert "Esta línea tiene varias cartas y se usa la primera" in page
    assert 'href="/letters"' in page
    assert f'action="{url(application)}/generate"' in page, "the letter can still be written"


def test_the_language_notice_when_the_posting_is_in_the_other_language(
    client, session, career, provider
):
    application, _template = ready(session, career, language="en")
    login(client, career.first.email)

    page = client.get(url(application)).text

    assert (
        "Este aviso está en inglés y tu línea de carrera está en español; la carta va en español."
        in page
    )
    assert 'role="status"' in page
    assert f'action="{url(application)}/generate"' in page, "the notice does not block"


# --- one bridge ---------------------------------------------------------------------------


def test_the_generate_post_makes_one_call_and_renders_the_bridge(client, session, career, provider):
    application, _template = ready(session, career)
    login(client, career.first.email)

    page = generate(client, application).text

    assert len(provider.calls) == 1
    assert field(page, "bridge-text") == BRIDGE
    full = field(page, "letter-text")
    assert BRIDGE in full and PRESENTATION in full and MARKER not in full
    assert full.index(ACHIEVEMENTS) < full.index(BRIDGE) < full.index("Quedo a su disposición.")
    assert "Versión 1 · impacto" in page
    assert "Salto hacia banca privada." in page, "the risk is shown beside the field"
    assert "Salto hacia banca privada." not in full, "and never inside the letter"
    assert "Coste: $0.000120" in page
    assert "Otra versión (2 de 5)" in page
    assert json.loads(previous_value(page)) == [BRIDGE]
    assert "para el texto generado" in page
    assert "✓" in page and "Sin marcadores pendientes" in page


def previous_value(page: str) -> str:
    match = re.search(r'name="previous" value="(.*?)"', page, re.S)
    assert match
    return match.group(1).replace("&#34;", '"').replace("&amp;", "&")


def test_the_prompt_carries_the_tracks_template_and_the_previous_versions(
    client, session, career, provider
):
    application, _template = ready(session, career)
    login(client, career.first.email)

    generate(client, application, previous=json.dumps(["Una versión anterior."]))

    message = provider.calls[0]["messages"][1]["content"]
    assert PRESENTATION in message and ACHIEVEMENTS in message
    assert "1. Una versión anterior." in message
    assert "Tuteo." in message


def test_a_rule_failure_makes_one_retry_that_names_the_rule(client, session, career, provider):
    banned = "El puesto pide Python y SQL. Me apasiona convertir datos en decisiones."
    provider.payloads = [bridge_payload(career, banned), bridge_payload(career)]
    application, _template = ready(session, career)
    login(client, career.first.email)

    page = generate(client, application).text

    assert len(provider.calls) == 2
    retry = provider.calls[1]["messages"][1]["content"]
    assert "Your previous answer was unusable" in retry and "me apasiona" in retry
    assert field(page, "bridge-text") == BRIDGE, "the retry's clean answer is shown"
    assert "Coste: $0.000240" in page, "both calls are paid and both are counted"


def test_a_hard_failure_after_the_retry_shows_no_paragraph_and_keeps_otra_version(
    client, session, career, provider
):
    invented = bridge_payload(career, "El puesto pide Python. Logré un 77% más de velocidad.")
    provider.payloads = [invented]
    application, _template = ready(session, career)
    login(client, career.first.email)

    page = generate(client, application, previous=json.dumps(["Versión anterior."])).text

    assert len(provider.calls) == 2, "one call and a single retry"
    assert "No se pudo escribir un párrafo que cumpla las reglas." in page
    assert "77%" not in field(page, "bridge-text") and "77%" not in field(page, "letter-text")
    assert "Otra versión (2 de 5)" in page
    assert previous_value(page) == '["Versión anterior."]', "a failure is not a version"


def test_a_soft_failure_shows_the_paragraph_marked(client, session, career, provider):
    banned = "El puesto pide Python y SQL. Me apasiona convertir datos en decisiones."
    provider.payloads = [bridge_payload(career, banned)]
    application, _template = ready(session, career)
    login(client, career.first.email)

    page = generate(client, application).text

    assert len(provider.calls) == 2, "a soft failure is retried too"
    assert field(page, "bridge-text") == banned, "it is shown after the retry"
    assert "✗ Sin frases de plantilla de IA" in page and "me apasiona" in page
    assert "Usa una frase de plantilla" in page


def test_a_bridge_citing_nothing_of_the_users_is_hard(client, session, career, provider):
    provider.payloads = [bridge_payload(career, sources=[])]
    application, _template = ready(session, career)
    login(client, career.first.email)

    page = generate(client, application).text

    assert "No se pudo escribir un párrafo que cumpla las reglas." in page


def test_a_failed_call_says_so_and_keeps_the_field(client, session, career, provider):
    provider.payloads = [{}]
    application, _template = ready(session, career)
    login(client, career.first.email)

    page = generate(client, application, bridge="Mi párrafo.").text

    assert "el modelo no respondió" in page.lower()
    assert field(page, "bridge-text") == "Mi párrafo."


def test_the_fifth_version_disables_the_button(client, session, career, provider):
    application, _template = ready(session, career)
    login(client, career.first.email)
    earlier = [f"Versión {number} del párrafo." for number in range(1, 5)]

    fifth = generate(client, application, previous=json.dumps(earlier)).text

    assert len(provider.calls) == 1
    assert "Versión 5 · impacto" in fifth
    assert "Llegaste a 5 versiones." in fifth
    assert re.search(r"<button type=\"submit\" disabled", fifth), "no sixth call is offered"
    assert len(json.loads(previous_value(fifth))) == 5


def test_a_bad_previous_list_is_a_400_and_makes_no_call(client, session, career, provider):
    application, _template = ready(session, career)
    login(client, career.first.email)

    five = json.dumps([f"Versión {number}." for number in range(5)])
    too_long = json.dumps(["x" * 1201])

    for bad in (five, "{not json", json.dumps({"a": 1}), json.dumps([1, 2]), too_long):
        assert generate(client, application, previous=bad).status_code == 400, bad
    assert provider.calls == []


# --- saving -------------------------------------------------------------------------------


def test_saving_stores_the_text_and_the_tracks_template(client, session, career, provider):
    application, template = ready(session, career)
    login(client, career.first.email)
    generate(client, application)

    saved = client.post(
        f"{url(application)}/save",
        data={"text": "Estimado equipo:\n\nCarta final.", "track_id": str(career.first_track.id)},
        follow_redirects=False,
    )

    assert saved.status_code == 303
    assert saved.headers["location"].startswith(f"{url(application)}?saved=1")
    session.expire_all()
    stored = get_application(career.first_profile.id, session, application.id)
    assert stored.letter_text == "Estimado equipo:\n\nCarta final."
    assert stored.letter_template_id == template.id
    assert "Carta guardada." in client.get(saved.headers["location"]).text


def test_a_saved_letter_opens_in_edited_mode_with_an_empty_bridge(
    client, session, career, provider
):
    application, _template = ready(session, career)
    login(client, career.first.email)
    client.post(
        f"{url(application)}/save",
        data={"text": "Estimado equipo:\n\nCarta final.", "track_id": str(career.first_track.id)},
    )

    page = client.get(url(application)).text

    assert field(page, "letter-text") == "Estimado equipo:\n\nCarta final."
    assert field(page, "bridge-text") == ""
    assert 'data-edited="1"' in page
    assert re.search(r'<p id="edited-notice"(?![^>]*\bhidden\b)', page), "the notice is shown"
    assert "Editaste la carta completa; el párrafo ya no se actualiza aquí." in page
    assert "Volver a montar" in page
    assert "Autogenerar párrafo de interés" in page, "the bridge can still be written"
    assert "para la carta guardada" in page
    assert provider.calls == []


def test_saving_overwrites_the_earlier_letter(client, session, career, provider):
    application, _template = ready(session, career)
    login(client, career.first.email)
    data = {"track_id": str(career.first_track.id)}

    client.post(f"{url(application)}/save", data={**data, "text": "Primera."})
    client.post(f"{url(application)}/save", data={**data, "text": "Segunda."})

    session.expire_all()
    stored = get_application(career.first_profile.id, session, application.id)
    assert stored.letter_text == "Segunda."


def test_generating_after_a_save_rebuilds_the_letter_from_the_blocks(
    client, session, career, provider
):
    application, _template = ready(session, career)
    login(client, career.first.email)
    client.post(
        f"{url(application)}/save",
        data={"text": "Carta vieja.", "track_id": str(career.first_track.id)},
    )

    page = generate(client, application).text

    assert "Carta vieja." not in field(page, "letter-text")
    assert BRIDGE in field(page, "letter-text")
    assert 'data-edited="0"' in page


def test_deleting_the_template_keeps_the_saved_letter(client, session, career, provider):
    from src.deletion import delete_letter_template

    application, template = ready(session, career)
    login(client, career.first.email)
    client.post(
        f"{url(application)}/save",
        data={"text": "Carta enviada.", "track_id": str(career.first_track.id)},
    )

    assert delete_letter_template(career.first_profile.id, session, template.id) is not None
    session.commit()
    session.expire_all()

    stored = get_application(career.first_profile.id, session, application.id)
    assert stored is not None and stored.letter_text == "Carta enviada."
    assert stored.letter_template_id is None


def test_the_history_marks_an_application_with_a_saved_letter(client, session, career, provider):
    application, _template = ready(session, career)
    login(client, career.first.email)
    client.post(
        f"{url(application)}/save",
        data={"text": "Carta guardada.", "track_id": str(career.first_track.id)},
    )

    assert ">carta<" in client.get("/applications").text.replace("\n", "")


def test_another_profiles_application_is_a_404(client, session, career, provider):
    application, _template = ready(session, career)
    login(client, career.second.email)

    assert client.get(url(application)).status_code == 404
    assert generate(client, application).status_code == 404
    saved = client.post(f"{url(application)}/save", data={"text": "x"})
    assert saved.status_code == 404
    assert provider.calls == []


# --- the script ---------------------------------------------------------------------------


def test_the_script_composes_before_bridge_after_and_stops_on_direct_edits(
    client, session, career, provider
):
    application, _template = ready(session, career)
    login(client, career.first.email)

    page = client.get(url(application)).text
    script = page[page.index("// F8: the full letter is before + bridge + after") :]

    assert "[root.dataset.before, text || marker, root.dataset.after].filter(Boolean)" in script
    assert ".join('\\n\\n')" in script
    # While the user types in the bridge field the full letter follows it...
    assert "if (!edited) full.value = compose();" in script
    # ...and a direct edit stops that, says so, and "Volver a montar" rebuilds it.
    assert "full.addEventListener('input', function () {\n      edited = true;" in script
    assert "notice.hidden = false;" in script
    assert "full.value = compose();\n      notice.hidden = true;" in script
    assert "localStorage" not in script and "sessionStorage" not in script
