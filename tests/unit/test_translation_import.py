"""Importing the other-language CV as a translation (PRD F4.2, 2026-09-27).

The provider is stubbed at `client._post`: the pairing is the model's judgement, and
everything around it — which roles are the same job, one-to-one pairs, which column
may be filled — is code that has to hold without one.
"""

import json
from datetime import date

import pytest

from src.bullets import create_bullet, get_bullet, list_bullets
from src.extract import client as extract_client
from src.extract.client import ProviderUnavailable
from src.extract.grading import CitationViolation
from src.ingest.draft import DraftBullet, DraftRole, ResumeDraft
from src.ingest.merge import MergePlan
from src.ingest.translation import (
    TranslationSelections,
    apply_translation,
    matched_roles,
    plan_translation,
    translation_available,
)
from src.roles import create_role, list_roles
from src.summaries import list_summaries
from src.tracks import list_tracks, set_track_bullets
from tests.conftest import login
from tests.unit.test_ingest_merge import make_resume, select_all


class Pairing:
    """A scripted pairing answer, one per call, priced like a real call."""

    def __init__(self, answers: list[list[dict]]):
        self.answers = answers or [[]]
        self.calls: list[dict] = []

    def __call__(self, payload: dict, api_key: str) -> dict:
        self.calls.append(payload)
        name = payload["response_format"]["json_schema"]["name"]
        assert name == "BulletPairing", "the translation path may not call anything else"
        answer = self.answers[min(len(self.calls) - 1, len(self.answers) - 1)]
        return {
            "choices": [{"message": {"content": json.dumps({"pairs": answer})}}],
            "usage": {"prompt_tokens": 120, "completion_tokens": 12, "cost": "0.0002"},
        }

    @property
    def turns(self) -> int:
        return len(self.calls)


@pytest.fixture
def pairing(monkeypatch, test_settings):
    def install(answers: list[list[dict]]) -> Pairing:
        stub = Pairing(answers)
        monkeypatch.setattr(extract_client, "_post", stub)
        return stub

    return install


def second_role(session, career):
    """A second role of the profile, selected by the same track, with real dates."""
    role = create_role(
        career.first_profile.id,
        session,
        employer="ONG Andina",
        title_es="Coordinadora",
        title_en=None,
        start_date=date(2019, 3, 1),
        end_date=date(2021, 6, 30),
    )
    bullet = create_bullet(
        career.first_profile.id,
        session,
        role_id=role.id,
        text_es="Coordiné el aula virtual",
        text_en=None,
        chips=[],
    )
    set_track_bullets(
        career.first_profile.id,
        session,
        career.first_track.id,
        [career.first_bullet.id, bullet.id],
    )
    session.commit()
    return role, bullet


def acme_draft_role() -> DraftRole:
    return DraftRole(
        employer="Acme",
        title="Data Analyst",
        start_date="2020-02",
        bullets=[
            DraftBullet(text="Cut reporting time by 30% with Python", chips=["python"]),
            DraftBullet(text="Ran the monthly KPI pack"),
        ],
    )


def andina_draft_role() -> DraftRole:
    return DraftRole(
        employer="ONG Andina",
        title="Coordinator",
        start_date="2020-02",
        bullets=[DraftBullet(text="Ran the virtual classroom")],
    )


def initech_draft_role() -> DraftRole:
    return DraftRole(
        employer="Initech",
        title="Consultant",
        bullets=[DraftBullet(text="Advised on dashboards")],
    )


def english_draft(*roles: DraftRole) -> ResumeDraft:
    """One of F4.2's translated CVs: English, with the roles a test asks for."""
    return ResumeDraft(
        language="en",
        headline="Data analyst",
        summary="Five years turning reporting into automation.",
        skills=["python"],
        roles=list(roles) or [acme_draft_role()],
    )


