"""The model-selection experiment (PRD §9, §7).

Three candidates are run over the labelled golden pairs and compared on rank
agreement, judge stability, latency and cost. Two things about this module are
deliberate and easy to get wrong:

**The cache is bypassed.** `llm_calls` doubles as a content-hash cache, so a naive
re-run of the same pair would return the stored answer and report perfect judge
stability — that measures the cache, not the judge. Every call here carries
`CallOptions(bypass_cache=True)` and the tests fail if a stability repeat ever reads
from the cache.

**Agreement is Kendall's tau-b first.** Twelve pairs spread over three buckets are
tie-dominated, and Spearman handles ties poorly; tau-b is the primary measure and
Spearman is reported beside it because the PRD names ρ. Both carry a bootstrap
confidence interval: at n=12 a point estimate alone is not evidence.

Stability is measured on the judge alone: the posting's extraction is held fixed
and the grading call is repeated, because the PRD's stability question is about the
ordinal the judge returns.
"""

import json
import math
import random
import time
import tomllib
import uuid
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Literal

import httpx
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.analysis import UNAVAILABLE_UNTIL_M9, Analysis, analyze
from src.extract.client import CallOptions, complete_json
from src.extract.grading import grade_evidence
from src.models import Base, Bullet, Profile, Role, User
from src.normalize.metrics import extract_metrics
from src.score.aggregate import SubScore, aggregate
from src.score.evidence import Level, evidence_coverage
from src.score.weights import W1
from src.vocabulary import resolve_bullet_terms, seed_vocabulary

# Deterministic ids, so a rerun of the same fixture produces the same citation
# targets and two reports can be compared without normalising uuids.
FIXTURE_NAMESPACE = uuid.UUID("6d2f4f6a-6a5c-4a1f-9f0d-2b7c3f6a1d10")

BUCKET_ORDINAL = {"stretch": 0, "plausible": 1, "strong": 2}

DEFAULT_SEED = 20260917
DEFAULT_REPEATS = 3

# PRD §12: the acceptance gate, and the operator's hard ceiling at list prices.
RHO_GATE = 0.70
COST_CEILING_USD = Decimal("0.02")
# PRD §9: above this share of changed ordinals, self-consistency is triggered.
INSTABILITY_FLAG = 0.10


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


class BulletFixture(BaseModel):
    key: str = ""
    text_es: str | None = None
    text_en: str | None = None
    skills: list[str] = Field(default_factory=list)


class RoleFixture(BaseModel):
    employer: str
    title: str
    start_date: str | None = None
    end_date: str | None = None
    bullets: list[BulletFixture] = Field(default_factory=list)


class ResumeFixture(BaseModel):
    display_name: str
    headline: str | None = None
    roles: list[RoleFixture] = Field(default_factory=list)


class JDFixture(BaseModel):
    title: str = ""
    text: str


class GoldenPair(BaseModel):
    """One labelled (résumé snapshot, posting) pair.

    The résumé side is a snapshot rather than a database reference: a labelled pair
    has to mean the same thing in a year, and a reference would silently change
    meaning the first time a bullet is edited. `resume_sha256` records where the
    snapshot came from without making the pair depend on it.
    """

    id: str
    language: Literal["es", "en"]
    bucket: Literal["strong", "plausible", "stretch"]
    profile: Literal["primary", "second"]
    reason: str
    resume_sha256: str | None = None
    resume: ResumeFixture
    jd: JDFixture

    @property
    def rank(self) -> int:
        return BUCKET_ORDINAL[self.bucket]


def load_pair(path: Path) -> GoldenPair:
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    try:
        return GoldenPair.model_validate(raw)
    except ValidationError as exc:
        raise ValueError(f"{path.name}: {exc}") from exc


def load_pairs(directory: Path) -> list[GoldenPair]:
    paths = sorted(directory.glob("*.toml"))
    if not paths:
        raise ValueError(f"no golden pairs (*.toml) in {directory}")
    pairs = [load_pair(path) for path in paths]
    ids = [pair.id for pair in pairs]
    duplicates = {value for value in ids if ids.count(value) > 1}
    if duplicates:
        raise ValueError(f"duplicate pair ids: {', '.join(sorted(duplicates))}")
    return pairs


