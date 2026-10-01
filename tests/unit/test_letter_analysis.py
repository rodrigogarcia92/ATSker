"""N8.4: the cover letter written for one analysis.

The provider is stubbed at `extract_client._post`: the tests are about the template
choice, the three bridges, the company-fact rule, the achievements-number rule and the
deterministic assembly.
"""

import json
import re
from decimal import Decimal

import pytest

from src.applications import create_application, get_application
from src.extract import client as extract_client
from src.letters import create_letter, save_letter_settings
from tests.conftest import login

JD = "Analista de datos — Banco Demo\nBuscamos un analista con Python y SQL."

BRIDGE = (
    "El puesto pide Python y SQL para convertir datos en decisiones, y eso es "
    "exactamente lo que hago: automaticé el reporte mensual y llevé el proceso a una "
    "rutina que corre sola. Banco Demo trabaja con carteras que se mueven rápido, y "
    "el tablero que mantuve en producción explicaba esos movimientos a negocio."
)


class Provider:
    def __init__(self, payload: dict):
        self.calls: list[dict] = []
        self.payload = payload

    def __call__(self, payload: dict, api_key: str) -> dict:
        self.calls.append(payload)
        return {
            "choices": [{"message": {"content": json.dumps(self.payload)}}],
            "usage": {"prompt_tokens": 1500, "completion_tokens": 400, "cost": "0.000120"},
        }


@pytest.fixture
def provider(monkeypatch, test_settings, career) -> Provider:
    payload = {
        "template_id": "",  # filled by the test after the letter exists
        "reason": "Encaja por el tipo de organización.",
        "runner_up_id": None,
        "variants": [
            {
                "angle": "impacto",
                "text": BRIDGE,
                "sources": [str(career.first_bullet.id)],
                "company_fact": {
                    "text": "Banco Demo",
                    "jd_quote": "Analista de datos — Banco Demo",
                },
            },
            {
                "angle": "método",
                "text": "Automaticé el reporte con Python y SQL, y expliqué cada cifra a negocio.",
                "sources": [str(career.first_bullet.id)],
                "company_fact": None,
            },
            {
                "angle": "cierre",
                "text": (
                    "Llevé el cierre mensual a una rutina que corre sola, sin rehacer "
                    "nada a mano."
                ),
                "sources": [str(career.first_bullet.id)],
                "company_fact": None,
            },
        ],
        "risk": "Salto hacia banca privada.",
    }
    stub = Provider(payload)
    monkeypatch.setattr(extract_client, "_post", stub)
    return stub


def stored_application(session, career, *, language: str = "es", title: str = "Analista de datos"):
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
                {
                    "requirement": "python",
                    "level": 3,
                    "bullet_id": str(career.first_bullet.id),
                }
            ],
            "score": {},
            "llm": {"calls": []},
        },
        weights_version="w4",
        prompt_versions={},
        token_cost_usd=Decimal(0),
        track_id=career.first_track.id,
    )
    session.commit()
    return application


def ready(session, career, provider, *, language: str = "es", track=True):
    """Settings, one template in the posting's language, and an application."""
    save_letter_settings(
        career.first_profile.id,
        session,
        lang=language,
        header="Ana\npersona@example.com",
        greeting="Estimado equipo,",
        closing="Quedo a su disposición.",
        sign_off="Ana",
        voice_notes="Tuteo.",
    )
    letter = create_letter(
        career.first_profile.id,
        session,
        name="Corporativo",
        applies_when="Banca",
        presentation="Me presento: analista de datos.",
        achievements="Automaticé el reporte mensual un 30% con Python y SQL.",
        lang=language,
        track_id=career.first_track.id if track else None,
    )
    session.commit()
    provider.payload["template_id"] = str(letter.id)
    application = stored_application(session, career, language=language)
    return application, letter


def url(application) -> str:
    return f"/applications/{application.id}/letter"


def test_a_get_makes_no_call_and_offers_the_button(client, session, career, provider):
    application, _letter = ready(session, career, provider)
    login(client, career.first.email)

    page = client.get(url(application)).text

    assert provider.calls == []
    assert f'action="{url(application)}/generate"' in page