def test_two_roles_match_and_their_bullets_pair(session, career, pairing):
    """Two matched roles, one call each, and the unpaired CV line left as a candidate."""
    profile_id = career.first_profile.id
    role, _ = second_role(session, career)
    stub = pairing([[{"existing": 0, "draft": 0}]])

    plan = plan_translation(
        profile_id,
        session,
        track=career.first_track,
        draft=english_draft(acme_draft_role(), andina_draft_role()),
    )

    assert [match.role.id for match in plan.matches] == [career.first_role.id, role.id]
    assert [pair.draft_text for pair in plan.pairs] == [
        "Cut reporting time by 30% with Python",
        "Ran the virtual classroom",
    ]
    assert stub.turns == 2, "one call per matched role"
    assert [tuple(bullet.text for bullet in match.unpaired) for match in plan.matches] == [
        ("Ran the monthly KPI pack",),
        (),
    ], "an unpaired CV line is an ordinary candidate, listed under its role"


def test_a_pair_fills_the_empty_column_and_leaves_the_other_one_alone(session, career, pairing):
    """The pair writes the CV's language where the column is empty, and nowhere else."""
    profile_id = career.first_profile.id
    # The role's English title already exists, so nothing but the bullet is filled and
    # the count is the bullet's alone.
    career.first_role.title_en = "Data Analyst"
    session.flush()
    pairing([[{"existing": 0, "draft": 0}]])
    draft = english_draft()
    resume = make_resume(session, profile_id, draft, "cv-en", career.first_track.id)

    plan = plan_translation(profile_id, session, track=career.first_track, draft=draft)
    result = apply_translation(
        profile_id,
        session,
        resume_id=resume.id,
        plan=plan,
        selections=TranslationSelections(pairs=frozenset({0})),
    )

    assert result is not None
    bullet = get_bullet(profile_id, session, career.first_bullet.id)
    assert bullet is not None and bullet.text_en == "Cut reporting time by 30% with Python"
    assert bullet.text_es == "Reduje 30% el tiempo de reporte con Python", "untouched"
    assert (result.translations_filled, result.translations_kept) == (1, 0)


def test_a_filled_column_with_different_text_is_kept(session, career, pairing):
    """A confirmed pair over existing text is counted kept, and the text stays."""
    profile_id = career.first_profile.id
    career.first_role.title_en = "Data Analyst"
    career.first_bullet.text_en = "Something else entirely in English"
    session.flush()
    pairing([[{"existing": 0, "draft": 0}]])
    draft = english_draft()
    resume = make_resume(session, profile_id, draft, "cv-en", career.first_track.id)

    plan = plan_translation(profile_id, session, track=career.first_track, draft=draft)
    result = apply_translation(
        profile_id,
        session,
        resume_id=resume.id,
        plan=plan,
        selections=TranslationSelections(pairs=frozenset({0})),
    )

    assert result is not None
    bullet = get_bullet(profile_id, session, career.first_bullet.id)
    assert bullet is not None and bullet.text_en == "Something else entirely in English"
    assert (result.translations_filled, result.translations_kept) == (0, 1)


def test_an_unconfirmed_pair_writes_nothing(session, career, pairing):
    profile_id = career.first_profile.id
    career.first_role.title_en = "Data Analyst"
    session.flush()
    pairing([[{"existing": 0, "draft": 0}]])
    draft = english_draft()
    resume = make_resume(session, profile_id, draft, "cv-en", career.first_track.id)
    plan = plan_translation(profile_id, session, track=career.first_track, draft=draft)

    result = apply_translation(
        profile_id,
        session,
        resume_id=resume.id,
        plan=plan,
        selections=TranslationSelections(),
    )

    assert result is not None
    assert (result.translations_filled, result.translations_kept) == (0, 0)
    untouched = get_bullet(profile_id, session, career.first_bullet.id)
    assert untouched is not None and untouched.text_en is None


