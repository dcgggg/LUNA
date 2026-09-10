"""User-editable channel to region mapping utilities.

The mapping is deliberately independent of the analysis algorithms.  The
current metadata CSV remains the default template, while this module lets the
GUI replace region labels for a loaded file without guessing from array
position.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

DEFAULT_TEMPLATE_REGIONS = ("M1", "STR", "PF", "SNr")


def region_order(channel_table: pd.DataFrame) -> list[str]:
    """Return non-empty regions in first appearance order in the table."""
    if not isinstance(channel_table, pd.DataFrame) or "region" not in channel_table:
        return []
    result: list[str] = []
    for value in channel_table["region"].tolist():
        name = "" if pd.isna(value) else str(value).strip()
        if name and name not in result:
            result.append(name)
    return result


def region_pairs(channel_table: pd.DataFrame) -> list[tuple[str, str]]:
    regions = region_order(channel_table)
    return [(regions[i], regions[j]) for i in range(len(regions)) for j in range(i + 1, len(regions))]


def mapping_rows(channel_table: pd.DataFrame) -> list[dict[str, Any]]:
    """Serialize the editable rows while retaining physical and array IDs."""
    if not isinstance(channel_table, pd.DataFrame):
        return []
    rows: list[dict[str, Any]] = []
    for row in channel_table.to_dict(orient="records"):
        rows.append(
            {
                "channel_name": str(row.get("channel_name", "")),
                "physical_channel_number": "" if pd.isna(row.get("physical_channel_number", "")) else row.get("physical_channel_number", ""),
                "array_index": int(row.get("array_index", 0)),
                "region": "" if pd.isna(row.get("region", "")) else str(row.get("region", "")).strip(),
                "label": "" if pd.isna(row.get("label", "")) else str(row.get("label", "")).strip(),
            }
        )
    return rows


def save_mapping(channel_table: pd.DataFrame, path: str | Path) -> Path:
    """Save a rich JSON mapping; it also contains the requested region lists."""
    output = Path(path).expanduser().resolve()
    rows = mapping_rows(channel_table)
    by_region: dict[str, list[Any]] = {}
    for row in rows:
        region = str(row.get("region", "")).strip()
        if not region:
            continue
        physical = row.get("physical_channel_number", "")
        value: Any = physical if physical not in (None, "") else row.get("channel_name", "")
        by_region.setdefault(region, []).append(value)
    payload = {
        "format": "LUNA channel mapping",
        "version": 1,
        "regions": by_region,
        "channels": rows,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return output


def load_mapping(path: str | Path) -> dict[str, Any]:
    """Load rich LUNA JSON or the simple ``{region: [physical_numbers]}`` form."""
    value = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError("mapping JSON 必须是对象。")
    if isinstance(value.get("channels"), list):
        rows = [row for row in value["channels"] if isinstance(row, dict)]
        return {"channels": rows, "regions": value.get("regions", {})}
    if isinstance(value.get("regions"), dict):
        return {"channels": [], "regions": value["regions"]}
    # Backwards-compatible simple dictionary: every key is a region and every
    # item is a physical channel number or channel name.
    return {"channels": [], "regions": value}


def _physical_key(value: Any) -> str:
    try:
        return str(int(float(value)))
    except (TypeError, ValueError):
        return str(value).strip()


def apply_mapping(channel_table: pd.DataFrame, mapping: dict[str, Any]) -> pd.DataFrame:
    """Apply a loaded mapping by channel name first, then physical number."""
    result = channel_table.copy()
    if "region" not in result:
        result["region"] = ""
    channel_rows = mapping.get("channels", []) if isinstance(mapping, dict) else []
    by_name: dict[str, str] = {}
    by_physical: dict[str, str] = {}
    for row in channel_rows:
        region = str(row.get("region", "")).strip()
        if not region:
            continue
        if row.get("channel_name") not in (None, ""):
            by_name[str(row["channel_name"])] = region
        if row.get("physical_channel_number") not in (None, ""):
            by_physical[_physical_key(row["physical_channel_number"])] = region
    regions = mapping.get("regions", {}) if isinstance(mapping, dict) else {}
    if isinstance(regions, dict):
        for region, values in regions.items():
            for item in values if isinstance(values, list) else [values]:
                key = _physical_key(item)
                by_physical[key] = str(region).strip()
                by_name[str(item).strip()] = str(region).strip()
    for index, row in result.iterrows():
        name = str(row.get("channel_name", ""))
        physical = _physical_key(row.get("physical_channel_number", ""))
        region = by_name.get(name, by_physical.get(physical))
        if region is not None:
            result.at[index, "region"] = region
            result.at[index, "mapping_status"] = "mapped"
    if "label" not in result:
        result["label"] = ""
    for row in channel_rows:
        name = str(row.get("channel_name", ""))
        if name and name in set(result["channel_name"].astype(str)) and row.get("label") is not None:
            result.loc[result["channel_name"].astype(str) == name, "label"] = str(row.get("label", ""))
    return result


def validate_mapping(channel_table: pd.DataFrame) -> list[str]:
    issues: list[str] = []
    if not isinstance(channel_table, pd.DataFrame) or channel_table.empty:
        return ["当前文件没有可编辑的通道。"]
    if "channel_name" not in channel_table:
        issues.append("缺少 channel_name。")
    elif channel_table["channel_name"].astype(str).duplicated().any():
        issues.append("通道名称重复。")
    if "region" not in channel_table or not channel_table["region"].fillna("").astype(str).str.strip().ne("").any():
        issues.append("至少需要为一个通道填写脑区名称。")
    return issues
