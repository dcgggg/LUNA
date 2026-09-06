import numpy as np
import pandas as pd
import pytest

from lfp_analysis.config import load_config
from lfp_analysis.connectivity import assess_region_redundancy, compute_connectivity
from lfp_analysis.parameterization import fit_channel_psd_table, fit_single_psd_detailed
from lfp_analysis.quality import assess_quality
from lfp_analysis.spectral import compute_psd, summarize_psd
from lfp_analysis.synthetic import make_synthetic_epochs


def test_specparam_result_fields_are_populated_when_available():
    data, channels = make_synthetic_epochs(n_epochs=6, n_channels=2, n_times=5000, seed=12)
    config = {
        "psd": {"fmin_hz": 1.0, "fmax_hz": 150.0, "nperseg": 1000, "noverlap": 500, "window": "hann", "detrend": "constant", "scaling": "density", "average": "mean"},
        "parameterization": load_config("configs/default.yaml")["parameterization"],
    }
    psd = summarize_psd(compute_psd(data, 1000.0, channels, config))["channel"]
    config["parameterization"]["enabled"] = True
    result = fit_channel_psd_table(psd, config)
    assert not result["model"].empty
    assert (result["model"]["fit_status"] == "ok").all()
    assert result["model"]["r_squared"].notna().all()
    assert result["model"]["exponent"].notna().all()
    assert not result["peaks"].empty
    assert not result["curves"].empty
    assert {
        "observed_power",
        "full_model_power",
        "aperiodic_power",
        "periodic_component_log10_additive",
        "residual_log10",
    }.issubset(result["curves"].columns)


def test_fooof_compatibility_backend_populates_same_outputs():
    pytest.importorskip("fooof")
    data, channels = make_synthetic_epochs(n_epochs=6, n_channels=2, n_times=5000, seed=13)
    config = {
        "psd": {"fmin_hz": 1.0, "fmax_hz": 150.0, "nperseg": 1000, "noverlap": 500, "window": "hann", "detrend": "constant", "scaling": "density", "average": "mean"},
        "parameterization": {
            "enabled": True,
            "backend": "fooof",
            "aperiodic_mode": "fixed",
            "fit_range_hz": [2.0, 150.0],
            "peak_width_limits_hz": [1.0, 12.0],
            "max_n_peaks": 6,
            "min_peak_height": 0.0,
            "min_peak_prominence": 0.0,
            "min_r_squared": 0.90,
        },
    }
    psd = summarize_psd(compute_psd(data, 1000.0, channels, config))["channel"]
    result = fit_channel_psd_table(psd, config)
    assert (result["model"]["backend_used"] == "FOOOF").all()
    assert (result["model"]["fit_status"] == "ok").all()
    assert not result["curves"].empty


def test_specparam_recovers_known_aperiodic_exponent_and_peak_frequency():
    pytest.importorskip("specparam")
    frequencies = np.arange(1.0, 151.0)
    log_power = -2.0 - 1.5 * np.log10(frequencies)
    log_power += 0.6 * np.exp(-0.5 * ((frequencies - 40.0) / 4.0) ** 2)
    config = {
        "parameterization": {
            "backend": "specparam",
            "aperiodic_mode": "fixed",
            "fit_range_hz": [2.0, 150.0],
            "peak_width_limits_hz": [1.0, 12.0],
            "max_n_peaks": 3,
            "min_peak_height": 0.0,
            "min_peak_prominence": 0.0,
            "min_r_squared": 0.99,
        }
    }
    base, peaks, model, curves = fit_single_psd_detailed(
        frequencies,
        10**log_power,
        config,
        {"channel_name": "synthetic_known_peak"},
    )
    assert base["fit_status"] == "ok"
    assert abs(base["exponent"] - 1.5) < 0.02
    assert abs(peaks.iloc[0]["center_frequency_hz"] - 40.0) < 1.0
    assert model.iloc[0]["r_squared"] > 0.99
    assert len(curves) == 149


def test_connectivity_runs_across_epochs_with_region_pairs():
    data, channels = make_synthetic_epochs(n_epochs=6, n_channels=4, n_times=5000, seed=11)
    quality_config = {"quality": {"line_noise_hz": [], "flat_std_threshold": 1e-15, "max_abs_z_threshold": 20, "saturation_fraction_threshold": 0.01}}
    quality = assess_quality(data, 1000.0, channels, quality_config)
    channel_table = pd.DataFrame({"array_index": range(4), "channel_name": channels, "region": ["R1", "R1", "R2", "R2"]})
    config = {"connectivity": {"methods": ["imcoh", "wpli2_debiased", "coh"], "mode": "fourier", "fmin_hz": 1.0, "fmax_hz": 100.0, "min_epochs": 5}}
    result = compute_connectivity(data, 1000.0, channel_table, quality["epoch"], config)
    assert result["status"] == "ok"
    assert not result["spectrum"].empty
    assert (result["spectrum"]["n_epochs"] == 6).all()


