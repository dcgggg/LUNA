"""LUNA PySide6 desktop application for interactive LFP analysis.

The window is deliberately a thin client over :mod:`gui_engine`: all numeric
work remains in the existing analysis modules and the worker thread never
touches Qt widgets directly.
"""

from __future__ import annotations

import copy
import json
import sys
import threading
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from PySide6 import QtCore, QtGui, QtSvg, QtWidgets

from .app_info import (
    APP_DESCRIPTION,
    APP_FULL_NAME,
    APP_NAME,
    APP_VERSION,
    DEFAULT_CONFIG_FILENAME,
    DEFAULT_MAPPING_FILENAME,
    DEFAULT_OUTPUT_DIRNAME,
    window_title,
)
from .band_power_plots import (
    band_label,
    ordered_bands,
    ordered_channels,
    plot_comparison,
    plot_overview,
    power_label,
    prepare_band_power,
)
from .colors import (
    DEFAULT_COLOR_TEMPLATE,
    available_color_templates,
    channel_colors,
    color_template_label,
    region_color,
)
from .config import load_config
from .connectivity_gui import ConnectivityView
from .fooof_plots import (
    normalize_bands,
    plot_aperiodic_details,
    plot_fooof_overview,
    plot_peak_distribution,
    plot_peak_parameters,
    plot_periodic_curves,
    plot_periodic_heatmap,
    plot_single_channel_detail,
    prepare_fooof,
)
from .fooof_plots import ordered_channels as ordered_fooof_channels
from .gui_engine import (
    inspect_file,
    load_saved_run,
    resolve_manifest_path,
    run_gui_analysis,
)
from .gui_layout import AdaptiveStackedWidget, PlotScrollArea, install_wheel_focus_guard
from .gui_specs import (
    PARAMETER_DEFINITIONS,
    config_value,
    parameter_schema,
    set_config_value,
    validate_snapshot,
)
from .mapping import (
    DEFAULT_TEMPLATE_REGIONS,
    apply_mapping,
    load_mapping,
    mapping_rows,
    region_order,
    region_pairs,
    save_mapping,
    validate_mapping,
)
from .resources import packaged_resource_path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
HEADER_CONTENT_WIDTH = 1120
HEADER_PANEL_HEIGHT = 122
GLOBAL_ACTION_HEIGHT = 32
RESULT_PAGE_MIN_HEIGHT = 340
# Kept as a compatibility constant for external callers; a collapsed table now
# occupies no height and is not populated until the user expands it.
RESULT_TABLE_PREVIEW_HEIGHT = 0
RESULT_TABLE_EXPANDED_HEIGHT = 320
INDICATORS = ("Quality", "PSD", "Band Power", "FOOOF", "MIC", "MIM", "wpli", "dpli", "wpli2_debiased", "Time Delay")


# Qt styling is kept here, instead of being scattered across individual pages,
# so the analysis views remain responsible only for scientific plotting.
GUI_COLORS = {
    "window": "#f4f6f8",
    "surface": "#ffffff",
    "surface_alt": "#f8fafc",
    "border": "#d6dce3",
    "text": "#1f2933",
    "muted": "#5f6b76",
    "accent": "#1769aa",
    "accent_hover": "#12588f",
    "accent_pressed": "#0d466f",
    "danger": "#b42318",
}


class FlowLayout(QtWidgets.QLayout):
    """Small wrapping layout used for compact, non-scrolling checkbox rows."""

    def __init__(self, parent: QtWidgets.QWidget | None = None, margin: int = 0, hspacing: int = 8, vspacing: int = 4) -> None:
        super().__init__(parent)
        self._items: list[QtWidgets.QLayoutItem] = []
        self._hspacing = hspacing
        self._vspacing = vspacing
        self.setContentsMargins(margin, margin, margin, margin)

    def addItem(self, item: QtWidgets.QLayoutItem) -> None:
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int) -> QtWidgets.QLayoutItem | None:
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index: int) -> QtWidgets.QLayoutItem | None:
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self) -> QtCore.Qt.Orientation:
        return QtCore.Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._do_layout(QtCore.QRect(0, 0, width, 0), True)

    def setGeometry(self, rect: QtCore.QRect) -> None:
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self) -> QtCore.QSize:
        return self.minimumSize()

    def minimumSize(self) -> QtCore.QSize:
        size = QtCore.QSize(0, 0)
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        return size + QtCore.QSize(margins.left() + margins.right(), margins.top() + margins.bottom())

    def _do_layout(self, rect: QtCore.QRect, test_only: bool) -> int:
        margins = self.contentsMargins()
        effective = rect.adjusted(margins.left(), margins.top(), -margins.right(), -margins.bottom())
        x = effective.x()
        y = effective.y()
        line_height = 0
        for item in self._items:
            size = item.sizeHint()
            next_x = x + size.width() + (self._hspacing if line_height else 0)
            if next_x - self._hspacing > effective.right() and line_height:
                x = effective.x()
                y += line_height + self._vspacing
                next_x = x + size.width()
                line_height = 0
            if not test_only:
                item.setGeometry(QtCore.QRect(QtCore.QPoint(x, y), size))
            x = next_x
            line_height = max(line_height, size.height())
        return y + line_height - rect.y() + margins.bottom()


class FlowCheckBoxGroup(QtWidgets.QWidget):
    """Wrapping checkbox collection with a QListWidget-like count API."""

    changed = QtCore.Signal()

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.flow_layout = FlowLayout(hspacing=10, vspacing=5)
        self.setLayout(self.flow_layout)
        self._checks: list[tuple[QtWidgets.QCheckBox, Any]] = []

    def clear(self) -> None:
        while self.flow_layout.count():
            item = self.flow_layout.takeAt(0)
            if item is not None and item.widget() is not None:
                item.widget().deleteLater()
        self._checks.clear()
        self.updateGeometry()

    def add_item(self, text: str, data: Any, checked: bool = True, tooltip: str = "") -> None:
        checkbox = QtWidgets.QCheckBox(text)
        checkbox.setMinimumWidth(max(90, checkbox.fontMetrics().horizontalAdvance(text) + 30))
        checkbox.setToolTip(tooltip or text)
        checkbox.setChecked(checked)
        checkbox.stateChanged.connect(self.changed)
        self.flow_layout.addWidget(checkbox)
        self._checks.append((checkbox, data))

    def count(self) -> int:
        return len(self._checks)

    def checked_data(self) -> list[Any]:
        return [data for checkbox, data in self._checks if checkbox.isChecked()]

    def items(self) -> list[tuple[QtWidgets.QCheckBox, Any]]:
        return list(self._checks)


