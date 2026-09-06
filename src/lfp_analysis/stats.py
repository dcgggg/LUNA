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
    return (
        clean.groupby(group_columns, dropna=False)
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
    match_columns = match_columns or ["nominal_dose_time_min"]
    required = {"animal_id", value_column, condition_column, *match_columns}
    missing = sorted(required - set(metric_nodes.columns))
    if missing:
        raise ValueError(f"Paired analysis requires columns: {missing}")
    work = metric_nodes.loc[metric_nodes["animal_id"].notna()].copy()
    work = work.loc[work[condition_column].isin([pre_label, post_label])]
    pivot = work.pivot_table(index=["animal_id", *match_columns], columns=condition_column, values=value_column, aggfunc="mean")
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
