from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

TABLES = ("animals", "records", "files", "epochs", "behavior", "channel_map")
REQUIRED_COLUMNS = {
    "animals": ["animal_id", "group"],
    "records": ["session_id", "animal_id"],
    "files": ["file_id", "session_id", "file_path"],
    "epochs": ["file_id", "saved_index", "original_candidate_index"],
    "behavior": ["animal_id", "session_id", "nominal_dose_time_min"],
    "channel_map": ["channel_name", "physical_channel_number", "region"],
}


def load_metadata_tables(metadata_dir: str | Path) -> dict[str, pd.DataFrame]:
    directory = Path(metadata_dir)
    tables: dict[str, pd.DataFrame] = {}
    for table in TABLES:
        path = directory / f"{table}.csv"
        tables[table] = pd.read_csv(path, dtype=str) if path.exists() else pd.DataFrame()
    return tables


def _missing(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip()) or pd.isna(value)


def validate_metadata_tables(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Validate keys and cross-table links without filling unknown values."""
    issues: list[dict[str, Any]] = []

    def issue(table: str, severity: str, code: str, message: str, row: Any = "") -> None:
        issues.append({"table": table, "severity": severity, "code": code, "message": message, "row": row})

    for table, required in REQUIRED_COLUMNS.items():
        frame = tables.get(table, pd.DataFrame())
        if frame.empty and table in {"animals", "records", "files", "behavior"}:
            issue(table, "info", "empty_template", "table is empty; this is allowed before metadata registration")
            continue
        for column in required:
            if column not in frame.columns:
                issue(table, "error", "missing_column", f"missing required column: {column}")
        if frame.empty:
            continue
        key_columns = {
            "animals": ["animal_id"],
            "records": ["session_id"],
            "files": ["file_id"],
            "epochs": ["file_id", "saved_index"],
            "behavior": ["animal_id", "session_id", "nominal_dose_time_min"],
            "channel_map": ["channel_name"],
        }[table]
        if all(column in frame.columns for column in key_columns):
            duplicated = frame.duplicated(key_columns, keep=False)
            for row_index in frame.index[duplicated]:
                issue(table, "error", "duplicate_key", f"duplicate key on {key_columns}", int(row_index))
        for column in required:
            if column in frame.columns:
                missing_rows = frame.index[frame[column].map(_missing)]
                for row_index in missing_rows:
                    issue(table, "warning", "missing_key_value", f"missing required value: {column}", int(row_index))

    animals = tables.get("animals", pd.DataFrame())
    records = tables.get("records", pd.DataFrame())
    files = tables.get("files", pd.DataFrame())
    behavior = tables.get("behavior", pd.DataFrame())
    animal_ids = set(animals.get("animal_id", pd.Series(dtype=str)).dropna().astype(str))
    session_ids = set(records.get("session_id", pd.Series(dtype=str)).dropna().astype(str))

    if not records.empty and "animal_id" in records:
        for idx, value in records["animal_id"].items():
            if value and value not in animal_ids:
                issue("records", "warning", "unmatched_animal", f"animal_id not found in animals: {value}", int(idx))
    if not files.empty:
        for idx, value in files.get("session_id", pd.Series(dtype=str)).items():
            if value and value not in session_ids:
                issue("files", "warning", "unmatched_session", f"session_id not found in records: {value}", int(idx))
        for idx, value in files.get("animal_id", pd.Series(dtype=str)).items():
            if value and value not in animal_ids:
                issue("files", "warning", "unmatched_animal", f"animal_id not found in animals: {value}", int(idx))
    if not behavior.empty:
        for idx, value in behavior.get("session_id", pd.Series(dtype=str)).items():
            if value and value not in session_ids:
                issue("behavior", "warning", "unmatched_session", f"session_id not found in records: {value}", int(idx))
    if not behavior.empty and not files.empty:
        behavior_keys = set(
            zip(
                behavior.get("animal_id", pd.Series(dtype=str)).astype(str),
                behavior.get("session_id", pd.Series(dtype=str)).astype(str),
                behavior.get("nominal_dose_time_min", pd.Series(dtype=str)).astype(str),
            )
        )
        file_keys = set(
            zip(
                files.get("animal_id", pd.Series(dtype=str)).astype(str),
                files.get("session_id", pd.Series(dtype=str)).astype(str),
                files.get("nominal_dose_time_min", pd.Series(dtype=str)).astype(str),
            )
        )
        for key in sorted(behavior_keys - file_keys):
            issue("behavior", "warning", "unmatched_behavior_node", f"behavior node has no file match: {key}")
    if not files.empty and "file_path" in files:
        paths = files["file_path"].dropna().astype(str)
        duplicated_paths = paths[paths.duplicated(keep=False)]
        for path in duplicated_paths.unique():
            issue("files", "warning", "duplicate_file_path", f"duplicate file path: {path}")
    return pd.DataFrame(issues, columns=["table", "severity", "code", "message", "row"])


def merge_behavior_at_node(metric_nodes: pd.DataFrame, behavior: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Merge behavior only at animal × session × nominal dose-time grain."""
    keys = ["animal_id", "session_id", "nominal_dose_time_min"]
    missing = [key for key in keys if key not in metric_nodes or key not in behavior]
    if missing:
        raise ValueError(f"Cannot merge behavior; missing keys: {missing}")
    merged = metric_nodes.merge(behavior, on=keys, how="left", indicator=True, suffixes=("", "_behavior"))
    unmatched = merged.loc[merged["_merge"] == "left_only", keys].drop_duplicates().copy()
    return merged.drop(columns=["_merge"]), unmatched