class CollapsiblePanel(QtWidgets.QWidget):
    """A compact section whose content can be folded without losing values."""

    def __init__(self, title: str, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(2)
        self.toggle = QtWidgets.QToolButton()
        self.toggle.setObjectName("panelToggle")
        self.toggle.setText(title)
        self.toggle.setCheckable(True)
        self.toggle.setChecked(True)
        self.toggle.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle.setArrowType(QtCore.Qt.ArrowType.DownArrow)
        self.toggle.toggled.connect(self._set_expanded)
        outer.addWidget(self.toggle)
        self.content = QtWidgets.QWidget()
        self.content_layout = QtWidgets.QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(8, 3, 8, 7)
        self.content_layout.setSpacing(7)
        outer.addWidget(self.content)

    def _set_expanded(self, expanded: bool) -> None:
        self.content.setVisible(bool(expanded))
        self.toggle.setArrowType(QtCore.Qt.ArrowType.DownArrow if expanded else QtCore.Qt.ArrowType.RightArrow)

    def setTitle(self, title: str) -> None:
        self.toggle.setText(title)


def _gui_stylesheet() -> str:
    """Return the compact, high-DPI-friendly Qt style for the application."""
    return f"""
    QMainWindow, QWidget {{
        background: {GUI_COLORS['window']};
        color: {GUI_COLORS['text']};
    }}
    QGroupBox {{
        background: {GUI_COLORS['surface']};
        border: 1px solid {GUI_COLORS['border']};
        border-radius: 6px;
        margin-top: 10px;
        padding: 12px 10px 10px 10px;
        font-weight: 600;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 10px;
        padding: 0 5px;
        color: {GUI_COLORS['text']};
    }}
    QLabel {{
        background: transparent;
    }}
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTableWidget, QListWidget,
    QPlainTextEdit {{
        background: {GUI_COLORS['surface']};
        border: 1px solid {GUI_COLORS['border']};
        border-radius: 4px;
        padding: 4px 6px;
        selection-background-color: #cfe8fb;
        selection-color: {GUI_COLORS['text']};
    }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus,
    QTableWidget:focus, QListWidget:focus, QPlainTextEdit:focus {{
        border: 1px solid {GUI_COLORS['accent']};
    }}
    QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {{
        min-height: 28px;
    }}
    QPushButton {{
        background: {GUI_COLORS['surface']};
        border: 1px solid {GUI_COLORS['border']};
        border-radius: 4px;
        min-height: 28px;
        padding: 4px 10px;
    }}
    QPushButton:hover {{
        background: #eef5fb;
        border-color: #8ab8da;
    }}
    QPushButton:pressed {{
        background: #dcecf8;
    }}
    QPushButton:checked {{
        background: #e2f0fb;
        border-color: {GUI_COLORS['accent']};
        color: {GUI_COLORS['accent_pressed']};
    }}
    QPushButton:disabled {{
        color: #9aa5af;
        background: #eef1f3;
    }}
    QPushButton#primaryAction, QPushButton#cancelAction,
    QPushButton#globalSecondaryAction {{
        min-height: 24px;
        max-height: 24px;
        padding: 3px 10px;
    }}
    QPushButton#primaryAction {{
        background: {GUI_COLORS['accent']};
        border-color: {GUI_COLORS['accent']};
        color: white;
        font-weight: 600;
    }}
    QPushButton#primaryAction:hover {{
        background: {GUI_COLORS['accent_hover']};
    }}
    QPushButton#cancelAction {{
        color: {GUI_COLORS['danger']};
    }}
    QToolButton#sectionToggle {{
        border: none;
        padding: 4px 6px;
        color: {GUI_COLORS['accent']};
    }}
    QToolButton#panelToggle {{
        background: {GUI_COLORS['surface']};
        border: 1px solid {GUI_COLORS['border']};
        border-radius: 6px;
        padding: 6px 8px;
        text-align: left;
        font-weight: 600;
        color: {GUI_COLORS['text']};
    }}
    QToolButton#panelToggle:hover {{
        background: #eef5fb;
        border-color: #8ab8da;
    }}
    QProgressBar {{
        min-height: 8px;
        max-height: 12px;
        border: 1px solid {GUI_COLORS['border']};
        border-radius: 5px;
        background: #e9edf1;
        text-align: center;
    }}
    QProgressBar::chunk {{
        background: {GUI_COLORS['accent']};
        border-radius: 4px;
    }}
    QTabWidget::pane {{
        border: 1px solid {GUI_COLORS['border']};
        background: {GUI_COLORS['surface']};
    }}
    QTabBar::tab {{
        background: #e9eef3;
        border: 1px solid {GUI_COLORS['border']};
        padding: 6px 10px;
    }}
    QTabBar::tab:selected {{
        background: {GUI_COLORS['surface']};
        color: {GUI_COLORS['accent_pressed']};
    }}
    QHeaderView::section {{
        background: #eef2f5;
        border: none;
        border-bottom: 1px solid {GUI_COLORS['border']};
        padding: 4px 6px;
        font-weight: 600;
    }}
    QSplitter::handle {{
        background: #d9e0e7;
    }}
    QToolTip {{
        background: #263238;
        color: white;
        border: 1px solid #455a64;
        padding: 5px;
    }}
    """


def _load_windows_cjk_font() -> str | None:
    """Load a bundled system CJK font when Qt does not expose Windows fonts."""
    for candidate in (
        Path(r"C:\Windows\Fonts\Noto Sans SC (TrueType).otf"),
        Path(r"C:\Windows\Fonts\simhei.ttf"),
        Path(r"C:\Windows\Fonts\Deng.ttf"),
    ):
        if not candidate.is_file():
            continue
        font_id = QtGui.QFontDatabase.addApplicationFont(str(candidate))
        families = QtGui.QFontDatabase.applicationFontFamilies(font_id)
        if families:
            return str(families[0])
    return None


class AnalysisWorker(QtCore.QObject):
    progress = QtCore.Signal(str, int)
    result = QtCore.Signal(object)
    finished = QtCore.Signal(object)

    def __init__(self, snapshot: dict[str, Any], config_path: Path, metadata_dir: Path) -> None:
        super().__init__()
        self.snapshot = copy.deepcopy(snapshot)
        self.config_path = config_path
        self.metadata_dir = metadata_dir
        self.cancel_event = threading.Event()
        self.task_id = str(self.snapshot.get("run_id", f"analysis_{time.time_ns()}"))

    @QtCore.Slot()
    def run(self) -> None:
        try:
            outcome = run_gui_analysis(
                self.snapshot,
                self.config_path,
                self.metadata_dir,
                progress=lambda message, percent: self.progress.emit(message, int(percent)),
                result_callback=lambda payload: self.result.emit({**payload, "task_id": self.task_id}),
                cancel_event=self.cancel_event,
            )
        except Exception as exc:  # noqa: BLE001 - worker forwards all failures
            outcome = {"run_dir": "", "manifest": {"status": "failed", "errors": [f"{type(exc).__name__}: {exc}"]}}
        self.finished.emit(outcome)


class InspectWorker(QtCore.QObject):
    finished = QtCore.Signal(object)
    failed = QtCore.Signal(object)

    def __init__(self, paths: list[str], metadata_dir: Path, config_path: Path) -> None:
        super().__init__()
        self.paths = paths
        self.metadata_dir = metadata_dir
        self.config_path = config_path
        self.task_id = f"inspect_{time.time_ns()}"

    @QtCore.Slot()
    def run(self) -> None:
        try:
            self.finished.emit({
                "task_id": self.task_id,
                "infos": [inspect_file(path, self.metadata_dir, self.config_path) for path in self.paths],
            })
        except Exception as exc:  # noqa: BLE001 - display the readable error
            self.failed.emit({"task_id": self.task_id, "message": f"{type(exc).__name__}: {exc}"})


class ResultCanvas(FigureCanvasQTAgg):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        self.figure = Figure(figsize=(9, 5), tight_layout=False)
        # The bundled Matplotlib style enables autolayout; GUI figures use
        # explicit margins so that resize/redraw does not emit tight-layout
        # warnings or clip labels.
        self.figure.set_layout_engine(None)
        self.color_template = DEFAULT_COLOR_TEMPLATE
        super().__init__(self.figure)
        self.setParent(parent)

    def show_payload(self, payload: dict[str, Any]) -> None:
        self.figure.clear()
        axis = self.figure.add_subplot(111)
        metric = str(payload.get("metric", "Result"))
        tables = payload.get("tables", {})
        file_id = payload.get("file_id", "")
        if metric == "Raw Waveform":
            data = np.asarray(payload.get("raw_data", np.empty((0, 0))), dtype=float)
            channel_names = [str(value) for value in payload.get("channel_names", [])]
            epoch_index = int(payload.get("preview_epoch_index", 0))
            times = np.asarray(payload.get("times_s", []), dtype=float)
            if data.ndim == 2 and data.shape[0] and data.shape[1]:
                if not times.size:
                    sfreq = float(payload.get("sfreq", 1.0))
                    times = np.arange(data.shape[1], dtype=float) / sfreq + float(payload.get("tmin", 0.0))
                finite = np.isfinite(data)
                centered = data - np.nanmedian(data, axis=1, keepdims=True)
                centered[~finite] = np.nan
                q05 = np.nanpercentile(np.abs(centered), 5) if np.any(finite) else 0.0
                q95 = np.nanpercentile(np.abs(centered), 95) if np.any(finite) else 0.0
                scale = max(float(q95 - q05), float(np.nanmax(np.abs(centered))) * 0.25 if np.any(finite) else 0.0, np.finfo(float).eps)
                offsets = np.arange(data.shape[0], dtype=float)[::-1] * scale * 3.0
                metadata = tables.get("channel_table", pd.DataFrame())
                rows = []
                if isinstance(metadata, pd.DataFrame) and not metadata.empty:
                    rows = metadata.to_dict("records")
                by_name = {str(row.get("channel_name", "")): row for row in rows}
                fallback_rows = [{"channel_name": name, "region": "未映射"} for name in channel_names]
                colors_by_channel = channel_colors([by_name.get(name, fallback) for name, fallback in zip(channel_names, fallback_rows, strict=False)], self.color_template)
                for index, name in enumerate(channel_names):
                    axis.plot(times, centered[index] + offsets[index], linewidth=0.65, color=colors_by_channel.get(name, "#777777"), label=name)
                axis.set_yticks(offsets, channel_names)
                axis.set_xlabel("Epoch time (s)")
                axis.set_ylabel("Channel (vertical display offset)")
                axis.grid(True, color="#dddddd", linewidth=0.4)
                quality_epoch = tables.get("quality_epoch", pd.DataFrame())
                status = ""
                if isinstance(quality_epoch, pd.DataFrame) and not quality_epoch.empty and "epoch_index" in quality_epoch:
                    matched = quality_epoch.loc[quality_epoch["epoch_index"].astype(int) == epoch_index]
                    if not matched.empty:
                        status = f"；质量状态={matched.iloc[0].get('quality_status', '')}"
                axis.set_title(f"{file_id} | 原始波形 | epoch {epoch_index}{status}\n通道按垂直偏移显示，未改变原始数据")
            else:
                axis.text(0.5, 0.5, "没有可显示的原始波形；请至少勾选一个通道。", ha="center", va="center", transform=axis.transAxes)
        elif metric == "Quality":
            table = tables.get("quality_epoch_channel", pd.DataFrame())
            if not table.empty:
                matrix = table.pivot(index="epoch_index", columns="channel_name", values="issue_score").fillna(0)
                image = axis.imshow(matrix.to_numpy(float), aspect="auto", cmap="magma")
                axis.set_xlabel("Channel")
                axis.set_ylabel("Epoch")
                axis.set_xticks(np.arange(len(matrix.columns)), matrix.columns, rotation=90, fontsize=7)
                self.figure.colorbar(image, ax=axis, label="Quality issue score")
            else:
                axis.text(0.5, 0.5, "No quality result", ha="center", va="center", transform=axis.transAxes)
        elif metric == "PSD":
            table = tables.get("channel", pd.DataFrame())
            metadata = tables.get("channel_table", pd.DataFrame())
            rows = metadata.to_dict("records") if isinstance(metadata, pd.DataFrame) else []
            by_name = {str(row.get("channel_name", "")): row for row in rows}
            for channel, group in table.groupby("channel_name") if not table.empty else []:
                row = by_name.get(str(channel), {"channel_name": str(channel), "region": "未映射"})
                color = channel_colors([row], self.color_template).get(str(channel), "#777777")
                axis.plot(group["frequency_hz"], group["psd_value"], linewidth=0.85, color=color, label=str(channel))
            region_table = tables.get("region", pd.DataFrame())
            if isinstance(region_table, pd.DataFrame) and not region_table.empty and "region" in region_table.columns:
                for region, group in region_table.groupby("region", sort=False):
                    axis.plot(group["frequency_hz"], group["psd_value"], linewidth=1.5, color=region_color(region, self.color_template), label=f"{region} mean")
            axis.set_xlabel("Frequency (Hz)")
            axis.set_ylabel("PSD (source unit²/Hz)")
            axis.set_yscale("log")
            if not table.empty:
                axis.legend(fontsize=7, ncol=2)
        elif metric == "Band Power":
            table = tables.get("band_power_summary", pd.DataFrame())
            if table.empty:
                table = tables.get("band_power", pd.DataFrame())
            if not table.empty:
                summary = table.groupby("band", as_index=False)["absolute_power"].mean()
                axis.bar(summary["band"].astype(str), summary["absolute_power"])
                axis.set_ylabel("Mean absolute power (source unit²)")
                axis.tick_params(axis="x", rotation=45)
            else:
                axis.text(0.5, 0.5, "No band power result", ha="center", va="center", transform=axis.transAxes)
        elif metric == "FOOOF":
            table = tables.get("curves", pd.DataFrame())
            for channel, group in table.groupby("channel_name") if not table.empty else []:
                group = group.sort_values("frequency_hz")
                axis.plot(group["frequency_hz"], group["observed_power"], linewidth=0.7, label=f"{channel} PSD")
                axis.plot(group["frequency_hz"], group["full_model_power"], linewidth=0.9, linestyle="--", label=f"{channel} model")
            axis.set_xlabel("Frequency (Hz)")
            axis.set_ylabel("Power")
            axis.set_yscale("log")
            if not table.empty:
                axis.legend(fontsize=7, ncol=2)
        elif metric == "Connectivity":
            table = tables.get("region_summary", pd.DataFrame())
            for (region_a, region_b), group in table.groupby(["region_a", "region_b"]) if not table.empty else []:
                method = str(group["method"].iloc[0])
                axis.plot(group["frequency_hz"], group["value_strength"], linewidth=0.8, label=f"{method} {region_a}-{region_b}")
            axis.set_xlabel("Frequency (Hz)")
            axis.set_ylabel("Connection strength (method-specific)")
            if not table.empty:
                axis.legend(fontsize=7, ncol=2)
        elif metric == "Time Delay":
            table = tables.get("region_spectrum", pd.DataFrame())
            if not table.empty:
                pairs = list(table[["region_a", "region_b"]].drop_duplicates().itertuples(index=False, name=None))[:6]
                for region_a, region_b in pairs:
                    group = table.loc[(table["region_a"] == region_a) & (table["region_b"] == region_b) & table["antisymmetrized"].astype(bool)]
                    if not group.empty:
                        axis.plot(group["delay_ms"], group["estimate_strength"], linewidth=0.8, label=f"{region_a}-{region_b}")
                axis.set_xlabel("Delay (ms); positive = seed leads target")
                axis.set_ylabel("TDE estimate strength")
                axis.legend(fontsize=7, ncol=2)
            else:
                axis.text(0.5, 0.5, "No time-delay result", ha="center", va="center", transform=axis.transAxes)
        if not axis.get_title():
            axis.set_title(f"{file_id} | {metric}")
        axis.title.set_fontsize(10)
        axis.xaxis.label.set_fontsize(9)
        axis.yaxis.label.set_fontsize(9)
        axis.tick_params(axis="both", labelsize=8)
        legend = axis.get_legend()
        if legend is not None:
            for text in legend.get_texts():
                text.set_fontsize(8)
        self.figure.subplots_adjust(left=0.10, right=0.97, bottom=0.12, top=0.90)
        axis.grid(True, color="#dddddd", linewidth=0.4)
        self.draw_idle()


class BandPowerView(QtWidgets.QWidget):
    """Two-panel, presentation-only view over saved band-power tables."""

    export_requested = QtCore.Signal(str)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.payload: dict[str, Any] | None = None
        self.selected_channels: set[str] | None = None
        self.selected_regions: set[str] | None = None
        self._prepared: dict[str, pd.DataFrame] = {"epoch": pd.DataFrame(), "summary": pd.DataFrame()}
        self._overview_info: dict[str, Any] = {}
        self._compare_items: list[str] = []
        self._updating_controls = False
        self.color_template = DEFAULT_COLOR_TEMPLATE

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)
        controls = QtWidgets.QGridLayout()
        controls.setHorizontalSpacing(8)
        controls.setVerticalSpacing(6)
        self.power_combo = QtWidgets.QComboBox()
        self.power_combo.addItem("绝对功率", "absolute")
        self.power_combo.addItem("相对功率 (%)", "relative")
        self.scale_combo = QtWidgets.QComboBox()
        self.scale_combo.addItem("线性", "linear")
        self.scale_combo.addItem("对数", "log")
        self.aggregation_combo = QtWidgets.QComboBox()
        self.aggregation_combo.addItem("均值", "mean")
        self.aggregation_combo.addItem("中位数", "median")
        self.mode_combo = QtWidgets.QComboBox()
        self.mode_combo.addItem("比较通道", "channel")
        self.mode_combo.addItem("比较频带", "band")
        self.band_combo = QtWidgets.QComboBox()
        self.channel_combo = QtWidgets.QComboBox()
        self.show_values_check = QtWidgets.QCheckBox("热图显示数值")
        self.show_distribution_check = QtWidgets.QCheckBox("显示 epoch 分布")
        self.show_distribution_check.setChecked(True)
        self.selection_label = QtWidgets.QLabel("当前选择：—")
        self.selection_label.setWordWrap(True)
        controls.addWidget(QtWidgets.QLabel("功率"), 0, 0)
        controls.addWidget(self.power_combo, 0, 1)
        controls.addWidget(QtWidgets.QLabel("色标/纵轴"), 0, 2)
        controls.addWidget(self.scale_combo, 0, 3)
        controls.addWidget(QtWidgets.QLabel("epoch 汇总"), 0, 4)
        controls.addWidget(self.aggregation_combo, 0, 5)
        controls.addWidget(QtWidgets.QLabel("比较模式"), 1, 0)
        controls.addWidget(self.mode_combo, 1, 1)
        controls.addWidget(QtWidgets.QLabel("选择频带"), 1, 2)
        controls.addWidget(self.band_combo, 1, 3)
        controls.addWidget(QtWidgets.QLabel("选择通道"), 1, 4)
        controls.addWidget(self.channel_combo, 1, 5)
        controls.addWidget(self.show_values_check, 2, 0, 1, 2)
        controls.addWidget(self.show_distribution_check, 2, 2, 1, 2)
        controls.addWidget(self.selection_label, 2, 4, 1, 2)
        root.addLayout(controls)

        filter_row = QtWidgets.QHBoxLayout()
        filter_row.addWidget(QtWidgets.QLabel("频带筛选"))
        self.band_filter_list = FlowCheckBoxGroup()
        self.band_filter_list.setToolTip("勾选需要显示的频带；控件会随窗口宽度自动换行。")
        filter_row.addWidget(self.band_filter_list, stretch=1)
        for label, kind in (("导出热图", "overview"), ("导出比较图", "comparison"), ("导出组合图", "combined")):
            button = QtWidgets.QPushButton(label)
            button.clicked.connect(lambda _checked=False, value=kind: self.export_requested.emit(value))
            filter_row.addWidget(button)
        root.addLayout(filter_row)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        overview_panel = QtWidgets.QWidget()
        overview_layout = QtWidgets.QVBoxLayout(overview_panel)
        overview_layout.addWidget(QtWidgets.QLabel("通道 × 频带总览"))
        self.overview_figure = Figure(figsize=(9, 5.8), tight_layout=False)
        self.overview_figure.set_layout_engine(None)
        self.overview_canvas = FigureCanvasQTAgg(self.overview_figure)
        self.overview_canvas.setMinimumHeight(440)
        self.overview_toolbar = NavigationToolbar2QT(self.overview_canvas, self)
        self.overview_toolbar.setFixedHeight(34)
        overview_layout.addWidget(self.overview_toolbar)
        overview_layout.addWidget(self.overview_canvas, stretch=1)
        overview_panel.setMinimumHeight(500)
        splitter.addWidget(overview_panel)

        comparison_panel = QtWidgets.QWidget()
        comparison_layout = QtWidgets.QVBoxLayout(comparison_panel)
        comparison_layout.addWidget(QtWidgets.QLabel("当前选择的比较图"))
        self.comparison_figure = Figure(figsize=(9, 4.4), tight_layout=False)
        self.comparison_figure.set_layout_engine(None)
        self.comparison_canvas = FigureCanvasQTAgg(self.comparison_figure)
        self.comparison_canvas.setMinimumHeight(330)
        self.comparison_toolbar = NavigationToolbar2QT(self.comparison_canvas, self)
        self.comparison_toolbar.setFixedHeight(34)
        comparison_layout.addWidget(self.comparison_toolbar)
        comparison_layout.addWidget(self.comparison_canvas, stretch=1)
        comparison_panel.setMinimumHeight(390)
        splitter.addWidget(comparison_panel)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(6)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        splitter.setMinimumHeight(900)
        splitter.setSizes([510, 390])
        plot_content = QtWidgets.QWidget()
        plot_content_layout = QtWidgets.QVBoxLayout(plot_content)
        plot_content_layout.setContentsMargins(0, 0, 0, 0)
        plot_content_layout.addWidget(splitter)
        self.plot_scroll = PlotScrollArea(plot_content, minimum_content_height=910)
        root.addWidget(self.plot_scroll, stretch=1)

        for widget in (self.power_combo, self.scale_combo, self.aggregation_combo, self.mode_combo, self.band_combo, self.channel_combo, self.show_values_check, self.show_distribution_check):
            if isinstance(widget, QtWidgets.QComboBox):
                widget.currentIndexChanged.connect(self._controls_changed)
            else:
                widget.stateChanged.connect(self._controls_changed)
        self.band_filter_list.changed.connect(self._controls_changed)
        self.overview_canvas.mpl_connect("button_press_event", self._overview_clicked)
        self.comparison_canvas.mpl_connect("button_press_event", self._comparison_clicked)

    def set_payload(
        self,
        payload: dict[str, Any],
        selected_channels: list[str] | None = None,
        selected_regions: list[str] | None = None,
    ) -> None:
        self.payload = payload
        self.selected_channels = None if selected_channels is None else set(map(str, selected_channels))
        self.selected_regions = None if selected_regions is None else set(map(str, selected_regions))
        self._populate_controls()
        self._refresh(preserve_scroll=False)

    def set_filters(self, selected_channels: list[str] | None, selected_regions: list[str] | None) -> None:
        if self.payload is None:
            return
        self.selected_channels = None if selected_channels is None else set(map(str, selected_channels))
        self.selected_regions = None if selected_regions is None else set(map(str, selected_regions))
        self._refresh()

    def set_color_template(self, template: str) -> None:
        """Refresh only the display layer; band power is not recomputed."""
        self.color_template = template if template in available_color_templates() else DEFAULT_COLOR_TEMPLATE
        if self.payload is not None:
            self._refresh()

    def _tables(self) -> dict[str, pd.DataFrame]:
        return self.payload.get("tables", {}) if self.payload else {}

    def _all_prepared(self) -> dict[str, pd.DataFrame]:
        return prepare_band_power(
            self._tables(),
            power_kind=str(self.power_combo.currentData() or "absolute"),
            aggregation=str(self.aggregation_combo.currentData() or "mean"),
            selected_channels=self.selected_channels,
            selected_regions=self.selected_regions,
        )

    def _populate_controls(self) -> None:
        if self.payload is None:
            return
        self._updating_controls = True
        try:
            all_prepared = self._all_prepared()
            bands = ordered_bands(all_prepared["summary"])
            channels = ordered_channels(all_prepared["summary"])
            old_band = self.band_combo.currentData()
            old_channel = self.channel_combo.currentData()
            old_filters = set(map(str, self.band_filter_list.checked_data()))
            self.band_combo.clear()
            self.channel_combo.clear()
            self.band_filter_list.clear()
            for row in bands:
                self.band_combo.addItem(band_label(row), row["band"])
                self.band_filter_list.add_item(str(row["band"]), row["band"], checked=not old_filters or row["band"] in old_filters, tooltip=band_label(row))
            for row in channels:
                self.channel_combo.addItem(f"{row['channel_label']} ({row['region']})", row["channel_name"])
            if self.band_combo.count():
                index = self.band_combo.findData(old_band)
                self.band_combo.setCurrentIndex(max(index, 0))
            if self.channel_combo.count():
                index = self.channel_combo.findData(old_channel)
                self.channel_combo.setCurrentIndex(max(index, 0))
            is_relative = str(self.power_combo.currentData()) == "relative"
            if is_relative:
                self.scale_combo.setCurrentIndex(0)
            self.scale_combo.setEnabled(not is_relative)
        finally:
            self._updating_controls = False

    def _selected_band_names(self) -> list[str]:
        return [str(value) for value in self.band_filter_list.checked_data()]

    def _controls_changed(self, *_args: Any) -> None:
        if self._updating_controls:
            return
        if self.sender() is self.power_combo:
            self._populate_controls()
        self._refresh()

    def _refresh(self, *, preserve_scroll: bool = True) -> None:
        if self.payload is None:
            return
        scroll_position = self.plot_scroll.scroll_position() if preserve_scroll else None
        power_kind = str(self.power_combo.currentData() or "absolute")
        aggregation = str(self.aggregation_combo.currentData() or "mean")
        scale = str(self.scale_combo.currentData() or "linear")
        selected_bands = self._selected_band_names()
        self._prepared = prepare_band_power(
            self._tables(),
            power_kind=power_kind,
            aggregation=aggregation,
            selected_channels=self.selected_channels,
            selected_regions=self.selected_regions,
            selected_bands=selected_bands,
        )
        selected_band = self.band_combo.currentData()
        selected_channel = self.channel_combo.currentData()
        valid_bands = [row["band"] for row in ordered_bands(self._prepared["summary"])]
        valid_channels = [row["channel_name"] for row in ordered_channels(self._prepared["summary"])]
        if selected_band not in valid_bands:
            selected_band = valid_bands[0] if valid_bands else None
            if selected_band is not None:
                self._set_current_data(None, selected_band)
        if selected_channel not in valid_channels:
            selected_channel = valid_channels[0] if valid_channels else None
            if selected_channel is not None:
                self._set_current_data(selected_channel, None)
        file_id = str(self.payload.get("file_id", "file"))
        denominator = self._denominator_hz()
        unit_label = power_label(power_kind, denominator)
        self.overview_figure.clear()
        overview_axis = self.overview_figure.add_subplot(111)
        self._overview_info = plot_overview(
            overview_axis,
            self.overview_figure,
            self._prepared,
            power_kind=power_kind,
            scale=scale,
            selected_channel=str(selected_channel) if selected_channel else None,
            selected_band=str(selected_band) if selected_band else None,
            show_values=self.show_values_check.isChecked(),
            title=f"{file_id} | 频带功率总览 | {unit_label} | {aggregation}",
            denominator_hz=denominator,
            color_template=self.color_template,
        )
        self.overview_figure.subplots_adjust(left=0.14, right=0.92, bottom=0.22, top=0.88)
        self.overview_canvas.draw_idle()

        self.comparison_figure.clear()
        comparison_axis = self.comparison_figure.add_subplot(111)
        mode = str(self.mode_combo.currentData() or "channel")
        self._compare_items = [
            row["channel_name"] for row in ordered_channels(self._prepared["summary"])
        ] if mode == "channel" else [row["band"] for row in ordered_bands(self._prepared["summary"])]
        comparison_context = (
            f"频带：{selected_band or '—'}" if mode == "channel" else f"通道：{selected_channel or '—'}"
        )
        comparison_info = plot_comparison(
            comparison_axis,
            self._prepared,
            mode=mode,
            power_kind=power_kind,
            scale=scale,
            selected_channel=str(selected_channel) if selected_channel else None,
            selected_band=str(selected_band) if selected_band else None,
            show_epoch_distribution=self.show_distribution_check.isChecked(),
            title=f"{file_id} | {'比较通道' if mode == 'channel' else '比较频带'} | {comparison_context} | {unit_label}",
            denominator_hz=denominator,
            color_template=self.color_template,
        )
        self.comparison_figure.subplots_adjust(left=0.11, right=0.98, bottom=0.22, top=0.88)
        self.comparison_canvas.draw_idle()
        selected_value = comparison_info.get("selection_value", np.nan)
        selected_text = "—" if not np.isfinite(selected_value) else f"{float(selected_value):.5g}"
        selection_name = str(selected_band if mode == "channel" else selected_channel or "—")
        self.selection_label.setText(f"当前选择：{selection_name}；显示值={selected_text}；单位={unit_label}")
        if scroll_position is not None:
            self.plot_scroll.restore_scroll_position(scroll_position)

    def reset_plot_scroll(self) -> None:
        self.plot_scroll.reset_position()

    def _denominator_hz(self) -> tuple[float, float] | None:
        for table in (self._tables().get("band_power", pd.DataFrame()), self._tables().get("band_power_epoch_channel", pd.DataFrame()), self._tables().get("band_power_summary", pd.DataFrame())):
            if isinstance(table, pd.DataFrame) and not table.empty and {"relative_denominator_low_hz", "relative_denominator_high_hz"}.issubset(table.columns):
                row = table.iloc[0]
                return float(row["relative_denominator_low_hz"]), float(row["relative_denominator_high_hz"])
        return None

    def _overview_clicked(self, event: Any) -> None:
        if event.inaxes is None or event.xdata is None or event.ydata is None:
            return
        channels = self._overview_info.get("channels", [])
        bands = self._overview_info.get("bands", [])
        column = round(float(event.xdata))
        row = round(float(event.ydata))
        if not (0 <= row < len(channels) and 0 <= column < len(bands)):
            return
        self._set_current_data(channels[row]["channel_name"], bands[column]["band"])
        self._refresh()

    def _comparison_clicked(self, event: Any) -> None:
        if event.inaxes is None or event.xdata is None or not self._compare_items:
            return
        index = round(float(event.xdata))
        if not 0 <= index < len(self._compare_items):
            return
        if str(self.mode_combo.currentData()) == "channel":
            self._set_current_data(self._compare_items[index], self.band_combo.currentData())
        else:
            self._set_current_data(self.channel_combo.currentData(), self._compare_items[index])
        self._refresh()

    def _set_current_data(self, channel_name: str | None, band_name: str | None) -> None:
        self._updating_controls = True
        try:
            if channel_name is not None:
                index = self.channel_combo.findData(channel_name)
                if index >= 0:
                    self.channel_combo.setCurrentIndex(index)
            if band_name is not None:
                index = self.band_combo.findData(band_name)
                if index >= 0:
                    self.band_combo.setCurrentIndex(index)
        finally:
            self._updating_controls = False

    def save_figure(self, kind: str, path: str | Path) -> None:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        if kind == "overview":
            self.overview_figure.savefig(output, dpi=300)
            return
        if kind == "comparison":
            self.comparison_figure.savefig(output, dpi=300)
            return
        if kind != "combined":
            raise ValueError(f"Unknown band-power figure kind: {kind}")
        import matplotlib.pyplot as plt

        combined, axes = plt.subplots(2, 1, figsize=(10, 10), constrained_layout=False)
        power_kind = str(self.power_combo.currentData() or "absolute")
        scale = str(self.scale_combo.currentData() or "linear")
        mode = str(self.mode_combo.currentData() or "channel")
        selected_channel = self.channel_combo.currentData()
        selected_band = self.band_combo.currentData()
        unit_label = power_label(power_kind, self._denominator_hz())
        plot_overview(
            axes[0],
            combined,
            self._prepared,
            power_kind,
            scale,
            selected_channel,
            selected_band,
            self.show_values_check.isChecked(),
            f"{self.payload.get('file_id', 'file')} | 频带功率总览 | {unit_label}",
            self._denominator_hz(),
            color_template=self.color_template,
        )
        plot_comparison(
            axes[1],
            self._prepared,
            mode,
            power_kind,
            scale,
            selected_channel,
            selected_band,
            self.show_distribution_check.isChecked(),
            f"{self.payload.get('file_id', 'file')} | {'比较通道' if mode == 'channel' else '比较频带'} | {unit_label}",
            self._denominator_hz(),
            color_template=self.color_template,
        )
        combined.subplots_adjust(left=0.12, right=0.91, bottom=0.10, top=0.93, hspace=0.38)
        combined.savefig(output, dpi=300)
        plt.close(combined)

    def save_csv(self, path: str | Path) -> None:
        """Save the numerical values represented by the current two-panel view."""
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        export = self._prepared["summary"].copy()
        if export.empty:
            pd.DataFrame(
                columns=[
                    "channel_name",
                    "physical_channel_number",
                    "region",
                    "band",
                    "band_low_hz",
                    "band_high_hz",
                ]
            ).to_csv(output, index=False, encoding="utf-8-sig")
            return
        aggregation = str(self.aggregation_combo.currentData() or "mean")
        epoch_tables = {"band_power": self._prepared["epoch"]}
        for power_kind in ("absolute", "relative"):
            summary = prepare_band_power(epoch_tables, power_kind=power_kind, aggregation=aggregation)["summary"]
            keep = [
                "channel_name",
                "physical_channel_number",
                "region",
                "band",
                "band_low_hz",
                "band_high_hz",
                "raw_value",
                "n_epochs",
            ]
            summary = summary[[column for column in keep if column in summary.columns]].rename(
                columns={"raw_value": f"{power_kind}_power", "n_epochs": f"{power_kind}_n_epochs"}
            )
            keys = [
                "channel_name",
                "physical_channel_number",
                "region",
                "band",
                "band_low_hz",
                "band_high_hz",
            ]
            export = export.merge(summary, on=[key for key in keys if key in export.columns and key in summary.columns], how="left", suffixes=("", f"_{power_kind}"))
        export = export.rename(columns={"raw_value": "selected_raw_value"})
        power_kind = str(self.power_combo.currentData() or "absolute")
        export["selected_power_kind"] = power_kind
        export["selected_power_unit"] = "%" if power_kind == "relative" else "source unit²"
        export["display_scale"] = str(self.scale_combo.currentData() or "linear")
        export["aggregation"] = aggregation
        export["comparison_mode"] = str(self.mode_combo.currentData() or "channel")
        export["selected_channel"] = self.channel_combo.currentData() or ""
        export["selected_band"] = self.band_combo.currentData() or ""
        denominator = self._denominator_hz()
        export["relative_denominator_low_hz"] = denominator[0] if denominator else np.nan
        export["relative_denominator_high_hz"] = denominator[1] if denominator else np.nan
        export["source_file_id"] = str(self.payload.get("file_id", "")) if self.payload else ""
        export["color_template"] = self.color_template
        export.to_csv(output, index=False, encoding="utf-8-sig")


