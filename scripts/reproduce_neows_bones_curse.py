#!/usr/bin/env python3
"""Reproduce Neow's Bones curse conditional RNG examples."""

from __future__ import annotations

import argparse
import random
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
from sts2_rng_predictor.source_inspection import (
    can_be_generated_by_modifiers,
    card_allowed_for_mode,
    load_titles,
    localized_title,
    model_db_references,
    pascal_to_id,
    relic_allowed_for_mode,
    relic_option_references_in_property,
)


CONFIG = load_local_source_config(Path(__file__).resolve().parents[1] / ".env")
CARD_DIR = CONFIG.code_root / "MegaCrit" / "sts2" / "Core" / "Models" / "Cards"
RELIC_DIR = CONFIG.code_root / "MegaCrit" / "sts2" / "Core" / "Models" / "Relics"
NEOW_FILE = CONFIG.code_root / "MegaCrit" / "sts2" / "Core" / "Models" / "Events" / "Neow.cs"
POOL_FILE = CONFIG.code_root / "MegaCrit" / "sts2" / "Core" / "Models" / "CardPools" / "CurseCardPool.cs"

ACTS = {"underdocks": 0, "overgrowth": 1}


def neow_curse_relics(multiplayer: bool) -> list[str]:
    text = NEOW_FILE.read_text(encoding="utf-8")
    return [
        relic
        for relic in relic_option_references_in_property(text, "CurseOptions")
        if relic_allowed_for_mode(RELIC_DIR, relic, multiplayer)
    ]


def curse_pool_order() -> list[str]:
    text = POOL_FILE.read_text(encoding="utf-8")
    return model_db_references(text, "Card")


def available_curses(multiplayer: bool) -> list[str]:
    # Source: NeowsBones.AfterObtained filters CurseCardPool by
    # CanBeGeneratedByModifiers, then orders by card Id before NextItem.
    return sorted(
        (
            card
            for card in curse_pool_order()
            if can_be_generated_by_modifiers(CARD_DIR, card)
            and card_allowed_for_mode(CARD_DIR, card, multiplayer)
        ),
        key=pascal_to_id,
    )


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


def neows_bones_option_observation(neow_curse_relics: list[str], net_id: int) -> IntObservation:
    # Neow.GenerateInitialOptions first rolls one curse-pool option. The
    # resulting option is appended as the third visible choice after
    # IsAllowedAtNeow filtering.
    relic_index = neow_curse_relics.index("NeowsBones")
    return IntObservation(
        event_offset_for_id("NEOW", net_id),
        0,
        IntCall(0, len(neow_curse_relics)),
        relic_index,
        relic_index,
    )


def neows_bones_curse_target(curse_count: int) -> IntTarget:
    # NeowsBones.AfterObtained uses RunState.Rng.Niche.NextItem on the
    # available curse list. The first and only curse is counter 0.
    return IntTarget("niche", 0, IntCall(0, curse_count))


def distribution_for(act_name: str, curse_count: int, neow_curse_relics: list[str], net_id: int):
    return predict_same_counter_fast(
        [act_observation(act_name), neows_bones_option_observation(neow_curse_relics, net_id)],
        neows_bones_curse_target(curse_count),
        max_target_buckets=curse_count,
    )


def print_distribution(title: str, result, curses: list[str], titles: dict[str, str]) -> None:
    print(title)
    print(f"  conditional seed count: {result.total_count:,}")
    for index, probability in sorted(result.distribution.items(), key=lambda item: item[1], reverse=True):
        curse = curses[index]
        print(f"  {localized_title(curse, titles):18s} {format_probability(probability)}  [{curse}]")
    print()


def _sample_distributions(
    sample_count: int,
    seed: int,
    curse_count: int,
    neow_curse_relics: list[str],
    net_id: int,
) -> None:
    rng = random.Random(seed)
    neow_offset = event_offset_for_id("NEOW", net_id)
    niche_offset = rng_offset_for_name("niche")
    bones_index = neow_curse_relics.index("NeowsBones")
    counts = {act: Counter() for act in ACTS}
    totals = {act: 0 for act in ACTS}

    for _ in range(sample_count):
        base_seed = rng.randrange(2**32)
        for act_name, act_value in ACTS.items():
            if call_next_int(base_seed, 0, 0, 2) != act_value:
                continue
            if call_next_int(base_seed, neow_offset, 0, len(neow_curse_relics)) != bones_index:
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
    parser.add_argument(
        "--net-id",
        type=int,
        default=1,
        help="player NetId to model; single-player uses 1",
    )
    parser.add_argument(
        "--multiplayer",
        action="store_true",
        help="use multiplayer card filtering; default is single-player filtering",
    )
    args = parser.parse_args()
    if args.net_id < 0:
        raise ValueError("--net-id must be non-negative")

    titles = load_titles(CONFIG.localization_root)
    curses = available_curses(args.multiplayer)
    curse_relics = neow_curse_relics(args.multiplayer)
    neow_offset = event_offset_for_id("NEOW", args.net_id)
    niche_offset = rng_offset_for_name("niche")

    print("Offsets")
    print(f"  player NetId:    {args.net_id}")
    print("  act roll:        0 (new Rng(hash(seed)))")
    print(f"  NEOW event:      {neow_offset} (NetId + hash('NEOW'))")
    print(f"  niche:           {niche_offset} (hash('niche'))")
    print()
    print(f"Neow curse option: NeowsBones index {curse_relics.index('NeowsBones')} of {len(curse_relics)}")
    print(f"Mode:              {'multiplayer' if args.multiplayer else 'single-player'}")
    print(f"Available curses:  {len(curses)}")
    print("Weighting: exact over all 32-bit values after StringHelper.GetDeterministicHashCode(seed).")
    print("Act observation assumes Underdocks is revealed and not single-player first-time forced.")
    print()
    print("Neow curse relic order")
    for index, relic in enumerate(curse_relics):
        print(f"  {index}: {relic}")
    print()

    print("Available curse order")
    for index, curse in enumerate(curses):
        print(f"  {index}: {localized_title(curse, titles)} [{curse}]")
    print()

    for act in ("underdocks", "overgrowth"):
        result = distribution_for(act, len(curses), curse_relics, args.net_id)
        print_distribution(f"Neow's Bones curse, conditioned on {act} and Neow's Bones option", result, curses, titles)

    if args.sample_check:
        _sample_distributions(args.sample_check, args.sample_seed, len(curses), curse_relics, args.net_id)


if __name__ == "__main__":
    main()