def test_an_unmatched_role_and_its_bullets_are_written_by_the_ordinary_merge(
    session, career, pairing
):
    """The reduced draft goes through F2.5's own write path, not a second one."""
    profile_id = career.first_profile.id
    pairing([[{"existing": 0, "draft": 0}]])
    draft = english_draft(acme_draft_role(), initech_draft_role())
    resume = make_resume(session, profile_id, draft, "cv-en", career.first_track.id)
    plan = plan_translation(profile_id, session, track=career.first_track, draft=draft)

    result = apply_translation(
        profile_id,
        session,
        resume_id=resume.id,
        plan=plan,
        selections=TranslationSelections(merge=select_all(plan.plan)),
    )

    assert result is not None and result.roles_created == 1
    initech = [
        bullet
        for bullet in list_bullets(profile_id, session, active_only=False)
        if bullet.role_id
        in {
            role.id
            for role in list_roles(profile_id, session, active_only=False)
            if role.employer == "Initech"
        }
    ]
    assert [bullet.text_en for bullet in initech] == ["Advised on dashboards"]
    assert initech[0].source_resume_id == resume.id, "provenance is F2.5's, unchanged"


def test_the_role_and_track_other_language_slots_are_filled(session, career, pairing):
    """The matched role's title and the track's headline fill their empty slots."""
    profile_id = career.first_profile.id
    pairing([[{"existing": 0, "draft": 0}]])
    draft = english_draft()
    resume = make_resume(session, profile_id, draft, "cv-en", career.first_track.id)
    plan = plan_translation(profile_id, session, track=career.first_track, draft=draft)

    result = apply_translation(
        profile_id,
        session,
        resume_id=resume.id,
        plan=plan,
        selections=TranslationSelections(pairs=frozenset({0})),
    )

    assert result is not None
    session.expire_all()
    role = career.first_role
    assert (role.title_es, role.title_en) == ("Analista de datos", "Data Analyst")
    assert role.title == "Analista de datos", "`title` still mirrors the primary language"
    assert result.track_headline_filled
    assert career.first_track.headline_en == "Data analyst"
    # The summary joins the pool in the CV's language and fills the track's empty
    # slot — F2.7's own write path, which the reduced draft goes through unchanged.
    assert result.track_summary_filled
    pooled = [entry for entry in list_summaries(profile_id, session)]
    assert [entry.lang for entry in pooled] == ["es", "en"]
    assert pooled[-1].text == "Five years turning reporting into automation."
    assert career.first_track.summary_en_id == pooled[-1].id


def test_a_bad_pairing_index_fails_after_one_retry(session, career, pairing):
    """An index the model was not given is a citation violation, twice, then loud."""
    stub = pairing([[{"existing": 9, "draft": 0}]])

    with pytest.raises(CitationViolation):
        plan_translation(
            career.first_profile.id,
            session,
            track=career.first_track,
            draft=english_draft(),
        )

    assert stub.turns == 2, "one retry, then the answer is refused"


def test_a_repeated_index_is_a_citation_violation(session, career, pairing):
    pairing([[{"existing": 0, "draft": 0}, {"existing": 0, "draft": 1}]])

    with pytest.raises(CitationViolation):
        plan_translation(
            career.first_profile.id,
            session,
            track=career.first_track,
            draft=english_draft(),
        )


def test_a_bullet_with_nothing_to_pair_with_is_not_sent_to_the_model(session, career, pairing):
    """An empty side cannot pair: the call is not made, and nothing is spent."""
    stub = pairing([[]])
    plan = plan_translation(
        career.first_profile.id,
        session,
        track=career.first_track,
        draft=ResumeDraft(language="en", roles=[]),
    )

    assert stub.turns == 0
    assert plan.pairs == ()
    assert isinstance(plan.plan, MergePlan)