class FooofView(QtWidgets.QWidget):
    """Interactive FOOOF/specparam comparison and detail view."""

    export_requested = QtCore.Signal(str)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.payload: dict[str, Any] | None = None
        self.selected_channels: set[str] | None = None
        self.selected_regions: set[str] | None = None
        self.bands: list[dict[str, Any]] = []
        self.prepared: dict[str, Any] = prepare_fooof({}, [])
        self._updating_controls = False
        self._overview_info: dict[str, Any] = {}
        self._peak_points: list[dict[str, Any]] = []
        self.color_template = DEFAULT_COLOR_TEMPLATE

        root = QtWidgets.QVBoxLayout(self)
        controls = QtWidgets.QGridLayout()
        self.quality_combo = QtWidgets.QComboBox()
        self.quality_combo.addItem("全部拟合结果", False)
        self.quality_combo.addItem("仅质量通过", True)
        self.region_combo = QtWidgets.QComboBox()
        self.channel_combo = QtWidgets.QComboBox()
        self.band_combo = QtWidgets.QComboBox()
        self.peak_mode_combo = QtWidgets.QComboBox()
        self.peak_mode_combo.addItem("频段代表峰（PW最大）", "representative")
        self.peak_mode_combo.addItem("全部峰", "all")
        self.curve_mode_combo = QtWidgets.QComboBox()
        self.curve_mode_combo.addItem("去背景后的观测谱", "observed")
        self.curve_mode_combo.addItem("两者叠加", "overlay")
        self.curve_mode_combo.addItem("拟合周期成分", "model")
        self.layout_combo = QtWidgets.QComboBox()
        self.layout_combo.addItem("按脑区 2×2", "region")
        self.layout_combo.addItem("选定通道叠加", "overlay")
        self.unified_check = QtWidgets.QCheckBox("统一坐标")
        self.unified_check.setChecked(True)
        self.legend_check = QtWidgets.QCheckBox("显示图例")
        self.legend_check.setChecked(True)
        self.font_spin = QtWidgets.QSpinBox()
        self.font_spin.setRange(7, 16)
        self.font_spin.setValue(9)
        control_specs = (
            ("质量筛选", self.quality_combo),
            ("脑区曲线", self.region_combo),
            ("详情通道", self.channel_combo),
            ("比较频段", self.band_combo),
            ("峰选择", self.peak_mode_combo),
            ("曲线显示", self.curve_mode_combo),
            ("曲线布局", self.layout_combo),
            ("字号", self.font_spin),
        )
        for index, (label, widget) in enumerate(control_specs):
            row = index // 4
            column = (index % 4) * 2
            controls.addWidget(QtWidgets.QLabel(label), row, column)
            controls.addWidget(widget, row, column + 1)
        controls.addWidget(self.unified_check, 2, 0, 1, 2)
        controls.addWidget(self.legend_check, 2, 2, 1, 2)
        self.status_label = QtWidgets.QLabel("FOOOF 结果尚未载入")
        self.status_label.setWordWrap(True)
        self.status_label.setMaximumHeight(44)
        controls.addWidget(self.status_label, 2, 4, 1, 4)
        root.addLayout(controls)

        export_row = QtWidgets.QHBoxLayout()
        for label, kind in (("导出当前图", "current"), ("导出全部图", "all"), ("导出数值表", "tables")):
            button = QtWidgets.QPushButton(label)
            button.clicked.connect(lambda _checked=False, value=kind: self.export_requested.emit(value))
            export_row.addWidget(button)
        export_row.addStretch(1)
        root.addLayout(export_row)

        self.tabs = QtWidgets.QTabWidget()
        root.addWidget(self.tabs, stretch=1)
        self._page_scrolls: dict[str, PlotScrollArea] = {}
        self.overview_figure, self.overview_canvas = self._new_canvas("总览")
        self.aperiodic_figure, self.aperiodic_canvas, self.aperiodic_table = self._new_canvas_with_table("非周期参数")
        self.periodic_figure, self.periodic_canvas = self._new_canvas("周期曲线")
        self.periodic_heatmap_figure, self.periodic_heatmap_canvas = self._new_canvas("周期热图")
        self.peaks_figure, self.peaks_canvas = self._new_canvas("峰参数")
        self.peak_distribution_figure, self.peak_distribution_canvas = self._new_canvas("峰分布")
        self.peak_table = QtWidgets.QTableWidget()
        self.detail_figure, self.detail_canvas = self._new_canvas("单通道详情")
        self.detail_table = QtWidgets.QTableWidget()
        self._add_page("总览", self.overview_canvas, self.overview_figure)
        self._add_page("非周期参数", self.aperiodic_canvas, self.aperiodic_figure, self.aperiodic_table)
        self._add_page("周期曲线", self.periodic_canvas, self.periodic_figure, self.periodic_heatmap_canvas)
        self._add_page("峰参数", self.peaks_canvas, self.peaks_figure, self.peak_distribution_canvas, self.peak_table)
        self._add_page("单通道详情", self.detail_canvas, self.detail_figure, self.detail_table)

        widgets = (
            self.quality_combo,
            self.region_combo,
            self.channel_combo,
            self.band_combo,
            self.peak_mode_combo,
            self.curve_mode_combo,
            self.layout_combo,
            self.unified_check,
            self.legend_check,
            self.font_spin,
        )
        for widget in widgets:
            signal = widget.stateChanged if isinstance(widget, QtWidgets.QCheckBox) else widget.valueChanged if isinstance(widget, QtWidgets.QSpinBox) else widget.currentIndexChanged
            signal.connect(self._controls_changed)
        self.overview_canvas.mpl_connect("button_press_event", self._overview_clicked)
        self.peak_distribution_canvas.mpl_connect("button_press_event", self._peak_clicked)

    def _new_canvas(self, _name: str) -> tuple[Figure, FigureCanvasQTAgg]:
        figure = Figure(figsize=(10, 5), tight_layout=False)
        figure.set_layout_engine(None)
        canvas = FigureCanvasQTAgg(figure)
        canvas.setObjectName(_name)
        return figure, canvas

    def _new_canvas_with_table(self, _name: str) -> tuple[Figure, FigureCanvasQTAgg, QtWidgets.QTableWidget]:
        figure, canvas = self._new_canvas(_name)
        return figure, canvas, QtWidgets.QTableWidget()

    def _add_page(self, name: str, canvas: FigureCanvasQTAgg, figure: Figure, *extras: QtWidgets.QWidget) -> None:
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(4)
        toolbar = NavigationToolbar2QT(canvas, self)
        toolbar.setFixedHeight(34)
        layout.addWidget(toolbar)
        plot_content = QtWidgets.QWidget()
        plot_layout = QtWidgets.QVBoxLayout(plot_content)
        plot_layout.setContentsMargins(0, 0, 6, 0)
        plot_layout.setSpacing(6)
        primary_height = 620 if name == "总览" else 470
        canvas.setMinimumHeight(primary_height)
        plot_layout.addWidget(canvas)
        for extra in extras:
            if isinstance(extra, FigureCanvasQTAgg):
                extra_toolbar = NavigationToolbar2QT(extra, self)
                extra_toolbar.setFixedHeight(34)
                extra.setMinimumHeight(420)
                plot_layout.addWidget(extra_toolbar)
                plot_layout.addWidget(extra)
            else:
                extra.setMinimumHeight(150)
                extra.setMaximumHeight(180)
                plot_layout.addWidget(extra)
        minimum_height = primary_height + sum(460 if isinstance(extra, FigureCanvasQTAgg) else 190 for extra in extras)
        scroll = PlotScrollArea(
            plot_content,
            minimum_content_height=minimum_height,
            allow_horizontal=name == "周期曲线",
        )
        layout.addWidget(scroll, stretch=1)
        self._page_scrolls[name] = scroll
        self.tabs.addTab(page, name)

    def set_payload(
        self,
        payload: dict[str, Any],
        selected_channels: list[str] | None = None,
        selected_regions: list[str] | None = None,
        bands: Any = None,
    ) -> None:
        self.payload = payload
        self.selected_channels = None if selected_channels is None else set(map(str, selected_channels))
        self.selected_regions = None if selected_regions is None else set(map(str, selected_regions))
        record_bands = payload.get("record", {}).get("parameters", {}).get("display_bands", {}) if isinstance(payload.get("record", {}), dict) else {}
        table_bands = payload.get("tables", {}).get("display_bands", {}) if isinstance(payload.get("tables", {}), dict) else {}
        self.bands = normalize_bands(bands if bands is not None else table_bands or record_bands)
        self._populate_controls()
        self._refresh(preserve_scroll=False)

    def set_filters(self, selected_channels: list[str] | None, selected_regions: list[str] | None, bands: Any = None) -> None:
        if self.payload is None:
            return
        self.selected_channels = None if selected_channels is None else set(map(str, selected_channels))
        self.selected_regions = None if selected_regions is None else set(map(str, selected_regions))
        if bands is not None:
            self.bands = normalize_bands(bands)
        self._populate_controls()
        self._refresh()

    def set_color_template(self, template: str) -> None:
        """Refresh FOOOF figures only; fitted tables remain untouched."""
        self.color_template = template if template in available_color_templates() else DEFAULT_COLOR_TEMPLATE
        if self.payload is not None:
            self._refresh()

    def _tables(self) -> dict[str, pd.DataFrame]:
        return self.payload.get("tables", {}) if self.payload else {}

    def _populate_controls(self) -> None:
        if self.payload is None:
            return
        self._updating_controls = True
        try:
            available = prepare_fooof(self._tables(), self.bands, self.selected_channels, self.selected_regions)
            channels = ordered_fooof_channels(available["models"], available["curves"])
            old_region = self.region_combo.currentData()
            old_region_index = self.region_combo.currentIndex()
            old_channel = self.channel_combo.currentData()
            old_band = self.band_combo.currentData()
            old_band_index = self.band_combo.currentIndex()
            self.region_combo.clear()
            self.region_combo.addItem("全部", "全部")
            regions: list[str] = []
            for row in channels:
                region = str(row.get("region", "")).strip()
                if region and region not in regions:
                    regions.append(region)
            for region in regions:
                self.region_combo.addItem(region, region)
            region_index = self.region_combo.findData(old_region)
            if old_region_index < 0 and regions:
                preferred = next((region for region in regions if self.selected_regions and region in self.selected_regions), regions[0])
                region_index = self.region_combo.findData(preferred)
            self.region_combo.setCurrentIndex(max(region_index, 0))
            self.channel_combo.clear()
            self.channel_combo.addItem("当前所有通道", None)
            for row in channels:
                self.channel_combo.addItem(f"{row['channel_label']} ({row['region']})", row["channel_name"])
            channel_index = self.channel_combo.findData(old_channel)
            self.channel_combo.setCurrentIndex(max(channel_index, 0))
            self.band_combo.clear()
            self.band_combo.addItem("全部拟合范围", None)
            for band in self.bands:
                self.band_combo.addItem(f"{band['name']} [{band['low_hz']:g}–{band['high_hz']:g} Hz]", band["name"])
            band_index = self.band_combo.findData(old_band)
            # A new view starts with the complete fit range.  Once the user
            # chooses a band, findData preserves that choice on redraw.
            if old_band_index < 0:
                band_index = 0
            self.band_combo.setCurrentIndex(max(band_index, 0))
        finally:
            self._updating_controls = False

    def _controls_changed(self, *_args: Any) -> None:
        if not self._updating_controls:
            self._refresh()

    def _selected_region(self) -> str:
        return str(self.region_combo.currentData() or "全部")

    def _selected_channel(self) -> str | None:
        value = self.channel_combo.currentData()
        return None if value in (None, "") else str(value)

    def _refresh(self, *, preserve_scroll: bool = True) -> None:
        if self.payload is None:
            return
        active_scroll = self._page_scrolls.get(self.tabs.tabText(self.tabs.currentIndex()))
        scroll_position = active_scroll.scroll_position() if preserve_scroll and active_scroll is not None else None
        selected_band = self.band_combo.currentData()
        self.prepared = prepare_fooof(
            self._tables(),
            self.bands,
            self.selected_channels,
            self.selected_regions,
            quality_only=bool(self.quality_combo.currentData()),
            selected_band=str(selected_band) if selected_band else None,
            peak_mode=str(self.peak_mode_combo.currentData() or "representative"),
        )
        channels = ordered_fooof_channels(self.prepared["models"], self.prepared["curves"])
        selected_channel = self._selected_channel()
        valid_names = {str(row["channel_name"]) for row in channels}
        if selected_channel not in valid_names:
            selected_channel = str(channels[0]["channel_name"]) if channels else None
            self._updating_controls = True
            try:
                index = self.channel_combo.findData(selected_channel)
                self.channel_combo.setCurrentIndex(max(index, 0))
            finally:
                self._updating_controls = False
        region = self._selected_region()
        font_size = int(self.font_spin.value())
        show_legend = self.legend_check.isChecked()
        curve_mode = str(self.curve_mode_combo.currentData() or "overlay")
        unified_axis = self.unified_check.isChecked()

        self.overview_figure.clear()
        self.overview_figure.set_size_inches(14.0, 8.0, forward=False)
        overview_axes = np.asarray(self.overview_figure.subplots(2, 3), dtype=object)
        self._overview_info = plot_fooof_overview(self.overview_figure, overview_axes, self.prepared, region, selected_channel, curve_mode, unified_axis, show_legend, font_size, color_template=self.color_template)
        self.overview_canvas.draw_idle()

        self.aperiodic_figure.clear()
        aperiodic_axes = np.asarray(self.aperiodic_figure.subplots(1, 2), dtype=object).ravel()
        plot_aperiodic_details(self.aperiodic_figure, aperiodic_axes, self.prepared, selected_channel, show_legend, font_size, color_template=self.color_template)
        self._set_table(self.aperiodic_table, self.prepared["models"])
        self.aperiodic_canvas.draw_idle()

        overlay_channels = [
            str(row["channel_name"])
            for row in channels
            if self.selected_channels is None or str(row["channel_name"]) in self.selected_channels
        ]
        if selected_channel and selected_channel not in overlay_channels:
            overlay_channels.append(selected_channel)
        plot_periodic_curves(self.periodic_figure, str(self.layout_combo.currentData() or "region"), self.prepared, region, overlay_channels, curve_mode, unified_axis, show_legend, font_size, color_template=self.color_template)
        self._resize_periodic_canvas()
        self.periodic_canvas.draw_idle()
        plot_periodic_heatmap(self.periodic_heatmap_figure, self.prepared, font_size)
        self.periodic_heatmap_canvas.draw_idle()

        plot_peak_parameters(self.peaks_figure, self.prepared, selected_channel, show_legend, font_size, color_template=self.color_template)
        self.peaks_canvas.draw_idle()
        self._peak_points = plot_peak_distribution(self.peak_distribution_figure, self.prepared, font_size)
        self.peak_distribution_canvas.draw_idle()
        self._set_table(self.peak_table, self.prepared["peaks_all"])

        plot_single_channel_detail(self.detail_figure, self.prepared, selected_channel, show_legend, font_size)
        self.detail_canvas.draw_idle()
        detail = self.prepared["models"].loc[self.prepared["models"]["channel_name"].astype(str) == str(selected_channel)] if selected_channel else pd.DataFrame()
        self._set_table(self.detail_table, pd.concat([detail, self.prepared["peaks_all"].loc[self.prepared["peaks_all"]["channel_name"].astype(str) == str(selected_channel)]], ignore_index=True, sort=False) if selected_channel else pd.DataFrame())
        status = self._status_text()
        self.status_label.setText(status)
        self.status_label.setToolTip(status)
        if active_scroll is not None and scroll_position is not None:
            active_scroll.restore_scroll_position(scroll_position)

    def reset_plot_scroll(self) -> None:
        for scroll in self._page_scrolls.values():
            scroll.reset_position()

    def _resize_periodic_canvas(self) -> None:
        """Keep wide 1xN region layouts scrollable instead of shrinking labels."""
        width, height = self.periodic_figure.get_size_inches() * self.periodic_figure.dpi
        self.periodic_canvas.setMinimumSize(int(width), int(height))

    def _status_text(self) -> str:
        models = self.prepared["models"]
        peaks = self.prepared["peaks_all"]
        if models.empty:
            return "当前筛选下没有 FOOOF/specparam 结果。"
        quality = models["fit_quality_status"].astype(str).value_counts().to_dict() if "fit_quality_status" in models else {}
        no_peak = int((models.get("peak_status", pd.Series(dtype=str)).astype(str) == "no_peaks_detected").sum())
        failed = int((models.get("fit_status", pd.Series(dtype=str)).astype(str) != "ok").sum())
        band = self.prepared.get("selected_band")
        band_text = "全部拟合范围" if band is None else f"{band['name']} [{band['low_hz']:g}–{band['high_hz']:g} Hz]（左闭右开）"
        return f"通道={len(models)}；全部峰={len(peaks)}；质量={quality}；无峰={no_peak}；拟合失败={failed}；峰筛选={band_text}。PW 为高于非周期背景的 log10 功率差；BW=2σ。"

    @staticmethod
    def _set_table(table: QtWidgets.QTableWidget, frame: pd.DataFrame) -> None:
        display = frame.head(1000).copy() if isinstance(frame, pd.DataFrame) else pd.DataFrame()
        table.clear()
        table.setRowCount(len(display))
        table.setColumnCount(len(display.columns))
        table.setHorizontalHeaderLabels([str(column) for column in display.columns])
        for row_index, row in enumerate(display.itertuples(index=False, name=None)):
            for column_index, value in enumerate(row):
                table.setItem(row_index, column_index, QtWidgets.QTableWidgetItem("" if pd.isna(value) else str(value)))
        table.resizeColumnsToContents()
        table.setToolTip(f"显示前 {len(display)} 行；完整结果保存在运行目录。")

    def _overview_clicked(self, event: Any) -> None:
        if event.inaxes is None or event.xdata is None:
            return
        channels = self._overview_info.get("channels", [])
        if not channels:
            return
        index = int(np.clip(round(float(event.xdata)), 0, len(channels) - 1))
        name = channels[index]["channel_name"]
        self._updating_controls = True
        try:
            combo_index = self.channel_combo.findData(name)
            if combo_index >= 0:
                self.channel_combo.setCurrentIndex(combo_index)
        finally:
            self._updating_controls = False
        self._refresh()

    def _peak_clicked(self, event: Any) -> None:
        if event.inaxes is None or event.xdata is None or event.ydata is None or not self._peak_points:
            return
        channels = ordered_fooof_channels(self.prepared["models"], self.prepared["curves"])
        if not channels:
            return
        channel_index = int(np.clip(round(float(event.ydata)), 0, len(channels) - 1))
        channel_name = channels[channel_index]["channel_name"]
        candidates = [row for row in self._peak_points if str(row.get("channel_name")) == str(channel_name) and np.isfinite(_to_float(row.get("center_frequency_hz")))]
        if candidates:
            selected = min(candidates, key=lambda row: abs(_to_float(row.get("center_frequency_hz")) - float(event.xdata)))
            channel_name = str(selected.get("channel_name"))
        self._updating_controls = True
        try:
            combo_index = self.channel_combo.findData(channel_name)
            if combo_index >= 0:
                self.channel_combo.setCurrentIndex(combo_index)
        finally:
            self._updating_controls = False
        self._refresh()

    def save_figure(self, kind: str, path: str | Path) -> None:
        figures = {
            "overview": self.overview_figure,
            "aperiodic": self.aperiodic_figure,
            "periodic": self.periodic_figure,
            "periodic_heatmap": self.periodic_heatmap_figure,
            "peaks": self.peaks_figure,
            "peak_distribution": self.peak_distribution_figure,
            "detail": self.detail_figure,
        }
        if kind == "current":
            kind = ("overview", "aperiodic", "periodic", "peaks", "detail")[self.tabs.currentIndex()]
        figure = figures.get(kind)
        if figure is None:
            raise ValueError(f"Unknown FOOOF figure kind: {kind}")
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(output, dpi=300)

    def save_all(self, output_dir: str | Path) -> list[Path]:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        saved: list[Path] = []
        for kind in ("overview", "aperiodic", "periodic", "periodic_heatmap", "peaks", "peak_distribution", "detail"):
            for suffix in (".png", ".svg"):
                path = output / f"fooof_{kind}{suffix}"
                self.save_figure(kind, path)
                saved.append(path)
        return saved

    def save_tables(self, prefix: str | Path) -> list[Path]:
        base = Path(prefix)
        if base.suffix:
            base = base.with_suffix("")
        base.parent.mkdir(parents=True, exist_ok=True)
        frames = {
            "models": self.prepared["models"],
            "peaks_all": self.prepared["peaks_all"],
            "peaks_selected": self.prepared["peaks_display"],
            "curves": self.prepared["curves"],
        }
        saved: list[Path] = []
        for name, frame in frames.items():
            path = base.parent / f"{base.name}_{name}.csv"
            frame.to_csv(path, index=False, encoding="utf-8-sig")
            saved.append(path)
        settings = pd.DataFrame(
            [
                {
                    "file_id": self.payload.get("file_id", "") if self.payload else "",
                    "quality_filter": "pass" if self.quality_combo.currentData() else "all",
                    "selected_region": self._selected_region(),
                    "selected_channel": self._selected_channel() or "",
                    "selected_band": self.band_combo.currentData() or "",
                    "peak_mode": self.peak_mode_combo.currentData(),
                    "curve_mode": self.curve_mode_combo.currentData(),
                    "fit_range_note": "显示频段只筛选已有峰；扩展拟合范围需重新运行 FOOOF/specparam",
                    "band_boundary_rule": "left_closed_right_open",
                    "pw_definition": "backend peak height above aperiodic model in log10 power",
                    "bw_definition": "FOOOF/specparam bandwidth = 2 sigma; distribution line is CF +/- BW/2",
                    "color_template": self.color_template,
                }
            ]
        )
        settings_path = base.parent / f"{base.name}_settings.csv"
        settings.to_csv(settings_path, index=False, encoding="utf-8-sig")
        saved.append(settings_path)
        return saved


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return np.nan


