from __future__ import annotations

from pathlib import Path

import pandas as pd

from lfp_analysis import plotting
from lfp_analysis.analysis_help_content import (
    FIGURES,
    HELP_TOPICS,
    TABLE_SCHEMAS,
    field_description,
)
from scripts.build_analysis_docs import build_all


def test_help_catalog_covers_every_documented_output_field_and_figure() -> None:
    assert {"workflow", "raw_quality", "psd", "band_power", "parameterization", "connectivity", "time_delay", "saved_results"} <= set(HELP_TOPICS)
    assert len(FIGURES) >= 15
    for figure in FIGURES:
        assert figure["title"] and figure["function"] and figure["fields"] and figure["short"] and figure["detail"]
    for info in TABLE_SCHEMAS.values():
        for field in info["fields"].split(","):
            assert field_description(field.strip()).strip()


def test_catalog_contains_real_pipeline_output_tables_and_parameters() -> None:
    required = {
        "metadata_validation.csv",
        "quality_file.csv",
        "psd_epoch_channel.csv",
        "band_power_epoch_channel.csv",
        "parameterization_model.csv",
        "parameterization_failures.csv",
        "connectivity_spectrum.csv",
        "connectivity_region_summary.csv",
        "connectivity_display_spectrum.csv",
        "time_delay_spectrum.csv",
        "time_delay_band_summary.csv",
    }
    assert required <= set(TABLE_SCHEMAS)
    fit_fields = set(TABLE_SCHEMAS["parameterization_model.csv"]["fields"].split(","))
    assert {"offset", "exponent", "knee", "r_squared", "error", "fit_status", "peak_status"} <= fit_fields
    conn_fields = set(TABLE_SCHEMAS["connectivity_spectrum.csv"]["fields"].split(","))
    assert {"value_raw", "value_strength", "direction_order", "frequency_is_masked_for_analysis"} <= conn_fields


def test_generated_markdown_matches_canonical_help_source() -> None:
    root = Path(__file__).resolve().parents[1]
    expected = build_all()
    assert expected.keys() == {"ANALYSIS_GUIDE.md", "RESULT_DATA_DICTIONARY.md", "FIGURE_RESULT_INDEX.md"}
    for name, content in expected.items():
        assert (root / "docs" / name).read_text(encoding="utf-8") == content


def test_psd_and_band_power_plot_units_are_explicit(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, list[str]] = {}

    def capture(fig, _output_base, dpi=150):
        captured["labels"] = [axis.get_ylabel() for axis in fig.axes]
        import matplotlib.pyplot as plt

        plt.close(fig)
        return tmp_path / "figure.png", tmp_path / "figure.svg"

    monkeypatch.setattr(plotting, "_save", capture)
    psd = pd.DataFrame(
        {"channel_name": ["A1"], "region": ["CTX"], "frequency_hz": [10.0], "psd_value": [2e-6]}
    )
    plotting.plot_psd(psd, tmp_path / "psd")
    assert "source unit²/Hz" in captured["labels"][0]

    bands = pd.DataFrame(
        {
            "channel_name": ["A1"],
            "region": ["CTX"],
            "band": ["theta"],
            "absolute_power": [3e-6],
            "absolute_power_unit": ["V^2"],
        }
    )
    plotting.plot_band_power(bands, tmp_path / "band")
    assert captured["labels"] == ["Absolute power (V^2)"]


def test_help_dialog_starts_compact_and_expands_details(monkeypatch) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6 import QtWidgets

    from lfp_analysis.analysis_help import AnalysisHelpDialog

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    dialog = AnalysisHelpDialog("psd")
    assert dialog.short_label.text() == HELP_TOPICS["psd"]["short"]
    assert dialog.detail_browser.isHidden()
    dialog.detail_button.setChecked(True)
    assert not dialog.detail_browser.isHidden()
    assert "PSD" in dialog.detail_browser.toPlainText()
    dialog.close()
    app.processEvents()