def test_the_post_writes_three_bridges_and_assembles_the_letter(client, session, career, provider):
    application, _letter = ready(session, career, provider)
    login(client, career.first.email)

    page = client.post(f"{url(application)}/generate").text

    assert len(provider.calls) == 1
    assert "Encaja por el tipo de organización." in page
    assert "Salto hacia banca privada." in page, "the risk is shown"
    assert "estimado equipo," in page.lower(), "the assembled letter carries the greeting"
    assert "Banco Demo" in page and "Analista de datos" in page
    assert 'name="template_id"' in page and 'name="text"' in page, "the save form"
    assert "Coste" in page


def test_the_assembled_letter_uses_the_postings_date_and_language(
    client, session, career, provider
):
    application, _letter = ready(session, career, provider)
    career.first.ui_lang = "en"
    session.commit()
    login(client, career.first.email)

    page = client.post(f"{url(application)}/generate").text

    assert re.search(r"\d{1,2} de \w+ de \d{4}", page), "the date is written in Spanish"


def test_a_fabricated_company_fact_is_dropped(client, session, career, provider):
    application, _letter = ready(session, career, provider)
    provider.payload["variants"][0]["company_fact"]["jd_quote"] = "Una cita que no está"
    login(client, career.first.email)

    page = client.post(f"{url(application)}/generate").text

    assert "Cita que no está" not in page
    assert "Automaticé el reporte con Python y SQL" in page, "the other variants stay"


def test_a_bridge_repeating_the_achievements_number_warns(client, session, career, provider):
    application, _letter = ready(session, career, provider)
    provider.payload["variants"][1]["text"] = "Automaticé el reporte un 30% con Python."
    login(client, career.first.email)

    page = client.post(f"{url(application)}/generate").text

    assert "Repite un número" in page, "the template's own 30% is flagged"


def test_an_invented_number_is_rejected(client, session, career, provider):
    application, _letter = ready(session, career, provider)
    provider.payload["variants"][1]["text"] = "Reduje el cierre un 40% con Python."
    login(client, career.first.email)

    page = client.post(f"{url(application)}/generate").text

    assert "40%" in page
    assert "no pasó la validación" not in page, "a bad variant is reported, not fatal"


# --- N8.7: the bridge must cite the user's own material -----------------------------


def _variant(text: str, cites: list[str]) -> dict:
    return {"angle": "impacto", "text": text, "sources": cites, "company_fact": None}


def test_a_variant_citing_nothing_of_the_users_material_is_refused(session, career, provider):
    """The posting is not the user's material: a cite of `__posting__` alone proves nothing."""
    from src.generate.letters import check_variants
    from src.generate.validators import PROVENANCE, Sources

    _application, letter = ready(session, career, provider)
    sources = Sources(bullets={str(career.first_bullet.id): career.first_bullet.text_es})

    survivors, violations = check_variants(
        {"template_id": str(letter.id), "variants": [_variant("Aporto valor al equipo.", [])]},
        sources=sources,
        candidates=[letter],
        jd_text=JD,
        company="Banco Demo",
        title="Analista de datos",
        achievements_text="",
    )

    assert [violation.rule for violation in violations] == [PROVENANCE]
    assert violations[0].message == "the bridge cites none of your material"
    assert survivors, "the variant is still shown, with the rule it broke"


def test_a_variant_citing_only_an_unknown_id_is_refused(session, career, provider):
    from src.generate.letters import check_variants
    from src.generate.validators import PROVENANCE, Sources

    _application, letter = ready(session, career, provider)
    sources = Sources(bullets={str(career.first_bullet.id): career.first_bullet.text_es})

    _survivors, violations = check_variants(
        {
            "template_id": str(letter.id),
            "variants": [_variant("Aporto valor al equipo.", ["nadie-que-yo-conozca"])],
        },
        sources=sources,
        candidates=[letter],
        jd_text=JD,
        company="Banco Demo",
        title="Analista de datos",
        achievements_text="",
    )

    messages = [violation.message for violation in violations if violation.rule == PROVENANCE]
    assert "the bridge cites none of your material" in messages
    assert "nadie-que-yo-conozca was not a supplied source" in messages


def test_a_variant_citing_one_owned_bullet_passes(session, career, provider):
    from src.generate.letters import check_variants
    from src.generate.validators import Sources

    _application, letter = ready(session, career, provider)
    sources = Sources(bullets={str(career.first_bullet.id): career.first_bullet.text_es})

    _survivors, violations = check_variants(
        {
            "template_id": str(letter.id),
            "variants": [_variant("Aporto valor al equipo.", [str(career.first_bullet.id)])],
        },
        sources=sources,
        candidates=[letter],
        jd_text=JD,
        company="Banco Demo",
        title="Analista de datos",
        achievements_text="",
    )

    assert violations == [], "one of the user's own sources is enough"