def vocabulary_entries() -> list[dict]:
    """The production vocabulary: decision 5 keeps it in the seed file, not in code."""
    path = Path(__file__).parent / "normalize" / "skills_seed.json"
    return json.loads(path.read_text(encoding="utf-8"))


def composition_notes(pairs: Sequence[GoldenPair]) -> list[str]:
    """PRD §9's composition rules, reported rather than enforced.

    A thin set still produces a table — it just produces a table that cannot carry
    the acceptance argument, and saying so is cheaper than discovering it later.
    """
    notes: list[str] = []
    spanish = sum(1 for pair in pairs if pair.language == "es")
    second = sum(1 for pair in pairs if pair.profile == "second")
    buckets = Counter(pair.bucket for pair in pairs)
    if len(pairs) != 12:
        notes.append(f"{len(pairs)} pairs; the PRD's set is 12")
    if spanish < 3:
        notes.append(f"{spanish} Spanish pairs; at least 3 are required")
    if second < 2:
        notes.append(f"{second} pairs from the second profile; at least 2 are required")
    empty = [bucket for bucket in BUCKET_ORDINAL if not buckets[bucket]]
    if empty:
        notes.append(f"no pairs in bucket(s): {', '.join(empty)}")
    return notes


def build_session(pair: GoldenPair) -> tuple[Session, uuid.UUID]:
    """An in-memory profile holding exactly the pair's résumé snapshot."""
    engine = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    seed_vocabulary(session, vocabulary_entries())

    # No password: the experiment never logs in, and hashing would only slow it.
    user = User(email=f"{pair.id}@golden.invalid", password_hash="not-a-login", ui_lang="es")
    session.add(user)
    session.flush()
    profile = Profile(
        user_id=user.id, display_name=pair.resume.display_name, headline=pair.resume.headline
    )
    session.add(profile)
    session.flush()

    for role_index, role in enumerate(pair.resume.roles):
        db_role = Role(
            id=uuid.uuid5(FIXTURE_NAMESPACE, f"{pair.id}:role:{role_index}"),
            profile_id=profile.id,
            employer=role.employer,
            title=role.title,
            start_date=date_or_none(role.start_date),
            end_date=date_or_none(role.end_date),
            active=True,
        )
        session.add(db_role)
        session.flush()
        for bullet_index, bullet in enumerate(role.bullets):
            canonical, _unknown = resolve_bullet_terms(session, bullet.skills)
            text = bullet.text_es or bullet.text_en or ""
            session.add(
                Bullet(
                    id=uuid.uuid5(
                        FIXTURE_NAMESPACE, f"{pair.id}:bullet:{role_index}:{bullet_index}"
                    ),
                    profile_id=profile.id,
                    role_id=db_role.id,
                    text_es=bullet.text_es,
                    text_en=bullet.text_en,
                    skills=canonical,
                    metrics=extract_metrics(text),
                    active=True,
                )
            )
    session.commit()
    return session, profile.id


def date_or_none(value: str | None) -> date | None:
    if not value or not value.strip():
        return None
    return date.fromisoformat(value.strip())


# --------------------------------------------------------------------------- #
# Candidates and prices
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Candidate:
    model: str
    label: str
    reasoning_effort: str | None = None
    reference: bool = False
    note: str = ""


@dataclass(frozen=True)
class ModelPrice:
    """List prices in USD per million tokens, plus what the provider shows today.

    Prices are data, dated and sourced, because a budget verdict computed from a
    stale number is worse than no verdict: the script prints the date and the
    source beside the table, and `verify_prices` checks the API at run time.
    """

    input_list: float
    output_list: float
    current_input: float
    current_output: float
    note: str = ""


# Source: https://openrouter.ai/api/v1/models, read 2026-09-17. The "current"
# columns are what the price list showed that day; "list" is the rate to judge the
# budget by.
PRICES_READ_ON = "2026-09-17"
MODELS_URL = "https://openrouter.ai/api/v1/models"

