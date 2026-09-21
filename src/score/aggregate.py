"""Aggregation and the report shape (PRD F4.4, F5.5).

A sub-score without its matched and missing terms is not a report ATSker shows, so
the two travel together in one object rather than as loose numbers.

`w2` declares nothing unavailable — semantic fit was removed, not deferred — so a
current report renormalises nothing. The machinery stays anyway: a component that
cannot be computed is still only accepted when the caller declares it with a reason,
and the report then records the omission, the weights actually applied and their hash.
"""

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field

from src.parse.gate import ParseReport, apply_gate
from src.score.weights import W2, WeightSet, hash_values

# The order the report shows them in (PRD F5.5's table).
SUB_SCORES = ("skills", "experience", "title", "keywords")


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
    unavailable: dict[str, str] = field(default_factory=dict)
    effective_weights: dict[str, float] = field(default_factory=dict)
    effective_weights_hash: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "weights_version": self.weights_version,
            "weights_hash": self.weights_hash,
            "weighted": round(self.weighted, 6),
            "uncapped": self.uncapped,
            "capped": self.capped,
            "cap": self.cap,
            "cap_reason": self.cap_reason,
            "unavailable": dict(self.unavailable),
            "effective_weights": dict(self.effective_weights),
            "effective_weights_hash": self.effective_weights_hash,
            "sub_scores": {name: asdict(score) for name, score in self.sub_scores.items()},
        }


def aggregate(
    sub_scores: Mapping[str, SubScore],
    weights: WeightSet = W2,
    *,
    gate: ParseReport | None = None,
    unavailable: Mapping[str, str] | None = None,
) -> ScoreReport:
    """Weighted sum → 0–100, then the gate cap.

    Every weight must be accounted for. A sub-score that was not computed is only
    accepted when the caller declares it unavailable with a reason: the total is
    then renormalised over the rest, which keeps reports comparable while saying
    out loud what is missing. Quietly dropping a component would make two reports
    incomparable while looking identical, so that fails loudly instead — `w2`
    declares nothing, but the guard is what makes that a statement rather than a
    silence (PRD F5.5).
    """
    declared = dict(unavailable or {})
    unknown = sorted(set(declared) - set(SUB_SCORES))
    if unknown:
        raise ValueError(f"unknown sub-scores declared unavailable: {', '.join(unknown)}")
    contradicted = sorted(set(declared) & set(sub_scores))
    if contradicted:
        raise ValueError(
            f"declared unavailable but supplied anyway: {', '.join(contradicted)}"
        )
    undeclared = [name for name in SUB_SCORES if name not in sub_scores and name not in declared]
    if undeclared:
        raise ValueError(f"missing sub-scores: {', '.join(undeclared)}")

    available = [name for name in SUB_SCORES if name in sub_scores]
    if declared:
        nominal = sum(getattr(weights, name) for name in available)
        if nominal <= 0:
            raise ValueError("the available weights sum to zero")
        effective = {name: getattr(weights, name) / nominal for name in available}
    else:
        # No omission: the effective weights are the config, exactly as written.
        effective = {name: getattr(weights, name) for name in available}

    weighted = sum(effective[name] * sub_scores[name].value for name in available)
    uncapped = round(100 * weighted)
    cap = gate.cap if gate is not None else None
    capped = uncapped if gate is None else apply_gate(uncapped, gate)

    return ScoreReport(
        weights_version=weights.version,
        weights_hash=weights.config_hash(),
        # Stored in the order the report shows them, whatever order the caller built
        # its dict in: the report page renders its own keys, and a stored report's
        # order is part of what it says.
        sub_scores={name: sub_scores[name] for name in SUB_SCORES if name in sub_scores},
        weighted=weighted,
        uncapped=uncapped,
        capped=capped,
        cap=cap,
        cap_reason=gate.cap_reason if gate is not None else None,
        unavailable=declared,
        effective_weights=effective,
        effective_weights_hash=hash_values(effective),
    )