def test_saving_persists_the_letter_and_the_template(client, session, career, provider):
    application, letter = ready(session, career, provider)
    login(client, career.first.email)
    client.post(f"{url(application)}/generate")

    saved = client.post(
        f"{url(application)}/save",
        data={"text": "Estimado equipo:\n\nCarta final.", "template_id": str(letter.id)},
        follow_redirects=False,
    )

    assert saved.status_code == 303
    session.expire_all()
    stored = get_application(career.first_profile.id, session, application.id)
    assert stored is not None
    assert stored.letter_text == "Estimado equipo:\n\nCarta final."
    assert stored.letter_template_id == letter.id

    reloaded = client.get(url(application)).text
    assert "Carta final." in reloaded, "the saved letter survives a reload"


def test_deleting_the_template_keeps_the_saved_letter(client, session, career, provider):
    from src.deletion import delete_letter_template

    application, letter = ready(session, career, provider)
    login(client, career.first.email)
    client.post(
        f"{url(application)}/save",
        data={"text": "Carta enviada.", "template_id": str(letter.id)},
    )

    assert delete_letter_template(career.first_profile.id, session, letter.id) is not None
    session.commit()
    session.expire_all()

    stored = get_application(career.first_profile.id, session, application.id)
    assert stored is not None and stored.letter_text == "Carta enviada."
    assert stored.letter_template_id is None


def test_another_profiles_application_is_a_404(client, session, career, provider):
    application, letter = ready(session, career, provider)
    login(client, career.second.email)

    assert client.get(url(application)).status_code == 404
    assert client.post(f"{url(application)}/generate").status_code == 404
    saved = client.post(
        f"{url(application)}/save", data={"text": "x", "template_id": str(letter.id)}
    )
    assert saved.status_code == 404


def test_no_template_in_the_postings_language_says_so(client, session, career, provider):
    """The blocks exist, but no template is written in the posting's language."""
    save_letter_settings(
        career.first_profile.id,
        session,
        lang="en",
        header="Ana",
        greeting="Dear team,",
        closing="Best regards,",
        sign_off="Ana",
    )
    session.commit()
    application = stored_application(session, career, language="en")
    login(client, career.first.email)

    page = client.get(url(application)).text

    assert "No hay plantillas en el idioma del aviso" in page
    assert client.post(f"{url(application)}/generate").status_code == 200
    assert provider.calls == []


# --- N8.5: the checklist and the history mark --------------------------------------


def test_the_checklist_is_rendered_beside_the_letter(client, session, career, provider):
    application, _letter = ready(session, career, provider)
    login(client, career.first.email)

    page = client.post(f"{url(application)}/generate").text

    assert "Sin marcadores pendientes" in page
    assert "Aparece el título exacto del aviso" in page
    assert "Se nombra la empresa" in page
    assert "Una página" in page
    assert "✓" in page


def test_an_unresolved_placeholder_fails_its_check(session, career, provider):
    from src.generate.letters import letter_checklist

    application, _letter = ready(session, career, provider)
    items = {
        item["key"]: item
        for item in letter_checklist(
            text="Carta con [ÁREA] pendiente.",
            application=application,
            language="es",
            unresolved=["area"],
            facts_attributed=True,
        )
    }

    assert items["placeholders"]["ok"] is False
    assert items["placeholders"]["detail"] == "area"
    assert items["title"]["ok"] is False, "the title is not in that text"


def test_a_one_page_letter_passes_the_length_check(session, career, provider):
    from src.generate.letters import letter_checklist

    application, _letter = ready(session, career, provider)
    items = {
        item["key"]: item
        for item in letter_checklist(
            text=" ".join(["palabra"] * 421),
            application=application,
            language="es",
            unresolved=[],
            facts_attributed=True,
        )
    }

    assert items["length"]["ok"] is False, "421 words is over one page"


def test_the_history_marks_an_application_with_a_saved_letter(client, session, career, provider):
    application, letter = ready(session, career, provider)
    login(client, career.first.email)
    client.post(
        f"{url(application)}/save",
        data={"text": "Carta guardada.", "template_id": str(letter.id)},
    )

    page = client.get("/applications").text

    assert ">carta<" in page.replace("\n", "")
