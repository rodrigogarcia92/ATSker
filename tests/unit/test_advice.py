"""F7.2's six edit rules: each one fires on its condition and nowhere else.

The reports here are hand-built dictionaries rather than analyses: the rules read the
report, and a fixture that says exactly what this rule needs is what makes "fires when
it holds and not otherwise" testable. No provider is stubbed because none is called —
the one test that checks that patches `_post` to raise.
"""

from decimal import Decimal

from src.advice import MAX_ITEMS, edit_advice
from src.bullets import create_bullet
from src.extract import client as extract_client
from src.models import Skill
from src.tracks import set_track_bullets
from src.web.alerts import advice_line
from tests.conftest import login
from tests.unit.test_analysis import w3_report


def grade(
    requirement: str,
    *,
    level: int,
    must_have: bool = True,
    bullet_id=None,
    text: str | None = None,
) -> dict:
    return {
        "requirement": requirement,
        "must_have": must_have,
        "level": level,
        "basis": "direct" if level else "none",
        "source": "bullet" if bullet_id else None,
        "bullet_id": str(bullet_id) if bullet_id else None,
        "bullet_text": text,
        "transfer_reason": None,
        "clamped": False,
        "downgraded": False,
        "inferred": False,
        "fallback": False,
    }


def clause(term: str, *, matched: bool = False) -> dict:
    return {
        "term": term,
        "matched": matched,
        "unit_kind": "bullet" if matched else None,
        "bullet_id": None,
        "unit_text": None,
    }


def failing_query(label: str, term: str, text: str) -> dict:
    return {
        "label": label,
        "passed": False,
        "query_text": text,
        "failing_term": term,
        "failing_kind": "missing",
        "clauses": [clause(term)],
    }


def language_alert() -> dict:
    return {
        "kind": "language_mismatch",
        "posting": "en",
        "other": "es",
        "fallback_bullets": 2,
        "bullets": 5,
        "fallback_titles": 1,
        "titles": 2,
    }


def report(*, grades=(), jd=None, title=1.0, queries=(), alerts=()) -> dict:
    return {
        "jd": {
            "title": "Analista de datos",
            "language": "es",
            "must_have": [],
            "nice_to_have": [],
            **(jd or {}),
        },
        "grades": list(grades),
        "score": {"sub_scores": {"title": {"value": title}}},
        "recall": {"queries": list(queries)},
        "gaps": {"alerts": list(alerts)},
    }


def bullet(session, career, text: str, chips: list[str] | None = None):
    created = create_bullet(
        career.first_profile.id,
        session,
        role_id=career.first_role.id,
        text_es=text,
        text_en=None,
        chips=chips or [],
    )
    session.commit()
    return created


def kinds(items) -> list[str]:
    return [item.kind for item in items]


def test_rule_one_promotes_a_demonstrated_bullet_below_the_first_three(session, career):
    profile_id = career.first_profile.id
    fillers = [bullet(session, career, f"Viñeta de relleno {index}") for index in range(3)]
    strong = bullet(session, career, "Modelé el riesgo con SQL")
    set_track_bullets(
        profile_id,
        session,
        career.first_track.id,
        [*(entry.id for entry in fillers), strong.id],
    )
    session.commit()

    items = edit_advice(
        profile_id,
        session,
        report=report(
            grades=[grade("python", level=3, bullet_id=strong.id, text="Modelé el riesgo con SQL")]
        ),
        track=career.first_track,
    )

    assert kinds(items) == ["promote_bullet"]
    assert items[0].bullet_id == str(strong.id)
    assert items[0].values == {"position": 4, "requirement": "python"}


