"""Boolean query derivation (PRD F5.2): the searches a recruiter would run.

Derivation is the model's judgement about the posting's own words — which terms are
the ones nobody would drop, and which belong to the narrowest query. Evaluation is
deterministic and lives in `src.search.boolean`, which never calls a provider: the
line between the two is the same line the rest of the project draws (design
principle 1).

The shape the model is asked for is flat — an AND of OR-groups, plus exclusions — and
the tree `src.search.boolean` walks is built from it here (A.8.1). A recursive schema
made strict mode (A.7) demand three keys at every node, so the default model nested
until it ran out of tokens and answered with JSON deeper than Python's parser allows
(2026-09-25); the two levels below cover the queries F5.2 describes.

Cached by content hash like every other extraction: a repeat analysis of the same
posting makes no network call.
"""

from dataclasses import dataclass

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.db import short_session
from src.extract.client import CallOptions, Completion, complete_json
from src.extract.prompts import BOOLEAN_RECALL_V2
from src.models import Skill

PURPOSE = "boolean_queries"

# One retry for a schema violation, like the other extraction calls.
RETRIES = 1

# F5.2 asks for three to five queries. Fewer is accepted and shown as it came — the
# panel is the truth — and more is truncated, because they arrive broadest first.
MAX_QUERIES = 5


@dataclass(frozen=True)
class BooleanExpr:
    """A node of the tree the evaluator walks: an operator over terms or nodes.

    `src.search.boolean` reads these three attributes off whatever it is handed, so
    the node type is the thinnest thing that satisfies it and the flat query builds
    one rather than asking the model to write a tree.
    """

    all_of: "tuple[BooleanTerm, ...]" = ()
    any_of: "tuple[BooleanTerm, ...]" = ()
    none_of: "tuple[BooleanTerm, ...]" = ()


# A term, or a node.
BooleanTerm = str | BooleanExpr


def _typed(term: str) -> str:
    """One term as a recruiter types it: a phrase goes in double quotes."""
    stripped = term.strip()
    return f'"{stripped}"' if " " in stripped else stripped


class BooleanQuery(BaseModel):
    """One recruiter's query, flat: an AND of OR-groups, plus exclusions.

    Every group in `all_of` must match, and a group matches when any of its terms
    does — a one-term group is a required term. `none_of` holds the terms that must
    not appear. Two levels and no more: see the module docstring.
    """

    label: str = Field(default="", description="broad, core or strict")
    all_of: list[list[str]] = Field(
        description="every group must match; a group matches when any of its terms does"
    )
    none_of: list[str] = Field(default_factory=list, description="terms that must not appear")

    @property
    def expr(self) -> BooleanExpr:
        """The flat query as the tree `src.search.boolean` evaluates (A.8.1)."""
        children: list[BooleanTerm] = [
            group[0] if len(group) == 1 else BooleanExpr(any_of=tuple(group))
            for group in self.all_of
        ]
        if self.none_of:
            children.append(BooleanExpr(none_of=tuple(self.none_of)))
        return BooleanExpr(all_of=tuple(children))

    @property
    def query_text(self) -> str:
        """The query as a recruiter types it into the search box (A.9.2).

        Flat queries are what the model answers with, but nobody runs `all_of` in an
        ATS: the user needs the line to paste. Every group is an AND, a group of more
        than one term is a parenthesised OR, exclusions follow as `AND NOT`.
        """
        parts = [
            _typed(group[0])
            if len(group) == 1
            else "(" + " OR ".join(_typed(term) for term in group) + ")"
            for group in self.all_of
            # A group with no terms is true of anything, so it is not part of the
            # search either.
            if any(term.strip() for term in group)
        ]
        parts += [f"NOT {_typed(term)}" for term in self.none_of if term.strip()]
        return " AND ".join(parts)


class BooleanQuerySet(BaseModel):
    queries: list[BooleanQuery] = Field(default_factory=list)


def _sanitised(proposal: BooleanQuerySet) -> BooleanQuerySet:
    """Drop queries with nothing in them, and keep the broadest five (F5.2)."""
    usable = [query for query in proposal.queries if _has_terms(query)]
    return BooleanQuerySet(queries=usable[:MAX_QUERIES])


def _has_terms(query: BooleanQuery) -> bool:
    """A query with no term at all constrains nothing, so it is not a query."""
    return any(term.strip() for group in query.all_of for term in group) or any(
        term.strip() for term in query.none_of
    )


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
        prompt_version=BOOLEAN_RECALL_V2.version,
        system=BOOLEAN_RECALL_V2.render_system(vocabulary=vocabulary or "(empty)"),
        user=BOOLEAN_RECALL_V2.render(posting=jd_text),
        schema=BooleanQuerySet,
        model=model,
        retries=RETRIES,
        options=options,
    )
    return _sanitised(BooleanQuerySet.model_validate(completion.data)), completion