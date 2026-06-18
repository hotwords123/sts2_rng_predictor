"""Reusable STS2/.NET RNG compatibility helpers."""

from __future__ import annotations

import re
import struct
from functools import lru_cache


INT_MAX = 2_147_483_647
INT_MIN = -2_147_483_648
UINT_MASK = 0xFFFFFFFF
MBIG = INT_MAX
MSEED = 161_803_398


def int32(value: int) -> int:
    value &= UINT_MASK
    if value >= 0x80000000:
        value -= 0x100000000
    return value


def uint32(value: int) -> int:
    return value & UINT_MASK


def u32_to_i32(value: int) -> int:
    return int32(value)


def to_single(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", value))[0]


def snake_case(txt: str) -> str:
    """Approximate STS2 StringHelper.SnakeCase for RNG enum/name inputs."""

    stripped = txt.strip()
    return re.sub(r"([A-Za-z0-9])([A-Z])", r"\1_\2", stripped).lower()


def deterministic_hash_code(text: str) -> int:
    """Mirror STS2 StringHelper.GetDeterministicHashCode."""

    num = 352_654_597
    num2 = num
    for i in range(0, len(text), 2):
        num = int32(int32((num << 5) + num) ^ ord(text[i]))
        if i == len(text) - 1:
            break
        num2 = int32(int32((num2 << 5) + num2) ^ ord(text[i + 1]))
    return int32(num + int32(num2 * 1_566_083_941))


def rng_offset_for_name(name: str) -> int:
    """Return the 32-bit STS2 RNG-name offset."""

    return uint32(deterministic_hash_code(snake_case(name)))


def event_offset_for_id(event_id: str, net_id: int = 1) -> int:
    """Return the 32-bit single-event RNG offset.

    EventModel.BeginEvent seeds event RNGs with
    `runSeed + (IsShared ? 0 : Owner.NetId) + hash(event.Id.Entry)`.
    Most single-player examples use `net_id=1`.
    """

    return uint32(net_id + deterministic_hash_code(event_id))


def player_offset_for_name(name: str, net_id: int = 1) -> int:
    """Return the 32-bit player RNG-name offset for a player's net id.

    Player.InitializeSeed seeds PlayerRngSet with
    `hash(runSeedString) + Owner.NetId`; PlayerRngSet then adds the
    snake-case RNG type hash.
    """

    return uint32(net_id + rng_offset_for_name(name))


def normalize_offset(offset: int | str) -> int:
    if isinstance(offset, str):
        return rng_offset_for_name(offset)
    return uint32(offset)


def derived_seed(base_seed: int, offset: int | str) -> int:
    """Return `(base_seed + offset) mod 2^32`."""

    return uint32(base_seed + normalize_offset(offset))


def abs_seed_from_i32(seed: int) -> int:
    if seed == INT_MIN:
        return INT_MAX
    return abs(seed)


def abs_seed_from_u32(seed: int) -> int:
    return abs_seed_from_i32(u32_to_i32(seed))


def derived_seeds_for_abs_seed(abs_seed: int) -> tuple[int, ...]:
    if not 0 <= abs_seed <= MBIG:
        raise ValueError("abs_seed out of range")
    if abs_seed == 0:
        return (0,)
    if abs_seed == MBIG:
        return (0x7FFFFFFF, 0x80000000, 0x80000001)
    return (abs_seed, uint32(-abs_seed))


class DotNetCompatRandom:
    """Compatibility PRNG used by `new System.Random(int seed)`."""

    def __init__(self, seed: int) -> None:
        self._seed_array = [0] * 56
        subtraction = abs_seed_from_i32(int32(seed))
        self._init_from_subtraction(subtraction)

    @classmethod
    def from_abs_seed(cls, abs_seed: int) -> DotNetCompatRandom:
        obj = cls.__new__(cls)
        obj._seed_array = [0] * 56
        obj._init_from_subtraction(abs_seed)
        return obj

    def _init_from_subtraction(self, subtraction: int) -> None:
        mj = int32(MSEED - subtraction)
        self._seed_array[55] = mj
        mk = 1
        for i in range(1, 55):
            ii = (21 * i) % 55
            self._seed_array[ii] = mk
            mk = int32(mj - mk)
            if mk < 0:
                mk = int32(mk + MBIG)
            mj = self._seed_array[ii]
        for _ in range(1, 5):
            for i in range(1, 56):
                self._seed_array[i] = int32(
                    self._seed_array[i] - self._seed_array[1 + (i + 30) % 55]
                )
                if self._seed_array[i] < 0:
                    self._seed_array[i] = int32(self._seed_array[i] + MBIG)
        self._inext = 0
        self._inextp = 21

    def internal_sample(self) -> int:
        loc_inext = self._inext + 1
        if loc_inext >= 56:
            loc_inext = 1

        loc_inextp = self._inextp + 1
        if loc_inextp >= 56:
            loc_inextp = 1

        ret_val = int32(self._seed_array[loc_inext] - self._seed_array[loc_inextp])
        if ret_val == MBIG:
            ret_val -= 1
        if ret_val < 0:
            ret_val = int32(ret_val + MBIG)

        self._seed_array[loc_inext] = ret_val
        self._inext = loc_inext
        self._inextp = loc_inextp
        return ret_val

    def next_int(self, max_exclusive: int = INT_MAX) -> int:
        return next_int_from_sample(self.internal_sample(), 0, max_exclusive)

    def next_int_range(self, min_inclusive: int, max_exclusive: int) -> int:
        return next_int_from_sample(self.internal_sample(), min_inclusive, max_exclusive)

    def next_float(self, min_value: float = 0.0, max_value: float = 1.0) -> float:
        return next_float_from_sample(self.internal_sample(), min_value, max_value)


@lru_cache(maxsize=None)
def internal_sample_from_abs_seed(abs_seed: int, counter: int) -> int:
    rng = DotNetCompatRandom.from_abs_seed(abs_seed)
    for _ in range(counter):
        rng.internal_sample()
    return rng.internal_sample()


@lru_cache(maxsize=None)
def sample_affine(counter: int) -> tuple[int, int]:
    beta = internal_sample_from_abs_seed(0, counter)
    one = internal_sample_from_abs_seed(1, counter)
    alpha = (one - beta) % MBIG
    if alpha == 0:
        raise RuntimeError(f"Unexpected non-invertible sample coefficient at counter {counter}")
    return alpha, beta


def internal_sample_from_derived_u32(seed: int, counter: int) -> int:
    abs_seed = abs_seed_from_u32(seed)
    if abs_seed == MBIG:
        return internal_sample_from_abs_seed(MBIG, counter)
    alpha, beta = sample_affine(counter)
    return (alpha * abs_seed + beta) % MBIG


def next_int_from_sample(sample: int, min_inclusive: int, max_exclusive: int) -> int:
    range_size = max_exclusive - min_inclusive
    if range_size <= 0:
        raise ValueError("next_int range must be positive")
    if range_size > INT_MAX:
        raise NotImplementedError("next_int ranges larger than int.MaxValue are not supported")
    return int((sample * (1.0 / MBIG)) * range_size) + min_inclusive


def next_float_from_sample(sample: int, min_value: float, max_value: float) -> float:
    value = (sample * (1.0 / MBIG)) * (max_value - min_value) + min_value
    return to_single(value)


def call_next_int(base_seed: int, offset: int | str, counter: int, max_exclusive: int = INT_MAX) -> int:
    seed = derived_seed(base_seed, offset)
    sample = internal_sample_from_derived_u32(seed, counter)
    return next_int_from_sample(sample, 0, max_exclusive)
