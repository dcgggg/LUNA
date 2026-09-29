"""Saved-result selection, compatibility checks, and subject-level summaries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from .project_store import ProjectStore
from .result_contract import canonical_fingerprint, load_result_manifest, load_table


@dataclass
class ComparisonSelection:
    included: pd.DataFrame
    excluded: pd.DataFrame
    compatibility: pd.DataFrame


def subject_match_preview(store: ProjectStore, filters: dict[str, Any], *, include_pending_review: bool = False) -> pd.DataFrame:
    """Return one explicit inclusion-status row per project subject.

    Missing target states and duplicate matching results stay visible instead
    of being silently dropped or averaged.
    """
    candidates = pd.DataFrame(store.analysis_results({key: value for key, value in filters.items() if value not in (None, "")}))
    rows: list[dict[str, Any]] = []
    subjects = store.subjects()
    if filters.get("subject_id") not in (None, ""):
        subjects = [subject for subject in subjects if str(subject["subject_id"]) == str(filters["subject_id"])]
    if filters.get("group_label") not in (None, ""):
        subjects = [subject for subject in subjects if str(subject.get("group_label") or "") == str(filters["group_label"])]
    for subject in subjects:
        subject_rows = candidates.loc[candidates["subject_id"].eq(subject["subject_id"])] if not candidates.empty else pd.DataFrame()
        valid = subject_rows.loc[
            subject_rows["active"].eq(1)
            & subject_rows["calculation_status"].eq("completed")
            & subject_rows["save_status"].eq("saved")
            & subject_rows["result_validity"].eq("current")
            & (subject_rows["review_status"].isin(["approved", "pending"]) if include_pending_review else subject_rows["review_status"].eq("approved"))
        ] if not subject_rows.empty else pd.DataFrame()
        if valid.empty:
            status = "missing_or_not_eligible"
            reason = "No saved compatible result matches the requested session/state/review filters"
            analysis = ""
        elif len(valid) > 1:
            status = "duplicate_requires_choice"
            reason = f"{len(valid)} matching results; select an analysis_id explicitly"
            analysis = ";".join(valid["analysis_id"].astype(str))
        else:
            status = "included"
            reason = ""
            analysis = str(valid.iloc[0]["analysis_id"])
        rows.append({"subject_id": subject["subject_id"], "subject_code": subject["subject_code"], "group_label": subject.get("group_label", ""), "match_status": status, "analysis_id": analysis, "reason": reason})
    return pd.DataFrame(rows)


def _compatibility_signature(manifest: dict[str, Any]) -> str:
    parameters = manifest.get("effective_parameters", {})
    relevant = {
        "module": manifest.get("module_name"),
        "method": manifest.get("method_name"),
        "signal_unit": manifest.get("signal_unit"),
        "sampling_rate_hz": manifest.get("sampling_rate_hz"),
        "parameters": parameters,
        "channel_mapping": manifest.get("channel_mapping"),
    }
    return canonical_fingerprint(relevant)


def select_results(
    store: ProjectStore,
    filters: dict[str, Any],
    *,
    include_pending_review: bool = False,
    selected_analysis_ids: list[str] | None = None,
) -> ComparisonSelection:
    query_filters = dict(filters)
    query_filters.setdefault("calculation_status", "completed")
    query_filters.setdefault("save_status", "saved")
    if selected_analysis_ids is None:
        query_filters.setdefault("active", 1)
        query_filters.setdefault("result_validity", "current")
    if not include_pending_review and selected_analysis_ids is None:
        query_filters.setdefault("review_status", "approved")
    candidates = pd.DataFrame(store.analysis_results(query_filters))
    if candidates.empty:
        return ComparisonSelection(pd.DataFrame(), pd.DataFrame(columns=["reason"]), pd.DataFrame())
    if selected_analysis_ids is not None:
        candidates = candidates.loc[candidates["analysis_id"].astype(str).isin(set(map(str, selected_analysis_ids)))].copy()
    key_columns = ["subject_id", "session_key", "condition_label", "timepoint_value", "timepoint_unit", "module_name"]
    if filters.get("timepoint_min") not in (None, "") or filters.get("timepoint_max") not in (None, ""):
        # A range may contain several scientifically distinct state records.
        # Until the user chooses an explicit analysis/version, do not silently
        # average them as one subject-level observation.
        key_columns = ["subject_id", "session_key", "condition_label", "module_name"]
    duplicated = candidates.duplicated(key_columns, keep=False)
    excluded = candidates.loc[duplicated].copy()
    if not excluded.empty:
        excluded["reason"] = "duplicate_matching_results_require_explicit_selection"
    included = candidates.loc[~duplicated].copy()
    signatures: list[dict[str, Any]] = []
    for row in included.itertuples():
        manifest = load_result_manifest(store.resolve_project_relative_path(row.result_path))
        signatures.append({"analysis_id": row.analysis_id, "compatibility_signature": _compatibility_signature(manifest)})
    compatibility = pd.DataFrame(signatures)
    if not compatibility.empty:
        included = included.merge(compatibility, on="analysis_id", how="left")
        compatibility["compatible_with_first"] = compatibility["compatibility_signature"].eq(compatibility.iloc[0]["compatibility_signature"])
    return ComparisonSelection(included.reset_index(drop=True), excluded.reset_index(drop=True), compatibility)


def subject_summary(
    store: ProjectStore,
    selection: ComparisonSelection,
    table_name: str,
    value_column: str,
    group_columns: list[str],
    aggregation: str = "mean",
    row_filters: dict[str, Any] | None = None,
) -> pd.DataFrame:
    if aggregation not in {"mean", "median"}:
        raise ValueError("aggregation must be mean or median")
    frames: list[pd.DataFrame] = []
    for row in selection.included.itertuples():
        manifest = load_result_manifest(store.resolve_project_relative_path(row.result_path))
        frame = load_table(manifest, table_name)
        if "region_pair" not in frame:
            if {"region_a", "region_b"}.issubset(frame.columns):
                frame["region_pair"] = frame["region_a"].astype(str) + "–" + frame["region_b"].astype(str)
            elif {"seed_region", "target_region"}.issubset(frame.columns):
                frame["region_pair"] = frame["seed_region"].astype(str) + "→" + frame["target_region"].astype(str)
        for column, expected in (row_filters or {}).items():
            if column == "__target_columns__":
                columns = [name for name in expected.get("columns", ()) if name in frame]
                if columns and expected.get("value") not in (None, "", "All"):
                    frame = frame.loc[
                        pd.concat(
                            [frame[name].astype(str).eq(str(expected["value"])) for name in columns],
                            axis=1,
                        ).any(axis=1)
                    ]
                continue
            if column in frame and expected not in (None, "", "All"):
                frame = frame.loc[frame[column].astype(str).eq(str(expected))]
        if frame.empty:
            continue
        if value_column not in frame:
            raise ValueError(f"{row.analysis_id}: missing value column {value_column}")
        available_groups = [column for column in group_columns if column in frame]
        grouped = frame.groupby(available_groups, dropna=False, as_index=False)[value_column].agg(aggregation) if available_groups else pd.DataFrame({value_column: [getattr(frame[value_column], aggregation)()]})
        grouped["subject_id"] = row.subject_id
        grouped["subject_code"] = row.subject_code
        grouped["group_label"] = row.group_label
        grouped["session_id"] = row.session_id
        grouped["session_key"] = row.session_key
        grouped["condition_label"] = row.condition_label
        grouped["timepoint_value"] = row.timepoint_value
        grouped["data_unit_id"] = row.data_unit_id
        grouped["analysis_id"] = row.analysis_id
        grouped["review_status"] = row.review_status
        grouped["compatibility_signature"] = getattr(row, "compatibility_signature", "")
        grouped["aggregation"] = aggregation
        frames.append(grouped)
    return pd.concat(frames, ignore_index=True, sort=False) if frames else pd.DataFrame()


def group_summary(subject_frame: pd.DataFrame, value_column: str, group_columns: list[str]) -> pd.DataFrame:
    if subject_frame.empty:
        return pd.DataFrame()
    columns = [column for column in group_columns if column in subject_frame]
    if not columns:
        return pd.DataFrame(
            {
                "value_mean": [subject_frame[value_column].mean()],
                "value_median": [subject_frame[value_column].median()],
                "value_sd": [subject_frame[value_column].std()],
                "n_subjects": [subject_frame["subject_id"].nunique()],
            }
        )
    return (
        subject_frame.groupby(columns, dropna=False, as_index=False)
        .agg(value_mean=(value_column, "mean"), value_median=(value_column, "median"), value_sd=(value_column, "std"), n_subjects=("subject_id", "nunique"))
    )


def paired_subject_summary(
    store: ProjectStore,
    first: ComparisonSelection,
    second: ComparisonSelection,
    table_name: str,
    value_column: str,
    group_columns: list[str],
    *,
    first_filters: dict[str, Any] | None = None,
    second_filters: dict[str, Any] | None = None,
    aggregation: str = "mean",
) -> pd.DataFrame:
    """Match two saved-result selections by stable subject identity.

    Duplicate or missing results are already absent from ``included`` and are
    therefore reported as incomplete pairs by callers rather than being paired
    by row order.  Scientific compatibility remains explicit for each side.
    """
    left = subject_summary(
        store,
        first,
        table_name,
        value_column,
        group_columns,
        aggregation,
        row_filters=first_filters,
    )
    right = subject_summary(
        store,
        second,
        table_name,
        value_column,
        group_columns,
        aggregation,
        row_filters=second_filters,
    )
    if left.empty or right.empty:
        return pd.DataFrame()
    keys = ["subject_id", *[column for column in group_columns if column in left and column in right]]
    left_columns = [*keys, "subject_code", "group_label", "analysis_id", "compatibility_signature", value_column]
    right_columns = [*keys, "analysis_id", "compatibility_signature", value_column]
    return left[left_columns].merge(
        right[right_columns],
        on=keys,
        how="inner",
        suffixes=("_first", "_second"),
        validate="one_to_one",
    )
