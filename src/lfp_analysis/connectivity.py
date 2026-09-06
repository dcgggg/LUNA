from __future__ import annotations

from itertools import combinations
from typing import Any

import numpy as np
import pandas as pd


def region_channel_pairs(channel_table: pd.DataFrame) -> pd.DataFrame:
    mapped = channel_table.copy()
    mapped["region"] = mapped["region"].fillna("").astype(str).str.strip()
    mapped = mapped.loc[mapped["region"] != ""]
    pairs: list[dict[str, Any]] = []
    for region_a, region_b in combinations(sorted(mapped["region"].unique()), 2):
        a_channels = mapped.loc[mapped["region"] == region_a]
        b_channels = mapped.loc[mapped["region"] == region_b]
        for _, row_a in a_channels.iterrows():
            for _, row_b in b_channels.iterrows():
                pairs.append(
                    {
                        "region_a": region_a,
                        "region_b": region_b,
                        "seed_array_index": int(row_a["array_index"]),
                        "target_array_index": int(row_b["array_index"]),
                        "seed_channel": row_a["channel_name"],
                        "target_channel": row_b["channel_name"],
                    }
                )
    return pd.DataFrame(pairs)


def compute_connectivity(
    data: np.ndarray,
    sfreq: float,
    channel_table: pd.DataFrame,
    quality_epoch: pd.DataFrame,
    config: dict[str, Any],
) -> dict[str, pd.DataFrame | str]:
    """Estimate connectivity across retained epochs; never concatenate epochs."""
    try:
        from mne_connectivity import spectral_connectivity_epochs
    except ImportError as exc:
        return {"status": f"not_run_missing_dependency: {exc}", "spectrum": pd.DataFrame(), "region_summary": pd.DataFrame()}
    conn_cfg = config.get("connectivity", {})
    pairs = region_channel_pairs(channel_table)
    if pairs.empty:
        return {"status": "not_run_channel_region_mapping_incomplete", "spectrum": pd.DataFrame(), "region_summary": pd.DataFrame()}
    min_epochs = int(conn_cfg.get("min_epochs", 5))
    valid_epoch = quality_epoch["quality_status"].astype(str).ne("fail").to_numpy()
    if int(np.sum(valid_epoch)) < min_epochs:
        return {
            "status": f"not_run_insufficient_valid_epochs: {int(np.sum(valid_epoch))} < {min_epochs}",
            "spectrum": pd.DataFrame(),
            "region_summary": pd.DataFrame(),
        }
    indices = (
        pairs["seed_array_index"].to_numpy(int),
        pairs["target_array_index"].to_numpy(int),
    )
    methods = list(conn_cfg.get("methods", ["imcoh", "wpli2_debiased", "coh"]))
    try:
        result = spectral_connectivity_epochs(
            np.asarray(data)[valid_epoch],
            names=channel_table.sort_values("array_index")["channel_name"].tolist(),
            method=methods,
            indices=indices,
            sfreq=float(sfreq),
            mode=str(conn_cfg.get("mode", "fourier")),
            fmin=float(conn_cfg.get("fmin_hz", 1.0)),
            fmax=float(conn_cfg.get("fmax_hz", 150.0)),
            faverage=False,
            verbose=False,
        )
    except Exception as exc:  # noqa: BLE001 - failed estimates are retained in status
        return {"status": f"failed: {type(exc).__name__}: {exc}", "spectrum": pd.DataFrame(), "region_summary": pd.DataFrame()}
    results = result if isinstance(result, list) else [result]
    rows: list[dict[str, Any]] = []
    n_epochs = int(np.sum(valid_epoch))
    effective_duration = n_epochs * data.shape[-1] / float(sfreq)
    for method, connection in zip(methods, results):
        values = np.asarray(connection.get_data())
        if values.ndim == 3:
            values = values[:, :, 0]
        frequencies = np.asarray(connection.freqs, dtype=float)
        for pair_index, pair in pairs.reset_index(drop=True).iterrows():
            for frequency_index, frequency in enumerate(frequencies):
                value = values[pair_index, frequency_index]
                rows.append(
                    {
                        **pair.to_dict(),
                        "method": method,
                        "frequency_hz": float(frequency),
                        "value": float(value),
                        "n_epochs": n_epochs,
                        "effective_duration_s": effective_duration,
                        "estimate_note": "across valid epochs; no epoch concatenation; not causal",
                    }
                )
    spectrum = pd.DataFrame(rows)
    if spectrum.empty:
        return {"status": "failed_empty_result", "spectrum": spectrum, "region_summary": pd.DataFrame()}
    summary = (
        spectrum.groupby(["method", "region_a", "region_b", "frequency_hz"], as_index=False)
        .agg(
            value=("value", "mean"),
            n_channel_pairs=("value", "size"),
            n_negative_estimates=("value", lambda values: int(np.sum(values < 0))),
            n_epochs=("n_epochs", "first"),
            effective_duration_s=("effective_duration_s", "first"),
        )
    )
    return {"status": "ok", "spectrum": spectrum, "region_summary": summary}