def test_multivariate_connectivity_and_wpli_keep_distinct_output_grains():
    data, channels = make_synthetic_epochs(n_epochs=6, n_channels=4, n_times=5000, seed=21)
    config = {
        "quality": {"line_noise_hz": [], "flat_std_threshold": 1e-15, "max_abs_z_threshold": 20, "saturation_fraction_threshold": 0.01},
        "connectivity": {
            "methods": ["mic", "mim", "wpli2_debiased"],
            "mode": "multitaper",
            "fmin_hz": 2.0,
            "fmax_hz": 30.0,
            "mt_bandwidth_hz": 4.0,
            "mt_adaptive": False,
            "mt_low_bias": True,
            "min_epochs": 5,
            "rank_sensitivity_enabled": False,
            "stability_enabled": False,
            "exclude_line_noise_hz": [],
        },
        "bands": {"theta": [4.0, 8.0], "alpha": [8.0, 12.0]},
        "expected_data": {"preprocessed_highpass_hz": 1.0, "preprocessed_lowpass_hz": 200.0},
    }
    quality = assess_quality(data, 1000.0, channels, config)
    channel_table = pd.DataFrame({"array_index": range(4), "channel_name": channels, "region": ["M1", "M1", "STR", "STR"]})
    result = compute_connectivity(data, 1000.0, channel_table, quality["epoch"], config)
    assert result["status"] == "ok"
    assert set(result["region_summary"]["method"]) == {"mic", "mim", "wpli2_debiased"}
    assert set(result["spectrum"].loc[result["spectrum"]["method"] == "mic", "aggregation_level"]) == {"multivariate_region_pair"}
    wpli = result["spectrum"].loc[result["spectrum"]["method"] == "wpli2_debiased"]
    assert set(wpli["aggregation_level"]) == {"cross_region_channel_pair"}
    assert wpli[["seed_channel", "target_channel"]].drop_duplicates().shape[0] == 4
    assert result["spectrum"].loc[result["spectrum"]["method"] == "mic", "value_strength"].ge(0).all()


def test_redundancy_rule_reduces_exactly_repeated_channels():
    rng = np.random.default_rng(31)
    data = rng.normal(size=(6, 4, 1000))
    data[:, 1] = data[:, 0]
    data[:, 3] = data[:, 2]
    channel_table = pd.DataFrame({"array_index": range(4), "channel_name": ["a1", "a2", "b1", "b2"], "region": ["M1", "M1", "STR", "STR"]})
    config = {"connectivity": {"rank_relative_tolerance": 1e-6, "rank_variance_threshold": 0.99}}
    result = assess_region_redundancy(data, 1000.0, channel_table, np.ones(6, dtype=bool), config)
    assert (result["summary"]["numerical_rank"] == 1).all()
    assert (result["summary"]["selected_rank"] == 1).all()


def test_connectivity_calibration_distinguishes_lagged_from_instantaneous_and_independent():
    """Calibration only: a known phase lag should exceed zero-lag mixing."""

    def make_case(kind: str, noise: float = 0.4, seed: int = 42):
        rng = np.random.default_rng(seed)
        n_epochs, n_times, sfreq = 10, 5000, 1000.0
        times = np.arange(n_times) / sfreq
        data = np.zeros((n_epochs, 4, n_times), dtype=float)
        for epoch in range(n_epochs):
            phase = rng.uniform(0, 2 * np.pi)
            source_a = np.sin(2 * np.pi * 10 * times + phase)
            source_b = np.sin(2 * np.pi * 18 * times + 0.7 * phase)
            if kind == "lagged":
                target_a = np.roll(source_a, 25)
                target_b = np.roll(source_b, 25)
            elif kind == "instantaneous":
                target_a = source_a
                target_b = source_b
            elif kind == "independent":
                target_a = np.sin(2 * np.pi * 13 * times + rng.uniform(0, 2 * np.pi))
                target_b = np.sin(2 * np.pi * 22 * times + rng.uniform(0, 2 * np.pi))
            else:
                raise ValueError(kind)
            data[epoch] = [
                source_a + noise * rng.normal(size=n_times),
                source_b + noise * rng.normal(size=n_times),
                target_a + noise * rng.normal(size=n_times),
                target_b + noise * rng.normal(size=n_times),
            ]
        return data, sfreq

    channel_names = ["c0", "c1", "c2", "c3"]
    channel_table = pd.DataFrame(
        {"array_index": range(4), "channel_name": channel_names, "region": ["M1", "M1", "STR", "STR"]}
    )
    config = {
        "connectivity": {
            "methods": ["mic", "mim", "wpli2_debiased"],
            "mode": "multitaper",
            "fmin_hz": 2.0,
            "fmax_hz": 40.0,
            "mt_bandwidth_hz": 4.0,
            "mt_adaptive": False,
            "mt_low_bias": True,
            "min_epochs": 5,
            "rank_sensitivity_enabled": False,
            "stability_enabled": False,
            "exclude_line_noise_hz": [],
        },
        "bands": {"alpha": [8.0, 12.0]},
        "expected_data": {"preprocessed_highpass_hz": 1.0, "preprocessed_lowpass_hz": 200.0},
    }

    def estimate(kind: str, noise: float = 0.4):
        data, sfreq = make_case(kind, noise=noise)
        quality = assess_quality(
            data,
            sfreq,
            channel_names,
            {"quality": {"line_noise_hz": [], "flat_std_threshold": 1e-15, "max_abs_z_threshold": 20, "saturation_fraction_threshold": 0.01}},
        )
        result = compute_connectivity(data, sfreq, channel_table, quality["epoch"], config)
        assert result["status"] == "ok"
        band = result["band_summary"].set_index("method")["value_raw_or_summary"]
        return band, result

    independent, _ = estimate("independent")
    instantaneous, _ = estimate("instantaneous")
    lagged, lagged_result = estimate("lagged")
    low_noise, _ = estimate("lagged", noise=0.2)
    high_noise, _ = estimate("lagged", noise=1.5)

    assert lagged["mic"] > instantaneous["mic"] + 0.5
    assert lagged["mim"] > instantaneous["mim"] + 0.5
    assert lagged["mic"] > independent["mic"] + 0.5
    assert lagged["mim"] > independent["mim"] + 0.5
    assert low_noise["mim"] > high_noise["mim"]
    wpli = lagged_result["spectrum"].query("method == 'wpli2_debiased'")
    assert np.allclose(wpli["value_raw"], wpli["value_strength"], equal_nan=True)
