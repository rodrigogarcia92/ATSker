"""Versioned weight sets (PRD F4.4, F5.5).

A change to any weight means a new version string; reports record both the version
and a hash of the values, so two scores are never compared across configs without
that being visible. The previous version stays in the file as history: a stored
report is read from its own keys and its own version string, never re-aggregated.
"""

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, fields


def hash_values(values: Mapping[str, float]) -> str:
    """Stable hash of a weight set, nominal or effective, for the report to record."""
    payload = json.dumps(dict(values), sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class WeightSet:
    """Values, their hash, and the version string the report records beside them.

    The field names *are* the sub-score names — `aggregate` reads a weight by the
    name of the sub-score it multiplies — which is why a version that renames a
    component is a different set of fields, not the same one with new values.
    """

    version: str

    def as_dict(self) -> dict[str, float]:
        return {field.name: getattr(self, field.name) for field in fields(self)}

    def total(self) -> float:
        return sum(value for name, value in self.as_dict().items() if name != "version")

    def config_hash(self) -> str:
        """Hash of the weight values; the version is recorded beside it, not inside it."""
        values = {key: value for key, value in self.as_dict().items() if key != "version"}
        return hash_values(values)


@dataclass(frozen=True)
class Weights(WeightSet):
    """`w1`, kept as history (PRD F4.4 v1).

    Five components, including the semantic fit that v2 removed — so a report
    written under `w1` still has a name for every number it shows, and the weights
    that produced its total remain readable here.
    """

    title: float
    evidence: float
    keyword: float
    semantic: float
    experience: float


@dataclass(frozen=True)
class WeightsV2(WeightSet):
    """`w2` — PRD F5.5's four sub-scores.

    `evidence` becomes `skills` (same mechanism, the name a recruiter recognises),
    `keyword` becomes `keywords`, and semantic fit is gone: its 0.10 was
    redistributed, which is why the values are not `w1`'s proportions under new
    names.
    """

    skills: float
    experience: float
    title: float
    keywords: float


W1 = Weights(
    version="w1",
    title=0.20,
    evidence=0.35,
    keyword=0.15,
    semantic=0.10,
    experience=0.20,
)

W2 = WeightsV2(
    version="w2",
    skills=0.40,
    experience=0.25,
    title=0.20,
    keywords=0.15,
)