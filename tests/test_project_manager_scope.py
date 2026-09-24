from __future__ import annotations

from pathlib import Path

import pytest

from lfp_analysis.project_store import ProjectStore


def _scope_project(tmp_path: Path):
    store = ProjectStore.create(tmp_path / "scope project", "Scope project")
    nodes: dict[str, object] = {"subjects": {}, "sessions": {}, "states": {}, "data": {}}
    counter = 0
    for subject_code, group in (("Mouse01", "LID"), ("Mouse02", "Control")):
        subject_id = store.add_subject(subject_code, group)
        nodes["subjects"][subject_code] = subject_id
        for session_key in ("Day3", "Day7"):
            session_id = store.add_session(subject_id, session_key)
            nodes["sessions"][(subject_code, session_key)] = session_id
            for state_name in (("T80", "T100") if session_key == "Day3" else ("T80", "Empty" if subject_code == "Mouse02" else "T40")):
                state_id = store.add_state_record(session_id, state_name)
                nodes["states"][(subject_code, session_key, state_name)] = state_id
                count = 2 if (subject_code, session_key, state_name) == ("Mouse01", "Day3", "T80") else 0 if state_name == "Empty" else 1
                for _ in range(count):
                    counter += 1
                    source = tmp_path / f"source {counter}.fif"
                    source.write_bytes(f"synthetic-source-{counter}".encode())
                    data_id = store.add_data_unit(state_id, source)
                    nodes["data"].setdefault((subject_code, session_key, state_name), []).append(data_id)
    nodes["subjects"]["MouseEmpty"] = store.add_subject("MouseEmpty")
    nodes["sessions"][("Mouse02", "Day14")] = store.add_session(nodes["subjects"]["Mouse02"], "Day14")
    return store, nodes


def _find_tree_item(tree, identity: tuple[str, str]):
    from PySide6.QtWidgets import QTreeWidgetItemIterator

    iterator = QTreeWidgetItemIterator(tree)
    while iterator.value() is not None:
        item = iterator.value()
        value = item.data(0, 256)
        if isinstance(value, (tuple, list)) and tuple(map(str, value)) == identity:
            return item
        iterator += 1
    raise AssertionError(f"Tree identity not found: {identity}")


def _visible_ids(window) -> set[str]:
    return {
        window.data_table.item(row, 10).text()
        for row in range(window.data_table.rowCount())
    }


def test_data_units_accept_exact_scope_ids_and_empty_explicit_ids(tmp_path: Path):
    store, nodes = _scope_project(tmp_path)
    project_id = store.project["project_id"]
    assert len(store.data_units(project_id=project_id)) == 8
    assert len(store.data_units(subject_id=nodes["subjects"]["Mouse01"])) == 5
    assert len(store.data_units(session_id=nodes["sessions"][("Mouse01", "Day3")])) == 3
    assert len(store.data_units(state_record_id=nodes["states"][("Mouse01", "Day3", "T80")])) == 2
    assert len(store.data_units(data_unit_id=nodes["data"][("Mouse01", "Day3", "T80")][0])) == 1
    assert store.data_units(state_record_id=nodes["states"][("Mouse02", "Day7", "Empty")]) == []
    assert store.data_units(data_unit_ids=[]) == []
    assert store.data_units(project_id=project_id, subject_id=nodes["subjects"]["Mouse02"])
    assert not store.data_units(subject_id=nodes["subjects"]["Mouse01"], session_id=nodes["sessions"][("Mouse02", "Day3")])


