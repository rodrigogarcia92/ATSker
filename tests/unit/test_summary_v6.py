"""summary_v6: the career title the summary opens with, and its 60-100 words (queue S5b).

`career_title` reads the profile's roles and the track's headlines and decides; the model
never picks a title. The route test runs on the provider stub: no real call.
"""

from datetime import date

from src.extract.prompts import SUMMARY_V4, SUMMARY_V5, SUMMARY_V6
from src.generate.summary_rules import career_title, check_length
from src.roles import create_role
from src.tracks import create_track
from src.vocabulary import alias_map
from tests.conftest import login
from tests.unit.test_generation import stored_application
from tests.unit.test_summary_v4 import GOOD, generate, queue  # noqa: F401

# --- the prompt ---------------------------------------------------------------------


def test_the_v6_prompt_opens_with_the_career_title_and_states_the_range():
    assert SUMMARY_V6.version == "summary_v6"
    assert SUMMARY_V4.version == "summary_v4" and SUMMARY_V5.version == "summary_v5"
    system = SUMMARY_V6.system
    assert "1. Open the first sentence with the career title given in the message" in system
    assert "Do not use any other job title." in system
    assert "posting's title exactly as given" not in system, "the old rule 1 is gone"
    assert "between 60 and 100 words" in system and "at most 80 words" not in system
    assert "Its job is to get the person a call" in system
    assert "place each of them inside what the person actually did" in system
    assert "Never return a list of skills" in system, "v4's context rule is unchanged"


def test_the_v6_template_has_no_posting_title():
    assert "The career title, to be used exactly as written:" in SUMMARY_V6.template
    assert "{title}" in SUMMARY_V6.template
    assert "The posting's title" not in SUMMARY_V6.template


# --- the length ---------------------------------------------------------------------


def test_the_range_is_sixty_to_a_hundred_words():
    assert not check_length(" ".join(["palabra"] * 59))["ok"]
    assert check_length(" ".join(["palabra"] * 60))["ok"]
    assert check_length(" ".join(["palabra"] * 100))["ok"]
    assert not check_length(" ".join(["palabra"] * 101))["ok"]
    assert check_length(GOOD)["ok"], "the text the route tests use is inside the range"


# --- the career title ---------------------------------------------------------------


def test_the_posting_title_is_used_when_a_held_title_carries_all_of_its_words(session, career):
    """The role title and the headline are both "Analista de datos" in the fixture."""
    title = career_title(
        career.first_profile.id,
        session,
        career.first_track,
        "Analista de Datos",
        alias_map(session),
        "es",
    )

    assert title == "Analista de Datos", "the posting's own words, as given"


def test_a_posting_title_sharing_only_one_word_is_not_held(session, career):
    title = career_title(
        career.first_profile.id,
        session,
        career.first_track,
        "Analista financiero",
        alias_map(session),
        "es",
    )

    assert title == "Analista de datos", "the track's headline, the user's own title"


def test_the_headline_is_read_in_the_postings_language(session, career):
    pid = career.first_profile.id
    track = create_track(
        pid,
        session,
        name="Analista",
        applies_when="",
        lang="es",
        headline_es="Analista de datos",
        headline_en="Data analyst",
    )
    session.commit()

    aliases = alias_map(session)

    assert career_title(pid, session, track, "Market Analyst", aliases, "es") == "Analista de datos"
    assert career_title(pid, session, track, "Market Analyst", aliases, "en") == "Data analyst"


def test_the_latest_role_title_stands_in_when_there_is_no_headline(session, career):
    pid = career.first_profile.id
    track = create_track(pid, session, name="Sin título", applies_when="", lang="es")
    create_role(
        pid,
        session,
        employer="Globex",
        title_es="Becaria",
        title_en="Intern",
        start_date=date(2019, 1, 1),
    )
    create_role(
        pid,
        session,
        employer="Banco Andino",
        title_es=None,
        title_en="Data analyst",
        start_date=date(2024, 1, 1),
    )
    session.commit()

    aliases = alias_map(session)

    assert career_title(pid, session, track, "Market Analyst", aliases, "en") == "Data analyst"
    assert career_title(pid, session, track, "Market Analyst", aliases, "es") == "Data analyst", (
        "the only title the latest role has, read as the roles are read"
    )


# --- the route ----------------------------------------------------------------------


def test_the_route_sends_and_shows_the_career_title(client, session, career, queue):  # noqa: F811
    application = stored_application(session, career)
    application.title = "Market Analyst"
    session.commit()
    stub = queue(GOOD)
    login(client, career.first.email)

    page = generate(client, application).text

    assert "The career title, to be used exactly as written:\nAnalista de datos" in stub.user()
    assert "Market Analyst" not in stub.user(), "the posting's title never reaches the prompt"
    assert "Título de carrera: Analista de datos" in page
    assert "Market Analyst" not in page, "and the pop-up names the career title only"
    assert "palabras" not in page.lower(), "no word count or limit is shown"