def test_rule_one_does_not_fire_when_nothing_weaker_is_above_it(session, career):
    profile_id = career.first_profile.id
    fillers = [bullet(session, career, f"Viñeta de relleno {index}") for index in range(3)]
    strong = bullet(session, career, "Modelé el riesgo con SQL")
    set_track_bullets(
        profile_id,
        session,
        career.first_track.id,
        [*(entry.id for entry in fillers), strong.id],
    )
    session.commit()
    # Every line above the strong one is itself cited: there is nothing to reorder.
    grades = [
        grade("python", level=3, bullet_id=strong.id, text="Modelé el riesgo con SQL"),
        *[grade("sql", level=1, must_have=False, bullet_id=entry.id) for entry in fillers],
    ]

    items = edit_advice(profile_id, session, report=report(grades=grades), track=career.first_track)

    assert kinds(items) == []

    # And a cited bullet already in the first three is not moved either.
    set_track_bullets(
        profile_id, session, career.first_track.id, [strong.id, *(e.id for e in fillers)]
    )
    session.commit()

    assert (
        edit_advice(profile_id, session, report=report(grades=grades), track=career.first_track)
        == []
    )


def test_rule_two_adds_a_bullet_that_would_raise_a_must_have(session, career):
    profile_id = career.first_profile.id
    outside = bullet(
        session, career, "Puse modelos de machine learning en producción", ["machine learning"]
    )

    items = edit_advice(
        profile_id,
        session,
        report=report(
            grades=[grade("machine learning", level=0)],
            jd={"must_have": ["machine learning"]},
        ),
        track=career.first_track,
    )

    assert kinds(items) == ["add_bullet"]
    assert items[0].bullet_id == str(outside.id)
    assert items[0].canonical == "machine learning"
    assert items[0].evidence == "Puse modelos de machine learning en producción"


def test_rule_two_does_not_fire_for_a_requirement_already_met(session, career):
    profile_id = career.first_profile.id
    bullet(session, career, "Puse modelos de machine learning en producción", ["machine learning"])
    # Graded 2: the must-have is demonstrated, so there is nothing to raise.
    items = edit_advice(
        profile_id,
        session,
        report=report(
            grades=[grade("machine learning", level=2, bullet_id=career.first_bullet.id)],
            jd={"must_have": ["machine learning"]},
        ),
        track=career.first_track,
    )

    assert kinds(items) == []


def test_rule_three_is_retired_and_a_new_analysis_emits_no_surface_skill(session, career):
    """F7.5: the Keywords card says which skill to surface; this rule no longer does."""
    profile_id = career.first_profile.id
    career.first_profile.skills = ["python"]
    session.flush()
    only_in_the_track = report(jd={"must_have": ["python"]})

    items = edit_advice(profile_id, session, report=only_in_the_track, track=career.first_track)

    assert items == [], "pool, evidenced, asked for, absent from the track's list: no item now"


def test_rule_four_names_a_failing_query_the_user_can_evidence(session, career):
    profile_id = career.first_profile.id
    outside = bullet(session, career, "Puse modelos en producción", ["machine learning"])
    queries = [
        failing_query("strict", "machine learning", '"machine learning" AND python'),
        {
            "label": "broad",
            "passed": True,
            "query_text": "analista",
            "clauses": [clause("analista", matched=True)],
        },
    ]

    items = edit_advice(
        profile_id,
        session,
        report=report(queries=queries),
        track=career.first_track,
    )

    assert kinds(items) == ["fix_query"]
    assert items[0].query_label == "strict"
    assert items[0].bullet_id == str(outside.id)
    assert items[0].values["query"] == '"machine learning" AND python'


def test_rule_four_leaves_a_term_the_user_cannot_evidence_alone(session, career):
    """The closure check: no bullet, no advice — it stays in the gaps (F6)."""
    profile_id = career.first_profile.id
    career.first_profile.skills = ["machine learning"]
    session.flush()
    queries = [failing_query("strict", "machine learning", '"machine learning"')]

    assert (
        edit_advice(profile_id, session, report=report(queries=queries), track=career.first_track)
        == []
    )