def test_project_manager_tree_selection_filters_records_and_keeps_empty_scope(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    from lfp_analysis.project_gui import ProjectWorkspace

    store, nodes = _scope_project(tmp_path)
    app = QApplication.instance() or QApplication([])
    window = ProjectWorkspace(store, Path("configs/luna.yaml"), Path("metadata"), mode="manage")
    try:
        app.processEvents()
        root = _find_tree_item(window.hierarchy, ("project", store.project["project_id"]))
        assert window.hierarchy.currentItem() is root
        assert len(_visible_ids(window)) == 8
        assert window.data_table.horizontalHeaderItem(0).text() == "Batch"
        assert all(window.data_table.item(row, 0).checkState().value == 0 for row in range(window.data_table.rowCount()))
        assert not window.data_table.item(0, 0).flags() & Qt.ItemFlag.ItemIsSelectable

        subject_id = nodes["subjects"]["Mouse01"]
        window.hierarchy.setCurrentItem(_find_tree_item(window.hierarchy, ("subject", subject_id)))
        app.processEvents()
        assert _visible_ids(window) == {value for key, values in nodes["data"].items() if key[0] == "Mouse01" for value in values}
        assert "Mouse01" in window.current_range_summary.text()

        session_id = nodes["sessions"][("Mouse01", "Day3")]
        window.hierarchy.setCurrentItem(_find_tree_item(window.hierarchy, ("session", session_id)))
        app.processEvents()
        assert _visible_ids(window) == set(nodes["data"][("Mouse01", "Day3", "T80")] + nodes["data"][("Mouse01", "Day3", "T100")])

        state_id = nodes["states"][("Mouse02", "Day7", "T80")]
        window.hierarchy.setCurrentItem(_find_tree_item(window.hierarchy, ("state", state_id)))
        app.processEvents()
        assert _visible_ids(window) == set(nodes["data"][("Mouse02", "Day7", "T80")])
        assert "Mouse02" in window.current_range_summary.text()

        data_id = nodes["data"][("Mouse02", "Day7", "T80")][0]
        window.hierarchy.setCurrentItem(_find_tree_item(window.hierarchy, ("data", data_id)))
        app.processEvents()
        assert _visible_ids(window) == {data_id}
        assert window._current_data_scope()["query"] == {"data_unit_id": data_id}

        empty_state_id = nodes["states"][("Mouse02", "Day7", "Empty")]
        empty_item = _find_tree_item(window.hierarchy, ("state", empty_state_id))
        window.hierarchy.setCurrentItem(empty_item)
        app.processEvents()
        assert window.data_table.rowCount() == 0
        assert "当前节点暂无数据" in window.empty_data_message.text()
        assert window._current_data_scope()["query"] == {"state_record_id": empty_state_id}

        empty_session_id = nodes["sessions"][("Mouse02", "Day14")]
        window.hierarchy.setCurrentItem(_find_tree_item(window.hierarchy, ("session", empty_session_id)))
        app.processEvents()
        assert window.data_table.rowCount() == 0
        assert "当前节点暂无数据" in window.empty_data_message.text()
        assert window._current_data_scope()["query"] == {"session_id": empty_session_id}

        empty_subject_id = nodes["subjects"]["MouseEmpty"]
        window.hierarchy.setCurrentItem(_find_tree_item(window.hierarchy, ("subject", empty_subject_id)))
        app.processEvents()
        assert window.data_table.rowCount() == 0
        assert "当前节点暂无数据" in window.empty_data_message.text()
        assert window._current_data_scope()["query"] == {"subject_id": empty_subject_id}

        window.hierarchy.setCurrentItem(root)
        window.manage_search.setText("no such file")
        app.processEvents()
        assert window.data_table.rowCount() == 0
        assert "没有符合条件" in window.empty_data_message.text()
        assert window._current_data_scope()["query"] == {"project_id": store.project["project_id"]}
        window.clear_data_filters_button.click()
        app.processEvents()
        assert window.data_table.rowCount() == 8
        assert window.hierarchy.currentItem() is root
        window.manage_group_filter.setCurrentText("Control")
        app.processEvents()
        assert _visible_ids(window) == {value for key, values in nodes["data"].items() if key[0] == "Mouse02" for value in values}
        assert "3 条 / 范围内 8 条" in window.visible_data_summary.text()
        window.clear_data_filters_button.click()
        app.processEvents()
        assert window.data_table.rowCount() == 8

        window.data_table.item(0, 0).setCheckState(Qt.CheckState.Checked)
        assert not window.data_table.selectionModel().selectedRows()
        assert window._selected_data_unit_ids() == [window.data_table.item(0, 10).text()]
        window.hierarchy.setCurrentItem(_find_tree_item(window.hierarchy, ("subject", nodes["subjects"]["Mouse02"])))
        app.processEvents()
        assert window._selected_data_unit_ids() == []

        opened: list[tuple[str, object]] = []
        window.open_data_unit.connect(lambda path, row: opened.append((path, row)))
        mouse2_session = _find_tree_item(window.hierarchy, ("session", nodes["sessions"][("Mouse02", "Day3")]))
        window._open_tree_item(mouse2_session)
        assert opened == []
        data_id = nodes["data"][("Mouse02", "Day3", "T80")][0]
        window._open_tree_item(_find_tree_item(window.hierarchy, ("data", data_id)))
        assert len(opened) == 1
        assert opened[0][1]["data_unit_id"] == data_id

        state_parent_session = nodes["sessions"][("Mouse02", "Day7")]
        window.hierarchy.setCurrentItem(empty_item)
        app.processEvents()
        before_expand = _visible_ids(window)
        parent_item = _find_tree_item(window.hierarchy, ("session", state_parent_session))
        parent_item.setExpanded(not parent_item.isExpanded())
        app.processEvents()
        assert window.hierarchy.currentItem() is empty_item
        assert _visible_ids(window) == before_expand
        with store.transaction() as connection:
            connection.execute("DELETE FROM state_records WHERE state_record_id=?", (empty_state_id,))
        window.refresh_all()
        app.processEvents()
        current = window.hierarchy.currentItem().data(0, 256)
        assert tuple(map(str, current)) == ("session", state_parent_session)
        assert _visible_ids(window) == set(nodes["data"][("Mouse02", "Day7", "T80")])
    finally:
        window.close()


def test_refresh_keeps_selected_state_identity_after_rename(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    from lfp_analysis.project_gui import ProjectWorkspace

    store, nodes = _scope_project(tmp_path)
    app = QApplication.instance() or QApplication([])
    window = ProjectWorkspace(store, Path("configs/luna.yaml"), Path("metadata"), mode="manage")
    try:
        session_id = nodes["sessions"][("Mouse01", "Day3")]
        state_id = nodes["states"][("Mouse01", "Day3", "T80")]
        window.hierarchy.setCurrentItem(_find_tree_item(window.hierarchy, ("state", state_id)))
        app.processEvents()
        expected_data_ids = set(nodes["data"][("Mouse01", "Day3", "T80")])
        state = next(row for row in store.state_records(session_id) if row["state_record_id"] == state_id)
        store.update_state_record(
            state_id,
            display_name="T80 renamed",
            condition_label=str(state.get("condition_label") or ""),
            timepoint_value=state.get("timepoint_value"),
            timepoint_unit=str(state.get("timepoint_unit") or "min"),
            reference_event=str(state.get("reference_event") or ""),
            actual_start=str(state.get("actual_start") or ""),
            actual_end=str(state.get("actual_end") or ""),
        )
        window.refresh_all()
        app.processEvents()
        assert tuple(map(str, window.hierarchy.currentItem().data(0, 256))) == ("state", state_id)
        assert _visible_ids(window) == expected_data_ids
        assert window.current_range_summary.text().endswith("/ T80 renamed")
    finally:
        window.close()


def test_scoped_filter_dialog_and_reopened_project_keep_scope_association(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    from lfp_analysis.project_gui import ProjectFilterExportDialog

    store, nodes = _scope_project(tmp_path)
    app = QApplication.instance() or QApplication([])
    state_id = nodes["states"][("Mouse01", "Day3", "T80")]
    dialog = ProjectFilterExportDialog(store, scope_query={"state_record_id": state_id}, scope_label="Scope project / Mouse01 / Day3 / T80")
    try:
        app.processEvents()
        expected = set(nodes["data"][("Mouse01", "Day3", "T80")])
        assert {row["data_unit_id"] for row in dialog._rows} == expected
        assert f"{len(expected)} after filters" in dialog.scope_summary.text()
        dialog.clear_filters()
        assert {row["data_unit_id"] for row in dialog._rows} == expected
        reopened = ProjectStore(store.paths.root)
        reopened_rows = reopened.data_units(state_record_id=state_id)
        assert {row["data_unit_id"] for row in reopened_rows} == expected
        assert all(row["state_record_id"] == state_id for row in reopened_rows)
    finally:
        dialog.close()


def test_import_into_selected_empty_state_refreshes_and_persists_in_that_scope(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    from lfp_analysis.project_gui import ProjectWorkspace

    store, nodes = _scope_project(tmp_path)
    app = QApplication.instance() or QApplication([])
    window = ProjectWorkspace(store, Path("configs/luna.yaml"), Path("metadata"), mode="manage")
    try:
        empty_state_id = nodes["states"][("Mouse02", "Day7", "Empty")]
        window.hierarchy.setCurrentItem(_find_tree_item(window.hierarchy, ("state", empty_state_id)))
        source = tmp_path / "imported copy.fif"
        source.write_bytes(b"read-only synthetic import bytes")
        original = source.read_bytes()
        window._begin_project_edit()
        data_id, copied = store.import_data_unit(empty_state_id, source)
        assert copied
        window._record_project_content_changes()
        window.refresh_all()
        app.processEvents()
        assert tuple(map(str, window.hierarchy.currentItem().data(0, 256))) == ("state", empty_state_id)
        assert _visible_ids(window) == {data_id}
        assert window._project_draft_dirty
        assert source.read_bytes() == original
        imported = store.data_units(data_unit_id=data_id)[0]
        assert imported["source_path_kind"] == "project_relative"
        assert store.resolve_source_path(imported).is_file()
        assert window.save_project()
        reopened = ProjectStore(store.paths.root)
        assert {row["data_unit_id"] for row in reopened.data_units(state_record_id=empty_state_id)} == {data_id}
    finally:
        window.close()


def test_switching_project_workspace_does_not_retain_previous_project_rows(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    from lfp_analysis.project_gui import ProjectWorkspace

    store, _nodes = _scope_project(tmp_path)
    other = ProjectStore.create(tmp_path / "second", "Second project")
    app = QApplication.instance() or QApplication([])
    first_window = ProjectWorkspace(store, Path("configs/luna.yaml"), Path("metadata"), mode="manage")
    second_window = ProjectWorkspace(other, Path("configs/luna.yaml"), Path("metadata"), mode="manage")
    try:
        app.processEvents()
        assert first_window.data_table.rowCount() == 8
        assert second_window.data_table.rowCount() == 0
        assert "Second project" in second_window.current_range_summary.text()
        assert "Scope project" not in second_window.current_range_summary.text()
    finally:
        first_window.close()
        second_window.close()


def test_closing_manager_hides_all_scoped_filter_windows(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    import shiboken6
    from PySide6 import QtCore
    from PySide6.QtWidgets import QApplication

    from lfp_analysis.project_gui import ProjectWorkspace

    store, _nodes = _scope_project(tmp_path)
    app = QApplication.instance() or QApplication([])
    window = ProjectWorkspace(store, Path("configs/luna.yaml"), Path("metadata"), mode="manage")
    window.show()
    try:
        window.open_filter_export()
        first_dialog = window.filter_export_dialog
        window.open_filter_export()
        second_dialog = window.filter_export_dialog
        app.processEvents()
        assert first_dialog.isVisible() and second_dialog.isVisible()
        window.close()
        app.processEvents()
        app.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
        app.processEvents()
        assert not window.isVisible()
        assert window.filter_export_dialog is None
        assert not shiboken6.isValid(first_dialog)
        assert not shiboken6.isValid(second_dialog)
    finally:
        window.close()


def test_cancelled_manager_close_keeps_filter_window_alive(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6 import QtCore, QtWidgets
    from PySide6.QtWidgets import QApplication

    from lfp_analysis.project_gui import ProjectWorkspace

    store, _nodes = _scope_project(tmp_path)
    app = QApplication.instance() or QApplication([])
    window = ProjectWorkspace(store, Path("configs/luna.yaml"), Path("metadata"), mode="manage")
    window.show()
    window._begin_project_edit()
    window.open_filter_export()
    dialog = window.filter_export_dialog
    app.processEvents()
    monkeypatch.setattr(
        QtWidgets.QMessageBox,
        "question",
        lambda *args, **kwargs: QtWidgets.QMessageBox.StandardButton.Cancel,
    )
    try:
        assert window.close() is False
        app.processEvents()
        assert window.isVisible()
        assert dialog.isVisible()
        assert window.filter_export_dialog is dialog
        assert dialog.store.project["project_id"] == store.project["project_id"]
    finally:
        window._project_draft_dirty = False
        window.close()
        app.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)


def test_individually_closed_filter_window_clears_owner_reference(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    import shiboken6
    from PySide6 import QtCore
    from PySide6.QtWidgets import QApplication

    from lfp_analysis.project_gui import ProjectWorkspace

    store, _nodes = _scope_project(tmp_path)
    app = QApplication.instance() or QApplication([])
    window = ProjectWorkspace(store, Path("configs/luna.yaml"), Path("metadata"), mode="manage")
    try:
        window.open_filter_export()
        old_dialog = window.filter_export_dialog
        old_dialog.close()
        app.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
        app.processEvents()
        assert window.filter_export_dialog is None
        assert not shiboken6.isValid(old_dialog)
        window.open_filter_export()
        assert window.filter_export_dialog is not None
        assert window.filter_export_dialog.store is store
    finally:
        window.close()
        app.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)


def test_import_preview_target_is_frozen_by_state_id(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    from lfp_analysis.project_gui import ImportPreviewDialog, ProjectWorkspace

    store, nodes = _scope_project(tmp_path)
    app = QApplication.instance() or QApplication([])
    window = ProjectWorkspace(store, Path("configs/luna.yaml"), Path("metadata"), mode="manage")
    source = tmp_path / "incoming.fif"
    source.write_bytes(b"synthetic preview source")
    original_state_id = nodes["states"][("Mouse01", "Day3", "T80")]
    later_state_id = nodes["states"][("Mouse02", "Day3", "T80")]
    dialog = ImportPreviewDialog(
        store,
        [str(source)],
        Path("configs/luna.yaml"),
        Path("metadata"),
        window,
        inherited={"state_record_id": original_state_id},
    )
    try:
        assert dialog.rows()[0]["state_record_id"] == original_state_id
        window.hierarchy.setCurrentItem(_find_tree_item(window.hierarchy, ("state", later_state_id)))
        app.processEvents()
        assert dialog.rows()[0]["state_record_id"] == original_state_id
    finally:
        dialog.close()
        window.close()


def test_attaching_project_destroys_previous_workspaces_and_uses_new_store(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from types import SimpleNamespace

    import shiboken6
    from PySide6 import QtCore
    from PySide6.QtWidgets import QApplication

    import lfp_analysis.gui as gui_module
    from lfp_analysis.gui import MainWindow

    class NoopSettings:
        def setValue(self, *_args):
            return None

    monkeypatch.setattr(gui_module.QtCore, "QSettings", lambda *_args: NoopSettings())
    app = QApplication.instance() or QApplication([])
    store_a = ProjectStore.create(tmp_path / "Project A", "Project A")
    store_b = ProjectStore.create(tmp_path / "Project B", "Project B")
    main = MainWindow()
    try:
        assert main._attach_project(store_a)
        old_workspace = main.project_workspace
        old_workspace.open_filter_export()
        old_dialog = old_workspace.filter_export_dialog
        old_workspace._begin_project_edit()
        monkeypatch.setattr(
            gui_module.QtWidgets.QMessageBox,
            "question",
            lambda *_args, **_kwargs: gui_module.QtWidgets.QMessageBox.StandardButton.Cancel,
        )
        assert not main._attach_project(store_b)
        assert main.project_store is store_a
        assert old_workspace.isVisible() and old_dialog.isVisible()
        old_workspace._project_draft_dirty = False
        monkeypatch.setattr(gui_module.QtWidgets.QMessageBox, "information", lambda *_args, **_kwargs: None)

        class RunningThread:
            @staticmethod
            def isRunning():
                return True

        main.project_batch_workspace = SimpleNamespace(batch_thread=RunningThread())
        assert not main._attach_project(store_b)
        assert main.project_store is store_a
        assert main.project_workspace is old_workspace and old_workspace.isVisible()
        assert old_dialog.isVisible()
        main.project_batch_workspace = None

        assert main._attach_project(store_b)
        new_workspace = main.project_workspace
        app.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
        app.processEvents()
        assert main.project_store is store_b
        assert new_workspace.store.project["project_id"] == store_b.project["project_id"]
        assert not shiboken6.isValid(old_workspace)
        assert not shiboken6.isValid(old_dialog)
        new_workspace.open_filter_export()
        assert new_workspace.filter_export_dialog.store is store_b
        assert new_workspace.filter_export_dialog is not old_dialog
    finally:
        main.close()
        app.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
