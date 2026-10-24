"""D7's "Dilo con sus palabras" group on the Keywords card (PRD F7.5).

The group holds every `pool`, `bullet` and `graded` item — a skill the user is already
credited with but a recruiter's search would miss — and is rendered before the
equivalents. It is advice only: no number on the page moves because of it.
"""

import copy

from tests.conftest import login
from tests.unit.test_advice import bullet, grade
from tests.unit.test_analysis import text_of
from tests.unit.test_keyword_advice import card_of, page_report, vocabulary
from tests.unit.test_report_layout import section


def test_the_say_it_group_comes_first_and_the_equivalents_follow(client, session, career):
    vocabulary(session, ("sql", None), ("tableau", "bi"), ("power bi", "bi"))
    career.first_profile.skills = ["sql", "tableau"]
    session.commit()
    application = page_report(session, career, ["Power BI", "SQL"], must=["SQL", "Power BI"])
    login(client, career.first.email)

    card = text_of(section(client.get(f"/applications/{application.id}").text, "recommendations"))

    assert "Dilo con sus palabras" in card
    assert "El evaluador ya te reconoce estas habilidades, pero un reclutador que busque" in card
    assert card.index("Dilo con sus palabras") < card.index("SQL")
    assert card.index("Dilo con sus palabras") < card.index("Power BI")


def test_a_graded_item_sits_in_the_group_and_names_the_bullet_it_cites(client, session, career):
    cited = bullet(session, career, "Puse modelos de crédito en producción", [])
    application = page_report(
        session,
        career,
        ["machine learning"],
        nice=["machine learning"],
        grades=[
            grade(
                "Machine learning aplicado al riesgo de crédito",
                level=2,
                bullet_id=cited.id,
                text="Puse modelos de crédito en producción",
            )
        ],
    )
    login(client, career.first.email)

    card = text_of(section(client.get(f"/applications/{application.id}").text, "recommendations"))

    assert "Dilo con sus palabras" in card
    assert "Lo tienes — dilo con sus palabras" in card
    assert (
        "el evaluador te lo reconoce en «Puse modelos de crédito en producción»; "
        "usa «machine learning» en ese bullet." in card
    )


def test_an_empty_group_renders_nothing(client, session, career):
    vocabulary(session, ("sql", None), ("tableau", "bi"), ("power bi", "bi"))
    career.first_profile.skills = ["sql", "tableau"]
    session.commit()
    only_say_it = page_report(session, career, ["SQL"], must=["SQL"])
    only_equivalent = page_report(session, career, ["Power BI"], must=["Power BI"])
    login(client, career.first.email)

    say_it_card = text_of(card_of(client.get(f"/applications/{only_say_it.id}").text))
    equivalent_card = text_of(card_of(client.get(f"/applications/{only_equivalent.id}").text))

    assert "Dilo con sus palabras" in say_it_card
    assert "Equivalente" not in say_it_card, "nothing to show, so no equivalent list"
    assert "Dilo con sus palabras" not in equivalent_card, "an empty group renders nothing"
    assert "Equivalente" in equivalent_card and "tienes tableau" in equivalent_card


def test_the_group_never_moves_job_match_or_the_ceiling(client, session, career):
    """D7 is advice only: the same report with and without a group shows the same numbers."""
    cited = bullet(session, career, "Puse modelos de crédito en producción", [])
    grades = [
        grade(
            "Machine learning aplicado al riesgo de crédito",
            level=2,
            bullet_id=cited.id,
            text="Puse modelos de crédito en producción",
        )
    ]
    grouped = page_report(
        session, career, ["machine learning"], nice=["machine learning"], grades=grades
    )
    plain = page_report(
        session, career, [], nice=["machine learning"], grades=copy.deepcopy(grades)
    )
    login(client, career.first.email)

    first = section(client.get(f"/applications/{grouped.id}").text, "fit")
    second = section(client.get(f"/applications/{plain.id}").text, "fit")

    assert "Dilo con sus palabras" not in first, "the group is in the card, not the fit section"
    assert first == second
