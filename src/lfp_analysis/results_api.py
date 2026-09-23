"""Public, GUI-independent project result reader and long-table exporter."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .project_store import ProjectStore
from .result_contract import load_array, load_result_manifest, load_table


class ProjectResults:
    def __init__(self, project_root: str | Path) -> None:
        self.store = ProjectStore(project_root)

    def list(self, **filters: Any) -> pd.DataFrame:
        return pd.DataFrame(self.store.analysis_results(filters))

    def manifest(self, analysis_id: str) -> dict[str, Any]:
        rows = self.store.query("SELECT result_path FROM analysis_runs WHERE analysis_id=?", (analysis_id,))
        if not rows:
            raise KeyError(analysis_id)
        return load_result_manifest(self.store.paths.root / rows[0]["result_path"])

    def table(self, analysis_id: str, table_name: str | None = None) -> pd.DataFrame:
        manifest = self.manifest(analysis_id)
        names = list(manifest.get("tables", {}))
        if table_name is None:
            if len(names) != 1:
                raise ValueError(f"Specify table_name; available={names}")
            table_name = names[0]
        return load_table(manifest, table_name)

    def array(self, analysis_id: str, array_name: str) -> np.ndarray:
        return load_array(self.manifest(analysis_id), array_name)

    def extract(self, analysis_id: str, table_name: str, *, channel: str | None = None, region: str | None = None, region_pair: str | None = None) -> pd.DataFrame:
        frame = self.table(analysis_id, table_name)
        if "region_pair" not in frame:
            if {"region_a", "region_b"}.issubset(frame.columns):
                frame["region_pair"] = frame["region_a"].astype(str) + "–" + frame["region_b"].astype(str)
            elif {"seed_region", "target_region"}.issubset(frame.columns):
                frame["region_pair"] = frame["seed_region"].astype(str) + "→" + frame["target_region"].astype(str)
        if channel is not None:
            channel_columns = [column for column in ("channel_name", "seed_channel", "target_channel") if column in frame]
            if not channel_columns:
                raise ValueError("Selected table has no channel field")
            mask = np.logical_or.reduce([frame[column].astype(str).eq(channel).to_numpy() for column in channel_columns])
            frame = frame.loc[mask]
        if region is not None:
            region_columns = [column for column in ("region", "region_a", "region_b", "seed_region", "target_region") if column in frame]
            if not region_columns:
                raise ValueError("Selected table has no region field")
            mask = np.logical_or.reduce([frame[column].astype(str).eq(region).to_numpy() for column in region_columns])
            frame = frame.loc[mask]
        if region_pair is not None:
            pair_columns = [column for column in ("pair_label", "region_pair") if column in frame]
            if not pair_columns:
                raise ValueError("Selected table has no region-pair field")
            frame = frame.loc[np.logical_or.reduce([frame[column].astype(str).eq(region_pair).to_numpy() for column in pair_columns])]
        return frame.copy()

    def to_long_table(self, analysis_ids: list[str], table_name: str, value_columns: list[str] | None = None) -> pd.DataFrame:
        rows: list[pd.DataFrame] = []
        index = {row["analysis_id"]: row for row in self.store.analysis_results() if row["analysis_id"] in set(analysis_ids)}
        for aid in analysis_ids:
            meta = index.get(aid)
            if meta is None:
                raise KeyError(aid)
            manifest = self.manifest(aid)
            frame = self.table(aid, table_name)
            if "region_pair" not in frame:
                if {"region_a", "region_b"}.issubset(frame.columns):
                    frame["region_pair"] = frame["region_a"].astype(str) + "–" + frame["region_b"].astype(str)
                elif {"seed_region", "target_region"}.issubset(frame.columns):
                    frame["region_pair"] = frame["seed_region"].astype(str) + "→" + frame["target_region"].astype(str)
            candidates = value_columns or [column for column in ("psd_value", "absolute_power", "relative_power", "offset", "exponent", "center_frequency_hz", "peak_power", "bandwidth_hz", "value_raw", "value_strength", "delay_ms", "value") if column in frame]
            id_columns = [column for column in frame.columns if column not in candidates]
            long = frame.melt(id_vars=id_columns, value_vars=candidates, var_name="metric", value_name="value") if candidates else frame.assign(metric="", value=np.nan)
            for key in ("subject_id", "subject_code", "group_label", "session_id", "session_key", "condition_label", "timepoint_value", "timepoint_unit", "state_record_id", "data_unit_id", "analysis_id", "module_name", "review_status"):
                long[key] = meta.get(key, manifest.get(key, ""))
            signal_unit = str(manifest.get("signal_unit") or "input_unit")
            unit_by_metric = {
                "psd_value": f"{signal_unit}^2/Hz",
                "absolute_power": f"{signal_unit}^2",
                "relative_power": "fraction",
                "center_frequency_hz": "Hz",
                "bandwidth_hz": "Hz",
                "delay_ms": "ms",
                "exponent": "dimensionless",
                "value_strength": "method_defined",
                "value_raw": "method_defined",
            }
            long["value_unit"] = long["metric"].map(unit_by_metric).fillna("method_defined")
            if "epoch_index" in frame:
                summary_level = "epoch"
            elif any(column in frame for column in ("pair_label", "region_pair", "seed_region", "target_region")):
                summary_level = "connection_or_region_pair"
            elif "channel_name" in frame:
                summary_level = "channel"
            elif "region" in frame:
                summary_level = "region"
            else:
                summary_level = "analysis"
            long["summary_level"] = summary_level
            long["quality_flag"] = long["status"].astype(str) if "status" in long else str(manifest.get("quality_summary", {}).get("algorithm_status") or manifest.get("calculation_status", ""))
            rows.append(long)
        return pd.concat(rows, ignore_index=True, sort=False) if rows else pd.DataFrame()

    def export_long_table(self, analysis_ids: list[str], table_name: str, output_path: str | Path, value_columns: list[str] | None = None) -> Path:
        target = Path(output_path).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        self.to_long_table(analysis_ids, table_name, value_columns).to_csv(target, index=False)
        return target
