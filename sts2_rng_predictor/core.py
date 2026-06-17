#!/usr/bin/env python3
"""Predict STS2 correlated RNG outputs from observed RNG call ranges.

The implementation mirrors the deterministic parts used by STS2:

* `StringHelper.GetDeterministicHashCode`
* `StringHelper.SnakeCase` for RNG names
* `Rng(uint seed, string name) => new Rng(seed + hash(name))`
* the .NET compatibility implementation behind `System.Random(int seed)`

The public API is intentionally small:

    CallSpec(kind="next_int", min_inclusive=0, max_exclusive=4)
    Observation(offset, counter, call, observed_min, observed_max)
    Target(offset, counter, call)
    predict_distribution(observations, target)

Run `uv run python -m sts2_rng_predictor --self-test` for built-in checks.
Run `uv run python -m sts2_rng_predictor --example` for a worked example.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from typing import Any, Iterable, Literal

from .rng_compat import (
    INT_MAX,
    INT_MIN,
    MBIG,
    DotNetCompatRandom,
    derived_seed,
    derived_seeds_for_abs_seed,
    deterministic_hash_code,
    internal_sample_from_abs_seed,
    internal_sample_from_derived_u32,
    next_float_from_sample,
    next_int_from_sample,
    normalize_offset,
    rng_offset_for_name,
    sample_affine,
    snake_case,
    to_single,
    uint32,
)
from .same_counter import (
    IntCall,
    IntObservation,
    IntTarget,
    predict_same_counter_fast,
)

CallKind = Literal["next_int", "next_float"]


class PredictionTooBroadError(ValueError):
    """Raised when exact enumeration would exceed max_candidates."""


@dataclass(frozen=True)
class CallSpec:
    """A single STS2 Rng call.

    For `next_int`, `min_inclusive` and `max_exclusive` match
    `Rng.NextInt(minInclusive, maxExclusive)`. `NextInt(maxExclusive)` is
    represented as `min_inclusive=0`.

    For `next_float`, the same fields represent the float min and max used by
    `Rng.NextFloat(min, max)`. If a target `next_float` distribution is needed,
    set `buckets` to group the continuous result range into equal-width bins.
    """

    kind: CallKind = "next_int"
    min_inclusive: int | float = 0
    max_exclusive: int | float = INT_MAX
    buckets: int | None = None

    def __post_init__(self) -> None:
        if self.kind == "next_int":
            if not isinstance(self.min_inclusive, int) or not isinstance(self.max_exclusive, int):
                raise TypeError("next_int bounds must be integers")
            if self.min_inclusive >= self.max_exclusive:
                raise ValueError("next_int min_inclusive must be lower than max_exclusive")
            if self.max_exclusive - self.min_inclusive > INT_MAX:
                raise NotImplementedError("next_int ranges larger than int.MaxValue are not supported")
        elif self.kind == "next_float":
            if float(self.min_inclusive) > float(self.max_exclusive):
                raise ValueError("next_float min must not be higher than max")
            if self.buckets is not None and self.buckets <= 0:
                raise ValueError("next_float buckets must be positive")
        else:
            raise ValueError(f"Unsupported call kind: {self.kind}")


@dataclass(frozen=True)
class Observation:
    """An observed output interval for one RNG stream.

    `offset` is the 32-bit offset added to the shared hidden base seed. It can
    be an integer offset or an RNG name such as "monster_ai" or
    "CombatEnergyCosts".

    `counter` is the STS2 Rng counter before the observed call. The first call
    from a fresh Rng has counter 0.

    For integer calls, `observed_min` and `observed_max` are inclusive result
    bounds. For float calls, they are inclusive numeric filter bounds.
    """

    offset: int | str
    counter: int
    call: CallSpec
    observed_min: int | float
    observed_max: int | float


@dataclass(frozen=True)
class Target:
    """The target RNG call to predict."""

    offset: int | str
    counter: int
    call: CallSpec


@dataclass(frozen=True)
class PredictionResult:
    """Exact posterior distribution over target outputs or buckets."""

    distribution: dict[int | str, float]
    candidate_count: int
    initial_candidate_count: int
    filtering_stats: dict[str, int]
    diagnostics: dict[str, int | str]


_uint32 = uint32
_derived_seeds_for_abs_seed = derived_seeds_for_abs_seed
_internal_sample_from_abs_seed = internal_sample_from_abs_seed
_sample_affine = sample_affine
_internal_sample_from_derived_u32 = internal_sample_from_derived_u32
_next_int_from_sample = next_int_from_sample
_next_float_from_sample = next_float_from_sample
_to_single = to_single


def _call_result_from_sample(sample: int, call: CallSpec) -> int | float:
    if call.kind == "next_int":
        return _next_int_from_sample(sample, int(call.min_inclusive), int(call.max_exclusive))
    return _next_float_from_sample(sample, float(call.min_inclusive), float(call.max_exclusive))


def _call_result(base_seed: int, offset: int | str, counter: int, call: CallSpec) -> int | float:
    seed = derived_seed(base_seed, offset)
    sample = _internal_sample_from_derived_u32(seed, counter)
    return _call_result_from_sample(sample, call)


def _observation_matches(base_seed: int, observation: Observation) -> bool:
    result = _call_result(base_seed, observation.offset, observation.counter, observation.call)
    return observation.observed_min <= result <= observation.observed_max


def _sample_intervals_for_next_int_observation(observation: Observation) -> list[tuple[int, int]]:
    call = observation.call
    if call.kind != "next_int":
        raise ValueError("Only next_int observations can be inverted into sample intervals")

    min_value = int(call.min_inclusive)
    max_value = int(call.max_exclusive)
    range_size = max_value - min_value

    observed_min = max(int(observation.observed_min), min_value)
    observed_max = min(int(observation.observed_max), max_value - 1)
    if observed_min > observed_max:
        return []

    lo_bucket = observed_min - min_value
    hi_bucket_exclusive = observed_max - min_value + 1

    # The exact System.Random path uses double arithmetic. These integer bounds
    # are the mathematical floor boundaries; expand a few samples on both sides
    # and let the normal exact-output filter remove any false positives.
    sample_lo = math.floor((lo_bucket * MBIG) / range_size) - 4
    sample_hi = math.ceil((hi_bucket_exclusive * MBIG) / range_size) + 4
    sample_lo = max(0, sample_lo)
    sample_hi = min(MBIG - 1, sample_hi)
    return [(sample_lo, sample_hi)]


def _candidate_count_for_intervals(intervals: Iterable[tuple[int, int]]) -> int:
    return sum(max(0, hi - lo + 1) for lo, hi in intervals)


def _choose_primary_observation(observations: list[Observation]) -> tuple[int, list[tuple[int, int]]]:
    invertible: list[tuple[int, list[tuple[int, int]], int]] = []
    for i, observation in enumerate(observations):
        if observation.call.kind != "next_int":
            continue
        intervals = _sample_intervals_for_next_int_observation(observation)
        invertible.append((i, intervals, _candidate_count_for_intervals(intervals)))
    if not invertible:
        raise ValueError("At least one next_int observation is required for exact candidate generation")
    index, intervals, _ = min(invertible, key=lambda item: item[2])
    return index, intervals


def _generate_candidates_from_primary(
    observation: Observation,
    intervals: list[tuple[int, int]],
    max_candidates: int,
) -> list[int]:
    offset = normalize_offset(observation.offset)
    alpha, beta = _sample_affine(observation.counter)
    inverse_alpha = pow(alpha, -1, MBIG)

    interval_sample_count = _candidate_count_for_intervals(intervals)
    estimated_candidates = interval_sample_count * 2 + 2
    if estimated_candidates > max_candidates:
        raise PredictionTooBroadError(
            "Primary observation leaves too many candidates "
            f"({estimated_candidates:,} estimated > {max_candidates:,}). "
            "Add narrower observations or raise max_candidates."
        )

    candidates: set[int] = set()
    for sample_lo, sample_hi in intervals:
        for sample in range(sample_lo, sample_hi + 1):
            abs_seed = ((sample - beta) * inverse_alpha) % MBIG
            for seed in _derived_seeds_for_abs_seed(abs_seed):
                candidates.add(_uint32(seed - offset))

    # Handle the non-linear abs(seed) corner where abs_seed == int.MaxValue.
    for seed in _derived_seeds_for_abs_seed(MBIG):
        base_seed = _uint32(seed - offset)
        if _observation_matches(base_seed, observation):
            candidates.add(base_seed)

    if len(candidates) > max_candidates:
        raise PredictionTooBroadError(
            "Primary observation leaves too many candidates "
            f"({len(candidates):,} > {max_candidates:,}). "
            "Add narrower observations or raise max_candidates."
        )
    return list(candidates)


def _target_bucket(result: int | float, call: CallSpec) -> int | str:
    if call.kind == "next_int":
        return int(result)
    if call.buckets is None:
        raise ValueError("next_float targets require CallSpec.buckets for a finite distribution")
    min_value = float(call.min_inclusive)
    max_value = float(call.max_exclusive)
    if min_value == max_value:
        return f"[{min_value}, {max_value}]"
    width = (max_value - min_value) / call.buckets
    index = int((float(result) - min_value) / width)
    index = min(max(index, 0), call.buckets - 1)
    lo = min_value + index * width
    hi = lo + width
    return f"[{lo:.8g}, {hi:.8g})"


def predict_distribution(
    observations: Iterable[Observation],
    target: Target,
    *,
    max_candidates: int = 5_000_000,
) -> PredictionResult:
    """Return an exact posterior target distribution.

    Exactness is over all 32-bit base seeds that satisfy the provided
    observations. Candidate generation requires at least one `next_int`
    observation.
    """

    observation_list = list(observations)
    if not observation_list:
        raise ValueError("At least one observation is required")
    if max_candidates <= 0:
        raise ValueError("max_candidates must be positive")

    primary_index, primary_intervals = _choose_primary_observation(observation_list)
    primary = observation_list[primary_index]
    candidates = _generate_candidates_from_primary(primary, primary_intervals, max_candidates)
    initial_count = len(candidates)

    filtering_stats: dict[str, int] = {f"primary[{primary_index}]": initial_count}
    filtered = candidates
    for i, observation in enumerate(observation_list):
        before = len(filtered)
        filtered = [base for base in filtered if _observation_matches(base, observation)]
        filtering_stats[f"observation[{i}]"] = before - len(filtered)
        if not filtered:
            break

    counts: Counter[int | str] = Counter()
    for base_seed in filtered:
        result = _call_result(base_seed, target.offset, target.counter, target.call)
        counts[_target_bucket(result, target.call)] += 1

    total = sum(counts.values())
    distribution = {
        result: count / total
        for result, count in sorted(counts.items(), key=lambda item: str(item[0]))
    } if total else {}

    diagnostics: dict[str, int | str] = {
        "primary_observation": primary_index,
        "primary_sample_count": _candidate_count_for_intervals(primary_intervals),
        "target_offset": normalize_offset(target.offset),
        "target_counter": target.counter,
        "target_kind": target.call.kind,
    }

    return PredictionResult(
        distribution=distribution,
        candidate_count=total,
        initial_candidate_count=initial_count,
        filtering_stats=filtering_stats,
        diagnostics=diagnostics,
    )


def _iter_base_seeds_from_primary_observation(
    observation: Observation,
    intervals: list[tuple[int, int]],
) -> Iterable[int]:
    offset = normalize_offset(observation.offset)
    alpha, beta = _sample_affine(observation.counter)
    inverse_alpha = pow(alpha, -1, MBIG)

    for sample_lo, sample_hi in intervals:
        for sample in range(sample_lo, sample_hi + 1):
            abs_seed = ((sample - beta) * inverse_alpha) % MBIG
            for seed in _derived_seeds_for_abs_seed(abs_seed):
                yield _uint32(seed - offset)

    # The int.MaxValue / int.MinValue folded-seed boundary is not represented
    # by the affine modulo-M inverse above, so include it as point cases.
    for seed in _derived_seeds_for_abs_seed(MBIG):
        base_seed = _uint32(seed - offset)
        if _observation_matches(base_seed, observation):
            yield base_seed


def predict_same_counter_distribution(
    observations: Iterable[Observation],
    target: Target,
    *,
    max_anchor_samples: int = 5_000_000,
) -> PredictionResult:
    """Predict a target distribution when all calls use the same counter.

    This is a streaming exact enumerator over the raw-sample space of the
    narrowest `next_int` observation. It avoids storing the full candidate
    base-seed set, but still refuses observations whose best anchor sample
    interval exceeds `max_anchor_samples`.
    """

    observation_list = list(observations)
    if not observation_list:
        raise ValueError("At least one observation is required")
    if max_anchor_samples <= 0:
        raise ValueError("max_anchor_samples must be positive")

    counters = {observation.counter for observation in observation_list}
    counters.add(target.counter)
    if len(counters) != 1:
        raise ValueError("predict_same_counter_distribution requires all observations and target to share one counter")

    primary_index, primary_intervals = _choose_primary_observation(observation_list)
    primary = observation_list[primary_index]
    anchor_sample_count = _candidate_count_for_intervals(primary_intervals)
    if anchor_sample_count > max_anchor_samples:
        raise PredictionTooBroadError(
            "Best same-counter anchor observation leaves too many raw samples "
            f"({anchor_sample_count:,} > {max_anchor_samples:,}). "
            "Add narrower observations or raise max_anchor_samples."
        )

    filtering_stats: dict[str, int] = {f"anchor[{primary_index}]": anchor_sample_count}
    generated_count = 0
    matched_count = 0
    counts: Counter[int | str] = Counter()

    for base_seed in _iter_base_seeds_from_primary_observation(primary, primary_intervals):
        generated_count += 1
        for i, observation in enumerate(observation_list):
            if not _observation_matches(base_seed, observation):
                filtering_stats[f"observation[{i}]"] = filtering_stats.get(f"observation[{i}]", 0) + 1
                break
        else:
            matched_count += 1
            result = _call_result(base_seed, target.offset, target.counter, target.call)
            counts[_target_bucket(result, target.call)] += 1

    distribution = {
        result: count / matched_count
        for result, count in sorted(counts.items(), key=lambda item: str(item[0]))
    } if matched_count else {}

    diagnostics: dict[str, int | str] = {
        "mode": "same_counter_raw_sample_anchor",
        "counter": next(iter(counters)),
        "anchor_observation": primary_index,
        "anchor_sample_count": anchor_sample_count,
        "generated_base_seed_count": generated_count,
        "target_offset": normalize_offset(target.offset),
        "target_kind": target.call.kind,
    }

    return PredictionResult(
        distribution=distribution,
        candidate_count=matched_count,
        initial_candidate_count=generated_count,
        filtering_stats=filtering_stats,
        diagnostics=diagnostics,
    )


def _format_distribution(distribution: dict[Any, float]) -> str:
    lines = []
    for result, probability in distribution.items():
        lines.append(f"  {result}: {probability:.6%}")
    return "\n".join(lines)


def run_example() -> None:
    base = 0x1234ABCD
    obs1_call = CallSpec("next_int", 0, INT_MAX)
    obs2_call = CallSpec("next_int", 0, INT_MAX)
    target_call = CallSpec("next_int", 0, 4)

    obs1_value = int(_call_result(base, "monster_ai", 0, obs1_call))
    obs2_value = int(_call_result(base, "combat_energy_costs", 2, obs2_call))
    target_value = int(_call_result(base, "shuffle", 0, target_call))

    observations = [
        Observation("monster_ai", 0, obs1_call, obs1_value, obs1_value),
        Observation("combat_energy_costs", 2, obs2_call, obs2_value, obs2_value),
    ]
    result = predict_distribution(
        observations,
        Target("shuffle", 0, target_call),
        max_candidates=100,
    )

    print("Synthetic hidden base seed: 0x1234ABCD")
    print(f"Observed monster_ai counter 0 NextInt(): {obs1_value}")
    print(f"Observed combat_energy_costs counter 2 NextInt(): {obs2_value}")
    print(f"Actual shuffle counter 0 NextInt(4): {target_value}")
    print(f"Posterior candidates: {result.candidate_count}")
    print("Predicted distribution:")
    print(_format_distribution(result.distribution))


def run_same_counter_example() -> None:
    base = 0xCC623A9B
    counter = 0
    obs_call = CallSpec("next_int", 0, 1_000_000)
    target_call = CallSpec("next_int", 0, 10)

    obs_a_value = int(_call_result(base, 0, counter, obs_call))
    obs_b_value = int(_call_result(base, "monster_ai", counter, obs_call))
    target_value = int(_call_result(base, "niche", counter, target_call))

    result = predict_same_counter_fast(
        [
            IntObservation(0, counter, IntCall(0, 1_000_000), obs_a_value, obs_a_value),
            IntObservation("monster_ai", counter, IntCall(0, 1_000_000), obs_b_value, obs_b_value),
        ],
        IntTarget("niche", counter, IntCall(0, 10)),
    )

    print("Synthetic hidden base seed: 0xCC623A9B")
    print(f"Observed offset 0 counter {counter} NextInt(1000000): {obs_a_value}")
    print(f"Observed monster_ai counter {counter} NextInt(1000000): {obs_b_value}")
    print(f"Actual niche counter {counter} NextInt(10): {target_value}")
    print(f"Posterior candidates: {result.total_count}")
    print("Predicted distribution:")
    print(_format_distribution(result.distribution))


def run_self_test() -> None:
    assert snake_case("CombatEnergyCosts") == "combat_energy_costs"
    assert snake_case("monster_ai") == "monster_ai"
    assert deterministic_hash_code("") == 757_602_046
    assert deterministic_hash_code("monster_ai") == 1_703_902_611
    assert deterministic_hash_code("combat_energy_costs") == -1_516_337_938
    assert rng_offset_for_name("CombatEnergyCosts") == _uint32(-1_516_337_938)

    expected_next_values = {
        0: [1_559_595_546, 1_755_192_844, 1_649_316_166, 1_198_642_031, 442_452_829],
        1: [534_011_718, 237_820_880, 1_002_897_798, 1_657_007_234, 1_412_011_072],
        -1: [534_011_718, 237_820_880, 1_002_897_798, 1_657_007_234, 1_412_011_072],
        -INT_MAX: [1_559_595_546, 1_755_192_844, 1_649_316_172, 1_198_642_031, 442_452_829],
        INT_MIN: [1_559_595_546, 1_755_192_844, 1_649_316_172, 1_198_642_031, 442_452_829],
        INT_MAX: [1_559_595_546, 1_755_192_844, 1_649_316_172, 1_198_642_031, 442_452_829],
    }
    for seed, expected in expected_next_values.items():
        rng = DotNetCompatRandom(seed)
        assert [rng.next_int() for _ in range(5)] == expected

    rng = DotNetCompatRandom(123_456_789)
    assert rng.next_int(10) == 5
    assert rng.next_int_range(5, 12) == 6
    assert abs(rng.next_float() - _to_single(0.621947593345282)) < 1e-7

    base = 0x0BADF00D
    obs_call = CallSpec("next_int", 0, INT_MAX)
    target_call = CallSpec("next_int", 0, 7)
    obs_a = int(_call_result(base, "monster_ai", 0, obs_call))
    obs_b = int(_call_result(base, "combat_energy_costs", 1, obs_call))
    target_value = int(_call_result(base, "shuffle", 3, target_call))
    prediction = predict_distribution(
        [
            Observation("monster_ai", 0, obs_call, obs_a, obs_a),
            Observation("combat_energy_costs", 1, obs_call, obs_b, obs_b),
        ],
        Target("shuffle", 3, target_call),
        max_candidates=100,
    )
    assert prediction.candidate_count >= 1
    assert prediction.distribution[target_value] > 0

    # Cross-check the predictor against brute force over the exact candidates
    # generated by a primary observation in a tiny synthetic case.
    tiny_call = CallSpec("next_int", 0, INT_MAX)
    tiny_obs_value = int(_call_result(base, 12345, 0, tiny_call))
    tiny_obs = Observation(12345, 0, tiny_call, tiny_obs_value, tiny_obs_value)
    primary_index, intervals = _choose_primary_observation([tiny_obs])
    assert primary_index == 0
    candidates = _generate_candidates_from_primary(tiny_obs, intervals, 100)
    brute_counts = Counter(
        int(_call_result(candidate, 67890, 0, CallSpec("next_int", 0, 5)))
        for candidate in candidates
        if _observation_matches(candidate, tiny_obs)
    )
    predicted = predict_distribution(
        [tiny_obs],
        Target(67890, 0, CallSpec("next_int", 0, 5)),
        max_candidates=100,
    )
    brute_total = sum(brute_counts.values())
    brute_distribution = {k: v / brute_total for k, v in sorted(brute_counts.items())}
    assert predicted.distribution == brute_distribution

    same_counter_prediction = predict_same_counter_distribution(
        [
            Observation("monster_ai", 0, obs_call, obs_a, obs_a),
            Observation("combat_energy_costs", 0, obs_call, int(_call_result(base, "combat_energy_costs", 0, obs_call)), int(_call_result(base, "combat_energy_costs", 0, obs_call))),
        ],
        Target("shuffle", 0, target_call),
        max_anchor_samples=100,
    )
    assert same_counter_prediction.candidate_count >= 1
    assert int(_call_result(base, "shuffle", 0, target_call)) in same_counter_prediction.distribution

    fast_same_counter = predict_same_counter_fast(
        [
            IntObservation("monster_ai", 0, IntCall(0, INT_MAX), obs_a, obs_a),
            IntObservation(
                "combat_energy_costs",
                0,
                IntCall(0, INT_MAX),
                int(_call_result(base, "combat_energy_costs", 0, obs_call)),
                int(_call_result(base, "combat_energy_costs", 0, obs_call)),
            ),
        ],
        IntTarget("shuffle", 0, IntCall(0, 7)),
    )
    assert fast_same_counter.total_count == same_counter_prediction.candidate_count
    assert fast_same_counter.distribution == same_counter_prediction.distribution

    for test_counter in (0, 1, 3):
        for test_base in (0, 1, 0x1234ABCD, 0xCC623A9B, 0x80000000):
            narrow_call = CallSpec("next_int", 0, 1_000_000)
            narrow_int_call = IntCall(0, 1_000_000)
            stream_observations = []
            fast_observations = []
            for offset in (0, "monster_ai"):
                value = int(_call_result(test_base, offset, test_counter, narrow_call))
                stream_observations.append(Observation(offset, test_counter, narrow_call, value, value))
                fast_observations.append(IntObservation(offset, test_counter, narrow_int_call, value, value))

            stream_result = predict_same_counter_distribution(
                stream_observations,
                Target("niche", test_counter, CallSpec("next_int", 0, 10)),
                max_anchor_samples=5_000,
            )
            fast_result = predict_same_counter_fast(
                fast_observations,
                IntTarget("niche", test_counter, IntCall(0, 10)),
            )
            assert fast_result.total_count == stream_result.candidate_count
            assert fast_result.distribution == stream_result.distribution

    print("self-test ok")
