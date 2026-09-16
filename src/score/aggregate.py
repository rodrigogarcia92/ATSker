"""Aggregation and the report shape (PRD F4.4).

A sub-score without its matched and missing terms is not a report ATSker shows, so
the two travel together in one object rather than as loose numbers.
"""

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field

from src.parse.gate import ParseReport, apply_gate
from src.score.weights import W1, Weights

SUB_SCORES = ("title", "evidence", "keyword", "semantic", "experience")


@dataclass(frozen=True)
class SubScore:
    name: str
    value: float
    matched: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    detail: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ScoreReport:
    weights_version: str
    weights_hash: str
    sub_scores: dict[str, SubScore]
    weighted: float
    uncapped: int
    capped: int
    cap: int | None
    cap_reason: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "weights_version": self.weights_version,
            "weights_hash": self.weights_hash,
            "weighted": round(self.weighted, 6),
            "uncapped": self.uncapped,
            "capped": self.capped,
            "cap": self.cap,
            "cap_reason": self.cap_reason,
            "sub_scores": {name: asdict(score) for name, score in self.sub_scores.items()},
        }


def aggregate(
    sub_scores: Mapping[str, SubScore],
    weights: Weights = W1,
    *,
    gate: ParseReport | None = None,
) -> ScoreReport:
    """Weighted sum → 0–100, then the gate cap. Missing sub-scores fail loudly.

    Every one of the five weights must be accounted for: quietly re-normalising
    over whichever sub-scores happen to exist would make two reports incomparable
    while looking identical.
    """
    absent = [name for name in SUB_SCORES if name not in sub_scores]
    if absent:
        raise ValueError(f"missing sub-scores: {', '.join(absent)}")

    weighted = sum(getattr(weights, name) * sub_scores[name].value for name in SUB_SCORES)
    uncapped = round(100 * weighted)
    cap = gate.cap if gate is not None else None
    capped = uncapped if gate is None else apply_gate(uncapped, gate)

    return ScoreReport(
        weights_version=weights.version,
        weights_hash=weights.config_hash(),
        sub_scores=dict(sub_scores),
        weighted=weighted,
        uncapped=uncapped,
        capped=capped,
        cap=cap,
        cap_reason=gate.cap_reason if gate is not None else None,
    )
