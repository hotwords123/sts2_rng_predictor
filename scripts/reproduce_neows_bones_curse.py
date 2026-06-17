#!/usr/bin/env python3
"""Reproduce Neow's Bones curse conditional RNG examples."""

from __future__ import annotations

import argparse
import json
import random
import re
from collections import Counter
from pathlib import Path

from sts2_rng_predictor import (
    IntCall,
    IntObservation,
    IntTarget,
    event_offset_for_id,
    predict_same_counter_fast,
)
from sts2_rng_predictor.config import load_local_source_config
from sts2_rng_predictor.rng_compat import call_next_int, rng_offset_for_name


CONFIG = load_local_source_config(Path(__file__).resolve().parents[1] / ".env")
CARD_DIR = CONFIG.code_root / "MegaCrit" / "sts2" / "Core" / "Models" / "Cards"
POOL_FILE = CONFIG.code_root / "MegaCrit" / "sts2" / "Core" / "Models" / "CardPools" / "CurseCardPool.cs"
LOC_FILE = CONFIG.localization_root / "eng" / "cards.json"

ACTS = {"underdocks": 0, "overgrowth": 1}
NEOW_CURSE_RELICS = [
    "CursedPearl",
    "HeftyTablet",
    "LargeCapsule",
    "LeafyPoultice",
    "NeowsBones",
    "PrecariousShears",
    "SilkenTress",
    "SilverCrucible",
]


def pascal_to_id(name: str) -> str:
    return re.sub(r"(?<=[A-Za-z0-9])(?=[A-Z])", "_", name).upper()


def load_titles() -> dict[str, str]:
    raw = json.loads(LOC_FILE.read_text(encoding="utf-8"))
    return {key.removesuffix(".title"): value for key, value in raw.items() if key.endswith(".title")}


def curse_pool_order() -> list[str]:
    text = POOL_FILE.read_text(encoding="utf-8")
    return re.findall(r"ModelDb\.Card<([A-Za-z0-9_]+)>\(\)", text)


def can_be_generated_by_modifiers(card_class: str) -> bool:
    text = (CARD_DIR / f"{card_class}.cs").read_text(encoding="utf-8")
    return "CanBeGeneratedByModifiers => false" not in text


def available_curses() -> list[str]:
    # Source: NeowsBones.AfterObtained filters CurseCardPool by
    # CanBeGeneratedByModifiers, then orders by card Id before NextItem.
    return sorted(
        (card for card in curse_pool_order() if can_be_generated_by_modifiers(card)),
        key=pascal_to_id,
    )


def card_title(card_class: str, titles: dict[str, str]) -> str:
    return titles.get(pascal_to_id(card_class), card_class)


def format_probability(probability: float) -> str:
    percent = probability * 100
    if 0 < percent < 0.000001:
        return f"{percent:11.3e}%"
    return f"{probability:11.6%}"


def act_observation(act_name: str) -> IntObservation:
    # StartRunLobby.BeginRunLocally uses `new Rng(hash(seed))`, then
    # ActModel.GetRandomList calls NextBool() to decide whether act 1 is
    # Underdocks instead of Overgrowth.
    return IntObservation(0, 0, IntCall(0, 2), ACTS[act_name], ACTS[act_name])


def neows_bones_option_observation() -> IntObservation:
    # Neow.GenerateInitialOptions first rolls one curse-pool option. The
    # resulting option is appended as the third visible choice.
    relic_index = NEOW_CURSE_RELICS.index("NeowsBones")
    return IntObservation(
        event_offset_for_id("NEOW"),
        0,
        IntCall(0, len(NEOW_CURSE_RELICS)),
        relic_index,
        relic_index,
    )


def neows_bones_curse_target(curse_count: int) -> IntTarget:
    # NeowsBones.AfterObtained uses RunState.Rng.Niche.NextItem on the
    # available curse list. The first and only curse is counter 0.
    return IntTarget("niche", 0, IntCall(0, curse_count))


def distribution_for(act_name: str, curse_count: int):
    return predict_same_counter_fast(
        [act_observation(act_name), neows_bones_option_observation()],
        neows_bones_curse_target(curse_count),
        max_target_buckets=curse_count,
    )


def print_distribution(title: str, result, curses: list[str], titles: dict[str, str]) -> None:
    print(title)
    print(f"  conditional seed count: {result.total_count:,}")
    for index, probability in sorted(result.distribution.items(), key=lambda item: item[1], reverse=True):
        curse = curses[index]
        print(f"  {card_title(curse, titles):18s} {format_probability(probability)}  [{curse}]")
    print()


def _sample_distributions(sample_count: int, seed: int, curse_count: int) -> None:
    rng = random.Random(seed)
    neow_offset = event_offset_for_id("NEOW")
    niche_offset = rng_offset_for_name("niche")
    bones_index = NEOW_CURSE_RELICS.index("NeowsBones")
    counts = {act: Counter() for act in ACTS}
    totals = {act: 0 for act in ACTS}

    for _ in range(sample_count):
        base_seed = rng.randrange(2**32)
        for act_name, act_value in ACTS.items():
            if call_next_int(base_seed, 0, 0, 2) != act_value:
                continue
            if call_next_int(base_seed, neow_offset, 0, len(NEOW_CURSE_RELICS)) != bones_index:
                continue
            curse = call_next_int(base_seed, niche_offset, 0, curse_count)
            counts[act_name][curse] += 1
            totals[act_name] += 1

    print(f"Monte Carlo check ({sample_count:,} random 32-bit seeds, rng seed {seed})")
    for act_name in ACTS:
        print(f"  {act_name}: matched {totals[act_name]:,}")
        if totals[act_name] == 0:
            continue
        compact = ", ".join(
            f"{index}:{count / totals[act_name]:.2%}"
            for index, count in counts[act_name].most_common()
        )
        print(f"    {compact}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--sample-check",
        type=int,
        default=0,
        help="run a Monte Carlo check with this many random 32-bit base seeds",
    )
    parser.add_argument(
        "--sample-seed",
        type=int,
        default=1,
        help="PRNG seed for --sample-check",
    )
    args = parser.parse_args()

    titles = load_titles()
    curses = available_curses()
    neow_offset = event_offset_for_id("NEOW")
    niche_offset = rng_offset_for_name("niche")

    print("Offsets")
    print("  act roll:        0 (new Rng(hash(seed)))")
    print(f"  NEOW event:      {neow_offset} (1 + hash('NEOW'))")
    print(f"  niche:           {niche_offset} (hash('niche'))")
    print()
    print(f"Neow curse option: NeowsBones index {NEOW_CURSE_RELICS.index('NeowsBones')} of {len(NEOW_CURSE_RELICS)}")
    print(f"Available curses:  {len(curses)}")
    print("Weighting: exact over all 32-bit values after StringHelper.GetDeterministicHashCode(seed).")
    print()
    print("Available curse order")
    for index, curse in enumerate(curses):
        print(f"  {index}: {card_title(curse, titles)} [{curse}]")
    print()

    for act in ("underdocks", "overgrowth"):
        result = distribution_for(act, len(curses))
        print_distribution(f"Neow's Bones curse, conditioned on {act} and Neow's Bones option", result, curses, titles)

    if args.sample_check:
        _sample_distributions(args.sample_check, args.sample_seed, len(curses))


if __name__ == "__main__":
    main()
