"""Helpers for reading local decompiled STS2 source and localization files."""

from __future__ import annotations

import json
import re
from pathlib import Path


def pascal_to_id(name: str) -> str:
    return re.sub(r"(?<=[A-Za-z0-9])(?=[A-Z])", "_", name).upper()


def load_titles(localization_root: Path, category: str = "cards", lang: str = "eng") -> dict[str, str]:
    raw = json.loads((localization_root / lang / f"{category}.json").read_text(encoding="utf-8"))
    return {key.removesuffix(".title"): value for key, value in raw.items() if key.endswith(".title")}


def localized_title(model_class: str, titles: dict[str, str]) -> str:
    return titles.get(pascal_to_id(model_class), model_class)


def model_db_references(source: str, model_type: str) -> list[str]:
    return re.findall(rf"ModelDb\.{model_type}<([A-Za-z0-9_]+)>\(\)", source)


def card_pool_order(pool_dir: Path, pool_class: str) -> list[str]:
    text = (pool_dir / f"{pool_class}.cs").read_text(encoding="utf-8")
    return model_db_references(text, "Card")


def card_rarity(card_dir: Path, card_class: str) -> str:
    text = (card_dir / f"{card_class}.cs").read_text(encoding="utf-8")
    match = re.search(r"CardRarity\.([A-Za-z0-9_]+)", text)
    if not match:
        raise ValueError(f"Could not parse rarity for {card_class}")
    return match.group(1)


def card_multiplayer_constraint(card_dir: Path, card_class: str) -> str:
    text = (card_dir / f"{card_class}.cs").read_text(encoding="utf-8")
    if "CardMultiplayerConstraint.MultiplayerOnly" in text:
        return "MultiplayerOnly"
    if "CardMultiplayerConstraint.SingleplayerOnly" in text:
        return "SingleplayerOnly"
    return "None"


def card_allowed_for_mode(card_dir: Path, card_class: str, multiplayer: bool) -> bool:
    constraint = card_multiplayer_constraint(card_dir, card_class)
    if multiplayer:
        return constraint != "SingleplayerOnly"
    return constraint != "MultiplayerOnly"


def can_be_generated_by_modifiers(card_dir: Path, card_class: str) -> bool:
    text = (card_dir / f"{card_class}.cs").read_text(encoding="utf-8")
    return "CanBeGeneratedByModifiers => false" not in text
