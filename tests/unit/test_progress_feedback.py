"""§12.3: every form that pays for a model call says it is working.

The queue's promise is narrow: the run forms carry `data-progress`, the accept, save and
discard forms do not, and one shared script turns the attribute into a locked button and a
status line with a counter. The tests read the templates for the first two and the page for
the third.
"""

import re
from pathlib import Path

import pytest

from src.i18n.strings import STRINGS, t
from src.letters import save_letter_settings, save_track_template
from src.models import Resume
from tests.conftest import login
from tests.unit.test_generation import rephrase_url, stored_application, story_bullets_url

TEMPLATES = Path(__file__).resolve().parents[2] / "src" / "web" / "templates"
FORM_TAG = re.compile(r"<form\b[^>]*>", re.S)

# The forms that call a model, by template, and the key each one carries.
RUN_FORMS = {
    "analyze/form.html": "analyze",
    # F11.3, F11.7: re-analysing a posting on another CV is a paid run too.
    "analyze/report.html": "analyze",
    "attempts/saved_cv.html": "analyze",
    "import/upload.html": "import",
    "import/review.html": "import",
    "generate/_summary_body.html": "generate",
    "generate/_keywords_body.html": "generate",
    "generate/bullet.html": "generate",
    "generate/story.html": "generate",
    "letters/letter.html": "letter",
    "tracks/letter.html": "letter",
}

# Forms that save, accept or discard what a call already produced; none may carry it.
NON_RUN_FORMS = (
    ("import/upload.html", "/discard"),
    ("import/review.html", "/review"),
    ("import/merge.html", "/merge"),
    ("generate/_summary_body.html", "/summary/accept"),
    ("generate/bullet.html", "/rephrase/accept"),
    ("generate/story.html", "/bullets/accept"),
    ("letters/letter.html", "/letter/save"),
    ("tracks/letter.html", '/letter"'),
)

PROGRESS_KEYS = ("analyze", "import", "generate", "letter")


def form_tags(template: str) -> list[str]:
    return FORM_TAG.findall((TEMPLATES / template).read_text(encoding="utf-8"))


@pytest.mark.parametrize(("template", "key"), sorted(RUN_FORMS.items()))
def test_each_run_form_carries_its_progress_key(template, key):
    tagged = [tag for tag in form_tags(template) if "data-progress" in tag]

    assert len(tagged) == 1, f"{template} has exactly one run form"
    assert f'data-progress="{key}"' in tagged[0]


@pytest.mark.parametrize(("template", "action"), NON_RUN_FORMS)
def test_accept_save_and_discard_forms_do_not(template, action):
    matching = [tag for tag in form_tags(template) if action in tag]

    assert matching, f"{template} still has its {action} form"
    assert all("data-progress" not in tag for tag in matching)


def test_no_other_template_carries_the_attribute():
    carriers = {
        path.relative_to(TEMPLATES).as_posix()
        for path in TEMPLATES.rglob("*.html")
        if any("data-progress=" in tag for tag in FORM_TAG.findall(path.read_text("utf-8")))
    }

    assert carriers == set(RUN_FORMS), "the attempt modal keeps its own in-flight state"


def run_form(page: str, key: str) -> str:
    match = re.search(rf'<form\b[^>]*data-progress="{key}".*?</form>', page, re.S)
    assert match, f"the page renders a {key} run form"
    return match.group(0)


def assert_status_under_the_button(page: str, key: str) -> None:
    form = run_form(page, key)
    button = form.index("</button>")
    status = form.index('role="status"')

    assert button < status, "the status line sits directly under the submit button"
    assert re.search(r'<p role="status" hidden\b', form), "and is hidden until submit"
    assert t(f"progress.{key}", "es") in form


def test_the_analyze_and_import_forms_render_the_status_line(client, career):
    login(client, career.first.email)

    assert_status_under_the_button(client.get("/analyze").text, "analyze")
    assert_status_under_the_button(client.get("/import").text, "import")


def test_the_import_retry_form_renders_the_status_line(client, session, career):
    resume = Resume(
        profile_id=career.first_profile.id,
        filename="cv.pdf",
        file_bytes=b"%PDF-1.4",
        sha256="0" * 64,
        draft=None,
        gate={"findings": []},
    )
    session.add(resume)
    session.commit()
    login(client, career.first.email)

    page = client.get(f"/import/{resume.id}").text

    assert f'action="/import/{resume.id}/retry"' in page
    assert_status_under_the_button(page, "import")


def test_the_generate_and_letter_run_forms_render_the_status_line(
    client, session, career, test_settings
):
    application = stored_application(session, career)
    save_letter_settings(
        career.first_profile.id,
        session,
        lang="es",
        header="Ana\npersona2@example.com",
        greeting="Estimado equipo,",
        closing="Quedo a su disposición.",
        sign_off="Ana",
        voice_notes="Tuteo.",
    )
    # The letter page offers its run form once the track has a template (F8).
    save_track_template(
        career.first_profile.id,
        session,
        career.first_track,
        presentation="Me presento.",
        achievements="Logros.",
    )
    session.commit()
    login(client, career.first.email)

    summary = client.get(f"/applications/{application.id}/summary").text
    bullet = client.get(rephrase_url(application, career.first_bullet.id)).text
    story = client.get(story_bullets_url(career.first_story)).text
    letter_page = client.get(f"/applications/{application.id}/letter").text
    template_page = client.get(f"/tracks/{career.first_track.id}/letter").text

    for page in (summary, bullet, story):
        assert_status_under_the_button(page, "generate")
    for page in (letter_page, template_page):
        assert_status_under_the_button(page, "letter")


def test_the_page_includes_the_progress_script_once(client, career):
    login(client, career.first.email)

    page = client.get("/analyze").text

    assert page.count("form[data-progress]") == 1
    assert page.count("<script>") == page.count("</script>")


def test_the_script_handles_the_back_forward_cache(client, career):
    login(client, career.first.email)

    page = client.get("/analyze").text

    assert "'pageshow'" in page and "event.persisted" in page
    assert "button.disabled = true" in page and "button.disabled = false" in page
    assert "localStorage" not in page and "sessionStorage" not in page, "nothing is stored"


@pytest.mark.parametrize("key", PROGRESS_KEYS)
def test_the_strings_exist_in_both_languages_with_an_honest_range(key):
    entry = STRINGS[f"progress.{key}"]
    expected = "20–40 s" if key in ("analyze", "import") else "10–30 s"

    assert set(entry) == {"es", "en"}
    assert expected in entry["es"] and expected in entry["en"]
