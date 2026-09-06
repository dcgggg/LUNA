import pandas as pd

from lfp_analysis.config import load_config
from lfp_analysis.connectivity import compute_connectivity
from lfp_analysis.parameterization import fit_channel_psd_table
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