def test_rule_five_asks_for_the_title_in_the_postings_language(session, career):
    profile_id = career.first_profile.id
    items = edit_advice(
        profile_id,
        session,
        report=report(jd={"title": "analista de datos", "language": "en"}, title=0.2),
        track=career.first_track,
    )

    assert kinds(items) == ["title_language"]
    assert items[0].role_id == str(career.first_role.id)
    assert items[0].values == {
        "title": "analista de datos",
        "role": "Analista de datos",
        "language": "es",
    }


def test_rule_five_falls_back_to_a_headline(session, career):
    profile_id = career.first_profile.id
    items = edit_advice(
        profile_id,
        session,
        report=report(jd={"title": "Data Scientist", "language": "en"}, title=0.2),
        track=career.first_track,
    )

    assert kinds(items) == ["title_headline"]

    # Above the floor there is nothing to say.
    assert (
        edit_advice(
            profile_id,
            session,
            report=report(jd={"title": "Data Scientist", "language": "en"}, title=0.6),
            track=career.first_track,
        )
        == []
    )


def test_rule_five_only_asks_to_fill_an_empty_slot(session, career):
    """F7.2 rule 5: a title the role already has in the posting's language is no edit."""
    profile_id = career.first_profile.id
    career.first_role.title_es = "Analista de datos"
    session.flush()
    spanish_posting = {"title": "analista de datos", "language": "en"}

    assert kinds(
        edit_advice(
            profile_id,
            session,
            report=report(jd=spanish_posting, title=0.2),
            track=career.first_track,
        )
    ) == ["title_language"], "the English slot is empty and the Spanish one is the whole title"

    career.first_role.title_en = "Analista de datos"
    session.flush()

    assert kinds(
        edit_advice(
            profile_id,
            session,
            report=report(jd=spanish_posting, title=0.2),
            track=career.first_track,
        )
    ) == ["title_headline"], "nothing left to fill"

    assert (
        edit_advice(
            profile_id,
            session,
            report=report(jd=spanish_posting, title=0.5),
            track=career.first_track,
        )
        == []
    ), "at the floor the title is no longer an edit"


def test_rule_five_needs_every_content_word_of_the_posting_title(session, career):
    """Half a title is not the translation rule 5 asks for; the headline still is."""
    profile_id = career.first_profile.id
    career.first_role.title_es = "Analista"
    session.flush()
    posting = {"title": "analista de datos", "language": "en"}

    assert kinds(
        edit_advice(
            profile_id,
            session,
            report=report(jd=posting, title=0.2),
            track=career.first_track,
        )
    ) == ["title_headline"], "'datos' is nowhere in the Spanish title"

    career.first_role.title_es = "Analista de datos"
    session.flush()

    assert kinds(
        edit_advice(
            profile_id,
            session,
            report=report(jd=posting, title=0.2),
            track=career.first_track,
        )
    ) == ["title_language"]


def test_rule_six_says_the_language_gap_as_an_edit(session, career):
    items = edit_advice(
        career.first_profile.id,
        session,
        report=report(alerts=[language_alert()]),
        track=career.first_track,
    )

    assert kinds(items) == ["language"]
    assert items[0].values == {
        "bullets": 2,
        "total_bullets": 5,
        "titles": 1,
        "language": "en",
    }
    assert "inglés" in advice_line(items[0].to_dict(), "es")
    assert "English" in advice_line(items[0].to_dict(), "en")


