#!/usr/bin/env python3
"""Reproduce the Leafy Poultice / Hefty Tablet conditional RNG examples."""

from __future__ import annotations

import json
import re
import argparse
from pathlib import Path

from sts2_rng_predictor import IntCall, IntObservation, IntTarget, predict_same_counter_fast
from sts2_rng_predictor.config import load_local_source_config
from sts2_rng_predictor.rng_compat import (
    deterministic_hash_code,
    normalize_offset,
    uint32,
)


CONFIG = load_local_source_config(Path(__file__).resolve().parents[1] / ".env")
CARD_DIR = CONFIG.code_root / "MegaCrit" / "sts2" / "Core" / "Models" / "Cards"
POOL_DIR = CONFIG.code_root / "MegaCrit" / "sts2" / "Core" / "Models" / "CardPools"
LOC_FILE = CONFIG.localization_root / "eng" / "cards.json"

ACTS = {"underdocks": 0, "overgrowth": 1}
NEOW_CURSE_INDEX = {"hefty_tablet": 1, "leafy_poultice": 3}
CHARACTER_POOLS = {
    "ironclad": "IroncladCardPool",
    "silent": "SilentCardPool",
    "defect": "DefectCardPool",
    "necrobinder": "NecrobinderCardPool",
    "regent": "RegentCardPool",
}


def pascal_to_id(name: str) -> str:
    return re.sub(r"(?<=[A-Za-z0-9])(?=[A-Z])", "_", name).upper()


def load_titles() -> dict[str, str]:
    raw = json.loads(LOC_FILE.read_text(encoding="utf-8"))
    return {key.removesuffix(".title"): value for key, value in raw.items() if key.endswith(".title")}


def card_pool_order(character: str) -> list[str]:
    pool = CHARACTER_POOLS[character]
    text = (POOL_DIR / f"{pool}.cs").read_text(encoding="utf-8")
    return re.findall(r"ModelDb\.Card<([A-Za-z0-9_]+)>\(\)", text)


def card_rarity(card_class: str) -> str:
    text = (CARD_DIR / f"{card_class}.cs").read_text(encoding="utf-8")
    match = re.search(r"CardRarity\.([A-Za-z0-9_]+)", text)
    if not match:
        raise ValueError(f"Could not parse rarity for {card_class}")
    return match.group(1)


def is_singleplayer_excluded(card_class: str) -> bool:
    text = (CARD_DIR / f"{card_class}.cs").read_text(encoding="utf-8")
    return "CardMultiplayerConstraint.MultiplayerOnly" in text


def card_title(card_class: str, titles: dict[str, str]) -> str:
    return titles.get(pascal_to_id(card_class), card_class)


def leafy_transform_options(character: str) -> list[str]:
    # Source: CardFactory.GetFilteredTransformationOptions for an Ironclad Basic
    # Strike/Defend outside combat. Keep the pool order from IroncladCardPool.
    return [
        card
        for card in card_pool_order(character)
        if card_rarity(card) in {"Common", "Uncommon", "Rare"}
        and not is_singleplayer_excluded(card)
    ]


def hefty_rare_options(character: str) -> list[str]:
    # Source: HeftyTablet -> CardFactory.CreateForReward(... Uniform,
    # c.Rarity == Rare, NoUpgradeRoll). The first option uses the full rare list;
    # later options blacklist earlier selected cards.
    return [
        card
        for card in card_pool_order(character)
        if card_rarity(card) == "Rare" and not is_singleplayer_excluded(card)
    ]


def distribution_for(act_name: str, neow_choice: str, target_offset: int | str, target_size: int, target_counter: int = 0):
    result = predict_same_counter_fast(
        [
            IntObservation(0, 0, IntCall(0, 2), ACTS[act_name], ACTS[act_name]),
            IntObservation(
                uint32(1 + deterministic_hash_code("NEOW")),
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
        print(f"  {card_title(options[index], titles):24s} {probability:9.4%}  [{options[index]}]")
    print()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--character",
        choices=sorted(CHARACTER_POOLS),
        default="ironclad",
        help="character card pool to use",
    )
    args = parser.parse_args()

    titles = load_titles()
    leafy = leafy_transform_options(args.character)
    hefty = hefty_rare_options(args.character)
    rewards_offset = uint32(1 + normalize_offset("rewards"))
    transformations_offset = uint32(1 + normalize_offset("transformations"))

    print("Offsets")
    print(f"  NEOW event:       {uint32(1 + deterministic_hash_code('NEOW'))} (1 + hash('NEOW'))")
    print(f"  rewards:          {rewards_offset} (1 + hash('rewards'))")
    print(f"  transformations:  {transformations_offset} (1 + hash('transformations'))")
    print()
    print(f"Character: {args.character}")
    print(f"Leafy transform option count: {len(leafy)}")
    print(f"Hefty first rare option count: {len(hefty)}")
    print("Weighting: exact over all 32-bit values after StringHelper.GetDeterministicHashCode(seed).")
    print()

    for act in ("underdocks", "overgrowth"):
        leafy_result = distribution_for(act, "leafy_poultice", transformations_offset, len(leafy), 0)
        print_distribution(f"Leafy Poultice first transform, {act}", leafy_result, leafy, titles)

    for act in ("underdocks", "overgrowth"):
        hefty_result = distribution_for(act, "hefty_tablet", rewards_offset, len(hefty), 0)
        print_distribution(f"Hefty Tablet first rare option, {act}", hefty_result, hefty, titles)


if __name__ == "__main__":
    main()
