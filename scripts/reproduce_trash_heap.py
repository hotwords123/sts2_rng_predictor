#!/usr/bin/env python3
"""Reproduce the Trash Heap conditional RNG examples."""

from __future__ import annotations

import argparse
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
from sts2_rng_predictor.rng_compat import call_next_int
from sts2_rng_predictor.source_inspection import model_db_references


CONFIG = load_local_source_config(Path(__file__).resolve().parents[1] / ".env")
TRASH_HEAP_FILE = CONFIG.code_root / "MegaCrit" / "sts2" / "Core" / "Models" / "Events" / "TrashHeap.cs"

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


def _array_body(source: str, property_name: str) -> str:
    match = re.search(
        rf"private static {property_name}Model\[\] {property_name}s => .*?"
        rf"new {property_name}Model\[[^\]]*\]\s*\{{(?P<body>.*?)\}};",
        source,
        re.DOTALL,
    )
    if not match:
        raise ValueError(f"Could not parse {property_name}s array from {TRASH_HEAP_FILE}")
    return match.group("body")


def trash_heap_cards() -> list[str]:
    text = TRASH_HEAP_FILE.read_text(encoding="utf-8")
    return model_db_references(_array_body(text, "Card"), "Card")


def trash_heap_relics() -> list[str]:
    text = TRASH_HEAP_FILE.read_text(encoding="utf-8")
    return model_db_references(_array_body(text, "Relic"), "Relic")


def act_observation(act_name: str) -> IntObservation:
    # StartRunLobby.BeginRunLocally uses `new Rng(hash(seed))`, then
    # ActModel.GetRandomList calls NextBool() to decide whether act 1 is
    # Underdocks instead of Overgrowth.
    return IntObservation(0, 0, IntCall(0, 2), ACTS[act_name], ACTS[act_name])


def neow_curse_observation(relic_index: int, net_id: int) -> IntObservation:
    # Neow is an event RNG: runSeed + NetId + hash("NEOW"). The first call is
    # NextItem(CurseOptions), whose source order is NEOW_CURSE_RELICS.
    return IntObservation(
        event_offset_for_id("NEOW", net_id),
        0,
        IntCall(0, len(NEOW_CURSE_RELICS)),
        relic_index,
        relic_index,
    )


def trash_heap_target(card_count: int, net_id: int) -> IntTarget:
    return IntTarget(event_offset_for_id("TRASH_HEAP", net_id), 0, IntCall(0, card_count))


def predict_trash_heap(observations: list[IntObservation], card_count: int, net_id: int):
    return predict_same_counter_fast(
        observations,
        trash_heap_target(card_count, net_id),
        max_target_buckets=card_count,
    )


def print_card_distribution(title: str, result, cards: list[str], min_probability: float = 0.0) -> None:
    print(title)
    print(f"  conditional seed count: {result.total_count:,}")
    for index, probability in sorted(result.distribution.items(), key=lambda item: item[1], reverse=True):
        if probability < min_probability:
            continue
        print(f"  {cards[index]:18s} {probability:9.4%}")
    print()


