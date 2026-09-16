"""Versioned weight sets (PRD F4.4).

A change to any weight means a new version string; reports record both the version
and a hash of the values, so two scores are never compared across configs without
that being visible.
"""

import hashlib
import json
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Weights:
    version: str
    title: float
    evidence: float
    keyword: float
    semantic: float
    experience: float

    def as_dict(self) -> dict[str, float]:
        return asdict(self)

    def total(self) -> float:
        return self.title + self.evidence + self.keyword + self.semantic + self.experience

    def config_hash(self) -> str:
        """Hash of the weight values; the version is recorded beside it, not inside it."""
        values = {key: value for key, value in self.as_dict().items() if key != "version"}
        payload = json.dumps(values, sort_keys=True, separators=(",", ":"))
        return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


W1 = Weights(
    version="w1",
    title=0.20,
    evidence=0.35,
    keyword=0.15,
    semantic=0.10,
    experience=0.20,
)
