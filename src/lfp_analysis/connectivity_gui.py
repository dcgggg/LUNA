"""Qt view for the two primary multivariate/bivariate connectivity plots."""

from __future__ import annotations

from itertools import combinations
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from PySide6 import QtCore, QtWidgets

from .connectivity_plots import (
    _pair_key,
    available_bands,
    available_components,
    available_methods,
    infer_region_order,
    method_label,
    pair_label,
    plot_band_matrices,
    plot_channel_pair_matrices,
    plot_channel_pair_matrix,
    plot_matrix,
    plot_spectrum,
    prepare_connectivity,
)


class _FlowLayout(QtWidgets.QLayout):
    """Wrapping layout for frequency bands without a nested scroll box."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.items: list[QtWidgets.QLayoutItem] = []
        self.setSpacing(8)

    def addItem(self, item: QtWidgets.QLayoutItem) -> None:
        self.items.append(item)

    def count(self) -> int:
        return len(self.items)

    def itemAt(self, index: int) -> QtWidgets.QLayoutItem | None:
        return self.items[index] if 0 <= index < len(self.items) else None

    def takeAt(self, index: int) -> QtWidgets.QLayoutItem | None:
        return self.items.pop(index) if 0 <= index < len(self.items) else None

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._layout(QtCore.QRect(0, 0, width, 0), True)

    def setGeometry(self, rect: QtCore.QRect) -> None:
        super().setGeometry(rect)
        self._layout(rect, False)

    def sizeHint(self) -> QtCore.QSize:
        return self.minimumSize()

    def minimumSize(self) -> QtCore.QSize:
        size = QtCore.QSize(0, 0)
        for item in self.items:
            size = size.expandedTo(item.minimumSize())
        return size

    def _layout(self, rect: QtCore.QRect, test_only: bool) -> int:
        x, y, line_height = rect.x(), rect.y(), 0
        for item in self.items:
            size = item.sizeHint()
            next_x = x + size.width() + (self.spacing() if line_height else 0)
            if next_x - self.spacing() > rect.right() and line_height:
                x, y = rect.x(), y + line_height + self.spacing()
                next_x = x + size.width()
                line_height = 0
            if not test_only:
                item.setGeometry(QtCore.QRect(QtCore.QPoint(x, y), size))
            x = next_x
            line_height = max(line_height, size.height())
        return y + line_height - rect.y()


class _BandCheckGroup(QtWidgets.QWidget):
    changed = QtCore.Signal()

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._layout = _FlowLayout()
        self.setLayout(self._layout)
        self._checks: list[tuple[QtWidgets.QCheckBox, dict[str, Any]]] = []

    def clear(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
        self._checks.clear()
        self.updateGeometry()

    def add_item(self, band: dict[str, Any], checked: bool = True) -> None:
        text = f"{band['name']} [{float(band['low_hz']):g}–{float(band['high_hz']):g} Hz]"
        checkbox = QtWidgets.QCheckBox(text)
        checkbox.setMinimumWidth(checkbox.fontMetrics().horizontalAdvance(text) + 28)
        checkbox.setToolTip(text)
        checkbox.setChecked(checked)
        checkbox.stateChanged.connect(self.changed)
        self._layout.addWidget(checkbox)
        self._checks.append((checkbox, band))

    def count(self) -> int:
        return len(self._checks)

    def checked_data(self) -> list[dict[str, Any]]:
        return [band for checkbox, band in self._checks if checkbox.isChecked()]


class ConnectivityView(QtWidgets.QWidget):
    """Display saved connectivity results without triggering another computation."""

    export_requested = QtCore.Signal(str)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        # A parent font is used by the main window; the fallback is kept for
        # standalone tests and embedded use.
        self.setFont(parent.font() if parent is not None else QtWidgets.QApplication.font())
        self.payload: dict[str, Any] | None = None
        self.selected_regions: set[str] | None = None
        self.selected_channels: set[str] | None = None
        self.prepared: dict[str, Any] = {}
        self._matrix_info: dict[str, Any] = {}
        self._updating = False
        self._focus_pair: tuple[str, str] | None = None
        self._focus_channel_pair: tuple[str, str] | None = None
        self._is_tde = False

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)
        controls = QtWidgets.QGridLayout()
        controls.setHorizontalSpacing(8)
        controls.setVerticalSpacing(6)
        self.metric_combo = QtWidgets.QComboBox()
        self.metric_combo.setToolTip("当前结果中的连接指标；切换只刷新展示，不重新计算。")
        self.pair_list = QtWidgets.QListWidget()
        self.pair_list.setMaximumHeight(76)
        self.band_list = _BandCheckGroup()
        self.band_list.setToolTip("勾选需要同时显示的频段；矩阵将按两列网格展示。")
        self.component_combo = QtWidgets.QComboBox()
        self.scale_combo = QtWidgets.QComboBox()
        self.scale_combo.addItem("线性", "linear")
        self.scale_combo.addItem("对数（仅正值）", "log")
        self.matrix_level_combo = QtWidgets.QComboBox()
        self.matrix_level_combo.addItem("脑区汇总矩阵", "region")
        self.matrix_level_combo.addItem("当前脑区对的通道对矩阵", "channel_pair")
        self.swap_matrix_check = QtWidgets.QCheckBox("交换 A/B")
        self.font_spin = QtWidgets.QSpinBox()
        self.font_spin.setRange(7, 18)
        self.font_spin.setValue(9)
        self.component_label = QtWidgets.QLabel("MIC 成分")
        self.band_label = QtWidgets.QLabel("Frequency bands display")
        fields = (
            ("Indicator", self.metric_combo),
            ("坐标尺度", self.scale_combo),
            ("矩阵层级", self.matrix_level_combo),
            ("字号", self.font_spin),
            ("MIC 成分", self.component_combo),
            ("", QtWidgets.QWidget()),
        )
        for index, (label, widget) in enumerate(fields):
            if not label:
                continue
            row = index // 4
            column = (index % 4) * 2
            label_widget = self.component_label if label == "MIC 成分" else QtWidgets.QLabel(label)
            controls.addWidget(label_widget, row, column)
            controls.addWidget(widget, row, column + 1)
        controls.addWidget(self.swap_matrix_check, 1, 2, 1, 2)
        controls.addWidget(self.band_label, 2, 0)
        controls.addWidget(self.band_list, 2, 1, 1, 7)
        controls.addWidget(QtWidgets.QLabel("脑区对（可多选）"), 3, 0)
        controls.addWidget(self.pair_list, 3, 1, 1, 7)
        root.addLayout(controls)

        # Keep a small compatibility alias for callers that used the former
        # single-band combo; new code always reads the checked band list.
        self.band_combo = self.band_list
        self.swap_matrix_check.setToolTip("仅影响有向 dPLI 或通道对矩阵的显示顺序。")

        button_row = QtWidgets.QHBoxLayout()
        for text, kind in (("导出当前频谱", "spectrum"), ("导出当前矩阵", "matrix"), ("导出组合图", "combined"), ("导出数值表", "tables")):
            button = QtWidgets.QPushButton(text)
            button.setMinimumHeight(28)
            button.clicked.connect(lambda _checked=False, value=kind: self.export_requested.emit(value))
            button_row.addWidget(button)
        button_row.addStretch(1)
        root.addLayout(button_row)

        self.status_label = QtWidgets.QLabel("连接结果尚未载入")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)
        plot_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        self.spectrum_figure, self.spectrum_canvas = self._new_canvas()
        self.matrix_figure, self.matrix_canvas = self._new_canvas()
        spectrum_panel = QtWidgets.QWidget()
        spectrum_layout = QtWidgets.QVBoxLayout(spectrum_panel)
        spectrum_layout.setContentsMargins(0, 0, 0, 0)
        spectrum_toolbar = NavigationToolbar2QT(self.spectrum_canvas, self)
        spectrum_toolbar.setMaximumHeight(34)
        spectrum_layout.addWidget(spectrum_toolbar)
        spectrum_layout.addWidget(self.spectrum_canvas)
        matrix_panel = QtWidgets.QWidget()
        matrix_layout = QtWidgets.QVBoxLayout(matrix_panel)
        matrix_layout.setContentsMargins(0, 0, 0, 0)
        matrix_toolbar = NavigationToolbar2QT(self.matrix_canvas, self)
        matrix_toolbar.setMaximumHeight(34)
        matrix_layout.addWidget(matrix_toolbar)
        matrix_layout.addWidget(self.matrix_canvas)
        self.matrix_scroll = QtWidgets.QScrollArea()
        self.matrix_scroll.setWidgetResizable(True)
        self.matrix_scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.matrix_scroll.setWidget(matrix_panel)
        plot_splitter.addWidget(spectrum_panel)
        plot_splitter.addWidget(self.matrix_scroll)
        plot_splitter.setChildrenCollapsible(False)
        plot_splitter.setHandleWidth(6)
        plot_splitter.setStretchFactor(0, 1)
        plot_splitter.setStretchFactor(1, 1)
        plot_splitter.setSizes([460, 380])
        root.addWidget(plot_splitter, stretch=1)

        self.detail_toggle = QtWidgets.QPushButton("展开 MIC patterns / rank 诊断")
        self.detail_toggle.setCheckable(True)
        self.detail_toggle.setChecked(False)
        self.detail_toggle.toggled.connect(self._details_toggled)
        root.addWidget(self.detail_toggle)
        self.detail_panel = QtWidgets.QGroupBox("按需详情：patterns 不是源定位或通道生物学贡献率")
        detail_layout = QtWidgets.QVBoxLayout(self.detail_panel)
        detail_controls = QtWidgets.QGridLayout()
        self.pattern_pair_combo = QtWidgets.QComboBox()
        self.pattern_component_combo = QtWidgets.QComboBox()
        self.pattern_frequency_combo = QtWidgets.QComboBox()
        self.pattern_mode_combo = QtWidgets.QComboBox()
        self.pattern_mode_combo.addItem("原始有符号 pattern", "raw")
        self.pattern_mode_combo.addItem("绝对 pattern", "absolute")
        detail_controls.addWidget(QtWidgets.QLabel("脑区对"), 0, 0)
        detail_controls.addWidget(self.pattern_pair_combo, 0, 1)
        detail_controls.addWidget(QtWidgets.QLabel("MIC 成分"), 0, 2)
        detail_controls.addWidget(self.pattern_component_combo, 0, 3)
        detail_controls.addWidget(QtWidgets.QLabel("频率"), 0, 4)
        detail_controls.addWidget(self.pattern_frequency_combo, 0, 5)
        detail_controls.addWidget(QtWidgets.QLabel("显示"), 0, 6)
        detail_controls.addWidget(self.pattern_mode_combo, 0, 7)
        detail_layout.addLayout(detail_controls)
        detail_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        self.pattern_figure, self.pattern_canvas = self._new_canvas()
        pattern_panel = QtWidgets.QWidget()
        pattern_layout = QtWidgets.QVBoxLayout(pattern_panel)
        pattern_layout.setContentsMargins(0, 0, 0, 0)
        pattern_toolbar = NavigationToolbar2QT(self.pattern_canvas, self)
        pattern_toolbar.setMaximumHeight(34)
        pattern_layout.addWidget(pattern_toolbar)
        pattern_layout.addWidget(self.pattern_canvas)
        rank_panel = QtWidgets.QWidget()
        rank_layout = QtWidgets.QVBoxLayout(rank_panel)
        rank_layout.setContentsMargins(0, 0, 0, 0)
        rank_layout.addWidget(QtWidgets.QLabel("有效 rank / 通道冗余诊断"))
        self.rank_table = QtWidgets.QTableWidget()
        rank_layout.addWidget(self.rank_table)
        detail_splitter.addWidget(pattern_panel)
        detail_splitter.addWidget(rank_panel)
        detail_splitter.setSizes([560, 380])
        detail_layout.addWidget(detail_splitter, stretch=1)
        root.addWidget(self.detail_panel, stretch=1)
        self.detail_panel.setVisible(False)

        self.metric_combo.currentIndexChanged.connect(self._controls_changed)
        self.band_list.changed.connect(self._controls_changed)
        self.component_combo.currentIndexChanged.connect(self._controls_changed)
        self.scale_combo.currentIndexChanged.connect(self._controls_changed)
        self.matrix_level_combo.currentIndexChanged.connect(self._controls_changed)
        self.swap_matrix_check.stateChanged.connect(self._controls_changed)
        self.font_spin.valueChanged.connect(self._controls_changed)
        self.pair_list.itemChanged.connect(self._controls_changed)
        self.pattern_pair_combo.currentIndexChanged.connect(self._controls_changed)
        self.pattern_component_combo.currentIndexChanged.connect(self._controls_changed)
        self.pattern_frequency_combo.currentIndexChanged.connect(self._controls_changed)
        self.pattern_mode_combo.currentIndexChanged.connect(self._controls_changed)
        self.matrix_canvas.mpl_connect("button_press_event", self._matrix_clicked)

    @staticmethod
    def _new_canvas() -> tuple[Figure, FigureCanvasQTAgg]:
        figure = Figure(figsize=(9, 4), tight_layout=True)
        return figure, FigureCanvasQTAgg(figure)

    def set_payload(
        self,
        payload: dict[str, Any],
        selected_channels: list[str] | None = None,
        selected_regions: list[str] | None = None,
    ) -> None:
        self.payload = payload
        self.selected_channels = None if selected_channels is None else set(map(str, selected_channels))
        self.selected_regions = None if selected_regions is None else set(map(str, selected_regions))
        self._focus_pair = None
        self._focus_channel_pair = None
        self._populate_controls()
        self._refresh()

    def set_filters(self, selected_channels: list[str] | None, selected_regions: list[str] | None) -> None:
        if self.payload is None:
            return
        self.selected_channels = None if selected_channels is None else set(map(str, selected_channels))
        self.selected_regions = None if selected_regions is None else set(map(str, selected_regions))
        self._focus_pair = None
        self._focus_channel_pair = None
        self._populate_controls()
        self._refresh()

    def _tables(self) -> dict[str, Any]:
        return self.payload.get("tables", {}) if self.payload else {}

    def _current_method(self) -> str:
        if self._is_tde:
            return "tde"
        return str(self.metric_combo.currentData() or "mic").lower()

    def _populate_controls(self) -> None:
        if self.payload is None:
            return
        self._is_tde = str(self.payload.get("metric", "")) == "Time Delay"
        if self._is_tde:
            self._populate_tde_controls()
            return
        self.matrix_level_combo.setVisible(True)
        self.swap_matrix_check.setVisible(True)
        tables = self._tables()
        methods = available_methods(tables)
        old_method = self._current_method()
        old_band_names = self._selected_band_names()
        self._updating = True
        try:
            self.metric_combo.clear()
            for method in methods:
                self.metric_combo.addItem(method_label(method), method)
            index = self.metric_combo.findData(old_method)
            self.metric_combo.setCurrentIndex(max(index, 0))
            self.component_combo.clear()
            for component in available_components(tables):
                self.component_combo.addItem(f"第 {component} 成分", component)
            is_mic = self._current_method() == "mic"
            self.component_combo.setEnabled(is_mic)
            self.component_label.setVisible(is_mic)
            self.component_combo.setVisible(is_mic)
            self.band_list.clear()
            for band in available_bands(tables):
                self.band_list.add_item(band, checked=not old_band_names or str(band["name"]) in old_band_names)
            self.pair_list.clear()
            frame = tables.get("region_summary", pd.DataFrame())
            display_regions = infer_region_order(tables)
            pairs: list[tuple[str, str]] = []
            if isinstance(frame, pd.DataFrame) and not frame.empty:
                method = self._current_method()
                rows = frame.loc[frame["method"].astype(str).str.lower().eq(method)]
                for row in rows[["region_a", "region_b"]].drop_duplicates().itertuples(index=False):
                    raw_pair = (str(row.region_a), str(row.region_b))
                    pair = next((candidate for candidate in combinations(display_regions, 2) if set(candidate) == set(raw_pair)), raw_pair)
                    if self.selected_regions and not set(pair).issubset(self.selected_regions):
                        continue
                    if pair not in pairs:
                        pairs.append(pair)
            order_index = {name: index for index, name in enumerate(display_regions)}
            pairs.sort(key=lambda value: (order_index.get(value[0], 999), order_index.get(value[1], 999)))
            for region_a, region_b in pairs:
                item = QtWidgets.QListWidgetItem(pair_label(region_a, region_b))
                item.setData(QtCore.Qt.ItemDataRole.UserRole, (region_a, region_b))
                item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(QtCore.Qt.CheckState.Checked)
                self.pair_list.addItem(item)
            self._update_matrix_level_options()
            self._populate_pattern_controls()
        finally:
            self._updating = False

    def _populate_tde_controls(self) -> None:
        """Use the same viewer shell for TDE without exposing MIC/MIM controls."""
        tables = self._tables()
        region_spectrum = tables.get("region_spectrum", pd.DataFrame())
        band_summary = tables.get("band_summary", pd.DataFrame())
        self._updating = True
        try:
            self.metric_combo.clear()
            self.metric_combo.addItem("TDE（时间延迟）", "tde")
            self.component_label.setVisible(False)
            self.component_combo.setVisible(False)
            self.matrix_level_combo.setVisible(False)
            self.swap_matrix_check.setVisible(False)
            self.band_list.clear()
            bands = []
            source = band_summary if isinstance(band_summary, pd.DataFrame) and not band_summary.empty else region_spectrum
            if isinstance(source, pd.DataFrame) and not source.empty and "frequency_band" in source.columns:
                for row in source[["frequency_band", "band_low_hz", "band_high_hz"]].drop_duplicates().sort_values(["band_low_hz", "band_high_hz"]).itertuples(index=False):
                    bands.append({"name": str(row.frequency_band), "low_hz": float(row.band_low_hz), "high_hz": float(row.band_high_hz)})
            for band in bands:
                self.band_list.add_item(band, checked=True)
            self.pair_list.clear()
            if isinstance(region_spectrum, pd.DataFrame) and not region_spectrum.empty and {"region_a", "region_b"}.issubset(region_spectrum.columns):
                pairs = region_spectrum[["region_a", "region_b"]].drop_duplicates().itertuples(index=False)
                for row in pairs:
                    pair = (str(row.region_a), str(row.region_b))
                    if self.selected_regions and not set(pair).issubset(self.selected_regions):
                        continue
                    item = QtWidgets.QListWidgetItem(pair_label(*pair))
                    item.setData(QtCore.Qt.ItemDataRole.UserRole, pair)
                    item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
                    item.setCheckState(QtCore.Qt.CheckState.Checked)
                    self.pair_list.addItem(item)
            self._populate_pattern_controls()
        finally:
            self._updating = False

    @staticmethod
    def _tde_bool_column(frame: pd.DataFrame, column: str = "antisymmetrized") -> pd.Series:
        """Parse the saved TDE boolean column without treating missing as True."""
        if column not in frame:
            return pd.Series(False, index=frame.index, dtype=bool)
        values = frame[column]
        if pd.api.types.is_bool_dtype(values):
            return values.fillna(False).astype(bool)
        return values.astype(str).str.strip().str.lower().isin({"true", "1", "yes", "on"})

    def _tde_primary_mode(self, frame: pd.DataFrame) -> bool:
        """Prefer the antisymmetrised curve when both TDE modes were saved."""
        if not isinstance(frame, pd.DataFrame) or frame.empty or "antisymmetrized" not in frame:
            return True
        modes = self._tde_bool_column(frame).unique().tolist()
        return True if True in modes else bool(modes[0]) if modes else True

    def _refresh_tde(self) -> None:
        """Render TDE delay curves and a band-level region comparison.

        TDE is intentionally kept in the same result shell, but it does not
        use MIC/MIM matrices or component selection.  The saved region-level
        tables are filtered only; no delay estimate is recomputed here.
        """
        tables = self._tables()
        spectrum = tables.get("region_spectrum", pd.DataFrame())
        band_summary = tables.get("band_summary", pd.DataFrame())
        selected_pairs = self._selected_pairs()
        selected_bands = self._selected_bands()
        selected_names = {str(band.get("name", "")) for band in selected_bands}
        pair_keys = {_pair_key(*pair) for pair in selected_pairs}
        if selected_bands and isinstance(spectrum, pd.DataFrame) and not spectrum.empty:
            spec = spectrum.copy()
            if "frequency_band" in spec:
                spec = spec.loc[spec["frequency_band"].astype(str).isin(selected_names)]
            if pair_keys and {"region_a", "region_b"}.issubset(spec.columns):
                spec = spec.loc[[ _pair_key(a, b) in pair_keys for a, b in zip(spec["region_a"], spec["region_b"], strict=False)]]
            primary = self._tde_primary_mode(spec if not spec.empty else spectrum)
            if "antisymmetrized" in spec:
                spec = spec.loc[self._tde_bool_column(spec).eq(primary)]
        else:
            spec = pd.DataFrame()
            primary = True

        self.spectrum_figure.clear()
        spectrum_axis = self.spectrum_figure.add_subplot(111)
        if isinstance(spec, pd.DataFrame) and not spec.empty and {"delay_ms", "estimate_strength"}.issubset(spec.columns):
            group_columns = [column for column in ("region_a", "region_b", "frequency_band") if column in spec.columns]
            for key, group in spec.groupby(group_columns, sort=False, dropna=False):
                key_values = (key,) if not isinstance(key, tuple) else key
                label = "–".join(map(str, key_values[:2]))
                if len(key_values) > 2:
                    label += f" | {key_values[2]}"
                group = group.sort_values("delay_ms")
                spectrum_axis.plot(
                    pd.to_numeric(group["delay_ms"], errors="coerce"),
                    pd.to_numeric(group["estimate_strength"], errors="coerce"),
                    linewidth=1.15,
                    label=label,
                )
            spectrum_axis.axvline(0.0, color="#777777", linewidth=0.7, linestyle=":")
            spectrum_axis.set_xlabel("Delay（ms；正值 = seed 领先 target）")
            spectrum_axis.set_ylabel("TDE estimate strength")
            spectrum_axis.set_title(f"{self.payload.get('file_id', '')} | TDE delay curve | {'antisymmetrized' if primary else 'raw'}")
            spectrum_axis.grid(True, color="#dddddd", linewidth=0.45)
            spectrum_axis.legend(fontsize=8, frameon=False, ncol=2)
        else:
            _message = "当前筛选没有可显示的 TDE delay curve"
            spectrum_axis.text(0.5, 0.5, _message, ha="center", va="center", transform=spectrum_axis.transAxes)
            spectrum_axis.set_axis_off()
        self.spectrum_figure.subplots_adjust(left=0.10, right=0.97, bottom=0.16, top=0.88)
        self.spectrum_canvas.draw_idle()

        self.matrix_figure.clear()
        compare_axis = self.matrix_figure.add_subplot(111)
        if selected_bands and isinstance(band_summary, pd.DataFrame) and not band_summary.empty:
            summary = band_summary.copy()
            if "frequency_band" in summary:
                summary = summary.loc[summary["frequency_band"].astype(str).isin(selected_names)]
            if pair_keys and {"region_a", "region_b"}.issubset(summary.columns):
                summary = summary.loc[[ _pair_key(a, b) in pair_keys for a, b in zip(summary["region_a"], summary["region_b"], strict=False)]]
            if "antisymmetrized" in summary:
                summary = summary.loc[self._tde_bool_column(summary).eq(primary)]
            delay_column = "region_peak_delay_ms" if "region_peak_delay_ms" in summary else "peak_delay_ms"
            if not summary.empty and delay_column in summary:
                x_labels = []
                values = []
                for row in summary.itertuples(index=False):
                    pair = f"{getattr(row, 'region_a', '')}–{getattr(row, 'region_b', '')}"
                    band = str(getattr(row, "frequency_band", ""))
                    x_labels.append(f"{pair}\n{band}" if band else pair)
                    values.append(pd.to_numeric(getattr(row, delay_column, np.nan), errors="coerce"))
                x = np.arange(len(values))
                compare_axis.scatter(x, values, color="#386cb0", s=34, zorder=3)
                compare_axis.axhline(0.0, color="#777777", linewidth=0.7, linestyle=":")
                compare_axis.set_xticks(x, x_labels, rotation=45, ha="right")
                compare_axis.set_ylabel("Peak delay（ms）")
                compare_axis.set_title(f"{self.payload.get('file_id', '')} | TDE brain-region comparison | {'antisymmetrized' if primary else 'raw'}")
                compare_axis.grid(True, axis="y", color="#dddddd", linewidth=0.45)
            else:
                compare_axis.text(0.5, 0.5, "当前筛选没有可显示的 TDE brain-region comparison", ha="center", va="center", transform=compare_axis.transAxes)
                compare_axis.set_axis_off()
        else:
            compare_axis.text(0.5, 0.5, "当前结果没有 TDE band summary", ha="center", va="center", transform=compare_axis.transAxes)
            compare_axis.set_axis_off()
        self.matrix_figure.subplots_adjust(left=0.10, right=0.97, bottom=0.30, top=0.86)
        self.matrix_canvas.setMinimumHeight(320)
        self.matrix_canvas.draw_idle()
        self._matrix_info = {"level": "tde", "axis_lookup": {}}
        self._refresh_details()
        n_rows = len(spec) if isinstance(spec, pd.DataFrame) else 0
        self.status_label.setText(
            f"TDE：选中脑区对={len(selected_pairs)}；频段={len(selected_bands)}；"
            f"曲线行数={n_rows}；显示={'antisymmetrized' if primary else 'raw'}；仅筛选已有结果。"
        )

    def _populate_pattern_controls(self) -> None:
        patterns = self._tables().get("patterns", pd.DataFrame())
        self._updating = True
        try:
            self.pattern_pair_combo.clear()
            self.pattern_component_combo.clear()
            self.pattern_frequency_combo.clear()
            if not isinstance(patterns, pd.DataFrame) or patterns.empty:
                self.detail_toggle.setEnabled(False)
                self.detail_toggle.setVisible(False)
                self.detail_panel.setVisible(False)
                self.detail_toggle.setText("MIC patterns / rank 诊断（当前后端未提供 patterns）")
                return
            is_mic = self._current_method() == "mic"
            self.detail_toggle.setEnabled(is_mic)
            self.detail_toggle.setVisible(is_mic)
            if not is_mic:
                self.detail_panel.setVisible(False)
            self.detail_toggle.setText("收起 MIC patterns / rank 诊断" if self.detail_toggle.isChecked() else "展开 MIC patterns / rank 诊断")
            pairs = patterns[["region_a", "region_b"]].drop_duplicates().itertuples(index=False)
            for row in pairs:
                self.pattern_pair_combo.addItem(pair_label(str(row.region_a), str(row.region_b)), (str(row.region_a), str(row.region_b)))
            components = pd.to_numeric(patterns.get("component_index", pd.Series(dtype=float)), errors="coerce").dropna().astype(int).unique()
            for component in sorted(components):
                self.pattern_component_combo.addItem(f"第 {component} 成分", int(component))
            frequencies = pd.to_numeric(patterns.get("frequency_hz", pd.Series(dtype=float)), errors="coerce").dropna().unique()
            for frequency in sorted(frequencies):
                self.pattern_frequency_combo.addItem(f"{float(frequency):g} Hz", float(frequency))
            self.pattern_pair_combo.setEnabled(self._current_method() == "mic")
            self.pattern_component_combo.setEnabled(self._current_method() == "mic")
            self.pattern_frequency_combo.setEnabled(self._current_method() == "mic")
            self.pattern_mode_combo.setEnabled(self._current_method() == "mic")
        finally:
            self._updating = False

    def _details_toggled(self, checked: bool) -> None:
        self.detail_panel.setVisible(bool(checked))
        self.detail_toggle.setText("收起 MIC patterns / rank 诊断" if checked else "展开 MIC patterns / rank 诊断")
        self._refresh_details()

    def _refresh_details(self) -> None:
        if not self.detail_toggle.isChecked() or self.payload is None:
            return
        patterns = self._tables().get("patterns", pd.DataFrame())
        self.pattern_figure.clear()
        axis = self.pattern_figure.add_subplot(111)
        axis.set_axis_on()
        method = self._current_method()
        if method != "mic":
            axis.text(0.5, 0.5, f"{method.upper()} 不提供 MIC patterns", ha="center", va="center", transform=axis.transAxes)
            axis.set_axis_off()
        elif not isinstance(patterns, pd.DataFrame) or patterns.empty:
            axis.text(0.5, 0.5, "该运行没有后端 MIC patterns", ha="center", va="center", transform=axis.transAxes)
            axis.set_axis_off()
        else:
            pair = self.pattern_pair_combo.currentData()
            component = int(self.pattern_component_combo.currentData() or 1)
            requested_frequency = float(self.pattern_frequency_combo.currentData() or 0.0)
            selected = patterns.loc[
                patterns["method"].astype(str).str.lower().eq("mic")
                & pd.to_numeric(patterns["component_index"], errors="coerce").eq(component)
            ].copy()
            if pair:
                selected = selected.loc[(selected["region_a"].astype(str) == str(pair[0])) & (selected["region_b"].astype(str) == str(pair[1]))]
            if not selected.empty and requested_frequency:
                actual_frequency = float(pd.to_numeric(selected["frequency_hz"], errors="coerce").iloc[(pd.to_numeric(selected["frequency_hz"], errors="coerce") - requested_frequency).abs().argmin()])
                selected = selected.loc[pd.to_numeric(selected["frequency_hz"], errors="coerce").eq(actual_frequency)]
            if selected.empty:
                axis.text(0.5, 0.5, "当前 patterns 筛选没有结果", ha="center", va="center", transform=axis.transAxes)
                axis.set_axis_off()
            else:
                selected["plot_value"] = pd.to_numeric(selected["pattern_value"], errors="coerce")
                if self.pattern_mode_combo.currentData() == "absolute":
                    selected["plot_value"] = selected["plot_value"].abs()
                selected = selected.sort_values(["pattern_role", "array_index"])
                x = np.arange(len(selected))
                colors = ["#386cb0" if str(role) == "seed" else "#f58231" for role in selected["pattern_role"]]
                axis.bar(x, selected["plot_value"], color=colors, alpha=0.85)
                axis.axhline(0.0, color="#888888", linewidth=0.7)
                axis.set_xticks(x, selected["channel_name"].astype(str), rotation=45, ha="right")
                frequency = float(selected["frequency_hz"].iloc[0])
                axis.set_ylabel("|pattern|" if self.pattern_mode_combo.currentData() == "absolute" else "pattern (raw signed)")
                axis.set_title(f"{pair_label(*pair) if pair else ''} | MIC component {component} | nearest {frequency:g} Hz")
                axis.grid(True, axis="y", color="#dddddd", linewidth=0.45)
        self.pattern_figure.subplots_adjust(bottom=0.35, left=0.12, right=0.96, top=0.84)
        self.pattern_canvas.draw_idle()
        rank = self._tables().get("rank_summary", pd.DataFrame())
        self._set_rank_table(rank)

    def _set_rank_table(self, frame: Any) -> None:
        display = frame.head(1000).copy() if isinstance(frame, pd.DataFrame) else pd.DataFrame()
        self.rank_table.clear()
        self.rank_table.setRowCount(len(display))
        self.rank_table.setColumnCount(len(display.columns))
        self.rank_table.setHorizontalHeaderLabels([str(column) for column in display.columns])
        for row_index, row in enumerate(display.itertuples(index=False, name=None)):
            for column_index, value in enumerate(row):
                self.rank_table.setItem(row_index, column_index, QtWidgets.QTableWidgetItem("" if pd.isna(value) else str(value)))
        self.rank_table.resizeColumnsToContents()

    def _selected_pairs(self) -> list[tuple[str, str]]:
        pairs: list[tuple[str, str]] = []
        for index in range(self.pair_list.count()):
            item = self.pair_list.item(index)
            if item.checkState() == QtCore.Qt.CheckState.Checked:
                value = item.data(QtCore.Qt.ItemDataRole.UserRole)
                if value:
                    pairs.append(tuple(value))
        return pairs

    def _selected_band(self) -> dict[str, Any] | None:
        bands = self._selected_bands()
        return bands[0] if bands else None

    def _selected_bands(self) -> list[dict[str, Any]]:
        return self.band_list.checked_data()

    def _selected_band_names(self) -> set[str]:
        return {str(band.get("name", "")) for band in self._selected_bands()}

    def _update_matrix_level_options(self) -> None:
        method = self._current_method()
        old = self.matrix_level_combo.currentData()
        self.matrix_level_combo.blockSignals(True)
        try:
            self.matrix_level_combo.clear()
            self.matrix_level_combo.addItem("方向矩阵（脑区）" if method == "dpli" else "脑区汇总矩阵", "region")
            if method in {"wpli", "dpli", "wpli2_debiased", "imcoh", "coh"}:
                self.matrix_level_combo.addItem("通道对矩阵", "channel_pair")
            index = self.matrix_level_combo.findData(old)
            self.matrix_level_combo.setCurrentIndex(max(0, index))
        finally:
            self.matrix_level_combo.blockSignals(False)

    def _controls_changed(self, *_args: Any) -> None:
        if self._updating:
            return
        if self.sender() is self.metric_combo:
            self._populate_controls()
        self._focus_pair = None
        self._focus_channel_pair = None
        self._refresh()

    def _refresh(self) -> None:
        if self.payload is None:
            return
        if self._is_tde:
            self._refresh_tde()
            return
        method = self._current_method()
        components = available_components(self._tables())
        component = int(self.component_combo.currentData() or (components[0] if components else 1))
        pairs = self._selected_pairs()
        plot_pairs = [self._focus_pair] if self._focus_pair is not None else pairs
        self.prepared = prepare_connectivity(
            self._tables(),
            method,
            component,
            plot_pairs,
            exact_direction=self._focus_pair is not None,
            display_region_order=infer_region_order(self._tables()),
        )
        if self._focus_channel_pair is not None and method in {"wpli", "dpli", "wpli2_debiased", "imcoh", "coh"}:
            seed_channel, target_channel = self._focus_channel_pair
            channel_spectrum = self.prepared.get("channel_spectrum", pd.DataFrame())
            if isinstance(channel_spectrum, pd.DataFrame):
                focused = channel_spectrum.loc[
                    (channel_spectrum["seed_channel"].astype(str) == seed_channel)
                    & (channel_spectrum["target_channel"].astype(str) == target_channel)
                ].copy()
                if not focused.empty:
                    focused["pair_label"] = f"{seed_channel}–{target_channel}"
                    focused["display_pair_label"] = f"{seed_channel}→{target_channel}" if method == "dpli" else focused["pair_label"]
                    self.prepared["spectrum"] = focused
        selected_bands = self._selected_bands()
        font_size = int(self.font_spin.value())
        title_prefix = f"{self.payload.get('file_id', '')} | "
        plot_spectrum(self.spectrum_figure.axes[0] if self.spectrum_figure.axes else self.spectrum_figure.add_subplot(111), self.prepared, selected_bands, self.scale_combo.currentData(), title_prefix, font_size)
        self.spectrum_figure.subplots_adjust(top=0.82, bottom=0.22, left=0.10, right=0.96)
        self.spectrum_canvas.draw_idle()
        matrix_prepared = prepare_connectivity(
            self._tables(),
            method,
            component,
            pairs,
            display_region_order=infer_region_order(self._tables()),
        )
        if self.matrix_level_combo.currentData() == "channel_pair":
            matrix_pair = self._focus_pair or (pairs[0] if pairs else None)
            self._matrix_info = plot_channel_pair_matrices(
                self.matrix_figure,
                matrix_prepared,
                selected_bands,
                matrix_pair,
                bool(self.swap_matrix_check.isChecked()),
                font_size,
            )
        else:
            self._matrix_info = plot_band_matrices(self.matrix_figure, matrix_prepared, selected_bands, self.scale_combo.currentData(), title_prefix, font_size)
        matrix_rows = max(1, int(np.ceil(len(selected_bands) / 2)))
        self.matrix_canvas.setMinimumHeight(max(320, matrix_rows * 220 + 90))
        self.matrix_canvas.draw_idle()
        self._refresh_details()
        spectrum = self.prepared.get("spectrum", pd.DataFrame())
        n_epochs = int(pd.to_numeric(spectrum.get("n_epochs", pd.Series(dtype=float)), errors="coerce").dropna().max()) if isinstance(spectrum, pd.DataFrame) and not spectrum.empty and "n_epochs" in spectrum else 0
        focus_text = f"；当前点击={pair_label(*self._focus_pair)}" if self._focus_pair else ""
        if self._focus_channel_pair:
            focus_text += f"；通道对={self._focus_channel_pair[0]}→{self._focus_channel_pair[1]}"
        if not available_methods(self._tables()):
            self.status_label.setText("当前连接结果中没有可显示的连接指标；请重新运行并勾选 MIC、MIM、wPLI 或 dPLI。")
        else:
            self.status_label.setText(
                f"{method.upper()}：选中脑区对={len(pairs)}；用于频谱显示={len(plot_pairs)}；有效 epoch={n_epochs}；"
                f"频段汇总只在已计算频率覆盖范围内进行；{method_label(method)}；dPLI 正反方向不镜像{focus_text}。"
            )

    def _matrix_clicked(self, event: Any) -> None:
        if event.inaxes is None or event.xdata is None or event.ydata is None:
            return
        i, j = round(float(event.ydata)), round(float(event.xdata))
        panel_info = self._matrix_info.get("axis_lookup", {}).get(id(event.inaxes), {})
        level = self._matrix_info.get("level")
        if level in {"channel_pair", "channel_pair_multi"}:
            lookup = panel_info.get("channel_pair_lookup", self._matrix_info.get("channel_pair_lookup", {}))
            channel_pair = lookup.get((i, j))
            if channel_pair is None:
                return
            self._focus_channel_pair = tuple(channel_pair)
            matrix_pair = self._matrix_info.get("region_pair") or panel_info.get("region_pair")
            if matrix_pair:
                method = self._current_method()
                self._focus_pair = tuple(matrix_pair[::-1] if method == "dpli" and self._matrix_info.get("swap") else matrix_pair)
        else:
            lookup = panel_info.get("pair_lookup", self._matrix_info.get("pair_lookup", {}))
            pair = lookup.get((i, j))
            if pair is None:
                return
            self._focus_pair = tuple(pair)
            self._focus_channel_pair = None
        self._refresh()

    def save_figure(self, kind: str, path: str | Path) -> None:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        if self._is_tde:
            if kind == "spectrum":
                self.spectrum_figure.savefig(output, dpi=300)
                return
            if kind == "matrix":
                self.matrix_figure.savefig(output, dpi=300)
                return
            if kind == "combined":
                figure = Figure(figsize=(10, 8), constrained_layout=True)
                axes = figure.subplots(2, 1)
                for source, target in zip((self.spectrum_figure, self.matrix_figure), axes, strict=False):
                    source_axis = source.axes[0] if source.axes else None
                    if source_axis is None:
                        continue
                    for line in source_axis.lines:
                        target.plot(line.get_xdata(), line.get_ydata(), label=line.get_label(), color=line.get_color(), linestyle=line.get_linestyle(), linewidth=line.get_linewidth())
                    for collection in source_axis.collections:
                        offsets = collection.get_offsets()
                        if len(offsets):
                            target.scatter(offsets[:, 0], offsets[:, 1], color=collection.get_facecolors(), s=collection.get_sizes())
                    target.set_title(source_axis.get_title())
                    target.set_xlabel(source_axis.get_xlabel())
                    target.set_ylabel(source_axis.get_ylabel())
                    target.grid(True, color="#dddddd", linewidth=0.45)
                    if source_axis.get_legend() is not None:
                        target.legend(fontsize=8, frameon=False, ncol=2)
                figure.savefig(output, dpi=300)
                return
            raise ValueError(f"Unknown TDE figure kind: {kind}")
        if kind == "spectrum":
            self.spectrum_figure.savefig(output, dpi=300)
        elif kind == "matrix":
            self.matrix_figure.savefig(output, dpi=300)
        elif kind == "combined":
            figure = Figure(figsize=(10, 8), constrained_layout=True)
            axes = figure.subplots(2, 1)
            # The on-screen matrix is the authoritative multi-band view.  The
            # legacy two-row combined export remains a compact first-band
            # summary so it does not silently replace the supplied axes.
            first_band = self._selected_band()
            plot_spectrum(axes[0], self.prepared, first_band, self.scale_combo.currentData(), f"{self.payload.get('file_id', '')} | " if self.payload else "", int(self.font_spin.value()))
            matrix_prepared = prepare_connectivity(self._tables(), self._current_method(), int(self.component_combo.currentData() or 1), self._selected_pairs())
            if self.matrix_level_combo.currentData() == "channel_pair":
                matrix_pair = self._focus_pair or (self._selected_pairs()[0] if self._selected_pairs() else None)
                plot_channel_pair_matrix(axes[1], figure, matrix_prepared, first_band, matrix_pair, bool(self.swap_matrix_check.isChecked()), int(self.font_spin.value()))
            else:
                plot_matrix(axes[1], figure, matrix_prepared, first_band, self.scale_combo.currentData(), f"{self.payload.get('file_id', '')} | " if self.payload else "", int(self.font_spin.value()))
            figure.savefig(output, dpi=300)
        else:
            raise ValueError(f"Unknown connectivity figure kind: {kind}")

    def save_all(self, output_dir: str | Path) -> list[Path]:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        saved: list[Path] = []
        for kind in ("spectrum", "matrix", "combined"):
            for suffix in (".png", ".svg"):
                path = output / f"connectivity_{kind}{suffix}"
                self.save_figure(kind, path)
                saved.append(path)
        return saved

    def save_tables(self, prefix: str | Path) -> list[Path]:
        base = Path(prefix)
        if base.suffix:
            base = base.with_suffix("")
        base.parent.mkdir(parents=True, exist_ok=True)
        saved: list[Path] = []
        if self._is_tde:
            source_tables = self._tables()
            tables = {
                "spectrum": source_tables.get("region_spectrum", pd.DataFrame()),
                "band_summary": source_tables.get("band_summary", pd.DataFrame()),
                "channel_pair_band_summary": source_tables.get("channel_pair_summary", pd.DataFrame()),
            }
        else:
            tables = {
                "spectrum": self.prepared.get("spectrum", pd.DataFrame()),
                "band_summary": self.prepared.get("bands", pd.DataFrame()),
                "channel_pair_band_summary": self.prepared.get("channel_pair_bands", pd.DataFrame()),
            }
        for name, frame in tables.items():
            path = base.parent / f"{base.name}_{name}.csv"
            frame.to_csv(path, index=False, encoding="utf-8-sig")
            saved.append(path)
        selected_band_names = [str(band.get("name", "")) for band in self._selected_bands()]
        settings = pd.DataFrame(
            [
                {
                    "file_id": self.payload.get("file_id", "") if self.payload else "",
                    "metric": self._current_method(),
                    "metric_label": method_label(self._current_method()),
                    "selected_pairs": "|".join(pair_label(*pair) for pair in self._selected_pairs()),
                    "selected_band": selected_band_names[0] if selected_band_names else "",
                    "selected_bands": "|".join(selected_band_names),
                    "component_index": self.component_combo.currentData() or "",
                    "scale": self.scale_combo.currentData(),
                    "matrix_level": self.matrix_level_combo.currentData(),
                    "matrix_swap": self.swap_matrix_check.isChecked(),
                    "dpli_neutral_reference": 0.5,
                    "tde_display": "delay curve + band-level brain-region comparison" if self._is_tde else "",
                    "mic_display_definition": "absolute value of raw signed MIC; raw signed MIC remains in spectrum table",
                    "mim_display_definition": "raw unnormalised MIM; no mean subtraction or clipping",
                    "matrix_definition": "frequency-bin summary within the selected band; mirrored cells are the same estimate, not additional samples",
                }
            ]
        )
        path = base.parent / f"{base.name}_settings.csv"
        settings.to_csv(path, index=False, encoding="utf-8-sig")
        saved.append(path)
        return saved