PRICES: dict[str, ModelPrice] = {
    "deepseek/deepseek-v4.1-flash": ModelPrice(
        input_list=0.15,
        output_list=0.60,
        current_input=0.15,
        current_output=0.60,
        note=(
            "weekday time-of-day overrides double the rate inside the peak window "
            "(see /models); the table uses the base rate, the measured cost shows "
            "what was actually billed"
        ),
    ),
    "google/gemini-3.8-flash": ModelPrice(
        input_list=0.75,
        output_list=7.50,
        current_input=0.75,
        current_output=3.75,
        note=(
            "list output is 2x the rate the API showed on 2026-09-17, per the "
            "operator's note that a 50% output discount is active; reasoning is "
            "mandatory on this model and bills at the output rate"
        ),
    ),
    "z-ai/glm-5.3": ModelPrice(
        input_list=1.40,
        output_list=4.40,
        current_input=1.40,
        current_output=4.40,
        note=(
            "reasoning bills as output; the operator's figure of $2.97/M for "
            "reasoning tokens does not match the $4.40/M the API showed on "
            "2026-09-17 - the measured cost settles it"
        ),
    ),
}

CANDIDATES: tuple[Candidate, ...] = (
    Candidate("deepseek/deepseek-v4.1-flash", "deepseek-v4.1-flash", note="cheap baseline"),
    Candidate("google/gemini-3.8-flash", "gemini-3.8-flash", note="mid tier"),
    Candidate(
        "z-ai/glm-5.3",
        "glm-5.3 (low)",
        reasoning_effort="low",
        note="reasoning cannot be disabled; pinned to low effort",
    ),
)

GLM_REFERENCE = Candidate(
    "z-ai/glm-5.3",
    "glm-5.3 (max, reference)",
    reasoning_effort="max",
    reference=True,
    note="quality ceiling, not a candidate",
)


class ProbeAnswer(BaseModel):
    ok: bool = True


def _fetch_models() -> dict:
    response = httpx.get(MODELS_URL, timeout=30.0)
    response.raise_for_status()
    return response.json()


def verify_prices(
    candidates: Sequence[Candidate], *, fetch: Callable[[], dict] | None = None
) -> list[str]:
    """Compare the recorded prices with what the provider shows right now.

    Best effort on purpose: no network is a warning, not a failed run. What it
    catches is the case that would quietly invalidate the table — a promotional
    rate ending between the run and the decision, or a provider dropping the
    parameters the stability measurement depends on.
    """
    try:
        payload = (fetch or _fetch_models)()
    except Exception as exc:  # noqa: BLE001 - a failed check must not fail the run
        return [f"price check skipped: {type(exc).__name__}: {exc}"]

    index = {entry.get("id"): entry for entry in payload.get("data", [])}
    notes: list[str] = []
    for candidate in candidates:
        entry = index.get(candidate.model)
        price = PRICES.get(candidate.model)
        if entry is None or price is None:
            notes.append(f"{candidate.model}: not found in the provider's model list")
            continue
        pricing = entry.get("pricing") or {}
        current_input = float(pricing.get("prompt") or 0) * 1_000_000
        current_output = float(pricing.get("completion") or 0) * 1_000_000
        if (
            round(current_input, 6) != round(price.current_input, 6)
            or round(current_output, 6) != round(price.current_output, 6)
        ):
            notes.append(
                f"{candidate.model}: price list changed since {PRICES_READ_ON} — recorded "
                f"${price.current_input:g}/${price.current_output:g} per M, provider shows "
                f"${current_input:g}/${current_output:g}"
            )
        supported = set(entry.get("supported_parameters") or [])
        missing = {"seed", "temperature"} - supported
        if missing:
            notes.append(
                f"{candidate.model}: provider no longer advertises {', '.join(sorted(missing))}"
            )
    return notes


@dataclass(frozen=True)
class ProbeOutcome:
    model: str
    ok: bool
    seed_accepted: bool | None
    fingerprint: str | None
    error: str = ""

    @property
    def seed_note(self) -> str:
        if not self.ok:
            return "unavailable"
        if self.seed_accepted:
            return "seed accepted" + (" (fingerprint echoed)" if self.fingerprint else "")
        return "seed rejected, retried without it"


