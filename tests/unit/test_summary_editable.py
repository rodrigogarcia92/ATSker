"""The proposed summary is editable and re-checked on accept (queue P5)."""

import json

from src.extract import client as extract_client
from src.models import Summary
from tests.conftest import login
from tests.unit.test_generation import stored_application

GOOD = "Analista de datos que automatizó el reporte con Python."


def payload(career, text=GOOD):
    return json.dumps({"summary": {"text": text, "cites": [str(career.first_bullet.id)]}})


def accept(client, application, career, *, text=None, dialog=True, **extra):
    data = {"payload": payload(career), **extra}
    if text is not None:
        data["text"] = text
    if dialog:
        data["dialog"] = "1"
    return client.post(
        f"/applications/{application.id}/summary/accept", data=data, follow_redirects=False
    )


def forbid_provider(monkeypatch):
    calls = []

    def post(payload, api_key):
        calls.append(payload)
        raise AssertionError("an edit must not call the provider")

    monkeypatch.setattr(extract_client, "_post", post)
    return calls


def test_an_edit_that_removes_the_offending_word_is_accepted_and_stored_as_edited(
    client, session, career, test_settings, monkeypatch
):
    calls = forbid_provider(monkeypatch)
    application = stored_application(session, career)
    login(client, career.first.email)
    edited = "Analista de datos que automatizó el reporte con Python en producción."

    # the original, with a number no source has, is refused; the edit without it is accepted
    refused = accept(client, application, career, text=GOOD + " 99%")
    assert refused.status_code == 200
    accepted = accept(client, application, career, text=edited)

    assert accepted.status_code == 303
    session.expire_all()
    assert session.query(Summary).filter_by(text=edited).count() == 1
    assert session.query(Summary).filter_by(text=GOOD + " 99%").count() == 0
    assert calls == []


def test_an_edit_adding_an_unsourced_number_re_renders_the_popup_with_the_users_text(
    client, session, career, test_settings, monkeypatch
):
    calls = forbid_provider(monkeypatch)
    application = stored_application(session, career)
    login(client, career.first.email)
    before = session.query(Summary).count()
    edited = GOOD + " Mejoré un 77% el cierre."

    answer = accept(client, application, career, text=edited)

    assert answer.status_code == 200
    page = answer.text
    assert "<html" not in page.lower(), "the pop-up's partial, not the full page"
    assert edited in page, "the user's own text is kept in the text area"
    assert "77%" in page and "<mark" in page, "the literal violation is shown"
    assert 'data-check="title"' in page, "the checklist is recomputed on the edited text"
    assert calls == [], "no provider call"
    session.expire_all()
    assert session.query(Summary).count() == before, "nothing was written"


def test_without_the_dialog_the_full_page_comes_back_with_the_text_kept(
    client, session, career, test_settings, monkeypatch
):
    forbid_provider(monkeypatch)
    application = stored_application(session, career)
    login(client, career.first.email)
    edited = GOOD + " Mejoré un 77% el cierre."

    answer = accept(client, application, career, text=edited, dialog=False)

    assert answer.status_code == 200
    assert "<html" in answer.text.lower() and edited in answer.text


def test_the_page_without_a_text_field_still_accepts_the_payloads_text(
    client, session, career, test_settings, monkeypatch
):
    forbid_provider(monkeypatch)
    application = stored_application(session, career)
    login(client, career.first.email)

    answer = accept(client, application, career, dialog=False)

    assert answer.status_code == 303
    session.expire_all()
    assert session.query(Summary).filter_by(text=GOOD).count() == 1


def test_an_empty_edit_is_refused(client, session, career, test_settings, monkeypatch):
    forbid_provider(monkeypatch)
    application = stored_application(session, career)
    login(client, career.first.email)
    before = session.query(Summary).count()

    answer = accept(client, application, career, text="   ")

    assert answer.status_code == 200
    session.expire_all()
    assert session.query(Summary).count() == before


def test_a_foreign_application_is_a_404(client, session, career, test_settings, monkeypatch):
    forbid_provider(monkeypatch)
    application = stored_application(session, career)
    login(client, career.second.email)

    assert accept(client, application, career, text=GOOD).status_code == 404