def print_relic_mapping(cards: list[str], relics: list[str]) -> None:
    print("Trash Heap card -> relic mapping")
    for index, card in enumerate(cards):
        relic = relics[index // 2]
        print(f"  {card:18s} -> {relic}")
    print()


def _sample_distributions(sample_count: int, act_name: str, card_count: int, seed: int, net_id: int) -> None:
    rng = random.Random(seed)
    act_value = ACTS[act_name]
    neow_offset = event_offset_for_id("NEOW", net_id)
    trash_offset = event_offset_for_id("TRASH_HEAP", net_id)
    base_counts: Counter[int] = Counter()
    base_total = 0
    relic_counts = [Counter() for _ in NEOW_CURSE_RELICS]
    relic_totals = [0 for _ in NEOW_CURSE_RELICS]

    for _ in range(sample_count):
        base_seed = rng.randrange(2**32)
        if call_next_int(base_seed, 0, 0, 2) != act_value:
            continue
        trash_card = call_next_int(base_seed, trash_offset, 0, card_count)
        base_counts[trash_card] += 1
        base_total += 1

        neow_relic = call_next_int(base_seed, neow_offset, 0, len(NEOW_CURSE_RELICS))
        relic_counts[neow_relic][trash_card] += 1
        relic_totals[neow_relic] += 1

    print(f"Monte Carlo check ({sample_count:,} random 32-bit seeds, rng seed {seed})")
    print(f"  matched {act_name}: {base_total:,}")
    print("  act-only:")
    for index, count in base_counts.most_common():
        print(f"    {index}: {count / base_total:9.4%} ({count:,})")
    print("  act + Neow curse relic:")
    for relic_index, total in enumerate(relic_totals):
        if total == 0:
            continue
        compact = ", ".join(
            f"{index}:{count / total:.2%}"
            for index, count in relic_counts[relic_index].most_common()
        )
        print(f"    {NEOW_CURSE_RELICS[relic_index]:18s} {total:8,d}  {compact}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--act",
        choices=sorted(ACTS),
        default="underdocks",
        help="act observation to condition on",
    )
    parser.add_argument(
        "--min-probability",
        type=float,
        default=0.0,
        help="hide card buckets below this probability, e.g. 0.001",
    )
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
        help="mark the modeled run as multiplayer; Trash Heap's fixed card array is not player-count filtered",
    )
    args = parser.parse_args()
    if args.net_id < 0:
        raise ValueError("--net-id must be non-negative")

    cards = trash_heap_cards()
    relics = trash_heap_relics()
    if len(cards) != 10 or len(relics) != 5:
        raise ValueError(f"Expected 10 cards and 5 relics, got {len(cards)} cards and {len(relics)} relics")

    print("Offsets")
    print(f"  player NetId:    {args.net_id}")
    print(f"  mode:            {'multiplayer' if args.multiplayer else 'single-player'}")
    print("  act roll:        0 (new Rng(hash(seed)))")
    print(f"  NEOW event:      {event_offset_for_id('NEOW', args.net_id)} (NetId + hash('NEOW'))")
    print(f"  TRASH_HEAP event:{event_offset_for_id('TRASH_HEAP', args.net_id)} (NetId + hash('TRASH_HEAP'))")
    print()
    print("Source arrays")
    print(f"  cards:  {', '.join(cards)}")
    print(f"  relics: {', '.join(relics)}")
    print("  note:   Trash Heap uses fixed event arrays, not player-count-filtered card pools")
    print("Weighting: exact over all 32-bit run seeds in the current same-counter model.")
    print("Act observation assumes Underdocks is revealed and not single-player first-time forced.")
    print()

    print_relic_mapping(cards, relics)

    act_obs = act_observation(args.act)
    base_result = predict_trash_heap([act_obs], len(cards), args.net_id)
    print_card_distribution(f"Trash Heap random card, conditioned on {args.act}", base_result, cards, args.min_probability)

    print(f"Trash Heap random card, conditioned on {args.act} and Neow curse pool relic")
    for relic_index, relic in enumerate(NEOW_CURSE_RELICS):
        result = predict_trash_heap([act_obs, neow_curse_observation(relic_index, args.net_id)], len(cards), args.net_id)
        compact = ", ".join(
            f"{cards[index]} {probability:.2%}"
            for index, probability in sorted(result.distribution.items(), key=lambda item: item[1], reverse=True)
            if probability >= args.min_probability
        )
        print(f"  {relic:18s} {result.total_count:12,d}  {compact}")

    print()
    print("Neow curse pool order")
    for index, relic in enumerate(NEOW_CURSE_RELICS):
        print(f"  {index}: {relic}")

    if args.sample_check:
        print()
        _sample_distributions(args.sample_check, args.act, len(cards), args.sample_seed, args.net_id)


if __name__ == "__main__":
    main()
