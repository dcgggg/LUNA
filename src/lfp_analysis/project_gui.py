"""PySide6 project-management workspace for LUNA."""

from __future__ import annotations

import json
import os
import threading
import traceback
import uuid
from pathlib import Path
from typing import Any, ClassVar

import numpy as np
import pandas as pd
from PySide6 import QtCore, QtGui, QtSvg, QtWidgets

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
        duplicate_row.setToolTip("Duplicate the selected import row so one source can be assigned to another state or selection.")
        duplicate_row.clicked.connect(self._duplicate_selected_row)
        fill_down = QtWidgets.QPushButton("Fill current cell down")
        fill_down.setToolTip("Copy the selected editable epoch/time cell value to following import rows.")
        fill_down.clicked.connect(self._fill_current_down)
        fill_targets = QtWidgets.QPushButton("Fill target state down")
        fill_targets.setToolTip("Copy the selected row's target state to following import rows.")
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
        browse.setToolTip("选择新项目上级目录；实际路径会在下方预览。 / Choose the parent folder; the target path is previewed below.")
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
        generate_subjects.setToolTip("按 Prefix、Start、Count 和 Zero padding 生成被试名称列表。 / Generate subject codes from the fields below.")
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
        generate_states.setToolTip("Generate state rows from Start, End, Step, and Unit. This only edits the template form until applied.")
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
        save_button.setToolTip("Save a reusable structure definition only; it does not create project nodes or folders.")
        self.apply_button.setToolTip("Create or reuse subject/session/state records and folders in the currently open project.")
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