def test_the_option_is_not_offered_when_the_languages_are_equal(session, career, pairing):
    profile_id = career.first_profile.id
    spanish = ResumeDraft(
        language="es",
        roles=[
            DraftRole(
                employer="Acme",
                title="Analista de datos",
                bullets=[DraftBullet(text="Otra redacción del mismo logro")],
            )
        ],
    )

    assert not translation_available(
        profile_id, session, track=career.first_track, draft=spanish
    )
    assert translation_available(
        profile_id, session, track=career.first_track, draft=english_draft()
    )
    assert not translation_available(profile_id, session, track=None, draft=english_draft())


def test_role_matching_reads_employer_and_overlapping_dates(session, career):
    """F4.2's deterministic half: folded employer, a missing end is today, ±3 months."""
    profile_id = career.first_profile.id
    role, _ = second_role(session, career)

    def matches(start: str | None, end: str | None) -> bool:
        draft = ResumeDraft(
            language="en",
            roles=[
                DraftRole(
                    employer="ONG  Andina",
                    title="Coordinator",
                    start_date=start,
                    end_date=end,
                    bullets=[DraftBullet(text="Anything")],
                )
            ],
        )
        return any(
            found.id == role.id
            for found, _ in matched_roles(
                profile_id, session, track=career.first_track, draft=draft
            )
        )

    assert matches("2019-04", "2021-05"), "inside the span"
    assert matches("2021-08", None), "a missing end is today, and the tolerance is ±3 months"
    assert not matches("2022-06", "2023-01"), "a year later is a different job"

    elsewhere = ResumeDraft(
        language="en",
        roles=[
            DraftRole(employer="Globex", title="Coordinator", bullets=[DraftBullet(text="x")])
        ],
    )
    assert matched_roles(profile_id, session, track=career.first_track, draft=elsewhere) == ()


def test_an_employer_differing_only_in_punctuation_pairs_with_the_stored_role(session, career):
    """E3: the employer compares on `match_key`, as the import and the attempt do."""
    role, _ = second_role(session, career)
    draft = ResumeDraft(
        language="en",
        roles=[
            DraftRole(
                employer="ONG. Andina",
                title="Coordinator",
                start_date="2019-04",
                bullets=[DraftBullet(text="Anything")],
            )
        ],
    )

    matches = matched_roles(career.first_profile.id, session, track=career.first_track, draft=draft)

    assert [found.id for found, _ in matches] == [role.id]


def test_each_existing_role_is_matched_once(session, career):
    """Two spellings of one job pair the first and leave the second to F2.5."""
    profile_id = career.first_profile.id
    _, _ = second_role(session, career)
    draft = ResumeDraft(
        language="en",
        roles=[
            DraftRole(
                employer="ONG Andina",
                title="Coordinator",
                start_date="2019-04",
                bullets=[DraftBullet(text="One")],
            ),
            DraftRole(
                employer="ONG Andina",
                title="Programme coordinator",
                start_date="2019-05",
                bullets=[DraftBullet(text="Two")],
            ),
        ],
    )

    matches = matched_roles(profile_id, session, track=career.first_track, draft=draft)

    assert [match.title for _, match in matches] == ["Coordinator"]


def test_the_route_offers_the_option_and_applies_the_pairs(client, session, career, pairing):
    """The whole screen: the offer on the merge page, the pairs, and the result."""
    profile_id = career.first_profile.id
    draft = english_draft()
    resume = make_resume(session, profile_id, draft, "cv-en", career.first_track.id)
    stub = pairing([[{"existing": 0, "draft": 0}]])
    login(client, career.first.email)

    merge_page = client.post(
        f"/import/{resume.id}/review",
        data={
            "language": "en",
            "headline": draft.headline or "",
            "summary": draft.summary or "",
            "skills": "python",
            "role_count": "1",
            "role_0_employer": "Acme",
            "role_0_title": "Data Analyst",
            "role_0_start": "2020-02",
            "role_0_end": "",
            "bullet_count_0": "1",
            "bullet_0_0_text": "Cut reporting time by 30% with Python",
            "bullet_0_0_chips": "python",
            "credential_count": "0",
        },
    ).text

    assert "Importar como traducción" in merge_page, "the offer is on the merge screen"

    pairs_page = client.post(f"/import/{resume.id}/translate").text
    assert "Cut reporting time by 30% with Python" in pairs_page
    assert 'name="pair_0"' in pairs_page
    assert stub.turns == 1

    applied = client.post(f"/import/{resume.id}/translate/apply", data={"pair_0": "on"})

    assert applied.status_code == 200
    assert "Traducciones escritas" in applied.text
    # The route wrote through its own session; this one re-reads the row.
    session.expire_all()
    filled = get_bullet(profile_id, session, career.first_bullet.id)
    assert filled is not None and filled.text_en == "Cut reporting time by 30% with Python"
    assert filled.text_es == "Reduje 30% el tiempo de reporte con Python"
    assert stub.turns == 1, "the apply re-derives the same answer from the cache: no second call"


