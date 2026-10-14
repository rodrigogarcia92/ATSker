"""The summary pop-up shows what it did: checklist and base line (queue M4, §12.5)."""

import uuid

import pytest

from src.summaries import create_summary, set_summary_active
from src.tracks import set_track_summary
from tests.conftest import login
from tests.unit.test_generation import stored_application
from tests.unit.test_summary_v4 import GOOD, NO_TITLE, Queue, generate, queue  # noqa: F401


def rows(page: str) -> dict[str, str]:
    """data-check rows → their visible text, whitespace squashed."""
    import re

    found = {}
    for rule, body in re.findall(r'<li data-check="(\w+)"[^>]*>(.*?)</li>', page, re.S):
        found[rule] = " ".join(re.sub(r"<[^>]+>", " ", body).split())
    return found


def test_a_passing_proposal_shows_two_ticks_and_no_word_count(
    client, session, career, queue  # noqa: F811
):
    queue(GOOD)
    application = stored_application(session, career)
    login(client, career.first.email)

    page = generate(client, application).text
    shown = rows(page)

    assert set(shown) == {"title", "skills"}, "the length row is never shown"
    assert shown["title"].startswith("✓ Título de carrera: Analista de datos")
    assert shown["skills"].startswith("✓ Habilidades clave nombradas (1): python")
    assert all("(cumple)" in text for text in shown.values()), "a word, not only a colour"
    assert "palabras" not in page.lower(), "no word count or limit anywhere"


def test_a_failing_proposal_shows_crosses_with_the_word_and_can_still_be_accepted(
    client, session, career, queue  # noqa: F811
):
    queue(NO_TITLE, NO_TITLE)
    application = stored_application(session, career)
    login(client, career.first.email)

    page = generate(client, application).text

    shown = rows(page)
    assert shown["title"].startswith("✗") and "(no cumple)" in shown["title"]
    assert set(shown) == {"title", "skills"}
    assert "/summary/accept" in page, "a style rule never blocks acceptance"


@pytest.mark.parametrize(
    ("origin", "expected"),
    [
        ("track", "Basado en el resumen de tu línea «"),
        ("cv", "Basado en el resumen de tu CV subido"),
        ("other", "Basado en tu resumen en inglés, traducido"),
        ("none", "No había un resumen base: escrito desde tus bullets"),
    ],
)
def test_the_base_line_for_each_origin(client, session, career, queue, origin, expected):  # noqa: F811
    pid = career.first_profile.id
    if origin == "track":
        base = create_summary(pid, session, text="Analista.", lang="es")
        set_track_summary(pid, session, career.first_track.id, lang="es", summary_id=base.id)
    elif origin == "cv":
        create_summary(pid, session, text="Analista.", lang="es", source_resume_id=uuid.uuid4())
    elif origin == "other":
        base = create_summary(pid, session, text="Analyst.", lang="en")
        set_track_summary(pid, session, career.first_track.id, lang="en", summary_id=base.id)
    queue(GOOD)
    application = stored_application(session, career)
    login(client, career.first.email)

    page = generate(client, application).text

    assert expected in page
    assert page.count("Basado en") + page.count("No había un resumen base") == 1


def test_an_inactive_cv_summary_is_not_reported_as_the_base(client, session, career, queue):  # noqa: F811
    pid = career.first_profile.id
    retired = create_summary(pid, session, text="Viejo.", lang="es", source_resume_id=uuid.uuid4())
    set_summary_active(pid, session, retired.id, active=False)
    queue(GOOD)
    application = stored_application(session, career)
    login(client, career.first.email)

    assert "No había un resumen base" in generate(client, application).text


def test_the_pop_up_speaks_english_for_an_english_interface(client, session, career, queue):  # noqa: F811
    career.first.ui_lang = "en"
    session.commit()
    queue(NO_TITLE, NO_TITLE)
    application = stored_application(session, career)
    application.title = "Platform Engineer"
    session.commit()
    login(client, career.first.email)

    page = generate(client, application).text
    shown = rows(page)

    assert "Career title: Analista de datos" in shown["title"] and "(not met)" in shown["title"]
    assert "Key skills named (1)" in shown["skills"]
    assert set(shown) == {"title", "skills"}, "no length row, no word count"
    assert "There was no base summary: written from your bullets" in page


def test_a_short_shortlist_says_how_many_there_were(client, session, career, queue):  # noqa: F811
    queue(GOOD)
    application = stored_application(session, career)
    login(client, career.first.email)

    page = generate(client, application).text

    assert "respalda directamente en esta oferta: 1." in page