def _load_logo_pixmap(path: Path, width: int = 190, height: int = 58) -> QtGui.QPixmap:
    """Render the supplied SVG without changing its aspect ratio."""
    pixmap = QtGui.QPixmap(width, height)
    pixmap.fill(QtCore.Qt.GlobalColor.transparent)
    renderer = QtSvg.QSvgRenderer(str(path))
    if renderer.isValid():
        view_box = renderer.viewBoxF()
        source_width = view_box.width() or 1.0
        source_height = view_box.height() or 1.0
        scale = min(width / source_width, height / source_height)
        target_width = source_width * scale
        target_height = source_height * scale
        target = QtCore.QRectF(
            (width - target_width) / 2.0,
            (height - target_height) / 2.0,
            target_width,
            target_height,
        )
        painter = QtGui.QPainter(pixmap)
        renderer.render(painter, target)
        painter.end()
    return pixmap


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, input_files: list[str] | None = None, output_dir: str | None = None) -> None:
        super().__init__()
        font_family = _load_windows_cjk_font() or "Noto Sans SC"
        # Set the font on the application as well as the main window.  Several
        # result widgets are created without a parent first; using the
        # application font prevents those widgets from falling back to a
        # CJK-incomplete default font on Windows/high-DPI displays.
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app_font = QtGui.QFont(font_family, 9)
            app.setFont(app_font)
        self.setFont(QtGui.QFont(font_family, 9))
        self.setStyleSheet(_gui_stylesheet())
        self.setWindowTitle(window_title())
        self.resize(1500, 980)
        self.setMinimumSize(980, 620)
        self.config_path = PROJECT_ROOT / "configs" / DEFAULT_CONFIG_FILENAME
        if not self.config_path.is_file():
            self.config_path = packaged_resource_path(f"configs/{DEFAULT_CONFIG_FILENAME}")
        self.metadata_dir = PROJECT_ROOT / "metadata"
        self.current_mapping_path: Path | None = None
        self.base_config = load_config(self.config_path)
        self.file_infos: list[dict[str, Any]] = []
        self.file_selections: dict[str, dict[str, Any]] = {}
        self.current_info: dict[str, Any] | None = None
        self.result_payloads: dict[str, dict[str, Any]] = {}
        self.result_records: dict[str, dict[str, Any]] = {}
        self.loaded_run: dict[str, Any] | None = None
        self.analysis_thread: QtCore.QThread | None = None
        self.analysis_worker: AnalysisWorker | None = None
        self.inspect_thread: QtCore.QThread | None = None
        self._running = False
        self._dirty = False
        self._last_progress_message = ""
        self._active_analysis_task_id = ""
        self._active_inspect_task_id = ""
        self._displayed_result_key = ""
        self._result_table_source = pd.DataFrame()
        self._result_table_loaded = False
        self._build_ui()
        self._wheel_focus_guard = install_wheel_focus_guard(self)
        help_menu = self.menuBar().addMenu("Help")
        about_action = QtGui.QAction("About LUNA", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)
        self._restore_defaults()
        if output_dir:
            self.output_edit.setText(str(Path(output_dir).expanduser()))
        if input_files:
            QtCore.QTimer.singleShot(100, lambda: self.load_paths(input_files))

    def _build_ui(self) -> None:
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        root = QtWidgets.QVBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)
        root.addWidget(self._build_top_toolbar(), stretch=0)
        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(6)
        root.addWidget(splitter, stretch=1)

        left_scroll = QtWidgets.QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setObjectName("analysisConfigScroll")
        self.analysis_config_scroll = left_scroll
        left_scroll.setMinimumWidth(350)
        left_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        left_scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        left_panel = QtWidgets.QWidget()
        left_panel.setMinimumWidth(338)
        left_scroll.setWidget(left_panel)
        left_layout = QtWidgets.QVBoxLayout(left_panel)
        left_layout.setContentsMargins(2, 2, 8, 2)
        left_layout.setSpacing(10)
        left_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        splitter.addWidget(left_scroll)

        right = QtWidgets.QWidget()
        right.setMinimumWidth(560)
        right_layout = QtWidgets.QVBoxLayout(right)
        right_layout.setContentsMargins(2, 2, 2, 2)
        right_layout.setSpacing(7)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([430, 1070])

        left_layout.addWidget(self._build_data_group())
        left_layout.addWidget(self._build_mapping_group())
        left_layout.addWidget(self._build_selection_group())
        left_layout.addWidget(self._build_indicator_group())
        left_layout.addWidget(self._build_parameter_group())
        left_layout.addWidget(self._build_task_group())

        # The result selector and each page's display controls stay outside the
        # plot viewport.  Only plot content scrolls, so controls remain usable
        # while the user inspects lower matrices or figures.
        self.result_combo = QtWidgets.QComboBox()
        self.result_combo.setToolTip("选择已读取的预览、分析结果或载入的历史结果。")
        self.result_combo.setFixedHeight(30)
        self.result_combo.currentTextChanged.connect(self._show_selected_result)
        right_layout.addWidget(self.result_combo, stretch=0)

        self.result_stack = QtWidgets.QStackedWidget()
        self.result_stack.setObjectName("resultStack")
        self.result_stack.setMinimumHeight(RESULT_PAGE_MIN_HEIGHT)
        self.result_stack.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)

        self.general_plot_widget = QtWidgets.QWidget()
        general_plot_layout = QtWidgets.QVBoxLayout(self.general_plot_widget)
        general_plot_layout.setContentsMargins(0, 0, 0, 0)
        general_plot_layout.setSpacing(4)
        self.canvas = ResultCanvas()
        self.canvas.setMinimumHeight(650)
        self.toolbar = NavigationToolbar2QT(self.canvas, self)
        self.toolbar.setFixedHeight(34)
        general_plot_layout.addWidget(self.toolbar)
        general_plot_content = QtWidgets.QWidget()
        general_plot_content_layout = QtWidgets.QVBoxLayout(general_plot_content)
        general_plot_content_layout.setContentsMargins(0, 0, 0, 0)
        general_plot_content_layout.addWidget(self.canvas)
        self.general_plot_scroll = PlotScrollArea(general_plot_content, minimum_content_height=660)
        general_plot_layout.addWidget(self.general_plot_scroll, stretch=1)
        self.result_stack.addWidget(self.general_plot_widget)

        self.band_power_view = BandPowerView()
        self.band_power_view.setFont(self.font())
        self.band_power_view.export_requested.connect(self._export_band_figure)
        self.result_stack.addWidget(self.band_power_view)

        self.fooof_view = FooofView()
        self.fooof_view.setFont(self.font())
        self.fooof_view.export_requested.connect(self._export_fooof)
        self.result_stack.addWidget(self.fooof_view)

        self.connectivity_view = ConnectivityView(right)
        self.connectivity_view.setFont(self.font())
        self.connectivity_view.export_requested.connect(self._export_connectivity)
        self.result_stack.addWidget(self.connectivity_view)
        right_layout.addWidget(self.result_stack, stretch=1)

        table_header = QtWidgets.QHBoxLayout()
        table_header.setContentsMargins(0, 0, 0, 0)
        self.table_toggle = QtWidgets.QToolButton()
        self.table_toggle.setObjectName("sectionToggle")
        self.table_toggle.setText("▶ 展开结果表")
        self.table_toggle.setCheckable(True)
        self.table_toggle.setChecked(False)
        self.table_toggle.setToolTip("结果表默认不创建单元格；展开后显示前 1000 行，不改变保存或导出内容。")
        self.table_toggle.toggled.connect(self._toggle_result_table)
        table_header.addWidget(self.table_toggle)
        table_header.addStretch(1)
        right_layout.addLayout(table_header)
        self.table = QtWidgets.QTableWidget()
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.setMinimumHeight(0)
        self.table.setMaximumHeight(0)
        self.table.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)
        self.table.setVisible(False)
        right_layout.addWidget(self.table, stretch=0)

        # Status and diagnostics remain at the bottom and use only two compact
        # rows by default.  Their full text is available through explicit
        # expand controls with independent scrolling.
        self.status_panel = QtWidgets.QWidget()
        self.status_panel.setObjectName("statusPanel")
        self.status_panel.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)
        status_layout = QtWidgets.QVBoxLayout(self.status_panel)
        status_layout.setContentsMargins(0, 2, 0, 0)
        status_layout.setSpacing(3)
        log_header = QtWidgets.QHBoxLayout()
        log_header.setContentsMargins(0, 0, 0, 0)
        log_header.addWidget(QtWidgets.QLabel("状态"))
        self.result_status_label = QtWidgets.QLabel("就绪：请导入 FIF 文件。")
        self.result_status_label.setStyleSheet(f"color: {GUI_COLORS['muted']};")
        self.result_status_label.setWordWrap(False)
        self.result_status_label.setFixedHeight(24)
        self.result_status_label.setSizePolicy(QtWidgets.QSizePolicy.Policy.Ignored, QtWidgets.QSizePolicy.Policy.Fixed)
        log_header.addWidget(self.result_status_label, stretch=1)
        self.log_toggle = QtWidgets.QToolButton()
        self.log_toggle.setObjectName("sectionToggle")
        self.log_toggle.setText("展开详细日志")
        self.log_toggle.setCheckable(True)
        self.log_toggle.setChecked(False)
        self.log_toggle.toggled.connect(self._toggle_log)
        log_header.addWidget(self.log_toggle)
        status_layout.addLayout(log_header)
        self.status_text = QtWidgets.QPlainTextEdit()
        self.status_text.setReadOnly(True)
        self.status_text.setMaximumBlockCount(2000)
        self.status_text.setPlaceholderText("详细运行日志已折叠；需要排查时点击“展开详细日志”。")
        self.status_text.setMinimumHeight(90)
        self.status_text.setMaximumHeight(150)
        self.status_text.setVisible(False)
        status_layout.addWidget(self.status_text, stretch=0)

        quality_header = QtWidgets.QHBoxLayout()
        quality_header.setContentsMargins(0, 0, 0, 0)
        self.quality_summary_label = QtWidgets.QLabel("质量：导入 FIF 后自动检查通道与 epoch。")
        self.quality_summary_label.setStyleSheet(f"color: {GUI_COLORS['muted']};")
        self.quality_summary_label.setWordWrap(False)
        self.quality_summary_label.setFixedHeight(24)
        self.quality_summary_label.setSizePolicy(QtWidgets.QSizePolicy.Policy.Ignored, QtWidgets.QSizePolicy.Policy.Fixed)
        quality_header.addWidget(self.quality_summary_label, stretch=1)
        self.quality_toggle = QtWidgets.QToolButton()
        self.quality_toggle.setObjectName("sectionToggle")
        self.quality_toggle.setText("展开质量详情")
        self.quality_toggle.setCheckable(True)
        self.quality_toggle.setChecked(False)
        self.quality_toggle.toggled.connect(self._toggle_quality)
        quality_header.addWidget(self.quality_toggle)
        status_layout.addLayout(quality_header)
        self.quality_alert_text = QtWidgets.QPlainTextEdit()
        self.quality_alert_text.setReadOnly(True)
        self.quality_alert_text.setMaximumBlockCount(1000)
        self.quality_alert_text.setMinimumHeight(90)
        self.quality_alert_text.setMaximumHeight(150)
        self.quality_alert_text.setPlaceholderText("添加 FIF 后，这里会列出可疑通道、epoch 和上游删除记录。")
        self.quality_alert_text.setVisible(False)
        status_layout.addWidget(self.quality_alert_text, stretch=0)
        right_layout.addWidget(self.status_panel, stretch=0)

    def _build_top_toolbar(self) -> QtWidgets.QWidget:
        """Global project and execution controls, independent of parameters."""
        panel = QtWidgets.QWidget()
        panel.setObjectName("topToolbarPanel")
        panel.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)
        panel.setFixedHeight(HEADER_PANEL_HEIGHT)
        outer = QtWidgets.QVBoxLayout(panel)
        outer.setContentsMargins(8, 5, 8, 5)
        outer.setSpacing(3)
        # Only the header content is fixed-width.  The main window and result
        # area remain resizable; a narrow window gets a local header scrollbar.
        header_scroll = QtWidgets.QScrollArea()
        header_scroll.setObjectName("headerScroll")
        header_scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        header_scroll.setWidgetResizable(False)
        header_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        header_scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        header_content = QtWidgets.QWidget()
        header_content.setFixedWidth(HEADER_CONTENT_WIDTH)
        self.header_scroll = header_scroll
        self.header_content_widget = header_content
        content_layout = QtWidgets.QVBoxLayout(header_content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(4)
        info_row = QtWidgets.QHBoxLayout()
        info_row.setSpacing(14)
        brand_panel = QtWidgets.QWidget()
        brand_panel.setFixedWidth(240)
        brand_layout = QtWidgets.QVBoxLayout(brand_panel)
        brand_layout.setContentsMargins(0, 0, 0, 0)
        brand_layout.setSpacing(0)
        logo = QtWidgets.QLabel()
        # The README/web light-theme header uses luna-logo.svg.  Reuse that
        # exact branding asset in the desktop header so both surfaces stay in
        # sync; the packaged copy is the installation fallback.
        logo_path = PROJECT_ROOT / "assets" / "branding" / "luna-logo.svg"
        if not logo_path.is_file():
            try:
                logo_path = packaged_resource_path("branding/luna-logo.svg")
            except FileNotFoundError:
                logo_path = packaged_resource_path("branding/luna-logo-on-white.svg")
        self.header_logo_path = logo_path
        self.header_logo = logo
        logo.setPixmap(_load_logo_pixmap(logo_path, width=218, height=72))
        logo.setFixedSize(218, 72)
        logo.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        logo.setToolTip(APP_DESCRIPTION)
        # The formal Logo already contains the wordmark and full name.  Keep
        # this brand area image-only so the name is not rendered twice.
        brand_layout.addWidget(logo, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)
        info_row.addWidget(brand_panel)
        summary_panel = QtWidgets.QWidget()
        summary_layout = QtWidgets.QVBoxLayout(summary_panel)
        summary_layout.setContentsMargins(0, 0, 0, 0)
        summary_layout.setSpacing(1)
        self.header_dataset_label = QtWidgets.QLabel("未载入数据集")
        self.header_dataset_label.setStyleSheet(f"color: {GUI_COLORS['text']}; font-weight: 600;")
        self.header_dataset_label.setWordWrap(False)
        self.header_dataset_label.setToolTip("当前数据文件")
        summary_layout.addWidget(self.header_dataset_label)
        self.header_data_summary_label = QtWidgets.QLabel("Epoch — / —；片段 —；通道 — / —")
        self.header_data_summary_label.setStyleSheet(f"color: {GUI_COLORS['muted']};")
        self.header_data_summary_label.setWordWrap(False)
        summary_layout.addWidget(self.header_data_summary_label)
        info_row.addWidget(summary_panel, stretch=1)
        self.header_task_label = QtWidgets.QLabel("就绪")
        self.header_task_label.setStyleSheet(f"color: {GUI_COLORS['muted']};")
        self.header_task_label.setMinimumWidth(180)
        self.header_task_label.setWordWrap(False)
        self.header_task_label.setFixedHeight(24)
        self.header_task_label.setSizePolicy(QtWidgets.QSizePolicy.Policy.Ignored, QtWidgets.QSizePolicy.Policy.Fixed)
        info_row.addWidget(self.header_task_label)
        content_layout.addLayout(info_row)
        # Keep the existing worker/status code independent of the layout.
        self.task_label = self.header_task_label
        action_row = QtWidgets.QHBoxLayout()
        action_row.setSpacing(8)
        action_row.addWidget(QtWidgets.QLabel("颜色模板"))
        self.color_template_combo = QtWidgets.QComboBox()
        self.color_template_combo.setMinimumWidth(150)
        for template in available_color_templates():
            self.color_template_combo.addItem(color_template_label(template), template)
        self.color_template_combo.setCurrentIndex(max(0, self.color_template_combo.findData(DEFAULT_COLOR_TEMPLATE)))
        self.color_template_combo.setToolTip("分类颜色模板；改变后只刷新显示，不重新计算分析结果。")
        self.color_template_combo.currentIndexChanged.connect(self._display_color_changed)
        action_row.addWidget(self.color_template_combo)
        action_row.addStretch(1)
        self.run_button = QtWidgets.QPushButton("Run Analysis")
        self.run_button.setObjectName("primaryAction")
        self.run_button.setToolTip("按当前文件、通道、epoch、脑区对和计算参数运行已勾选指标。")
        self.run_button.clicked.connect(self._run)
        self.cancel_button = QtWidgets.QPushButton("Stop")
        self.cancel_button.setObjectName("cancelAction")
        self.cancel_button.setEnabled(False)
        self.cancel_button.setToolTip("请求取消后台任务；已经完成的结果会保留。")
        self.cancel_button.clicked.connect(self._cancel)
        self.save_result_button = QtWidgets.QPushButton("Save Result")
        self.save_result_button.setObjectName("globalSecondaryAction")
        self.save_result_button.setToolTip("保存当前结果视图对应的图和数值表；不重新计算。")
        self.save_result_button.clicked.connect(self._save_result)
        self.export_figure_button = QtWidgets.QPushButton("Export Figure")
        self.export_figure_button.setObjectName("globalSecondaryAction")
        self.export_figure_button.setToolTip("导出当前结果图；具体指标视图会提供相应格式。")
        self.export_figure_button.clicked.connect(self._export_figure)
        for button in (self.run_button, self.cancel_button, self.save_result_button, self.export_figure_button):
            button.setMinimumWidth(button.fontMetrics().horizontalAdvance(button.text()) + 28)
            button.setFixedHeight(GLOBAL_ACTION_HEIGHT)
            button.setSizePolicy(QtWidgets.QSizePolicy.Policy.Minimum, QtWidgets.QSizePolicy.Policy.Fixed)
            action_row.addWidget(button)
        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setTextVisible(False)
        self.progress.setFixedWidth(86)
        self.progress.setToolTip("后台任务进度；无法估计时会使用不确定进度。")
        action_row.addWidget(self.progress)
        content_layout.addLayout(action_row)
        header_scroll.setWidget(header_content)
        header_scroll.setFixedHeight(112)
        outer.addWidget(header_scroll)
        return panel

    def _group(self, title: str) -> tuple[CollapsiblePanel, QtWidgets.QVBoxLayout]:
        box = CollapsiblePanel(title)
        layout = box.content_layout
        return box, layout

    def _build_data_group(self) -> QtWidgets.QGroupBox:
        box, layout = self._group("数据")
        row = QtWidgets.QHBoxLayout()
        add = QtWidgets.QPushButton("导入文件")
        add.setObjectName("primaryAction")
        add.setToolTip("选择一个或多个 FIF 文件。读取后自动显示波形、质量和实际有效时长。")
        add.clicked.connect(self._choose_files)
        clear = QtWidgets.QPushButton("清空文件")
        clear.setToolTip("移除当前已载入文件和内存中的显示结果。不会删除磁盘文件。")
        clear.clicked.connect(self._clear_files)
        row.addWidget(add)
        row.addWidget(clear)
        row.addStretch(1)
        layout.addLayout(row)
        self.file_combo = QtWidgets.QComboBox()
        self.file_combo.setMinimumWidth(180)
        self.file_combo.setToolTip("当前文件；悬停可查看完整路径。")
        self.file_combo.currentIndexChanged.connect(self._file_changed)
        layout.addWidget(self.file_combo)
        output_row = QtWidgets.QHBoxLayout()
        self.output_edit = QtWidgets.QLineEdit(str(PROJECT_ROOT / "results" / DEFAULT_OUTPUT_DIRNAME))
        self.output_edit.setToolTip("分析结果保存目录；完整路径可直接编辑、复制。")
        choose_output = QtWidgets.QPushButton("输出目录")
        choose_output.setToolTip("选择分析结果保存目录。")
        choose_output.clicked.connect(self._choose_output)
        output_row.addWidget(self.output_edit)
        output_row.addWidget(choose_output)
        layout.addLayout(output_row)
        self.data_info_label = QtWidgets.QLabel("尚未载入文件。")
        self.data_info_label.setWordWrap(True)
        layout.addWidget(self.data_info_label)
        return box

    def _build_mapping_group(self) -> CollapsiblePanel:
        box, layout = self._group("Channel Mapping")
        self.mapping_hint = QtWidgets.QLabel("导入文件后编辑脑区和标签；空白脑区不会参与脑区级连接。")
        self.mapping_hint.setWordWrap(True)
        self.mapping_hint.setStyleSheet(f"color: {GUI_COLORS['muted']};")
        layout.addWidget(self.mapping_hint)
        self.mapping_table = QtWidgets.QTableWidget(0, 4)
        self.mapping_table.setHorizontalHeaderLabels(["Channel", "Physical", "Region", "Label"])
        self.mapping_table.setAlternatingRowColors(True)
        self.mapping_table.setMinimumHeight(120)
        self.mapping_table.setMaximumHeight(250)
        self.mapping_table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.mapping_table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.mapping_table.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.mapping_table.horizontalHeader().setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.mapping_table.itemChanged.connect(self._mapping_edited)
        layout.addWidget(self.mapping_table)
        mapping_buttons = QtWidgets.QHBoxLayout()
        apply_button = QtWidgets.QPushButton("Apply Mapping")
        apply_button.setToolTip("应用当前表格中的 Region/Label 到当前文件；不会改写 FIF。")
        apply_button.clicked.connect(self._apply_mapping_from_table)
        save_button = QtWidgets.QPushButton("Save Mapping")
        save_button.setToolTip("将当前通道映射保存为可复用的 JSON。")
        save_button.clicked.connect(self._save_mapping_file)
        load_button = QtWidgets.QPushButton("Load Mapping")
        load_button.setToolTip("载入 JSON，并按通道名或物理编号匹配当前文件。")
        load_button.clicked.connect(self._load_mapping_file)
        for button in (apply_button, save_button, load_button):
            button.setMinimumHeight(30)
            mapping_buttons.addWidget(button)
        layout.addLayout(mapping_buttons)
        self.mapping_status_label = QtWidgets.QLabel("尚未载入文件。")
        self.mapping_status_label.setWordWrap(True)
        self.mapping_status_label.setStyleSheet(f"color: {GUI_COLORS['muted']};")
        layout.addWidget(self.mapping_status_label)
        return box

    def _mapping_edited(self, *_args: Any) -> None:
        if getattr(self, "_mapping_table_loading", False):
            return
        self._set_dirty(True)

    def _populate_mapping_table(self) -> None:
        table = self.current_info.get("channel_table", pd.DataFrame()) if self.current_info else pd.DataFrame()
        self._mapping_table_loading = True
        try:
            self.mapping_table.setRowCount(0)
            for row_index, row in enumerate(mapping_rows(table)):
                self.mapping_table.insertRow(row_index)
                values = (
                    row.get("channel_name", ""),
                    row.get("physical_channel_number", ""),
                    row.get("region", ""),
                    row.get("label", ""),
                )
                for column, value in enumerate(values):
                    item = QtWidgets.QTableWidgetItem("" if pd.isna(value) else str(value))
                    if column < 2:
                        item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
                    self.mapping_table.setItem(row_index, column, item)
            if self.current_info:
                mapped = len(region_order(table))
                total = len(table)
                self.mapping_status_label.setText(f"当前映射：{mapped} 个脑区，{total} 个通道；可直接编辑 Region 和 Label。")
            else:
                self.mapping_status_label.setText("尚未载入文件。")
        finally:
            self._mapping_table_loading = False

    def _mapping_table_dataframe(self) -> pd.DataFrame:
        if self.current_info is None:
            return pd.DataFrame()
        table = self.current_info["channel_table"].copy()
        by_name = {str(row.channel_name): index for index, row in table.iterrows()}
        for row_index in range(self.mapping_table.rowCount()):
            name_item = self.mapping_table.item(row_index, 0)
            if name_item is None:
                continue
            name = name_item.text().strip()
            if name not in by_name:
                continue
            target = by_name[name]
            region_item = self.mapping_table.item(row_index, 2)
            label_item = self.mapping_table.item(row_index, 3)
            table.at[target, "region"] = region_item.text().strip() if region_item else ""
            table.at[target, "label"] = label_item.text().strip() if label_item else ""
            table.at[target, "mapping_status"] = "mapped" if table.at[target, "region"] else "unmapped"
        return table

    def _populate_rank_mapping_table(self) -> None:
        old: dict[str, str] = {}
        for row in range(getattr(self, "rank_mapping_table", QtWidgets.QTableWidget()).rowCount()):
            region_item = self.rank_mapping_table.item(row, 0)
            rank_item = self.rank_mapping_table.item(row, 1)
            if region_item is not None and rank_item is not None:
                old[region_item.text().strip()] = rank_item.text().strip()
        table = self.current_info.get("channel_table", pd.DataFrame()) if self.current_info else pd.DataFrame()
        regions = region_order(table) if not table.empty else list(DEFAULT_TEMPLATE_REGIONS)
        self.rank_mapping_table.blockSignals(True)
        try:
            self.rank_mapping_table.setRowCount(0)
            for row_index, region in enumerate(regions):
                self.rank_mapping_table.insertRow(row_index)
                region_item = QtWidgets.QTableWidgetItem(region)
                region_item.setFlags(region_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
                self.rank_mapping_table.setItem(row_index, 0, region_item)
                self.rank_mapping_table.setItem(row_index, 1, QtWidgets.QTableWidgetItem(old.get(region, "0")))
        finally:
            self.rank_mapping_table.blockSignals(False)

    def _apply_channel_table(self, table: pd.DataFrame, source: str = "当前编辑") -> None:
        if self.current_info is None:
            return
        issues = validate_mapping(table)
        self.current_info["channel_table"] = table
        for info in self.file_infos:
            if str(info.get("path")) == str(self.current_info.get("path")):
                info["channel_table"] = table
        if source and source not in {"当前编辑", "预设"}:
            self.current_mapping_path = Path(source)
        self._populate_current_file()
        if issues:
            self.mapping_status_label.setText("映射已应用，但有提示：" + "；".join(issues))
        else:
            self.mapping_status_label.setText(f"映射已应用：{len(region_order(table))} 个脑区。")
        self._set_dirty(True)
        self._log(f"已应用通道映射：{len(region_order(table))} 个脑区。")

    def _apply_mapping_from_table(self) -> None:
        if self.current_info is None:
            self._show_message(QtWidgets.QMessageBox.Icon.Information, "尚未载入文件", "请先导入 FIF 文件。")
            return
        self._apply_channel_table(self._mapping_table_dataframe())

    def _save_mapping_file(self) -> None:
        if self.current_info is None:
            self._show_message(QtWidgets.QMessageBox.Icon.Information, "尚未载入文件", "请先导入 FIF 文件。")
            return
        table = self._mapping_table_dataframe()
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "保存通道映射",
            str(PROJECT_ROOT / DEFAULT_MAPPING_FILENAME),
            "JSON (*.json)",
        )
        if not path:
            return
        try:
            output = save_mapping(table, path)
            self.current_mapping_path = output
            self._apply_channel_table(table, str(output))
            self._log(f"已保存通道映射：{output}")
        except Exception as exc:  # noqa: BLE001 - user-facing file operation
            self._show_message(QtWidgets.QMessageBox.Icon.Warning, "保存通道映射失败", str(exc))

    def _load_mapping_file(self) -> None:
        if self.current_info is None:
            self._show_message(QtWidgets.QMessageBox.Icon.Information, "尚未载入文件", "请先导入 FIF 文件。")
            return
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "载入通道映射", str(PROJECT_ROOT), "JSON (*.json)")
        if not path:
            return
        try:
            table = apply_mapping(self.current_info["channel_table"], load_mapping(path))
            self.current_mapping_path = Path(path).resolve()
            self._apply_channel_table(table, str(self.current_mapping_path))
            self._log(f"已载入通道映射：{path}")
        except Exception as exc:  # noqa: BLE001 - user-facing file operation
            self._show_message(QtWidgets.QMessageBox.Icon.Warning, "载入通道映射失败", str(exc))

    def _rebuild_region_controls(self) -> None:
        old_selected = {name for name, checkbox in self.region_checks.items() if checkbox.isChecked()}
        table = self.current_info.get("channel_table", pd.DataFrame()) if self.current_info else pd.DataFrame()
        regions = region_order(table)
        self.region_checks_group.blockSignals(True)
        self.region_checks_group.clear()
        self.region_checks = {}
        preserve_selection = bool(old_selected.intersection(regions))
        for region in regions:
            checked = region in old_selected if preserve_selection else True
            self.region_checks_group.add_item(region, region, checked=checked, tooltip=f"选择脑区 {region} 的全部已映射通道。")
            self.region_checks[region] = self.region_checks_group.items()[-1][0]
        self.region_checks_group.blockSignals(False)
        self.region_checks_group.updateGeometry()

    def _rebuild_pair_controls(self) -> None:
        old_selected = {pair for pair, checkbox in self.pair_checks.items() if checkbox.isChecked()}
        table = self.current_info.get("channel_table", pd.DataFrame()) if self.current_info else pd.DataFrame()
        pairs = region_pairs(table) if not table.empty else [
            (DEFAULT_TEMPLATE_REGIONS[i], DEFAULT_TEMPLATE_REGIONS[j])
            for i in range(len(DEFAULT_TEMPLATE_REGIONS))
            for j in range(i + 1, len(DEFAULT_TEMPLATE_REGIONS))
        ]
        self.pair_checks_group.blockSignals(True)
        self.pair_checks_group.clear()
        self.pair_checks = {}
        preserve_selection = bool(old_selected.intersection(pairs))
        for pair in pairs:
            checked = pair in old_selected if preserve_selection else True
            self.pair_checks_group.add_item(f"{pair[0]}–{pair[1]}", pair, checked=checked, tooltip=f"选择 {pair[0]} 与 {pair[1]} 的跨脑区连接。")
            self.pair_checks[pair] = self.pair_checks_group.items()[-1][0]
        self.pair_checks_group.blockSignals(False)
        self.pair_checks_group.updateGeometry()

    def _build_selection_group(self) -> QtWidgets.QGroupBox:
        box, layout = self._group("分析范围")
        region_label = QtWidgets.QLabel("脑区（用于批量选择通道）")
        region_label.setStyleSheet(f"color: {GUI_COLORS['muted']};")
        layout.addWidget(region_label)
        self.region_checks_group = FlowCheckBoxGroup()
        self.region_checks: dict[str, QtWidgets.QCheckBox] = {}
        self.region_checks_group.changed.connect(self._selection_changed)
        layout.addWidget(self.region_checks_group)
        apply_row = QtWidgets.QHBoxLayout()
        apply_regions = QtWidgets.QPushButton("应用脑区选择")
        apply_regions.setToolTip("将勾选的脑区应用到下方实际通道。")
        apply_regions.clicked.connect(self._apply_region_selection)
        apply_row.addWidget(apply_regions)
        apply_row.addStretch(1)
        layout.addLayout(apply_row)
        channel_label = QtWidgets.QLabel("实际通道（按 FIF 通道名和物理映射显示）")
        channel_label.setStyleSheet(f"color: {GUI_COLORS['muted']};")
        layout.addWidget(channel_label)
        self.channel_list = QtWidgets.QListWidget()
        self.channel_list.setMaximumHeight(190)
        self.channel_list.setMinimumHeight(92)
        self.channel_list.setToolTip("勾选参与计算和波形预览的通道；物理编号来自 FIF 通道映射。")
        self.channel_list.itemChanged.connect(self._channel_selection_changed)
        layout.addWidget(self.channel_list)
        epoch_row = QtWidgets.QHBoxLayout()
        epoch_row.addWidget(QtWidgets.QLabel("epoch 子集"))
        self.epoch_edit = QtWidgets.QLineEdit("all")
        self.epoch_edit.setMinimumWidth(100)
        self.epoch_edit.setToolTip("可写 all、0-20、0,2,4；索引为本次 FIF 保存数组索引。")
        self.epoch_edit.editingFinished.connect(self._selection_changed)
        epoch_row.addWidget(self.epoch_edit)
        layout.addLayout(epoch_row)
        time_row = QtWidgets.QHBoxLayout()
        time_row.addWidget(QtWidgets.QLabel("epoch 时间窗 s"))
        self.time_start = QtWidgets.QDoubleSpinBox()
        self.time_end = QtWidgets.QDoubleSpinBox()
        for widget in (self.time_start, self.time_end):
            widget.setDecimals(4)
            widget.setSingleStep(0.01)
            widget.valueChanged.connect(self._selection_changed)
        time_row.addWidget(self.time_start)
        time_row.addWidget(QtWidgets.QLabel("至"))
        time_row.addWidget(self.time_end)
        layout.addLayout(time_row)
        preview_row = QtWidgets.QHBoxLayout()
        preview_row.addWidget(QtWidgets.QLabel("右侧预览 epoch"))
        self.preview_prev_button = QtWidgets.QPushButton("‹")
        self.preview_prev_button.setMinimumSize(40, 32)
        self.preview_prev_button.setEnabled(False)
        self.preview_prev_button.setToolTip("切换到上一段预览；不改变正式分析的 epoch 子集。")
        self.preview_prev_button.clicked.connect(lambda: self._step_preview(-1))
        preview_row.addWidget(self.preview_prev_button)
        self.preview_epoch = QtWidgets.QSpinBox()
        self.preview_epoch.setRange(0, 0)
        self.preview_epoch.setVisible(False)
        self.preview_epoch.setToolTip("仅改变右侧原始波形预览；正式分析使用下方 epoch 子集设置。")
        self.preview_epoch.valueChanged.connect(self._preview_changed)
        preview_row.addWidget(self.preview_epoch)
        self.preview_epoch_label = QtWidgets.QLabel("Epoch — / —")
        self.preview_epoch_label.setMinimumWidth(108)
        self.preview_epoch_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.preview_epoch_label.setToolTip("显示编号从 1 开始；波形标题和分析表保留保存数组索引。")
        preview_row.addWidget(self.preview_epoch_label)
        self.preview_next_button = QtWidgets.QPushButton("›")
        self.preview_next_button.setMinimumSize(40, 32)
        self.preview_next_button.setEnabled(False)
        self.preview_next_button.setToolTip("切换到下一段预览；不改变正式分析的 epoch 子集。")
        self.preview_next_button.clicked.connect(lambda: self._step_preview(1))
        preview_row.addWidget(self.preview_next_button)
        preview_row.addStretch(1)
        layout.addLayout(preview_row)
        self.selection_label = QtWidgets.QLabel("选择数据量：尚未载入")
        layout.addWidget(self.selection_label)
        return box

    def _build_indicator_group(self) -> QtWidgets.QGroupBox:
        box, layout = self._group("指标")
        self.indicator_checks: dict[str, QtWidgets.QCheckBox] = {}
        descriptions = {
            "Quality": "读取质量和有效时长",
            "PSD": "Welch / Multitaper 功率谱",
            "Band Power": "频段绝对/相对功率",
            "FOOOF": "specparam/FOOOF 参数化",
            "MIC": "多变量 MIC",
            "MIM": "多变量 MIM",
            "wpli": "通道对加权相位滞后指数",
            "dpli": "通道对有向相位滞后指数",
            "wpli2_debiased": "通道对去偏平方 wPLI",
            "Time Delay": "PyBispectra 时间延迟",
        }
        connectivity_box = QtWidgets.QGroupBox("功能连接 Connectivity")
        connectivity_layout = QtWidgets.QVBoxLayout(connectivity_box)
        pair_hint = QtWidgets.QLabel("连接脑区对（先选择脑区对，再选择分析指标）")
        pair_hint.setStyleSheet(f"color: {GUI_COLORS['muted']};")
        connectivity_layout.addWidget(pair_hint)
        self.pair_checks: dict[tuple[str, str], QtWidgets.QCheckBox] = {}
        self.pair_checks_group = FlowCheckBoxGroup()
        self.pair_checks_group.changed.connect(self._selection_changed)
        connectivity_layout.addWidget(self.pair_checks_group)
        method_hint = QtWidgets.QLabel("Analysis method / 分析指标")
        method_hint.setStyleSheet(f"color: {GUI_COLORS['muted']};")
        connectivity_layout.addWidget(method_hint)
        method_grid = QtWidgets.QGridLayout()
        method_names = ("MIC", "MIM", "wpli", "dpli", "wpli2_debiased", "Time Delay")
        method_display_names = {"wpli": "wPLI", "dpli": "dPLI", "wpli2_debiased": "wPLI²_debiased", "Time Delay": "TDE"}
        for index, name in enumerate(method_names):
            checkbox = QtWidgets.QCheckBox(method_display_names.get(name, name))
            checkbox.setToolTip(descriptions[name])
            checkbox.stateChanged.connect(self._indicator_changed)
            self.indicator_checks[name] = checkbox
            method_grid.addWidget(checkbox, index // 3, index % 3)
        connectivity_layout.addLayout(method_grid)
        layout.addWidget(connectivity_box)
        for name in ("Quality", "PSD", "Band Power", "FOOOF"):
            checkbox = QtWidgets.QCheckBox(name)
            checkbox.setToolTip(descriptions[name])
            checkbox.stateChanged.connect(self._indicator_changed)
            self.indicator_checks[name] = checkbox
            layout.addWidget(checkbox)
        self._rebuild_pair_controls()
        return box

    def _build_parameter_group(self) -> QtWidgets.QGroupBox:
        box, layout = self._group("计算参数（实际传入后端）")
        self.parameter_tabs = QtWidgets.QTabWidget()
        self.parameter_widgets: dict[str, QtWidgets.QWidget] = {}
        self.parameter_labels: dict[str, QtWidgets.QLabel] = {}
        tab_layouts: dict[str, QtWidgets.QFormLayout] = {}
        for tab_name in ("PSD 方法 / 参数", "FOOOF", "Connectivity", "频段功率"):
            tab = QtWidgets.QWidget()
            form = QtWidgets.QFormLayout(tab)
            form.setContentsMargins(10, 10, 10, 10)
            form.setHorizontalSpacing(10)
            form.setVerticalSpacing(7)
            form.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
            form.setRowWrapPolicy(QtWidgets.QFormLayout.RowWrapPolicy.WrapLongRows)
            form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
            tab_layouts[tab_name] = form
            self.parameter_tabs.addTab(tab, tab_name)
        self.parameter_tabs.setUsesScrollButtons(True)
        self.parameter_tabs.tabBar().setExpanding(False)
        self.parameter_tabs.setToolTip("参数按功能分组；切换分析指标后，仅启用相关参数。")

        psd_content = QtWidgets.QWidget()
        self._psd_content = psd_content
        psd_layout = QtWidgets.QVBoxLayout(psd_content)
        psd_layout.setContentsMargins(0, 0, 0, 0)
        psd_layout.setSpacing(7)

        method_form = QtWidgets.QFormLayout()
        method_form.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self._add_parameter_to_form(method_form, "psd.method")
        psd_layout.addLayout(method_form)

        common_panel = QtWidgets.QGroupBox("通用参数")
        common_form = QtWidgets.QFormLayout(common_panel)
        common_form.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        for key in ("psd.epoch_aggregation", "psd.fmin_hz", "psd.fmax_hz"):
            self._add_parameter_to_form(common_form, key)
        psd_layout.addWidget(common_panel)

        self._psd_welch_panel = QtWidgets.QGroupBox("Welch 专属参数")
        welch_layout = QtWidgets.QVBoxLayout(self._psd_welch_panel)
        welch_form = QtWidgets.QFormLayout()
        welch_form.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        for key in ("psd.window", "psd.window_seconds", "psd.overlap_percent"):
            self._add_parameter_to_form(welch_form, key)
        welch_layout.addLayout(welch_form)
        self._psd_welch_advanced = CollapsiblePanel("高级参数")
        welch_advanced_form = QtWidgets.QFormLayout()
        welch_advanced_form.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        for key in ("psd.nfft", "psd.detrend", "psd.average"):
            self._add_parameter_to_form(welch_advanced_form, key)
        self._psd_welch_advanced.content_layout.addLayout(welch_advanced_form)
        self._psd_welch_advanced.toggle.setChecked(False)
        self._psd_welch_advanced._set_expanded(False)
        welch_layout.addWidget(self._psd_welch_advanced)
        self._psd_multitaper_panel = QtWidgets.QGroupBox("Multitaper 专属参数")
        multitaper_layout = QtWidgets.QVBoxLayout(self._psd_multitaper_panel)
        multitaper_form = QtWidgets.QFormLayout()
        multitaper_form.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self._add_parameter_to_form(multitaper_form, "psd.multitaper_bandwidth_hz")
        multitaper_layout.addLayout(multitaper_form)
        self._psd_multitaper_advanced = CollapsiblePanel("高级参数")
        multitaper_advanced_form = QtWidgets.QFormLayout()
        multitaper_advanced_form.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        for key in (
            "psd.multitaper_adaptive",
            "psd.multitaper_low_bias",
            "psd.multitaper_normalization",
            "psd.multitaper_remove_dc",
            "psd.multitaper_n_jobs",
        ):
            self._add_parameter_to_form(multitaper_advanced_form, key)
        self._psd_multitaper_advanced.content_layout.addLayout(multitaper_advanced_form)
        self._psd_multitaper_advanced.toggle.setChecked(False)
        self._psd_multitaper_advanced._set_expanded(False)
        multitaper_layout.addWidget(self._psd_multitaper_advanced)
        self._psd_method_stack = AdaptiveStackedWidget()
        self._psd_method_stack.setObjectName("psdMethodStack")
        self._psd_method_stack.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Preferred,
        )
        self._psd_method_stack.addWidget(self._psd_welch_panel)
        self._psd_method_stack.addWidget(self._psd_multitaper_panel)
        psd_layout.addWidget(self._psd_method_stack)
        tab_layouts["PSD 方法 / 参数"].addRow(psd_content)

        for definition in PARAMETER_DEFINITIONS:
            if definition.key.startswith(("psd.", "connectivity.", "time_delay.")):
                continue
            tab_name = {
                "psd": "PSD 方法 / 参数",
                "parameterization": "FOOOF",
            }.get(definition.key.split(".")[0], "PSD 方法 / 参数")
            widget = self._make_parameter_widget(definition)
            self.parameter_widgets[definition.key] = widget
            label = QtWidgets.QLabel(f"{definition.label} ({definition.unit})" if definition.unit else definition.label)
            label.setWordWrap(True)
            label.setToolTip(definition.help_text)
            self.parameter_labels[definition.key] = label
            tab_layouts[tab_name].addRow(label, widget)

        self._connectivity_panels: dict[str, QtWidgets.QGroupBox] = {}
        self._connectivity_panel_forms: dict[str, QtWidgets.QFormLayout] = {}
        connectivity_content = QtWidgets.QWidget()
        connectivity_layout = QtWidgets.QVBoxLayout(connectivity_content)
        connectivity_layout.setContentsMargins(0, 0, 0, 0)
        connectivity_layout.setSpacing(8)
        connectivity_scroll = QtWidgets.QScrollArea()
        connectivity_scroll.setWidgetResizable(True)
        connectivity_scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        connectivity_scroll.setWidget(connectivity_content)
        self._connectivity_scroll = connectivity_scroll

        common_panel = self._new_connectivity_panel(
            "共同频谱参数",
            "仅对 MIC、MIM、wPLI、dPLI 和 wPLI²_debiased 显示；TDE 使用下方独立参数。",
        )
        self._add_parameter_to_connectivity_panel(common_panel, "connectivity.mode")
        self._add_parameter_to_connectivity_panel(common_panel, "connectivity.fmin_hz")
        self._add_parameter_to_connectivity_panel(common_panel, "connectivity.fmax_hz")
        self._add_parameter_to_connectivity_panel(common_panel, "connectivity.mt_bandwidth_hz")
        self._add_parameter_to_connectivity_panel(common_panel, "connectivity.mt_adaptive")
        self._add_parameter_to_connectivity_panel(common_panel, "connectivity.mt_low_bias")
        self._add_parameter_to_connectivity_panel(common_panel, "connectivity.min_epochs")
        self._add_parameter_to_connectivity_panel(common_panel, "connectivity.n_jobs")
        self._add_parameter_to_connectivity_panel(common_panel, "connectivity.stability_n_subsamples")
        connectivity_layout.addWidget(common_panel)

        multivariate_panel = self._new_connectivity_panel(
            "多变量 rank（MIC / MIM）",
            "rank 表示每个脑区保留的信号维度；MIC 和 MIM 共用同一套 rank。",
        )
        for key in (
            "connectivity.rank_strategy",
            "connectivity.rank_variance_threshold",
        ):
            self._add_parameter_to_connectivity_panel(multivariate_panel, key)
        self.rank_mapping_table = QtWidgets.QTableWidget(0, 2)
        self.rank_mapping_table.setHorizontalHeaderLabels(["Region", "Fixed rank (0=auto)"])
        self.rank_mapping_table.setMaximumHeight(155)
        self.rank_mapping_table.horizontalHeader().setStretchLastSection(True)
        self.rank_mapping_table.itemChanged.connect(self._selection_changed)
        multivariate_panel.layout().addWidget(QtWidgets.QLabel("手动 rank（按当前 Channel Mapping 动态生成）"))  # type: ignore[union-attr]
        multivariate_panel.layout().addWidget(self.rank_mapping_table)  # type: ignore[union-attr]
        connectivity_layout.addWidget(multivariate_panel)

        mic_panel = self._new_connectivity_panel("MIC 专属参数", "MIC 输出成分数；MIM 不使用此参数。")
        self._add_parameter_to_connectivity_panel(mic_panel, "connectivity.n_components")
        connectivity_layout.addWidget(mic_panel)

        bivariate_panel = self._new_connectivity_panel(
            "wPLI / wPLI²_debiased 专属参数",
            "wPLI²_debiased 是独立指标；去偏结果不会通过开关覆盖普通 wPLI。",
        )
        self._add_parameter_to_connectivity_panel(bivariate_panel, "connectivity.region_pair_summary")
        debias_note = QtWidgets.QLabel("普通 wPLI 不提供额外 debias 开关；需要去偏平方结果时勾选 wPLI²_debiased。")
        debias_note.setWordWrap(True)
        bivariate_panel.layout().addWidget(debias_note)  # type: ignore[union-attr]
        connectivity_layout.addWidget(bivariate_panel)

        dpli_panel = self._new_connectivity_panel(
            "dPLI 专属说明",
            "dPLI 使用有序 seed → target 约定；seed/target 不是因果方向。",
        )
        direction_note = QtWidgets.QLabel("phase direction convention：数值 0.5 为中性；结果范围和方向解释沿用当前后端。")
        direction_note.setWordWrap(True)
        dpli_panel.layout().addWidget(direction_note)  # type: ignore[union-attr]
        connectivity_layout.addWidget(dpli_panel)

        tde_panel = self._new_connectivity_panel(
            "TDE 专属参数",
            "TDE 使用 PyBispectra 时间延迟参数；不会读取 MIC/MIM 的 rank 或 component。",
        )
        for key in (
            "time_delay.analysis_sfreq_hz",
            "time_delay.max_delay_ms",
            "time_delay.fmin_hz",
            "time_delay.fmax_hz",
            "time_delay.fft_window",
            "time_delay.n_points",
            "time_delay.n_jobs",
        ):
            self._add_parameter_to_connectivity_panel(tde_panel, key)
        tde_note = QtWidgets.QLabel("延迟正负号沿用当前后端约定；频率范围和延迟窗口均为 TDE 专属设置。")
        tde_note.setWordWrap(True)
        tde_panel.layout().addWidget(tde_note)  # type: ignore[union-attr]
        connectivity_layout.addWidget(tde_panel)
        connectivity_layout.addStretch(1)
        tab_layouts["Connectivity"].addRow(connectivity_scroll)

        band_box = QtWidgets.QGroupBox("可编辑频段（频段边界改动只重新汇总已有 PSD）")
        band_layout = QtWidgets.QVBoxLayout(band_box)
        self.band_table = QtWidgets.QTableWidget(0, 3)
        self.band_table.setHorizontalHeaderLabels(["名称", "下限 Hz", "上限 Hz"])
        self.band_table.setMinimumHeight(120)
        self.band_table.setAlternatingRowColors(True)
        self.band_table.horizontalHeader().setStretchLastSection(True)
        self.band_table.itemChanged.connect(self._selection_changed)
        band_layout.addWidget(self.band_table)
        band_buttons = QtWidgets.QHBoxLayout()
        add_band = QtWidgets.QPushButton("新增频段")
        add_band.clicked.connect(lambda: self._add_band_row("new_band", 1.0, 4.0))
        remove_band = QtWidgets.QPushButton("删除选中")
        remove_band.clicked.connect(self._remove_band_row)
        band_buttons.addWidget(add_band)
        band_buttons.addWidget(remove_band)
        band_layout.addLayout(band_buttons)
        denominator_row = QtWidgets.QHBoxLayout()
        denominator_row.addWidget(QtWidgets.QLabel("相对功率分母 Hz"))
        self.denominator_low = QtWidgets.QDoubleSpinBox()
        self.denominator_high = QtWidgets.QDoubleSpinBox()
        for widget in (self.denominator_low, self.denominator_high):
            widget.setRange(0.0, 10000.0)
            widget.setDecimals(4)
            widget.valueChanged.connect(self._selection_changed)
        denominator_row.addWidget(self.denominator_low)
        denominator_row.addWidget(QtWidgets.QLabel("至"))
        denominator_row.addWidget(self.denominator_high)
        band_layout.addLayout(denominator_row)
        tab_layouts["频段功率"].addRow(band_box)
        self.parameter_tabs.currentChanged.connect(self._selection_changed)
        method_widget = self.parameter_widgets.get("psd.method")
        if isinstance(method_widget, QtWidgets.QComboBox):
            method_widget.currentTextChanged.connect(self._update_psd_method_controls)
        connectivity_mode_widget = self.parameter_widgets.get("connectivity.mode")
        if isinstance(connectivity_mode_widget, QtWidgets.QComboBox):
            connectivity_mode_widget.currentTextChanged.connect(self._update_connectivity_controls)
        self._update_psd_method_controls()
        self._update_parameter_tabs()
        layout.addWidget(self.parameter_tabs)
        return box

    def _add_parameter_to_form(self, form: QtWidgets.QFormLayout, key: str) -> None:
        """Create one schema-backed control and add it to a form exactly once."""

        definition = next(item for item in PARAMETER_DEFINITIONS if item.key == key)
        widget = self._make_parameter_widget(definition)
        label = QtWidgets.QLabel(f"{definition.label} ({definition.unit})" if definition.unit else definition.label)
        label.setWordWrap(True)
        label.setToolTip(definition.help_text)
        self.parameter_widgets[key] = widget
        self.parameter_labels[key] = label
        form.addRow(label, widget)

    def _new_connectivity_panel(self, title: str, note: str) -> QtWidgets.QGroupBox:
        panel = QtWidgets.QGroupBox(title)
        panel_layout = QtWidgets.QVBoxLayout(panel)
        panel_layout.setContentsMargins(8, 10, 8, 8)
        panel_layout.setSpacing(5)
        label = QtWidgets.QLabel(note)
        label.setWordWrap(True)
        label.setStyleSheet(f"color: {GUI_COLORS['muted']};")
        panel_layout.addWidget(label)
        form = QtWidgets.QFormLayout()
        form.setHorizontalSpacing(8)
        form.setVerticalSpacing(6)
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form.setRowWrapPolicy(QtWidgets.QFormLayout.RowWrapPolicy.WrapLongRows)
        form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
        panel_layout.addLayout(form)
        self._connectivity_panels[title] = panel
        self._connectivity_panel_forms[title] = form
        panel.setVisible(False)
        return panel

    def _add_parameter_to_connectivity_panel(self, panel: QtWidgets.QGroupBox, key: str) -> None:
        definition = next(item for item in PARAMETER_DEFINITIONS if item.key == key)
        widget = self._make_parameter_widget(definition)
        label = QtWidgets.QLabel(f"{definition.label} ({definition.unit})" if definition.unit else definition.label)
        label.setWordWrap(True)
        label.setToolTip(definition.help_text)
        self.parameter_widgets[key] = widget
        self.parameter_labels[key] = label
        form = self._connectivity_panel_forms[panel.title()]
        form.addRow(label, widget)

    def _make_parameter_widget(self, definition: Any) -> QtWidgets.QWidget:
        current = config_value(self.base_config, definition.key, definition.default)
        if definition.key == "psd.window_seconds":
            current = float(config_value(self.base_config, "psd.nperseg", 1000)) / 1000.0
        elif definition.key == "psd.overlap_percent":
            nperseg = float(config_value(self.base_config, "psd.nperseg", 1000))
            current = 100.0 * float(config_value(self.base_config, "psd.noverlap", nperseg / 2)) / nperseg
        elif definition.key == "parameterization.fit_low_hz":
            current = config_value(self.base_config, "parameterization.fit_range_hz", [2.0, 150.0])[0]
        elif definition.key == "parameterization.fit_high_hz":
            current = config_value(self.base_config, "parameterization.fit_range_hz", [2.0, 150.0])[1]
        elif definition.key == "parameterization.peak_width_low_hz":
            current = config_value(self.base_config, "parameterization.peak_width_limits_hz", [1.0, 12.0])[0]
        elif definition.key == "parameterization.peak_width_high_hz":
            current = config_value(self.base_config, "parameterization.peak_width_limits_hz", [1.0, 12.0])[1]
        if definition.value_type == "choice":
            widget = QtWidgets.QComboBox()
            choices = {
                "psd.method": ["welch", "multitaper"],
                "psd.window": ["hann", "hamming", "blackman", "boxcar"],
                "psd.detrend": ["constant", "linear", "none"],
                "psd.average": ["mean", "median"],
                "psd.epoch_aggregation": ["mean", "median"],
                "parameterization.aperiodic_mode": ["fixed", "knee"],
                "connectivity.mode": ["multitaper", "fourier"],
                "connectivity.region_pair_summary": ["mean", "median"],
                "connectivity.rank_strategy": ["data_driven_energy_99pct", "fixed_rank"],
                "time_delay.fft_window": ["hamming", "hann", "blackman", "boxcar"],
            }.get(definition.key, [str(current)])
            widget.addItems(choices)
            index = widget.findText(str(current))
            widget.setCurrentIndex(max(0, index))
            widget.currentTextChanged.connect(self._selection_changed)
        elif definition.value_type == "bool":
            widget = QtWidgets.QCheckBox("启用")
            widget.setChecked(bool(current))
            widget.stateChanged.connect(self._selection_changed)
        elif definition.value_type == "int":
            widget = QtWidgets.QSpinBox()
            lower = int(definition.minimum if definition.minimum is not None else -2_000_000_000)
            upper = int(definition.maximum if definition.maximum is not None else 2_000_000_000)
            widget.setRange(lower, upper)
            widget.setValue(int(current or 0))
            widget.valueChanged.connect(self._selection_changed)
        else:
            widget = QtWidgets.QDoubleSpinBox()
            widget.setDecimals(4)
            widget.setRange(float(definition.minimum if definition.minimum is not None else -1e9), float(definition.maximum if definition.maximum is not None else 1e9))
            widget.setValue(float(current or 0.0))
            widget.valueChanged.connect(self._selection_changed)
        widget.setToolTip(definition.help_text)
        return widget

    def _update_psd_method_controls(self, *_args: Any) -> None:
        method_widget = self.parameter_widgets.get("psd.method")
        method = method_widget.currentText().strip().lower() if isinstance(method_widget, QtWidgets.QComboBox) else "welch"
        welch_keys = ("psd.window", "psd.window_seconds", "psd.overlap_percent", "psd.nfft", "psd.detrend", "psd.average")
        multitaper_keys = (
            "psd.multitaper_bandwidth_hz",
            "psd.multitaper_adaptive",
            "psd.multitaper_low_bias",
            "psd.multitaper_normalization",
            "psd.multitaper_remove_dc",
            "psd.multitaper_n_jobs",
        )
        # Keep the UI fail-safe while the schema/validation layer reports an
        # invalid value: an unknown or temporarily empty method falls back to
        # the first supported page rather than leaving both pages blank.
        show_multitaper = method == "multitaper"
        show_welch = not show_multitaper
        if hasattr(self, "_psd_method_stack"):
            self._psd_method_stack.setCurrentIndex(0 if show_welch else 1)
        # Keep the explicit visibility state as well as the stacked index.
        # This makes the state unambiguous to accessibility tools and tests,
        # while AdaptiveStackedWidget prevents the inactive page from reserving
        # layout height.
        self._psd_welch_panel.setVisible(show_welch)
        self._psd_multitaper_panel.setVisible(show_multitaper)
        for key in welch_keys:
            self.parameter_widgets[key].setEnabled(show_welch)
            self.parameter_labels[key].setEnabled(show_welch)
        for key in multitaper_keys:
            self.parameter_widgets[key].setEnabled(show_multitaper)
            self.parameter_labels[key].setEnabled(show_multitaper)
        self._psd_content.updateGeometry()
        self._psd_content.layout().invalidate()
        self._psd_content.layout().activate()
        self.parameter_tabs.currentWidget().updateGeometry()
        self.parameter_tabs.updateGeometry()

    def _update_connectivity_controls(self, *_args: Any) -> None:
        """Show only parameters belonging to the selected connectivity methods."""
        selected = set(self._selected_indicators()) if hasattr(self, "indicator_checks") else set()
        has_static_connectivity = bool(selected & {"MIC", "MIM", "wpli", "dpli", "wpli2_debiased"})
        has_tde = "Time Delay" in selected
        has_connectivity = has_static_connectivity or has_tde
        has_multivariate = bool(selected & {"MIC", "MIM"})
        has_bivariate = bool(selected & {"wpli", "dpli", "wpli2_debiased"})
        has_mic = "MIC" in selected
        mode_widget = self.parameter_widgets.get("connectivity.mode")
        mode = mode_widget.currentText().strip().lower() if isinstance(mode_widget, QtWidgets.QComboBox) else "multitaper"
        panel_visibility = {
            "共同频谱参数": has_static_connectivity,
            "多变量 rank（MIC / MIM）": has_multivariate,
            "MIC 专属参数": has_mic,
            "wPLI / wPLI²_debiased 专属参数": bool(selected & {"wpli", "wpli2_debiased"}),
            "dPLI 专属说明": "dpli" in selected,
            "TDE 专属参数": has_tde,
        }
        for title, panel in getattr(self, "_connectivity_panels", {}).items():
            panel.setVisible(panel_visibility.get(title, False))

        common_keys = (
            "connectivity.mode",
            "connectivity.fmin_hz",
            "connectivity.fmax_hz",
            "connectivity.min_epochs",
            "connectivity.n_jobs",
            "connectivity.stability_n_subsamples",
        )
        for key in common_keys:
            if key in self.parameter_widgets:
                self.parameter_widgets[key].setEnabled(has_connectivity)
            if key in self.parameter_labels:
                self.parameter_labels[key].setEnabled(has_connectivity)
        aggregation_key = "connectivity.region_pair_summary"
        if aggregation_key in self.parameter_widgets:
            self.parameter_widgets[aggregation_key].setEnabled(has_bivariate)
        if aggregation_key in self.parameter_labels:
            self.parameter_labels[aggregation_key].setEnabled(has_bivariate)
        for key in (
            "connectivity.rank_strategy",
            "connectivity.rank_variance_threshold",
            "connectivity.fixed_rank_M1",
            "connectivity.fixed_rank_STR",
            "connectivity.fixed_rank_PF",
            "connectivity.fixed_rank_SNr",
        ):
            if key in self.parameter_widgets:
                self.parameter_widgets[key].setEnabled(has_multivariate)
            if key in self.parameter_labels:
                self.parameter_labels[key].setEnabled(has_multivariate)
        for key in ("connectivity.mt_bandwidth_hz", "connectivity.mt_adaptive", "connectivity.mt_low_bias"):
            enabled = has_static_connectivity and mode == "multitaper"
            if key in self.parameter_widgets:
                self.parameter_widgets[key].setEnabled(enabled)
            if key in self.parameter_labels:
                self.parameter_labels[key].setEnabled(enabled)
        if "connectivity.n_components" in self.parameter_widgets:
            self.parameter_widgets["connectivity.n_components"].setVisible(has_mic)
            self.parameter_widgets["connectivity.n_components"].setEnabled(has_mic)
        if "connectivity.n_components" in self.parameter_labels:
            self.parameter_labels["connectivity.n_components"].setVisible(has_mic)
            self.parameter_labels["connectivity.n_components"].setEnabled(has_mic)
        for key in (
            "time_delay.analysis_sfreq_hz",
            "time_delay.max_delay_ms",
            "time_delay.fmin_hz",
            "time_delay.fmax_hz",
            "time_delay.fft_window",
            "time_delay.n_points",
            "time_delay.n_jobs",
        ):
            if key in self.parameter_widgets:
                self.parameter_widgets[key].setEnabled(has_tde)
            if key in self.parameter_labels:
                self.parameter_labels[key].setEnabled(has_tde)

    def _build_task_group(self) -> QtWidgets.QGroupBox:
        box, layout = self._group("预设与历史")
        row2 = QtWidgets.QGridLayout()
        for text, callback in (("保存预设", self._save_preset), ("载入预设", self._load_preset), ("恢复默认", self._restore_defaults), ("载入历史", self._load_history)):
            button = QtWidgets.QPushButton(text)
            button.clicked.connect(callback)
            button.setToolTip({"保存预设": "保存当前指标、选择范围和参数。", "载入预设": "载入已保存的指标和参数。", "恢复默认": "恢复配置文件中的默认值。", "载入历史": "载入已有运行目录并重新查看结果。"}[text])
            index = row2.count()
            row2.addWidget(button, index // 2, index % 2)
        layout.addLayout(row2)
        open_button = QtWidgets.QPushButton("打开结果目录")
        open_button.setToolTip("在文件管理器中打开当前输出目录。")
        open_button.clicked.connect(self._open_output)
        layout.addWidget(open_button)
        return box

    def _restore_defaults(self) -> None:
        for definition in PARAMETER_DEFINITIONS:
            widget = self.parameter_widgets.get(definition.key)
            if widget is None:
                continue
            value = self._make_parameter_value_from_config(definition)
            if isinstance(widget, QtWidgets.QComboBox):
                index = widget.findText(str(value))
                widget.setCurrentIndex(max(0, index))
            elif isinstance(widget, QtWidgets.QCheckBox):
                widget.setChecked(bool(value))
            elif isinstance(widget, QtWidgets.QSpinBox):
                widget.setValue(int(value or 0))
            else:
                widget.setValue(float(value))
        self.band_table.setRowCount(0)
        for name, bounds in self.base_config.get("bands", {}).items():
            self._add_band_row(str(name), float(bounds[0]), float(bounds[1]))
        denominator = self.base_config.get("relative_power", {}).get("denominator_hz", [1.0, 100.0])
        self.denominator_low.setValue(float(denominator[0]))
        self.denominator_high.setValue(float(denominator[1]))
        for row in range(self.rank_mapping_table.rowCount()):
            item = self.rank_mapping_table.item(row, 1)
            if item is not None:
                item.setText("0")
        self._update_psd_method_controls()
        self._set_dirty(False)

    def _make_parameter_value_from_config(self, definition: Any) -> Any:
        if definition.key == "psd.window_seconds":
            return float(self.base_config.get("psd", {}).get("nperseg", 1000)) / 1000.0
        if definition.key == "psd.overlap_percent":
            cfg = self.base_config.get("psd", {})
            return float(cfg.get("noverlap", 500)) / float(cfg.get("nperseg", 1000)) * 100.0
        if definition.key == "parameterization.fit_low_hz":
            return self.base_config.get("parameterization", {}).get("fit_range_hz", [2.0, 150.0])[0]
        if definition.key == "parameterization.fit_high_hz":
            return self.base_config.get("parameterization", {}).get("fit_range_hz", [2.0, 150.0])[1]
        if definition.key == "parameterization.peak_width_low_hz":
            return self.base_config.get("parameterization", {}).get("peak_width_limits_hz", [1.0, 12.0])[0]
        if definition.key == "parameterization.peak_width_high_hz":
            return self.base_config.get("parameterization", {}).get("peak_width_limits_hz", [1.0, 12.0])[1]
        return config_value(self.base_config, definition.key, definition.default)

    def _add_band_row(self, name: str, low: float, high: float) -> None:
        row = self.band_table.rowCount()
        self.band_table.insertRow(row)
        self.band_table.setItem(row, 0, QtWidgets.QTableWidgetItem(str(name)))
        self.band_table.setItem(row, 1, QtWidgets.QTableWidgetItem(str(low)))
        self.band_table.setItem(row, 2, QtWidgets.QTableWidgetItem(str(high)))

    def _remove_band_row(self) -> None:
        rows = sorted({index.row() for index in self.band_table.selectedIndexes()}, reverse=True)
        for row in rows:
            self.band_table.removeRow(row)
        self._set_dirty(True)

    def _choose_files(self) -> None:
        paths, _ = QtWidgets.QFileDialog.getOpenFileNames(self, "选择 FIF 文件", str(PROJECT_ROOT / "data" / "real"), "FIF files (*.fif *.fif.gz);;All files (*.*)")
        if paths:
            self.load_paths(paths)

    def load_paths(self, paths: list[str]) -> None:
        self.result_payloads.clear()
        self.result_records.clear()
        self.result_combo.clear()
        self._displayed_result_key = ""
        self._collapse_result_table()
        self.quality_alert_text.clear()
        self.status_text.clear()
        self._log(f"开始读取 {len(paths)} 个 FIF；将自动计算质量和实际有效时长…")
        self.task_label.setText("状态：正在读取 FIF 和通道映射…")
        self.run_button.setEnabled(False)
        self.inspect_thread = QtCore.QThread(self)
        worker = InspectWorker(paths, self.metadata_dir, self.config_path)
        self._active_inspect_task_id = worker.task_id
        self.inspect_thread.worker = worker  # type: ignore[attr-defined]
        worker.moveToThread(self.inspect_thread)
        self.inspect_thread.started.connect(worker.run)
        worker.finished.connect(self._inspection_finished)
        worker.failed.connect(self._inspection_failed)
        worker.finished.connect(self.inspect_thread.quit)
        worker.failed.connect(self.inspect_thread.quit)
        self.inspect_thread.finished.connect(worker.deleteLater)
        self.inspect_thread.finished.connect(self.inspect_thread.deleteLater)
        self.inspect_thread.start()

    def _inspection_finished(self, payload: list[dict[str, Any]] | dict[str, Any]) -> None:
        if isinstance(payload, dict):
            if str(payload.get("task_id", "")) != self._active_inspect_task_id:
                return
            infos = payload.get("infos", [])
        else:
            infos = payload
        self.file_infos = infos
        self.file_selections = {
            self._file_selection_key(info): {
                "selected_channel_names": [str(name) for name in info["loaded"].ch_names],
                "selected_epoch_indices": list(range(int(info.get("n_epochs", 0)))),
                "epoch_text": "all",
                "selected_region_pairs": [list(pair) for pair in region_pairs(info.get("channel_table", pd.DataFrame()))],
                "selection": {
                    "time_start_s": float(info.get("tmin", 0.0)),
                    "time_end_s": float(info.get("tmax", 0.0)) + 1.0 / float(info.get("sfreq", 1.0)),
                },
            }
            for info in infos
            if self._file_selection_key(info)
        }
        self.file_combo.blockSignals(True)
        self.file_combo.clear()
        for info in infos:
            self.file_combo.addItem(Path(info["path"]).name, str(info["path"]))
            index = self.file_combo.count() - 1
            self.file_combo.setItemData(index, str(info["path"]), QtCore.Qt.ItemDataRole.ToolTipRole)
        self.file_combo.blockSignals(False)
        if infos:
            self.file_combo.setCurrentIndex(0)
            self._file_changed(0)
            for info in infos:
                quality_file = info.get("quality_file", {})
                self._log(
                    f"自动质量检查完成：{Path(info['path']).name}；"
                    f"实际有效时长={float(info.get('effective_duration_s', 0.0)):g} s；"
                    f"异常 epoch-channel={int(quality_file.get('n_fail_epoch_channel_rows', 0))} fail / "
                    f"{int(quality_file.get('n_warn_epoch_channel_rows', 0))} warn。"
                )
        self.run_button.setEnabled(True)
        self.run_button.setText("Run Analysis")
        self.task_label.setText(f"状态：已读取 {len(infos)} 个文件。")
        self._set_dirty(True)

    def _inspection_failed(self, payload: str | dict[str, Any]) -> None:
        if isinstance(payload, dict):
            if str(payload.get("task_id", "")) != self._active_inspect_task_id:
                return
            message = str(payload.get("message", "读取失败"))
        else:
            message = str(payload)
        self.run_button.setEnabled(True)
        self.run_button.setText("Failed")
        self.task_label.setText(f"读取失败：{message}")
        self._show_message(QtWidgets.QMessageBox.Icon.Critical, "读取 FIF 失败", message)

    def _clear_files(self) -> None:
        self.file_infos = []
        self.file_selections.clear()
        self.current_info = None
        self.result_payloads.clear()
        self.result_records.clear()
        self._displayed_result_key = ""
        self.file_combo.clear()
        self.result_combo.clear()
        self.channel_list.clear()
        self.mapping_table.setRowCount(0)
        self.region_checks_group.clear()
        self.pair_checks_group.clear()
        self.region_checks.clear()
        self.pair_checks.clear()
        self.mapping_status_label.setText("尚未载入文件。")
        self.header_dataset_label.setText("未载入数据集")
        self.header_data_summary_label.setText("Epoch — / —；片段 —；通道 — / —")
        self.run_button.setText("Run Analysis")
        self.data_info_label.setText("尚未载入文件。")
        self.selection_label.setText("选择数据量：尚未载入")
        self._update_preview_epoch_label()
        self.preview_prev_button.setEnabled(False)
        self.preview_next_button.setEnabled(False)
        self.quality_alert_text.clear()
        self._collapse_result_table()
        self.status_text.clear()
        self.band_power_view.setVisible(False)
        self.fooof_view.setVisible(False)
        self.connectivity_view.setVisible(False)
        self.general_plot_widget.setVisible(True)
        self.canvas.figure.clear()
        self.canvas.draw_idle()
        self._set_dirty(True)

    def _file_changed(self, index: int) -> None:
        self._capture_current_file_selection()
        if 0 <= index < len(self.file_infos):
            self.current_info = self.file_infos[index]
            self._populate_current_file()

    def _file_selection_key(self, info: dict[str, Any] | None = None) -> str:
        source = info or self.current_info or {}
        return str(source.get("file_uid") or source.get("path") or "")

    def _capture_current_file_selection(self) -> None:
        if self.current_info is None or not hasattr(self, "channel_list"):
            return
        key = self._file_selection_key()
        if not key:
            return
        epoch_text = self.epoch_edit.text().strip() if hasattr(self, "epoch_edit") else "all"
        epochs = self._parse_epochs(epoch_text, self.current_info["n_epochs"], show_error=False)
        self.file_selections[key] = {
            "selected_channel_names": self._selected_channel_names(),
            "selected_epoch_indices": epochs if epochs else [],
            "epoch_text": epoch_text,
            "selected_region_pairs": [list(pair) for pair, checkbox in self.pair_checks.items() if checkbox.isChecked()],
            "selection": {"time_start_s": self.time_start.value(), "time_end_s": self.time_end.value()},
        }

    def _populate_current_file(self) -> None:
        if self.current_info is None:
            return
        info = self.current_info
        table = info["channel_table"]
        self._populate_mapping_table()
        self._rebuild_region_controls()
        self._rebuild_pair_controls()
        self._populate_rank_mapping_table()
        mapping = {str(row.channel_name): row for row in table.itertuples()}
        quality_channel = info.get("quality", {}).get("channel", pd.DataFrame())
        quality_by_name = {
            str(row.channel_name): row
            for row in quality_channel.itertuples()
        } if isinstance(quality_channel, pd.DataFrame) and not quality_channel.empty else {}
        self.channel_list.blockSignals(True)
        self.channel_list.clear()
        for name in info["loaded"].ch_names:
            row = mapping.get(str(name))
            region = str(getattr(row, "region", "")) if row else ""
            physical = getattr(row, "physical_channel_number", "") if row else ""
            quality_row = quality_by_name.get(str(name))
            n_fail = int(getattr(quality_row, "n_fail_epochs", 0)) if quality_row else 0
            n_warn = int(getattr(quality_row, "n_warn_epochs", 0)) if quality_row else 0
            quality_marker = " ⚠" if n_fail or n_warn else ""
            text = f"{name}{quality_marker} | 物理 {physical or '?'} | {region or '未映射'}"
            item = QtWidgets.QListWidgetItem(text)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, str(name))
            item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(QtCore.Qt.CheckState.Checked)
            if quality_row is not None and (n_fail or n_warn):
                flags = set()
                rows = info["quality"]["epoch_channel"].loc[
                    info["quality"]["epoch_channel"]["channel_name"].astype(str) == str(name), "quality_flags"
                ]
                for value in rows.astype(str):
                    flags.update(flag for flag in value.split(";") if flag)
                severity = "fail" if n_fail else "warn"
                item.setToolTip(
                    f"自动质量：{severity}\n"
                    f"fail epoch={n_fail}；warn epoch={n_warn}\n"
                    f"原因：{', '.join(sorted(flags)) or '见右侧质量提示'}"
                )
                item.setForeground(QtGui.QColor("#b00020" if n_fail else "#a06000"))
            else:
                item.setToolTip("自动质量：当前阈值下未发现 fail/warn")
            self.channel_list.addItem(item)
        self.channel_list.blockSignals(False)
        saved = self.file_selections.get(self._file_selection_key(info), {})
        if saved:
            saved_channels = set(map(str, saved.get("selected_channel_names", [])))
            self.channel_list.blockSignals(True)
            for row_index in range(self.channel_list.count()):
                item = self.channel_list.item(row_index)
                name = str(item.data(QtCore.Qt.ItemDataRole.UserRole))
                item.setCheckState(QtCore.Qt.CheckState.Checked if name in saved_channels else QtCore.Qt.CheckState.Unchecked)
            self.channel_list.blockSignals(False)
            if "epoch_text" in saved:
                self.epoch_edit.setText(str(saved["epoch_text"]))
            saved_selection = saved.get("selection", {})
            if isinstance(saved_selection, dict):
                if saved_selection.get("time_start_s") is not None:
                    self.time_start.setValue(float(saved_selection["time_start_s"]))
                if saved_selection.get("time_end_s") is not None:
                    self.time_end.setValue(float(saved_selection["time_end_s"]))
            if "selected_region_pairs" in saved:
                saved_pairs = {tuple(map(str, pair)) for pair in saved.get("selected_region_pairs", [])}
                for pair, checkbox in self.pair_checks.items():
                    checkbox.setChecked(tuple(pair) in saved_pairs)
        self.time_start.setRange(info["tmin"], info["tmax"] + 1.0 / info["sfreq"])
        self.time_end.setRange(info["tmin"], info["tmax"] + 1.0 / info["sfreq"])
        if not saved:
            self.time_start.setValue(info["tmin"])
            self.time_end.setValue(info["tmax"] + 1.0 / info["sfreq"])
        self.preview_epoch.blockSignals(True)
        self.preview_epoch.setRange(0, max(0, info["n_epochs"] - 1))
        self.preview_epoch.setValue(0)
        self.preview_epoch.blockSignals(False)
        self._update_preview_epoch_label()
        has_epochs = int(info.get("n_epochs", 0)) > 0
        self.preview_prev_button.setEnabled(has_epochs)
        self.preview_next_button.setEnabled(has_epochs)
        quality_file = info.get("quality_file", {})
        quality_status = "fail" if int(quality_file.get("n_fail_epoch_channel_rows", 0)) else ("warn" if int(quality_file.get("n_warn_epoch_channel_rows", 0)) else "ok")
        self.data_info_label.setText(
            f"文件：{Path(info['path']).name}\n"
            f"采样率：{info['sfreq']:g} Hz；形状：{info['n_epochs']} × {info['n_channels']} × {info['n_times']}\n"
            f"epoch 时间：{info['tmin']:g}–{info['tmax']:g} s；保留数据名义时长：{float(info.get('nominal_duration_s', 0.0)):g} s\n"
            f"实际有效时长：{float(info.get('effective_duration_s', 0.0)):g} s；"
            f"候选 epoch：{info.get('n_candidate_epochs', info['n_epochs'])}，上游删除：{info.get('n_dropped_candidates', 0)}\n"
            f"自动质量：{quality_status}；fail={int(quality_file.get('n_fail_epoch_channel_rows', 0))}，"
            f"warn={int(quality_file.get('n_warn_epoch_channel_rows', 0))}\n"
            f"SHA-256：{info['sha256'][:16]}…"
        )
        self.header_dataset_label.setText(Path(info["path"]).name)
        self.header_dataset_label.setToolTip(str(info["path"]))
        self._update_header_data_summary()
        self.data_info_label.setToolTip(str(info["path"]))
        self._update_selection_label()
        self._show_quality_alert()
        self._update_raw_preview()

    def _apply_region_selection(self) -> None:
        if self.current_info is None:
            return
        selected_regions = {name for name, checkbox in self.region_checks.items() if checkbox.isChecked()}
        table = self.current_info["channel_table"]
        names = set(table.loc[table["region"].astype(str).isin(selected_regions), "channel_name"].astype(str))
        self.channel_list.blockSignals(True)
        for index in range(self.channel_list.count()):
            item = self.channel_list.item(index)
            name = str(item.data(QtCore.Qt.ItemDataRole.UserRole))
            item.setCheckState(QtCore.Qt.CheckState.Checked if name in names else QtCore.Qt.CheckState.Unchecked)
        self.channel_list.blockSignals(False)
        self._selection_changed()
        self._update_raw_preview()
        self._refresh_band_power_filters()
        self._refresh_fooof_filters()

    def _selection_changed(self, *_args: Any) -> None:
        self._update_selection_label()
        self._set_dirty(True)
        self._refresh_fooof_filters()
        if hasattr(self, "_refresh_connectivity_filters"):
            self._refresh_connectivity_filters()

    def _channel_selection_changed(self, *_args: Any) -> None:
        self._selection_changed()
        self._update_raw_preview()
        self._refresh_band_power_filters()
        self._refresh_fooof_filters()
        if hasattr(self, "_refresh_connectivity_filters"):
            self._refresh_connectivity_filters()

    def _preview_changed(self, *_args: Any) -> None:
        self._update_preview_epoch_label()
        self._update_raw_preview()

    def _step_preview(self, delta: int) -> None:
        if self.current_info is None:
            return
        current = self.preview_epoch.value()
        target = min(max(0, current + int(delta)), max(0, self.current_info["n_epochs"] - 1))
        if target != current:
            self.preview_epoch.setValue(target)

    def _update_preview_epoch_label(self) -> None:
        if self.current_info is None:
            self.preview_epoch_label.setText("Epoch — / —")
            if hasattr(self, "header_data_summary_label"):
                self.header_data_summary_label.setText("Epoch — / —；片段 —；通道 — / —")
            return
        total = int(self.current_info.get("n_epochs", 0))
        current = min(max(0, self.preview_epoch.value()), max(0, total - 1))
        self.preview_epoch_label.setText(f"Epoch {current + 1} / {total}")
        self._update_header_data_summary()

    def _update_header_data_summary(self) -> None:
        """Keep the fixed header factual and synchronized with current UI state."""
        if not hasattr(self, "header_data_summary_label"):
            return
        if self.current_info is None:
            self.header_data_summary_label.setText("Epoch — / —；片段 —；通道 — / —")
            return
        info = self.current_info
        total_epochs = int(info.get("n_epochs", 0))
        current_epoch = min(max(0, int(self.preview_epoch.value())), max(0, total_epochs - 1)) + 1 if total_epochs else 0
        duration = float(info.get("n_times", 0)) / float(info.get("sfreq", 1.0)) if float(info.get("sfreq", 0.0)) > 0 else np.nan
        selected_count = len(self._selected_channel_names()) if hasattr(self, "channel_list") else 0
        duration_text = f"{duration:g} s" if np.isfinite(duration) else "—"
        self.header_data_summary_label.setText(
            f"Epoch {current_epoch} / {total_epochs}；片段 {duration_text}；"
            f"通道 {int(info.get('n_channels', 0))} / {selected_count}"
        )

    def _update_selection_label(self) -> None:
        if self.current_info is None:
            return
        channels = self._selected_channel_names()
        epochs = self._parse_epochs(self.epoch_edit.text(), self.current_info["n_epochs"], show_error=False)
        duration = max(0.0, self.time_end.value() - self.time_start.value())
        self.selection_label.setText(f"选择数据量：{len(channels)} 通道 × {len(epochs)} epoch × {duration:g} s；约 {len(epochs) * duration:g} 有效秒")
        self._update_header_data_summary()

    def _raw_preview_payload(self) -> dict[str, Any] | None:
        if self.current_info is None:
            return None
        info = self.current_info
        loaded = info["loaded"]
        channel_names = self._selected_channel_names()
        index_by_name = {str(name): index for index, name in enumerate(loaded.ch_names)}
        channel_indices = [index_by_name[name] for name in channel_names if name in index_by_name]
        epoch_index = min(max(0, self.preview_epoch.value()), max(0, info["n_epochs"] - 1))
        raw_data = loaded.data[epoch_index, channel_indices, :] if channel_indices else np.empty((0, loaded.data.shape[-1]), dtype=float)
        quality = info.get("quality", {})
        return {
            "metric": "Raw Waveform",
            "file_id": str(info.get("file_id") or Path(info["path"]).stem),
            "file_uid": str(info.get("file_uid", "")),
            "display_name": str(info.get("display_name") or Path(info["path"]).name),
            "raw_data": raw_data,
            "channel_names": [loaded.ch_names[index] for index in channel_indices],
            "preview_epoch_index": epoch_index,
            "times_s": loaded.tmin + np.arange(loaded.data.shape[-1], dtype=float) / loaded.sfreq,
            "sfreq": loaded.sfreq,
            "tmin": loaded.tmin,
            "tables": {
                "channel_table": info.get("channel_table", pd.DataFrame()).loc[info.get("channel_table", pd.DataFrame())["channel_name"].astype(str).isin(channel_names)].copy() if isinstance(info.get("channel_table", pd.DataFrame()), pd.DataFrame) and not info.get("channel_table", pd.DataFrame()).empty else pd.DataFrame(),
                "quality_epoch_channel": quality.get("epoch_channel", pd.DataFrame()),
                "quality_epoch": quality.get("epoch", pd.DataFrame()),
                "quality_channel": quality.get("channel", pd.DataFrame()),
                "quality_file": quality.get("file", pd.DataFrame()),
            },
        }

    def _result_key(self, payload: dict[str, Any], metric: str | None = None) -> str:
        metric_name = str(metric or payload.get("metric", "Result"))
        identity = str(payload.get("file_uid") or payload.get("file_id") or "file")
        return f"{identity} | {metric_name}"

    def _store_result_payload(self, payload: dict[str, Any], record: dict[str, Any] | None = None) -> str:
        """Store a result under a stable file key while keeping a readable label."""
        key = self._result_key(payload)
        metric = str(payload.get("metric", "Result"))
        file_id = str(payload.get("file_id") or payload.get("display_name") or "file")
        label = f"{file_id} | {metric}"
        existing_label_index = self.result_combo.findText(label)
        existing_key = self.result_combo.itemData(existing_label_index) if existing_label_index >= 0 else None
        if existing_label_index >= 0 and existing_key != key:
            short_uid = str(payload.get("file_uid", ""))[:8]
            label = f"{file_id} [{short_uid}] | {metric}" if short_uid else f"{file_id} [{key[:8]}] | {metric}"
        self.result_payloads[key] = payload
        if record is not None:
            self.result_records[key] = record
        index = self.result_combo.findData(key)
        if index < 0:
            self.result_combo.addItem(label, key)
        else:
            self.result_combo.setItemText(index, label)
        return key

    def _current_result_key(self) -> str:
        if not hasattr(self, "result_combo"):
            return ""
        value = self.result_combo.currentData()
        return str(value) if value not in (None, "") else self.result_combo.currentText()

    def _update_raw_preview(self) -> None:
        payload = self._raw_preview_payload()
        if payload is None:
            return
        with QtCore.QSignalBlocker(self.result_combo):
            key = self._store_result_payload(payload)
            index = self.result_combo.findData(key)
            if index >= 0:
                self.result_combo.setCurrentIndex(index)
        self._show_payload(payload)

    def _show_quality_alert(self) -> None:
        if self.current_info is None:
            self.quality_alert_text.clear()
            self.quality_summary_label.setText("质量：导入 FIF 后自动检查通道与 epoch。")
            self.quality_summary_label.setToolTip("")
            return
        info = self.current_info
        quality = info.get("quality", {})
        quality_file = info.get("quality_file", {})
        lines = [
            f"文件：{Path(info['path']).name}",
            f"实际有效时长：{float(info.get('effective_duration_s', 0.0)):g} s（按每个保留 epoch 的有限样本计算）",
            f"质量阈值来源：{info.get('quality_config_path', '')}",
        ]
        dropped = info.get("dropped_candidates", [])
        if dropped:
            lines.append(f"上游已删除候选分段 {len(dropped)} 个：" + "；".join(f"#{row['original_candidate_index']}({row['drop_reason']})" for row in dropped[:20]))

        channel_table = info.get("channel_table", pd.DataFrame())
        channel_meta = {
            str(row.channel_name): f"物理 {getattr(row, 'physical_channel_number', '') or '?'} / {getattr(row, 'region', '') or '未映射'}"
            for row in channel_table.itertuples()
        } if isinstance(channel_table, pd.DataFrame) else {}
        channel_quality = quality.get("channel", pd.DataFrame())
        epoch_quality = quality.get("epoch", pd.DataFrame())
        epoch_channel = quality.get("epoch_channel", pd.DataFrame())
        bad_channels = channel_quality.loc[
            (channel_quality.get("n_fail_epochs", pd.Series(dtype=int)) > 0)
            | (channel_quality.get("n_warn_epochs", pd.Series(dtype=int)) > 0)
        ] if isinstance(channel_quality, pd.DataFrame) and not channel_quality.empty else pd.DataFrame()
        bad_epochs = epoch_quality.loc[epoch_quality["quality_status"].astype(str) != "ok"] if isinstance(epoch_quality, pd.DataFrame) and not epoch_quality.empty else pd.DataFrame()
        if bad_channels.empty and bad_epochs.empty and not dropped:
            lines.append("未发现当前阈值下的 fail/warn。质量标记不会自动删除数据，请仍结合原始波形和 PSD 判断。")
        else:
            lines.append(
                f"检测汇总：epoch-channel fail={int(quality_file.get('n_fail_epoch_channel_rows', 0))}，"
                f"warn={int(quality_file.get('n_warn_epoch_channel_rows', 0))}。以下仅为提示，不是自动排除。"
            )
            if not bad_channels.empty:
                lines.append("可疑通道：")
                for row in bad_channels.itertuples():
                    channel_name = str(row.channel_name)
                    flags = set()
                    if isinstance(epoch_channel, pd.DataFrame) and not epoch_channel.empty:
                        matches = epoch_channel.loc[epoch_channel["channel_name"].astype(str) == channel_name, "quality_flags"]
                        for value in matches.astype(str):
                            flags.update(flag for flag in value.split(";") if flag)
                    lines.append(
                        f"  - {channel_name}（{channel_meta.get(channel_name, '物理 ? / 未映射')}）："
                        f"fail epoch={int(getattr(row, 'n_fail_epochs', 0))}，warn epoch={int(getattr(row, 'n_warn_epochs', 0))}；"
                        f"原因={','.join(sorted(flags)) or '见质量表'}"
                    )
            if not bad_epochs.empty:
                lines.append("可疑分段（epoch 保存数组索引）：")
                for row in bad_epochs.itertuples():
                    index = int(row.epoch_index)
                    names = []
                    if isinstance(epoch_channel, pd.DataFrame) and not epoch_channel.empty:
                        matches = epoch_channel.loc[
                            (epoch_channel["epoch_index"].astype(int) == index)
                            & (epoch_channel["quality_status"].astype(str) != "ok")
                        ]
                        names = [
                            f"{name}({flags})"
                            for name, flags in zip(matches["channel_name"].astype(str), matches["quality_flags"].astype(str), strict=False)
                        ]
                    lines.append(
                        f"  - epoch {index}：状态={row.quality_status}，"
                        f"异常通道={', '.join(names) or '见质量表'}"
                    )
        detail_text = "\n".join(lines)
        self.quality_alert_text.setPlainText(detail_text)
        self.quality_alert_text.verticalScrollBar().setValue(0)
        n_bad_channels = len(bad_channels)
        n_bad_epochs = len(bad_epochs)
        n_dropped = len(dropped)
        duration = float(info.get("effective_duration_s", 0.0))
        if n_bad_channels or n_bad_epochs or n_dropped:
            summary = (
                f"质量：可疑通道 {n_bad_channels}；可疑 epoch {n_bad_epochs}；"
                f"上游删除 {n_dropped}；有效时长 {duration:g} s。"
            )
        else:
            summary = f"质量：当前阈值下未发现 fail/warn；有效时长 {duration:g} s。"
        self.quality_summary_label.setText(summary)
        self.quality_summary_label.setToolTip(detail_text)

    def _selected_channel_names(self) -> list[str]:
        names: list[str] = []
        for index in range(self.channel_list.count()):
            item = self.channel_list.item(index)
            if item.checkState() == QtCore.Qt.CheckState.Checked:
                names.append(str(item.data(QtCore.Qt.ItemDataRole.UserRole)))
        return names

    def _parse_epochs(self, text: str, n_epochs: int, show_error: bool = True) -> list[int]:
        text = text.strip().lower()
        if text in {"", "all", "全部"}:
            return list(range(n_epochs))
        values: set[int] = set()
        try:
            for piece in text.replace("，", ",").split(","):
                piece = piece.strip()
                if not piece:
                    continue
                if "-" in piece:
                    low, high = [int(value.strip()) for value in piece.split("-", 1)]
                    values.update(range(low, high + 1))
                else:
                    values.add(int(piece))
            parsed = sorted(value for value in values if 0 <= value < n_epochs)
            if not parsed:
                raise ValueError("没有落在有效 epoch 范围内的索引")
            return parsed
        except Exception as exc:  # noqa: BLE001 - user-facing validation
            if show_error:
                self._show_message(QtWidgets.QMessageBox.Icon.Warning, "epoch 子集无效", f"{exc}")
            return []

    def _indicator_changed(self, *_args: Any) -> None:
        self._update_parameter_tabs()
        self._set_dirty(True)

    def _update_parameter_tabs(self) -> None:
        selected = self._selected_indicators()
        selected_set = set(selected)
        tab_enabled = (
            bool(selected_set & {"PSD", "Band Power", "FOOOF"}),
            "FOOOF" in selected_set,
            bool(selected_set & {"MIC", "MIM", "wpli", "dpli", "wpli2_debiased", "Time Delay"}),
            bool(selected_set & {"PSD", "Band Power", "FOOOF"}),
        )
        for index, enabled in enumerate(tab_enabled):
            self.parameter_tabs.setTabEnabled(index, enabled)
            self.parameter_tabs.setTabVisible(index, enabled)
        self._update_psd_method_controls()
        self._update_connectivity_controls()

    def _selected_indicators(self) -> list[str]:
        return [name for name, checkbox in self.indicator_checks.items() if checkbox.isChecked()]

    def _read_parameter_values(self, *, active_psd_only: bool = True) -> dict[str, Any]:
        values: dict[str, Any] = {}
        method_widget = self.parameter_widgets.get("psd.method")
        psd_method = method_widget.currentText().strip().lower() if isinstance(method_widget, QtWidgets.QComboBox) else "welch"
        common_psd_keys = {"psd.method", "psd.epoch_aggregation", "psd.fmin_hz", "psd.fmax_hz"}
        welch_keys = {"psd.window", "psd.window_seconds", "psd.overlap_percent", "psd.nfft", "psd.detrend", "psd.average"}
        multitaper_keys = {
            "psd.multitaper_bandwidth_hz",
            "psd.multitaper_adaptive",
            "psd.multitaper_low_bias",
            "psd.multitaper_normalization",
            "psd.multitaper_remove_dc",
            "psd.multitaper_n_jobs",
        }
        active_psd_keys = common_psd_keys | (welch_keys if psd_method == "welch" else multitaper_keys)
        for definition in PARAMETER_DEFINITIONS:
            if active_psd_only and definition.key.startswith("psd.") and definition.key not in active_psd_keys:
                continue
            widget = self.parameter_widgets.get(definition.key)
            if widget is None:
                continue
            if isinstance(widget, QtWidgets.QComboBox):
                value: Any = widget.currentText()
            elif isinstance(widget, QtWidgets.QCheckBox):
                value = widget.isChecked()
            elif isinstance(widget, QtWidgets.QSpinBox):
                value = widget.value()
            else:
                value = widget.value()
            set_config_value(values, definition.key, value)
        bands: list[dict[str, Any]] = []
        for row in range(self.band_table.rowCount()):
            try:
                name = self.band_table.item(row, 0).text().strip()
                low = float(self.band_table.item(row, 1).text())
                high = float(self.band_table.item(row, 2).text())
                if name:
                    bands.append({"name": name, "low_hz": low, "high_hz": high})
            except (AttributeError, TypeError, ValueError):
                continue
        values["bands"] = bands
        values["relative_power"] = {"denominator_low_hz": self.denominator_low.value(), "denominator_high_hz": self.denominator_high.value()}
        rank_map: dict[str, int] = {}
        for row in range(self.rank_mapping_table.rowCount()):
            region_item = self.rank_mapping_table.item(row, 0)
            rank_item = self.rank_mapping_table.item(row, 1)
            if region_item is None or rank_item is None:
                continue
            try:
                rank = int(rank_item.text().strip() or 0)
            except ValueError:
                continue
            if rank > 0:
                rank_map[region_item.text().strip()] = rank
        values.setdefault("connectivity", {})["fixed_rank_by_region"] = rank_map
        return values

    def _snapshot(self) -> dict[str, Any]:
        if self.current_info is None:
            raise ValueError("请先添加并读取至少一个 FIF 文件。")
        self._capture_current_file_selection()
        epochs = self._parse_epochs(self.epoch_edit.text(), self.current_info["n_epochs"])
        pairs = [list(pair) for pair, checkbox in self.pair_checks.items() if checkbox.isChecked()]
        selections_by_file = {
            str(info.get("file_uid") or info.get("path")): state
            for info in self.file_infos
            if (state := self.file_selections.get(self._file_selection_key(info))) is not None
        }
        return {
            "run_id": f"run_{time.strftime('%Y%m%d_%H%M%S')}_{int(time.time() * 1000) % 1000:03d}",
            "input_files": [str(info["path"]) for info in self.file_infos],
            "output_dir": str(Path(self.output_edit.text()).expanduser()),
            "config_path": str(self.config_path),
            "metadata_dir": str(self.metadata_dir),
            "indicators": self._selected_indicators(),
            "selected_channel_names": self._selected_channel_names(),
            "selected_epoch_indices": epochs,
            "selected_region_pairs": pairs,
            "selected_channel_names_by_file": {key: value.get("selected_channel_names", []) for key, value in selections_by_file.items()},
            "selected_epoch_indices_by_file": {key: value.get("selected_epoch_indices", []) for key, value in selections_by_file.items()},
            "selected_region_pairs_by_file": {key: value.get("selected_region_pairs", []) for key, value in selections_by_file.items()},
            "selection_by_file": {key: value.get("selection", {}) for key, value in selections_by_file.items()},
            "file_selections": copy.deepcopy(self.file_selections),
            "channel_mapping": mapping_rows(self.current_info.get("channel_table", pd.DataFrame())),
            "channel_mappings_by_file": {
                str(info.get("path", "")): mapping_rows(info.get("channel_table", pd.DataFrame()))
                for info in self.file_infos
            },
            "mapping_file": str(self.current_mapping_path or ""),
            "selection": {"time_start_s": self.time_start.value(), "time_end_s": self.time_end.value()},
            "values": self._read_parameter_values(),
            "display_settings": {"color_template": str(self.color_template_combo.currentData() or DEFAULT_COLOR_TEMPLATE)},
            "parameter_schema": parameter_schema(),
        }

    def _run(self) -> None:
        if self._running:
            self._log("已有分析任务运行中。")
            return
        try:
            snapshot = self._snapshot()
            if not snapshot["input_files"]:
                raise ValueError("请先添加 FIF 文件。")
            if not snapshot["selected_region_pairs"] and set(snapshot["indicators"]) & {"MIC", "MIM", "wpli", "dpli", "wpli2_debiased"}:
                raise ValueError("至少选择一组连接脑区对。")
            errors, warnings = validate_snapshot(
                snapshot,
                self.current_info["sfreq"],
                round((self.time_end.value() - self.time_start.value()) * self.current_info["sfreq"]),
                self.current_info["n_epochs"],
                self.current_info["channel_table"],
            )
            if errors:
                raise ValueError("；".join(errors))
            if warnings:
                self._log("运行前提示：" + "；".join(warnings))
        except Exception as exc:  # noqa: BLE001 - validation must not crash window
            self._show_message(QtWidgets.QMessageBox.Icon.Warning, "参数或数据选择无效", str(exc))
            return
        self._running = True
        task_id = str(snapshot["run_id"])
        self._active_analysis_task_id = task_id
        self._dirty = False
        self._last_progress_message = ""
        self.run_button.setEnabled(False)
        self.run_button.setText("Running...")
        self.cancel_button.setEnabled(True)
        self.task_label.setText("状态：后台运行中…")
        self.progress.setValue(0)
        self.analysis_thread = QtCore.QThread(self)
        self.analysis_worker = AnalysisWorker(snapshot, self.config_path, self.metadata_dir)
        self.analysis_worker.moveToThread(self.analysis_thread)
        self.analysis_thread.started.connect(self.analysis_worker.run)
        # Use QObject-bound slots with an explicit queued connection.  A plain
        # Python lambda connected to a worker signal is executed in the worker
        # thread by PySide, which allowed Matplotlib figures and Qt widgets to
        # be mutated concurrently with a main-thread canvas draw.  Besides
        # intermittent ``Axes has not been added yet`` errors, that race can
        # terminate the process inside the Qt/Matplotlib native code.
        queued = QtCore.Qt.ConnectionType.QueuedConnection
        self.analysis_worker.progress.connect(self._progress_update, queued)
        self.analysis_worker.result.connect(self._result_ready, queued)
        self.analysis_worker.finished.connect(self._run_finished, queued)
        self.analysis_worker.finished.connect(self.analysis_thread.quit)
        self.analysis_thread.finished.connect(self.analysis_worker.deleteLater)
        self.analysis_thread.finished.connect(self.analysis_thread.deleteLater)
        self.analysis_thread.start()

    def _cancel(self) -> None:
        if self.analysis_worker is not None:
            self.analysis_worker.cancel_event.set()
            self.task_label.setText("状态：正在请求取消；已完成结果会保留…")

    @QtCore.Slot(str, int)
    def _progress_update(self, message: str, percent: int) -> None:
        if self._active_analysis_task_id and self.analysis_worker is not None and self.analysis_worker.task_id != self._active_analysis_task_id:
            return
        self.task_label.setText(f"状态：{message}")
        self.progress.setValue(percent)
        if message != self._last_progress_message:
            self._log(f"进度 {percent}%：{message}")
            self._last_progress_message = message

    @QtCore.Slot(object)
    def _result_ready(self, payload: dict[str, Any]) -> None:
        if payload.get("task_id") and str(payload.get("task_id")) != self._active_analysis_task_id:
            return
        if payload.get("status") == "failed":
            self._log(f"失败：{payload.get('file_id', '')} — {payload.get('error', '')}")
            return
        record = payload.get("record", {})
        # Adding/selecting an item emits currentTextChanged.  Block that signal
        # here because this method performs the one authoritative display
        # refresh immediately below.  Without the blocker, a newly delivered
        # result was plotted twice in succession.
        with QtCore.QSignalBlocker(self.result_combo):
            key = self._store_result_payload(payload, record if isinstance(record, dict) else {})
            index = self.result_combo.findData(key)
            if index >= 0:
                self.result_combo.setCurrentIndex(index)
        self._show_payload(payload, force_new_result=True)
        parameters = record.get("parameters", {}) if isinstance(record, dict) else {}
        call_count = parameters.get("estimation_call_count") if isinstance(parameters, dict) else None
        suffix = f"；谱估计调用={call_count}" if call_count is not None else ""
        self._log(f"完成：{key}；状态={record.get('status', 'completed')}{suffix}")

    @QtCore.Slot(object)
    def _run_finished(self, outcome: dict[str, Any], task_id: str | None = None) -> None:
        outcome_task_id = str(outcome.get("manifest", {}).get("run_id", ""))
        expected_task_id = str(task_id or self._active_analysis_task_id)
        if expected_task_id and outcome_task_id and outcome_task_id != expected_task_id:
            return
        self._running = False
        manifest = outcome.get("manifest", {})
        self.run_button.setEnabled(True)
        self.run_button.setText("Completed" if manifest.get("status") in {"completed", "completed_with_errors"} else "Failed")
        self.cancel_button.setEnabled(False)
        self.progress.setValue(100 if manifest.get("status") in {"completed", "completed_with_errors"} else self.progress.value())
        self.task_label.setText(f"状态：{manifest.get('status', 'unknown')}；结果目录：{outcome.get('run_dir', '')}")
        self._log(
            f"任务结束：{manifest.get('status', 'unknown')}；"
            f"文件={len(manifest.get('files', []))}；"
            f"错误={len(manifest.get('errors', []))}；"
            f"警告={len(manifest.get('warnings', []))}。"
        )
        self.loaded_run = outcome
        self._active_analysis_task_id = ""

    def _show_selected_result(self, key: str) -> None:
        resolved_key = self._current_result_key()
        if resolved_key in self.result_payloads:
            self._show_payload(
                self.result_payloads[resolved_key],
                force_new_result=resolved_key != self._displayed_result_key,
            )

    def _display_color_changed(self, *_args: Any) -> None:
        """Update classification colours without invalidating numeric results."""
        template = str(self.color_template_combo.currentData() or DEFAULT_COLOR_TEMPLATE)
        self.canvas.color_template = template
        self.band_power_view.set_color_template(template)
        self.fooof_view.set_color_template(template)
        key = self._current_result_key()
        payload = self.result_payloads.get(key)
        if payload is not None and str(payload.get("metric", "")) not in {"Band Power", "FOOOF"}:
            self.canvas.show_payload(payload)

    def _show_payload(self, payload: dict[str, Any], *, force_new_result: bool = False) -> None:
        result_key = self._result_key(payload)
        is_new_result = force_new_result or result_key != self._displayed_result_key
        is_band_power = str(payload.get("metric", "")) == "Band Power"
        is_fooof = str(payload.get("metric", "")) == "FOOOF"
        is_connectivity = str(payload.get("metric", "")) in {"Connectivity", "Time Delay"}
        target_view = (
            self.band_power_view
            if is_band_power
            else self.fooof_view
            if is_fooof
            else self.connectivity_view
            if is_connectivity
            else self.general_plot_widget
        )
        self.result_stack.setCurrentWidget(target_view)
        if is_band_power:
            selected_channels = self._selected_channel_names() if self.current_info is not None else None
            selected_regions = [name for name, checkbox in self.region_checks.items() if checkbox.isChecked()] if self.current_info is not None else None
            self.band_power_view.set_payload(payload, selected_channels, selected_regions)
        elif is_fooof:
            selected_channels = self._selected_channel_names() if self.current_info is not None else None
            selected_regions = [name for name, checkbox in self.region_checks.items() if checkbox.isChecked()] if self.current_info is not None else None
            display_bands = self._read_parameter_values().get("bands", []) if self.current_info is not None else self.base_config.get("bands", {})
            self.fooof_view.set_payload(payload, selected_channels, selected_regions, display_bands)
        elif is_connectivity:
            selected_channels = self._selected_channel_names() if self.current_info is not None else None
            selected_regions = [name for name, checkbox in self.region_checks.items() if checkbox.isChecked()] if self.current_info is not None else None
            self.connectivity_view.set_payload(payload, selected_channels, selected_regions)
        else:
            self.canvas.show_payload(payload)
        if is_new_result:
            reset_scroll = getattr(target_view, "reset_plot_scroll", None)
            if callable(reset_scroll):
                reset_scroll()
            elif target_view is self.general_plot_widget:
                self.general_plot_scroll.reset_position()
        tables = payload.get("tables", {})
        table = next((value for value in tables.values() if isinstance(value, pd.DataFrame) and not value.empty), pd.DataFrame())
        self._set_result_table_source(table, reset=is_new_result)
        self._displayed_result_key = result_key

    def _refresh_band_power_filters(self) -> None:
        if self.current_info is None:
            return
        key = self._current_result_key()
        payload = self.result_payloads.get(key)
        if payload and str(payload.get("metric", "")) == "Band Power":
            selected_regions = [name for name, checkbox in self.region_checks.items() if checkbox.isChecked()]
            self.band_power_view.set_filters(self._selected_channel_names(), selected_regions)

    def _refresh_fooof_filters(self) -> None:
        if not hasattr(self, "result_combo"):
            return
        key = self._current_result_key()
        payload = self.result_payloads.get(key)
        if not payload or str(payload.get("metric", "")) != "FOOOF":
            return
        selected_channels = self._selected_channel_names() if self.current_info is not None else None
        selected_regions = [name for name, checkbox in self.region_checks.items() if checkbox.isChecked()] if self.current_info is not None else None
        display_bands = self._read_parameter_values().get("bands", []) if self.current_info is not None else self.base_config.get("bands", {})
        self.fooof_view.set_filters(selected_channels, selected_regions, display_bands)

    def _refresh_connectivity_filters(self) -> None:
        if not hasattr(self, "result_combo"):
            return
        key = self._current_result_key()
        payload = self.result_payloads.get(key)
        if not payload or str(payload.get("metric", "")) not in {"Connectivity", "Time Delay"}:
            return
        selected_channels = self._selected_channel_names() if self.current_info is not None else None
        selected_regions = [name for name, checkbox in self.region_checks.items() if checkbox.isChecked()] if self.current_info is not None else None
        self.connectivity_view.set_filters(selected_channels, selected_regions)

    def _set_result_table_source(self, frame: pd.DataFrame, *, reset: bool) -> None:
        if reset:
            self._collapse_result_table()
        self._result_table_source = frame if isinstance(frame, pd.DataFrame) else pd.DataFrame()
        if not reset and self.table_toggle.isChecked() and not self._result_table_loaded:
            self._populate_result_table()

    def _populate_result_table(self) -> None:
        """Populate visible rows only when the user asks to inspect the table."""

        display = self._result_table_source.head(1000).copy()
        self.table.clear()
        self.table.setRowCount(len(display))
        self.table.setColumnCount(len(display.columns))
        self.table.setHorizontalHeaderLabels([str(column) for column in display.columns])
        for row_index, row in enumerate(display.itertuples(index=False, name=None)):
            for column_index, value in enumerate(row):
                self.table.setItem(row_index, column_index, QtWidgets.QTableWidgetItem("" if pd.isna(value) else str(value)))
        self.table.resizeColumnsToContents()
        self.table.setToolTip(f"显示前 {len(display)} 行；完整数据已保存。")
        self._result_table_loaded = True

    def _show_table(self, frame: pd.DataFrame) -> None:
        """Compatibility wrapper: update the source without eager population."""

        self._set_result_table_source(frame, reset=False)

    def _log(self, message: str) -> None:
        compact = " ".join(str(message).split())
        if not compact:
            return
        if len(compact) > 600:
            compact = compact[:597] + "..."
        self.status_text.appendPlainText(compact)
        if hasattr(self, "result_status_label"):
            summary = compact if len(compact) <= 180 else compact[:177] + "..."
            self.result_status_label.setText(summary)
            self.result_status_label.setToolTip(compact)

    def _toggle_result_table(self, expanded: bool) -> None:
        """Show the result table on demand without reserving collapsed space."""
        if expanded:
            if not self._result_table_loaded:
                self._populate_result_table()
            self.table.setVisible(True)
            self.table.setMinimumHeight(RESULT_TABLE_EXPANDED_HEIGHT)
            self.table.setMaximumHeight(RESULT_TABLE_EXPANDED_HEIGHT)
            self.table_toggle.setText("▼ 收起结果表")
        else:
            self.table.setVisible(False)
            # A hidden table normally contributes no layout height, but clear
            # its explicit expanded constraints as well so a future Qt style
            # or layout pass cannot leave an invisible blank reservation.
            self.table.setMinimumHeight(0)
            self.table.setMaximumHeight(0)
            self.table_toggle.setText("▶ 展开结果表")
        self.result_stack.updateGeometry()

    def _collapse_result_table(self) -> None:
        with QtCore.QSignalBlocker(self.table_toggle):
            self.table_toggle.setChecked(False)
        self.table.setVisible(False)
        self.table.clear()
        self.table.setMinimumHeight(0)
        self.table.setMaximumHeight(0)
        self.table.setRowCount(0)
        self.table.setColumnCount(0)
        self._result_table_source = pd.DataFrame()
        self._result_table_loaded = False
        self.table_toggle.setText("▶ 展开结果表")

    def _toggle_log(self, expanded: bool) -> None:
        """Show detailed logs only on demand so plots keep the available height."""
        self.status_text.setVisible(bool(expanded))
        self.log_toggle.setText("收起详细日志" if expanded else "展开详细日志")
        if expanded:
            self.status_text.verticalScrollBar().setValue(self.status_text.verticalScrollBar().maximum())

    def _toggle_quality(self, expanded: bool) -> None:
        """Expose complete quality details without reserving permanent space."""
        self.quality_alert_text.setVisible(bool(expanded))
        self.quality_toggle.setText("收起质量详情" if expanded else "展开质量详情")
        if expanded:
            self.quality_alert_text.verticalScrollBar().setValue(0)

    def _show_message(self, icon: QtWidgets.QMessageBox.Icon, title: str, message: str) -> None:
        """Display concise errors with the full technical message in a scrollable detail area."""
        text = str(message)
        box = QtWidgets.QMessageBox(icon, title, "操作未完成，请查看详细信息。", parent=self)
        box.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        box.setDetailedText(text)
        box.setSizeGripEnabled(True)
        box.setMinimumWidth(520)
        box.exec()

    def _set_dirty(self, value: bool) -> None:
        self._dirty = bool(value)
        if self._running:
            self.task_label.setText("状态：当前任务使用已冻结快照；修改将用于下一次运行。")
        elif value:
            self.task_label.setText("状态：参数或数据选择已修改，需要重新计算。")

    def _choose_output(self) -> None:
        path = QtWidgets.QFileDialog.getExistingDirectory(self, "选择输出目录", self.output_edit.text())
        if path:
            self.output_edit.setText(path)
            self._set_dirty(True)

    def _save_preset(self) -> None:
        try:
            snapshot = self._snapshot()
        except Exception as exc:  # noqa: BLE001
            self._show_message(QtWidgets.QMessageBox.Icon.Warning, "无法保存预设", str(exc))
            return
        # Presets remember both method pages so switching back restores the
        # user's last Welch and Multitaper values.  Runtime snapshots above
        # still contain only the currently effective PSD branch.
        snapshot["values"] = self._read_parameter_values(active_psd_only=False)
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "保存分析预设", str(PROJECT_ROOT / "configs" / "gui_preset.json"), "JSON (*.json)")
        if path:
            preset = {
                "schema_version": 2,
                "software": {"name": APP_NAME, "version": APP_VERSION},
                **{
                    key: snapshot[key]
                    for key in (
                        "indicators",
                        "selected_channel_names",
                        "selected_epoch_indices",
                        "selected_region_pairs",
                        "selected_channel_names_by_file",
                        "selected_epoch_indices_by_file",
                        "selected_region_pairs_by_file",
                        "selection_by_file",
                        "file_selections",
                        "channel_mapping",
                        "channel_mappings_by_file",
                        "mapping_file",
                        "selection",
                        "values",
                        "display_settings",
                        "parameter_schema",
                    )
                },
            }
            Path(path).write_text(json.dumps(preset, ensure_ascii=False, indent=2), encoding="utf-8")
            self._log(f"已保存预设：{path}")

    def _load_preset(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "载入分析预设", str(PROJECT_ROOT / "configs"), "JSON (*.json)")
        if not path:
            return
        try:
            preset = json.loads(Path(path).read_text(encoding="utf-8"))
            for name, checkbox in self.indicator_checks.items():
                checkbox.setChecked(name in preset.get("indicators", []))
            values = preset.get("values", {})
            display_settings = preset.get("display_settings", {})
            template = str(display_settings.get("color_template", DEFAULT_COLOR_TEMPLATE)) if isinstance(display_settings, dict) else DEFAULT_COLOR_TEMPLATE
            color_index = self.color_template_combo.findData(template)
            if color_index >= 0:
                self.color_template_combo.setCurrentIndex(color_index)
            for definition in PARAMETER_DEFINITIONS:
                widget = self.parameter_widgets.get(definition.key)
                if widget is None:
                    continue
                value = config_value(values, definition.key, None)
                if value is None:
                    continue
                if isinstance(widget, QtWidgets.QComboBox):
                    widget.setCurrentText(str(value))
                elif isinstance(widget, QtWidgets.QCheckBox):
                    widget.setChecked(bool(value))
                elif isinstance(widget, QtWidgets.QSpinBox):
                    widget.setValue(int(value))
                else:
                    widget.setValue(float(value))
            if self.current_info is not None and isinstance(preset.get("channel_mapping"), list) and preset.get("channel_mapping"):
                self._apply_channel_table(apply_mapping(self.current_info["channel_table"], {"channels": preset["channel_mapping"]}), "预设")
            if self.current_info is not None:
                current_key = self._file_selection_key()
                saved_selection = preset.get("file_selections", {}).get(current_key, {}) if isinstance(preset.get("file_selections"), dict) else {}
                if not saved_selection:
                    saved_selection = {
                        "selected_channel_names": preset.get("selected_channel_names", []),
                        "selected_epoch_indices": preset.get("selected_epoch_indices", []),
                        "epoch_text": "all" if not preset.get("selected_epoch_indices") else ",".join(str(value + 1) for value in preset.get("selected_epoch_indices", [])),
                        "selected_region_pairs": preset.get("selected_region_pairs", []),
                        "selection": preset.get("selection", {}),
                    }
                self.file_selections[current_key] = saved_selection
                self._populate_current_file()
            self._update_parameter_tabs()
            self._set_dirty(True)
            self._log(f"已载入预设：{path}")
        except Exception as exc:  # noqa: BLE001
            self._show_message(QtWidgets.QMessageBox.Icon.Warning, "载入预设失败", str(exc))

    def _load_history(self) -> None:
        root = QtWidgets.QFileDialog.getExistingDirectory(self, "选择包含 run_manifest.json 的运行目录", str(self.output_edit.text()))
        if not root:
            return
        try:
            loaded = load_saved_run(root)
            self.result_payloads.clear()
            self.result_records.clear()
            self.result_combo.clear()
            run_root = Path(loaded["run_dir"])
            for file_record in loaded["manifest"].get("files", []):
                file_dir = resolve_manifest_path(run_root, file_record.get("file_dir", ""), "file_dir")
                for record in file_record.get("metrics", []):
                    payload = self._payload_from_saved_record(
                        record,
                        file_record.get("file_id", "file"),
                        file_dir,
                        file_record.get("file_uid", ""),
                        file_record.get("display_name", ""),
                    )
                    if payload:
                        self._store_result_payload(payload, record)
            self.loaded_run = loaded
            self.task_label.setText(f"状态：已载入历史运行 {loaded['manifest'].get('run_id', '')}；不需要原始 FIF 即可查看。")
            manifest = loaded["manifest"]
            self._log(
                f"历史运行已载入：{manifest.get('status', 'unknown')}；"
                f"文件={len(manifest.get('files', []))}；"
                f"错误={len(manifest.get('errors', []))}；"
                f"警告={len(manifest.get('warnings', []))}。"
            )
            if self.result_combo.count():
                self.result_combo.setCurrentIndex(0)
        except Exception as exc:  # noqa: BLE001
            self._show_message(QtWidgets.QMessageBox.Icon.Warning, "载入历史失败", str(exc))

    def _payload_from_saved_record(
        self,
        record: dict[str, Any],
        file_id: str,
        file_dir: Path,
        file_uid: str = "",
        display_name: str = "",
    ) -> dict[str, Any] | None:
        tables: dict[str, pd.DataFrame] = {}
        metric = str(record.get("metric", "Result"))
        metric_folder = {
            "Quality": "quality",
            "PSD": "psd",
            "Band Power": "band_power",
            "FOOOF": "fooof",
            "Connectivity": "connectivity",
            "Time Delay": "time_delay",
        }.get(metric, "")
        for name, filename in record.get("paths", {}).get("tables", {}).items():
            if not isinstance(filename, str):
                continue
            try:
                relative = Path(filename)
                if relative.is_absolute():
                    raise ValueError("absolute path")
                candidates = [
                    resolve_manifest_path(file_dir, Path(metric_folder) / relative, "saved table path"),
                    resolve_manifest_path(file_dir, relative, "saved table path"),
                ] if metric_folder else [resolve_manifest_path(file_dir, relative, "saved table path")]
            except ValueError as exc:
                self._log(f"历史表路径非法，已跳过：{filename}（{exc}）")
                continue
            matches = [candidate for candidate in candidates if candidate.is_file()]
            if len(matches) > 1:
                self._log(f"历史表路径不唯一，已跳过：{filename}")
                continue
            if matches:
                try:
                    tables[name] = pd.read_csv(matches[0])
                except Exception as exc:  # noqa: BLE001
                    self._log(f"历史表读取失败：{matches[0]} — {exc}")
        channel_table_path = file_dir / "channel_table.csv"
        if channel_table_path.is_file():
            try:
                tables["channel_table"] = pd.read_csv(channel_table_path)
            except Exception as exc:  # noqa: BLE001
                self._log(f"历史通道表读取失败：{channel_table_path} — {exc}")
        aliases = {
            "PSD": {"channel": tables.get("psd_channel_summary", pd.DataFrame()), "region": tables.get("psd_region_summary", pd.DataFrame())},
            "Band Power": {"band_power": tables.get("band_power_epoch_channel", pd.DataFrame()), "band_power_summary": tables.get("band_power_summary", pd.DataFrame())},
            "FOOOF": {**tables, "display_bands": record.get("parameters", {}).get("display_bands", {})},
            "Connectivity": tables,
            "Time Delay": tables,
            "Quality": tables,
        }
        return {
            "metric": metric,
            "file_id": file_id,
            "file_uid": file_uid,
            "display_name": display_name or file_id,
            "tables": aliases.get(metric, tables),
            "record": record,
        }

    def _export_figure(self) -> None:
        if self.result_combo.currentText().endswith("| Band Power"):
            self._export_band_figure("comparison")
            return
        if self.result_combo.currentText().endswith("| FOOOF"):
            self._export_fooof("current")
            return
        if self.result_combo.currentText().endswith("| Connectivity") or self.result_combo.currentText().endswith("| Time Delay"):
            self._export_connectivity("spectrum")
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "导出当前图", str(PROJECT_ROOT / "results" / "luna_figure.svg"), "SVG (*.svg);;PNG (*.png);;PDF (*.pdf)")
        if path:
            self.canvas.figure.savefig(path, dpi=200)
            self._log(f"已导出图：{path}")

    def _save_result(self) -> None:
        """Save the current view using the existing per-metric exporters."""
        if not self.result_combo.currentText():
            self._log("当前没有可保存的结果。")
            return
        self._export_figure()

    def _export_band_figure(self, kind: str) -> None:
        names = {"overview": "band_power_overview", "comparison": "band_power_compare", "combined": "band_power_combined"}
        default = PROJECT_ROOT / "results" / DEFAULT_OUTPUT_DIRNAME / f"luna_{names.get(kind, 'band_power')}.svg"
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "导出频带功率图",
            str(default),
            "PNG (*.png);;TIFF (*.tif *.tiff);;SVG (*.svg);;PDF (*.pdf)",
        )
        if path:
            self.band_power_view.save_figure(kind, path)
            csv_path = Path(path).with_suffix(".csv")
            self.band_power_view.save_csv(csv_path)
            self._log(f"已导出频带功率图和数据：{Path(path).name}、{csv_path.name}")

    def _export_fooof(self, kind: str) -> None:
        if self.fooof_view.payload is None:
            return
        if kind == "all":
            directory = QtWidgets.QFileDialog.getExistingDirectory(self, "选择 FOOOF 全部结果输出目录", str(PROJECT_ROOT / "results" / DEFAULT_OUTPUT_DIRNAME))
            if directory:
                figures = self.fooof_view.save_all(directory)
                tables = self.fooof_view.save_tables(Path(directory) / "fooof")
                self._log(f"已导出 FOOOF 全部图表 {len(figures)} 个和数据表 {len(tables)} 个。")
            return
        if kind == "tables":
            path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "导出 FOOOF 数值表前缀", str(PROJECT_ROOT / "results" / DEFAULT_OUTPUT_DIRNAME / "luna_fooof.csv"), "CSV (*.csv)")
            if path:
                tables = self.fooof_view.save_tables(path)
                self._log(f"已导出 FOOOF 数据表 {len(tables)} 个。")
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "导出当前 FOOOF 图",
            str(PROJECT_ROOT / "results" / DEFAULT_OUTPUT_DIRNAME / "luna_fooof_current.svg"),
            "PNG (*.png);;TIFF (*.tif *.tiff);;SVG (*.svg);;PDF (*.pdf)",
        )
        if path:
            self.fooof_view.save_figure("current", path)
            tables = self.fooof_view.save_tables(Path(path).with_suffix(""))
            self._log(f"已导出 FOOOF 图和数据表：{Path(path).name}；表={len(tables)}。")

    def _export_connectivity(self, kind: str) -> None:
        if self.connectivity_view.payload is None:
            return
        if kind == "tables":
            path, _ = QtWidgets.QFileDialog.getSaveFileName(
                self,
                "导出连接指标数值表前缀",
                str(PROJECT_ROOT / "results" / DEFAULT_OUTPUT_DIRNAME / "luna_connectivity.csv"),
                "CSV (*.csv)",
            )
            if path:
                tables = self.connectivity_view.save_tables(path)
                self._log(f"已导出连接数值表 {len(tables)} 个。")
            return
        default_name = f"luna_connectivity_{kind}.svg"
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "导出连接指标图",
            str(PROJECT_ROOT / "results" / DEFAULT_OUTPUT_DIRNAME / default_name),
            "PNG (*.png);;TIFF (*.tif *.tiff);;SVG (*.svg);;PDF (*.pdf)",
        )
        if path:
            self.connectivity_view.save_figure(kind, path)
            self._log(f"已导出连接图：{Path(path).name}。")

    def _open_output(self) -> None:
        path = Path(self.output_edit.text()).expanduser()
        path.mkdir(parents=True, exist_ok=True)
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(path.resolve())))

    def _show_about(self) -> None:
        QtWidgets.QMessageBox.information(
            self,
            f"About {APP_NAME}",
            f"<b>{APP_NAME}</b><br>{APP_FULL_NAME}<br><br>{APP_DESCRIPTION}<br><br>Version {APP_VERSION}<br><br>支持多通道 LFP、频谱、谱参数化、频带功率、功能连接和网络动态分析；不包含 spike sorting 或 single-unit analysis。",
        )

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        if self.analysis_worker is not None:
            self.analysis_worker.cancel_event.set()
        if self.analysis_thread is not None and self.analysis_thread.isRunning():
            self.analysis_thread.requestInterruption()
            if not self.analysis_thread.wait(3000):
                self.task_label.setText("状态：后台任务仍在收尾，请稍后再关闭窗口。")
                event.ignore()
                return
        if self.inspect_thread is not None and self.inspect_thread.isRunning():
            self.inspect_thread.requestInterruption()
            if not self.inspect_thread.wait(3000):
                self.task_label.setText("状态：文件读取仍在收尾，请稍后再关闭窗口。")
                event.ignore()
                return
        event.accept()


def launch(input_files: list[str] | None = None, output_dir: str | None = None) -> int:
    """Start the desktop GUI and return the Qt exit code."""
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setStyle("Fusion")
    window = MainWindow(input_files=input_files, output_dir=output_dir)
    window.show()
    return app.exec()