def test_a_failed_pairing_says_so_and_leaves_the_merge_available(client, session, career, pairing):
    profile_id = career.first_profile.id
    draft = english_draft()
    resume = make_resume(session, profile_id, draft, "cv-en", career.first_track.id)
    pairing([[{"existing": 9, "draft": 0}]])
    login(client, career.first.email)

    page = client.post(f"/import/{resume.id}/translate").text

    assert "no devolvió una respuesta utilizable" in page
    assert "Importar la selección" in page, "the ordinary merge is still there"


class Down:
    """The provider is unreachable: `_post` raises the way a transport failure does."""

    def __call__(self, payload: dict, api_key: str) -> dict:
        raise ProviderUnavailable("connection refused")


def test_a_failed_pairing_on_apply_says_so_and_writes_nothing(
    client, session, career, monkeypatch
):
    """F4.2: the apply route fails like the first one — a screen, not a 500, no write."""
    profile_id = career.first_profile.id
    draft = english_draft()
    resume = make_resume(session, profile_id, draft, "cv-en", career.first_track.id)
    login(client, career.first.email)
    before = _row_counts(session, profile_id)
    monkeypatch.setattr(extract_client, "_post", Down())

    applied = client.post(f"/import/{resume.id}/translate/apply", data={"pair_0": "on"})

    assert applied.status_code == 200
    assert "no devolvió una respuesta utilizable" in applied.text
    assert "Importar la selección" in applied.text, "the ordinary merge is still there"
    session.expire_all()
    assert _row_counts(session, profile_id) == before, "no role, bullet or track changed"
    session.refresh(resume)
    assert resume.merged_at is None, "the upload is still pending review"


def _row_counts(session, profile_id) -> tuple[int, int, int]:
    """What a failed pairing must not touch: the roles, bullets and tracks it reads."""
    return (
        len(list_roles(profile_id, session)),
        len(list_bullets(profile_id, session)),
        len(list_tracks(profile_id, session)),
    )


def test_an_import_in_the_same_language_is_not_a_translation(client, session, career, pairing):
    profile_id = career.first_profile.id
    draft = ResumeDraft(
        language="es",
        roles=[
            DraftRole(
                employer="Acme",
                title="Analista de datos",
                bullets=[DraftBullet(text="Otra redacción")],
            )
        ],
    )
    resume = make_resume(session, profile_id, draft, "cv-es", career.first_track.id)
    login(client, career.first.email)

    merge_page = client.post(
        f"/import/{resume.id}/review",
        data={
            "language": "es",
            "role_count": "1",
            "role_0_employer": "Acme",
            "role_0_title": "Analista de datos",
            "role_0_start": "2020-02",
            "role_0_end": "",
            "bullet_count_0": "1",
            "bullet_0_0_text": "Otra redacción",
            "bullet_0_0_chips": "",
            "credential_count": "0",
        },
    ).text

    assert "Importar como traducción" not in merge_page
    assert client.post(f"/import/{resume.id}/translate").status_code == 404
