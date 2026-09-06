from __future__ import annotations

import pandas as pd


def node_level_behavior_status(behavior: pd.DataFrame) -> pd.DataFrame:
    """Summarize behavior availability without expanding a score to epoch rows."""
    if behavior.empty:
        return pd.DataFrame(columns=["animal_id", "session_id", "nominal_dose_time_min", "behavior_status"])
    keys = ["animal_id", "session_id", "nominal_dose_time_min"]
    out = behavior[keys].drop_duplicates().copy()
    score_columns = [column for column in behavior.columns if column.startswith("aims_")]
    out["behavior_status"] = "node_present"
    if score_columns:
        out["has_any_aims_score"] = behavior.groupby(keys, dropna=False)[score_columns].apply(lambda frame: frame.notna().any().any()).to_numpy()
    return out

