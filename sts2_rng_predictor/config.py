"""Configuration helpers for local source-inspection examples."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values


ENV_FILE_VAR = "STS2_RNG_PREDICTOR_ENV"


@dataclass(frozen=True)
class LocalSourceConfig:
    code_root: Path
    localization_root: Path


def load_local_source_config(env_file: Path | None = None) -> LocalSourceConfig:
    env_path = _resolve_env_file(env_file)
    values = dotenv_values(env_path)

    code_root = _resolve_config_path(values, "STS2_CODE_ROOT", env_path)
    localization_root = _resolve_config_path(values, "STS2_LOCALIZATION_ROOT", env_path)

    if not (code_root / "MegaCrit" / "sts2").is_dir():
        raise FileNotFoundError(
            f"STS2_CODE_ROOT must point at the decompiled source root containing MegaCrit/sts2: {code_root}"
        )
    if not localization_root.is_dir():
        raise FileNotFoundError(f"STS2_LOCALIZATION_ROOT must point at the localization directory: {localization_root}")

    return LocalSourceConfig(code_root=code_root, localization_root=localization_root)


def _resolve_env_file(env_file: Path | None) -> Path:
    if env_file is not None:
        path = env_file.expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Config file not found: {path}")
        return path

    override = os.environ.get(ENV_FILE_VAR)
    if override:
        path = Path(override).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"{ENV_FILE_VAR} points at a missing file: {path}")
        return path

    for candidate in [Path.cwd(), *Path.cwd().parents]:
        path = candidate / ".env"
        if path.is_file():
            return path.resolve()

    raise FileNotFoundError(
        f"Could not find .env. Run from rng-predictor or set {ENV_FILE_VAR} to the config file path."
    )


def _resolve_config_path(values: dict[str, str | None], key: str, env_path: Path) -> Path:
    raw_value = values.get(key)
    if not raw_value:
        raise KeyError(f"Missing {key} in {env_path}")
    path = Path(raw_value).expanduser()
    if not path.is_absolute():
        path = env_path.parent / path
    return path.resolve()
