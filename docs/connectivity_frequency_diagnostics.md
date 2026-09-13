# Connectivity frequency diagnostics

LUNA keeps the estimator output in `connectivity_spectrum.csv` and records
frequency handling separately. `connectivity_frequency_diagnostics.csv` has
one row per method and frequency and reports the zero-based plot frequency
index plus the number of total, finite,
NaN, and Inf values, whether the bin is marked, the processing stage, and the
configuration source.

The default policy is one 50 Hz line-noise source with a 1 Hz full-width
interval. Harmonics are enabled, so a 100 Hz harmonic can be marked when it
falls inside the configured range. 60 Hz is not inferred. To use a 60 Hz
source, configure it explicitly with the legacy list or use a separate source
policy in the YAML configuration.

```yaml
connectivity:
  line_noise:
    frequency_hz: 50.0
    mask_width_hz: 1.0
    harmonics: true
    mask_for_analysis: true
    mask_for_plot: true
```

The estimator still receives the aligned, discontinuous time-domain epochs.
Masking is an annotation used for plot visibility and configured band
summaries; raw frequency rows remain in the output. No NaN or Inf is replaced
with zero. Optional frequency binning and display-only Gaussian smoothing are
disabled by default. If enabled, each operates within continuous valid
segments and never crosses a marked frequency interval. Smoothed values are
saved separately in `connectivity_display_spectrum.csv` and are not used for
raw band statistics.

`connectivity_roughness.csv` reports the median absolute adjacent difference,
total variation, coefficient of variation, and segment-level resampling
variability on the raw unmasked spectrum. `connectivity_band_cv.csv` adds the
within-band coefficient of variation for each configured band. These are
diagnostics for visual jaggedness, not inferential statistics.

The GUI spectrum selector distinguishes `全频谱＋标记频段` from `仅显示选定频段`; changing it only redraws an existing result. The shaded line-noise
interval is a quality annotation, not evidence that the estimator returned a
gap.

The GUI treats the line-noise marker and plot exclusion as independent display
controls. The marker is off by default and only adds a shaded annotation. Plot
exclusion is also off by default and is the only display option that inserts
NaNs and creates visual line breaks. Neither option changes the saved raw
spectrum or the configured band-summary mask.

## Estimator-call audit

Every invocation of the installed `mne_connectivity.spectral_connectivity_epochs`
backend is recorded in `connectivity_estimation_calls.csv`. The table includes
the analysis task ID, purpose (`main`, `rank_sensitivity`, or
`segment_stability`), ordered region pair, array indices on each side, method,
input shape, epoch duration, frequency range, multitaper bandwidth and DPSS
taper count, returned frequency grid, elapsed time, status, and any error.

`cache_hit` is currently `false` with `cache_status=no_estimator_cache_configured`:
the project does not silently reuse an estimator result. Calls made by rank and
segment stability diagnostics are expected additional estimates; they are
separately labelled so they can be distinguished from the main result. GUI
display-only refreshes use the saved tables and do not invoke the estimator.
