from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from lfp_analysis.project_store import ProjectStore

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _workspace(store: ProjectStore, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    from lfp_analysis.project_gui import ProjectWorkspace

    app = QApplication.instance() or QApplication([])
    window = ProjectWorkspace(store, PROJECT_ROOT / "configs" / "luna.yaml", PROJECT_ROOT / "metadata")
    return app, window


def _crash_after_edit(project_root: Path, edit_statements: str) -> subprocess.CompletedProcess[str]:
    child_script = f"""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / 'src'))
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from PySide6.QtWidgets import QApplication
from lfp_analysis.project_gui import ProjectWorkspace
from lfp_analysis.project_store import ProjectStore
root = Path(sys.argv[1])
app = QApplication([])
store = ProjectStore(root)
window = ProjectWorkspace(store, Path('configs/luna.yaml'), Path('metadata'))
window._begin_project_edit()
{edit_statements}
# Abruptly stop after SQLite commits, before orderly GUI cleanup.
os._exit(73)
"""
    return subprocess.run(
        [sys.executable, "-c", child_script, str(project_root)],
        cwd=PROJECT_ROOT,
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def test_save_and_discard_define_second_reader_visibility(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    store = ProjectStore.create(tmp_path / "project", "Draft visibility")
    subject_id = store.add_subject("Mouse01", "GroupA")
    app, window = _workspace(store, monkeypatch)

    window._begin_project_edit()
    store.update_subject(subject_id, subject_code="Mouse01", group_label="DraftGroup")
    reader = ProjectStore(store.paths.root)
    assert reader.subjects()[0]["group_label"] == "DraftGroup"
    assert window._project_draft_marker.is_file()
    assert window._project_draft_backup is not None and window._project_draft_backup.is_file()

    assert window.discard_project_changes()
    assert reader.subjects()[0]["group_label"] == "GroupA"
    assert ProjectStore(store.paths.root).subjects()[0]["group_label"] == "GroupA"
    assert not window._project_draft_marker.exists()

    window._begin_project_edit()
    store.update_subject(subject_id, subject_code="Mouse01", group_label="SavedGroup")
    assert reader.subjects()[0]["group_label"] == "SavedGroup"
    backup = window._project_draft_backup
    assert backup is not None and backup.is_file()
    assert window.save_project()
    assert not window._project_draft_marker.exists()
    assert not backup.exists()
    assert ProjectStore(store.paths.root).subjects()[0]["group_label"] == "SavedGroup"

    window.close()
    app.processEvents()


def test_process_crash_reopens_draft_and_discard_protects_directories(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    store = ProjectStore.create(tmp_path / "project", "Crash recovery")
    store.add_subject("Baseline")
    protected_file = store.paths.subjects / "Baseline" / "keep.txt"
    protected_file.write_text("pre-existing project content", encoding="utf-8")

    child = _crash_after_edit(
        store.paths.root,
        "store.add_subject('DraftSubject')\nstore.add_subject('EmptyDraftSubject')",
    )
    assert child.returncode == 73, child.stderr

    reopened_store = ProjectStore(store.paths.root)
    assert {row["subject_code"] for row in reopened_store.subjects()} == {
        "Baseline", "DraftSubject", "EmptyDraftSubject",
    }
    marker = reopened_store.paths.logs / "project_draft.json"
    assert marker.is_file()

    from PySide6 import QtWidgets
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(
        QtWidgets.QMessageBox,
        "question",
        lambda *_args, **_kwargs: QtWidgets.QMessageBox.StandardButton.RestoreDefaults,
    )
    from lfp_analysis.project_gui import ProjectWorkspace

    window = ProjectWorkspace(reopened_store, PROJECT_ROOT / "configs" / "luna.yaml", PROJECT_ROOT / "metadata")
    app.processEvents()
    assert window._project_draft_dirty
    assert {row["subject_code"] for row in reopened_store.subjects()} == {
        "Baseline", "DraftSubject", "EmptyDraftSubject",
    }

    # A file created after the crash is not part of the recorded draft files;
    # Discard must preserve it and therefore retain its now non-empty folder.
    untracked_file = reopened_store.paths.subjects / "DraftSubject" / "keep.txt"
    untracked_file.write_text("preserve non-empty directory", encoding="utf-8")
    assert window.discard_project_changes()

    assert [row["subject_code"] for row in reopened_store.subjects()] == ["Baseline"]
    assert protected_file.read_text(encoding="utf-8") == "pre-existing project content"
    assert untracked_file.read_text(encoding="utf-8") == "preserve non-empty directory"
    assert (reopened_store.paths.subjects / "DraftSubject").is_dir()
    assert not (reopened_store.paths.subjects / "EmptyDraftSubject").exists()
    assert not marker.exists()
    assert not list((reopened_store.paths.logs / "backups").glob("project-draft-*.sqlite3"))

    window.close()
    app.processEvents()


def test_crashed_draft_can_be_recovered_saved_and_reopened(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    store = ProjectStore.create(tmp_path / "project", "Crash then save")
    original_subject = store.add_subject("Mouse01", "GroupA")
    child = _crash_after_edit(
        store.paths.root,
        "subject_id = store.subjects()[0]['subject_id']\n"
        "store.update_subject(subject_id, subject_code='Mouse01', group_label='RecoveredDraft')",
    )
    assert child.returncode == 73, child.stderr

    reopened_store = ProjectStore(store.paths.root)
    marker = reopened_store.paths.logs / "project_draft.json"
    assert reopened_store.subjects()[0]["group_label"] == "RecoveredDraft"
    from PySide6 import QtWidgets
    from PySide6.QtWidgets import QApplication

    monkeypatch.setattr(
        QtWidgets.QMessageBox,
        "question",
        lambda *_args, **_kwargs: QtWidgets.QMessageBox.StandardButton.RestoreDefaults,
    )
    app = QApplication.instance() or QApplication([])
    from lfp_analysis.project_gui import ProjectWorkspace

    window = ProjectWorkspace(reopened_store, PROJECT_ROOT / "configs" / "luna.yaml", PROJECT_ROOT / "metadata")
    app.processEvents()
    assert window._project_draft_dirty
    assert reopened_store.subjects()[0]["subject_id"] == original_subject
    assert window.save_project()
    assert not marker.exists()
    assert not list((reopened_store.paths.logs / "backups").glob("project-draft-*.sqlite3"))
    assert ProjectStore(store.paths.root).subjects()[0]["group_label"] == "RecoveredDraft"

    window.close()
    app.processEvents()


def test_schema_five_migration_adds_order_without_losing_project_rows(tmp_path: Path):
    source = tmp_path / "record.fif"
    source.write_bytes(b"synthetic project source")
    store = ProjectStore.create(tmp_path / "project", "Schema five")
    subject_id = store.add_subject("Mouse01", "LID")
    day3_id = store.add_session(subject_id, "Day3", session_date="2026-09-03")
    day10_id = store.add_session(subject_id, "Day10", session_date="2026-09-10")
    day3_state = store.add_state_record(day3_id, "T80", condition_label="L-DOPA", timepoint_value=80.0)
    data_unit_id = store.add_data_unit(day3_state, source)
    with store.transaction() as connection:
        connection.execute("DROP INDEX idx_sessions_subject_order")
        connection.execute("ALTER TABLE sessions DROP COLUMN sort_order")
        connection.execute("UPDATE projects SET schema_version=5")
        connection.execute("UPDATE schema_info SET version=5")
        connection.execute("UPDATE sessions SET created_at_utc='2026-09-01T00:00:00+00:00' WHERE session_id=?", (day3_id,))
        connection.execute("UPDATE sessions SET created_at_utc='2026-09-02T00:00:00+00:00' WHERE session_id=?", (day10_id,))

    migrated = ProjectStore(store.paths.root)
    sessions = migrated.sessions(subject_id)
    assert migrated.project["schema_version"] == 6
    assert [row["session_id"] for row in sessions] == [day3_id, day10_id]
    assert [row["sort_order"] for row in sessions] == [0, 1]
    assert migrated.state_records()[0]["state_record_id"] == day3_state
    assert migrated.data_units(data_unit_ids=[data_unit_id])[0]["source_sha256"]
    indexes = migrated.query("SELECT name FROM sqlite_master WHERE type='index'")
    assert "idx_sessions_subject_order" in {row["name"] for row in indexes}
