"""The document drop zone (PRD §12.4, V4): one component on Importar CV and in the modal.

The zone is a `<label>` for a real `<input type="file">`, so it works as a plain file field
without script; one small script in the base template adds the drag-and-drop and the
client-side checks. The server keeps its own checks, so the normal multipart upload on both
pages still works unchanged (the existing import and attempt suites cover that).
"""

import re

import pytest

from src.extract import client as extract_client
from src.i18n import t
from src.web.routes.ingest import MAX_UPLOAD_BYTES
from tests.conftest import login
from tests.unit.attempt_support import AttemptProvider, analyzed_application, resume_payload


@pytest.fixture
def provider(monkeypatch, test_settings, career) -> AttemptProvider:
    stub = AttemptProvider(
        bullet_id=str(career.first_bullet.id),
        resume=resume_payload(career.first_bullet.text_es),
    )
    monkeypatch.setattr(extract_client, "_post", stub)
    return stub


def _pages(client, session, career, provider) -> dict[str, str]:
    login(client, career.first.email)
    application, _analysis = analyzed_application(session, career, provider)
    return {
        "import": client.get("/import").text,
        "modal": client.get(f"/applications/{application.id}").text,
    }


def _input(raw: str, input_id: str) -> str:
    return re.search(rf'<input id="{input_id}"[^>]*>', raw, re.S).group(0)


@pytest.mark.parametrize(
    ("page", "input_id", "accept"),
    [("import", "file", ".pdf,.docx"), ("modal", "attempt-file", ".docx,.pdf")],
)
def test_both_pages_render_a_label_for_a_real_required_file_input(
    client, session, career, provider, page, input_id, accept
):
    raw = _pages(client, session, career, provider)[page]

    card = re.search(r"<label[^>]*data-dropzone[^>]*>", raw, re.S).group(0)
    assert f'for="{input_id}"' in card
    field = _input(raw, input_id)
    assert 'type="file"' in field and 'name="file"' in field
    assert f'accept="{accept}"' in field
    assert " required" in field
    assert "sr-only" in field, "visually hidden but still focusable"
    assert f'data-accept="{accept}"' in card
    assert "Arrastra tu CV aquí o elige un archivo" in raw


def test_the_formats_line_is_computed_from_the_upload_limit(client, session, career, provider):
    pages = _pages(client, session, career, provider)
    megabytes = f"{MAX_UPLOAD_BYTES / 1048576:g}"

    for raw in pages.values():
        assert f".docx o .pdf · máx. {megabytes} MB" in raw
        assert f'data-max-bytes="{MAX_UPLOAD_BYTES}"' in raw
        assert f"El archivo supera los {megabytes} MB" in raw
    assert t("dropzone.formats", "en", mb=megabytes) == ".docx or .pdf · max 10 MB"


def test_the_script_is_included_once_and_the_login_page_has_no_zone(
    client, session, career, provider
):
    pages = _pages(client, session, career, provider)

    for raw in pages.values():
        assert raw.count("§12.4: the one script behind every [data-dropzone]") == 1
    assert raw.count("data-dropzone-root") >= 1
    assert raw.count("<label") >= 1


def test_every_dropzone_string_exists_in_both_languages():
    for key in (
        "dropzone.prompt",
        "dropzone.formats",
        "dropzone.release",
        "dropzone.change",
        "dropzone.one_file",
        "dropzone.bad_type",
        "dropzone.too_big",
    ):
        assert t(key, "es", mb=10) != key and t(key, "en", mb=10) != key
        assert t(key, "es", mb=10) != t(key, "en", mb=10)


def _script(raw: str) -> str:
    start = raw.index("§12.4: the one script behind every [data-dropzone]")
    return raw[start : raw.index("</script>", start)]


def test_the_script_handles_the_drag_events_and_the_three_checks(
    client, session, career, provider
):
    script = _script(_pages(client, session, career, provider)["import"])

    for event in ("'dragenter'", "'dragover'", "'dragleave'", "'drop'"):
        assert event in script
    # One file, the extension, the size — each with its own message.
    assert "files.length !== 1" in script and "dataset.oneFile" in script
    assert "endsWith(ext)" in script and "dataset.badType" in script
    assert "file.size > maxBytes" in script and "dataset.tooBig" in script
    # A drop puts the file into the same input and announces it; a refusal empties it.
    assert "input.files = files" in script
    assert "new Event('change'" in script
    assert "input.value = ''" in script
    # The picker is held to the same checks as a drop.
    assert "input.addEventListener('change'" in script
    # A drop outside a zone never opens the file.
    outside = script[: script.index("function size")]
    assert "document.addEventListener(type" in outside and "event.preventDefault()" in outside
    assert "closest('[data-dropzone-root]')" in outside
    # No upload on drop.
    assert "fetch(" not in script and "XMLHttpRequest" not in script


def test_the_zone_has_an_alert_line_and_a_change_control(client, session, career, provider):
    for raw in _pages(client, session, career, provider).values():
        assert re.search(r'<p role="alert" hidden data-dropzone-error', raw)
        change = re.search(r"<button[^>]*data-dropzone-change[^>]*>.*?</button>", raw, re.S)
        assert change and 'type="button"' in change.group(0)
        assert "btn " in change.group(0), "a .btn is a 44 px target"
        assert "Cambiar" in change.group(0)
