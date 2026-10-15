"""§12.1 item 6: the recommendations in one column, grouped (queue U5).

The items are stored as kind, evidence and values; the page groups them under headings
with counts, merges the skills into one card, shows the first three and keeps the rest
behind "Ver todas (N)". The grouping is a function (`advice_layout`), so it is tested as
one, and the page is read for what a reader sees.
"""

import re

from src.web.alerts import advice_layout
from tests.conftest import login
from tests.unit.test_analysis import text_of
from tests.unit.test_report_layout import section, stored

ITEM_ROW = '<li class="flex items-start gap-3 px-4 py-3">'
LONG = "Diseñé el modelo y la arquitectura de datos de soluciones BI en Power BI, con medidas."


def promote(position: int = 7, requirement: str = "sql") -> dict:
    return {
        "kind": "promote_bullet",
        "bullet_id": f"b{position}",
        "evidence": LONG,
        "values": {"position": position, "requirement": requirement},
    }


def skill(name: str) -> dict:
    return {
        "kind": "surface_skill",
        "canonical": name,
        "evidence": name,
        "values": {"canonical": name},
    }


def add(canonical: str = "dbt") -> dict:
    return {
        "kind": "add_bullet",
        "bullet_id": "x",
        "canonical": canonical,
        "evidence": LONG,
        "values": {"canonical": canonical},
    }


def title_headline() -> dict:
    return {"kind": "title_headline", "values": {}}


def language() -> dict:
    return {
        "kind": "language",
        "values": {"language": "en", "bullets": 3, "total_bullets": 9, "titles": 1},
    }


RANKING = {
    "candidates": [
        {
            "name": "Analista de datos",
            "chosen": True,
            "job_match": 70,
            "sub_scores": {"skills": 70, "experience": 80, "title": 50, "keywords": 40},
        }
    ],
    "margin": None,
    "tie_break": None,
    "justification": None,
    "not_graded": [],
}


def recommendations(client, session, career, advice, **changes) -> str:
    application = stored(session, career, advice=advice, **changes)
    login(client, career.first.email)
    return section(client.get(f"/applications/{application.id}").text, "recommendations")


def headings(page: str) -> list[str]:
    return [text_of(h3).strip() for h3 in re.findall(r"<h3\b[^>]*>(.*?)</h3>", page, re.S)]


def test_there_is_no_two_column_grid_in_the_section(client, session, career):
    page = recommendations(
        client, session, career, [promote(), skill("sql"), add()], recommendation=RANKING
    )

    assert "sm:grid-cols-2" not in page
    assert "grid-cols" not in page, "one full-width column"


def test_the_track_ranking_is_its_own_card_before_the_first_group(client, session, career):
    page = recommendations(client, session, career, [promote()], recommendation=RANKING)

    assert 'id="track-ranking"' in page
    assert page.index('id="track-ranking"') < page.index("<h3")
    assert "Analista de datos" in text_of(page[: page.index("<h3")])


def test_no_ranking_card_without_a_recommendation(client, session, career):
    page = recommendations(client, session, career, [promote()])

    assert 'id="track-ranking"' not in page


def test_three_skills_render_one_card_listing_all_three_names(client, session, career):
    page = recommendations(
        client, session, career, [skill("microsoft excel"), skill("power bi"), skill("sql")]
    )

    sentence = "Añade a las habilidades de la línea: la oferta las pide y las tienes evidenciadas."
    assert text_of(page).count(sentence) == 1, "one sentence, one card — not one per skill"
    card = page[page.index(sentence) :]
    for name in ("microsoft excel", "power bi", "sql"):
        assert f">{name}</li>" in card
    assert headings(page) == ["Habilidades · 3"]


def test_groups_come_in_the_stated_order_with_their_counts(client, session, career):
    items = [
        language(),
        title_headline(),
        skill("sql"),
        skill("power bi"),
        add(),
        promote(7),
        promote(5),
    ]
    page = recommendations(client, session, career, items)

    assert headings(page) == [
        "Ordena tus bullets · 2",
        "Añade a esta línea · 1",
        "Habilidades · 2",
        "Búsquedas y título · 1",
        "Idioma · 1",
    ], "the five groups in order, each with its count"


