"""§8 Terminology: the track is a "línea de carrera" in the Spanish interface (queue K2).

English keeps "Track"; code, keys and placeholders are untouched. "Puesto" stays wherever it
means a job — the posting's, or one of the user's own roles.
"""

import re

from src.i18n import t
from src.i18n.strings import STRINGS


def test_no_spanish_value_still_says_puesto_objetivo():
    offenders = [
        key for key, value in STRINGS.items() if re.search(r"puestos? objetivo", value["es"], re.I)
    ]

    assert offenders == []


def test_no_spanish_value_calls_a_track_a_pista():
    offenders = [
        key for key, value in STRINGS.items() if re.search(r"\bpistas?\b", value["es"], re.I)
    ]

    assert offenders == []


def test_the_nav_label_is_lineas_de_carrera_in_spanish_and_tracks_in_english():
    assert t("nav.tracks", "es") == "Líneas de carrera"
    assert t("nav.tracks", "en") == "Tracks"


def test_the_agreement_around_the_track_is_feminine():
    assert t("attempt.incorporate.este", "es") == "Esta línea"
    assert t("attempt.incorporate.nuevo", "es") == "Nueva línea"
    assert t("letters.assign", "es") == "Asignar a una línea"
    assert t("analyze.recommend", "es") == "Recomendar línea de carrera"
    assert t("letters.unlinked_title", "es") == "Sin línea"
    assert t("report.recommendation.track", "es") == "Línea"
    assert t("attempt.delta", "es", delta="+3") == "+3 vs. análisis de la línea"


def test_the_job_in_the_posting_keeps_puesto_and_its_placeholder():
    assert t("letters.placeholder.role", "es") == "[PUESTO] / [ROLE]"
    assert t("analyze.jd", "es") == "Descripción del puesto"
    assert t("letters.default.closing", "es").endswith("sobre el puesto de [PUESTO].")


def test_the_users_own_roles_keep_puesto():
    assert t("roles.new", "es") == "Nuevo puesto"
    assert t("dashboard.roles", "es") == "Puestos"