class ProjectFilterExportDialog(QtWidgets.QDialog):
    """Filter project data units without pairing, averaging, or plotting."""

    COLUMNS: ClassVar[list[str]] = [
        "subject_code", "group_label", "session_key", "session_date",
        "state_display_name", "condition_label", "timepoint_value",
        "timepoint_unit", "reference_event", "inspection_status",
        "data_unit_id", "source_path", "resolved_source_path",
        "result_status", "result_analysis_ids",
    ]

    def __init__(
        self,
        store: ProjectStore,
        parent: QtWidgets.QWidget | None = None,
        *,
        scope_query: dict[str, Any] | None = None,
        scope_label: str | None = None,
    ) -> None:
        super().__init__(parent)
        self.store = store
        self.scope_query = dict(scope_query or {"project_id": str(store.project["project_id"])})
        self.scope_label = scope_label or str(store.project["name"])
        self.setWindowTitle(f"LUNA — Filter / export data list — {store.project['name']}")
        self.resize(1240, 760)
        self._rows: list[dict[str, Any]] = []
        self._lists: dict[str, QtWidgets.QListWidget] = {}
        self._build_ui()
        self.refresh()

    @staticmethod
    def _checked_values(widget: QtWidgets.QListWidget) -> list[str]:
        all_item = widget.item(0)
        if all_item is not None and all_item.checkState() == QtCore.Qt.CheckState.Checked:
            return []
        return [
            widget.item(index).text()
            for index in range(1, widget.count())
            if widget.item(index).checkState() == QtCore.Qt.CheckState.Checked
        ]

    def _make_list(self, name: str, values: list[str]) -> QtWidgets.QListWidget:
        widget = QtWidgets.QListWidget()
        widget.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
        widget.setMaximumHeight(72)
        all_item = QtWidgets.QListWidgetItem("All")
        all_item.setCheckState(QtCore.Qt.CheckState.Checked)
        widget.addItem(all_item)
        for value in values:
            item = QtWidgets.QListWidgetItem(str(value))
            item.setCheckState(QtCore.Qt.CheckState.Unchecked)
            widget.addItem(item)
        widget.itemChanged.connect(lambda changed, current=widget: self._all_item_rule(changed, current))
        self._lists[name] = widget
        return widget

    @staticmethod
    def _all_item_rule(changed: QtWidgets.QListWidgetItem, widget: QtWidgets.QListWidget) -> None:
        if changed.text() == "All" and changed.checkState() == QtCore.Qt.CheckState.Checked:
            for index in range(1, widget.count()):
                widget.item(index).setCheckState(QtCore.Qt.CheckState.Unchecked)
        elif changed.text() != "All" and changed.checkState() == QtCore.Qt.CheckState.Checked:
            widget.item(0).setCheckState(QtCore.Qt.CheckState.Unchecked)

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        controls = QtWidgets.QGridLayout()
        units = self.store.data_units(**self.scope_query)
        choices = {
            "group": sorted({str(row.get("group_label") or "未设置") for row in units}),
            "subject": sorted({str(row.get("subject_code") or "未设置") for row in units}),
            "session": sorted({str(row.get("session_key") or "未设置") for row in units}),
            "state": sorted({str(row.get("state_display_name") or "未设置") for row in units}),
            "condition": sorted({str(row.get("condition_label") or "未设置") for row in units}),
        }
        labels = {"group": "Group", "subject": "Subject", "session": "Session", "state": "State", "condition": "Condition"}
        for column, key in enumerate(("group", "subject", "session", "state", "condition")):
            controls.addWidget(QtWidgets.QLabel(labels[key]), 0, column)
            controls.addWidget(self._make_list(key, choices[key]), 1, column)
        self.unit_combo = QtWidgets.QComboBox(); self.unit_combo.addItem("All", "")
        for value in sorted({str(row.get("timepoint_unit") or "未设置") for row in units}): self.unit_combo.addItem(value, value)
        self.reference_combo = QtWidgets.QComboBox(); self.reference_combo.addItem("All", "")
        for value in sorted({str(row.get("reference_event") or "未设置") for row in units}): self.reference_combo.addItem(value, value)
        self.inspection_combo = QtWidgets.QComboBox(); self.inspection_combo.addItem("All", "")
        for value in sorted({str(row.get("inspection_status") or "未设置") for row in units}): self.inspection_combo.addItem(value, value)
        self.module_combo = QtWidgets.QComboBox(); self.module_combo.addItem("All modules", "")
        scoped_ids = [str(row["data_unit_id"]) for row in units]
        scoped_results = self.store.analysis_results({"data_unit_ids": scoped_ids})
        for value in sorted({str(row.get("module_name") or "") for row in scoped_results if row.get("module_name")}): self.module_combo.addItem(value, value)
        self.exact_time_check = QtWidgets.QCheckBox("Exact timepoint")
        self.exact_time = QtWidgets.QDoubleSpinBox(); self.exact_time.setRange(-1_000_000, 1_000_000); self.exact_time.setDecimals(3); self.exact_time.setEnabled(False)
        self.exact_time_check.toggled.connect(self.exact_time.setEnabled)
        self.only_result_check = QtWidgets.QCheckBox("Only records with a saved current result")
        controls.addWidget(QtWidgets.QLabel("Time unit"), 2, 0); controls.addWidget(self.unit_combo, 3, 0)
        controls.addWidget(QtWidgets.QLabel("Reference event"), 2, 1); controls.addWidget(self.reference_combo, 3, 1)
        controls.addWidget(QtWidgets.QLabel("Inspection"), 2, 2); controls.addWidget(self.inspection_combo, 3, 2)
        controls.addWidget(QtWidgets.QLabel("Result module"), 2, 3); controls.addWidget(self.module_combo, 3, 3)
        time_row = QtWidgets.QHBoxLayout(); time_row.addWidget(self.exact_time_check); time_row.addWidget(self.exact_time); time_row.addStretch(1)
        controls.addLayout(time_row, 3, 4)
        controls.addWidget(self.only_result_check, 4, 0, 1, 3)
        self.scope_summary = QtWidgets.QLabel(f"Current scope: {self.scope_label} · {len(units)} data records before filters")
        self.scope_summary.setWordWrap(True)
        layout.addWidget(self.scope_summary)
        layout.addLayout(controls)
        actions = QtWidgets.QHBoxLayout()
        refresh = QtWidgets.QPushButton("Refresh list"); refresh.clicked.connect(self.refresh)
        clear_filters = QtWidgets.QPushButton("Clear filters"); clear_filters.clicked.connect(self.clear_filters)
        export_csv = QtWidgets.QPushButton("Export CSV"); export_csv.clicked.connect(lambda: self._export("csv"))
        export_json = QtWidgets.QPushButton("Export JSON"); export_json.clicked.connect(lambda: self._export("json"))
        for button in (refresh, clear_filters, export_csv, export_json): actions.addWidget(button)
        actions.addStretch(1)
        self.summary = QtWidgets.QLabel(); self.summary.setWordWrap(True); actions.addWidget(self.summary, stretch=1)
        layout.addLayout(actions)
        self.table = QtWidgets.QTableWidget(); self.table.setColumnCount(len(self.COLUMNS)); self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(len(self.COLUMNS) - 1, QtWidgets.QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, stretch=1)

    def _filters(self) -> dict[str, Any]:
        return {
            "group_label": self._checked_values(self._lists["group"]),
            "subject_code": self._checked_values(self._lists["subject"]),
            "session_key": self._checked_values(self._lists["session"]),
            "state_display_name": self._checked_values(self._lists["state"]),
            "condition_label": self._checked_values(self._lists["condition"]),
            "timepoint_unit": str(self.unit_combo.currentData() or ""),
            "reference_event": str(self.reference_combo.currentData() or ""),
            "inspection_status": str(self.inspection_combo.currentData() or ""),
            "module_name": str(self.module_combo.currentData() or ""),
            "timepoint_value": float(self.exact_time.value()) if self.exact_time_check.isChecked() else None,
            "only_result": bool(self.only_result_check.isChecked()),
        }

    def clear_filters(self) -> None:
        for widget in self._lists.values():
            with QtCore.QSignalBlocker(widget):
                for index in range(widget.count()):
                    widget.item(index).setCheckState(
                        QtCore.Qt.CheckState.Checked if index == 0 else QtCore.Qt.CheckState.Unchecked
                    )
        for widget in (self.unit_combo, self.reference_combo, self.inspection_combo, self.module_combo):
            widget.setCurrentIndex(0)
        self.exact_time_check.setChecked(False)
        self.only_result_check.setChecked(False)
        self.refresh()

    def refresh(self) -> None:
        filters = self._filters()
        base_units = self.store.data_units(**self.scope_query)
        base_ids = [str(row["data_unit_id"]) for row in base_units]
        result_rows = self.store.analysis_results({
            "calculation_status": "completed", "save_status": "saved", "result_validity": "current",
            "data_unit_ids": base_ids,
        })
        by_unit: dict[str, list[dict[str, Any]]] = {}
        for row in result_rows: by_unit.setdefault(str(row["data_unit_id"]), []).append(row)
        rows: list[dict[str, Any]] = []
        for source in base_units:
            values = {key: str(source.get(key) or "未设置") for key in ("group_label", "subject_code", "session_key", "state_display_name", "condition_label", "timepoint_unit", "reference_event", "inspection_status")}
            if any(filters[key] and values[key] not in filters[key] for key in ("group_label", "subject_code", "session_key", "state_display_name", "condition_label")): continue
            if filters["timepoint_unit"] and values["timepoint_unit"] != filters["timepoint_unit"]: continue
            if filters["reference_event"] and values["reference_event"] != filters["reference_event"]: continue
            if filters["inspection_status"] and values["inspection_status"] != filters["inspection_status"]: continue
            timepoint = source.get("timepoint_value")
            if filters["timepoint_value"] is not None and (timepoint is None or not np.isclose(float(timepoint), filters["timepoint_value"])): continue
            available = by_unit.get(str(source["data_unit_id"]), [])
            if filters["module_name"]: available = [row for row in available if str(row.get("module_name")) == filters["module_name"]]
            if filters["only_result"] and not available: continue
            rows.append({**source, "result_status": "; ".join(sorted({str(row.get("module_name")) for row in available})) or "缺少目标结果", "result_analysis_ids": "; ".join(str(row.get("analysis_id")) for row in available)})
        self._rows = rows
        self.table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            for column_index, column in enumerate(self.COLUMNS):
                value = row.get(column, "")
                self.table.setItem(row_index, column_index, QtWidgets.QTableWidgetItem("" if value is None else str(value)))
        self.table.resizeColumnsToContents()
        subject_count = len({row.get("subject_id") for row in rows}); session_count = len({row.get("session_id") for row in rows}); state_count = len({row.get("state_record_id") for row in rows}); result_count = sum(bool(row.get("result_analysis_ids")) for row in rows)
        self.scope_summary.setText(
            f"Current scope: {self.scope_label} · {len(base_units)} data records before filters · "
            f"{len(rows)} after filters"
        )
        self.summary.setText(f"匹配：{subject_count} 个被试、{session_count} 个 session、{state_count} 个 state、{len(rows)} 条数据记录；有目标结果 {result_count} 条。字段之间为且，同一字段勾选为或；缺少结果不会自动排除。")

    def _export(self, kind: str) -> None:
        suffix = ".csv" if kind == "csv" else ".json"
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Export data list", str(self.store.paths.exports / f"luna_data_list{suffix}"), f"{kind.upper()} (*{suffix})")
        if not path: return
        target = Path(path).expanduser().resolve(); target.parent.mkdir(parents=True, exist_ok=True)
        frame = pd.DataFrame(self._rows)
        if kind == "csv": frame.to_csv(target, index=False, encoding="utf-8-sig")
        else:
            payload = {"schema_version": 1, "project_id": self.store.project["project_id"], "scope": {"label": self.scope_label, "query": self.scope_query}, "filters": self._filters(), "counts": {"records": len(self._rows), "subjects": len({row.get("subject_id") for row in self._rows}), "sessions": len({row.get("session_id") for row in self._rows}), "states": len({row.get("state_record_id") for row in self._rows})}, "records": frame.where(pd.notna(frame), None).to_dict(orient="records")}
            target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        self.summary.setText(self.summary.text() + f" 已导出：{target}")

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        parent = self.parentWidget()
        while parent is not None and not isinstance(parent, ProjectWorkspace):
            parent = parent.parentWidget()
        if parent is not None and getattr(parent, "filter_export_dialog", None) is self:
            parent.filter_export_dialog = None
        event.accept()


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
        role = {"manage": "Project manager", "batch": "Batch analysis", "filter": "Data filter/export", "review": "Result review"}.get(mode, "Project")
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
                ("Filter/export list", self.open_filter_export),
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
        self.toolbar_actions: dict[str, QtGui.QAction] = {}
        for text, callback in actions:
            action = toolbar.addAction(text)
            action.triggered.connect(callback)
            self.toolbar_actions[text] = action
            action.setToolTip({
                "Import data": "Import FIF records; source files are copied and verified, then assigned to existing states.",
                "Save project": "Validate and confirm current project-structure/import draft changes. Analysis results are saved separately.",
                "Filter/export list": "Filter and export data records inside the selected hierarchy scope.",
                "Open in analysis": "Open the selected data record and restore saved results if available; does not run analysis.",
                "Add to batch": "Send only checked records from the currently displayed list to the batch workspace.",
                "Structure template": "Edit a reusable structure and apply it to this project; saving a template alone creates no project nodes.",
                "Edit mapping": "Review and save channel-to-region mapping for the selected data record.",
                "Organize data": "Copy checked external source files into this project and update their links; originals remain untouched.",
                "Refresh": "Reload project metadata and results while preserving the current tree selection when possible.",
                "Check duplicate states": "Review exact same-parent duplicate state records; this is not a general delete-data action.",
            }.get(text, "Reload this Project Manager view."))
        self.tabs = QtWidgets.QTabWidget()
        self.setCentralWidget(self.tabs)
        if self.mode == "manage":
            self.tabs.addTab(self._build_data_tab(), "Project data")
        elif self.mode == "batch":
            self.tabs.addTab(self._build_batch_tab(), "Batch analysis")
        elif self.mode == "filter":
            self.tabs.addTab(self._build_filter_tab(), "Filter / export list")
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
        self.data_actions: dict[str, QtWidgets.QPushButton] = {}
        for text, callback in (
            ("Add subject", self.add_subject),
            ("Add session", self.add_session),
            ("Add state", self.add_state),
            ("Edit selected", self.edit_selected_hierarchy),
            ("Edit selected metadata", self.edit_selected_data_metadata),
            ("Apply template", self.open_structure_template),
            ("Add to batch", self.add_selected_to_batch),
            ("Filter/export list", self.open_filter_export),
            ("Relocate source", self.relocate_selected_source),
            ("Previous data", lambda: self.open_adjacent(-1)),
            ("Next data", lambda: self.open_adjacent(1)),
        ):
            button = QtWidgets.QPushButton(text)
            button.clicked.connect(callback)
            help_text = {
                "Add subject": "Create a subject in this project. The project tree is the only data scope; save the project to formalize the draft.",
                "Add session": "Create a session under the selected subject. Select a subject node first.",
                "Add state": "Create a state under the selected session. Select a session node first.",
                "Edit selected": "Edit the selected subject, session, or state; this does not rename stable internal IDs.",
                "Edit selected metadata": "Edit group/condition metadata for selected data rows; if no row is selected, the selected data node is used.",
                "Apply template": "Instantiate the current saved structure template in this project; this is different from saving a reusable template.",
                "Add to batch": "Queue only checked rows in the currently displayed data list. It does not check every row automatically.",
                "Filter/export list": "Filter and export data records within the currently selected tree node; clearing filters keeps this scope.",
                "Relocate source": "Relink one selected data record to a file with the same fingerprint; no file is moved or deleted.",
                "Previous data": "Open the previous row in the currently displayed list.",
                "Next data": "Open the next row in the currently displayed list.",
            }
            button.setToolTip(help_text[text])
            self.data_actions[text] = button
            row.addWidget(button)
        row.addStretch(1)
        layout.addLayout(row)
        scope_row = QtWidgets.QHBoxLayout()
        self.current_range_summary = QtWidgets.QLabel()
        self.current_range_summary.setObjectName("currentDataRange")
        self.current_range_summary.setWordWrap(True)
        scope_row.addWidget(self.current_range_summary, 1)
        self.visible_data_summary = QtWidgets.QLabel()
        scope_row.addWidget(self.visible_data_summary)
        layout.addLayout(scope_row)
        filter_row = QtWidgets.QHBoxLayout()
        self.manage_search = QtWidgets.QLineEdit()
        self.manage_search.setPlaceholderText("Search within current scope: subject, group, session, state, condition, file")
        self.manage_search.setToolTip("Search only data records belonging to the selected project-tree node.")
        self.manage_search.textChanged.connect(self._refresh_data_table)
        filter_row.addWidget(self.manage_search, 1)
        self.manage_group_filter = QtWidgets.QComboBox()
        self.manage_group_filter.setToolTip("Filter groups only within the selected tree scope.")
        self.manage_condition_filter = QtWidgets.QComboBox()
        self.manage_condition_filter.setToolTip("Filter conditions only within the selected tree scope.")
        self.manage_inspection_filter = QtWidgets.QComboBox()
        self.manage_inspection_filter.setToolTip("Filter inspection status only within the selected tree scope.")
        for label, combo in (("Group", self.manage_group_filter), ("Condition", self.manage_condition_filter), ("Inspection", self.manage_inspection_filter)):
            combo.addItem(f"All {label.lower()}", "")
            combo.currentIndexChanged.connect(self._refresh_data_table)
            filter_row.addWidget(combo)
        self.clear_data_filters_button = QtWidgets.QPushButton("Clear filters")
        self.clear_data_filters_button.setToolTip("Clear search and extra filters without changing the selected tree scope.")
        self.clear_data_filters_button.clicked.connect(self.clear_data_filters)
        filter_row.addWidget(self.clear_data_filters_button)
        self.clear_visible_batch_button = QtWidgets.QPushButton("Clear visible batch checks")
        self.clear_visible_batch_button.setToolTip("Uncheck batch boxes in the visible list only; this does not alter project records.")
        self.clear_visible_batch_button.clicked.connect(self.clear_visible_batch_checks)
        filter_row.addWidget(self.clear_visible_batch_button)
        layout.addLayout(filter_row)
        self.empty_data_message = QtWidgets.QLabel()
        self.empty_data_message.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.empty_data_message.setStyleSheet("color: #64748b; padding: 6px;")
        self.empty_data_message.hide()
        layout.addWidget(self.empty_data_message)
        splitter = QtWidgets.QSplitter()
        self.hierarchy = QtWidgets.QTreeWidget()
        self.hierarchy.setHeaderLabels(["Project hierarchy"])
        self.hierarchy.setMinimumWidth(320)
        self.hierarchy.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.hierarchy.customContextMenuRequested.connect(self._hierarchy_context_menu)
        self.hierarchy.itemDoubleClicked.connect(self._open_tree_item)
        splitter.addWidget(self.hierarchy)
        self.data_table = QtWidgets.QTableWidget()
        self.data_table.setColumnCount(11)
        self.data_table.setHorizontalHeaderLabels(["Batch", "Subject", "Group", "Session", "State", "Condition", "Timepoint", "File", "Validity", "Module status", "data_unit_id"])
        self.data_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.data_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.data_table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.data_table.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.data_table.customContextMenuRequested.connect(self._data_table_context_menu)
        self.data_table.horizontalHeader().setSectionResizeMode(7, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.data_table.doubleClicked.connect(self.open_selected)
        self.data_table.itemChanged.connect(self._update_manage_action_states)
        self.data_table.itemSelectionChanged.connect(self._update_manage_action_states)
        self.data_table.setColumnHidden(10, True)
        splitter.addWidget(self.data_table)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, stretch=1)
        self.state_resources_label = QtWidgets.QLabel("选择状态后查看电生理、行为附件和评分摘要。")
        self.state_resources_label.setWordWrap(True)
        self.state_resources_label.setStyleSheet("color: #5f6b76;")
        self.state_resources_label.setToolTip("行为数据与同步信息仅作为可追溯元数据保存；不根据同名文件推断同步关系。")
        layout.addWidget(self.state_resources_label)
        self.hierarchy.currentItemChanged.connect(self._on_hierarchy_selection_changed)
        self._update_manage_action_states()
        return widget

    def _build_filter_tab(self) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)
        layout.addWidget(QtWidgets.QLabel("Filter data records and export a machine-readable list. This view does not compare, pair, average, or calculate across records."))
        self.filter_export_dialog = ProjectFilterExportDialog(self.store, widget)
        self.filter_export_dialog.setWindowFlags(QtCore.Qt.WindowType.Widget)
        layout.addWidget(self.filter_export_dialog)
        return widget

    def open_filter_export(self) -> None:
        if self.mode != "manage":
            return
        scope = self._current_data_scope()
        self.filter_export_dialog = ProjectFilterExportDialog(
            self.store, self, scope_query=scope["query"], scope_label=scope["label"]
        )
        self.filter_export_dialog.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.filter_export_dialog.setModal(False)
        self.filter_export_dialog.show()
        self.filter_export_dialog.raise_()
        self.filter_export_dialog.activateWindow()

    def _data_table_context_menu(self, position: QtCore.QPoint) -> None:
        clicked = self.data_table.itemAt(position)
        selected_rows = {index.row() for index in self.data_table.selectionModel().selectedRows()}
        if clicked is not None and clicked.row() not in selected_rows:
            self.data_table.clearSelection()
            self.data_table.selectRow(clicked.row())
        menu = QtWidgets.QMenu(self)
        edit_action = menu.addAction("Edit selected group/condition")
        edit_action.setToolTip("Edit group for selected subject(s) and condition for selected state(s). Changes remain in the project draft until Save project.")
        edit_action.triggered.connect(self.edit_selected_data_metadata)
        menu.exec(self.data_table.viewport().mapToGlobal(position))

    @staticmethod
    def _bulk_text_value(parent: QtWidgets.QWidget, title: str, field: str, current_values: set[str]) -> tuple[bool, str]:
        dialog = QtWidgets.QDialog(parent)
        dialog.setWindowTitle(title)
        form = QtWidgets.QFormLayout(dialog)
        current = "多个值" if len(current_values) > 1 else (next(iter(current_values), "") if current_values else "未设置")
        form.addRow("当前值", QtWidgets.QLabel(current))
        edit = QtWidgets.QLineEdit()
        if len(current_values) == 1:
            edit.setText(next(iter(current_values)))
        edit.setPlaceholderText(f"输入新的 {field}；勾选应用后留空表示清空")
        form.addRow(field, edit)
        apply_all = QtWidgets.QCheckBox("将此值应用到所有选中记录")
        apply_all.setChecked(len(current_values) <= 1)
        form.addRow(apply_all)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject); form.addRow(buttons)
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted or not apply_all.isChecked():
            return False, ""
        return True, edit.text().strip()

    def edit_selected_data_metadata(self) -> None:
        selected_rows = sorted({index.row() for index in self.data_table.selectionModel().selectedRows()}) if hasattr(self, "data_table") else []
        if not selected_rows:
            current = self._current_data_unit()
            selected_ids = [str(current["data_unit_id"])] if current else []
        else:
            selected_ids = [str(self.data_table.item(row, 10).text()) for row in selected_rows if self.data_table.item(row, 10)]
        units = [row for row in self.store.data_units(data_unit_ids=selected_ids)]
        if not units:
            QtWidgets.QMessageBox.information(self, "Edit metadata", "Select one or more data records first.")
            return
        subject_ids = {str(row["subject_id"]) for row in units}
        state_ids = {str(row["state_record_id"]) for row in units}
        subject_rows = {str(row["subject_id"]): row for row in self.store.subjects() if str(row["subject_id"]) in subject_ids}
        state_rows = {str(row["state_record_id"]): row for row in self.store.state_records() if str(row["state_record_id"]) in state_ids}
        group_values = {str(row.get("group_label") or "") for row in subject_rows.values()}
        condition_values = {str(row.get("condition_label") or "") for row in state_rows.values()}
        change_group, group = self._bulk_text_value(self, "Edit group", "Group", group_values)
        if not change_group:
            return
        change_condition, condition = self._bulk_text_value(self, "Edit condition", "Condition", condition_values)
        if not change_condition:
            return
        self._begin_project_edit()
        for subject_id, row in subject_rows.items():
            self.store.update_subject(subject_id, subject_code=str(row["subject_code"]), group_label=group)
        for state_id, row in state_rows.items():
            self.store.update_state_record(
                state_id,
                display_name=str(row["display_name"]),
                condition_label=condition,
                timepoint_value=row.get("timepoint_value"),
                timepoint_unit=str(row.get("timepoint_unit") or "min"),
                reference_event=str(row.get("reference_event") or ""),
                actual_start=str(row.get("actual_start") or ""),
                actual_end=str(row.get("actual_end") or ""),
            )
        self.refresh_all()
        self.statusBar().showMessage(f"Updated group for {len(subject_rows)} subject(s) and condition for {len(state_rows)} state(s). Save project to formalize the metadata change.", 10000)

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
        temporary = self._project_draft_marker.with_name(
            f".{self._project_draft_marker.name}.{uuid.uuid4().hex}.tmp"
        )
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as stream:
                stream.write(json.dumps(payload, ensure_ascii=False, indent=2))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self._project_draft_marker)
        finally:
            temporary.unlink(missing_ok=True)

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

    def _restore_project_draft_marker_state(self, payload: dict[str, Any], backup: Path) -> None:
        self._project_draft_backup = backup
        self._project_draft_dirty = True
        self._project_draft_initial_files = set(map(str, payload.get("initial_files", [])))
        self._project_draft_initial_dirs = set(map(str, payload.get("initial_dirs", [])))
        self._project_draft_created_files = set(map(str, payload.get("created_files", [])))
        self._project_draft_created_dirs = set(map(str, payload.get("created_dirs", [])))
        # A process may stop after SQLite creates a hierarchy folder but before
        # the marker is refreshed. Discover only new directories here; discard
        # removes them only when they are still empty.
        _, current_directories = self._project_content_snapshot()
        self._project_draft_created_dirs.update(current_directories - self._project_draft_initial_dirs)

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
                self._restore_project_draft_marker_state(payload, backup)
                self.discard_project_changes()
            elif answer == QtWidgets.QMessageBox.StandardButton.RestoreDefaults:
                self._restore_project_draft_marker_state(payload, backup)
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
        lfp_count = len(self.store.data_units(state_record_id=state_id))
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
        self.batch_checked_only.setToolTip("This filters by the data inspection status, not by the batch checkbox.")
        self.batch_checked_only.toggled.connect(self._refresh_batch_data_selector)
        self.batch_selected_only = QtWidgets.QCheckBox("Selected for batch only")
        self.batch_selected_only.setToolTip("Show the persistent batch selection, including records hidden by the search or inspection filter.")
        self.batch_selected_only.toggled.connect(self._refresh_batch_data_selector)
        select_visible = QtWidgets.QPushButton("Select filtered")
        select_visible.setToolTip("Add every currently visible row to the cross-filter batch selection.")
        select_visible.clicked.connect(lambda: self._set_batch_visible_checked(True))
        clear_selection = QtWidgets.QPushButton("Clear all selected")
        clear_selection.setToolTip("Remove all batch checks, including records currently hidden by filters. This does not delete project data.")
        clear_selection.clicked.connect(self._clear_all_batch_selection)
        filter_row.addWidget(self.batch_search, 1); filter_row.addWidget(self.batch_checked_only); filter_row.addWidget(self.batch_selected_only); filter_row.addWidget(select_visible); filter_row.addWidget(clear_selection)
        layout.addLayout(filter_row)
        self.batch_data_table = QtWidgets.QTableWidget(0, 9)
        self.batch_data_table.setHorizontalHeaderLabels(["Batch", "Subject", "Session", "State", "Condition", "Timepoint", "Inspection", "Source", "data_unit_id"])
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
        self.batch_selection_label.setToolTip("The count includes batch selections across all current batch filters.")
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
        if hasattr(self, "state_resources_label"):
            self._refresh_state_resources()

    def _tree_identity(self, item: QtWidgets.QTreeWidgetItem | None = None) -> tuple[str, str]:
        item = item if item is not None else (self.hierarchy.currentItem() if hasattr(self, "hierarchy") else None)
        identity = item.data(0, QtCore.Qt.ItemDataRole.UserRole) if item is not None else None
        if isinstance(identity, (tuple, list)) and len(identity) == 2:
            return str(identity[0]), str(identity[1])
        project_id = str(self.store.project["project_id"])
        return "project", project_id

    def _current_data_scope(self) -> dict[str, Any]:
        """Resolve the selected tree node to an exact ID query and readable path."""
        kind, stable_id = self._tree_identity()
        project = self.store.project
        project_id = str(project["project_id"])
        if kind == "project" and stable_id == project_id:
            return {"kind": "project", "id": project_id, "query": {"project_id": project_id}, "label": project["name"]}
        if kind == "subject":
            rows = self.store.query(
                "SELECT subject_code FROM subjects WHERE subject_id=? AND project_id=?",
                (stable_id, project_id),
            )
            if rows:
                return {"kind": kind, "id": stable_id, "query": {"subject_id": stable_id}, "label": f"{project['name']} / {rows[0]['subject_code']}"}
        elif kind == "session":
            rows = self.store.query(
                "SELECT u.subject_code,s.session_key FROM sessions s JOIN subjects u ON u.subject_id=s.subject_id WHERE s.session_id=? AND u.project_id=?",
                (stable_id, project_id),
            )
            if rows:
                row = rows[0]
                return {"kind": kind, "id": stable_id, "query": {"session_id": stable_id}, "label": f"{project['name']} / {row['subject_code']} / {row['session_key']}"}
        elif kind == "state":
            rows = self.store.query(
                "SELECT u.subject_code,s.session_key,r.display_name FROM state_records r JOIN sessions s ON s.session_id=r.session_id JOIN subjects u ON u.subject_id=s.subject_id WHERE r.state_record_id=? AND u.project_id=?",
                (stable_id, project_id),
            )
            if rows:
                row = rows[0]
                return {"kind": kind, "id": stable_id, "query": {"state_record_id": stable_id}, "label": f"{project['name']} / {row['subject_code']} / {row['session_key']} / {row['display_name']}"}
        elif kind == "data":
            rows = self.store.data_units(data_unit_id=stable_id, project_id=project_id)
            if rows:
                row = rows[0]
                return {
                    "kind": kind,
                    "id": stable_id,
                    "query": {"data_unit_id": stable_id},
                    "label": f"{project['name']} / {row['subject_code']} / {row['session_key']} / {row['state_display_name']} / {Path(row['source_path']).name}",
                }
        return {"kind": "project", "id": project_id, "query": {"project_id": project_id}, "label": project["name"]}

    def _on_hierarchy_selection_changed(self, _current: Any = None, _previous: Any = None) -> None:
        if hasattr(self, "data_table"):
            self._refresh_data_table()
        self._refresh_state_resources()
        self._update_manage_action_states()

    def clear_data_filters(self) -> None:
        with QtCore.QSignalBlocker(self.manage_search):
            self.manage_search.clear()
        for combo in (self.manage_group_filter, self.manage_condition_filter, self.manage_inspection_filter):
            with QtCore.QSignalBlocker(combo):
                combo.setCurrentIndex(0)
        self._refresh_data_table()

    def clear_visible_batch_checks(self) -> None:
        with QtCore.QSignalBlocker(self.data_table):
            for row in range(self.data_table.rowCount()):
                item = self.data_table.item(row, 0)
                if item is not None:
                    item.setCheckState(QtCore.Qt.CheckState.Unchecked)
        self._update_manage_action_states()

    def _update_manage_action_states(self, *_args: Any) -> None:
        if not hasattr(self, "data_actions") or not hasattr(self, "hierarchy"):
            return
        kind, _stable_id = self._tree_identity()
        selected_rows = self.data_table.selectionModel().selectedRows() if hasattr(self, "data_table") else []
        checked_count = len(self._selected_data_unit_ids()) if hasattr(self, "data_table") else 0
        self.data_actions["Add subject"].setEnabled(True)
        self.data_actions["Add session"].setEnabled(kind == "subject")
        self.data_actions["Add state"].setEnabled(kind == "session")
        self.data_actions["Edit selected"].setEnabled(kind in {"subject", "session", "state"})
        self.data_actions["Edit selected metadata"].setEnabled(bool(selected_rows) or kind == "data")
        if "Open in analysis" in self.toolbar_actions:
            self.toolbar_actions["Open in analysis"].setEnabled(len(selected_rows) == 1 or kind == "data")
        self.data_actions["Add to batch"].setEnabled(checked_count > 0)
        if "Add to batch" in self.toolbar_actions:
            self.toolbar_actions["Add to batch"].setEnabled(checked_count > 0)
        if "Organize data" in self.toolbar_actions:
            self.toolbar_actions["Organize data"].setEnabled(checked_count > 0)
        self.data_actions["Relocate source"].setEnabled(len(selected_rows) == 1 or kind == "data")
        has_rows = bool(getattr(self, "data_table", None) and self.data_table.rowCount())
        self.data_actions["Previous data"].setEnabled(has_rows)
        self.data_actions["Next data"].setEnabled(has_rows)

    def _refresh_hierarchy(self) -> None:
        expanded: set[tuple[str, str]] = set()
        selection_chain: list[tuple[str, str]] = []
        if self.hierarchy.topLevelItemCount():
            iterator = QtWidgets.QTreeWidgetItemIterator(self.hierarchy)
            while iterator.value() is not None:
                item = iterator.value()
                identity = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
                if isinstance(identity, tuple) and len(identity) == 2:
                    stable_identity = (str(identity[0]), str(identity[1]))
                    if item.isExpanded():
                        expanded.add(stable_identity)
                iterator += 1
            selected_item = self.hierarchy.currentItem()
            while selected_item is not None:
                identity = selected_item.data(0, QtCore.Qt.ItemDataRole.UserRole)
                if isinstance(identity, (tuple, list)) and len(identity) == 2:
                    selection_chain.append((str(identity[0]), str(identity[1])))
                selected_item = selected_item.parent()
        blocker = QtCore.QSignalBlocker(self.hierarchy)
        self.hierarchy.clear()
        units = self.store.data_units()
        by_state: dict[str, list[dict[str, Any]]] = {}
        for unit in units:
            by_state.setdefault(str(unit["state_record_id"]), []).append(unit)
        root = QtWidgets.QTreeWidgetItem([self.store.project["name"]])
        root.setData(0, QtCore.Qt.ItemDataRole.UserRole, ("project", self.store.project["project_id"]))
        root.setToolTip(0, str(self.store.paths.root))
        self.hierarchy.addTopLevelItem(root)
        items_by_identity: dict[tuple[str, str], QtWidgets.QTreeWidgetItem] = {
            ("project", str(self.store.project["project_id"])): root
        }
        for subject in self.store.subjects():
            subject_sessions = self.store.sessions(subject["subject_id"])
            subject_item = QtWidgets.QTreeWidgetItem([f"{subject['subject_code']}  ({len(subject_sessions)} sessions)"])
            subject_item.setData(0, QtCore.Qt.ItemDataRole.UserRole, ("subject", subject["subject_id"]))
            items_by_identity[("subject", str(subject["subject_id"]))] = subject_item
            if subject.get("relative_path"):
                subject_item.setToolTip(0, str(self.store.paths.root / Path(subject["relative_path"])))
            root.addChild(subject_item)
            for session in subject_sessions:
                session_states = self.store.state_records(session["session_id"])
                session_item = QtWidgets.QTreeWidgetItem([f"{session['session_key']}  ({len(session_states)} states)"])
                session_item.setData(0, QtCore.Qt.ItemDataRole.UserRole, ("session", session["session_id"]))
                items_by_identity[("session", str(session["session_id"]))] = session_item
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
                    items_by_identity[("state", str(state["state_record_id"]))] = state_item
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
                        items_by_identity[("data", str(unit["data_unit_id"]))] = data_item
                        data_item.setToolTip(
                            0,
                            f"dataset_id: {unit['data_unit_id']}\n"
                            f"Project path: {unit.get('source_path', '')}\n"
                            f"Inspection revision: {int(unit.get('inspection_revision') or 0)}",
                        )
                        state_item.addChild(data_item)
        root.setExpanded(True)
        for stable_identity in expanded:
            if stable_identity in items_by_identity:
                items_by_identity[stable_identity].setExpanded(True)
        selected = next((identity for identity in selection_chain if identity in items_by_identity), None)
        if selected is None:
            selected = ("project", str(self.store.project["project_id"]))
        selected_item = items_by_identity[selected]
        self.hierarchy.setCurrentItem(selected_item)
        parent = selected_item.parent()
        while parent is not None:
            parent.setExpanded(True)
            parent = parent.parent()
        del blocker

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

    @staticmethod
    def _refresh_scope_filter(combo: QtWidgets.QComboBox, values: set[str], all_label: str, selected: str | None) -> None:
        with QtCore.QSignalBlocker(combo):
            combo.clear()
            combo.addItem(all_label, "")
            for value in sorted(values, key=str.casefold):
                combo.addItem(value, value)
            index = combo.findData(selected or "")
            combo.setCurrentIndex(max(0, index))

    def _refresh_data_table(self, *_args: Any) -> None:
        scope = self._current_data_scope()
        scope_key = (scope["kind"], scope["id"])
        scope_changed = scope_key != getattr(self, "_last_data_scope_key", None)
        previous_checks: dict[str, bool] = {}
        if not scope_changed and hasattr(self, "data_table"):
            for row in range(self.data_table.rowCount()):
                id_item = self.data_table.item(row, 10)
                batch_item = self.data_table.item(row, 0)
                if id_item is not None and batch_item is not None:
                    previous_checks[id_item.text()] = batch_item.checkState() == QtCore.Qt.CheckState.Checked
        units = self.store.data_units(**scope["query"])
        old_filter_values = (
            str(self.manage_group_filter.currentData() or ""),
            str(self.manage_condition_filter.currentData() or ""),
            str(self.manage_inspection_filter.currentData() or ""),
        )
        self._refresh_scope_filter(self.manage_group_filter, {str(row.get("group_label") or "未设置") for row in units}, "All groups", old_filter_values[0])
        self._refresh_scope_filter(self.manage_condition_filter, {str(row.get("condition_label") or "未设置") for row in units}, "All conditions", old_filter_values[1])
        self._refresh_scope_filter(self.manage_inspection_filter, {str(row.get("inspection_status") or "unchecked") for row in units}, "All inspection states", old_filter_values[2])
        query = self.manage_search.text().strip().casefold()
        group_filter = str(self.manage_group_filter.currentData() or "")
        condition_filter = str(self.manage_condition_filter.currentData() or "")
        inspection_filter = str(self.manage_inspection_filter.currentData() or "")
        active_filters = []
        if query:
            active_filters.append(f"搜索={self.manage_search.text().strip()}")
        if group_filter:
            active_filters.append(f"Group={group_filter}")
        if condition_filter:
            active_filters.append(f"Condition={condition_filter}")
        if inspection_filter:
            active_filters.append(f"Inspection={inspection_filter}")
        filtered: list[dict[str, Any]] = []
        for unit in units:
            if group_filter and str(unit.get("group_label") or "未设置") != group_filter:
                continue
            if condition_filter and str(unit.get("condition_label") or "未设置") != condition_filter:
                continue
            if inspection_filter and str(unit.get("inspection_status") or "unchecked") != inspection_filter:
                continue
            haystack = " ".join(str(unit.get(key) or "") for key in (
                "subject_code", "group_label", "session_key", "state_display_name", "condition_label", "source_path"
            )).casefold()
            if query and query not in haystack:
                continue
            filtered.append(unit)
        ids = [str(unit["data_unit_id"]) for unit in filtered]
        status_by_data: dict[str, list[str]] = {}
        for result in self.store.analysis_results({"active": 1, "data_unit_ids": ids}):
            status_by_data.setdefault(str(result["data_unit_id"]), []).append(
                f"{result['module_name']}: {result['calculation_status']}/{result['save_status']}/"
                f"{result.get('result_validity', 'current')}/{result['review_status']}"
            )
        with QtCore.QSignalBlocker(self.data_table):
            self.data_table.setRowCount(len(filtered))
            for row, unit in enumerate(filtered):
                use = QtWidgets.QTableWidgetItem()
                use.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
                use.setCheckState(QtCore.Qt.CheckState.Checked if previous_checks.get(str(unit["data_unit_id"]), False) else QtCore.Qt.CheckState.Unchecked)
                use.setToolTip("Only checked records in the currently displayed list are added to batch.")
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
        self.data_table.setRowCount(len(filtered))
        self.data_table.clearSelection()
        self.data_table.resizeColumnsToContents()
        self.data_table.horizontalHeader().setSectionResizeMode(7, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self._last_data_scope_key = scope_key
        filter_suffix = f"  |  当前筛选生效：{'；'.join(active_filters)}" if active_filters else ""
        self.current_range_summary.setText(f"当前范围：{scope['label']}{filter_suffix}")
        self.visible_data_summary.setText(f"数据记录：{len(filtered)} 条 / 范围内 {len(units)} 条")
        self.visible_data_summary.setToolTip("范围内数量是节点总数；左侧搜索和筛选仅改变当前显示数量，不扩大范围。")
        if not units:
            self.empty_data_message.setText("当前节点暂无数据记录。可直接在此状态导入数据。")
            self.empty_data_message.show()
        elif not filtered:
            self.empty_data_message.setText("当前筛选条件下没有符合条件的数据记录。清除筛选不会改变当前目录范围。")
            self.empty_data_message.show()
        else:
            self.empty_data_message.hide()
        self._update_manage_action_states()

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
        selected_only = self.batch_selected_only.isChecked()
        units = []
        for unit in self.store.data_units():
            haystack = " ".join(str(unit.get(key, "")) for key in ("subject_code", "session_key", "state_display_name", "condition_label", "timepoint_value", "source_path")).lower()
            if query and query not in haystack:
                continue
            if checked_only and str(unit.get("inspection_status", "unchecked")) != "checked" and unit["data_unit_id"] not in self.batch_selected_ids:
                continue
            if selected_only and unit["data_unit_id"] not in self.batch_selected_ids:
                continue
            units.append(unit)
        with QtCore.QSignalBlocker(self.batch_data_table):
            self.batch_data_table.setRowCount(len(units))
            for row, unit in enumerate(units):
                use = QtWidgets.QTableWidgetItem(); use.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
                use.setCheckState(QtCore.Qt.CheckState.Checked if unit["data_unit_id"] in old_selected else QtCore.Qt.CheckState.Unchecked)
                self.batch_data_table.setItem(row, 0, use)
                values = [unit["subject_code"], unit["session_key"], unit["state_display_name"], unit.get("condition_label", ""), "" if unit.get("timepoint_value") is None else f"{unit['timepoint_value']:g} {unit.get('timepoint_unit') or ''}", unit.get("inspection_status", "unchecked"), Path(unit["source_path"]).name, unit["data_unit_id"]]
                for column, value in enumerate(values, 1):
                    self.batch_data_table.setItem(row, column, QtWidgets.QTableWidgetItem(str(value or "")))
        self._update_batch_selection_label()

    def _update_batch_selection_label(self, *_args: Any) -> None:
        if hasattr(self, "batch_selection_label"):
            self.batch_selection_label.setText(f"{len(self._selected_data_unit_ids())} data units selected across filters")

    def _set_batch_visible_checked(self, checked: bool) -> None:
        with QtCore.QSignalBlocker(self.batch_data_table):
            for row in range(self.batch_data_table.rowCount()):
                self.batch_data_table.item(row, 0).setCheckState(QtCore.Qt.CheckState.Checked if checked else QtCore.Qt.CheckState.Unchecked)
        self._update_batch_selection_label()

    def _clear_all_batch_selection(self) -> None:
        self.batch_selected_ids.clear()
        self._refresh_batch_data_selector()

    def _current_data_unit(self) -> dict[str, Any] | None:
        selected_rows = sorted({index.row() for index in self.data_table.selectionModel().selectedRows()}) if hasattr(self, "data_table") else []
        if len(selected_rows) == 1:
            item = self.data_table.item(selected_rows[0], 10)
            if item is not None:
                matches = self.store.data_units(data_unit_id=item.text())
                return matches[0] if matches else None
        if len(selected_rows) > 1:
            return None
        item = self.hierarchy.currentItem() if hasattr(self, "hierarchy") else None
        identity = item.data(0, QtCore.Qt.ItemDataRole.UserRole) if item else None
        if isinstance(identity, (tuple, list)) and len(identity) == 2 and identity[0] == "data":
            matches = self.store.data_units(data_unit_id=str(identity[1]))
            return matches[0] if matches else None
        return None

    def _open_tree_item(self, item: QtWidgets.QTreeWidgetItem, _column: int = 0) -> None:
        identity = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if isinstance(identity, (tuple, list)) and len(identity) == 2 and identity[0] == "data":
            self.open_data_unit_by_id(str(identity[1]))

    def open_data_unit_by_id(self, data_unit_id: str) -> None:
        rows = self.store.data_units(data_unit_id=data_unit_id)
        if not rows:
            self.statusBar().showMessage("所选数据记录已不存在，请刷新项目目录。", 8000)
            return
        self._open_data_unit(rows[0])

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
            if not ok:
                return
            session_date, ok = QtWidgets.QInputDialog.getText(self, "Edit session", "Session date (optional)", text=str(row.get("session_date") or ""))
            if not ok:
                return
            sort_order, ok = QtWidgets.QInputDialog.getInt(
                self,
                "Edit session",
                "Display order (lower first)",
                value=int(row.get("sort_order") or 0),
                minValue=0,
                maxValue=2_147_483_647,
            )
            if ok:
                self._begin_project_edit()
                self.store.update_session(
                    stable_id,
                    session_key=key,
                    experiment_name=experiment,
                    session_date=session_date,
                    notes=str(row.get("notes") or ""),
                    sort_order=sort_order,
                )
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
            self.statusBar().showMessage("请选择一条数据记录后再打开分析。", 5000)
            return
        self._open_data_unit(unit)

    def _open_data_unit(self, unit: dict[str, Any]) -> None:
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

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        if self.mode != "manage" or not self._project_draft_dirty:
            event.accept()
        else:
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
        if event.isAccepted():
            # Filter/export windows capture a stable scope and may be visible
            # independently of the manager. Destroy them only after Save or
            # Discard accepts closing; Cancel must leave them intact.
            for dialog in self.findChildren(ProjectFilterExportDialog):
                dialog.close()
                dialog.deleteLater()
            self.filter_export_dialog = None
