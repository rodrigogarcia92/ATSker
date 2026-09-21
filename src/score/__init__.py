"""Scoring: sub-scores and aggregation.

May not make network calls (PRD 5.1) — a test reads this package's imports and
fails if one appears. Weights live in a named, versioned config so that every
report can record the version and a config hash.
"""

from src.score.aggregate import SUB_SCORES, ScoreReport, SubScore, aggregate
from src.score.weights import W1, W2, Weights, WeightSet, WeightsV2

__all__ = [
    "SUB_SCORES",
    "ScoreReport",
    "SubScore",
    "W1",
    "W2",
    "WeightSet",
    "Weights",
    "WeightsV2",
    "aggregate",
]
