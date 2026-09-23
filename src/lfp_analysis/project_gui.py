"""PySide6 project-management workspace for LUNA."""

from __future__ import annotations

import json
import threading
import traceback
import uuid
from pathlib import Path
from typing import Any, ClassVar

import numpy as np
import pandas as pd
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.colors import Normalize, TwoSlopeNorm
from matplotlib.figure import Figure
from PySide6 import QtCore, QtGui, QtSvg, QtWidgets

from .comparison import (
    paired_subject_summary,
    select_results,
    subject_match_preview,
    subject_summary,
)
from .gui_engine import inspect_file
from .mapping import mapping_rows
from .project_batch import MODULE_TO_INDICATORS, ProjectBatchRunner
from .project_store import (
    PROJECT_DATABASE,
    ProjectStore,
    normalize_project_folder_name,
    utc_now,
)
from .resources import packaged_resource_path
from .result_contract import load_result_manifest, load_table

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _project_font_family() -> str:
    installed = set(QtGui.QFontDatabase.families())
    for family in ("Microsoft YaHei UI", "Microsoft YaHei", "Noto Sans CJK SC", "Segoe UI"):
        if family in installed:
            return family
    for candidate in (
        Path(r"C:\Windows\Fonts\Noto Sans SC (TrueType).otf"),
        Path(r"C:\Windows\Fonts\simhei.ttf"),
        Path(r"C:\Windows\Fonts\Deng.ttf"),
    ):
        if candidate.is_file():
            font_id = QtGui.QFontDatabase.addApplicationFont(str(candidate))
            families = QtGui.QFontDatabase.applicationFontFamilies(font_id)
            if families:
                return str(families[0])
    return "Arial"


def _project_logo_pixmap(width: int = 172, height: int = 48) -> QtGui.QPixmap:
    """Load the same formal image-only LUNA logo used by the main GUI."""
    path = PROJECT_ROOT / "assets" / "branding" / "luna-logo.svg"
    if not path.is_file():
        try:
            path = packaged_resource_path("branding/luna-logo.svg")
        except (FileNotFoundError, TypeError):
            path = packaged_resource_path("branding/luna-logo-on-white.svg")
    pixmap = QtGui.QPixmap(width, height)
    pixmap.fill(QtCore.Qt.GlobalColor.transparent)
    renderer = QtSvg.QSvgRenderer(str(path))
    if not renderer.isValid():
        return pixmap
    view_box = renderer.viewBoxF()
    source_width = view_box.width() or 1.0
    source_height = view_box.height() or 1.0
    scale = min(width / source_width, height / source_height)
    target = QtCore.QRectF((width - source_width * scale) / 2.0, (height - source_height * scale) / 2.0, source_width * scale, source_height * scale)
    painter = QtGui.QPainter(pixmap)
    renderer.render(painter, target)
    painter.end()
    return pixmap


def _append_project_operation_log(
    store: ProjectStore,
    event: str,
    status: str,
    details: dict[str, Any],
) -> Path:
    """Append one auditable project-management event without signal data."""
    target = store.paths.logs / "project_operations.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "timestamp_utc": utc_now(),
        "event": event,
        "status": status,
        "project_id": store.project["project_id"],
        "project_root": str(store.paths.root),
        "details": details,
    }
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
    return target


class ClipboardTableWidget(QtWidgets.QTableWidget):
    """QTableWidget with predictable tabular copy/paste for import previews."""

    def paste_text(self, text: str, start_row: int | None = None, start_column: int | None = None) -> None:
        row0 = self.currentRow() if start_row is None else start_row
        column0 = self.currentColumn() if start_column is None else start_column
        if row0 < 0 or column0 < 0:
            return
        for row_offset, line in enumerate(text.splitlines()):
            row = row0 + row_offset
            if row >= self.rowCount():
                break
            for column_offset, value in enumerate(line.split("\t")):
                column = column0 + column_offset
                if column >= self.columnCount():
                    break
                item = self.item(row, column)
                if item is not None and item.flags() & QtCore.Qt.ItemFlag.ItemIsEditable:
                    item.setText(value)

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        if event.matches(QtGui.QKeySequence.StandardKey.Paste):
            self.paste_text(QtWidgets.QApplication.clipboard().text())
            return
        if event.matches(QtGui.QKeySequence.StandardKey.Copy):
            ranges = self.selectedRanges()
            if ranges:
                selection = ranges[0]
                text = "\n".join(
                    "\t".join(
                        self.item(row, column).text() if self.item(row, column) is not None else ""
                        for column in range(selection.leftColumn(), selection.rightColumn() + 1)
                    )
                    for row in range(selection.topRow(), selection.bottomRow() + 1)
                )
                QtWidgets.QApplication.clipboard().setText(text)
                return
        super().keyPressEvent(event)


class ImportPreviewDialog(QtWidgets.QDialog):
    COLUMNS: ClassVar[list[str]] = [
        "Include", "File", "Existing target state", "Subject", "Session", "State",
        "Condition", "Timepoint", "Unit", "Epoch indices", "Start s", "End s",
        "Duplicate", "Project copy",
    ]

    def __init__(self, store: ProjectStore, paths: list[str], config_path: Path, metadata_dir: Path, parent: QtWidgets.QWidget | None = None, inherited: dict[str, Any] | None = None) -> None:
        super().__init__(parent)
        self.setFont(QtGui.QFont(_project_font_family(), 9))
        self.store = store
        self.config_path = config_path
        self.metadata_dir = metadata_dir
        self.inherited = dict(inherited or {})
        self.targets = self.store.state_targets()
        self.targets_by_id = {str(row["state_record_id"]): row for row in self.targets}
        self.setWindowTitle("LUNA — Import preview")
        self.resize(1500, 620)
        layout = QtWidgets.QVBoxLayout(self)
        note = QtWidgets.QLabel(
            "Each file must be mapped to an existing state. Import never creates subjects, sessions, or states. "
            "The selected target is frozen by its internal ID when you confirm this dialog."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        self.target_summary = QtWidgets.QLabel(self._target_summary_text(str(self.inherited.get("state_record_id") or "")))
        self.target_summary.setWordWrap(True)
        layout.addWidget(self.target_summary)
        self.table = ClipboardTableWidget(len(paths), len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Stretch)
        for row, raw_path in enumerate(paths):
            source = Path(raw_path).resolve()
            include = QtWidgets.QTableWidgetItem()
            include.setFlags(include.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
            include.setCheckState(QtCore.Qt.CheckState.Checked)
            self.table.setItem(row, 0, include)
            file_item = QtWidgets.QTableWidgetItem(str(source))
            file_item.setFlags(file_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 1, file_item)
            combo = self._target_combo(str(self.inherited.get("state_record_id") or ""))
            combo.currentIndexChanged.connect(lambda _index, current_row=row: self._target_changed(current_row))
            self.table.setCellWidget(row, 2, combo)
            for column in range(3, 12):
                item = QtWidgets.QTableWidgetItem()
                if column <= 8:
                    item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row, column, item)
            self._target_changed(row)
            duplicates = self.store.duplicate_candidates(source)
            duplicate_item = QtWidgets.QTableWidgetItem("content duplicate" if duplicates else "new content")
            duplicate_item.setFlags(duplicate_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
            if duplicates:
                duplicate_item.setBackground(QtGui.QColor("#ffe6b3"))
                duplicate_item.setToolTip("Existing data_unit_id: " + ", ".join(item["data_unit_id"] for item in duplicates))
            self.table.setItem(row, 12, duplicate_item)
            target_text = self.store.paths.raw_data / "<content fingerprint>" / source.name
            target_item = QtWidgets.QTableWidgetItem(str(target_text.relative_to(self.store.paths.root)))
            target_item.setFlags(target_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 13, target_item)
        layout.addWidget(self.table)
        tools = QtWidgets.QHBoxLayout()
        duplicate_row = QtWidgets.QPushButton("Duplicate selected row")
        duplicate_row.clicked.connect(self._duplicate_selected_row)
        fill_down = QtWidgets.QPushButton("Fill current cell down")
        fill_down.clicked.connect(self._fill_current_down)
        fill_targets = QtWidgets.QPushButton("Fill target state down")
        fill_targets.clicked.connect(self._fill_target_down)
        tools.addWidget(duplicate_row); tools.addWidget(fill_down); tools.addWidget(fill_targets); tools.addStretch(1)
        layout.addLayout(tools)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Cancel | QtWidgets.QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self._validate)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _text(self, row: int, column: int) -> str:
        item = self.table.item(row, column)
        return item.text().strip() if item else ""

    def _target_combo(self, selected_id: str = "") -> QtWidgets.QComboBox:
        combo = QtWidgets.QComboBox()
        combo.setMinimumWidth(330)
        combo.addItem("— Pending assignment —", "")
        for target in self.targets:
            state_id = str(target["state_record_id"])
            combo.addItem(self._target_label(target), state_id)
            combo.setItemData(combo.count() - 1, self._target_label(target), QtCore.Qt.ItemDataRole.ToolTipRole)
        index = combo.findData(selected_id)
        combo.setCurrentIndex(max(index, 0))
        return combo

    @staticmethod
    def _target_label(target: dict[str, Any]) -> str:
        timepoint = ""
        if target.get("timepoint_value") is not None:
            timepoint = f"; {target['timepoint_value']:g} {target.get('timepoint_unit') or ''}".rstrip()
        condition = f"; {target.get('condition_label')}" if target.get("condition_label") else ""
        return f"{target['subject_code']} / {target['session_key']} / {target['display_name']}{condition}{timepoint}"

    def _target_summary_text(self, state_id: str) -> str:
        target = self.targets_by_id.get(state_id)
        if target is None:
            return f"Project: {self.store.project['name']} | Target: choose an existing state for every included file."
        return f"Project: {self.store.project['name']} | Selected target: {self._target_label(target)}"

    def _target_id(self, row: int) -> str:
        combo = self.table.cellWidget(row, 2)
        return str(combo.currentData() or "") if isinstance(combo, QtWidgets.QComboBox) else ""

    def _target_changed(self, row: int) -> None:
        target = self.targets_by_id.get(self._target_id(row))
        values = (
            [target.get("subject_code", ""), target.get("session_key", ""), target.get("display_name", ""),
             target.get("condition_label", ""), "" if target.get("timepoint_value") is None else f"{target['timepoint_value']:g}",
             target.get("timepoint_unit", "")]
            if target else ["", "", "", "", "", ""]
        )
        for column, value in zip(range(3, 9), values, strict=True):
            item = self.table.item(row, column)
            if item is not None:
                item.setText(str(value or ""))

    def rows(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for row in range(self.table.rowCount()):
            include = self.table.item(row, 0)
            if include is None or include.checkState() != QtCore.Qt.CheckState.Checked:
                continue
            state_id = self._target_id(row)
            target = self.targets_by_id.get(state_id, {})
            epoch_text = self._text(row, 9)
            start_text = self._text(row, 10)
            end_text = self._text(row, 11)
            result.append({
                "source_path": self._text(row, 1), "state_record_id": state_id,
                "subject_code": target.get("subject_code", ""), "session_key": target.get("session_key", ""),
                "condition_label": target.get("condition_label", ""), "timepoint_value": target.get("timepoint_value"),
                "timepoint_unit": target.get("timepoint_unit", ""), "reference_event": target.get("reference_event", ""),
                "display_name": target.get("display_name", ""),
                "epoch_selection": {"indices": self._parse_epoch_indices(epoch_text)} if epoch_text else {},
                "time_selection": {"start_s": float(start_text), "end_s": float(end_text)} if start_text and end_text else {},
                "selection_text_complete": bool(start_text) == bool(end_text),
                "is_duplicate": self._text(row, 12) == "content duplicate",
            })
        return result

    @staticmethod
    def _parse_epoch_indices(text: str) -> list[int]:
        values: list[int] = []
        for token in text.replace(";", ",").split(","):
            token = token.strip()
            if not token:
                continue
            if "-" in token:
                start, end = (int(part.strip()) for part in token.split("-", 1))
                if start < 0 or end < start:
                    raise ValueError(f"invalid epoch range: {token}")
                values.extend(range(start, end + 1))
            else:
                value = int(token)
                if value < 0:
                    raise ValueError(f"invalid epoch index: {token}")
                values.append(value)
        return list(dict.fromkeys(values))

    def _duplicate_selected_row(self) -> None:
        source_row = self.table.currentRow()
        if source_row < 0:
            return
        target_row = self.table.rowCount()
        self.table.insertRow(target_row)
        for column in range(self.table.columnCount()):
            if column == 2:
                continue
            source_item = self.table.item(source_row, column)
            copied = source_item.clone() if source_item is not None else QtWidgets.QTableWidgetItem()
            self.table.setItem(target_row, column, copied)
        combo = self._target_combo(self._target_id(source_row))
        combo.currentIndexChanged.connect(lambda _index, current_row=target_row: self._target_changed(current_row))
        self.table.setCellWidget(target_row, 2, combo)
        self._target_changed(target_row)
        self.table.selectRow(target_row)

    def _fill_current_down(self) -> None:
        row, column = self.table.currentRow(), self.table.currentColumn()
        if row < 0 or column < 9 or column >= 12:
            return
        value = self._text(row, column)
        for target in range(row + 1, self.table.rowCount()):
            item = self.table.item(target, column)
            if item is not None:
                item.setText(value)

    def _fill_target_down(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            return
        state_id = self._target_id(row)
        for target_row in range(row + 1, self.table.rowCount()):
            combo = self.table.cellWidget(target_row, 2)
            if isinstance(combo, QtWidgets.QComboBox):
                index = combo.findData(state_id)
                combo.setCurrentIndex(max(index, 0))

    def _validate(self) -> None:
        errors: list[str] = []
        try:
            rows = self.rows()
        except ValueError as exc:
            QtWidgets.QMessageBox.warning(self, "Invalid selection", str(exc))
            return
        seen: set[tuple[str, str, str]] = set()
        for number, row in enumerate(rows, 1):
            if not row["state_record_id"]:
                errors.append(f"row {number}: assign an existing target state")
            elif row["state_record_id"] not in self.targets_by_id:
                errors.append(f"row {number}: target state no longer exists; refresh and choose again")
            if not row["selection_text_complete"]:
                errors.append(f"row {number}: both Start s and End s are required for a time selection")
            if row["time_selection"] and row["time_selection"]["end_s"] <= row["time_selection"]["start_s"]:
                errors.append(f"row {number}: End s must be greater than Start s")
            try:
                inspected = inspect_file(row["source_path"], self.metadata_dir, self.config_path)
                indices = row["epoch_selection"].get("indices", [])
                if indices and max(indices) >= int(inspected["n_epochs"]):
                    errors.append(f"row {number}: epoch selection exceeds the available {inspected['n_epochs']} epochs")
                if row["time_selection"]:
                    lower = float(inspected["tmin"])
                    upper = float(inspected["tmax"] + 1.0 / inspected["sfreq"])
                    if row["time_selection"]["start_s"] < lower or row["time_selection"]["end_s"] > upper:
                        errors.append(f"row {number}: time selection must stay within [{lower:g}, {upper:g}] s")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"row {number}: source inspection failed: {exc}")
            if self.store.duplicate_selection_candidates(
                row["source_path"],
                epoch_selection=row["epoch_selection"],
                time_selection=row["time_selection"],
            ):
                errors.append(f"row {number}: identical source and selection are already registered")
            key = (row["source_path"], json.dumps(row["epoch_selection"], sort_keys=True), json.dumps(row["time_selection"], sort_keys=True))
            if key in seen:
                errors.append(f"row {number}: identical source and selection are repeated in this import preview")
            seen.add(key)
        if errors:
            QtWidgets.QMessageBox.warning(self, "Import preview is incomplete", "\n".join(errors))
            return
        if not rows:
            QtWidgets.QMessageBox.warning(self, "Nothing to import", "Select at least one non-duplicate file.")
            return
        self.accept()


class ChannelMappingDialog(QtWidgets.QDialog):
    def __init__(self, rows: list[dict[str, Any]], parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Channel / brain-region mapping")
        self.resize(760, 560)
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(QtWidgets.QLabel("Region is user-defined. Empty regions are allowed for non-region analyses but block region-level connectivity."))
        self.table = QtWidgets.QTableWidget(len(rows), 4)
        self.table.setHorizontalHeaderLabels(["Channel", "Physical number", "Region", "Label"])
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        for row_index, row in enumerate(rows):
            for column, key in enumerate(("channel_name", "physical_channel_number", "region", "label")):
                item = QtWidgets.QTableWidgetItem(str(row.get(key, "")))
                if column == 0:
                    item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row_index, column, item)
        layout.addWidget(self.table)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Cancel | QtWidgets.QDialogButtonBox.StandardButton.Save)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def mapping(self) -> list[dict[str, Any]]:
        return [
            {
                "channel_name": self.table.item(row, 0).text().strip(),
                "physical_channel_number": self.table.item(row, 1).text().strip(),
                "region": self.table.item(row, 2).text().strip(),
                "label": self.table.item(row, 3).text().strip(),
            }
            for row in range(self.table.rowCount())
        ]


class JsonEditorDialog(QtWidgets.QDialog):
    def __init__(self, title: str, value: dict[str, Any], parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(760, 560)
        layout = QtWidgets.QVBoxLayout(self)
        note = QtWidgets.QLabel("Only explicitly entered keys override lower-priority settings. The analysis backend still validates effective parameters before calculation.")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.editor = QtWidgets.QPlainTextEdit(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))
        layout.addWidget(self.editor)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Cancel | QtWidgets.QDialogButtonBox.StandardButton.Save)
        buttons.accepted.connect(self._validate)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.value: dict[str, Any] = value

    def _validate(self) -> None:
        try:
            value = json.loads(self.editor.toPlainText())
            if not isinstance(value, dict):
                raise TypeError("The configuration must be a JSON object.")
        except (ValueError, TypeError) as exc:
            QtWidgets.QMessageBox.warning(self, "Invalid configuration", str(exc))
            return
        self.value = value
        self.accept()


