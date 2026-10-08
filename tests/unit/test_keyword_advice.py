"""F7.5's Keywords card, deterministic part (queue K5).

Every candidate is a missing keyword of the report; the card says which basis the user's own
data gives it — `pool`, then `bullet`, then `equivalent`, strongest first, never twice — and
where it would go. A candidate with none of the three is counted in the footer and advised
nowhere. The reports are hand-built: the module reads a stored report and the user's rows,
makes no model call, and writes nothing.
"""

import copy
import re
from pathlib import Path

from src.advice import edit_advice
from src.extract import client as extract_client
from src.keyword_advice import SHOWN, keyword_advice
from src.models import Skill
from src.tracks import set_track_bullets
from tests.conftest import login
from tests.unit.test_advice import bullet
from tests.unit.test_advice import report as advice_report
from tests.unit.test_analysis import text_of
from tests.unit.test_report_layout import section, stored


def keyword_report(missing, *, must=(), nice=(), language="es") -> dict:
    """A report whose Keywords sub-score lists `missing` for a posting asking for the rest."""
    base = advice_report(jd={"must_have": list(must), "nice_to_have": list(nice)})
    base["jd"]["language"] = language
    base["score"]["sub_scores"]["keywords"] = {
        "name": "keywords",
        "value": 0.4,
        "matched": [],
        "missing": list(missing),
    }
    return base


def vocabulary(session, *rows) -> None:
    for canonical, family in rows:
        session.add(Skill(canonical=canonical, aliases=[canonical], family=family))
    session.commit()


def advise(session, career, report, **kwargs):
    return keyword_advice(
        career.first_profile.id, session, report=report, track=career.first_track, **kwargs
    )


def test_a_canonical_in_the_pool_is_lo_tienes_and_goes_to_habilidades(session, career):
    vocabulary(session, ("sql", None))
    career.first_profile.skills = ["sql"]
    session.commit()

    card = advise(session, career, keyword_report(["SQL"], must=["SQL"]))

    [item] = card.items
    assert (item.keyword, item.canonical, item.basis, item.where) == (
        "SQL",
        "sql",
        "pool",
        "skills",
    )
    assert item.priority == "must_have" and card.unsupported == []


def test_a_bullet_tagged_with_it_but_not_naming_it_is_named_with_its_text(session, career):
    named = bullet(session, career, "Puse modelos en producción", ["machine learning"])

    card = advise(session, career, keyword_report(["Machine Learning"], nice=["machine learning"]))

    [item] = card.items
    assert item.basis == "bullet" and item.where == "bullet"
    assert item.bullet_id == str(named.id) and item.bullet_text == "Puse modelos en producción"
    assert item.bullet_says is False, "it describes the keyword without naming it"
    assert item.priority == "nice_to_have"


def test_a_bullet_outside_the_track_that_already_says_it_is_added_not_reworded(session, career):
    outside = bullet(session, career, "Entrené modelos de machine learning", ["machine learning"])

    [item] = advise(session, career, keyword_report(["machine learning"])).items

    assert item.basis == "bullet" and item.bullet_id == str(outside.id)
    assert item.bullet_says is True, "the card says to include it, not to reword it"


def test_a_family_sibling_is_named_and_added_only_if_used(session, career):
    vocabulary(session, ("tableau", "bi"), ("power bi", "bi"))
    career.first_profile.skills = ["tableau"]
    session.commit()

    [item] = advise(session, career, keyword_report(["Power BI"], must=["Power BI"])).items

    assert (item.basis, item.sibling, item.where) == ("equivalent", "tableau", "skills")


def test_the_strongest_basis_wins_and_a_keyword_is_never_listed_twice(session, career):
    vocabulary(session, ("tableau", "bi"), ("power bi", "bi"))
    career.first_profile.skills = ["tableau", "power bi"]
    bullet(session, career, "Armé tableros", ["power bi"])
    session.commit()

    card = advise(session, career, keyword_report(["Power BI", "power bi"]))

    assert [(i.keyword, i.basis) for i in card.items] == [("Power BI", "pool")]


def test_a_keyword_nothing_backs_is_counted_not_advised(session, career):
    vocabulary(session, ("docker", None))

    card = advise(session, career, keyword_report(["Kubernetes", "docker"]))

    assert card.items == []
    assert [c.keyword for c in card.unsupported] == ["Kubernetes", "docker"]
    assert card.candidates == 2


