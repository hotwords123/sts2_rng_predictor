"""Non-enumerating same-counter conditional predictor.

This module is intentionally separate from the older base-seed enumerator in
`core.py`. It only reuses `rng_compat.py` for STS2/.NET RNG behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import Iterable, Literal

from .rng_compat import (
    MBIG,
    derived_seed,
    internal_sample_from_derived_u32,
    next_int_from_sample,
    normalize_offset,
    sample_affine,
    uint32,
)


Q = 2**32
Sign = Literal[1, -1]
Interval = tuple[int, int]
BranchState = tuple[Sign, int]
BOUNDARY_DERIVED_SEEDS = (MBIG, MBIG + 1, MBIG + 2)


@dataclass(frozen=True)
class IntCall:
    min_inclusive: int = 0
    max_exclusive: int = 2_147_483_647

    def __post_init__(self) -> None:
        if self.min_inclusive >= self.max_exclusive:
            raise ValueError("min_inclusive must be lower than max_exclusive")

    @property
    def size(self) -> int:
        return self.max_exclusive - self.min_inclusive


@dataclass(frozen=True)
class IntObservation:
    offset: int | str
    counter: int
    call: IntCall
    observed_min: int
    observed_max: int


@dataclass(frozen=True)
class IntTarget:
    offset: int | str
    counter: int
    call: IntCall


@dataclass(frozen=True)
class SameCounterResult:
    distribution: dict[int, float]
    counts: dict[int, int]
    total_count: int
    diagnostics: dict[str, int | str]


def _normalize_intervals(intervals: Iterable[Interval], mod: int = MBIG) -> tuple[Interval, ...]:
    cleaned = sorted((max(0, lo), min(mod, hi)) for lo, hi in intervals if lo < hi)
    if not cleaned:
        return ()
    merged: list[Interval] = []
    cur_lo, cur_hi = cleaned[0]
    for lo, hi in cleaned[1:]:
        if lo <= cur_hi:
            cur_hi = max(cur_hi, hi)
        else:
            merged.append((cur_lo, cur_hi))
            cur_lo, cur_hi = lo, hi
    merged.append((cur_lo, cur_hi))
    return tuple(merged)


def _intersect_two(a: Iterable[Interval], b: Iterable[Interval]) -> tuple[Interval, ...]:
    left = list(a)
    right = list(b)
    i = j = 0
    result: list[Interval] = []
    while i < len(left) and j < len(right):
        lo = max(left[i][0], right[j][0])
        hi = min(left[i][1], right[j][1])
        if lo < hi:
            result.append((lo, hi))
        if left[i][1] < right[j][1]:
            i += 1
        else:
            j += 1
    return tuple(result)


def _interval_from_start_len(start: int, length: int, mod: int = MBIG) -> tuple[Interval, ...]:
    if length <= 0:
        return ()
    if length >= mod:
        return ((0, mod),)
    start %= mod
    end = start + length
    if end <= mod:
        return ((start, end),)
    return ((start, mod), (0, end - mod))


def _shift_intervals(intervals: Iterable[Interval], delta: int, mod: int = MBIG) -> tuple[Interval, ...]:
    result: list[Interval] = []
    for lo, hi in intervals:
        result.extend(_interval_from_start_len(lo + delta, hi - lo, mod))
    return _normalize_intervals(result, mod)


def _reflect_preimage_intervals(intervals: Iterable[Interval], offset: int, mod: int = MBIG) -> tuple[Interval, ...]:
    result: list[Interval] = []
    for lo, hi in intervals:
        result.extend(_interval_from_start_len(offset - hi + 1, hi - lo, mod))
    return _normalize_intervals(result, mod)


def _sample_intervals(call: IntCall, observed_min: int, observed_max: int) -> tuple[Interval, ...]:
    observed_min = max(observed_min, call.min_inclusive)
    observed_max = min(observed_max, call.max_exclusive - 1)
    if observed_min > observed_max:
        return ()

    lo = _first_sample_with_result_at_least(call, observed_min)
    hi = _first_sample_with_result_at_least(call, observed_max + 1)
    return _normalize_intervals(((lo, hi),))


def _first_sample_with_result_at_least(call: IntCall, threshold: int) -> int:
    if threshold <= call.min_inclusive:
        return 0
    if threshold >= call.max_exclusive:
        return MBIG

    lo = 0
    hi = MBIG
    while lo < hi:
        mid = (lo + hi) // 2
        result = next_int_from_sample(mid, call.min_inclusive, call.max_exclusive)
        if result >= threshold:
            hi = mid
        else:
            lo = mid + 1
    return lo


def _target_bucket_interval(call: IntCall, result: int) -> tuple[Interval, ...]:
    return _sample_intervals(call, result, result)


def _floor_sum(n: int, m: int, a: int, b: int) -> int:
    """Return sum_{0 <= i < n} floor((a*i+b)/m)."""

    result = 0
    while True:
        if a >= m:
            result += (n - 1) * n * (a // m) // 2
            a %= m
        if b >= m:
            result += n * (b // m)
            b %= m

        y_max = a * n + b
        if y_max < m:
            return result
        n = y_max // m
        b = y_max % m
        a, m = m, a


def _prefix_mod_lt(n: int, threshold: int, p: int, q: int, mod: int = MBIG) -> int:
    if n <= 0 or threshold <= 0:
        return 0
    if threshold >= mod:
        return n
    p %= mod
    q %= mod
    ge_count = _floor_sum(n, mod, p, q + mod - threshold) - _floor_sum(n, mod, p, q)
    return n - ge_count


def _count_mod_interval(x_interval: Interval, p: int, q: int, s_interval: Interval) -> int:
    x_lo, x_hi = x_interval
    s_lo, s_hi = s_interval
    below_hi = _prefix_mod_lt(x_hi, s_hi, p, q) - _prefix_mod_lt(x_lo, s_hi, p, q)
    below_lo = _prefix_mod_lt(x_hi, s_lo, p, q) - _prefix_mod_lt(x_lo, s_lo, p, q)
    return below_hi - below_lo


def _count_x_with_s_guard(
    x_intervals: Iterable[Interval],
    s_intervals: Iterable[Interval],
    p: int,
    q: int,
) -> int:
    total = 0
    for x_interval in x_intervals:
        for s_interval in s_intervals:
            total += _count_mod_interval(x_interval, p, q, s_interval)
    return total


def _intersect_linear_intervals(a: Interval, b: Interval) -> Interval | None:
    lo = max(a[0], b[0])
    hi = min(a[1], b[1])
    return (lo, hi) if lo < hi else None


def _z_interval_to_anchor_s(anchor_sign: Sign, z_interval: Interval) -> tuple[Interval, ...]:
    z_lo, z_hi = z_interval
    if anchor_sign == 1:
        clipped = _intersect_linear_intervals((z_lo, z_hi), (0, MBIG))
        return (clipped,) if clipped else ()

    # z = Q - S for the negative anchor branch. The affine domain excludes the
    # three abs(seed) == int.MaxValue boundary seeds, so S is [1, M).
    lo = Q - z_hi + 1
    hi = Q - z_lo + 1
    clipped = _intersect_linear_intervals((lo, hi), (1, MBIG))
    return (clipped,) if clipped else ()


def _guard_intervals_for_stream(
    anchor_sign: Sign,
    stream_sign: Sign,
    stream_wrap: int,
    delta_q: int,
) -> tuple[Interval, ...]:
    if stream_wrap not in (0, 1):
        raise ValueError("stream_wrap must be 0 or 1")

    sign_interval = (0, MBIG) if stream_sign == 1 else (MBIG + 3, Q)
    if stream_wrap == 0:
        wrap_interval = (0, Q - delta_q)
        shifted_sign_interval = (sign_interval[0] - delta_q, sign_interval[1] - delta_q)
    else:
        wrap_interval = (Q - delta_q, Q)
        shifted_sign_interval = (Q + sign_interval[0] - delta_q, Q + sign_interval[1] - delta_q)

    z_interval = _intersect_linear_intervals(wrap_interval, shifted_sign_interval)
    if not z_interval:
        return ()
    return _z_interval_to_anchor_s(anchor_sign, z_interval)


def _relation_to_anchor(
    alpha: int,
    beta: int,
    anchor_sign: Sign,
    stream_sign: Sign,
    stream_wrap: int,
    delta_m: int,
) -> tuple[Sign, int]:
    r_anchor = 1 if anchor_sign == 1 else -1
    t_anchor = 0 if anchor_sign == 1 else 2
    if stream_sign == 1:
        coeff = r_anchor
        const = t_anchor + delta_m - 2 * stream_wrap
    else:
        coeff = -r_anchor
        const = 2 - (t_anchor + delta_m) + 2 * stream_wrap

    if coeff == 1:
        return 1, (alpha * const) % MBIG
    return -1, (alpha * const + 2 * beta) % MBIG


def _pull_back_sample_intervals(
    intervals: Iterable[Interval],
    sign: Sign,
    offset: int,
) -> tuple[Interval, ...]:
    if sign == 1:
        return _shift_intervals(intervals, -offset)
    return _reflect_preimage_intervals(intervals, offset)


def _call_result(base_seed: int, offset: int | str, counter: int, call: IntCall) -> int:
    seed = derived_seed(base_seed, offset)
    sample = internal_sample_from_derived_u32(seed, counter)
    return next_int_from_sample(sample, call.min_inclusive, call.max_exclusive)


def _matches_observation(base_seed: int, observation: IntObservation) -> bool:
    result = _call_result(base_seed, observation.offset, observation.counter, observation.call)
    return observation.observed_min <= result <= observation.observed_max


def _add_boundary_point_counts(
    counts: dict[int, int],
    observations: list[IntObservation],
    target: IntTarget,
) -> int:
    offsets = {normalize_offset(observation.offset) for observation in observations}
    offsets.add(normalize_offset(target.offset))
    added = 0
    seen: set[int] = set()
    for offset in offsets:
        for seed in BOUNDARY_DERIVED_SEEDS:
            base_seed = uint32(seed - offset)
            if base_seed in seen:
                continue
            seen.add(base_seed)
            if all(_matches_observation(base_seed, observation) for observation in observations):
                result = _call_result(base_seed, target.offset, target.counter, target.call)
                counts[result] = counts.get(result, 0) + 1
                added += 1
    return added


def predict_same_counter_fast(
    observations: Iterable[IntObservation],
    target: IntTarget,
    *,
    max_target_buckets: int = 100_000,
) -> SameCounterResult:
    observation_list = list(observations)
    if not observation_list:
        raise ValueError("At least one observation is required")
    if max_target_buckets <= 0:
        raise ValueError("max_target_buckets must be positive")
    if target.call.size > max_target_buckets:
        raise ValueError(
            "target range has too many output buckets "
            f"({target.call.size:,} > {max_target_buckets:,}); "
            "narrow the target call or raise max_target_buckets"
        )

    counters = {observation.counter for observation in observation_list}
    counters.add(target.counter)
    if len(counters) != 1:
        raise ValueError("all observations and target must use the same counter")
    counter = next(iter(counters))

    alpha, beta = sample_affine(counter)
    inv_alpha = pow(alpha, -1, MBIG)
    s_from_x_p = inv_alpha
    s_from_x_q = (-inv_alpha * beta) % MBIG

    obs_intervals = [_sample_intervals(o.call, o.observed_min, o.observed_max) for o in observation_list]
    if any(not intervals for intervals in obs_intervals):
        return SameCounterResult({}, {}, 0, {"counter": counter, "reason": "empty_observation"})

    anchor_index = min(range(len(observation_list)), key=lambda i: sum(hi - lo for lo, hi in obs_intervals[i]))
    anchor = observation_list[anchor_index]
    anchor_offset = normalize_offset(anchor.offset)
    anchor_intervals = obs_intervals[anchor_index]

    offsets = sorted({normalize_offset(o.offset) for o in observation_list} | {normalize_offset(target.offset)})
    other_offsets = [offset for offset in offsets if offset != anchor_offset]
    counts: dict[int, int] = {}
    branch_count = 0
    branch_states: tuple[BranchState, ...] = ((1, 0), (1, 1), (-1, 0), (-1, 1))

    for anchor_sign in (1, -1):
        for states in product(branch_states, repeat=len(other_offsets)):
            branch_count += 1
            state_by_offset: dict[int, BranchState] = {
                anchor_offset: (anchor_sign, 0),
                **dict(zip(other_offsets, states)),
            }

            s_guard: tuple[Interval, ...] = ((0, MBIG),) if anchor_sign == 1 else ((1, MBIG),)
            for offset, (sign, wrap) in state_by_offset.items():
                if offset == anchor_offset:
                    continue
                guard = _guard_intervals_for_stream(anchor_sign, sign, wrap, (offset - anchor_offset) % Q)
                s_guard = _intersect_two(s_guard, guard)
                if not s_guard:
                    break
            if not s_guard:
                continue

            common_x = anchor_intervals
            for observation, intervals in zip(observation_list, obs_intervals):
                offset = normalize_offset(observation.offset)
                if offset == anchor_offset:
                    pulled = intervals
                else:
                    delta_q = (offset - anchor_offset) % Q
                    relation_sign, relation_offset = _relation_to_anchor(
                        alpha,
                        beta,
                        anchor_sign,
                        state_by_offset[offset][0],
                        state_by_offset[offset][1],
                        delta_q % MBIG,
                    )
                    pulled = _pull_back_sample_intervals(intervals, relation_sign, relation_offset)
                common_x = _intersect_two(common_x, pulled)
                if not common_x:
                    break
            if not common_x:
                continue

            target_offset = normalize_offset(target.offset)
            target_delta_q = (target_offset - anchor_offset) % Q
            relation_sign, relation_offset = _relation_to_anchor(
                alpha,
                beta,
                anchor_sign,
                state_by_offset[target_offset][0],
                state_by_offset[target_offset][1],
                target_delta_q % MBIG,
            )
            for result in range(target.call.min_inclusive, target.call.max_exclusive):
                target_intervals = _target_bucket_interval(target.call, result)
                target_x = _pull_back_sample_intervals(target_intervals, relation_sign, relation_offset)
                x_domain = _intersect_two(common_x, target_x)
                if not x_domain:
                    continue
                count = _count_x_with_s_guard(x_domain, s_guard, s_from_x_p, s_from_x_q)
                if count:
                    counts[result] = counts.get(result, 0) + count

    boundary_count = _add_boundary_point_counts(counts, observation_list, target)
    counts = {result: count for result, count in counts.items() if count}
    total = sum(counts.values())
    distribution = {result: count / total for result, count in sorted(counts.items())} if total else {}
    return SameCounterResult(
        distribution=distribution,
        counts=dict(sorted(counts.items())),
        total_count=total,
        diagnostics={
            "counter": counter,
            "anchor_observation": anchor_index,
            "anchor_offset": anchor_offset,
            "branch_count": branch_count,
            "boundary_count": boundary_count,
        },
    )
