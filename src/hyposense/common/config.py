"""Configuration loading. Scientific constants live in version-controlled YAML under configs/."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from hyposense.common.hashing import sha256_json

REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG_DIR = REPO_ROOT / "configs"


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a YAML mapping at top level")
    return data


def load_config(name: str = "default.yaml") -> dict[str, Any]:
    return load_yaml(CONFIG_DIR / name)


def config_hash(cfg: dict[str, Any]) -> str:
    """Hash of the parsed configuration (insensitive to comments and key order)."""
    return sha256_json(cfg)