def test_a_keyword_the_tracks_own_bullets_already_say_is_not_missing_any_more(session, career):
    vocabulary(session, ("sql", None))
    career.first_profile.skills = ["sql"]
    said = bullet(session, career, "Modelé el riesgo con SQL", ["sql"])
    set_track_bullets(career.first_profile.id, session, career.first_track.id, [said.id])
    session.commit()

    card = advise(session, career, keyword_report(["SQL"]))

    assert card.items == [] and card.unsupported == [], "stale: neither advised nor unsupported"


def test_order_is_must_have_then_nice_then_the_rest_and_within_that_by_basis(session, career):
    vocabulary(session, ("sql", None), ("tableau", "bi"), ("power bi", "bi"), ("docker", None))
    career.first_profile.skills = ["sql", "tableau"]
    bullet(session, career, "Puse modelos en producción", ["machine learning"])
    session.commit()
    missing = ["Power BI", "machine learning", "SQL", "extra pool", "Docker"]
    report = keyword_report(missing, must=["Power BI", "SQL"], nice=["machine learning", "Docker"])

    card = advise(session, career, report)

    assert [(i.keyword, i.priority, i.basis) for i in card.items] == [
        ("SQL", "must_have", "pool"),
        ("Power BI", "must_have", "equivalent"),
        ("machine learning", "nice_to_have", "bullet"),
    ]
    assert [c.keyword for c in card.unsupported] == ["Docker", "extra pool"]


def test_the_eight_shown_and_the_rest_behind_ver_todas(session, career):
    names = [f"skill{index}" for index in range(10)]
    vocabulary(session, *[(name, None) for name in names])
    career.first_profile.skills = names
    session.commit()

    card = advise(session, career, keyword_report(names))

    assert len(card.items) == 10 and len(card.shown) == SHOWN == 8 and len(card.rest) == 2


def test_a_report_without_a_keywords_sub_score_has_no_card(session, career):
    assert advise(session, career, advice_report()) is None


def test_the_module_reads_and_writes_nothing_and_never_reaches_a_provider():
    source = (Path(__file__).resolve().parents[2] / "src" / "keyword_advice.py").read_text(
        encoding="utf-8"
    )

    for banned in ("httpx", "src.extract", "session.add", "session.commit", "session.flush"):
        assert banned not in source, banned


def test_rule_three_and_the_skill_branch_of_rule_four_no_longer_emit_surface_skill(session, career):
    career.first_profile.skills = ["python", "machine learning"]
    bullet(session, career, "Puse python en producción", ["python"])
    report = advice_report(jd={"must_have": ["python"]})

    items = edit_advice(career.first_profile.id, session, report=report, track=career.first_track)

    assert [item.kind for item in items] == []


# --- the page ----------------------------------------------------------------------


def page_report(session, career, missing, *, must=(), nice=(), **changes):
    application = stored(session, career)
    report = copy.deepcopy(application.report)
    report["jd"] = {
        "title": "Analista",
        "language": "es",
        "must_have": list(must),
        "nice_to_have": list(nice),
        "raw_keywords": [],
    }
    report["score"]["sub_scores"] = {
        "keywords": {"name": "keywords", "value": 0.4, "matched": [], "missing": list(missing)}
    }
    report.update(changes)
    application.report = report
    application.track_id = career.first_track.id
    session.commit()
    return application


def card_of(page: str) -> str:
    match = re.search(r'<div id="keywords-card".*?</ul>\s*(?:</div>)?', page, re.S)
    assert match, "the page has the Keywords card"
    return match.group(0)


def test_the_card_sits_between_the_ranking_and_the_other_advice(client, session, career):
    vocabulary(session, ("sql", None))
    career.first_profile.skills = ["sql"]
    application = page_report(
        session,
        career,
        ["SQL"],
        must=["SQL"],
        recommendation={
            "candidates": [{"name": "Riesgo", "chosen": True, "job_match": 60, "sub_scores": {}}],
            "margin": None,
        },
        advice=[{"kind": "title_headline", "values": {}, "evidence": ""}],
    )
    login(client, career.first.email)

    page = section(client.get(f"/applications/{application.id}").text, "recommendations")

    assert page.index('id="track-ranking"') < page.index('id="keywords-card"')
    assert page.index('id="keywords-card"') < page.index("Búsquedas y título")


