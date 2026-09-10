from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(path: str | Path) -> dict[str, Any]:
    """Load an editable YAML configuration."""
    config_path = Path(path).expanduser()
    with config_path.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}
    if not isinstance(config, dict):
        raise TypeError(f"Configuration must be a mapping: {config_path}")
    extends = config.pop("extends", None)
    if extends:
        parent = (config_path.parent / str(extends)).resolve()
        if not parent.is_file():
            raise FileNotFoundError(f"Extended configuration not found: {parent}")
        return _merge(load_config(parent), config)
    return config


def nested(config: dict[str, Any], *keys: str, default: Any = None) -> Any:
    value: Any = config
    for key in keys:
        if not isinstance(value, dict) or key not in value:
            return default
        value = value[key]
    return value


def as_float(value: Any, default: float | None = None) -> float | None:
    if value in (None, ""):
        return default
    return float(value)
