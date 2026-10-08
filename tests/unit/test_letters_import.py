"""N8.2: the letters screen, and the import CLI that fills it from a local file.

The CLI's database is injected, so these tests never leave the in-memory session; the
dev-host refusal is a pure string check on the connection URL.
"""

import json
from contextlib import contextmanager

import pytest

from scripts import letters_import
from src.config import get_settings
from src.letters import get_letter_settings, list_letters
from tests.conftest import login

PAYLOAD = {
    "settings": [
        {
            "lang": "es",
            "header": "Ana\npersona@example.com",
            "greeting": "Estimado equipo,",
            "closing": "Quedo a su disposición.",
            "sign_off": "Ana",
            "voice_notes": "Tuteo.",
        }
    ],
    "templates": [
        {
            "name": "Corporativo",
            "applies_when": "Banca corporativa",
            "presentation": "Me presento.",
            "achievements": "Logros.",
            "lang": "es",
            "track_name": "Analista de datos",
        },
        {
            "name": "Sin puesto",
            "applies_when": "Cualquiera",
            "presentation": "Me presento.",
            "achievements": "Logros.",
            "lang": "es",
            "track_name": "Puesto que no existe",
        },
    ],
}


def write_payload(tmp_path, payload=None) -> str:
    path = tmp_path / "letters.json"
    path.write_text(json.dumps(payload if payload is not None else PAYLOAD), encoding="utf-8")
    return str(path)


@contextmanager
def scope(session):
    yield session


# --- the screen --------------------------------------------------------------------


def test_the_letters_page_shows_the_blocks_and_the_template_groups(client, session, career):
    from src.letters import create_letter, save_letter_settings

    save_letter_settings(
        career.first_profile.id,
        session,
        lang="es",
        header="Ana",
        greeting="Hola,",
        closing="Quedo.",
        sign_off="Ana",
    )
    create_letter(
        career.first_profile.id,
        session,
        name="Corporativo",
        applies_when="Banca",
        presentation="x",
        achievements="y",
        track_id=career.first_track.id,
    )
    create_letter(
        career.first_profile.id,
        session,
        name="Suelta",
        applies_when="",
        presentation="Texto de la carta suelta.",
        achievements="y",
    )
    session.commit()
    login(client, career.first.email)

    page = client.get("/letters").text

    assert "Bloques comunes" in page
    assert 'name="voice_notes"' in page and 'value="Hola,"' in page
    assert "Analista de datos" in page, "the linked track has its row"
    assert "Texto de la carta suelta." in page, "the unlinked template is listed"
    assert page.index("Carta por línea") < page.index("Texto de la carta suelta.")


def test_saving_the_blocks_persists_them(client, session, career):
    login(client, career.first.email)

    saved = client.post(
        "/letters/settings",
        data={
            "lang": "en",
            "header": "Ana",
            "greeting": "Dear team,",
            "closing": "Best regards,",
            "sign_off": "Ana",
            "voice_notes": "Formal.",
        },
        follow_redirects=False,
    )

    assert saved.status_code == 303
    session.expire_all()
    entry = get_letter_settings(career.first_profile.id, session, "en")
    assert entry is not None and entry.greeting == "Dear team," and entry.voice_notes == "Formal."


# --- the import CLI ----------------------------------------------------------------


def test_a_dry_run_changes_nothing(session, career, tmp_path, capsys):
    code = letters_import.main(
        ["--email", career.first.email, "--file", write_payload(tmp_path)],
        confirm=lambda _prompt: "IMPORT",
        scope=lambda: scope(session),
    )

    assert code == 0
    assert "dry run: nothing written" in capsys.readouterr().out
    assert get_letter_settings(career.first_profile.id, session, "es") is None
    assert all(
        letter.name != "Corporativo"
        for letter in list_letters(career.first_profile.id, session)
    )


def test_apply_writes_settings_and_templates_and_links_a_track(session, career, tmp_path, capsys):
    code = letters_import.main(
        ["--email", career.first.email, "--file", write_payload(tmp_path), "--apply"],
        confirm=lambda _prompt: "IMPORT",
        scope=lambda: scope(session),
    )

    assert code == 0
    out = capsys.readouterr().out
    assert "no track named 'Puesto que no existe'" in out, "the operator is told"
    session.expire_all()
    entry = get_letter_settings(career.first_profile.id, session, "es")
    assert entry is not None and entry.greeting == "Estimado equipo,"
    letters = {letter.name: letter for letter in list_letters(career.first_profile.id, session)}
    assert letters["Corporativo"].track_id == career.first_track.id
    assert letters["Sin puesto"].track_id is None


def test_apply_is_not_undone_by_a_wrong_confirmation(session, career, tmp_path):
    code = letters_import.main(
        ["--email", career.first.email, "--file", write_payload(tmp_path), "--apply"],
        confirm=lambda _prompt: "no",
        scope=lambda: scope(session),
    )

    assert code == 2
    assert get_letter_settings(career.first_profile.id, session, "es") is None


def test_a_second_apply_updates_instead_of_duplicating(session, career, tmp_path):
    path = write_payload(tmp_path)
    kwargs = {"confirm": lambda _prompt: "IMPORT", "scope": lambda: scope(session)}
    letters_import.main(["--email", career.first.email, "--file", path, "--apply"], **kwargs)
    session.expire_all()
    letters_import.main(["--email", career.first.email, "--file", path, "--apply"], **kwargs)

    session.expire_all()
    names = sorted(letter.name for letter in list_letters(career.first_profile.id, session))
    assert names.count("Corporativo") == 1 and names.count("Sin puesto") == 1, (
        "upsert, never duplicate"
    )


