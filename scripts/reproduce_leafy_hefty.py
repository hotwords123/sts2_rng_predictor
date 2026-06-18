#!/usr/bin/env python3
"""Reproduce the Leafy Poultice / Hefty Tablet conditional RNG examples."""

import argparse
from pathlib import Path

from sts2_rng_predictor import (
    IntCall,
    IntObservation,
    IntTarget,
    event_offset_for_id,
    player_offset_for_name,
    predict_same_counter_fast,
)
from sts2_rng_predictor.config import load_local_source_config
from sts2_rng_predictor.source_inspection import (
    card_allowed_for_mode,
    card_pool_order,
    card_rarity,
    load_titles,
    localized_title,
)


CONFIG = load_local_source_config(Path(__file__).resolve().parents[1] / ".env")
CARD_DIR = CONFIG.code_root / "MegaCrit" / "sts2" / "Core" / "Models" / "Cards"
POOL_DIR = CONFIG.code_root / "MegaCrit" / "sts2" / "Core" / "Models" / "CardPools"

ACTS = {"underdocks": 0, "overgrowth": 1}
NEOW_CURSE_INDEX = {"hefty_tablet": 1, "leafy_poultice": 3}
CHARACTER_POOLS = {
    "ironclad": "IroncladCardPool",
    "silent": "SilentCardPool",
    "defect": "DefectCardPool",
    "necrobinder": "NecrobinderCardPool",
    "regent": "RegentCardPool",
}


def character_card_pool_order(character: str) -> list[str]:
    pool = CHARACTER_POOLS[character]
    return card_pool_order(POOL_DIR, pool)


def leafy_transform_options(character: str, multiplayer: bool) -> list[str]:
    # Source: CardFactory.GetFilteredTransformationOptions for an Ironclad Basic
    # Strike/Defend outside combat. Keep the pool order from IroncladCardPool.
    return [
        card
        for card in character_card_pool_order(character)
        if card_rarity(CARD_DIR, card) in {"Common", "Uncommon", "Rare"}
        and card_allowed_for_mode(CARD_DIR, card, multiplayer)
    ]


def hefty_rare_options(character: str, multiplayer: bool) -> list[str]:
    # Source: HeftyTablet -> CardFactory.CreateForReward(... Uniform,
    # c.Rarity == Rare, NoUpgradeRoll). The first option uses the full rare list;
    # later options blacklist earlier selected cards.
    return [
        card
        for card in character_card_pool_order(character)
        if card_rarity(CARD_DIR, card) == "Rare" and card_allowed_for_mode(CARD_DIR, card, multiplayer)
    ]


def distribution_for(
    act_name: str,
    neow_choice: str,
    net_id: int,
    target_offset: int,
    target_size: int,
    target_counter: int = 0,
):
    result = predict_same_counter_fast(
        [
            IntObservation(0, 0, IntCall(0, 2), ACTS[act_name], ACTS[act_name]),
            IntObservation(
                event_offset_for_id("NEOW", net_id),
                0,
                IntCall(0, 8),
                NEOW_CURSE_INDEX[neow_choice],
                NEOW_CURSE_INDEX[neow_choice],
            ),
        ],
        IntTarget(target_offset, target_counter, IntCall(0, target_size)),
        max_target_buckets=target_size,
    )
    return result


def print_distribution(title: str, result, options: list[str], titles: dict[str, str]) -> None:
    print(title)
    print(f"  conditional seed count: {result.total_count:,}")
    for index, probability in sorted(result.distribution.items(), key=lambda item: item[1], reverse=True):
        print(f"  {localized_title(options[index], titles):24s} {probability:9.4%}  [{options[index]}]")
    print()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--character",
        choices=sorted(CHARACTER_POOLS),
        default="ironclad",
        help="character card pool to use",
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
    leafy = leafy_transform_options(args.character, args.multiplayer)
    hefty = hefty_rare_options(args.character, args.multiplayer)
    neow_offset = event_offset_for_id("NEOW", args.net_id)
    rewards_offset = player_offset_for_name("rewards", args.net_id)
    transformations_offset = player_offset_for_name("transformations", args.net_id)

    print("Offsets")
    print(f"  player NetId:     {args.net_id}")
    print(f"  NEOW event:       {neow_offset} (NetId + hash('NEOW'))")
    print(f"  rewards:          {rewards_offset} (NetId + hash('rewards'))")
    print(f"  transformations:  {transformations_offset} (NetId + hash('transformations'))")
    print()
    print(f"Character: {args.character}")
    print(f"Mode: {'multiplayer' if args.multiplayer else 'single-player'}")
    print(f"Leafy transform option count: {len(leafy)}")
    print(f"Hefty first rare option count: {len(hefty)}")
    print("Weighting: exact over all 32-bit values after StringHelper.GetDeterministicHashCode(seed).")
    print("Act observation assumes Underdocks is revealed and not single-player first-time forced.")
    print()

    for act in ("underdocks", "overgrowth"):
        leafy_result = distribution_for(act, "leafy_poultice", args.net_id, transformations_offset, len(leafy), 0)
        print_distribution(f"Leafy Poultice first transform, {act}", leafy_result, leafy, titles)

    for act in ("underdocks", "overgrowth"):
        hefty_result = distribution_for(act, "hefty_tablet", args.net_id, rewards_offset, len(hefty), 0)
        print_distribution(f"Hefty Tablet first rare option, {act}", hefty_result, hefty, titles)


if __name__ == "__main__":
    main()
