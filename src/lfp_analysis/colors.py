"""Stable, shared classification colours for LUNA plots.

Classification colours identify regions and channels.  They are deliberately
separate from continuous data colormaps (PSD, power, and quality heatmaps).
Colour assignment is deterministic from the region/channel identifiers, so
filtering, reordering, and loading a saved run do not silently change it.
"""

from __future__ import annotations

import colorsys
import hashlib
from collections.abc import Iterable
from typing import Any

import numpy as np
from matplotlib import colors as mpl_colors
from matplotlib.colors import to_hex

COLOR_TEMPLATES: dict[str, dict[str, float]] = {
    "indigo_lavender": {"hue_offset": 0.67, "saturation": 0.62, "lightness": 0.43},
    "colorblind_safe": {"hue_offset": 0.56, "saturation": 0.68, "lightness": 0.42},
    "teal_amber": {"hue_offset": 0.46, "saturation": 0.70, "lightness": 0.43},
    "earth_science": {"hue_offset": 0.08, "saturation": 0.64, "lightness": 0.42},
    "deep_jewel": {"hue_offset": 0.86, "saturation": 0.72, "lightness": 0.40},
    "muted_contrast": {"hue_offset": 0.25, "saturation": 0.58, "lightness": 0.45},
}

COLOR_TEMPLATE_LABELS = {
    "indigo_lavender": "Indigo / Lavender",
    "colorblind_safe": "Color-blind safe",
    "teal_amber": "Teal / Amber",
    "earth_science": "Earth science",
    "deep_jewel": "Deep jewel",
    "muted_contrast": "Muted contrast",
}

DEFAULT_COLOR_TEMPLATE = "indigo_lavender"
UNMAPPED_REGION = "未映射"


def available_color_templates() -> tuple[str, ...]:
    return tuple(COLOR_TEMPLATES)


def color_template_label(name: str) -> str:
    return COLOR_TEMPLATE_LABELS.get(str(name), str(name))


def _stable_fraction(value: Any) -> float:
    digest = hashlib.sha1(str(value).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") / float(2**64)


def _text(value: Any, fallback: str = "") -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return fallback
    text = str(value).strip()
    return fallback if text in {"", "nan", "None"} else text


def _template(name: str) -> dict[str, float]:
    return COLOR_TEMPLATES.get(str(name), COLOR_TEMPLATES[DEFAULT_COLOR_TEMPLATE])


def region_color(region: Any, template: str = DEFAULT_COLOR_TEMPLATE) -> str:
    """Return a stable, moderately dark colour for a region identifier."""
    name = _text(region, UNMAPPED_REGION)
    if name == UNMAPPED_REGION:
        return "#777777"
    spec = _template(template)
    hue = (spec["hue_offset"] + _stable_fraction(f"region:{name}") * 0.92) % 1.0
    # Keep lightness in a range that remains legible on white backgrounds.
    lightness = float(np.clip(spec["lightness"] + (_stable_fraction(f"light:{name}") - 0.5) * 0.08, 0.34, 0.55))
    return to_hex(colorsys.hls_to_rgb(hue, lightness, spec["saturation"]), keep_alpha=False)


def channel_color(channel: Any, region: Any = UNMAPPED_REGION, template: str = DEFAULT_COLOR_TEMPLATE) -> str:
    """Return a deterministic channel variant within its region palette."""
    region_name = _text(region, UNMAPPED_REGION)
    if region_name == UNMAPPED_REGION:
        return "#777777"
    base = region_color(region_name, template)
    rgb = np.asarray(mpl_colors.to_rgb(base), dtype=float)
    hue, lightness, saturation = colorsys.rgb_to_hls(*rgb)
    # Stable per-channel variation; this does not depend on the current
    # subset length or order.  More channels can share a level but retain the
    # same region hue, while line styles can distinguish very large groups.
    slot = int(_stable_fraction(f"channel:{region_name}:{_text(channel)}") * 7) % 7
    lightness_delta = (-0.13, -0.08, -0.04, 0.0, 0.04, 0.08, 0.13)[slot]
    saturation = float(np.clip(saturation + 0.04 * ((slot % 3) - 1), 0.52, 0.82))
    lightness = float(np.clip(lightness + lightness_delta, 0.27, 0.66))
    return to_hex(colorsys.hls_to_rgb(hue, lightness, saturation), keep_alpha=False)


def _row_value(row: Any, key: str, default: Any = "") -> Any:
    if isinstance(row, dict):
        return row.get(key, default)
    return getattr(row, key, default)


def channel_colors(rows: Iterable[Any], template: str = DEFAULT_COLOR_TEMPLATE) -> dict[str, str]:
    """Map channel names to stable region-aware colours."""
    result: dict[str, str] = {}
    for row in rows:
        name = _text(_row_value(row, "channel_name"))
        if name:
            result[name] = channel_color(name, _row_value(row, "region", UNMAPPED_REGION), template)
    return result


def region_colors(rows: Iterable[Any], template: str = DEFAULT_COLOR_TEMPLATE) -> dict[str, str]:
    result: dict[str, str] = {}
    for row in rows:
        name = _text(row.get("region") if isinstance(row, dict) else row, UNMAPPED_REGION)
        result[name] = region_color(name, template)
    return result


def color_scheme_for_rows(rows: Iterable[Any], template: str = DEFAULT_COLOR_TEMPLATE) -> dict[str, Any]:
    """Return both region and channel maps for plotters and legends."""
    materialized = list(rows)
    return {
        "template": template if template in COLOR_TEMPLATES else DEFAULT_COLOR_TEMPLATE,
        "regions": region_colors([_row_value(row, "region", UNMAPPED_REGION) for row in materialized], template),
        "channels": channel_colors(materialized, template),
    }