class ProjectCreationDialog(QtWidgets.QDialog):
    """Small, explicit name + parent project creator."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFont(QtGui.QFont(_project_font_family(), 9))
        self.setWindowTitle("Create LUNA project")
        self.setMinimumWidth(620)
        layout = QtWidgets.QFormLayout(self)
        self.name_edit = QtWidgets.QLineEdit()
        self.parent_edit = QtWidgets.QLineEdit(str(Path.home() / "LUNAProjects"))
        browse = QtWidgets.QPushButton("Choose parent…")
        browse.clicked.connect(self._choose_parent)
        parent_row = QtWidgets.QHBoxLayout()
        parent_row.addWidget(self.parent_edit, 1)
        parent_row.addWidget(browse)
        self.preview = QtWidgets.QLabel()
        self.preview.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        self.name_edit.textChanged.connect(self._update_preview)
        self.parent_edit.textChanged.connect(self._update_preview)
        layout.addRow("Project name", self.name_edit)
        layout.addRow("Parent folder", parent_row)
        layout.addRow("Project folder", self.preview)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        create_button = buttons.addButton("Create", QtWidgets.QDialogButtonBox.ButtonRole.AcceptRole)
        create_button.clicked.connect(self._validate)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)
        self._update_preview()

    def _choose_parent(self) -> None:
        path = QtWidgets.QFileDialog.getExistingDirectory(self, "Choose parent folder", self.parent_edit.text())
        if path:
            self.parent_edit.setText(path)

    def _update_preview(self) -> None:
        try:
            folder = normalize_project_folder_name(self.name_edit.text())
            target = Path(self.parent_edit.text()).expanduser() / folder
            suffix = " — existing project" if (target / PROJECT_DATABASE).is_file() else (" — folder exists" if target.exists() else "")
            self.preview.setText(str(target) + suffix)
        except ValueError as exc:
            self.preview.setText(str(exc))

    def _validate(self) -> None:
        try:
            folder = normalize_project_folder_name(self.name_edit.text())
        except ValueError as exc:
            QtWidgets.QMessageBox.warning(self, "Invalid project name", str(exc))
            return
        parent = Path(self.parent_edit.text()).expanduser()
        target = parent / folder
        if target.exists():
            message = "An existing LUNA project has this name. Open it instead." if (target / PROJECT_DATABASE).is_file() else "The target folder already exists. Choose another project name."
            QtWidgets.QMessageBox.warning(self, "Project folder exists", f"{message}\n\n{target}")
            return
        self.accept()

    @property
    def project_name(self) -> str:
        return self.name_edit.text().strip()

    @property
    def parent_directory(self) -> Path:
        return Path(self.parent_edit.text()).expanduser().resolve()


class StructureTemplateDialog(QtWidgets.QDialog):
    """Three-step, non-JSON project structure template editor."""

    about_to_apply = QtCore.Signal()

    def __init__(self, store: ProjectStore, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFont(QtGui.QFont(_project_font_family(), 9))
        self.store = store
        self.setWindowTitle("Batch create subjects, sessions, and states")
        self.resize(900, 690)
        layout = QtWidgets.QVBoxLayout(self)
        saved_row = QtWidgets.QHBoxLayout()
        self.saved_combo = QtWidgets.QComboBox()
        self.saved_combo.addItem("New template", None)
        for item in store.structure_templates():
            self.saved_combo.addItem(item["name"], item)
        self.saved_combo.currentIndexChanged.connect(self._load_saved)
        saved_row.addWidget(QtWidgets.QLabel("Saved template"))
        saved_row.addWidget(self.saved_combo, 1)
        layout.addLayout(saved_row)
        self.steps = QtWidgets.QTabWidget()
        layout.addWidget(self.steps, 1)
        self.subjects_edit = QtWidgets.QPlainTextEdit()
        self.subjects_edit.setPlaceholderText("One subject per line, for example:\nMouse01\nMouse02\nMouse03")
        self.subject_prefix = QtWidgets.QLineEdit("Mouse")
        self.subject_start = QtWidgets.QSpinBox(); self.subject_start.setRange(0, 999999); self.subject_start.setValue(1)
        self.subject_count = QtWidgets.QSpinBox(); self.subject_count.setRange(1, 9999); self.subject_count.setValue(5)
        self.subject_padding = QtWidgets.QSpinBox(); self.subject_padding.setRange(1, 8); self.subject_padding.setValue(2)
        generate_subjects = QtWidgets.QPushButton("Generate subject list")
        generate_subjects.clicked.connect(self._generate_subjects)
        self.steps.addTab(self._text_step(self.subjects_edit, [("Prefix", self.subject_prefix), ("Start", self.subject_start), ("Count", self.subject_count), ("Zero padding", self.subject_padding)], generate_subjects), "1. Subjects")
        self.sessions_edit = QtWidgets.QPlainTextEdit()
        self.sessions_edit.setPlaceholderText("One reusable session key per line, for example:\nDay1\nDay7\nDay14")
        self.steps.addTab(self._text_step(self.sessions_edit), "2. Sessions")
        state_page = QtWidgets.QWidget(); state_layout = QtWidgets.QVBoxLayout(state_page)
        self.condition_edit = QtWidgets.QLineEdit()
        self.reference_edit = QtWidgets.QLineEdit()
        self.states_edit = QtWidgets.QPlainTextEdit()
        self.states_edit.setPlaceholderText("One state per line. Use Baseline, or label,value,unit.\nBaseline\nT20,20,min\nT40,40,min")
        state_layout.addWidget(QtWidgets.QLabel("Condition")); state_layout.addWidget(self.condition_edit)
        state_layout.addWidget(QtWidgets.QLabel("Reference event")); state_layout.addWidget(self.reference_edit)
        state_layout.addWidget(self.states_edit, 1)
        range_row = QtWidgets.QHBoxLayout()
        self.state_start = QtWidgets.QDoubleSpinBox(); self.state_start.setRange(-1e6, 1e6); self.state_start.setValue(20)
        self.state_end = QtWidgets.QDoubleSpinBox(); self.state_end.setRange(-1e6, 1e6); self.state_end.setValue(180)
        self.state_step = QtWidgets.QDoubleSpinBox(); self.state_step.setRange(0.0001, 1e6); self.state_step.setValue(20)
        self.state_unit = QtWidgets.QLineEdit("min")
        for label, widget in (("Start", self.state_start), ("End", self.state_end), ("Step", self.state_step), ("Unit", self.state_unit)):
            range_row.addWidget(QtWidgets.QLabel(label)); range_row.addWidget(widget)
        generate_states = QtWidgets.QPushButton("Generate timepoints")
        generate_states.clicked.connect(self._generate_states)
        range_row.addWidget(generate_states)
        state_layout.addLayout(range_row)
        self.steps.addTab(state_page, "3. States / timepoints")
        self.summary = QtWidgets.QLabel("Enter values to preview the affected structure.")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        distinction = QtWidgets.QLabel(
            "Save template stores a reusable definition only. Apply current structure creates persistent project records and folders from the editor contents."
        )
        distinction.setWordWrap(True)
        distinction.setStyleSheet("color: #56566f;")
        layout.addWidget(distinction)
        self.template_name = QtWidgets.QLineEdit()
        name_row = QtWidgets.QFormLayout(); name_row.addRow("Template name (optional)", self.template_name)
        layout.addLayout(name_row)
        for editor in (self.subjects_edit, self.sessions_edit, self.states_edit):
            editor.textChanged.connect(self._update_summary)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Cancel | QtWidgets.QDialogButtonBox.StandardButton.Apply)
        save_button = buttons.addButton("Save template", QtWidgets.QDialogButtonBox.ButtonRole.ActionRole)
        self.apply_button = buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Apply)
        self.apply_button.setText("Apply current structure")
        save_button.clicked.connect(self._save_template)
        self.apply_button.clicked.connect(self._apply)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.apply_result: dict[str, Any] | None = None
        self._applying = False
        self._update_summary()

    @staticmethod
    def _text_step(editor: QtWidgets.QPlainTextEdit, fields: list[tuple[str, QtWidgets.QWidget]] | None = None, button: QtWidgets.QPushButton | None = None) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget(); layout = QtWidgets.QVBoxLayout(page); layout.addWidget(editor, 1)
        if fields:
            row = QtWidgets.QHBoxLayout()
            for label, widget in fields:
                row.addWidget(QtWidgets.QLabel(label)); row.addWidget(widget)
            if button is not None:
                row.addWidget(button)
            layout.addLayout(row)
        return page

    @staticmethod
    def _lines(editor: QtWidgets.QPlainTextEdit) -> list[str]:
        return list(dict.fromkeys(line.strip() for line in editor.toPlainText().splitlines() if line.strip()))

    def _generate_subjects(self) -> None:
        values = [f"{self.subject_prefix.text()}{index:0{self.subject_padding.value()}d}" for index in range(self.subject_start.value(), self.subject_start.value() + self.subject_count.value())]
        self.subjects_edit.setPlainText("\n".join(values))

    def _generate_states(self) -> None:
        values: list[str] = []
        current = self.state_start.value()
        while current <= self.state_end.value() + self.state_step.value() * 1e-9:
            values.append(f"T{current:g},{current:g},{self.state_unit.text().strip() or 'min'}")
            current += self.state_step.value()
        self.states_edit.setPlainText("\n".join(values))

    def template(self) -> dict[str, Any]:
        states: list[dict[str, Any]] = []
        for line in self._lines(self.states_edit):
            parts = [part.strip() for part in line.split(",")]
            if len(parts) == 1:
                states.append({"display_name": parts[0], "condition_label": self.condition_edit.text().strip(), "timepoint_value": None, "timepoint_unit": self.state_unit.text().strip() or "min", "reference_event": self.reference_edit.text().strip()})
            else:
                states.append({"display_name": parts[0], "condition_label": self.condition_edit.text().strip(), "timepoint_value": float(parts[1]), "timepoint_unit": parts[2] if len(parts) > 2 and parts[2] else (self.state_unit.text().strip() or "min"), "reference_event": self.reference_edit.text().strip()})
        return {
            "subjects": [{"subject_code": value} for value in self._lines(self.subjects_edit)],
            "sessions": [{"session_key": value} for value in self._lines(self.sessions_edit)],
            "states": states,
        }

    def _update_summary(self) -> None:
        try:
            value = self.template()
            n_subjects, n_sessions, n_states = len(value["subjects"]), len(value["sessions"]), len(value["states"])
            if not n_subjects or not n_sessions or not n_states:
                self.summary.setText(
                    f"Current editor: {n_subjects} subjects, {n_sessions} sessions per subject, {n_states} states per session. Complete all three sections before applying."
                )
                return
            plan = self.store.preview_structure_template(value)
            first_target = plan["target_paths"][0] if plan["target_paths"] else ""
            self.summary.setText(
                f"Creation plan: add {plan['subjects_created']} subjects, {plan['sessions_created']} sessions, "
                f"{plan['states_created']} states; reuse {plan['subjects_reused']}/{plan['sessions_reused']}/{plan['states_reused']}. "
                f"Total state records in this template: {n_subjects * n_sessions * n_states}. "
                f"Target: {self.store.paths.root / Path(first_target) if first_target else self.store.paths.subjects}."
            )
        except ValueError as exc:
            self.summary.setText(f"Invalid state row: {exc}")

    def _save_template(self) -> None:
        try:
            value = self.template()
        except ValueError as exc:
            QtWidgets.QMessageBox.warning(self, "Invalid template", str(exc)); return
        name = self.template_name.text().strip()
        if not name:
            QtWidgets.QMessageBox.information(self, "Template name", "Enter a template name before saving."); return
        self.store.save_structure_template(name, value)
        existing_index = self.saved_combo.findText(name)
        if existing_index >= 0:
            self.saved_combo.setItemData(existing_index, {"name": name, "template": value})
            self.saved_combo.setCurrentIndex(existing_index)
        else:
            self.saved_combo.addItem(name, {"name": name, "template": value})
            self.saved_combo.setCurrentIndex(self.saved_combo.count() - 1)
        QtWidgets.QMessageBox.information(
            self,
            "Template saved",
            "The reusable template definition was saved. It has not yet been applied to the project.",
        )

    def _load_saved(self) -> None:
        payload = self.saved_combo.currentData()
        if not isinstance(payload, dict):
            return
        value = payload.get("template", {})
        self.subjects_edit.setPlainText("\n".join(str(item.get("subject_code", "")) for item in value.get("subjects", [])))
        self.sessions_edit.setPlainText("\n".join(str(item.get("session_key", "")) for item in value.get("sessions", [])))
        states = []
        for item in value.get("states", []):
            timepoint = item.get("timepoint_value")
            states.append(str(item.get("display_name", "")) if timepoint is None else f"{item.get('display_name', '')},{timepoint},{item.get('timepoint_unit', 'min')}")
        self.states_edit.setPlainText("\n".join(states))
        if value.get("states"):
            self.condition_edit.setText(str(value["states"][0].get("condition_label", "")))
            self.reference_edit.setText(str(value["states"][0].get("reference_event", "")))
        self.template_name.setText(str(payload.get("name", "")))

    def _apply(self) -> None:
        if self._applying:
            return
        self._applying = True
        self.apply_button.setEnabled(False)
        previous_summary = self.summary.text()
        self.summary.setText("Applying template: creating project records and folders…")
        QtWidgets.QApplication.processEvents()
        try:
            value = self.template()
            if not value["subjects"] or not value["sessions"] or not value["states"]:
                raise ValueError("Subjects, sessions, and states must each contain at least one item")
            plan = self.store.preview_structure_template(value)
            self.about_to_apply.emit()
            self.apply_result = self.store.apply_structure_template(value)
            _append_project_operation_log(
                self.store,
                "apply_structure_template",
                "completed",
                {"plan": plan, "result": self.apply_result},
            )
        except Exception as exc:  # noqa: BLE001 - GUI must report unexpected persistence failures
            log_failure = ""
            try:
                _append_project_operation_log(
                    self.store,
                    "apply_structure_template",
                    "failed",
                    {"error": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc()},
                )
            except Exception as log_exc:  # noqa: BLE001 - preserve both failures for the user
                log_failure = f"\n\nThe technical log could not be written: {type(log_exc).__name__}: {log_exc}"
            self.summary.setText(previous_summary)
            QtWidgets.QMessageBox.warning(
                self,
                "Cannot apply template",
                f"The project structure was not fully applied.\n\n{exc}{log_failure}",
            )
            self._applying = False
            self.apply_button.setEnabled(True)
            return
        self._applying = False
        self.apply_button.setEnabled(True)
        self.accept()


class BatchWorker(QtCore.QObject):
    progress = QtCore.Signal(str, int, int, str, str)
    finished = QtCore.Signal(object)
    failed = QtCore.Signal(str)

    def __init__(self, runner: ProjectBatchRunner, batch_job_id: str) -> None:
        super().__init__()
        self.runner = runner
        self.batch_job_id = batch_job_id
        self.cancel_event = threading.Event()

    @QtCore.Slot()
    def run(self) -> None:
        try:
            result = self.runner.run(self.batch_job_id, progress=self.progress.emit, cancel_event=self.cancel_event)
            self.finished.emit(result)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class ProjectWorkspace(QtWidgets.QMainWindow):
    open_data_unit = QtCore.Signal(str, object)
    queue_data_units = QtCore.Signal(object)
    request_parameter_snapshot = QtCore.Signal()

    def __init__(
        self,
        store: ProjectStore,
        config_path: str | Path,
        metadata_dir: str | Path,
        parent: QtWidgets.QWidget | None = None,
        *,
        mode: str = "manage",
        initial_data_unit_ids: list[str] | None = None,
    ) -> None:
        super().__init__(parent)
        # Project Manager is a normal, non-modal workspace.  It may be raised
        # once when opened from the analysis window, but it must not stay on
        # top of the analysis window or steal focus during background work.
        self.setWindowModality(QtCore.Qt.WindowModality.NonModal)
        self.store = store
        self.config_path = Path(config_path).resolve()
        self.metadata_dir = Path(metadata_dir).resolve()
        self.mode = mode
        self.initial_data_unit_ids = list(dict.fromkeys(initial_data_unit_ids or []))
        self.batch_selected_ids = set(self.initial_data_unit_ids)
        self.batch_thread: QtCore.QThread | None = None
        self.batch_worker: BatchWorker | None = None
        self.batch_task_config: dict[str, Any] = {}
        self.current_comparison_selection: Any = None
        self.current_comparison_second: Any = None
        self.current_comparison_preview = pd.DataFrame()
        self.current_comparison_second_preview = pd.DataFrame()
        self.current_snapshot_analysis_ids: list[str] | None = None
        self.current_snapshot_second_ids: list[str] | None = None
        self._project_draft_dirty = False
        self._project_draft_backup: Path | None = None
        self._project_draft_marker = self.store.paths.logs / "project_draft.json"
        self._project_draft_initial_files: set[str] = set()
        self._project_draft_initial_dirs: set[str] = set()
        self._project_draft_created_files: set[str] = set()
        self._project_draft_created_dirs: set[str] = set()
        self._project_draft_recovery_pending = self._project_draft_marker.is_file()
        self.setAcceptDrops(self.mode == "manage")
        if parent is None:
            self.setFont(QtGui.QFont(_project_font_family(), 9))
        role = {"manage": "Project manager", "batch": "Batch analysis", "compare": "Result comparison", "review": "Result review"}.get(mode, "Project")
        self.setWindowTitle(f"LUNA — {role} — {store.project['name']}")
        self.resize(1480, 900)
        self.setMinimumSize(1050, 680)
        self._build_ui()
        self.refresh_all()
        if self._project_draft_recovery_pending and self.mode == "manage":
            QtCore.QTimer.singleShot(0, self._offer_draft_recovery)

    def _build_ui(self) -> None:
        toolbar = self.addToolBar("Project")
        toolbar.setMovable(False)
        if self.mode == "manage":
            actions = (
                ("Import data", self.import_files),
                ("Save project", self.save_project),
                ("Open in analysis", self.open_selected),
                ("Add to batch", self.add_selected_to_batch),
                ("Structure template", self.open_structure_template),
                ("Edit mapping", self.edit_mapping),
                ("Organize data", self.organize_selected_data),
                ("Refresh", self.refresh_all),
                ("Check duplicate states", self.review_duplicate_states),
            )
        else:
            actions = (("Refresh", self.refresh_all),)
        for text, callback in actions:
            action = toolbar.addAction(text)
            action.triggered.connect(callback)
        self.tabs = QtWidgets.QTabWidget()
        self.setCentralWidget(self.tabs)
        if self.mode == "manage":
            self.tabs.addTab(self._build_data_tab(), "Project data")
        elif self.mode == "batch":
            self.tabs.addTab(self._build_batch_tab(), "Batch analysis")
        elif self.mode == "compare":
            self.tabs.addTab(self._build_compare_tab(), "A / B comparison")
        elif self.mode == "review":
            self.tabs.addTab(self._build_results_tab(), "Review results")
        else:
            raise ValueError(f"Unsupported project workspace mode: {self.mode}")
        self.statusBar().showMessage("Ready")
        if self.mode == "manage":
            self._update_project_draft_ui()
            save_action = QtGui.QAction("Save project", self)
            save_action.setShortcut(QtGui.QKeySequence.StandardKey.Save)
            save_action.triggered.connect(self.save_project)
            self.addAction(save_action)

    def _build_data_tab(self) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)
        project = self.store.project
        header = QtWidgets.QHBoxLayout()
        logo = QtWidgets.QLabel()
        logo.setPixmap(_project_logo_pixmap())
        logo.setFixedSize(180, 50)
        logo.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        logo.setToolTip("LUNA — Local field potential Unified Network Analysis platform")
        header.addWidget(logo)
        self.project_label = QtWidgets.QLabel(f"{project['name']}\n{project['description']}")
        self.project_label.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        self.project_label.setToolTip(str(self.store.paths.root))
        header.addWidget(self.project_label, stretch=1)
        self.project_save_status = QtWidgets.QLabel("已保存")
        self.project_save_status.setStyleSheet("color: #5f6b76;")
        header.addWidget(self.project_save_status)
        layout.addLayout(header)
        row = QtWidgets.QHBoxLayout()
        for text, callback in (
            ("Add subject", self.add_subject),
            ("Add session", self.add_session),
            ("Add state", self.add_state),
            ("Edit selected", self.edit_selected_hierarchy),
            ("Apply template", self.open_structure_template),
            ("Add to batch", self.add_selected_to_batch),
            ("Relocate source", self.relocate_selected_source),
            ("Previous data", lambda: self.open_adjacent(-1)),
            ("Next data", lambda: self.open_adjacent(1)),
        ):
            button = QtWidgets.QPushButton(text)
            button.clicked.connect(callback)
            row.addWidget(button)
        row.addStretch(1)
        layout.addLayout(row)
        splitter = QtWidgets.QSplitter()
        self.hierarchy = QtWidgets.QTreeWidget()
        self.hierarchy.setHeaderLabels(["Project hierarchy"])
        self.hierarchy.setMinimumWidth(320)
        self.hierarchy.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.hierarchy.customContextMenuRequested.connect(self._hierarchy_context_menu)
        self.hierarchy.itemDoubleClicked.connect(lambda _item, _column: self.open_selected())
        splitter.addWidget(self.hierarchy)
        self.data_table = QtWidgets.QTableWidget()
        self.data_table.setColumnCount(11)
        self.data_table.setHorizontalHeaderLabels(["Use", "Subject", "Group", "Session", "State", "Condition", "Timepoint", "File", "Validity", "Module status", "data_unit_id"])
        self.data_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.data_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.data_table.horizontalHeader().setSectionResizeMode(7, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.data_table.doubleClicked.connect(self.open_selected)
        self.data_table.setColumnHidden(10, True)
        splitter.addWidget(self.data_table)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, stretch=1)
        self.state_resources_label = QtWidgets.QLabel("选择状态后查看电生理、行为附件和评分摘要。")
        self.state_resources_label.setWordWrap(True)
        self.state_resources_label.setStyleSheet("color: #5f6b76;")
        self.state_resources_label.setToolTip("行为数据与同步信息仅作为可追溯元数据保存；不根据同名文件推断同步关系。")
        layout.addWidget(self.state_resources_label)
        self.hierarchy.currentItemChanged.connect(lambda _current, _previous: self._refresh_state_resources())
        return widget

    def _project_content_snapshot(self) -> tuple[set[str], set[str]]:
        files: set[str] = set()
        directories: set[str] = set()
        for root in (self.store.paths.raw_data, self.store.paths.subjects):
            if not root.exists():
                continue
            directories.update(path.relative_to(self.store.paths.root).as_posix() for path in root.rglob("*") if path.is_dir())
            files.update(path.relative_to(self.store.paths.root).as_posix() for path in root.rglob("*") if path.is_file())
        return files, directories

    def _write_project_draft_marker(self) -> None:
        if self._project_draft_backup is None:
            return
        self._project_draft_marker.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 1,
            "created_at_utc": utc_now(),
            "backup_path": str(self._project_draft_backup),
            "initial_files": sorted(self._project_draft_initial_files),
            "initial_dirs": sorted(self._project_draft_initial_dirs),
            "created_files": sorted(self._project_draft_created_files),
            "created_dirs": sorted(self._project_draft_created_dirs),
        }
        self._project_draft_marker.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _begin_project_edit(self, *_args: Any) -> None:
        """Start a recoverable Project Manager draft before a mutating action."""
        if self.mode != "manage" or self._project_draft_dirty:
            return
        backup_dir = self.store.paths.logs / "backups"
        backup_path = backup_dir / f"project-draft-{uuid.uuid4().hex}.sqlite3"
        initial_files, initial_dirs = self._project_content_snapshot()
        self.store.backup_database(backup_path)
        self._project_draft_backup = backup_path
        self._project_draft_initial_files = initial_files
        self._project_draft_initial_dirs = initial_dirs
        self._project_draft_created_files = set()
        self._project_draft_created_dirs = set()
        self._project_draft_dirty = True
        self._write_project_draft_marker()
        _append_project_operation_log(self.store, "project_draft", "started", {"backup_path": str(backup_path)})
        self._update_project_draft_ui()

    def _record_project_content_changes(self) -> None:
        if not self._project_draft_dirty:
            return
        files, directories = self._project_content_snapshot()
        self._project_draft_created_files.update(files - self._project_draft_initial_files)
        self._project_draft_created_dirs.update(directories - self._project_draft_initial_dirs)
        self._write_project_draft_marker()

    def _update_project_draft_ui(self) -> None:
        if self.mode != "manage":
            return
        dirty = bool(self._project_draft_dirty)
        if hasattr(self, "project_save_status"):
            self.project_save_status.setText("★ 有未保存更改" if dirty else "已保存")
            self.project_save_status.setStyleSheet("color: #b42318; font-weight: 600;" if dirty else "color: #5f6b76;")
            self.project_save_status.setToolTip("项目结构、导入归属和元数据尚未正式保存。" if dirty else "项目结构和导入归属已保存。")
        for action in self.findChildren(QtGui.QAction):
            if action.text() == "Save project":
                action.setEnabled(dirty)
        self.statusBar().showMessage("有未保存项目更改" if dirty else "Project saved", 4000)

    def _validate_project_draft(self) -> None:
        """Check references before formalizing a Project Manager draft."""
        for unit in self.store.data_units():
            if str(unit.get("source_path_kind") or "") == "project_relative" and not self.store.resolve_source_path(unit).is_file():
                raise FileNotFoundError(f"Imported project file is missing: {unit.get('source_path')}")
        for row in (*self.store.subjects(), *self.store.sessions(), *self.store.state_records()):
            relative = str(row.get("relative_path") or "")
            if relative and not (self.store.paths.root / Path(relative)).is_dir():
                raise FileNotFoundError(f"Hierarchy directory is missing: {relative}")

    def save_project(self) -> bool:
        if self.mode != "manage":
            return True
        if not self._project_draft_dirty:
            self.statusBar().showMessage("没有需要保存的项目更改。", 5000)
            return True
        try:
            self._validate_project_draft()
            self._record_project_content_changes()
            backup = self._project_draft_backup
            if self._project_draft_marker.exists():
                self._project_draft_marker.unlink()
            if backup is not None and backup.exists():
                backup.unlink()
            self._project_draft_backup = None
            self._project_draft_dirty = False
            _append_project_operation_log(self.store, "project_save", "completed", {"saved_at_utc": utc_now()})
            self._update_project_draft_ui()
            self.statusBar().showMessage(f"项目已保存：{utc_now()}", 10000)
            return True
        except Exception as exc:  # noqa: BLE001 - retain draft for retry
            _append_project_operation_log(self.store, "project_save", "failed", {"error": f"{type(exc).__name__}: {exc}"})
            QtWidgets.QMessageBox.warning(self, "项目保存失败", f"项目更改仍保留在当前草稿中，可修复后重试。\n\n{exc}")
            return False

    def _cleanup_project_draft_files(self) -> None:
        for relative in sorted(self._project_draft_created_files, key=len, reverse=True):
            target = (self.store.paths.root / Path(relative)).resolve()
            try:
                target.relative_to(self.store.paths.root)
            except ValueError:
                continue
            if target.is_file():
                try:
                    target.chmod(0o666)
                    target.unlink()
                except OSError:
                    pass
        for relative in sorted(self._project_draft_created_dirs, key=len, reverse=True):
            target = (self.store.paths.root / Path(relative)).resolve()
            try:
                target.relative_to(self.store.paths.root)
                target.rmdir()
            except (OSError, ValueError):
                pass

    def discard_project_changes(self) -> bool:
        if not self._project_draft_dirty:
            return True
        backup = self._project_draft_backup
        if backup is None or not backup.is_file():
            QtWidgets.QMessageBox.warning(self, "放弃项目更改失败", "找不到项目草稿备份，当前更改未被放弃。")
            return False
        try:
            self.store.restore_database_backup(backup)
            self._cleanup_project_draft_files()
            if self._project_draft_marker.exists():
                self._project_draft_marker.unlink()
            backup.unlink(missing_ok=True)
            _append_project_operation_log(self.store, "project_discard", "completed", {})
            self._project_draft_backup = None
            self._project_draft_dirty = False
            self._project_draft_created_files.clear()
            self._project_draft_created_dirs.clear()
            self.refresh_all()
            self._update_project_draft_ui()
            return True
        except Exception as exc:  # noqa: BLE001
            _append_project_operation_log(self.store, "project_discard", "failed", {"error": f"{type(exc).__name__}: {exc}"})
            QtWidgets.QMessageBox.warning(self, "放弃项目更改失败", str(exc))
            return False

    def _offer_draft_recovery(self) -> None:
        if not self._project_draft_marker.is_file():
            return
        try:
            payload = json.loads(self._project_draft_marker.read_text(encoding="utf-8"))
            backup = Path(str(payload.get("backup_path", ""))).expanduser().resolve()
            if not backup.is_file():
                self._project_draft_marker.unlink(missing_ok=True)
                return
            answer = QtWidgets.QMessageBox.question(
                self,
                "发现未保存项目草稿",
                "上次项目管理窗口可能异常退出，发现未保存草稿。\n\n恢复草稿继续编辑，还是放弃并恢复正式保存状态？",
                QtWidgets.QMessageBox.StandardButton.RestoreDefaults | QtWidgets.QMessageBox.StandardButton.Discard | QtWidgets.QMessageBox.StandardButton.Cancel,
                QtWidgets.QMessageBox.StandardButton.RestoreDefaults,
            )
            if answer == QtWidgets.QMessageBox.StandardButton.Discard:
                self._project_draft_backup = backup
                self._project_draft_dirty = True
                self._project_draft_created_files = set(map(str, payload.get("created_files", [])))
                self._project_draft_created_dirs = set(map(str, payload.get("created_dirs", [])))
                self.discard_project_changes()
            elif answer == QtWidgets.QMessageBox.StandardButton.RestoreDefaults:
                self._project_draft_backup = backup
                self._project_draft_dirty = True
                self._project_draft_initial_files = set(map(str, payload.get("initial_files", [])))
                self._project_draft_initial_dirs = set(map(str, payload.get("initial_dirs", [])))
                self._project_draft_created_files = set(map(str, payload.get("created_files", [])))
                self._project_draft_created_dirs = set(map(str, payload.get("created_dirs", [])))
                self._update_project_draft_ui()
                self.statusBar().showMessage("已恢复未保存项目草稿；点击 Save project 正式保存。", 10000)
        except Exception as exc:  # noqa: BLE001
            self.statusBar().showMessage(f"未保存草稿恢复失败：{exc}", 10000)

    def _refresh_state_resources(self) -> None:
        if not hasattr(self, "state_resources_label"):
            return
        state_id = self._selected_hierarchy("state")
        if not state_id:
            self.state_resources_label.setText("选择状态后查看电生理、行为附件和评分摘要。")
            return
        attachments = self.store.behavior_attachments(state_id)
        scores = self.store.behavior_scores(state_id)
        syncs = self.store.synchronization_records(state_id)
        lfp_count = sum(1 for unit in self.store.data_units() if str(unit.get("state_record_id")) == state_id)
        score_text = "未录入评分" if not scores else f"评分 {len(scores)} 项（0 分与缺失值分开保存）"
        sync_text = "未确认同步" if not syncs else f"同步记录 {len(syncs)} 条（是否确认：{sum(int(row['confirmed']) for row in syncs)}/{len(syncs)}）"
        self.state_resources_label.setText(
            f"状态资源：LFP 数据 {lfp_count} 条；行为附件 {len(attachments)}；{score_text}；{sync_text}。"
        )

    def _build_batch_tab(self) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)
        layout.addWidget(QtWidgets.QLabel("1. Select data → 2. Select modules and parameters → 3. Preview frozen tasks → 4. Run. Inspection decisions remain data-specific."))
        filter_row = QtWidgets.QHBoxLayout()
        self.batch_search = QtWidgets.QLineEdit(); self.batch_search.setPlaceholderText("Search subject, session, condition, state, or file")
        self.batch_search.textChanged.connect(self._refresh_batch_data_selector)
        self.batch_checked_only = QtWidgets.QCheckBox("Checked data only")
        self.batch_checked_only.setChecked(True)
        self.batch_checked_only.toggled.connect(self._refresh_batch_data_selector)
        select_visible = QtWidgets.QPushButton("Select filtered")
        select_visible.clicked.connect(lambda: self._set_batch_visible_checked(True))
        clear_selection = QtWidgets.QPushButton("Clear selection")
        clear_selection.clicked.connect(lambda: self._set_batch_visible_checked(False))
        filter_row.addWidget(self.batch_search, 1); filter_row.addWidget(self.batch_checked_only); filter_row.addWidget(select_visible); filter_row.addWidget(clear_selection)
        layout.addLayout(filter_row)
        self.batch_data_table = QtWidgets.QTableWidget(0, 9)
        self.batch_data_table.setHorizontalHeaderLabels(["Use", "Subject", "Session", "State", "Condition", "Timepoint", "Inspection", "Source", "data_unit_id"])
        self.batch_data_table.setColumnHidden(8, True)
        self.batch_data_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.batch_data_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.batch_data_table.itemChanged.connect(self._update_batch_selection_label)
        for column in range(1, 7):
            self.batch_data_table.horizontalHeader().setSectionResizeMode(column, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.batch_data_table.horizontalHeader().setSectionResizeMode(7, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.batch_data_table.setMaximumHeight(260)
        layout.addWidget(self.batch_data_table)
        self.batch_selection_label = QtWidgets.QLabel("0 data units selected")
        layout.addWidget(self.batch_selection_label)
        module_box = QtWidgets.QGroupBox("Modules")
        module_layout = QtWidgets.QGridLayout(module_box)
        self.module_checks: dict[str, QtWidgets.QCheckBox] = {}
        for index, module in enumerate(MODULE_TO_INDICATORS):
            check = QtWidgets.QCheckBox(module)
            check.setChecked(module in {"Quality", "PSD", "Band Power"})
            self.module_checks[module] = check
            module_layout.addWidget(check, index // 4, index % 4)
        layout.addWidget(module_box)
        control = QtWidgets.QGridLayout()
        control.setHorizontalSpacing(8)
        control.setVerticalSpacing(6)
        self.batch_mode = QtWidgets.QComboBox()
        self.batch_mode.addItems(["Calculate missing/outdated", "Recalculate selected"])
        control.addWidget(QtWidgets.QLabel("Run mode"), 0, 0)
        control.addWidget(self.batch_mode, 0, 1, 1, 2)
        self.batch_settings = QtWidgets.QPushButton("View effective parameters")
        self.batch_settings.clicked.connect(self.edit_batch_task_config)
        control.addWidget(self.batch_settings, 0, 3)
        edit_current = QtWidgets.QPushButton("Edit parameters in analysis panel")
        edit_current.setToolTip("Return to the main analysis window and edit the existing per-module parameter controls; then copy the values back into this batch.")
        edit_current.clicked.connect(self._focus_main_parameter_panel)
        control.addWidget(edit_current, 0, 4, 1, 2)
        copy_current = QtWidgets.QPushButton("Use current single-file parameters")
        copy_current.setToolTip("The main analysis window supplies its current calculation parameters. Channel and epoch inspection decisions are not copied.")
        copy_current.clicked.connect(self._request_current_parameters)
        control.addWidget(copy_current, 0, 6, 1, 2)
        save_scheme = QtWidgets.QPushButton("Save parameter scheme")
        save_scheme.clicked.connect(self._save_batch_parameter_scheme)
        load_scheme = QtWidgets.QPushButton("Load parameter scheme")
        load_scheme.clicked.connect(self._load_batch_parameter_scheme)
        control.addWidget(save_scheme, 1, 0, 1, 2)
        control.addWidget(load_scheme, 1, 2, 1, 2)
        self.batch_start = QtWidgets.QPushButton("Run selected data units")
        self.batch_start.clicked.connect(self.start_batch)
        control.addWidget(self.batch_start, 1, 4, 1, 2)
        self.batch_stop = QtWidgets.QPushButton("Stop")
        self.batch_stop.setEnabled(False)
        self.batch_stop.clicked.connect(self.stop_batch)
        control.addWidget(self.batch_stop, 1, 6)
        self.batch_resume = QtWidgets.QPushButton("Resume latest interrupted")
        self.batch_resume.clicked.connect(self.resume_latest_batch)
        control.addWidget(self.batch_resume, 1, 7)
        control.setColumnStretch(8, 1)
        layout.addLayout(control)
        self.batch_progress = QtWidgets.QProgressBar()
        layout.addWidget(self.batch_progress)
        self.batch_table = QtWidgets.QTableWidget()
        self.batch_table.setColumnCount(6)
        self.batch_table.setHorizontalHeaderLabels(["Job", "Status", "Data unit", "Item status", "Started", "Error"])
        self.batch_table.horizontalHeader().setSectionResizeMode(5, QtWidgets.QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.batch_table, stretch=1)
        return widget

    def _build_results_tab(self) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)
        row = QtWidgets.QHBoxLayout()
        for text, status in (("Mark approved", "approved"), ("Mark excluded", "excluded"), ("Reset to pending", "pending")):
            button = QtWidgets.QPushButton(text)
            button.clicked.connect(lambda _checked=False, value=status: self.set_review(value))
            row.addWidget(button)
        row.addStretch(1)
        layout.addLayout(row)
        self.results_table = QtWidgets.QTableWidget()
        self.results_table.setColumnCount(12)
        self.results_table.setHorizontalHeaderLabels(["Subject", "Session", "State", "Module", "Method", "Calculation", "Saved", "Validity", "Review", "Created", "analysis_id", "Path"])
        self.results_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.results_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.results_table.horizontalHeader().setSectionResizeMode(11, QtWidgets.QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.results_table)
        return widget

    def _request_current_parameters(self) -> None:
        self.request_parameter_snapshot.emit()

    def _focus_main_parameter_panel(self) -> None:
        main = self.parentWidget()
        if main is None:
            QtWidgets.QMessageBox.information(self, "Analysis parameters", "Open this batch window from the main LUNA analysis window to edit its calculation controls.")
            return
        main.showNormal()
        main.raise_()
        main.activateWindow()
        self.statusBar().showMessage("Edit calculation parameters in the main analysis panel, then click ‘Use current single-file parameters’. Inspection decisions stay data-specific.", 10000)

    def set_batch_task_config(self, values: dict[str, Any]) -> None:
        self.batch_task_config = json.loads(json.dumps(values))
        if hasattr(self, "batch_settings"):
            self.batch_settings.setText("Effective parameters (copied)")
        self.statusBar().showMessage("Current single-file calculation parameters copied. Data-specific inspection decisions were not copied.", 8000)

    def _build_compare_tab(self) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)
        controls = QtWidgets.QGridLayout()
        self.compare_session = QtWidgets.QComboBox()
        self.compare_specific_session = QtWidgets.QComboBox()
        self.compare_specific_session.addItem("All matching sessions", "")
        self.compare_subject = QtWidgets.QComboBox()
        self.compare_subject.addItem("All subjects", "")
        self.compare_group = QtWidgets.QComboBox()
        self.compare_condition = QtWidgets.QComboBox()
        self.compare_timepoint = QtWidgets.QDoubleSpinBox()
        self.compare_timepoint.setRange(-100000, 100000)
        self.compare_timepoint.setDecimals(3)
        self.compare_time_range = QtWidgets.QCheckBox("Timepoint range")
        self.compare_time_min = QtWidgets.QDoubleSpinBox()
        self.compare_time_max = QtWidgets.QDoubleSpinBox()
        for control in (self.compare_time_min, self.compare_time_max):
            control.setRange(-100000, 100000)
            control.setDecimals(3)
            control.setEnabled(False)
        self.compare_time_max.setValue(180.0)
        self.compare_time_range.toggled.connect(self.compare_time_min.setEnabled)
        self.compare_time_range.toggled.connect(self.compare_time_max.setEnabled)
        self.compare_time_range.toggled.connect(lambda checked: self.compare_timepoint.setEnabled(not checked))
        self.compare_time_range.toggled.connect(lambda checked: self.compare_paired.setChecked(False) if checked else None)
        self.compare_paired = QtWidgets.QCheckBox("Enable B group / paired comparison")
        self.compare_paired.setChecked(True)
        self.compare_second_timepoint = QtWidgets.QDoubleSpinBox()
        self.compare_second_timepoint.setRange(-100000, 100000)
        self.compare_second_timepoint.setDecimals(3)
        self.compare_second_timepoint.setEnabled(False)
        self.compare_paired.toggled.connect(self.compare_second_timepoint.setEnabled)
        self.compare_b_group = QtWidgets.QComboBox()
        self.compare_b_subject = QtWidgets.QComboBox(); self.compare_b_subject.addItem("All subjects", "")
        self.compare_b_session = QtWidgets.QComboBox()
        self.compare_b_condition = QtWidgets.QComboBox()
        copy_a = QtWidgets.QPushButton("Copy A settings to B")
        copy_a.clicked.connect(self._copy_compare_a_to_b)
        self.compare_module = QtWidgets.QComboBox()
        self.compare_module.addItems(["PSD", "Band Power", "FOOOF", "Connectivity", "Time Delay", "Quality"])
        self.compare_view = QtWidgets.QComboBox()
        self.compare_view.addItem("Subject summary")
        self.compare_view.currentTextChanged.connect(
            lambda _text: self._plot_comparison(self.current_comparison_selection)
            if self.current_comparison_selection is not None
            else None
        )
        self.compare_module.currentTextChanged.connect(self._refresh_compare_views)
        self.compare_band = QtWidgets.QComboBox()
        self.compare_band.addItem("All")
        self.compare_band.currentTextChanged.connect(
            lambda _text: self._plot_comparison(self.current_comparison_selection)
            if self.current_comparison_selection is not None
            else None
        )
        self.compare_metric = QtWidgets.QComboBox()
        self.compare_metric.addItem("All")
        self.compare_metric.currentTextChanged.connect(
            lambda _text: self._plot_comparison(self.current_comparison_selection)
            if self.current_comparison_selection is not None
            else None
        )
        self.compare_dimension = QtWidgets.QComboBox()
        self.compare_dimension.addItems(["All", "Channel", "Region", "Region pair"])
        self.compare_target = QtWidgets.QComboBox()
        self.compare_target.addItem("All")
        self.compare_dimension.currentTextChanged.connect(
            lambda _text: self._refresh_compare_targets(self.current_comparison_selection)
            if self.current_comparison_selection is not None
            else None
        )
        self.compare_target.currentTextChanged.connect(
            lambda _text: self._plot_comparison(self.current_comparison_selection)
            if self.current_comparison_selection is not None
            else None
        )
        self.compare_pending = QtWidgets.QCheckBox("Include pending review (exploratory)")
        self.compare_refresh = QtWidgets.QPushButton("Preview matching results")
        self.compare_refresh.clicked.connect(self._refresh_comparison_from_controls)
        self.compare_queue_missing = QtWidgets.QPushButton("Add missing results to batch")
        self.compare_queue_missing.setToolTip("Adds matching data units without a saved compatible result to the batch queue. It does not calculate during comparison.")
        self.compare_queue_missing.clicked.connect(self._queue_missing_comparison_data)
        for column, (label, control) in enumerate((("Group", self.compare_group), ("Session key", self.compare_session), ("Condition", self.compare_condition), ("Timepoint", self.compare_timepoint), ("Module", self.compare_module), ("Metric/method", self.compare_metric), ("Band", self.compare_band))):
            controls.addWidget(QtWidgets.QLabel(label), 0, column)
            controls.addWidget(control, 1, column)
        controls.addWidget(self.compare_pending, 2, 4, 1, 2)
        controls.addWidget(self.compare_refresh, 2, 6)
        controls.addWidget(self.compare_queue_missing, 7, 4, 1, 2)
        self.compare_save = QtWidgets.QPushButton("Save comparison snapshot")
        self.compare_save.clicked.connect(self.save_comparison)
        controls.addWidget(self.compare_save, 2, 0, 1, 2)
        self.compare_export = QtWidgets.QPushButton("Export preview CSV")
        self.compare_export.clicked.connect(self.export_comparison)
        controls.addWidget(self.compare_export, 2, 2, 1, 2)
        self.compare_load = QtWidgets.QPushButton("Load saved comparison")
        self.compare_load.clicked.connect(self.load_comparison)
        controls.addWidget(self.compare_load, 3, 0, 1, 2)
        controls.addWidget(self.compare_paired, 3, 2)
        controls.addWidget(QtWidgets.QLabel("Target level"), 3, 4)
        controls.addWidget(self.compare_dimension, 3, 5)
        controls.addWidget(self.compare_target, 3, 6)
        controls.addWidget(QtWidgets.QLabel("Specific session"), 4, 0)
        controls.addWidget(self.compare_specific_session, 4, 1, 1, 3)
        controls.addWidget(self.compare_time_range, 4, 4)
        controls.addWidget(self.compare_time_min, 4, 5)
        controls.addWidget(self.compare_time_max, 4, 6)
        controls.addWidget(QtWidgets.QLabel("Subject"), 5, 0)
        controls.addWidget(self.compare_subject, 5, 1, 1, 3)
        controls.addWidget(QtWidgets.QLabel("View"), 5, 4)
        controls.addWidget(self.compare_view, 5, 5, 1, 2)
        controls.addWidget(QtWidgets.QLabel("B group"), 6, 0)
        controls.addWidget(self.compare_b_group, 6, 1)
        controls.addWidget(QtWidgets.QLabel("B subject"), 6, 2)
        controls.addWidget(self.compare_b_subject, 6, 3)
        controls.addWidget(QtWidgets.QLabel("B session"), 6, 4)
        controls.addWidget(self.compare_b_session, 6, 5)
        controls.addWidget(QtWidgets.QLabel("B condition"), 6, 6)
        controls.addWidget(self.compare_b_condition, 7, 6)
        controls.addWidget(copy_a, 7, 0, 1, 2)
        controls.addWidget(QtWidgets.QLabel("B timepoint"), 7, 2)
        controls.addWidget(self.compare_second_timepoint, 7, 3)
        self.compare_session.currentTextChanged.connect(self._refresh_specific_sessions)
        layout.addLayout(controls)
        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        self.compare_table = QtWidgets.QTableWidget()
        self.compare_table.setColumnCount(16)
        self.compare_table.setHorizontalHeaderLabels([
            "Subject", "Group", "A session", "A condition/time", "A file", "A effective samples", "A status", "A result",
            "B session", "B condition/time", "B file", "B effective samples", "B status", "B result", "Reason", "Compatibility",
        ])
        self.compare_table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Interactive)
        self.compare_table.horizontalHeader().setSectionResizeMode(14, QtWidgets.QHeaderView.ResizeMode.Stretch)
        for column in (4, 10):
            self.compare_table.setColumnWidth(column, 170)
        for column in (7, 13):
            self.compare_table.setColumnWidth(column, 155)
        splitter.addWidget(self.compare_table)
        self.compare_figure = Figure(figsize=(10, 4), layout="constrained")
        self.compare_canvas = FigureCanvasQTAgg(self.compare_figure)
        splitter.addWidget(self.compare_canvas)
        splitter.setSizes([280, 420])
        layout.addWidget(splitter, stretch=1)
        return widget

    def _queue_missing_comparison_data(self) -> None:
        filters = [self._comparison_filters()]
        if self.compare_paired.isChecked():
            filters.append({
                **filters[0],
                "group_label": str(self.compare_b_group.currentData() or ""),
                "subject_id": str(self.compare_b_subject.currentData() or ""),
                "session_key": self.compare_b_session.currentText(),
                "condition_label": self.compare_b_condition.currentText(),
                "timepoint_value": self.compare_second_timepoint.value(),
                "timepoint_min": None, "timepoint_max": None,
            })
        module = self.compare_module.currentText()
        available = {
            (row["data_unit_id"], row["module_name"])
            for row in self.store.analysis_results({
                "active": 1,
                "calculation_status": "completed",
                "save_status": "saved",
                "result_validity": "current",
            })
        }
        identifiers: list[str] = []
        for unit in self.store.data_units():
            for current in filters:
                if current.get("subject_id") and unit["subject_id"] != current["subject_id"]:
                    continue
                if current.get("group_label") and str(unit.get("group_label") or "") != current["group_label"]:
                    continue
                if current.get("session_key") and unit["session_key"] != current["session_key"]:
                    continue
                if current.get("condition_label") and str(unit.get("condition_label") or "") != current["condition_label"]:
                    continue
                if current.get("timepoint_value") is not None and unit.get("timepoint_value") != current["timepoint_value"]:
                    continue
                if (unit["data_unit_id"], module) not in available:
                    identifiers.append(unit["data_unit_id"])
        identifiers = list(dict.fromkeys(identifiers))
        if not identifiers:
            QtWidgets.QMessageBox.information(self, "Batch queue", "No matching data unit with a missing saved result was found.")
            return
        self.queue_data_units.emit(identifiers)
        self.statusBar().showMessage(f"Added {len(identifiers)} data units with missing {module} results to the batch queue.", 8000)

    def _copy_compare_a_to_b(self) -> None:
        for source, target in (
            (self.compare_group, self.compare_b_group),
            (self.compare_subject, self.compare_b_subject),
            (self.compare_session, self.compare_b_session),
            (self.compare_condition, self.compare_b_condition),
        ):
            data = source.currentData()
            index = target.findData(data) if data is not None else -1
            if index < 0:
                index = target.findText(source.currentText())
            target.setCurrentIndex(max(0, index))
        self.compare_second_timepoint.setValue(self.compare_timepoint.value())

    def _refresh_compare_views(self) -> None:
        current = self.compare_view.currentText()
        values = ["Subject summary"]
        if self.compare_module.currentText() == "Connectivity":
            values.extend(["Connection spectrum", "Region matrices"])
        with QtCore.QSignalBlocker(self.compare_view):
            self.compare_view.clear()
            self.compare_view.addItems(values)
            self.compare_view.setCurrentText(current if current in values else values[0])

    def refresh_all(self) -> None:
        if hasattr(self, "hierarchy"):
            self._refresh_hierarchy()
        if hasattr(self, "data_table"):
            self._refresh_data_table()
        if hasattr(self, "batch_data_table"):
            self._refresh_batch_data_selector()
            self._refresh_batch_table()
        if hasattr(self, "results_table"):
            self._refresh_results_table()
        if hasattr(self, "compare_group"):
            self._refresh_compare_filters()
        if hasattr(self, "state_resources_label"):
            self._refresh_state_resources()

    def _refresh_hierarchy(self) -> None:
        expanded: set[tuple[str, str]] = set()
        selected: tuple[str, str] | None = None
        if self.hierarchy.topLevelItemCount():
            iterator = QtWidgets.QTreeWidgetItemIterator(self.hierarchy)
            while iterator.value() is not None:
                item = iterator.value()
                identity = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
                if isinstance(identity, tuple) and len(identity) == 2:
                    stable_identity = (str(identity[0]), str(identity[1]))
                    if item.isExpanded():
                        expanded.add(stable_identity)
                    if item is self.hierarchy.currentItem():
                        selected = stable_identity
                iterator += 1
        self.hierarchy.clear()
        units = self.store.data_units()
        by_state: dict[str, list[dict[str, Any]]] = {}
        for unit in units:
            by_state.setdefault(str(unit["state_record_id"]), []).append(unit)
        root = QtWidgets.QTreeWidgetItem([self.store.project["name"]])
        root.setData(0, QtCore.Qt.ItemDataRole.UserRole, ("project", self.store.project["project_id"]))
        root.setToolTip(0, str(self.store.paths.root))
        self.hierarchy.addTopLevelItem(root)
        for subject in self.store.subjects():
            subject_sessions = self.store.sessions(subject["subject_id"])
            subject_item = QtWidgets.QTreeWidgetItem([f"{subject['subject_code']}  ({len(subject_sessions)} sessions)"])
            subject_item.setData(0, QtCore.Qt.ItemDataRole.UserRole, ("subject", subject["subject_id"]))
            if subject.get("relative_path"):
                subject_item.setToolTip(0, str(self.store.paths.root / Path(subject["relative_path"])))
            root.addChild(subject_item)
            for session in subject_sessions:
                session_states = self.store.state_records(session["session_id"])
                session_item = QtWidgets.QTreeWidgetItem([f"{session['session_key']}  ({len(session_states)} states)"])
                session_item.setData(0, QtCore.Qt.ItemDataRole.UserRole, ("session", session["session_id"]))
                if session.get("relative_path"):
                    session_item.setToolTip(0, str(self.store.paths.root / Path(session["relative_path"])))
                subject_item.addChild(session_item)
                for state in session_states:
                    state_units = by_state.get(str(state["state_record_id"]), [])
                    if not state_units:
                        status = "未导入数据"
                    elif all(str(unit.get("inspection_status")) == "checked" for unit in state_units):
                        status = "已检查"
                    else:
                        status = "待检查"
                    state_item = QtWidgets.QTreeWidgetItem([f"{state['display_name']}  ({len(state_units)} data; {status})"])
                    state_item.setData(0, QtCore.Qt.ItemDataRole.UserRole, ("state", state["state_record_id"]))
                    if state.get("relative_path"):
                        state_item.setToolTip(0, str(self.store.paths.root / Path(state["relative_path"])))
                    session_item.addChild(state_item)
                    for unit in state_units:
                        inspection_labels = {
                            "unchecked": "待检查",
                            "in_progress": "检查中",
                            "checked": "已检查",
                            "needs_review": "需复核",
                        }
                        inspection_status = inspection_labels.get(str(unit.get("inspection_status") or "unchecked"), str(unit.get("inspection_status") or "待检查"))
                        file_name = Path(str(unit.get("source_path") or "")).name
                        data_item = QtWidgets.QTreeWidgetItem([f"{file_name}  [{inspection_status}]"])
                        data_item.setData(0, QtCore.Qt.ItemDataRole.UserRole, ("data", unit["data_unit_id"]))
                        data_item.setToolTip(
                            0,
                            f"dataset_id: {unit['data_unit_id']}\n"
                            f"Project path: {unit.get('source_path', '')}\n"
                            f"Inspection revision: {int(unit.get('inspection_revision') or 0)}",
                        )
                        state_item.addChild(data_item)
        root.setExpanded(True)
        iterator = QtWidgets.QTreeWidgetItemIterator(self.hierarchy)
        while iterator.value() is not None:
            item = iterator.value()
            identity = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
            stable_identity = (str(identity[0]), str(identity[1])) if isinstance(identity, tuple) and len(identity) == 2 else None
            if stable_identity in expanded:
                item.setExpanded(True)
            if stable_identity == selected:
                self.hierarchy.setCurrentItem(item)
            iterator += 1

    def _reveal_hierarchy_nodes(self, stable_ids: list[str]) -> None:
        """Expand and focus persisted nodes created or reused by an operation."""
        wanted = set(stable_ids)
        first_match: QtWidgets.QTreeWidgetItem | None = None
        iterator = QtWidgets.QTreeWidgetItemIterator(self.hierarchy)
        while iterator.value() is not None:
            item = iterator.value()
            identity = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
            if isinstance(identity, tuple) and len(identity) == 2 and str(identity[1]) in wanted:
                parent = item.parent()
                while parent is not None:
                    parent.setExpanded(True)
                    parent = parent.parent()
                if first_match is None:
                    first_match = item
            iterator += 1
        if first_match is not None:
            self.hierarchy.setCurrentItem(first_match)
            self.hierarchy.scrollToItem(first_match, QtWidgets.QAbstractItemView.ScrollHint.PositionAtCenter)

    def _refresh_data_table(self) -> None:
        units = self.store.data_units()
        status_by_data: dict[str, list[str]] = {}
        for result in self.store.analysis_results({"active": 1}):
            status_by_data.setdefault(str(result["data_unit_id"]), []).append(
                f"{result['module_name']}: {result['calculation_status']}/{result['save_status']}/"
                f"{result.get('result_validity', 'current')}/{result['review_status']}"
            )
        self.data_table.setRowCount(len(units))
        for row, unit in enumerate(units):
            use = QtWidgets.QTableWidgetItem()
            use.setFlags(use.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
            use.setCheckState(QtCore.Qt.CheckState.Checked)
            self.data_table.setItem(row, 0, use)
            statuses = status_by_data.get(str(unit["data_unit_id"]), [])
            validity = f"inspection={unit.get('inspection_status', 'unchecked')}; data={unit['validity_status']}; import={unit.get('import_status', 'ready')}"
            values = [unit["subject_code"], unit.get("group_label", ""), unit["session_key"], unit["state_display_name"], unit.get("condition_label", ""), "" if unit.get("timepoint_value") is None else f"{unit['timepoint_value']:g} {unit.get('timepoint_unit') or ''}", Path(unit["source_path"]).name, validity, "; ".join(statuses) if statuses else "not run", unit["data_unit_id"]]
            for column, value in enumerate(values, 1):
                item = QtWidgets.QTableWidgetItem(str(value or ""))
                if column == 7:
                    item.setToolTip(unit["source_path"])
                elif column == 9:
                    item.setToolTip("\n".join(statuses) if statuses else "No active result")
                self.data_table.setItem(row, column, item)
        self.data_table.resizeColumnsToContents()
        self.data_table.horizontalHeader().setSectionResizeMode(7, QtWidgets.QHeaderView.ResizeMode.Stretch)

    def _selected_data_unit_ids(self) -> list[str]:
        table = self.batch_data_table if hasattr(self, "batch_data_table") else self.data_table
        id_column = 8 if table is getattr(self, "batch_data_table", None) else 10
        visible = {
            table.item(row, id_column).text()
            for row in range(table.rowCount())
            if table.item(row, 0).checkState() == QtCore.Qt.CheckState.Checked
        }
        if table is getattr(self, "batch_data_table", None):
            visible_ids = {table.item(row, id_column).text() for row in range(table.rowCount())}
            self.batch_selected_ids.difference_update(visible_ids)
            self.batch_selected_ids.update(visible)
            return sorted(self.batch_selected_ids)
        return sorted(visible)

    def _refresh_batch_data_selector(self) -> None:
        if not hasattr(self, "batch_data_table"):
            return
        if self.batch_data_table.rowCount():
            self._selected_data_unit_ids()
        old_selected = set(self.batch_selected_ids)
        query = self.batch_search.text().strip().lower()
        checked_only = self.batch_checked_only.isChecked()
        units = []
        for unit in self.store.data_units():
            haystack = " ".join(str(unit.get(key, "")) for key in ("subject_code", "session_key", "state_display_name", "condition_label", "timepoint_value", "source_path")).lower()
            if query and query not in haystack:
                continue
            if checked_only and str(unit.get("inspection_status", "unchecked")) != "checked" and unit["data_unit_id"] not in self.batch_selected_ids:
                continue
            units.append(unit)
        with QtCore.QSignalBlocker(self.batch_data_table):
            self.batch_data_table.setRowCount(len(units))
            for row, unit in enumerate(units):
                use = QtWidgets.QTableWidgetItem(); use.setFlags(use.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
                use.setCheckState(QtCore.Qt.CheckState.Checked if unit["data_unit_id"] in old_selected else QtCore.Qt.CheckState.Unchecked)
                self.batch_data_table.setItem(row, 0, use)
                values = [unit["subject_code"], unit["session_key"], unit["state_display_name"], unit.get("condition_label", ""), "" if unit.get("timepoint_value") is None else f"{unit['timepoint_value']:g} {unit.get('timepoint_unit') or ''}", unit.get("inspection_status", "unchecked"), Path(unit["source_path"]).name, unit["data_unit_id"]]
                for column, value in enumerate(values, 1):
                    self.batch_data_table.setItem(row, column, QtWidgets.QTableWidgetItem(str(value or "")))
        self._update_batch_selection_label()

    def _update_batch_selection_label(self, *_args: Any) -> None:
        if hasattr(self, "batch_selection_label"):
            self.batch_selection_label.setText(f"{len(self._selected_data_unit_ids())} data units selected")

    def _set_batch_visible_checked(self, checked: bool) -> None:
        with QtCore.QSignalBlocker(self.batch_data_table):
            for row in range(self.batch_data_table.rowCount()):
                self.batch_data_table.item(row, 0).setCheckState(QtCore.Qt.CheckState.Checked if checked else QtCore.Qt.CheckState.Unchecked)
        self._update_batch_selection_label()

    def _current_data_unit(self) -> dict[str, Any] | None:
        item = self.hierarchy.currentItem() if hasattr(self, "hierarchy") else None
        identity = item.data(0, QtCore.Qt.ItemDataRole.UserRole) if item else None
        if isinstance(identity, tuple) and identity[0] == "data":
            matches = self.store.data_units(data_unit_ids=[str(identity[1])])
            return matches[0] if matches else None
        row = self.data_table.currentRow()
        if row < 0:
            return None
        data_unit_id = self.data_table.item(row, 10).text()
        matches = self.store.data_units(data_unit_ids=[data_unit_id])
        return matches[0] if matches else None

    def add_subject(self) -> None:
        code, ok = QtWidgets.QInputDialog.getText(self, "Add subject", "Subject code (unique within project)")
        if not ok or not code.strip():
            return
        group, ok = QtWidgets.QInputDialog.getText(self, "Add subject", "Group (optional)")
        if ok:
            try:
                self._begin_project_edit()
                self.store.add_subject(code, group)
                self._record_project_content_changes()
                self.refresh_all()
            except Exception as exc:  # noqa: BLE001
                QtWidgets.QMessageBox.warning(self, "Cannot add subject", str(exc))

    def _selected_hierarchy(self, kind: str) -> str | None:
        item = self.hierarchy.currentItem()
        value = item.data(0, QtCore.Qt.ItemDataRole.UserRole) if item else None
        return str(value[1]) if isinstance(value, tuple) and value[0] == kind else None

    def add_session(self) -> None:
        subject_id = self._selected_hierarchy("subject")
        if not subject_id:
            QtWidgets.QMessageBox.information(self, "Select subject", "Select a subject in the project tree first.")
            return
        key, ok = QtWidgets.QInputDialog.getText(self, "Add session", "Session key (for example Day7)")
        if ok and key.strip():
            try:
                self._begin_project_edit()
                self.store.add_session(subject_id, key)
                self._record_project_content_changes()
                self.refresh_all()
            except Exception as exc:  # noqa: BLE001
                QtWidgets.QMessageBox.warning(self, "Cannot add session", str(exc))

    def add_state(self) -> None:
        session_id = self._selected_hierarchy("session")
        if not session_id:
            QtWidgets.QMessageBox.information(self, "Select session", "Select a session in the project tree first.")
            return
        label, ok = QtWidgets.QInputDialog.getText(self, "Add state", "State display label")
        if ok and label.strip():
            try:
                self._begin_project_edit()
                self.store.add_state_record(session_id, label)
                self._record_project_content_changes()
                self.refresh_all()
            except Exception as exc:  # noqa: BLE001
                QtWidgets.QMessageBox.warning(self, "Cannot add state", str(exc))

    def open_structure_template(self) -> None:
        dialog = StructureTemplateDialog(self.store, self)
        dialog.about_to_apply.connect(self._begin_project_edit)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            self._record_project_content_changes()
            self.refresh_all()
            result = dialog.apply_result or {}
            self._reveal_hierarchy_nodes(list(result.get("state_ids", [])))
            created = (
                f"新增 {result.get('subjects_created', 0)} 个被试、"
                f"{result.get('sessions_created', 0)} 个试次、{result.get('states_created', 0)} 个状态"
            )
            reused = (
                f"复用 {result.get('subjects_reused', 0)} / {result.get('sessions_reused', 0)} / "
                f"{result.get('states_reused', 0)} 个已有节点"
            )
            message = f"模板已应用：{created}；{reused}；新建 {result.get('directories_created', 0)} 个目录。"
            if not any(result.get(key, 0) for key in ("subjects_created", "sessions_created", "states_created")):
                message += " 没有需要新增的节点，现有结构保持不变。"
            self.statusBar().showMessage(message, 15000)
            QtWidgets.QMessageBox.information(self, "模板已应用", message)

    def review_duplicate_states(self) -> None:
        groups = self.store.duplicate_state_preview()
        if not groups:
            QtWidgets.QMessageBox.information(self, "Duplicate states", "No same-parent duplicate-looking states were found.")
            return
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Duplicate state migration preview")
        dialog.resize(980, 460)
        layout = QtWidgets.QVBoxLayout(dialog)
        text = QtWidgets.QLabel(
            "Only exact same-parent semantic duplicates are eligible for automatic merge. "
            "Ambiguous same-label states remain unchanged. A SQLite backup is created before every merge."
        )
        text.setWordWrap(True)
        layout.addWidget(text)
        table = QtWidgets.QTableWidget(len(groups), 7)
        table.setHorizontalHeaderLabels(["Merge", "Subject", "Session", "State", "Nodes", "Data / results", "Decision"])
        for row_index, group in enumerate(groups):
            use = QtWidgets.QTableWidgetItem()
            use.setFlags(use.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
            use.setCheckState(QtCore.Qt.CheckState.Checked if group["safe_to_merge"] else QtCore.Qt.CheckState.Unchecked)
            if not group["safe_to_merge"]:
                use.setFlags(use.flags() & ~QtCore.Qt.ItemFlag.ItemIsEnabled)
            table.setItem(row_index, 0, use)
            nodes = group["nodes"]
            values = [
                group["subject_code"], group["session_key"], group["display_name"], str(len(nodes)),
                f"{sum(int(node['data_count']) for node in nodes)} / {sum(int(node['result_count']) for node in nodes)}",
                group["reason"],
            ]
            for column, value in enumerate(values, 1):
                table.setItem(row_index, column, QtWidgets.QTableWidgetItem(str(value)))
            table.item(row_index, 3).setToolTip("\n".join(str(value) for value in group["state_ids"]))
        table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(6, QtWidgets.QHeaderView.ResizeMode.Stretch)
        layout.addWidget(table)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Cancel | QtWidgets.QDialogButtonBox.StandardButton.Apply)
        buttons.rejected.connect(dialog.reject)
        buttons.accepted.connect(dialog.accept)
        layout.addWidget(buttons)
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        selected = [group for index, group in enumerate(groups) if table.item(index, 0).checkState() == QtCore.Qt.CheckState.Checked]
        if not selected:
            self.statusBar().showMessage("Duplicate-state preview closed without changes.", 8000)
            return
        outcomes: list[dict[str, Any]] = []
        try:
            self._begin_project_edit()
            for group in selected:
                outcomes.append(self.store.merge_duplicate_states(group["state_ids"]))
        except Exception as exc:  # noqa: BLE001
            QtWidgets.QMessageBox.warning(self, "Duplicate-state migration failed", str(exc))
            self.refresh_all()
            return
        self.refresh_all()
        backups = "\n".join(str(item["backup_path"]) for item in outcomes)
        QtWidgets.QMessageBox.information(
            self,
            "Duplicate states merged",
            f"Merged {len(outcomes)} exact duplicate group(s); moved {sum(item['moved_data_units'] for item in outcomes)} data unit(s).\n\nBackups:\n{backups}",
        )

    def _selected_import_context(self) -> dict[str, Any]:
        item = self.hierarchy.currentItem() if hasattr(self, "hierarchy") else None
        identity = item.data(0, QtCore.Qt.ItemDataRole.UserRole) if item else None
        if not isinstance(identity, tuple):
            return {}
        kind, stable_id = str(identity[0]), str(identity[1])
        if kind == "subject":
            row = next((value for value in self.store.subjects() if value["subject_id"] == stable_id), None)
            return {"subject_code": row["subject_code"], "group_label": row.get("group_label", "")} if row else {}
        if kind == "session":
            session = next((value for value in self.store.sessions() if value["session_id"] == stable_id), None)
            if not session:
                return {}
            subject = next(value for value in self.store.subjects() if value["subject_id"] == session["subject_id"])
            return {"subject_code": subject["subject_code"], "group_label": subject.get("group_label", ""), "session_key": session["session_key"], "experiment_name": session.get("experiment_name", "")}
        if kind == "state":
            state = next((value for value in self.store.state_records() if value["state_record_id"] == stable_id), None)
            if not state:
                return {}
            session = next(value for value in self.store.sessions() if value["session_id"] == state["session_id"])
            subject = next(value for value in self.store.subjects() if value["subject_id"] == session["subject_id"])
            return {
                "subject_code": subject["subject_code"], "group_label": subject.get("group_label", ""),
                "session_key": session["session_key"], "experiment_name": session.get("experiment_name", ""),
                "condition_label": state.get("condition_label", ""), "timepoint_value": state.get("timepoint_value"),
                "timepoint_unit": state.get("timepoint_unit", ""), "reference_event": state.get("reference_event", ""),
                "state_display_name": state["display_name"],
                "state_record_id": state["state_record_id"],
            }
        if kind == "data":
            matches = self.store.data_units(data_unit_ids=[stable_id])
            if not matches:
                return {}
            unit = matches[0]
            return {
                "subject_code": unit["subject_code"], "group_label": unit.get("group_label", ""),
                "session_key": unit["session_key"], "experiment_name": unit.get("experiment_name", ""),
                "condition_label": unit.get("condition_label", ""), "timepoint_value": unit.get("timepoint_value"),
                "timepoint_unit": unit.get("timepoint_unit", ""), "reference_event": unit.get("reference_event", ""),
                "state_display_name": unit["state_display_name"], "state_record_id": unit["state_record_id"],
            }
        return {}

    def _hierarchy_context_menu(self, position: QtCore.QPoint) -> None:
        item = self.hierarchy.itemAt(position)
        if item is None:
            return
        self.hierarchy.setCurrentItem(item)
        identity = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        menu = QtWidgets.QMenu(self)
        if isinstance(identity, tuple) and identity[0] == "state":
            menu.addAction("Import data into this state", self.import_to_selected_state)
        if isinstance(identity, tuple) and identity[0] == "data":
            menu.addAction("Open in analysis", self.open_selected)
        if not menu.isEmpty():
            menu.exec(self.hierarchy.viewport().mapToGlobal(position))

    def import_to_selected_state(self) -> None:
        context = self._selected_import_context()
        if not context.get("state_record_id"):
            QtWidgets.QMessageBox.information(self, "Select state", "Select an existing state node, then import data into that state.")
            return
        paths, _ = QtWidgets.QFileDialog.getOpenFileNames(self, "Import FIF files into selected state", str(Path.home()), "FIF files (*.fif *.fif.gz)")
        if paths:
            self._run_import_preview(paths, inherited=context)

    def import_folder(self) -> None:
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, "Choose folder containing FIF files", str(Path.home()))
        if not folder:
            return
        paths = self._expand_import_paths([folder])
        if not paths:
            QtWidgets.QMessageBox.information(self, "No FIF files", "The selected folder contains no .fif or .fif.gz files.")
            return
        self._run_import_preview(paths)

    @staticmethod
    def _expand_import_paths(paths: list[str]) -> list[str]:
        files: list[Path] = []
        for raw_path in paths:
            path = Path(raw_path).expanduser().resolve()
            if path.is_dir():
                files.extend(candidate for candidate in path.rglob("*") if candidate.is_file() and candidate.name.lower().endswith((".fif", ".fif.gz")))
            elif path.is_file() and path.name.lower().endswith((".fif", ".fif.gz")):
                files.append(path)
        return [str(path) for path in sorted(dict.fromkeys(files), key=lambda item: str(item).lower())]

    def dragEnterEvent(self, event: QtGui.QDragEnterEvent) -> None:
        if self.mode == "manage" and event.mimeData().hasUrls():
            local_paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
            if self._expand_import_paths(local_paths):
                event.acceptProposedAction()
                return
        super().dragEnterEvent(event)

    def dropEvent(self, event: QtGui.QDropEvent) -> None:
        if self.mode == "manage" and event.mimeData().hasUrls():
            local_paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
            files = self._expand_import_paths(local_paths)
            if files:
                event.acceptProposedAction()
                self._run_import_preview(files)
                return
        super().dropEvent(event)

    def edit_selected_hierarchy(self) -> None:
        item = self.hierarchy.currentItem()
        identity = item.data(0, QtCore.Qt.ItemDataRole.UserRole) if item else None
        if not isinstance(identity, tuple) or identity[0] == "project":
            QtWidgets.QMessageBox.information(self, "Edit", "Select a subject, session, or state in the project tree.")
            return
        kind, stable_id = str(identity[0]), str(identity[1])
        if kind == "subject":
            row = next(record for record in self.store.subjects() if record["subject_id"] == stable_id)
            code, ok = QtWidgets.QInputDialog.getText(self, "Edit subject", "Subject code", text=row["subject_code"])
            if not ok or not code.strip():
                return
            group, ok = QtWidgets.QInputDialog.getText(self, "Edit subject", "Group", text=str(row.get("group_label") or ""))
            if ok:
                self._begin_project_edit()
                self.store.update_subject(stable_id, subject_code=code, group_label=group)
        elif kind == "session":
            row = next(record for record in self.store.sessions() if record["session_id"] == stable_id)
            key, ok = QtWidgets.QInputDialog.getText(self, "Edit session", "Session key", text=row["session_key"])
            if not ok or not key.strip():
                return
            experiment, ok = QtWidgets.QInputDialog.getText(self, "Edit session", "Experiment name", text=str(row.get("experiment_name") or ""))
            if ok:
                self._begin_project_edit()
                self.store.update_session(stable_id, session_key=key, experiment_name=experiment, session_date=str(row.get("session_date") or ""), notes=str(row.get("notes") or ""))
        elif kind == "state":
            row = next(record for record in self.store.state_records() if record["state_record_id"] == stable_id)
            label, ok = QtWidgets.QInputDialog.getText(self, "Edit state", "Display label", text=row["display_name"])
            if not ok or not label.strip():
                return
            condition, ok = QtWidgets.QInputDialog.getText(self, "Edit state", "Condition", text=str(row.get("condition_label") or ""))
            if ok:
                self._begin_project_edit()
                self.store.update_state_record(
                    stable_id,
                    display_name=label,
                    condition_label=condition,
                    timepoint_value=row.get("timepoint_value"),
                    timepoint_unit=str(row.get("timepoint_unit") or "min"),
                    reference_event=str(row.get("reference_event") or ""),
                    actual_start=str(row.get("actual_start") or ""),
                    actual_end=str(row.get("actual_end") or ""),
                )
        self.refresh_all()

    def import_files(self) -> None:
        paths, _ = QtWidgets.QFileDialog.getOpenFileNames(self, "Import FIF files", str(Path.home()), "FIF files (*.fif *.fif.gz)")
        if not paths:
            return
        self._run_import_preview(paths)

    def _run_import_preview(self, paths: list[str], *, inherited: dict[str, Any] | None = None) -> None:
        context = self._selected_import_context() if inherited is None else inherited
        dialog = ImportPreviewDialog(self.store, paths, self.config_path, self.metadata_dir, self, inherited=context)
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        self._begin_project_edit()
        imported = failed = reused_copy = 0
        errors: list[str] = []
        reveal_ids: list[str] = []
        for row in dialog.rows():
            try:
                state_id = str(row["state_record_id"])
                if not state_id:
                    raise ValueError("target state is pending assignment")
                inspected = inspect_file(row["source_path"], self.metadata_dir, self.config_path)
                suggested_mapping = mapping_rows(inspected["channel_table"])
                loaded = inspected.get("loaded")
                source_structure = {
                    "channel_names": [str(name) for name in getattr(loaded, "ch_names", [])],
                    "n_channels": int(inspected["n_channels"]),
                    "n_epochs": int(inspected["n_epochs"]),
                    "n_times": int(inspected["n_times"]),
                    "sampling_rate_hz": float(inspected["sfreq"]),
                    "epoch_tmin_s": float(inspected["tmin"]),
                    "epoch_tmax_s": float(inspected["tmax"]),
                    "original_epoch_indices": [int(value) for value in getattr(loaded, "selection", range(int(inspected["n_epochs"])))],
                }
                data_id, copied = self.store.import_data_unit(
                    state_id, row["source_path"], channel_mapping=suggested_mapping,
                    epoch_selection=row["epoch_selection"], time_selection=row["time_selection"],
                    sampling_rate_hz=inspected["sfreq"], validity_status="needs_mapping_confirmation",
                    validity_message="Confirm channel-to-region mapping before region-level analysis",
                    source_structure=source_structure,
                )
                imported += 1
                reused_copy += int(not copied)
                if copied:
                    self._record_project_content_changes()
                reveal_ids.extend([state_id, data_id])
            except Exception as exc:  # noqa: BLE001 - each import row is independently reportable and retryable
                failed += 1
                errors.append(f"{Path(row['source_path']).name}: {type(exc).__name__}: {exc}")
        self.refresh_all()
        self._reveal_hierarchy_nodes(reveal_ids)
        summary = f"Import finished: {imported} succeeded, {failed} failed, {reused_copy} reused an existing project copy."
        self.statusBar().showMessage(summary, 12000)
        if errors:
            QtWidgets.QMessageBox.warning(self, "Some imports failed", summary + "\n\n" + "\n".join(errors))

    def edit_project_template(self) -> None:
        dialog = JsonEditorDialog("Project analysis template", self.store.project.get("analysis_template", {}), self)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            self._begin_project_edit()
            self.store.update_project(analysis_template=dialog.value)
            self.refresh_all()
            self.statusBar().showMessage("Project template changed in draft; click Save project to formalize it.", 10000)

    def edit_data_override(self) -> None:
        unit = self._current_data_unit()
        if unit is None:
            QtWidgets.QMessageBox.information(self, "Data override", "Select one data unit first.")
            return
        dialog = JsonEditorDialog("Data-unit analysis override", dict(unit.get("analysis_override", {})), self)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            self._begin_project_edit()
            self.store.update_data_unit_override(unit["data_unit_id"], dialog.value)
            self.refresh_all()
            self.statusBar().showMessage("Data-unit override changed in draft; click Save project to formalize it.", 10000)

    def edit_mapping(self) -> None:
        unit = self._current_data_unit()
        if unit is None:
            QtWidgets.QMessageBox.information(self, "Select data", "Select one data unit first.")
            return
        rows = unit.get("channel_mapping", {})
        if isinstance(rows, dict):
            rows = rows.get("channels", [])
        dialog = ChannelMappingDialog(list(rows), self)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            self._begin_project_edit()
            self.store.update_data_unit_mapping(unit["data_unit_id"], dialog.mapping(), validity_status="ready")
            self.refresh_all()

    def relocate_selected_source(self) -> None:
        unit = self._current_data_unit()
        if unit is None:
            QtWidgets.QMessageBox.information(self, "Relocate source", "Select one data unit first.")
            return
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Locate the same source file", str(self.store.resolve_source_path(unit).parent), "FIF files (*.fif *.fif.gz);;All files (*)")
        if not path:
            return
        try:
            self._begin_project_edit()
            self.store.relocate_source(unit["data_unit_id"], path)
            self.refresh_all()
        except Exception as exc:  # noqa: BLE001
            QtWidgets.QMessageBox.warning(self, "Source does not match", str(exc))

    def open_adjacent(self, step: int) -> None:
        count = self.data_table.rowCount()
        if not count:
            return
        row = self.data_table.currentRow()
        row = 0 if row < 0 else max(0, min(count - 1, row + step))
        self.data_table.selectRow(row)
        self.open_selected()

    def open_selected(self, *_args: Any) -> None:
        unit = self._current_data_unit()
        if unit is None:
            return
        if self._project_draft_dirty:
            answer = QtWidgets.QMessageBox.question(
                self,
                "需要先保存项目",
                "当前项目有未保存的结构或导入更改。开始分析前必须先保存项目。是否保存并继续？",
                QtWidgets.QMessageBox.StandardButton.Save | QtWidgets.QMessageBox.StandardButton.Cancel,
                QtWidgets.QMessageBox.StandardButton.Save,
            )
            if answer != QtWidgets.QMessageBox.StandardButton.Save or not self.save_project():
                return
        self.open_data_unit.emit(str(self.store.resolve_source_path(unit)), unit)

    def add_selected_to_batch(self) -> None:
        identifiers = self._selected_data_unit_ids()
        if not identifiers:
            QtWidgets.QMessageBox.information(self, "Batch selection", "Select at least one imported data unit.")
            return
        if self._project_draft_dirty:
            answer = QtWidgets.QMessageBox.question(
                self,
                "需要先保存项目",
                "批处理只接收已正式保存的数据单元。是否保存当前项目并继续？",
                QtWidgets.QMessageBox.StandardButton.Save | QtWidgets.QMessageBox.StandardButton.Cancel,
                QtWidgets.QMessageBox.StandardButton.Save,
            )
            if answer != QtWidgets.QMessageBox.StandardButton.Save or not self.save_project():
                return
        self.queue_data_units.emit(identifiers)
        self.statusBar().showMessage(f"Added {len(identifiers)} unique data units to the analysis batch queue.", 8000)

    def organize_selected_data(self) -> None:
        identifiers = self._selected_data_unit_ids()
        if not identifiers:
            QtWidgets.QMessageBox.information(self, "Organize data", "Select at least one data unit.")
            return
        self._begin_project_edit()
        outcomes = []
        for data_unit_id in identifiers:
            try:
                outcomes.append(self.store.organize_external_data(data_unit_id))
            except Exception as exc:  # noqa: BLE001
                outcomes.append({"data_unit_id": data_unit_id, "status": f"failed: {exc}"})
        self.refresh_all()
        self._record_project_content_changes()
        counts: dict[str, int] = {}
        for item in outcomes:
            counts[item["status"]] = counts.get(item["status"], 0) + 1
        QtWidgets.QMessageBox.information(self, "Organize data", "\n".join(f"{key}: {value}" for key, value in counts.items()))

    def start_batch(self) -> None:
        data_ids = self._selected_data_unit_ids()
        modules = [name for name, check in self.module_checks.items() if check.isChecked()]
        if not data_ids or not modules:
            QtWidgets.QMessageBox.warning(self, "Batch is incomplete", "Select at least one data unit and one module.")
            return
        units = self.store.data_units(data_unit_ids=data_ids)
        missing_sources = sum(not self.store.resolve_source_path(unit).is_file() for unit in units)
        mapping_pending = sum(unit["validity_status"] == "needs_mapping_confirmation" for unit in units)
        unchecked = sum(str(unit.get("inspection_status", "unchecked")) != "checked" for unit in units)
        region_modules = {"MIC", "MIM", "wPLI", "wPLI2 Debiased", "dPLI", "Time Delay"}
        if mapping_pending and set(modules).intersection(region_modules):
            QtWidgets.QMessageBox.warning(
                self,
                "Channel mapping must be confirmed",
                f"{mapping_pending} selected data unit(s) still contain unconfirmed region suggestions. "
                "Confirm their channel-to-region mapping before region-level connectivity or delay analysis.",
            )
            return
        existing = self.store.analysis_results({
            "active": 1,
            "calculation_status": "completed",
            "save_status": "saved",
            "result_validity": "current",
        })
        existing_for_units = sum(row["data_unit_id"] in set(data_ids) for row in existing)
        policy = "reuse exact compatible results" if self.batch_mode.currentIndex() == 0 else "recalculate selected data"
        answer = QtWidgets.QMessageBox.question(
            self,
            "Batch preflight",
            f"Data units: {len(data_ids)}\nModules: {', '.join(modules)}\nPolicy: {policy}\n"
            f"Task-level setting keys: {len(self.batch_task_config)}\nData-unit overrides: {sum(bool(unit.get('analysis_override')) for unit in units)}\n"
            f"Existing active results in selection: {existing_for_units}\nMissing sources: {missing_sources}\n"
            f"Mappings awaiting confirmation: {mapping_pending}\nUnchecked data explicitly included: {unchecked}\n"
            f"Each data unit keeps its own channel/epoch inspection decisions.\n\nStart this frozen batch task?",
        )
        if answer != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        runner = ProjectBatchRunner(self.store, self.config_path, self.metadata_dir)
        job_id = runner.create_job(
            data_ids,
            modules,
            task_config=self.batch_task_config,
            name="GUI batch",
            reuse_existing=self.batch_mode.currentIndex() == 0,
        )
        self._launch_batch_worker(runner, job_id, len(data_ids))

    def edit_batch_task_config(self) -> None:
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Batch calculation parameters")
        dialog.resize(780, 620)
        layout = QtWidgets.QVBoxLayout(dialog)
        note = QtWidgets.QLabel("These are calculation parameters only. Modify them in the main single-file analysis controls, then click ‘Use current single-file parameters’. Channel and epoch inspection decisions remain separate for every data unit.")
        note.setWordWrap(True); layout.addWidget(note)
        table = QtWidgets.QTreeWidget(); table.setHeaderLabels(["Parameter", "Value"])
        table.header().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        table.header().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Stretch)
        def add(parent: QtWidgets.QTreeWidgetItem | None, mapping: dict[str, Any]) -> None:
            for key, value in sorted(mapping.items()):
                item = QtWidgets.QTreeWidgetItem([str(key), "" if isinstance(value, dict) else str(value)])
                (parent.addChild(item) if parent is not None else table.addTopLevelItem(item))
                if isinstance(value, dict):
                    add(item, value)
        add(None, self.batch_task_config)
        table.expandToDepth(1); layout.addWidget(table)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Close)
        edit_button = buttons.addButton("Edit in main analysis panel", QtWidgets.QDialogButtonBox.ButtonRole.ActionRole)
        edit_button.clicked.connect(lambda: (dialog.accept(), self._focus_main_parameter_panel()))
        buttons.rejected.connect(dialog.reject); layout.addWidget(buttons)
        dialog.exec()

    def _save_batch_parameter_scheme(self) -> None:
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save batch parameter scheme", str(self.store.paths.configs / "batch-parameters.json"), "JSON (*.json)")
        if path:
            Path(path).write_text(json.dumps({"schema_version": 1, "calculation_parameters": self.batch_task_config}, ensure_ascii=False, indent=2), encoding="utf-8")

    def _load_batch_parameter_scheme(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Load batch parameter scheme", str(self.store.paths.configs), "JSON (*.json)")
        if not path:
            return
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
            values = payload.get("calculation_parameters", payload)
            if not isinstance(values, dict):
                raise TypeError("Parameter scheme must contain an object")
            self.set_batch_task_config(values)
        except (OSError, ValueError, TypeError) as exc:
            QtWidgets.QMessageBox.warning(self, "Cannot load parameter scheme", str(exc))

    def _launch_batch_worker(self, runner: ProjectBatchRunner, job_id: str, item_count: int) -> None:
        self.batch_thread = QtCore.QThread(self)
        self.batch_worker = BatchWorker(runner, job_id)
        self.batch_worker.moveToThread(self.batch_thread)
        self.batch_thread.started.connect(self.batch_worker.run)
        self.batch_worker.progress.connect(self._batch_progress)
        self.batch_worker.finished.connect(self._batch_finished)
        self.batch_worker.failed.connect(self._batch_failed)
        self.batch_worker.finished.connect(self.batch_thread.quit)
        self.batch_worker.failed.connect(self.batch_thread.quit)
        self.batch_thread.finished.connect(self.batch_worker.deleteLater)
        self.batch_thread.finished.connect(self.batch_thread.deleteLater)
        self.batch_start.setEnabled(False)
        self.batch_stop.setEnabled(True)
        self.batch_resume.setEnabled(False)
        self.batch_progress.setRange(0, item_count)
        self.batch_progress.setValue(0)
        self.batch_thread.start()

    def resume_latest_batch(self) -> None:
        jobs = [job for job in self.store.batch_jobs() if job["status"] not in {"completed"}]
        if not jobs:
            QtWidgets.QMessageBox.information(self, "Resume batch", "No interrupted or incomplete batch job is available.")
            return
        job = jobs[0]
        self.store.prepare_batch_resume(job["batch_job_id"])
        runner = ProjectBatchRunner(self.store, self.config_path, self.metadata_dir)
        self._launch_batch_worker(runner, job["batch_job_id"], len(job["items"]))

    def stop_batch(self) -> None:
        if self.batch_worker is not None:
            self.batch_worker.cancel_event.set()
            self.store.request_batch_cancel(self.batch_worker.batch_job_id)

    @QtCore.Slot(str, int, int, str, str)
    def _batch_progress(self, message: str, done: int, total: int, _data_unit_id: str, _module: str) -> None:
        self.batch_progress.setRange(0, max(1, total))
        self.batch_progress.setValue(done)
        self.statusBar().showMessage(message)

    @QtCore.Slot(object)
    def _batch_finished(self, result: dict[str, Any]) -> None:
        self.batch_start.setEnabled(True)
        self.batch_stop.setEnabled(False)
        self.batch_resume.setEnabled(True)
        self.statusBar().showMessage(f"Batch {result['status']}: {result['completed']}/{result['total']}", 10000)
        self.refresh_all()

    @QtCore.Slot(str)
    def _batch_failed(self, message: str) -> None:
        self.batch_start.setEnabled(True)
        self.batch_stop.setEnabled(False)
        self.batch_resume.setEnabled(True)
        QtWidgets.QMessageBox.critical(self, "Batch failed", message)
        self.refresh_all()

    def _refresh_batch_table(self) -> None:
        rows = [(job, item) for job in self.store.batch_jobs() for item in job["items"]]
        self.batch_table.setRowCount(len(rows))
        for row, (job, item) in enumerate(rows):
            values = [job["name"], job["status"], item["data_unit_id"], item["status"], item.get("started_at_utc", ""), item.get("error_message", "")]
            for column, value in enumerate(values):
                self.batch_table.setItem(row, column, QtWidgets.QTableWidgetItem(str(value or "")))

    def _refresh_results_table(self) -> None:
        rows = self.store.analysis_results()
        self.results_table.setRowCount(len(rows))
        for row, result in enumerate(rows):
            values = [result["subject_code"], result["session_key"], result["state_display_name"], result["module_name"], result.get("method_name", ""), result["calculation_status"], result["save_status"], result.get("result_validity", "current"), result["review_status"], result["created_at_utc"], result["analysis_id"], result["result_path"]]
            for column, value in enumerate(values):
                self.results_table.setItem(row, column, QtWidgets.QTableWidgetItem(str(value or "")))

    def set_review(self, status: str) -> None:
        rows = sorted({index.row() for index in self.results_table.selectedIndexes()})
        if not rows:
            return
        notes, ok = QtWidgets.QInputDialog.getMultiLineText(self, "Review note", "Optional review note")
        if not ok:
            return
        for row in rows:
            self.store.set_review(self.results_table.item(row, 10).text(), status, notes)
        self._refresh_results_table()

    def _refresh_compare_filters(self) -> None:
        session_value = self.compare_session.currentText() if self.compare_session.count() else ""
        condition_value = self.compare_condition.currentText() if self.compare_condition.count() else ""
        sessions = sorted({row["session_key"] for row in self.store.sessions()})
        conditions = sorted({str(row.get("condition_label") or "") for row in self.store.state_records()})
        groups = sorted({str(row.get("group_label") or "") for row in self.store.subjects() if str(row.get("group_label") or "")})
        subject_value = self.compare_subject.currentData() if self.compare_subject.count() else ""
        group_value = self.compare_group.currentData() if self.compare_group.count() else ""
        b_group_value = self.compare_b_group.currentData() if self.compare_b_group.count() else ""
        b_subject_value = self.compare_b_subject.currentData() if self.compare_b_subject.count() else ""
        b_session_value = self.compare_b_session.currentText() if self.compare_b_session.count() else ""
        b_condition_value = self.compare_b_condition.currentText() if self.compare_b_condition.count() else ""
        self.compare_group.clear()
        self.compare_group.addItem("All", "")
        for group in groups:
            self.compare_group.addItem(group, group)
        self.compare_group.setCurrentIndex(max(0, self.compare_group.findData(group_value)))
        self.compare_subject.clear()
        self.compare_subject.addItem("All subjects", "")
        for subject in self.store.subjects():
            self.compare_subject.addItem(subject["subject_code"], subject["subject_id"])
        self.compare_subject.setCurrentIndex(max(0, self.compare_subject.findData(subject_value)))
        self.compare_session.clear()
        self.compare_session.addItems(sessions)
        self.compare_condition.clear()
        self.compare_condition.addItems(conditions)
        self.compare_session.setCurrentText(session_value)
        self.compare_condition.setCurrentText(condition_value)
        self.compare_b_group.clear(); self.compare_b_group.addItem("All", "")
        for group in groups:
            self.compare_b_group.addItem(group, group)
        self.compare_b_group.setCurrentIndex(max(0, self.compare_b_group.findData(b_group_value)))
        self.compare_b_subject.clear(); self.compare_b_subject.addItem("All subjects", "")
        for subject in self.store.subjects():
            self.compare_b_subject.addItem(subject["subject_code"], subject["subject_id"])
        self.compare_b_subject.setCurrentIndex(max(0, self.compare_b_subject.findData(b_subject_value)))
        self.compare_b_session.clear(); self.compare_b_session.addItems(sessions); self.compare_b_session.setCurrentText(b_session_value)
        self.compare_b_condition.clear(); self.compare_b_condition.addItems(conditions); self.compare_b_condition.setCurrentText(b_condition_value)
        self._refresh_specific_sessions()

    def _refresh_specific_sessions(self) -> None:
        current = self.compare_specific_session.currentData() if self.compare_specific_session.count() else ""
        rows = self.store.query(
            """SELECT s.session_id,s.session_key,s.experiment_name,u.subject_code
               FROM sessions s JOIN subjects u ON u.subject_id=s.subject_id
               WHERE s.session_key=? ORDER BY u.subject_code,s.created_at_utc""",
            (self.compare_session.currentText(),),
        )
        with QtCore.QSignalBlocker(self.compare_specific_session):
            self.compare_specific_session.clear()
            self.compare_specific_session.addItem("All matching sessions", "")
            for row in rows:
                label = f"{row['subject_code']} | {row.get('experiment_name') or row['session_key']} | {row['session_id'][:18]}…"
                self.compare_specific_session.addItem(label, row["session_id"])
            index = self.compare_specific_session.findData(current)
            self.compare_specific_session.setCurrentIndex(max(0, index))

    def _refresh_comparison_from_controls(self) -> None:
        self.current_snapshot_analysis_ids = None
        self.current_snapshot_second_ids = None
        self.refresh_comparison()

    def _comparison_preview(self, filters: dict[str, Any], selection: Any, snapshot_ids: list[str] | None) -> pd.DataFrame:
        if snapshot_ids is None:
            return subject_match_preview(self.store, filters, include_pending_review=self.compare_pending.isChecked())
        by_subject = {str(row.subject_id): str(row.analysis_id) for row in selection.included.itertuples()}
        return pd.DataFrame(
            [
                {
                    "subject_id": subject["subject_id"],
                    "subject_code": subject["subject_code"],
                    "group_label": subject.get("group_label", ""),
                    "match_status": "included_from_snapshot" if subject["subject_id"] in by_subject else "not_in_snapshot",
                    "analysis_id": by_subject.get(subject["subject_id"], ""),
                    "reason": "Fixed saved comparison membership" if subject["subject_id"] in by_subject else "Not included in the saved snapshot",
                }
                for subject in self.store.subjects()
                if not filters.get("group_label") or str(subject.get("group_label") or "") == str(filters["group_label"])
                if not filters.get("subject_id") or str(subject["subject_id"]) == str(filters["subject_id"])
            ]
        )

    def refresh_comparison(self) -> None:
        filters = {
            "group_label": str(self.compare_group.currentData() or ""),
            "subject_id": str(self.compare_subject.currentData() or ""),
            "session_key": self.compare_session.currentText(),
            "session_id": str(self.compare_specific_session.currentData() or ""),
            "condition_label": self.compare_condition.currentText(),
            "timepoint_value": None if self.compare_time_range.isChecked() else self.compare_timepoint.value(),
            "timepoint_min": self.compare_time_min.value() if self.compare_time_range.isChecked() else None,
            "timepoint_max": self.compare_time_max.value() if self.compare_time_range.isChecked() else None,
            "module_name": self.compare_module.currentText(),
        }
        selection = select_results(
            self.store,
            filters,
            include_pending_review=self.compare_pending.isChecked(),
            selected_analysis_ids=self.current_snapshot_analysis_ids,
        )
        preview = self._comparison_preview(filters, selection, self.current_snapshot_analysis_ids)
        self.current_comparison_selection = selection
        second_filters = {
            **filters,
            "group_label": str(self.compare_b_group.currentData() or ""),
            "subject_id": str(self.compare_b_subject.currentData() or ""),
            "session_key": self.compare_b_session.currentText(),
            "session_id": "",
            "condition_label": self.compare_b_condition.currentText(),
            "timepoint_value": self.compare_second_timepoint.value(),
            "timepoint_min": None,
            "timepoint_max": None,
        }
        self.current_comparison_second = (
            select_results(
                self.store,
                second_filters,
                include_pending_review=self.compare_pending.isChecked(),
                selected_analysis_ids=self.current_snapshot_second_ids,
            )
            if self.compare_paired.isChecked()
            else None
        )
        second_preview = (
            self._comparison_preview(second_filters, self.current_comparison_second, self.current_snapshot_second_ids)
            if self.current_comparison_second is not None
            else pd.DataFrame()
        )
        self.current_comparison_preview = preview
        self.current_comparison_second_preview = second_preview
        self._refresh_compare_bands(selection)
        self._refresh_compare_metrics(selection)
        self._refresh_compare_targets(selection)
        compatibility = dict(zip(selection.compatibility.get("analysis_id", []), selection.compatibility.get("compatible_with_first", [])))
        result_records = {str(record["analysis_id"]): record for record in self.store.analysis_results()}

        def result_details(analysis_id: str) -> list[str]:
            if not analysis_id or ";" in analysis_id:
                return ["", "", "", ""]
            record = result_records.get(analysis_id)
            if record is None:
                return ["", "", "", ""]
            condition_time = str(record.get("condition_label") or "")
            if record.get("timepoint_value") is not None:
                condition_time = f"{condition_time} | {float(record['timepoint_value']):g} {record.get('timepoint_unit') or ''}".strip(" |")
            samples = ""
            try:
                result_path = Path(str(record["result_path"]))
                manifest = load_result_manifest(result_path if result_path.is_absolute() else self.store.paths.root / result_path)
                quality = manifest.get("quality_summary", {})
                parts = []
                if quality.get("n_epochs") is not None:
                    parts.append(f"{int(quality['n_epochs'])} epochs")
                if quality.get("effective_duration_s") is not None:
                    parts.append(f"{float(quality['effective_duration_s']):g} s")
                samples = "; ".join(parts)
            except (OSError, ValueError, KeyError, TypeError):
                samples = "manifest unavailable"
            return [str(record.get("session_key") or ""), condition_time, Path(str(record.get("source_path") or "")).name, samples]

        detail_columns = ["session_key", "condition_time", "source_file", "effective_samples"]
        for frame in (preview, second_preview):
            if frame.empty:
                continue
            details = [result_details(str(value)) for value in frame["analysis_id"]]
            for index, column in enumerate(detail_columns):
                frame[column] = [values[index] for values in details]
        self.current_comparison_preview = preview
        self.current_comparison_second_preview = second_preview

        self.compare_table.setRowCount(len(preview))
        for row, item in preview.iterrows():
            analysis = str(item["analysis_id"])
            second = second_preview.loc[second_preview["subject_id"].eq(item["subject_id"])] if not second_preview.empty else pd.DataFrame()
            second_status = str(second.iloc[0]["match_status"]) if not second.empty else ""
            second_analysis = str(second.iloc[0]["analysis_id"]) if not second.empty else ""
            first_details = result_details(analysis)
            second_details = result_details(second_analysis)
            reasons = [str(item["reason"])]
            if not second.empty and str(second.iloc[0]["reason"]):
                reasons.append("Second: " + str(second.iloc[0]["reason"]))
            values = [
                item["subject_code"], item.get("group_label", ""), *first_details, item["match_status"], analysis,
                *second_details, second_status, second_analysis, " | ".join(value for value in reasons if value),
                "" if not analysis or ";" in analysis else str(compatibility.get(analysis, "")),
            ]
            for column, value in enumerate(values):
                cell = QtWidgets.QTableWidgetItem(str(value or ""))
                cell.setToolTip(str(value or ""))
                self.compare_table.setItem(row, column, cell)
        self._plot_comparison(selection)

    def _comparison_filters(self) -> dict[str, Any]:
        return {
            "group_label": str(self.compare_group.currentData() or ""),
            "subject_id": str(self.compare_subject.currentData() or ""),
            "session_key": self.compare_session.currentText(),
            "session_id": str(self.compare_specific_session.currentData() or ""),
            "condition_label": self.compare_condition.currentText(),
            "timepoint_value": None if self.compare_time_range.isChecked() else self.compare_timepoint.value(),
            "timepoint_min": self.compare_time_min.value() if self.compare_time_range.isChecked() else None,
            "timepoint_max": self.compare_time_max.value() if self.compare_time_range.isChecked() else None,
            "module_name": self.compare_module.currentText(),
        }

    def save_comparison(self) -> None:
        if self.current_comparison_selection is None:
            self.refresh_comparison()
        name, ok = QtWidgets.QInputDialog.getText(self, "Save comparison", "Snapshot name", text=f"{self.compare_session.currentText()} {self.compare_condition.currentText()} T{self.compare_timepoint.value():g}")
        if not ok or not name.strip():
            return
        selection = self.current_comparison_selection
        comparison_id = self.store.create_comparison_snapshot(
            name,
            self._comparison_filters(),
            selection.included.to_dict("records"),
            selection.excluded.to_dict("records"),
            {
                "band": self.compare_band.currentText(),
                "metric": self.compare_metric.currentText(),
                "include_pending_review": self.compare_pending.isChecked(),
                "paired": self.compare_paired.isChecked(),
                "second_timepoint": self.compare_second_timepoint.value(),
                "second_filters": {
                    "group_label": str(self.compare_b_group.currentData() or ""),
                    "subject_id": str(self.compare_b_subject.currentData() or ""),
                    "session_key": self.compare_b_session.currentText(),
                    "condition_label": self.compare_b_condition.currentText(),
                    "timepoint_value": self.compare_second_timepoint.value(),
                },
                "target_level": self.compare_dimension.currentText(),
                "target": self.compare_target.currentText(),
                "view": self.compare_view.currentText(),
                "second_analysis_ids": (
                    self.current_comparison_second.included["analysis_id"].astype(str).tolist()
                    if self.current_comparison_second is not None and not self.current_comparison_second.included.empty
                    else []
                ),
            },
        )
        self.statusBar().showMessage(f"Saved comparison snapshot: {comparison_id}", 10000)

    def load_comparison(self) -> None:
        snapshots = self.store.comparison_snapshots()
        if not snapshots:
            QtWidgets.QMessageBox.information(self, "Load comparison", "No saved comparison snapshot is available.")
            return
        labels = [f"{row['name']} — {row['created_at_utc']}" for row in snapshots]
        label, ok = QtWidgets.QInputDialog.getItem(self, "Load comparison", "Saved snapshot", labels, editable=False)
        if not ok:
            return
        payload = self.store.load_comparison_snapshot(snapshots[labels.index(label)]["comparison_id"])
        filters = payload.get("filters", {})
        settings = payload.get("settings", {})
        with QtCore.QSignalBlocker(self.compare_group):
            index = self.compare_group.findData(filters.get("group_label", ""))
            self.compare_group.setCurrentIndex(max(0, index))
        subject_index = self.compare_subject.findData(str(filters.get("subject_id", "")))
        self.compare_subject.setCurrentIndex(max(0, subject_index))
        self.compare_session.setCurrentText(str(filters.get("session_key", "")))
        session_index = self.compare_specific_session.findData(str(filters.get("session_id", "")))
        self.compare_specific_session.setCurrentIndex(max(0, session_index))
        self.compare_condition.setCurrentText(str(filters.get("condition_label", "")))
        if filters.get("timepoint_value") is not None:
            self.compare_timepoint.setValue(float(filters["timepoint_value"]))
        range_enabled = filters.get("timepoint_min") is not None or filters.get("timepoint_max") is not None
        self.compare_time_range.setChecked(range_enabled)
        if filters.get("timepoint_min") is not None:
            self.compare_time_min.setValue(float(filters["timepoint_min"]))
        if filters.get("timepoint_max") is not None:
            self.compare_time_max.setValue(float(filters["timepoint_max"]))
        self.compare_module.setCurrentText(str(filters.get("module_name", "Band Power")))
        self.compare_pending.setChecked(bool(settings.get("include_pending_review", False)))
        self.compare_paired.setChecked(bool(settings.get("paired", False)))
        if settings.get("second_timepoint") is not None:
            self.compare_second_timepoint.setValue(float(settings["second_timepoint"]))
        second_filters = settings.get("second_filters", {})
        if isinstance(second_filters, dict):
            for combo, key in (
                (self.compare_b_group, "group_label"),
                (self.compare_b_subject, "subject_id"),
            ):
                index = combo.findData(str(second_filters.get(key, "")))
                combo.setCurrentIndex(max(0, index))
            self.compare_b_session.setCurrentText(str(second_filters.get("session_key", "")))
            self.compare_b_condition.setCurrentText(str(second_filters.get("condition_label", "")))
        self.compare_dimension.setCurrentText(str(settings.get("target_level", "All")))
        self.current_snapshot_analysis_ids = [str(row["analysis_id"]) for row in payload.get("included", []) if row.get("analysis_id")]
        self.current_snapshot_second_ids = [str(value) for value in settings.get("second_analysis_ids", [])]
        self.refresh_comparison()
        if settings.get("band"):
            self.compare_band.setCurrentText(str(settings["band"]))
        if settings.get("metric"):
            self.compare_metric.setCurrentText(str(settings["metric"]))
        if settings.get("target"):
            self.compare_target.setCurrentText(str(settings["target"]))
        if settings.get("view"):
            self.compare_view.setCurrentText(str(settings["view"]))
        self.statusBar().showMessage(f"Loaded fixed comparison snapshot: {payload['comparison_id']}", 10000)

    def export_comparison(self) -> None:
        if self.current_comparison_preview.empty:
            self.refresh_comparison()
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Export comparison preview", str(self.store.paths.root / "comparison_preview.csv"), "CSV (*.csv)")
        if path:
            output = self.current_comparison_preview
            if not self.current_comparison_second_preview.empty:
                output = output.merge(
                    self.current_comparison_second_preview,
                    on=["subject_id", "subject_code", "group_label"],
                    how="outer",
                    suffixes=("_first", "_second"),
                )
            output.to_csv(path, index=False)
            self.statusBar().showMessage(f"Exported: {path}", 10000)

    def _refresh_compare_bands(self, selection: Any) -> None:
        current = self.compare_band.currentText()
        values: list[str] = []
        if not selection.included.empty:
            first = selection.included.iloc[0]
            try:
                manifest = load_result_manifest(self.store.paths.root / first["result_path"])
                table_names = list(manifest.get("tables", {}))
                preferred = "band_power_summary" if "band_power_summary" in table_names else ("band_summary" if "band_summary" in table_names else "")
                if preferred:
                    frame = load_table(manifest, preferred)
                    column = "band" if "band" in frame else ("frequency_band" if "frequency_band" in frame else "")
                    if column:
                        values = list(dict.fromkeys(frame[column].dropna().astype(str)))
            except (OSError, ValueError, KeyError, TypeError):
                values = []
        with QtCore.QSignalBlocker(self.compare_band):
            self.compare_band.clear()
            self.compare_band.addItems(values or ["All"])
            if current in values:
                self.compare_band.setCurrentText(current)

    def _refresh_compare_metrics(self, selection: Any) -> None:
        current = self.compare_metric.currentText()
        values: list[str] = []
        if not selection.included.empty:
            first = selection.included.iloc[0]
            try:
                manifest = load_result_manifest(self.store.paths.root / first["result_path"])
                preferred = "band_summary" if "band_summary" in manifest.get("tables", {}) else ""
                if preferred:
                    frame = load_table(manifest, preferred)
                    if "method" in frame:
                        values = list(dict.fromkeys(frame["method"].dropna().astype(str)))
            except (OSError, ValueError, KeyError, TypeError):
                values = []
        with QtCore.QSignalBlocker(self.compare_metric):
            self.compare_metric.clear()
            self.compare_metric.addItems(values or ["All"])
            if current in values:
                self.compare_metric.setCurrentText(current)

    def _refresh_compare_targets(self, selection: Any) -> None:
        current = self.compare_target.currentText()
        values: list[str] = []
        level = self.compare_dimension.currentText()
        if selection is not None and not selection.included.empty and level != "All":
            table_by_module = {
                "PSD": "psd_channel_summary",
                "Band Power": "band_power_summary",
                "FOOOF": "model",
                "Connectivity": "band_summary",
                "Time Delay": "band_summary",
            }
            candidates = {
                "Channel": ("channel_name", "seed_channel", "target_channel"),
                "Region": ("region", "region_a", "region_b", "seed_region", "target_region"),
                "Region pair": ("pair_label", "region_pair"),
            }
            first = selection.included.iloc[0]
            try:
                manifest = load_result_manifest(self.store.paths.root / first["result_path"])
                table_name = table_by_module.get(self.compare_module.currentText(), "")
                if table_name and table_name in manifest.get("tables", {}):
                    frame = load_table(manifest, table_name)
                    if level == "Region pair" and "region_pair" not in frame:
                        if {"region_a", "region_b"}.issubset(frame.columns):
                            frame["region_pair"] = frame["region_a"].astype(str) + "–" + frame["region_b"].astype(str)
                        elif {"seed_region", "target_region"}.issubset(frame.columns):
                            frame["region_pair"] = frame["seed_region"].astype(str) + "→" + frame["target_region"].astype(str)
                    for column in candidates[level]:
                        if column in frame:
                            values.extend(frame[column].dropna().astype(str).tolist())
            except (OSError, ValueError, KeyError, TypeError):
                values = []
        values = list(dict.fromkeys(value for value in values if value))
        with QtCore.QSignalBlocker(self.compare_target):
            self.compare_target.clear()
            self.compare_target.addItems(["All", *values])
            if current in values:
                self.compare_target.setCurrentText(current)

    def _comparison_row_filters(self, module: str) -> dict[str, Any]:
        filters: dict[str, Any] = {}
        selected_band = self.compare_band.currentText()
        if selected_band != "All":
            filters["frequency_band" if module == "Time Delay" else "band"] = selected_band
        selected_metric = self.compare_metric.currentText()
        if selected_metric != "All":
            filters["method"] = selected_metric
        target = self.compare_target.currentText()
        level = self.compare_dimension.currentText()
        if target != "All":
            candidates = {
                "Channel": ("channel_name", "seed_channel", "target_channel"),
                "Region": ("region", "region_a", "region_b", "seed_region", "target_region"),
                "Region pair": ("pair_label", "region_pair"),
            }.get(level, ())
            filters["__target_columns__"] = {"columns": candidates, "value": target}
        return filters

    def _plot_comparison(self, selection: Any) -> None:
        self.compare_figure.clear()
        module = self.compare_module.currentText()
        if module == "Connectivity" and self.compare_view.currentText() == "Connection spectrum":
            self._plot_connectivity_spectra(selection)
            self.compare_canvas.draw_idle()
            return
        if module == "Connectivity" and self.compare_view.currentText() == "Region matrices":
            self._plot_connectivity_matrices(selection)
            self.compare_canvas.draw_idle()
            return
        axis = self.compare_figure.add_subplot(111)
        specs = {
            "PSD": ("psd_channel_summary", "psd_value", ["frequency_hz"]),
            "Band Power": ("band_power_summary", "absolute_power", ["band"]),
            "FOOOF": ("model", "exponent", []),
                "Connectivity": ("band_summary", "value_strength", ["method", "band", "region_pair"]),
                "Time Delay": ("band_summary", "region_peak_delay_ms", ["frequency_band", "region_pair"]),
        }
        if module not in specs or selection.included.empty:
            axis.text(0.5, 0.5, "No unambiguous saved result available for this selection", ha="center", va="center", transform=axis.transAxes)
            axis.set_axis_off()
            self.compare_canvas.draw_idle()
            return
        if module == "PSD":
            if self.compare_paired.isChecked():
                axis.text(0.5, 0.5, "Paired scalar summaries are available for Band Power, FOOOF, Connectivity, and Time Delay.\nPSD remains an individual-curve comparison.", ha="center", va="center", transform=axis.transAxes)
                axis.set_axis_off()
                self.compare_canvas.draw_idle()
                return
            self._plot_psd_comparison(axis, selection)
            self.compare_canvas.draw_idle()
            return
        table, value, groups = specs[module]
        try:
            selected_band = self.compare_band.currentText()
            row_filters = self._comparison_row_filters(module)
            effective_groups = [group for group in groups if group not in {"band", "frequency_band"}]
            if self.compare_paired.isChecked() and self.current_comparison_second is not None:
                self._plot_paired_comparison(axis, selection, self.current_comparison_second, table, value, effective_groups, row_filters)
                self.compare_canvas.draw_idle()
                return
            points = subject_summary(self.store, selection, table, value, effective_groups, row_filters=row_filters)
            if points.empty:
                raise ValueError("empty summary")
            if points.duplicated("subject_id", keep=False).any():
                raise ValueError("Several channel/region targets remain per subject. Select one target level and target before comparing.")
            subject_order = list(dict.fromkeys(points["subject_code"].astype(str)))
            xmap = {name: index for index, name in enumerate(subject_order)}
            signatures = list(dict.fromkeys(points["compatibility_signature"].astype(str)))
            palette = ["#34345C", "#9281BD", "#D06A45", "#3F8C78"]
            for signature_index, signature in enumerate(signatures):
                subset = points.loc[points["compatibility_signature"].astype(str).eq(signature)]
                axis.scatter(
                    [xmap[str(subject)] for subject in subset["subject_code"]],
                    subset[value].astype(float),
                    color=palette[signature_index % len(palette)],
                    alpha=0.8,
                    label=f"parameter set {signature_index + 1}",
                )
            axis.set_xticks(range(len(subject_order)), subject_order, rotation=35, ha="right")
            axis.set_ylabel(value)
            band_text = f", {selected_band}" if selected_band != "All" else ""
            axis.set_title(f"{module}{band_text}: subject-level representatives (n={points['subject_id'].nunique()})")
            axis.grid(axis="y", color="#dddddd", linewidth=0.6)
            if len(signatures) > 1:
                axis.legend(title="Not pooled: incompatible parameters")
        except Exception as exc:  # noqa: BLE001
            axis.text(0.5, 0.5, f"Comparison preview unavailable:\n{exc}", ha="center", va="center", transform=axis.transAxes)
            axis.set_axis_off()
        self.compare_canvas.draw_idle()

    @staticmethod
    def _with_region_pair(frame: pd.DataFrame) -> pd.DataFrame:
        result = frame.copy()
        if "region_pair" not in result:
            if {"region_a", "region_b"}.issubset(result.columns):
                result["region_pair"] = result["region_a"].astype(str) + "–" + result["region_b"].astype(str)
            elif {"seed_region", "target_region"}.issubset(result.columns):
                result["region_pair"] = result["seed_region"].astype(str) + "→" + result["target_region"].astype(str)
        return result

    def _connection_method_and_pair(self, frames: list[pd.DataFrame]) -> tuple[str, str]:
        methods = list(dict.fromkeys(str(value) for frame in frames for value in frame.get("method", pd.Series(dtype=str)).dropna().unique()))
        method = self.compare_metric.currentText()
        if method == "All":
            if len(methods) != 1:
                raise ValueError("Select one connectivity method before comparing spectra or matrices.")
            method = methods[0]
        pairs = list(dict.fromkeys(str(value) for frame in frames for value in self._with_region_pair(frame).get("region_pair", pd.Series(dtype=str)).dropna().unique()))
        pair = self.compare_target.currentText() if self.compare_dimension.currentText() == "Region pair" else "All"
        if pair == "All" and len(pairs) == 1:
            pair = pairs[0]
        return method, pair

    def _plot_connectivity_spectra(self, selection: Any) -> None:
        axis = self.compare_figure.add_subplot(111)
        if selection is None or selection.included.empty:
            axis.text(0.5, 0.5, "No unambiguous saved connectivity result is available.", ha="center", va="center", transform=axis.transAxes)
            axis.set_axis_off()
            return
        loaded: list[tuple[Any, pd.DataFrame]] = []
        for row in selection.included.itertuples():
            manifest = load_result_manifest(self.store.paths.root / row.result_path)
            loaded.append((row, self._with_region_pair(load_table(manifest, "spectrum"))))
        try:
            method, pair = self._connection_method_and_pair([frame for _row, frame in loaded])
            if pair == "All":
                raise ValueError("Select Region pair and one pair before comparing connectivity spectra.")
            count = 0
            for row, frame in loaded:
                subset = frame.loc[frame["method"].astype(str).eq(method) & frame["region_pair"].astype(str).eq(pair)].copy()
                if subset.empty:
                    continue
                if "component_index" in subset and subset["component_index"].notna().any():
                    subset = subset.loc[subset["component_index"].fillna(1).eq(subset["component_index"].dropna().min())]
                value = "value_strength" if "value_strength" in subset else "value_raw"
                curve = subset.groupby("frequency_hz", as_index=False)[value].mean().sort_values("frequency_hz")
                axis.plot(curve["frequency_hz"], curve[value], linewidth=1.2, alpha=0.8, label=str(row.subject_code))
                count += 1
            if not count:
                raise ValueError("The selected method/pair is absent from the included results.")
            axis.set_xlabel("Frequency (Hz)")
            axis.set_ylabel("Connectivity strength")
            axis.set_title(f"{method} | {pair} | individual saved-result spectra (n={count})")
            axis.grid(color="#dddddd", linewidth=0.6)
            axis.legend(ncol=2, fontsize=8)
        except (KeyError, ValueError) as exc:
            axis.text(0.5, 0.5, str(exc), ha="center", va="center", transform=axis.transAxes)
            axis.set_axis_off()

    def _plot_connectivity_matrices(self, selection: Any) -> None:
        if selection is None or selection.included.empty:
            axis = self.compare_figure.add_subplot(111)
            axis.text(0.5, 0.5, "No unambiguous saved connectivity result is available.", ha="center", va="center", transform=axis.transAxes)
            axis.set_axis_off()
            return
        loaded: list[tuple[Any, pd.DataFrame]] = []
        for row in selection.included.itertuples():
            manifest = load_result_manifest(self.store.paths.root / row.result_path)
            loaded.append((row, self._with_region_pair(load_table(manifest, "band_summary"))))
        try:
            method, _pair = self._connection_method_and_pair([frame for _row, frame in loaded])
            band = self.compare_band.currentText()
            if band == "All":
                raise ValueError("Select one frequency band before displaying region matrices.")
            filtered: list[tuple[Any, pd.DataFrame]] = []
            values: list[float] = []
            for row, frame in loaded:
                subset = frame.loc[frame["method"].astype(str).eq(method) & frame["band"].astype(str).eq(band)].copy()
                if "component_index" in subset and subset["component_index"].notna().any():
                    subset = subset.loc[subset["component_index"].fillna(1).eq(subset["component_index"].dropna().min())]
                if subset.empty:
                    continue
                value_column = "value_raw_or_summary" if method.lower() in {"dpli", "wpli2_debiased", "mim"} else "value_strength"
                values.extend(pd.to_numeric(subset[value_column], errors="coerce").dropna().tolist())
                subset["_matrix_value"] = pd.to_numeric(subset[value_column], errors="coerce")
                filtered.append((row, subset))
            if not filtered or not values:
                raise ValueError("The selected method/band is absent from the included results.")
            lower_method = method.lower()
            if lower_method == "dpli":
                norm: Normalize = TwoSlopeNorm(vmin=0.0, vcenter=0.5, vmax=1.0)
                cmap = "coolwarm"
            elif lower_method in {"mic", "wpli"}:
                norm = Normalize(vmin=0.0, vmax=1.0)
                cmap = "viridis"
            elif lower_method == "wpli2_debiased" and min(values) < 0 < max(values):
                bound = max(abs(min(values)), abs(max(values)))
                norm = TwoSlopeNorm(vmin=-bound, vcenter=0.0, vmax=bound)
                cmap = "coolwarm"
            else:
                vmin, vmax = min(values), max(values)
                if vmin == vmax:
                    vmax = vmin + 1.0
                norm = Normalize(vmin=vmin, vmax=vmax)
                cmap = "viridis"
            columns = 2
            rows = int(np.ceil(len(filtered) / columns))
            axes = np.asarray(self.compare_figure.subplots(rows, columns, squeeze=False)).ravel()
            for axis, (record, frame) in zip(axes, filtered, strict=False):
                regions = list(dict.fromkeys([*frame["region_a"].astype(str), *frame["region_b"].astype(str)]))
                matrix = np.full((len(regions), len(regions)), np.nan)
                region_index = {name: index for index, name in enumerate(regions)}
                for _index, item in frame.iterrows():
                    a, b = region_index[str(item["region_a"])], region_index[str(item["region_b"])]
                    matrix[a, b] = float(item["_matrix_value"])
                    if lower_method != "dpli":
                        matrix[b, a] = float(item["_matrix_value"])
                image = axis.imshow(matrix, cmap=cmap, norm=norm, interpolation="nearest")
                axis.set_xticks(range(len(regions)), regions, rotation=35, ha="right")
                axis.set_yticks(range(len(regions)), regions)
                axis.set_title(str(record.subject_code))
                self.compare_figure.colorbar(image, ax=axis, fraction=0.046, pad=0.04)
            for axis in axes[len(filtered):]:
                axis.set_visible(False)
            self.compare_figure.suptitle(f"{method} | {band} | one saved matrix per subject; common color scale")
        except (KeyError, ValueError) as exc:
            self.compare_figure.clear()
            axis = self.compare_figure.add_subplot(111)
            axis.text(0.5, 0.5, str(exc), ha="center", va="center", transform=axis.transAxes)
            axis.set_axis_off()

    def _plot_paired_comparison(
        self,
        axis: Any,
        first: Any,
        second: Any,
        table: str,
        value: str,
        groups: list[str],
        row_filters: dict[str, Any],
    ) -> None:
        paired = paired_subject_summary(
            self.store,
            first,
            second,
            table,
            value,
            groups,
            first_filters=row_filters,
            second_filters=row_filters,
        )
        if paired.empty:
            raise ValueError("no unambiguous subject pair is available")
        compatible = paired["compatibility_signature_first"].eq(paired["compatibility_signature_second"])
        palette = ["#34345C", "#9281BD", "#D06A45", "#3F8C78", "#4C78A8"]
        for index, row in enumerate(paired.itertuples()):
            color = palette[index % len(palette)] if bool(compatible.iloc[index]) else "#9E9E9E"
            axis.plot([0, 1], [getattr(row, f"{value}_first"), getattr(row, f"{value}_second")], marker="o", color=color, alpha=0.8, label=str(row.subject_code))
        axis.set_xticks([0, 1], [f"T{self.compare_timepoint.value():g}", f"T{self.compare_second_timepoint.value():g}"])
        axis.set_ylabel(value)
        axis.set_title(f"Paired by subject_id (complete pairs n={paired['subject_id'].nunique()}); grey = incompatible parameters")
        axis.grid(axis="y", color="#dddddd", linewidth=0.6)
        if len(paired) <= 12:
            axis.legend(ncol=2, fontsize=8)

    def _plot_psd_comparison(self, axis: Any, selection: Any) -> None:
        palette = ["#34345C", "#9281BD", "#D06A45", "#3F8C78", "#4C78A8"]
        groups: dict[tuple[str, str], list[tuple[np.ndarray, np.ndarray]]] = {}
        subject_count = 0
        for index, row in enumerate(selection.included.itertuples()):
            manifest = load_result_manifest(self.store.paths.root / row.result_path)
            frame = load_table(manifest, "psd_channel_summary")
            if not {"frequency_hz", "psd_value"}.issubset(frame.columns):
                continue
            curve = frame.groupby("frequency_hz", as_index=False)["psd_value"].mean().sort_values("frequency_hz")
            frequencies = curve["frequency_hz"].to_numpy(float)
            values = curve["psd_value"].to_numpy(float)
            color = palette[index % len(palette)]
            axis.plot(frequencies, values, color=color, alpha=0.55, linewidth=1.0, label=str(row.subject_code))
            groups.setdefault((str(row.group_label or "ungrouped"), str(row.compatibility_signature)), []).append((frequencies, values))
            subject_count += 1
        for group_index, ((group_label, _signature), curves) in enumerate(groups.items()):
            reference = curves[0][0]
            if len(curves) < 2 or not all(np.array_equal(reference, frequency) for frequency, _values in curves[1:]):
                continue
            mean_curve = np.nanmean(np.vstack([values for _frequency, values in curves]), axis=0)
            axis.plot(reference, mean_curve, color=palette[group_index % len(palette)], linewidth=2.4, linestyle="--", label=f"{group_label} mean (n={len(curves)})")
        axis.set_xlabel("Frequency (Hz)")
        axis.set_ylabel("PSD")
        axis.set_title(f"PSD: individual subject curves (n={subject_count}); means require identical compatible grids")
        axis.grid(color="#dddddd", linewidth=0.6)
        axis.legend(ncol=2, fontsize=8)

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        if self.mode != "manage" or not self._project_draft_dirty:
            event.accept()
            return
        answer = QtWidgets.QMessageBox.question(
            self,
            "项目有未保存更改",
            "项目结构或导入关联尚未正式保存。请选择保存、放弃修改或取消关闭。",
            QtWidgets.QMessageBox.StandardButton.Save
            | QtWidgets.QMessageBox.StandardButton.Discard
            | QtWidgets.QMessageBox.StandardButton.Cancel,
            QtWidgets.QMessageBox.StandardButton.Save,
        )
        if answer == QtWidgets.QMessageBox.StandardButton.Save:
            event.setAccepted(self.save_project())
        elif answer == QtWidgets.QMessageBox.StandardButton.Discard:
            event.setAccepted(self.discard_project_changes())
        else:
            event.ignore()
