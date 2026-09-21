"""Boolean query derivation (PRD F5.2): the searches a recruiter would run.

Derivation is the model's judgement about the posting's own words — which terms are
the ones nobody would drop, and which belong to the narrowest query. Evaluation is
deterministic and lives in `src.search.boolean`, which never calls a provider: the
line between the two is the same line the rest of the project draws (design
principle 1).

Cached by content hash like every other extraction: a repeat analysis of the same
posting makes no network call.
"""

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.db import short_session
from src.extract.client import CallOptions, Completion, complete_json
from src.extract.prompts import BOOLEAN_RECALL
from src.models import Skill

PURPOSE = "boolean_queries"

# One retry for a schema violation, like the other extraction calls.
RETRIES = 1

# F5.2 asks for three to five queries. Fewer is accepted and shown as it came — the
# panel is the truth — and more is truncated, because they arrive broadest first.
MAX_QUERIES = 5


class BooleanExpr(BaseModel):
    """One node of a query tree: an operator over terms or further nodes.

    The PRD's own shape: `{"and": ["data analyst", {"or": ["sql", "python"]}]}`.
    """

    model_config = ConfigDict(populate_by_name=True)

    all_of: list["BooleanTerm"] | None = Field(default=None, alias="and")
    any_of: list["BooleanTerm"] | None = Field(default=None, alias="or")
    none_of: list["BooleanTerm"] | None = Field(default=None, alias="not")


# A term, or a node. The alias has to come after the class: pydantic resolves it on
# `model_rebuild()` below.
BooleanTerm = str | BooleanExpr  # noqa: UP007 - a recursive alias, resolved at runtime

BooleanExpr.model_rebuild()


class BooleanQuery(BaseModel):
    label: str = Field(default="", description="the query's own name: broad, core, strict")
    expr: BooleanTerm = Field(description="a term, or a tree of and/or/not over terms")


class BooleanQuerySet(BaseModel):
    queries: list[BooleanQuery] = Field(default_factory=list)


def _sanitised(proposal: BooleanQuerySet) -> BooleanQuerySet:
    """Drop queries with nothing in them, and keep the broadest five (F5.2)."""
    usable = [query for query in proposal.queries if _has_terms(query.expr)]
    return BooleanQuerySet(queries=usable[:MAX_QUERIES])


def _has_terms(expr: BooleanTerm) -> bool:
    if isinstance(expr, str):
        return bool(expr.strip())
    children = [*(expr.all_of or []), *(expr.any_of or []), *(expr.none_of or [])]
    return any(_has_terms(child) for child in children)


def vocabulary_names(session: Session) -> list[str]:
    """Canonical skill names, the block the prompt prefers terms from."""
    with short_session(session) as reader:
        return list(reader.scalars(select(Skill.canonical).order_by(Skill.canonical)))


def derive_boolean_queries(
    session: Session,
    jd_text: str,
    *,
    model: str | None = None,
    options: CallOptions | None = None,
) -> tuple[BooleanQuerySet, Completion]:
    """Three to five queries, broadest to narrowest, and the call that produced them."""
    if not jd_text.strip():
        raise ValueError("a boolean derivation needs a posting")

    # The prompt's vocabulary read is the function's own; the caller's transaction is
    # never opened or ended here (client.complete_json refuses to run inside one).
    vocabulary = ", ".join(vocabulary_names(session))
    completion = complete_json(
        session,
        purpose=PURPOSE,
        prompt_version=BOOLEAN_RECALL.version,
        system=BOOLEAN_RECALL.render_system(vocabulary=vocabulary or "(empty)"),
        user=BOOLEAN_RECALL.render(posting=jd_text),
        schema=BooleanQuerySet,
        model=model,
        retries=RETRIES,
        options=options,
    )
    return _sanitised(BooleanQuerySet.model_validate(completion.data)), completion