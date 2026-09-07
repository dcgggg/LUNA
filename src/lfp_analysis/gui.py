"""PySide6 desktop application for interactive LFP analysis.

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
from PySide6 import QtCore, QtGui, QtWidgets

from .config import load_config
from .gui_engine import inspect_file, load_saved_run, run_gui_analysis
from .gui_specs import (
    PARAMETER_DEFINITIONS,
    REGION_ORDER,
    REGION_PAIRS,
    config_value,
    parameter_schema,
    set_config_value,
    validate_snapshot,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
INDICATORS = ("Quality", "PSD", "Band Power", "FOOOF", "MIC", "MIM", "wpli2_debiased", "Time Delay")


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

    @QtCore.Slot()
    def run(self) -> None:
        try:
            outcome = run_gui_analysis(
                self.snapshot,
                self.config_path,
                self.metadata_dir,
                progress=lambda message, percent: self.progress.emit(message, int(percent)),
                result_callback=lambda payload: self.result.emit(payload),
                cancel_event=self.cancel_event,
            )
        except Exception as exc:  # noqa: BLE001 - worker forwards all failures
            outcome = {"run_dir": "", "manifest": {"status": "failed", "errors": [f"{type(exc).__name__}: {exc}"]}}
        self.finished.emit(outcome)


class InspectWorker(QtCore.QObject):
    finished = QtCore.Signal(object)
    failed = QtCore.Signal(str)

    def __init__(self, paths: list[str], metadata_dir: Path) -> None:
        super().__init__()
        self.paths = paths
        self.metadata_dir = metadata_dir

    @QtCore.Slot()
    def run(self) -> None:
        try:
            self.finished.emit([inspect_file(path, self.metadata_dir) for path in self.paths])
        except Exception as exc:  # noqa: BLE001 - display the readable error
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class ResultCanvas(FigureCanvasQTAgg):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        self.figure = Figure(figsize=(9, 5), tight_layout=True)
        super().__init__(self.figure)
        self.setParent(parent)

    def show_payload(self, payload: dict[str, Any]) -> None:
        self.figure.clear()
        axis = self.figure.add_subplot(111)
        metric = str(payload.get("metric", "Result"))
        tables = payload.get("tables", {})
        file_id = payload.get("file_id", "")
        if metric == "Quality":
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
            for channel, group in table.groupby("channel_name") if not table.empty else []:
                axis.plot(group["frequency_hz"], group["psd_value"], linewidth=0.85, label=str(channel))
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
        axis.set_title(f"{file_id} | {metric}")
        axis.grid(True, color="#dddddd", linewidth=0.4)
        self.draw_idle()


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, input_files: list[str] | None = None, output_dir: str | None = None) -> None:
        super().__init__()
        self.setWindowTitle("小鼠多脑区 LFP 分析 GUI")
        self.resize(1500, 980)
        self.config_path = PROJECT_ROOT / "configs" / "default.yaml"
        self.metadata_dir = PROJECT_ROOT / "metadata"
        self.base_config = load_config(self.config_path)
        self.file_infos: list[dict[str, Any]] = []
        self.current_info: dict[str, Any] | None = None
        self.result_payloads: dict[str, dict[str, Any]] = {}
        self.result_records: dict[str, dict[str, Any]] = {}
        self.loaded_run: dict[str, Any] | None = None
        self.analysis_thread: QtCore.QThread | None = None
        self.analysis_worker: AnalysisWorker | None = None
        self.inspect_thread: QtCore.QThread | None = None
        self._running = False
        self._dirty = False
        self._build_ui()
        self._restore_defaults()
        if output_dir:
            self.output_edit.setText(str(Path(output_dir).expanduser()))
        if input_files:
            QtCore.QTimer.singleShot(100, lambda: self.load_paths(input_files))

    def _build_ui(self) -> None:
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        root = QtWidgets.QHBoxLayout(central)
        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        root.addWidget(splitter)

        left_scroll = QtWidgets.QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_panel = QtWidgets.QWidget()
        left_scroll.setWidget(left_panel)
        left_layout = QtWidgets.QVBoxLayout(left_panel)
        left_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        splitter.addWidget(left_scroll)

        right = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right)
        splitter.addWidget(right)
        splitter.setSizes([520, 980])

        left_layout.addWidget(self._build_data_group())
        left_layout.addWidget(self._build_selection_group())
        left_layout.addWidget(self._build_indicator_group())
        left_layout.addWidget(self._build_parameter_group())
        left_layout.addWidget(self._build_task_group())

        self.result_combo = QtWidgets.QComboBox()
        self.result_combo.currentTextChanged.connect(self._show_selected_result)
        right_layout.addWidget(self.result_combo)
        self.canvas = ResultCanvas()
        self.toolbar = NavigationToolbar2QT(self.canvas, self)
        right_layout.addWidget(self.toolbar)
        right_layout.addWidget(self.canvas, stretch=3)
        self.table = QtWidgets.QTableWidget()
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        right_layout.addWidget(self.table, stretch=2)
        self.status_text = QtWidgets.QPlainTextEdit()
        self.status_text.setReadOnly(True)
        self.status_text.setMaximumBlockCount(2000)
        right_layout.addWidget(self.status_text, stretch=1)

    def _group(self, title: str) -> tuple[QtWidgets.QGroupBox, QtWidgets.QVBoxLayout]:
        box = QtWidgets.QGroupBox(title)
        layout = QtWidgets.QVBoxLayout(box)
        return box, layout

    def _build_data_group(self) -> QtWidgets.QGroupBox:
        box, layout = self._group("数据")
        row = QtWidgets.QHBoxLayout()
        add = QtWidgets.QPushButton("添加 FIF")
        add.clicked.connect(self._choose_files)
        clear = QtWidgets.QPushButton("清空")
        clear.clicked.connect(self._clear_files)
        row.addWidget(add)
        row.addWidget(clear)
        layout.addLayout(row)
        self.file_combo = QtWidgets.QComboBox()
        self.file_combo.currentIndexChanged.connect(self._file_changed)
        layout.addWidget(self.file_combo)
        output_row = QtWidgets.QHBoxLayout()
        self.output_edit = QtWidgets.QLineEdit(str(PROJECT_ROOT / "results" / "gui"))
        choose_output = QtWidgets.QPushButton("输出目录")
        choose_output.clicked.connect(self._choose_output)
        output_row.addWidget(self.output_edit)
        output_row.addWidget(choose_output)
        layout.addLayout(output_row)
        self.data_info_label = QtWidgets.QLabel("尚未载入文件。")
        self.data_info_label.setWordWrap(True)
        layout.addWidget(self.data_info_label)
        return box

    def _build_selection_group(self) -> QtWidgets.QGroupBox:
        box, layout = self._group("分析范围")
        layout.addWidget(QtWidgets.QLabel("脑区（用于批量选择通道）"))
        region_row = QtWidgets.QHBoxLayout()
        self.region_checks: dict[str, QtWidgets.QCheckBox] = {}
        for region in REGION_ORDER:
            checkbox = QtWidgets.QCheckBox(region)
            checkbox.setChecked(True)
            self.region_checks[region] = checkbox
            region_row.addWidget(checkbox)
        apply_regions = QtWidgets.QPushButton("应用脑区选择")
        apply_regions.clicked.connect(self._apply_region_selection)
        region_row.addWidget(apply_regions)
        layout.addLayout(region_row)
        layout.addWidget(QtWidgets.QLabel("实际通道（按 FIF 通道名和映射显示）"))
        self.channel_list = QtWidgets.QListWidget()
        self.channel_list.setMaximumHeight(190)
        self.channel_list.itemChanged.connect(self._selection_changed)
        layout.addWidget(self.channel_list)
        epoch_row = QtWidgets.QHBoxLayout()
        epoch_row.addWidget(QtWidgets.QLabel("epoch 子集"))
        self.epoch_edit = QtWidgets.QLineEdit("all")
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
        self.selection_label = QtWidgets.QLabel("选择数据量：尚未载入")
        layout.addWidget(self.selection_label)
        layout.addWidget(QtWidgets.QLabel("连接脑区对"))
        self.pair_checks: dict[tuple[str, str], QtWidgets.QCheckBox] = {}
        pair_grid = QtWidgets.QGridLayout()
        for index, pair in enumerate(REGION_PAIRS):
            checkbox = QtWidgets.QCheckBox(f"{pair[0]}–{pair[1]}")
            checkbox.setChecked(True)
            checkbox.stateChanged.connect(self._selection_changed)
            self.pair_checks[pair] = checkbox
            pair_grid.addWidget(checkbox, index // 3, index % 3)
        layout.addLayout(pair_grid)
        return box

    def _build_indicator_group(self) -> QtWidgets.QGroupBox:
        box, layout = self._group("指标")
        self.indicator_checks: dict[str, QtWidgets.QCheckBox] = {}
        descriptions = {
            "Quality": "读取质量和有效时长",
            "PSD": "Welch 功率谱",
            "Band Power": "频段绝对/相对功率",
            "FOOOF": "specparam/FOOOF 参数化",
            "MIC": "多变量 MIC",
            "MIM": "多变量 MIM",
            "wpli2_debiased": "通道对去偏平方 wPLI",
            "Time Delay": "PyBispectra 时间延迟",
        }
        for name in INDICATORS:
            checkbox = QtWidgets.QCheckBox(f"{name}  —  {descriptions[name]}")
            checkbox.stateChanged.connect(self._indicator_changed)
            self.indicator_checks[name] = checkbox
            layout.addWidget(checkbox)
        return box

    def _build_parameter_group(self) -> QtWidgets.QGroupBox:
        box, layout = self._group("计算参数（实际传入后端）")
        self.parameter_tabs = QtWidgets.QTabWidget()
        self.parameter_widgets: dict[str, QtWidgets.QWidget] = {}
        self.parameter_labels: dict[str, QtWidgets.QLabel] = {}
        tab_layouts: dict[str, QtWidgets.QFormLayout] = {}
        for tab_name in ("PSD / Welch", "FOOOF", "Connectivity", "频段功率", "Time Delay"):
            tab = QtWidgets.QWidget()
            form = QtWidgets.QFormLayout(tab)
            form.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
            tab_layouts[tab_name] = form
            self.parameter_tabs.addTab(tab, tab_name)
        for definition in PARAMETER_DEFINITIONS:
            tab_name = {
                "psd": "PSD / Welch",
                "parameterization": "FOOOF",
                "connectivity": "Connectivity",
                "time_delay": "Time Delay",
            }.get(definition.key.split(".")[0], "PSD / Welch")
            widget = self._make_parameter_widget(definition)
            self.parameter_widgets[definition.key] = widget
            label = QtWidgets.QLabel(f"{definition.label} ({definition.unit})" if definition.unit else definition.label)
            label.setToolTip(definition.help_text)
            self.parameter_labels[definition.key] = label
            tab_layouts[tab_name].addRow(label, widget)
        band_box = QtWidgets.QGroupBox("可编辑频段（频段边界改动只重新汇总已有 PSD）")
        band_layout = QtWidgets.QVBoxLayout(band_box)
        self.band_table = QtWidgets.QTableWidget(0, 3)
        self.band_table.setHorizontalHeaderLabels(["名称", "下限 Hz", "上限 Hz"])
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
        layout.addWidget(self.parameter_tabs)
        return box

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
                "psd.window": ["hann", "hamming", "blackman", "boxcar"],
                "psd.detrend": ["constant", "linear", "none"],
                "psd.average": ["mean", "median"],
                "psd.epoch_aggregation": ["mean", "median"],
                "parameterization.aperiodic_mode": ["fixed", "knee"],
                "connectivity.rank_strategy": ["data_driven_energy_99pct", "fixed_rank"],
            }.get(definition.key, [str(current)])
            widget.addItems(choices)
            index = widget.findText(str(current))
            widget.setCurrentIndex(max(0, index))
            widget.currentTextChanged.connect(self._selection_changed)
        elif definition.value_type == "int":
            widget = QtWidgets.QSpinBox()
            widget.setRange(int(definition.minimum or -2_000_000_000), int(definition.maximum or 2_000_000_000))
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

    def _build_task_group(self) -> QtWidgets.QGroupBox:
        box, layout = self._group("任务与结果")
        self.run_button = QtWidgets.QPushButton("运行勾选指标")
        self.run_button.clicked.connect(self._run)
        self.cancel_button = QtWidgets.QPushButton("取消")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self._cancel)
        row = QtWidgets.QHBoxLayout()
        row.addWidget(self.run_button)
        row.addWidget(self.cancel_button)
        layout.addLayout(row)
        row2 = QtWidgets.QHBoxLayout()
        for text, callback in (("保存预设", self._save_preset), ("载入预设", self._load_preset), ("恢复默认", self._restore_defaults), ("载入历史", self._load_history)):
            button = QtWidgets.QPushButton(text)
            button.clicked.connect(callback)
            row2.addWidget(button)
        layout.addLayout(row2)
        row3 = QtWidgets.QHBoxLayout()
        export_button = QtWidgets.QPushButton("导出当前图")
        export_button.clicked.connect(self._export_figure)
        open_button = QtWidgets.QPushButton("打开结果目录")
        open_button.clicked.connect(self._open_output)
        row3.addWidget(export_button)
        row3.addWidget(open_button)
        layout.addLayout(row3)
        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 100)
        layout.addWidget(self.progress)
        self.task_label = QtWidgets.QLabel("状态：待运行")
        self.task_label.setWordWrap(True)
        layout.addWidget(self.task_label)
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
            elif isinstance(widget, QtWidgets.QSpinBox):
                widget.setValue(int(value))
            else:
                widget.setValue(float(value))
        self.band_table.setRowCount(0)
        for name, bounds in self.base_config.get("bands", {}).items():
            self._add_band_row(str(name), float(bounds[0]), float(bounds[1]))
        denominator = self.base_config.get("relative_power", {}).get("denominator_hz", [1.0, 100.0])
        self.denominator_low.setValue(float(denominator[0]))
        self.denominator_high.setValue(float(denominator[1]))
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
        self.task_label.setText("状态：正在读取 FIF 和通道映射…")
        self.run_button.setEnabled(False)
        self.inspect_thread = QtCore.QThread(self)
        worker = InspectWorker(paths, self.metadata_dir)
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

    def _inspection_finished(self, infos: list[dict[str, Any]]) -> None:
        self.file_infos = infos
        self.file_combo.blockSignals(True)
        self.file_combo.clear()
        for info in infos:
            self.file_combo.addItem(Path(info["path"]).name)
        self.file_combo.blockSignals(False)
        if infos:
            self.file_combo.setCurrentIndex(0)
            self._file_changed(0)
        self.run_button.setEnabled(True)
        self.task_label.setText(f"状态：已读取 {len(infos)} 个文件。")
        self._set_dirty(True)

    def _inspection_failed(self, message: str) -> None:
        self.run_button.setEnabled(True)
        self.task_label.setText(f"读取失败：{message}")
        QtWidgets.QMessageBox.critical(self, "读取 FIF 失败", message)

    def _clear_files(self) -> None:
        self.file_infos = []
        self.current_info = None
        self.file_combo.clear()
        self.channel_list.clear()
        self.data_info_label.setText("尚未载入文件。")
        self.selection_label.setText("选择数据量：尚未载入")
        self._set_dirty(True)

    def _file_changed(self, index: int) -> None:
        if 0 <= index < len(self.file_infos):
            self.current_info = self.file_infos[index]
            self._populate_current_file()

    def _populate_current_file(self) -> None:
        if self.current_info is None:
            return
        info = self.current_info
        table = info["channel_table"]
        mapping = {str(row.channel_name): row for row in table.itertuples()}
        self.channel_list.blockSignals(True)
        self.channel_list.clear()
        for name in info["loaded"].ch_names:
            row = mapping.get(str(name))
            region = str(getattr(row, "region", "")) if row else ""
            physical = getattr(row, "physical_channel_number", "") if row else ""
            text = f"{name} | 物理 {physical or '?'} | {region or '未映射'}"
            item = QtWidgets.QListWidgetItem(text)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, str(name))
            item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(QtCore.Qt.CheckState.Checked)
            self.channel_list.addItem(item)
        self.channel_list.blockSignals(False)
        self.time_start.setRange(info["tmin"], info["tmax"] + 1.0 / info["sfreq"])
        self.time_end.setRange(info["tmin"], info["tmax"] + 1.0 / info["sfreq"])
        self.time_start.setValue(info["tmin"])
        self.time_end.setValue(info["tmax"] + 1.0 / info["sfreq"])
        self.data_info_label.setText(
            f"文件：{Path(info['path']).name}\n"
            f"采样率：{info['sfreq']:g} Hz；形状：{info['n_epochs']} × {info['n_channels']} × {info['n_times']}\n"
            f"epoch 时间：{info['tmin']:g}–{info['tmax']:g} s；文件级名义时长：{info['effective_duration_s']:g} s\n"
            f"SHA-256：{info['sha256'][:16]}…"
        )
        self._update_selection_label()

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

    def _selection_changed(self, *_args: Any) -> None:
        self._update_selection_label()
        self._set_dirty(True)

    def _update_selection_label(self) -> None:
        if self.current_info is None:
            return
        channels = self._selected_channel_names()
        epochs = self._parse_epochs(self.epoch_edit.text(), self.current_info["n_epochs"], show_error=False)
        duration = max(0.0, self.time_end.value() - self.time_start.value())
        self.selection_label.setText(f"选择数据量：{len(channels)} 通道 × {len(epochs)} epoch × {duration:g} s；约 {len(epochs) * duration:g} 有效秒")

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
                QtWidgets.QMessageBox.warning(self, "epoch 子集无效", f"{exc}")
            return []

    def _indicator_changed(self, *_args: Any) -> None:
        self._update_parameter_tabs()
        self._set_dirty(True)

    def _update_parameter_tabs(self) -> None:
        selected = self._selected_indicators()
        self.parameter_tabs.setTabEnabled(0, bool(set(selected) & {"PSD", "Band Power", "FOOOF"}))
        self.parameter_tabs.setTabEnabled(1, "FOOOF" in selected)
        self.parameter_tabs.setTabEnabled(2, bool(set(selected) & {"MIC", "MIM", "wpli2_debiased"}))
        self.parameter_tabs.setTabEnabled(3, bool(set(selected) & {"PSD", "Band Power", "FOOOF"}))
        self.parameter_tabs.setTabEnabled(4, "Time Delay" in selected)

    def _selected_indicators(self) -> list[str]:
        return [name for name, checkbox in self.indicator_checks.items() if checkbox.isChecked()]

    def _read_parameter_values(self) -> dict[str, Any]:
        values: dict[str, Any] = {}
        for definition in PARAMETER_DEFINITIONS:
            widget = self.parameter_widgets[definition.key]
            if isinstance(widget, QtWidgets.QComboBox):
                value: Any = widget.currentText()
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
        return values

    def _snapshot(self) -> dict[str, Any]:
        if self.current_info is None:
            raise ValueError("请先添加并读取至少一个 FIF 文件。")
        epochs = self._parse_epochs(self.epoch_edit.text(), self.current_info["n_epochs"])
        pairs = [list(pair) for pair, checkbox in self.pair_checks.items() if checkbox.isChecked()]
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
            "selection": {"time_start_s": self.time_start.value(), "time_end_s": self.time_end.value()},
            "values": self._read_parameter_values(),
            "parameter_schema": parameter_schema(),
        }

    def _run(self) -> None:
        try:
            snapshot = self._snapshot()
            if not snapshot["input_files"]:
                raise ValueError("请先添加 FIF 文件。")
            if not snapshot["selected_region_pairs"] and set(snapshot["indicators"]) & {"MIC", "MIM", "wpli2_debiased"}:
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
            QtWidgets.QMessageBox.warning(self, "参数或数据选择无效", str(exc))
            return
        self._running = True
        self._dirty = False
        self.run_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.task_label.setText("状态：后台运行中…")
        self.progress.setValue(0)
        self.analysis_thread = QtCore.QThread(self)
        self.analysis_worker = AnalysisWorker(snapshot, self.config_path, self.metadata_dir)
        self.analysis_worker.moveToThread(self.analysis_thread)
        self.analysis_thread.started.connect(self.analysis_worker.run)
        self.analysis_worker.progress.connect(self._progress_update)
        self.analysis_worker.result.connect(self._result_ready)
        self.analysis_worker.finished.connect(self._run_finished)
        self.analysis_worker.finished.connect(self.analysis_thread.quit)
        self.analysis_thread.finished.connect(self.analysis_worker.deleteLater)
        self.analysis_thread.finished.connect(self.analysis_thread.deleteLater)
        self.analysis_thread.start()

    def _cancel(self) -> None:
        if self.analysis_worker is not None:
            self.analysis_worker.cancel_event.set()
            self.task_label.setText("状态：正在请求取消；已完成结果会保留…")

    def _progress_update(self, message: str, percent: int) -> None:
        self.task_label.setText(f"状态：{message}")
        self.progress.setValue(percent)
        self._log(message)

    def _result_ready(self, payload: dict[str, Any]) -> None:
        if payload.get("status") == "failed":
            self._log(f"失败：{payload.get('file_id', '')} — {payload.get('error', '')}")
            return
        metric = str(payload.get("metric", "Result"))
        file_id = str(payload.get("file_id", "file"))
        key = f"{file_id} | {metric}"
        self.result_payloads[key] = payload
        self.result_records[key] = payload.get("record", {})
        if self.result_combo.findText(key) < 0:
            self.result_combo.addItem(key)
        self.result_combo.setCurrentText(key)
        self._show_payload(payload)
        record = payload.get("record", {})
        self._log(f"完成：{key}；状态={record.get('status', 'completed')}")

    def _run_finished(self, outcome: dict[str, Any]) -> None:
        self._running = False
        self.run_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        manifest = outcome.get("manifest", {})
        self.progress.setValue(100 if manifest.get("status") in {"completed", "completed_with_errors"} else self.progress.value())
        self.task_label.setText(f"状态：{manifest.get('status', 'unknown')}；结果目录：{outcome.get('run_dir', '')}")
        self._log(json.dumps(manifest, ensure_ascii=False, indent=2))
        self.loaded_run = outcome

    def _show_selected_result(self, key: str) -> None:
        if key in self.result_payloads:
            self._show_payload(self.result_payloads[key])

    def _show_payload(self, payload: dict[str, Any]) -> None:
        self.canvas.show_payload(payload)
        tables = payload.get("tables", {})
        table = next((value for value in tables.values() if isinstance(value, pd.DataFrame) and not value.empty), pd.DataFrame())
        self._show_table(table)

    def _show_table(self, frame: pd.DataFrame) -> None:
        display = frame.head(1000).copy() if isinstance(frame, pd.DataFrame) else pd.DataFrame()
        self.table.clear()
        self.table.setRowCount(len(display))
        self.table.setColumnCount(len(display.columns))
        self.table.setHorizontalHeaderLabels([str(column) for column in display.columns])
        for row_index, row in enumerate(display.itertuples(index=False, name=None)):
            for column_index, value in enumerate(row):
                self.table.setItem(row_index, column_index, QtWidgets.QTableWidgetItem("" if pd.isna(value) else str(value)))
        self.table.resizeColumnsToContents()
        self.table.setToolTip(f"显示前 {len(display)} 行；完整数据已保存。")

    def _log(self, message: str) -> None:
        self.status_text.appendPlainText(str(message))

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
            QtWidgets.QMessageBox.warning(self, "无法保存预设", str(exc))
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "保存分析预设", str(PROJECT_ROOT / "configs" / "gui_preset.json"), "JSON (*.json)")
        if path:
            Path(path).write_text(json.dumps({key: snapshot[key] for key in ("indicators", "selected_channel_names", "selected_epoch_indices", "selected_region_pairs", "selection", "values", "parameter_schema")}, ensure_ascii=False, indent=2), encoding="utf-8")
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
            for definition in PARAMETER_DEFINITIONS:
                widget = self.parameter_widgets[definition.key]
                value = config_value(values, definition.key, None)
                if value is None:
                    continue
                if isinstance(widget, QtWidgets.QComboBox):
                    widget.setCurrentText(str(value))
                elif isinstance(widget, QtWidgets.QSpinBox):
                    widget.setValue(int(value))
                else:
                    widget.setValue(float(value))
            self.epoch_edit.setText("all")
            self._update_parameter_tabs()
            self._set_dirty(True)
            self._log(f"已载入预设：{path}")
        except Exception as exc:  # noqa: BLE001
            QtWidgets.QMessageBox.warning(self, "载入预设失败", str(exc))

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
                file_dir = run_root / file_record.get("file_dir", "")
                for record in file_record.get("metrics", []):
                    payload = self._payload_from_saved_record(record, file_record.get("file_id", "file"), file_dir)
                    if payload:
                        key = f"{file_record.get('file_id', 'file')} | {record.get('metric', 'Result')}"
                        self.result_payloads[key] = payload
                        self.result_records[key] = record
                        self.result_combo.addItem(key)
            self.loaded_run = loaded
            self.task_label.setText(f"状态：已载入历史运行 {loaded['manifest'].get('run_id', '')}；不需要原始 FIF 即可查看。")
            self._log(json.dumps(loaded["manifest"], ensure_ascii=False, indent=2))
            if self.result_combo.count():
                self.result_combo.setCurrentIndex(0)
        except Exception as exc:  # noqa: BLE001
            QtWidgets.QMessageBox.warning(self, "载入历史失败", str(exc))

    def _payload_from_saved_record(self, record: dict[str, Any], file_id: str, file_dir: Path) -> dict[str, Any] | None:
        tables: dict[str, pd.DataFrame] = {}
        for name, filename in record.get("paths", {}).get("tables", {}).items():
            if not isinstance(filename, str):
                continue
            matches = list(file_dir.rglob(Path(filename).name))
            if matches:
                try:
                    tables[name] = pd.read_csv(matches[0])
                except Exception as exc:  # noqa: BLE001
                    self._log(f"历史表读取失败：{matches[0]} — {exc}")
        metric = str(record.get("metric", "Result"))
        aliases = {
            "PSD": {"channel": tables.get("psd_channel_summary", pd.DataFrame()), "region": tables.get("psd_region_summary", pd.DataFrame())},
            "Band Power": {"band_power": tables.get("band_power_epoch_channel", pd.DataFrame()), "band_power_summary": tables.get("band_power_summary", pd.DataFrame())},
            "FOOOF": tables,
            "Connectivity": tables,
            "Time Delay": tables,
            "Quality": tables,
        }
        return {"metric": metric, "file_id": file_id, "tables": aliases.get(metric, tables), "record": record}

    def _export_figure(self) -> None:
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "导出当前图", str(PROJECT_ROOT / "results" / "gui_figure.svg"), "SVG (*.svg);;PNG (*.png);;PDF (*.pdf)")
        if path:
            self.canvas.figure.savefig(path, dpi=200)
            self._log(f"已导出图：{path}")

    def _open_output(self) -> None:
        path = Path(self.output_edit.text()).expanduser()
        path.mkdir(parents=True, exist_ok=True)
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(path.resolve())))

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        if self._running and self.analysis_worker is not None:
            self.analysis_worker.cancel_event.set()
        event.accept()


def launch(input_files: list[str] | None = None, output_dir: str | None = None) -> int:
    """Start the desktop GUI and return the Qt exit code."""
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    app.setApplicationName("Mouse LFP Analysis")
    app.setStyle("Fusion")
    window = MainWindow(input_files=input_files, output_dir=output_dir)
    window.show()
    return app.exec()