def test_the_production_database_is_refused(
    monkeypatch, test_settings, session, career, tmp_path, capsys
):
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://user:secret@REDACTED-PROD-ENDPOINT/db",
    )
    get_settings.cache_clear()

    code = letters_import.main(
        ["--email", career.first.email, "--file", write_payload(tmp_path), "--apply"],
        confirm=lambda _prompt: "IMPORT",
        scope=lambda: scope(session),
    )

    assert code == 3
    assert "production database" in capsys.readouterr().err
    assert get_letter_settings(career.first_profile.id, session, "es") is None


def test_the_refusal_helper_is_a_string_check():
    assert letters_import.refusal_reason("sqlite:///x.db", prod=False) is None
    assert (
        letters_import.refusal_reason(
            "postgresql://u:p@REDACTED-PROD-ENDPOINT/db", prod=False
        )
        is not None
    )
    assert (
        letters_import.refusal_reason(
            "postgresql://u:p@REDACTED-PROD-ENDPOINT/db", prod=True
        )
        is None
    )


def test_a_bad_payload_is_refused_before_anything_runs(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")

    with pytest.raises(letters_import.ImportRefused):
        letters_import.load_payload(path)


# --- one template per track (F8) ---------------------------------------------------


def run_import(session, career, tmp_path, payload, *, apply=True, capsys=None):
    argv = ["--email", career.first.email, "--file", write_payload(tmp_path, payload)]
    if apply:
        argv.append("--apply")
    code = letters_import.main(
        argv, confirm=lambda _prompt: "IMPORT", scope=lambda: scope(session)
    )
    assert code == 0
    session.expire_all()
    return capsys.readouterr().out if capsys is not None else ""


def template(name, *, track_name="Analista de datos", lang="es"):
    entry = {
        "name": name,
        "applies_when": "",
        "presentation": f"Presentación de {name}.",
        "achievements": "Logros.",
        "lang": lang,
    }
    if track_name is not None:
        entry["track_name"] = track_name
    return entry


def linked_names(session, career):
    return sorted(
        letter.name
        for letter in list_letters(career.first_profile.id, session)
        if letter.track_id == career.first_track.id
    )


def test_a_second_template_for_the_same_track_is_imported_unlinked_and_listed(
    session, career, tmp_path, capsys
):
    payload = {"templates": [template("Primera"), template("Segunda")]}

    out = run_import(session, career, tmp_path, payload, capsys=capsys)

    assert linked_names(session, career) == ["Primera"], "one template per track"
    letters = {letter.name: letter for letter in list_letters(career.first_profile.id, session)}
    assert letters["Segunda"].track_id is None, "imported, not dropped"
    assert "track 'Analista de datos' already has a template; imported unlinked" in out


def test_a_track_that_already_has_a_template_keeps_it(session, career, tmp_path, capsys):
    from src.letters import save_track_template

    save_track_template(
        career.first_profile.id,
        session,
        career.first_track,
        presentation="La que ya tenía.",
        achievements="Logros.",
    )
    session.commit()

    out = run_import(
        session, career, tmp_path, {"templates": [template("Nueva")]}, capsys=capsys
    )

    assert linked_names(session, career) == ["Analista de datos"], "the existing one stays"
    assert "already has a template; imported unlinked" in out
    letters = {letter.name: letter for letter in list_letters(career.first_profile.id, session)}
    assert letters["Nueva"].track_id is None


def test_a_template_in_another_language_than_its_track_is_imported_unlinked(
    session, career, tmp_path, capsys
):
    payload = {"templates": [template("English one", lang="en")]}

    out = run_import(session, career, tmp_path, payload, capsys=capsys)

    assert linked_names(session, career) == []
    assert "template is in EN and track 'Analista de datos' is in ES; imported unlinked" in out
    names = [letter.name for letter in list_letters(career.first_profile.id, session)]
    assert "English one" in names


def test_a_template_without_a_track_name_is_unlinked(session, career, tmp_path):
    run_import(session, career, tmp_path, {"templates": [template("Suelta", track_name=None)]})

    letters = {letter.name: letter for letter in list_letters(career.first_profile.id, session)}
    assert letters["Suelta"].track_id is None


def test_a_matching_template_takes_a_track_that_has_none(session, career, tmp_path):
    run_import(session, career, tmp_path, {"templates": [template("Primera")]})

    letters = {letter.name: letter for letter in list_letters(career.first_profile.id, session)}
    assert letters["Primera"].track_id == career.first_track.id
    assert letters["Primera"].lang == career.first_track.lang


def test_running_the_import_again_keeps_the_link_and_lists_nothing(
    session, career, tmp_path, capsys
):
    payload = {"templates": [template("Primera")]}
    run_import(session, career, tmp_path, payload)

    out = run_import(session, career, tmp_path, payload, capsys=capsys)

    assert linked_names(session, career) == ["Primera"]
    assert "already has a template" not in out
    letters = list_letters(career.first_profile.id, session)
    assert sum(letter.name == "Primera" for letter in letters) == 1


def test_the_dry_run_lists_the_same_lines_and_writes_nothing(
    session, career, tmp_path, capsys
):
    payload = {"templates": [template("Primera"), template("Segunda")]}

    out = run_import(session, career, tmp_path, payload, apply=False, capsys=capsys)

    assert "already has a template; imported unlinked" in out
    assert "dry run: nothing written" in out
    assert linked_names(session, career) == []
    assert all(
        letter.name not in ("Primera", "Segunda")
        for letter in list_letters(career.first_profile.id, session)
    )
