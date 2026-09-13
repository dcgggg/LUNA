import numpy as np
import pandas as pd

from lfp_analysis.connectivity import (
    _finite_epoch_mask,
    assess_region_redundancy,
    compute_connectivity,
)
from lfp_analysis.quality import align_epoch_quality
from lfp_analysis.time_delay import _region_summary


def test_epoch_quality_aligns_by_explicit_analysis_id_not_row_order():
    quality = pd.DataFrame(
        {
            "analysis_epoch_index": [2, 0, 1],
            "original_epoch_index": [20, 10, 11],
            "quality_status": ["fail", "ok", "warn"],
        }
    )
    aligned = align_epoch_quality(quality, 3)
    assert aligned["original_epoch_index"].tolist() == [10, 11, 20]
    mask, _ = _finite_epoch_mask(np.ones((3, 1, 4)), quality)
    assert mask.tolist() == [True, True, False]


def test_missing_quality_row_is_not_assumed_valid():
    quality = pd.DataFrame({"epoch_index": [0, 2], "quality_status": ["ok", "ok"]})
    aligned = align_epoch_quality(quality, 3)
    assert aligned.loc[1, "quality_status"] == "missing_quality_status"
    mask, _ = _finite_epoch_mask(np.ones((3, 1, 4)), quality)
    assert mask.tolist() == [True, False, True]


def test_quality_alignment_rejects_duplicate_ids():
    quality = pd.DataFrame({"epoch_index": [0, 0], "quality_status": ["ok", "ok"]})
    try:
        align_epoch_quality(quality, 2)
    except ValueError as exc:
        assert "unique" in str(exc)
    else:
        raise AssertionError("duplicate epoch IDs must be rejected")


def test_single_channel_region_has_explicit_rank_one_diagnostic():
    data = np.arange(5 * 2 * 20, dtype=float).reshape(5, 2, 20)
    channel_table = pd.DataFrame(
        {
            "array_index": [0, 1],
            "channel_name": ["M1-1", "STR-1"],
            "region": ["M1", "STR"],
        }
    )
    diagnostics = assess_region_redundancy(
        data,
        100.0,
        channel_table,
        np.ones(5, dtype=bool),
        {"connectivity": {"rank_variance_threshold": 0.99}},
    )
    summary = diagnostics["summary"].set_index("region")
    assert summary.loc["M1", "n_channels"] == 1
    assert summary.loc["M1", "selected_rank"] == 1
    correlation = diagnostics["correlation"]
    assert correlation.shape[0] == 2
    assert correlation.loc[correlation["region"] == "M1", "correlation"].iloc[0] == 1.0


def test_explicit_empty_connectivity_selection_does_not_restore_all_pairs():
    data = np.random.default_rng(3).normal(size=(5, 2, 40))
    channel_table = pd.DataFrame(
        {
            "array_index": [0, 1],
            "channel_name": ["M1-1", "STR-1"],
            "region": ["M1", "STR"],
        }
    )
    quality = pd.DataFrame({"epoch_index": range(5), "quality_status": ["ok"] * 5})
    result = compute_connectivity(
        data,
        100.0,
        channel_table,
        quality,
        {"connectivity": {"methods": ["wpli"], "selected_region_pairs": [], "min_epochs": 5}},
    )
    assert result["status"] == "not_run_no_selected_region_pairs"
    assert result["spectrum"].empty


def test_tde_region_summary_counts_unique_seed_target_pairs():
    rows = []
    for seed in ("M1-1", "M1-2"):
        for target in ("STR-1", "STR-2"):
            for delay in (0.0, 5.0):
                rows.append(
                    {
                        "region_a": "M1",
                        "region_b": "STR",
                        "method": 1,
                        "method_name": "test",
                        "antisymmetrized": True,
                        "seed_channel": seed,
                        "target_channel": target,
                        "frequency_band": "alpha",
                        "band_low_hz": 8.0,
                        "band_high_hz": 12.0,
                        "delay_ms": delay,
                        "estimate_strength": delay + 1.0,
                        "n_epochs": 5,
                        "effective_duration_s": 2.0,
                        "analysis_sfreq_hz": 100.0,
                        "n_points": 40,
                        "delay_resolution_ms": 10.0,
                    }
                )
    summary = _region_summary(pd.DataFrame(rows))
    assert summary["n_channel_pairs"].eq(4).all()
