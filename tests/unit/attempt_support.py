"""Shared setup for the F10 attempt tests (Run B).

One provider answers both sides — the analysis that produces the application, and the
attempt that scores the file — dispatching on the schema name the client asks for.
`analyzed_application` stores a real analysis, so an attempt reuses its posting, its
queries and its grading cache exactly as the product does.
"""

import json

from src.analysis import analyze
from src.applications import create_application

POSTING = """
Analista de datos — Banco Demo (híbrido, Lima)
Buscamos un analista con 3 años de experiencia en Python y machine learning.
Imprescindible: título universitario.
"""

JD = json.dumps(
    {
        "language": "es",
        "title": "Analista de datos",
        "seniority": "mid",
        "years_required": 3,
        "must_have": ["python"],
        "nice_to_have": ["machine learning"],
        "raw_keywords": ["reportes"],
        "hard_requirements": ["título universitario"],
        "location_policy": "hybrid_lima",
        "responsibilities": [],
    }
)

QUERIES = json.dumps(
    {
        "queries": [
            {"label": "broad", "all_of": [["analista de datos"], ["python"]], "none_of": []},
            {
                "label": "strict",
                "all_of": [["python"], ["machine learning"]],
                "none_of": ["excel"],
            },
        ]
    }
)

GAPS = json.dumps(
    {
        "gaps": [
            {
                "requirement": "machine learning",
                "blocking": False,
                "interpretation": "Machine learning está mencionado sin una historia.",
            }
        ],
        "warning": {"text": "", "handling": ""},
        "not_found": "",
    }
)


def grading_payload(bullet_id: str | None = None) -> str:
    """A direct grade for `python` on the master bullet, one gap for the rest.

    Without a `bullet_id` every requirement is level 0: a test whose file replaces the
    bullet set has no master id the stub could legally cite.
    """
    first = (
        {
            "index": 0,
            "level": 2,
            "basis": "direct",
            "source": "bullet",
            "evidence_id": bullet_id,
            "transfer_reason": None,
        }
        if bullet_id
        else {"index": 0, "level": 0, "basis": "none", "source": None}
    )
    return json.dumps(
        {
            "grades": [first, {"index": 1, "level": 0, "basis": "none", "source": None}],
            "task_grades": [],
            "note": "una nota",
        }
    )


def resume_payload(
    *bullets: str, language: str = "es", skills: tuple[str, ...] = ()
) -> str:
    """A résumé extraction whose single role mirrors the master row, bullet by bullet."""
    return json.dumps(
        {
            "language": language,
            "headline": "Analista de datos",
            "summary": "",
            "roles": [
                {
                    "employer": "Acme",
                    "title": "Analista de datos",
                    "start_date": None,
                    "end_date": None,
                    "bullets": list(bullets),
                }
            ],
            "credentials": [],
            "skills": list(skills),
        }
    )


class AttemptProvider:
    """Answers every schema the analysis and the attempt ask for. Counts its calls."""

    def __init__(self, *, bullet_id: str, resume: str | None = None):
        self.calls: list[dict] = []
        self.answers = {
            "JDProposal": JD,
            "BooleanQuerySet": QUERIES,
            "EvidenceGrading": grading_payload(bullet_id),
            "GapInterpretation": GAPS,
            "ResumeExtraction": resume or resume_payload("placeholder"),
        }

    def calls_for(self, schema: str) -> list[dict]:
        return [
            call
            for call in self.calls
            if call["response_format"]["json_schema"]["name"] == schema
        ]

    def __call__(self, payload: dict, api_key: str) -> dict:
        self.calls.append(payload)
        name = payload["response_format"]["json_schema"]["name"]
        return {
            "choices": [{"message": {"content": self.answers[name]}}],
            "usage": {"prompt_tokens": 2200, "completion_tokens": 140, "cost": "0.000123"},
        }


def analyzed_application(session, career, provider, *, track=None):
    """Store a real analysis, so the attempt reuses its posting and its cache."""
    chosen = track if track is not None else career.first_track
    analysis = analyze(
        career.first_profile.id, session, jd_text=POSTING, track=chosen
    )
    application = create_application(
        career.first_profile.id,
        session,
        jd_text=POSTING,
        jd_hash=analysis.jd_hash,
        report=analysis.report,
        weights_version=analysis.weights_version,
        prompt_versions=analysis.prompt_versions,
        token_cost_usd=analysis.cost_usd,
        track_id=chosen.id,
    )
    session.commit()
    return application, analysis
