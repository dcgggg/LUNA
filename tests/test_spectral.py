import numpy as np

from lfp_analysis.quality import assess_quality
from lfp_analysis.spectral import compute_band_power, compute_psd, summarize_psd
from lfp_analysis.synthetic import make_synthetic_epochs


def _config():
    return {
        "quality": {"line_noise_hz": [], "flat_std_threshold": 1e-15, "max_abs_z_threshold": 20, "saturation_fraction_threshold": 0.01},
        "psd": {"fmin_hz": 1, "fmax_hz": 100, "nperseg": 1000, "noverlap": 500, "window": "hann", "detrend": "constant", "scaling": "density", "average": "mean"},
        "bands": {"theta": [4, 8], "alpha": [8, 12], "low_gamma": [30, 55]},
        "relative_power": {"denominator_hz": [1, 100], "exclude_line_noise_hz": []},
    }


def test_synthetic_frequency_identification_and_band_power():
    data, channels = make_synthetic_epochs(n_epochs=4, n_channels=2, seed=4)
    config = _config()
    quality = assess_quality(data, 1000.0, channels, config)
    assert quality["file"]["effective_valid_duration_s"].iloc[0] == 20.0
    psd = compute_psd(data, 1000.0, channels, config)
    summaries = summarize_psd(psd)["channel"]
    peak_frequencies = summaries.loc[summaries.groupby("channel_name")["psd_value"].idxmax(), "frequency_hz"]
    assert np.all(np.abs(peak_frequencies.to_numpy() - 10.0) <= 2.0)
    bands = compute_band_power(psd, config)
    alpha = bands.loc[bands["band"] == "alpha", "absolute_power"]
    theta = bands.loc[bands["band"] == "theta", "absolute_power"]
    assert alpha.mean() > theta.mean()


def test_nonfinite_epoch_is_flagged_and_psd_is_not_silently_filled():
    data, channels = make_synthetic_epochs(n_epochs=2, n_channels=2, seed=5)
    data[1, 0, 0] = np.nan
    config = _config()
    quality = assess_quality(data, 1000.0, channels, config)
    assert (quality["epoch_channel"]["quality_flags"].str.contains("nonfinite")).any()
    psd = compute_psd(data, 1000.0, channels, config)
    assert (psd["status"] == "skipped_nonfinite").any()

