from __future__ import annotations

import numpy as np
import pandas as pd

from lfp_analysis.band_power_plots import (
    ordered_channels,
    plot_comparison,
    plot_overview,
    prepare_band_power,
)


def _band_table(include_epochs: bool = True) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for epoch_index in (0, 1) if include_epochs else (None,):
        for physical, name, region, delta, theta in (
            (17, "PF17", "PF", 3.0, 1.0),
            (1, "M1-1", "M1", 2.0, 4.0),
            (21, "SNr21", "SNr", 5.0, 2.0),
        ):
            for band, low, high, value in (("theta", 4.0, 8.0, theta), ("delta", 1.0, 4.0, delta)):
                rows.append(
                    {
                        **({"epoch_index": epoch_index} if include_epochs else {"n_epochs": 2}),
                        "channel_array_index": physical - 1,
                        "channel_name": name,
                        "physical_channel_number": physical,
                        "region": region,
                        "band": band,
                        "band_low_hz": low,
                        "band_high_hz": high,
                        "absolute_power": value + (0.5 if epoch_index == 1 else 0.0),
                        "relative_power": 0.1,
                        "status": "ok",
                    }
                )
    return pd.DataFrame(rows)


def test_band_power_uses_physical_channel_order_and_epoch_summary() -> None:
    prepared = prepare_band_power({"band_power": _band_table()})
    channels = ordered_channels(prepared["summary"])
    assert [row["physical_channel_number"] for row in channels] == ["1", "17", "21"]
    delta = prepared["summary"].query("band == 'delta' and channel_name == 'M1-1'").iloc[0]
    assert delta["raw_value"] == 2.25
    assert delta["n_epochs"] == 2


def test_band_power_summary_only_table_is_supported() -> None:
    prepared = prepare_band_power({"band_power_summary": _band_table(include_epochs=False)})
    assert not prepared["summary"].empty
    assert set(prepared["summary"]["n_epochs"]) == {2}


def test_band_power_plots_keep_two_requested_plot_structures() -> None:
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib.figure import Figure

    prepared = prepare_band_power({"band_power": _band_table()})
    overview = Figure(figsize=(6, 4))
    overview_axis = overview.add_subplot(111)
    info = plot_overview(overview_axis, overview, prepared, "absolute", "linear", "M1-1", "delta", False, "test")
    comparison = Figure(figsize=(6, 4))
    comparison_axis = comparison.add_subplot(111)
    plot_comparison(comparison_axis, prepared, "channel", "absolute", "linear", "M1-1", "delta", False, "test")
    assert len(info["channels"]) == 3
    assert len(overview.axes) == 2  # heatmap plus one colorbar
    assert len(comparison.axes) == 1
    assert np.isfinite(info["matrix"]).all()