def test_every_item_shows_its_keyword_basis_place_and_a_copy_control(client, session, career):
    vocabulary(session, ("sql", None), ("tableau", "bi"), ("power bi", "bi"))
    career.first_profile.skills = ["sql", "tableau"]
    bullet(session, career, "Puse modelos en producción", ["machine learning"])
    application = page_report(
        session, career, ["SQL", "Power BI", "machine learning", "Kubernetes"], must=["SQL"]
    )
    login(client, career.first.email)

    page = client.get(f"/applications/{application.id}").text
    card = text_of(section(page, "recommendations"))

    assert "calculado con tu material actual" in card
    assert "SQL Lo tienes" in card and "ya figura en tu material; añádela a tu lista" in card
    assert "Power BI Equivalente" in card
    assert "tienes tableau; añádela solo si de verdad la has usado" in card
    assert "machine learning Un bullet tuyo lo respalda" in card
    assert "tu bullet «Puse modelos en producción» lo describe sin nombrarlo" in card
    assert "1 palabra clave no tiene respaldo en tu material: está en tus brechas." in card
    assert page.count('data-copy="SQL"') == 1 and 'aria-label="Copiar «SQL»"' in page
    assert "Habilidades" in card


def test_two_unsupported_keywords_use_the_plural_footer(client, session, career):
    application = page_report(session, career, ["Kubernetes", "Terraform"])
    login(client, career.first.email)

    card = text_of(section(client.get(f"/applications/{application.id}").text, "recommendations"))

    assert "2 palabras clave no tienen respaldo en tu material: están en tus brechas." in card


def test_ver_todas_reveals_the_items_past_the_eighth(client, session, career):
    names = [f"skill{index}" for index in range(10)]
    vocabulary(session, *[(name, None) for name in names])
    career.first_profile.skills = names
    application = page_report(session, career, names)
    login(client, career.first.email)

    page = client.get(f"/applications/{application.id}").text
    card = section(page, "recommendations")

    head, _, rest = card.partition('<details class="disclosure mt-2')
    assert head.count("data-copy=") == 8 and rest.count("data-copy=") == 2
    assert "Ver todas (10)" in text_of(rest)


def test_a_report_without_keywords_shows_no_card_and_no_error(client, session, career):
    application = stored(session, career)
    login(client, career.first.email)

    response = client.get(f"/applications/{application.id}")

    assert response.status_code == 200 and 'id="keywords-card"' not in response.text


def test_a_report_stored_with_surface_skill_items_still_renders_them(client, session, career):
    skill = {
        "kind": "surface_skill",
        "canonical": "python",
        "evidence": "python",
        "values": {"canonical": "python"},
    }
    application = page_report(session, career, [], advice=[skill])
    login(client, career.first.email)

    page = text_of(client.get(f"/applications/{application.id}").text)

    assert "Añade a las habilidades de la línea: la oferta las pide" in page
    assert "python" in page


def test_the_page_is_a_get_with_no_provider_call_and_changes_nothing(
    client, session, career, monkeypatch
):
    vocabulary(session, ("sql", None))
    career.first_profile.skills = ["sql"]
    application = page_report(session, career, ["SQL"], must=["SQL"])
    calls = []
    monkeypatch.setattr(extract_client, "_post", lambda *args: calls.append(args))
    before = (
        copy.deepcopy(application.report),
        application.weights_version,
        list(career.first_profile.skills),
    )
    login(client, career.first.email)

    assert client.get(f"/applications/{application.id}").status_code == 200

    session.expire_all()
    from src.applications import get_application

    after = get_application(career.first_profile.id, session, str(application.id))
    assert calls == []
    assert (after.report, after.weights_version, list(career.first_profile.skills)) == before
    assert after.report["score"]["capped"] == before[0]["score"]["capped"]


def test_another_profiles_application_is_a_404(client, session, career):
    application = page_report(session, career, ["SQL"])
    login(client, career.second.email)

    assert client.get(f"/applications/{application.id}").status_code == 404


def test_an_attempts_report_words_the_card_for_the_document(client, session, career):
    from src.models import ApplicationAttempt

    vocabulary(session, ("sql", None))
    career.first_profile.skills = ["sql"]
    application = page_report(session, career, ["SQL"], must=["SQL"])
    attempt = ApplicationAttempt(
        application_id=application.id,
        profile_id=career.first_profile.id,
        attempt_no=1,
        status="done",
        file_format="docx",
        report=application.report,
        weights_version="w4",
        prompt_versions={},
        token_cost_usd=0,
    )
    session.add(attempt)
    session.commit()
    login(client, career.first.email)

    page = client.get(f"/applications/{application.id}/attempts/{attempt.id}/report").text
    card = text_of(card_of(page))

    assert "faltan en tu documento" in card
    assert "añádela a tu sección Habilidades" in card
    assert "esta línea" not in card