def test_a_group_with_no_items_shows_no_heading(client, session, career):
    page = recommendations(client, session, career, [add()])

    assert headings(page) == ["Añade a esta línea · 1"]


def test_with_six_items_exactly_three_are_outside_ver_todas(client, session, career):
    items = [promote(position) for position in range(4, 10)]
    page = recommendations(client, session, career, items)

    start = page.find('<details class="disclosure mt-4')
    assert start != -1, "the rest sit behind a toggle"
    inside = page[start:]
    assert "Ver todas (6)" in text_of(inside), "the toggle names every item"
    assert " open" not in inside[: inside.index(">")], "closed by default"
    outside = page.replace(inside, "")
    assert outside.count(ITEM_ROW) == 3
    assert inside.count(ITEM_ROW) == 3, "the rest, in the same groups and order"
    assert headings(inside) == ["Ordena tus bullets · 3"]


def test_up_to_three_items_have_no_ver_todas(client, session, career):
    page = recommendations(client, session, career, [promote(7), promote(6), add()])

    assert "Ver todas" not in page
    assert page.count(ITEM_ROW) == 3


def test_a_promote_item_has_its_position_chip_and_clamped_evidence(client, session, career):
    page = recommendations(client, session, career, [promote(7, "sql")])

    assert "7 → top 3" in text_of(page)
    assert "line-clamp-2" in page, "the evidence is clamped to two lines"
    assert "Ver más" in text_of(page)
    details = re.search(r'<details class="disclosure text-xs">.*?</details>', page, re.S).group(0)
    assert LONG in details and " open" not in details[: details.index(">")]


def test_the_proposal_link_is_the_third_button_of_the_actions_row(client, session, career):
    """Design v3 §5: Probar nuevo CV · Carta · Proponer resumen are one row of tertiary buttons."""
    application = stored(session, career, advice=[promote()])
    application.track_id = career.first_track.id
    session.commit()
    login(client, career.first.email)

    raw = client.get(f"/applications/{application.id}").text
    toolbar = re.search(r'<aside\b[^>]*aria-label="Acciones".*?</aside>', raw, re.S).group(0)

    link = f'href="/applications/{application.id}/summary"'
    assert link in toolbar and "btn btn-tertiary" in toolbar
    assert link not in section(raw, "recommendations"), "it left the collapsed row"


def test_the_layout_splits_after_three_items_and_keeps_group_order():
    items = [language(), add(), promote(7), promote(5), promote(4)]

    layout = advice_layout(items)

    assert [(g["key"], len(g["items"])) for g in layout["shown"]] == [("promote", 3)]
    assert [(g["key"], len(g["items"])) for g in layout["rest"]] == [("add", 1), ("language", 1)]
    assert layout["total"] == 5


def test_the_skills_card_is_never_split_across_the_fold():
    items = [promote(7), add(), skill("a"), skill("b"), skill("c"), language()]

    layout = advice_layout(items)

    shown = {g["key"]: len(g["items"]) for g in layout["shown"]}
    assert shown == {"promote": 1, "add": 1, "skills": 3}, "one item of budget keeps the card"
    assert [(g["key"], len(g["items"])) for g in layout["rest"]] == [("language", 1)]

    # With the budget spent before the skills, the whole card waits behind the toggle.
    late = advice_layout([promote(7), promote(6), promote(5), skill("a"), skill("b")])
    assert [g["key"] for g in late["shown"]] == ["promote"]
    assert [(g["key"], len(g["items"])) for g in late["rest"]] == [("skills", 2)]


def test_an_unknown_kind_is_shown_not_dropped():
    layout = advice_layout([{"kind": "future_rule", "values": {}}])

    assert [g["key"] for g in layout["shown"]] == ["other"]


def test_each_item_keeps_its_place_in_the_stored_list():
    """§12.7: the highlight map keys an advice item by its position in the stored advice, so
    the page needs that position to name the bullet an item lights — grouping keeps it."""
    layout = advice_layout([language(), add(), promote(7)])

    assert [item["index"] for group in layout["shown"] for item in group["items"]] == [2, 1, 0]
