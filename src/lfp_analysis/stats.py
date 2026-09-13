from __future__ import annotations

from typing import Any

import pandas as pd


def animal_level_descriptive(metric_nodes: pd.DataFrame, value_column: str, group_columns: list[str]) -> pd.DataFrame:
    """Aggregate only after an animal identifier is present."""
    required = {"animal_id", value_column, *group_columns}
    missing = sorted(required - set(metric_nodes.columns))
    if missing:
        raise ValueError(f"Animal-level summary requires columns: {missing}")
    clean = metric_nodes.loc[metric_nodes["animal_id"].notna() & metric_nodes["animal_id"].astype(str).ne("")].copy()
    clean[value_column] = pd.to_numeric(clean[value_column], errors="coerce")
    clean = clean.loc[clean[value_column].notna()]
    grouping = [column for column in group_columns if column != "animal_id"]
    animal_nodes = (
        clean.groupby(["animal_id", *grouping], dropna=False, as_index=False)[value_column]
        .mean()
    )
    return (
        animal_nodes.groupby(grouping, dropna=False)
        .agg(
            mean=(value_column, "mean"),
            sd=(value_column, "std"),
            n_animals=("animal_id", "nunique"),
            n_nodes=(value_column, "count"),
        )
        .reset_index()
    )


def paired_pre_post(
    metric_nodes: pd.DataFrame,
    value_column: str,
    condition_column: str = "ldn_status",
    pre_label: str = "pre",
    post_label: str = "post",
    match_columns: list[str] | None = None,
) -> pd.DataFrame:
    """Create animal-paired differences at the requested node/time grain."""
    if match_columns is None:
        day_column = next((column for column in ("l_dopa_day", "record_day", "recording_day") if column in metric_nodes.columns), None)
        if day_column is None:
            return pd.DataFrame(
                [{"status": "not_run_missing_record_day", "reason": "paired_pre_post requires session_id, a record-day field, and nominal_dose_time_min"}]
            )
        match_columns = ["session_id", day_column, "nominal_dose_time_min"]
    else:
        match_columns = list(match_columns)
    day_columns = {"l_dopa_day", "record_day", "recording_day"}
    if "session_id" not in match_columns or not day_columns.intersection(match_columns) or "nominal_dose_time_min" not in match_columns:
        return pd.DataFrame(
            [{"status": "not_run_incomplete_pairing_keys", "reason": "paired_pre_post requires session_id, a record-day field, and nominal_dose_time_min"}]
        )
    required = {"animal_id", value_column, condition_column, *match_columns}
    missing = sorted(required - set(metric_nodes.columns))
    if missing:
        raise ValueError(f"Paired analysis requires columns: {missing}")
    work = metric_nodes.loc[metric_nodes["animal_id"].notna()].copy()
    work = work.loc[work[condition_column].isin([pre_label, post_label])]
    work[value_column] = pd.to_numeric(work[value_column], errors="coerce")
    work = work.loc[work[value_column].notna()]
    node_keys = ["animal_id", *match_columns]
    duplicate_condition = work.groupby([*node_keys, condition_column], dropna=False).size()
    if (duplicate_condition > 1).any():
        return pd.DataFrame(
            [{"status": "not_run_duplicate_condition_nodes", "reason": "multiple values share one explicit animal/session/day/time/condition key"}]
        )
    pivot = work.pivot(index=node_keys, columns=condition_column, values=value_column)
    if pre_label not in pivot or post_label not in pivot:
        return pd.DataFrame(columns=["animal_id", *match_columns, "pre_value", "post_value", "difference"])
    pivot = pivot.reset_index().rename(columns={pre_label: "pre_value", post_label: "post_value"})
    pivot["difference"] = pivot["post_value"] - pivot["pre_value"]
    return pivot


def safe_inferential_design_note(actual_n_animals: int, repeated_measure: bool) -> dict[str, Any]:
    if actual_n_animals < 2:
        return {"status": "not_run", "reason": "fewer_than_two_animals"}
    if repeated_measure:
        return {"status": "design_required", "reason": "choose mixed/repeated-measures model after missingness and distribution review"}
    return {"status": "design_required", "reason": "choose model after distribution and sample-size review"}