def probe_candidate(candidate: Candidate, *, seed: int) -> ProbeOutcome:
    """One throwaway call to learn what this provider accepts before spending more.

    OpenRouter's model list advertises `seed`, `temperature` and `reasoning` for all
    three candidates, but an advertisement is not a guarantee; the probe sends a
    seeded request first and retries once without the seed rather than failing the
    whole run.
    """
    session, _ = build_session(
        GoldenPair(
            id=f"probe-{candidate.label}",
            language="en",
            bucket="plausible",
            profile="primary",
            reason="probe",
            resume=ResumeFixture(display_name="Probe"),
            jd=JDFixture(text="probe"),
        )
    )
    error = ""
    for options in (
        CallOptions(bypass_cache=True, seed=seed, reasoning_effort=candidate.reasoning_effort),
        CallOptions(bypass_cache=True, reasoning_effort=candidate.reasoning_effort),
    ):
        try:
            completion = complete_json(
                session,
                purpose="model_probe",
                prompt_version="probe_v1",
                system='You answer probes. Reply with JSON: {"ok": true}',
                user="probe",
                schema=ProbeAnswer,
                model=candidate.model,
                options=options,
            )
        except Exception as exc:  # noqa: BLE001 - the probe reports any failure as data
            error = f"{type(exc).__name__}: {exc}"
            continue
        return ProbeOutcome(
            model=candidate.model,
            ok=True,
            seed_accepted=options.seed is not None,
            fingerprint=completion.fingerprint,
        )
    return ProbeOutcome(
        model=candidate.model, ok=False, seed_accepted=None, fingerprint=None, error=error
    )


# --------------------------------------------------------------------------- #
# Statistics
# --------------------------------------------------------------------------- #