def test_the_rules_run_in_order_and_stop_at_eight(session, career):
    """The cap is a promise about noise: the most useful eight, in F7.2's order."""
    profile_id = career.first_profile.id
    session.add_all(
        [
            Skill(canonical="dax", aliases=["dax"]),
            Skill(canonical="excel", aliases=["excel"]),
            Skill(canonical="power bi", aliases=["power bi"]),
            Skill(canonical="sql", aliases=["sql"]),
        ]
    )
    session.flush()
    fillers = [bullet(session, career, f"Viñeta de relleno {index}") for index in range(3)]
    strong = bullet(session, career, "Modelé el riesgo con SQL")
    for canonical in ("dax", "excel", "power bi", "sql"):
        bullet(session, career, f"Trabajé con {canonical}", [canonical])
    bullet(session, career, "Puse modelos en producción", ["machine learning"])
    set_track_bullets(
        profile_id,
        session,
        career.first_track.id,
        [*(entry.id for entry in fillers), strong.id],
    )
    career.first_profile.skills = ["python"]
    session.flush()
    grades = [
        grade("python", level=3, bullet_id=strong.id, text="Modelé el riesgo con SQL"),
        *[grade(canonical, level=0) for canonical in ("dax", "excel", "power bi", "sql")],
    ]

    items = edit_advice(
        profile_id,
        session,
        report=report(
            grades=grades,
            jd={
                "must_have": ["python", "dax", "excel", "power bi", "sql"],
                "nice_to_have": ["machine learning"],
                "title": "analista de datos",
                "language": "en",
            },
            title=0.2,
            queries=[failing_query("strict", "machine learning", '"machine learning"')],
            alerts=[language_alert()],
        ),
        track=career.first_track,
    )

    assert len(items) == MAX_ITEMS
    assert kinds(items) == [
        "promote_bullet",
        "add_bullet",  # dax
        "add_bullet",  # excel
        "add_bullet",  # power bi
        "add_bullet",  # sql
        "fix_query",  # machine learning
        "title_language",
        "language",
    ], "in F7.2's order; with rule 3 retired the language item now fits under the cap"


def test_the_rules_make_no_provider_call(session, career, monkeypatch, test_settings):
    """F7.2 is arithmetic: the seam every provider call goes through stays untouched."""
    def forbidden(payload: dict, api_key: str) -> dict:
        raise AssertionError("edit advice may not call a provider")

    monkeypatch.setattr(extract_client, "_post", forbidden)

    assert (
        edit_advice(
            career.first_profile.id,
            session,
            report=report(grades=[grade("python", level=3)]),
            track=career.first_track,
        )
        == []
    )


def test_advice_without_a_track_is_only_the_document_rules(session, career):
    """Rules 1 to 4 are about a selected track; there is none, so they advise nothing."""
    profile_id = career.first_profile.id
    career.first_profile.skills = ["python"]
    session.flush()
    items = edit_advice(
        profile_id,
        session,
        report=report(
            grades=[grade("python", level=3, bullet_id=career.first_bullet.id)],
            jd={"must_have": ["python"], "title": "Data Scientist", "language": "en"},
            title=0.2,
            alerts=[language_alert()],
        ),
        track=None,
    )

    assert kinds(items) == ["title_headline", "language"]


def test_an_unknown_requirement_canonical_is_never_advised(session, career):
    """A posting term the vocabulary does not know has no canonical to close over."""
    profile_id = career.first_profile.id
    bullet(session, career, "Coordiné el programa", ["python"])

    items = edit_advice(
        profile_id,
        session,
        report=report(
            grades=[grade("oratoria", level=0)],
            jd={"must_have": ["oratoria"]},
        ),
        track=career.first_track,
    )

    assert kinds(items) == []


def test_a_stored_report_without_advice_renders_as_before(client, session, career):
    """The report page reads `report.advice`; an old row has none (F7.2)."""
    from src.applications import create_application

    login(client, career.first.email)

    stored = create_application(
        career.first_profile.id,
        session,
        company="Banco Demo",
        title="Analista de datos",
        jd_text="Analista de datos con Python",
        jd_hash="sha256:old",
        report=w3_report(),
        weights_version="w4",
        prompt_versions={},
        token_cost_usd=Decimal("0"),
    )
    session.commit()

    page = client.get(f"/applications/{stored.id}")

    assert page.status_code == 200
    # K4: a track-less analysis keeps the section for its disabled "Proponer resumen", and
    # shows no advice item, no ranking and no error.
    recommendations = page.text[page.text.index('id="recommendations"') :]
    recommendations = recommendations[: recommendations.index("</section>")]
    assert "Recomendaciones" in recommendations
    assert "disabled" in recommendations and "advice-evidence" not in recommendations
    assert 'id="track-ranking"' not in recommendations