def kendall_tau_b(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    """Tie-corrected rank correlation. None when every pair is a tie.

    Twelve pairs over three buckets are full of ties, which is exactly the case
    Kendall's tau-b corrects and Spearman's rho does not.
    """
    concordant = discordant = tied_x = tied_y = 0
    for i in range(len(xs)):
        for j in range(i + 1, len(xs)):
            dx = xs[j] - xs[i]
            dy = ys[j] - ys[i]
            if dx == 0 and dy == 0:
                continue
            if dx == 0:
                tied_x += 1
            elif dy == 0:
                tied_y += 1
            elif dx * dy > 0:
                concordant += 1
            else:
                discordant += 1
    denominator = math.sqrt(
        (concordant + discordant + tied_x) * (concordant + discordant + tied_y)
    )
    if denominator == 0:
        return None
    return (concordant - discordant) / denominator


def average_ranks(values: Sequence[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda index: values[index])
    ranks = [0.0] * len(values)
    start = 0
    while start < len(order):
        end = start
        while end + 1 < len(order) and values[order[end + 1]] == values[order[start]]:
            end += 1
        average = (start + end) / 2 + 1
        for position in range(start, end + 1):
            ranks[order[position]] = average
        start = end + 1
    return ranks


def spearman_rho(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    """Reported because the PRD names it; the primary measure is tau-b."""
    return _pearson(average_ranks(xs), average_ranks(ys))


def _pearson(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    n = len(xs)
    if n < 2:
        return None
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    covariance = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    variance_x = sum((x - mean_x) ** 2 for x in xs)
    variance_y = sum((y - mean_y) ** 2 for y in ys)
    if variance_x == 0 or variance_y == 0:
        return None
    return covariance / math.sqrt(variance_x * variance_y)


def _quantile(sorted_values: Sequence[float], probability: float) -> float:
    if not sorted_values:
        raise ValueError("no values")
    position = probability * (len(sorted_values) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return sorted_values[lower]
    weight = position - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


def bootstrap_ci(
    measure: Callable[[Sequence[float], Sequence[float]], float | None],
    xs: Sequence[float],
    ys: Sequence[float],
    *,
    resamples: int = 2000,
    level: float = 0.95,
    seed: int = DEFAULT_SEED,
) -> tuple[float | None, float | None]:
    """Percentile bootstrap: no distributional assumption, deterministic under seed.

    At n=12 the interval is wide, which is the point — a point estimate reported
    without one is not evidence.
    """
    rng = random.Random(seed)
    n = len(xs)
    values: list[float] = []
    for _ in range(resamples):
        index = [rng.randrange(n) for _ in range(n)]
        value = measure([xs[i] for i in index], [ys[i] for i in index])
        if value is not None:
            values.append(value)
    if not values:
        return None, None
    values.sort()
    return _quantile(values, (1 - level) / 2), _quantile(values, (1 + level) / 2)


# --------------------------------------------------------------------------- #
# Running
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class PairResult:
    pair_id: str
    language: str
    bucket: str
    rank: int
    requirements: tuple[str, ...]
    total: int
    levels: tuple[int, ...]
    repeat_totals: tuple[int, ...]
    repeat_levels: tuple[tuple[int, ...], ...]
    cost_usd: Decimal
    stability_cost_usd: Decimal
    prompt_tokens: int
    completion_tokens: int
    latency_s: float
    fingerprint: str | None

    @property
    def max_score_delta(self) -> int:
        totals = self.repeat_totals
        if len(totals) < 2:
            return 0
        return max(totals) - min(totals)

    @property
    def stability(self) -> float | None:
        """Mean tau-b between the pair's repeated gradings, if defined."""
        values = [
            kendall_tau_b(self.repeat_levels[i], self.repeat_levels[j])
            for i in range(len(self.repeat_levels))
            for j in range(i + 1, len(self.repeat_levels))
        ]
        present = [value for value in values if value is not None]
        if not present:
            return None
        return sum(present) / len(present)

    @property
    def identical_repeats(self) -> bool:
        return len(set(self.repeat_levels)) == 1

    @property
    def changed_ordinals(self) -> float:
        """PRD §9's own stability number: share of ordinals that moved."""
        if len(self.repeat_levels) < 2 or not self.levels:
            return 0.0
        first = self.repeat_levels[0]
        moves = 0
        checks = 0
        for run in self.repeat_levels[1:]:
            moves += sum(1 for a, b in zip(first, run, strict=True) if a != b)
            checks += len(first)
        return moves / checks if checks else 0.0


def _total_with_evidence(analysis: Analysis, levels: Sequence[Level]) -> int:
    """The pair's total with a repeat's grading substituted, everything else fixed."""
    recorded = analysis.report["score"]["sub_scores"]
    sub_scores = {
        name: SubScore(name=name, value=float(entry["value"]))
        for name, entry in recorded.items()
        if name != "evidence"
    }
    sub_scores["evidence"] = evidence_coverage(levels)
    return aggregate(sub_scores, W1, unavailable=UNAVAILABLE_UNTIL_M9).uncapped


def run_pair(
    candidate: Candidate,
    pair: GoldenPair,
    *,
    seed: int,
    repeats: int = DEFAULT_REPEATS,
    session: Session | None = None,
    profile_id: uuid.UUID | None = None,
) -> PairResult:
    """One analysis of the pair, then `repeats` fresh gradings of the same posting.

    The first grading is the analysis's own, so a pair costs one extraction plus
    `repeats` gradings. Extraction is held fixed for the repeats: the PRD's
    stability question is about the judge's ordinal, not about how the posting was
    read that day.

    A caller may supply the session it built itself — the test suite pre-warms that
    session's cache to prove the bypass is real.
    """
    if session is None:
        session, profile_id = build_session(pair)
    elif profile_id is None:
        raise ValueError("a supplied session needs the profile id it was built for")
    options = CallOptions(
        bypass_cache=True, seed=seed, reasoning_effort=candidate.reasoning_effort
    )

    started = time.perf_counter()
    analysis = analyze(
        profile_id, session, jd_text=pair.jd.text, model=candidate.model, options=options
    )
    latency = time.perf_counter() - started

    grades = analysis.report["grades"]
    requirements = tuple(str(grade["requirement"]) for grade in grades)
    must_have = tuple(bool(grade["must_have"]) for grade in grades)
    first_levels = tuple(int(grade["level"]) for grade in grades)
    llm_calls = analysis.report["llm"]["calls"]

    repeat_levels: list[tuple[int, ...]] = [first_levels]
    repeat_totals: list[int] = [int(analysis.report["score"]["uncapped"])]
    stability_cost = Decimal("0")
    for _ in range(max(1, repeats) - 1):
        report = grade_evidence(
            session,
            analysis.jd,
            analysis.bullets,
            language=analysis.jd.language,
            model=candidate.model,
            known_names=[pair.resume.display_name],
            options=options,
        )
        levels = tuple(entry.level for entry in report.levels)
        if len(levels) != len(requirements):
            # A short list would misalign the comparison; fail loudly instead.
            raise RuntimeError(
                f"{pair.id}: repeat returned {len(levels)} grades for "
                f"{len(requirements)} requirements"
            )
        repeat_levels.append(levels)
        repeat_totals.append(
            _total_with_evidence(
                analysis,
                [
                    Level(requirement, level, is_must)
                    for requirement, level, is_must in zip(
                        requirements, levels, must_have, strict=True
                    )
                ],
            )
        )
        stability_cost += sum(call.cost_usd for call in report.calls)

    return PairResult(
        pair_id=pair.id,
        language=pair.language,
        bucket=pair.bucket,
        rank=pair.rank,
        requirements=requirements,
        total=repeat_totals[0],
        levels=first_levels,
        repeat_totals=tuple(repeat_totals),
        repeat_levels=tuple(repeat_levels),
        cost_usd=analysis.cost_usd,
        stability_cost_usd=stability_cost,
        prompt_tokens=sum(int(call["prompt_tokens"]) for call in llm_calls),
        completion_tokens=sum(int(call["completion_tokens"]) for call in llm_calls),
        latency_s=latency,
        fingerprint=llm_calls[0].get("fingerprint") if llm_calls else None,
    )


@dataclass(frozen=True)
class CandidateReport:
    candidate: Candidate
    probe: ProbeOutcome
    pairs: tuple[PairResult, ...]
    seed: int
    repeats: int

    # -- aggregates ------------------------------------------------------- #

    @property
    def totals(self) -> list[int]:
        return [pair.total for pair in self.pairs]

    @property
    def ranks(self) -> list[int]:
        return [pair.rank for pair in self.pairs]

    def tau_b(self) -> float | None:
        return kendall_tau_b(self.totals, self.ranks)

    def tau_ci(self) -> tuple[float | None, float | None]:
        return bootstrap_ci(kendall_tau_b, self.totals, self.ranks, seed=self.seed)

    def rho(self) -> float | None:
        return spearman_rho(self.totals, self.ranks)

    def rho_ci(self) -> tuple[float | None, float | None]:
        return bootstrap_ci(spearman_rho, self.totals, self.ranks, seed=self.seed)

    def stability(self) -> float | None:
        values = [pair.stability for pair in self.pairs if pair.stability is not None]
        return sum(values) / len(values) if values else None

    def max_score_delta(self) -> int:
        return max((pair.max_score_delta for pair in self.pairs), default=0)

    def changed_ordinals(self) -> float:
        if not self.pairs:
            return 0.0
        return sum(pair.changed_ordinals for pair in self.pairs) / len(self.pairs)

    def identical_repeat_share(self) -> float:
        if not self.pairs:
            return 0.0
        return sum(1 for pair in self.pairs if pair.identical_repeats) / len(self.pairs)

    def costs(self) -> list[Decimal]:
        return [pair.cost_usd for pair in self.pairs]

    def total_spend(self) -> Decimal:
        return sum(
            (pair.cost_usd + pair.stability_cost_usd for pair in self.pairs), Decimal("0")
        )

    def cost_effective(self) -> Decimal:
        costs = self.costs()
        return sum(costs, Decimal("0")) / len(costs) if costs else Decimal("0")

    def cost_effective_spread(self) -> tuple[Decimal, Decimal, Decimal]:
        costs = sorted(self.costs())
        if not costs:
            return Decimal("0"), Decimal("0"), Decimal("0")
        middle = len(costs) // 2
        median = (
            costs[middle]
            if len(costs) % 2
            else (costs[middle - 1] + costs[middle]) / 2
        )
        return costs[0], median, costs[-1]

    def cost_list(self) -> Decimal:
        """What the run would cost at list prices, from the tokens it actually used."""
        if not self.pairs:
            return Decimal("0")
        price = PRICES[self.candidate.model]
        per_pair = [
            Decimal(str(price.input_list)) * pair.prompt_tokens / Decimal(1_000_000)
            + Decimal(str(price.output_list)) * pair.completion_tokens / Decimal(1_000_000)
            for pair in self.pairs
        ]
        return sum(per_pair, Decimal("0")) / len(per_pair)

    def latency_median(self) -> float:
        values = sorted(pair.latency_s for pair in self.pairs)
        if not values:
            return 0.0
        middle = len(values) // 2
        if len(values) % 2:
            return values[middle]
        return (values[middle - 1] + values[middle]) / 2

    def verdict(self) -> str:
        if not self.probe.ok:
            return "unavailable"
        if self.candidate.reference:
            return "reference only"
        flags: list[str] = []
        rho = self.rho()
        if rho is None or rho < RHO_GATE:
            flags.append(f"below gate (rho {rho if rho is None else round(rho, 2)} < {RHO_GATE})")
        if self.cost_list() > COST_CEILING_USD:
            flags.append(f"over budget at list (${self.cost_list():.6f} > ${COST_CEILING_USD})")
        if self.changed_ordinals() > INSTABILITY_FLAG:
            flags.append(f"unstable ({self.changed_ordinals():.0%} of ordinals moved)")
        return "; ".join(flags) if flags else "pass"


def run_experiment(
    pairs: Sequence[GoldenPair],
    candidates: Sequence[Candidate] = CANDIDATES,
    *,
    seed: int = DEFAULT_SEED,
    repeats: int = DEFAULT_REPEATS,
    progress: Callable[[str], None] | None = None,
) -> list[CandidateReport]:
    reports: list[CandidateReport] = []
    for candidate in candidates:
        probe = probe_candidate(candidate, seed=seed)
        if progress:
            failure = f" ({probe.error})" if probe.error else ""
            progress(f"{candidate.label}: {probe.seed_note}{failure}")
        results: list[PairResult] = []
        if probe.ok:
            for pair in pairs:
                if progress:
                    progress(f"  {candidate.label} · {pair.id} ({pair.bucket}, {pair.language})")
                results.append(run_pair(candidate, pair, seed=seed, repeats=repeats))
        reports.append(
            CandidateReport(
                candidate=candidate,
                probe=probe,
                pairs=tuple(results),
                seed=seed,
                repeats=repeats,
            )
        )
    return reports


# --------------------------------------------------------------------------- #
# Output
# --------------------------------------------------------------------------- #

TABLE_HEADER = (
    "| model | tau-b [95% CI] | rho [95% CI] | stability | max score delta | "
    "cost/analysis (effective) | cost/analysis (list) | median latency | verdict |"
)
TABLE_RULE = "|---|---|---|---|---|---|---|---|---|"


def _interval(value: float | None, confidence: tuple[float | None, float | None]) -> str:
    if value is None:
        return "n/a"
    low, high = confidence
    if low is None or high is None:
        return f"{value:.2f}"
    return f"{value:.2f} [{low:.2f}, {high:.2f}]"


def table_row(report: CandidateReport) -> str:
    stability = report.stability()
    cells = [
        report.candidate.label,
        _interval(report.tau_b(), report.tau_ci()),
        _interval(report.rho(), report.rho_ci()),
        "n/a" if stability is None else f"{stability:.2f}",
        str(report.max_score_delta()),
        f"${report.cost_effective():.6f}",
        f"${report.cost_list():.6f}",
        f"{report.latency_median():.1f}s",
        report.verdict(),
    ]
    return "| " + " | ".join(cells) + " |"


def render_table(reports: Sequence[CandidateReport], *, pairs: int) -> str:
    lines = [
        f"# Model selection — {pairs} labelled pairs, n repeats = "
        f"{reports[0].repeats if reports else 0}, seed {reports[0].seed if reports else 0}",
        "",
        "Agreement is Kendall's tau-b against the pair's bucket; Spearman is reported "
        "because the PRD names it. Confidence intervals are percentile bootstrap "
        "(2000 resamples, same seed). Stability is the mean tau-b between repeated "
        "gradings of the same posting, extraction held fixed.",
        "",
        TABLE_HEADER,
        TABLE_RULE,
    ]
    lines.extend(table_row(report) for report in reports)
    return "\n".join(lines)


def render_notes(reports: Sequence[CandidateReport]) -> str:
    lines: list[str] = []
    for report in reports:
        price = PRICES[report.candidate.model]
        low, middle, high = report.cost_effective_spread()
        lines.append(f"## {report.candidate.label}")
        if report.candidate.note:
            lines.append(f"- {report.candidate.note}")
        lines.append(
            f"- provider: {report.probe.seed_note}"
            + (f" — {report.probe.error}" if report.probe.error else "")
        )
        lines.append(
            f"- repeated gradings byte-identical: {report.identical_repeat_share():.0%} of pairs"
        )
        lines.append(
            f"- ordinals that moved between repeats (PRD §9): {report.changed_ordinals():.1%}"
        )
        lines.append(
            f"- cost per analysis: min ${low:.6f} / median ${middle:.6f} / max ${high:.6f} "
            f"(effective, billed) · list ${report.cost_list():.6f}"
        )
        lines.append(f"- spend this run: ${report.total_spend():.6f}")
        lines.append(
            f"- list price used: ${price.input_list}/M input, ${price.output_list}/M output"
            f" (provider showed ${price.current_input}/${price.current_output} that day)"
        )
        lines.append(f"  - {price.note}")
    return "\n".join(lines)


def report_to_json(report: CandidateReport) -> dict:
    return {
        "model": report.candidate.model,
        "label": report.candidate.label,
        "reasoning_effort": report.candidate.reasoning_effort,
        "reference": report.candidate.reference,
        "seed": report.seed,
        "repeats": report.repeats,
        "probe": {
            "ok": report.probe.ok,
            "seed_accepted": report.probe.seed_accepted,
            "fingerprint": report.probe.fingerprint,
            "error": report.probe.error,
        },
        "metrics": {
            "tau_b": report.tau_b(),
            "tau_b_ci": list(report.tau_ci()),
            "rho": report.rho(),
            "rho_ci": list(report.rho_ci()),
            "stability": report.stability(),
            "max_score_delta": report.max_score_delta(),
            "changed_ordinals": report.changed_ordinals(),
            "identical_repeat_share": report.identical_repeat_share(),
            "cost_effective_mean": str(report.cost_effective()),
            "cost_effective_min": str(report.cost_effective_spread()[0]),
            "cost_effective_median": str(report.cost_effective_spread()[1]),
            "cost_effective_max": str(report.cost_effective_spread()[2]),
            "cost_list": str(report.cost_list()),
            "latency_median_s": report.latency_median(),
            "total_spend": str(report.total_spend()),
            "verdict": report.verdict(),
        },
        "pairs": [
            {
                "id": pair.pair_id,
                "language": pair.language,
                "bucket": pair.bucket,
                "total": pair.total,
                "repeat_totals": list(pair.repeat_totals),
                "levels": list(pair.levels),
                "repeat_levels": [list(run) for run in pair.repeat_levels],
                "requirements": list(pair.requirements),
                "stability": pair.stability,
                "max_score_delta": pair.max_score_delta,
                "cost_usd": str(pair.cost_usd),
                "stability_cost_usd": str(pair.stability_cost_usd),
                "prompt_tokens": pair.prompt_tokens,
                "completion_tokens": pair.completion_tokens,
                "latency_s": pair.latency_s,
            }
            for pair in report.pairs
        ],
    }
