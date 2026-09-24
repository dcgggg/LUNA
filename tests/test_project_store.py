from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from lfp_analysis.comparison import paired_subject_summary, select_results
from lfp_analysis.project_store import ProjectStore, normalize_project_folder_name
from lfp_analysis.result_contract import (
    load_array,
    load_result_manifest,
    load_table,
    write_result_manifest,
)
from lfp_analysis.results_api import ProjectResults


def _hierarchy(store: ProjectStore, source: Path, subject_code: str = "M01", session_key: str = "Day7", timepoint: float = 100.0) -> str:
    subject_id = store.add_subject(subject_code, "LID")
    session_id = store.add_session(subject_id, session_key, "L-DOPA response")
    state_id = store.add_state_record(
        session_id,
        f"T{int(timepoint)}",
        condition_label="L-DOPA",
        timepoint_value=timepoint,
        timepoint_unit="min",
        reference_event="L-DOPA administration",
    )
    return store.add_data_unit(state_id, source)


def test_project_hierarchy_uses_stable_ids_and_content_duplicate_detection(tmp_path: Path):
    source = tmp_path / "record.fif"
    source.write_bytes(b"same-content")
    store = ProjectStore.create(tmp_path / "project", "Study")
    data_unit_id = _hierarchy(store, source)

    assert store.duplicate_candidates(source)[0]["data_unit_id"] == data_unit_id
    assert store.duplicate_selection_candidates(source)[0]["data_unit_id"] == data_unit_id
    assert store.duplicate_selection_candidates(source, epoch_selection={"indices": [0, 1]}) == []
    session_id = store.sessions(store.subjects()[0]["subject_id"])[0]["session_id"]
    split_state = store.add_state_record(session_id, "explicit subset")
    split_id = store.add_data_unit(split_state, source, epoch_selection={"indices": [0, 1]})
    assert store.duplicate_selection_candidates(source, epoch_selection={"indices": [0, 1]})[0]["data_unit_id"] == split_id
    subject = store.subjects()[0]
    store.update_subject(subject["subject_id"], subject_code="renamed", group_label="LID")
    unit = store.data_units(data_unit_ids=[data_unit_id])[0]
    assert unit["data_unit_id"] == data_unit_id
    assert unit["subject_code"] == "renamed"

    relocated = tmp_path / "moved.fif"
    relocated.write_bytes(source.read_bytes())
    store.relocate_source(data_unit_id, relocated)
    assert store.source_status(data_unit_id)["status"] == "ok"
    relocated.write_bytes(b"changed")
    assert store.source_status(data_unit_id)["status"] == "changed"

    comparison_id = store.create_comparison_snapshot("empty", {"session_key": "Day7"}, [], [], {"band": "delta"})
    assert store.load_comparison_snapshot(comparison_id)["comparison_id"] == comparison_id
    assert store.comparison_snapshots()[0]["comparison_id"] == comparison_id

    session = store.sessions(subject["subject_id"])[0]
    store.update_session(session["session_id"], session_key="Day7-renamed", experiment_name="updated")
    state = next(record for record in store.state_records(session["session_id"]) if record["state_record_id"] == unit["state_record_id"])
    store.update_state_record(state["state_record_id"], display_name="post-dose", timepoint_value=100.0)
    renamed_unit = store.data_units(data_unit_ids=[data_unit_id])[0]
    assert renamed_unit["session_key"] == "Day7-renamed"
    assert renamed_unit["state_display_name"] == "post-dose"


def test_behavior_metadata_distinguishes_missing_and_zero_and_keeps_state_links(tmp_path: Path):
    store = ProjectStore.create(tmp_path / "project", "Behavior metadata")
    subject = store.add_subject("Mouse01")
    session = store.add_session(subject, "Day1")
    state = store.add_state_record(session, "T80", timepoint_value=80.0)
    attachment = store.add_behavior_attachment(state, tmp_path / "video.mp4", resource_type="video", file_format="mp4")
    missing_score = store.add_behavior_score(state, "AIMs", None, unit_or_scale="score")
    zero_score = store.add_behavior_score(state, "AIMs", 0.0, unit_or_scale="score")
    sync_id = store.add_synchronization_record(state, attachment_id=attachment, method="manual", confirmed=False)

    scores = store.behavior_scores(state)
    assert [row["score_id"] for row in scores] == [missing_score, zero_score]
    assert scores[0]["value"] is None
    assert scores[1]["value"] == 0.0
    assert store.behavior_attachments(state)[0]["attachment_id"] == attachment
    assert store.synchronization_records(state)[0]["sync_id"] == sync_id
    assert store.project["schema_version"] == 6


def test_project_database_backup_restores_metadata_without_touching_result_files(tmp_path: Path):
    store = ProjectStore.create(tmp_path / "project", "Draft save")
    store.add_subject("Mouse01")
    result_file = store.paths.results / "keep.txt"
    result_file.write_text("saved result", encoding="utf-8")
    backup = store.paths.logs / "draft.sqlite3"
    store.backup_database(backup)
    store.add_subject("Mouse02")
    store.restore_database_backup(backup)
    assert [row["subject_code"] for row in store.subjects()] == ["Mouse01"]
    assert result_file.read_text(encoding="utf-8") == "saved result"


def test_result_contract_is_named_versioned_and_readable_without_source(tmp_path: Path):
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    pd.DataFrame({"channel_name": ["A"], "value": [1.5]}).to_csv(bundle / "values.csv", index=False)
    np.savez_compressed(bundle / "arrays.npz", spectrum=np.asarray([[1.0, 2.0]]), frequency=np.asarray([10.0, 20.0]))
    manifest = write_result_manifest(
        bundle,
        identities={"project_id": "p", "subject_id": "s", "session_id": "se", "state_record_id": "st", "data_unit_id": "d"},
        module_name="PSD",
        method_name="welch",
        parameters={"nperseg": 1000},
        data_fingerprint="abc",
        source={"path": "missing.fif", "sha256": "abc"},
        selections={"epochs": [0]},
        channel_mapping=[{"channel_name": "A", "region": "R"}],
        sampling_rate_hz=1000.0,
        signal_unit="V",
        tables={"values": "values.csv"},
        arrays={"primary": "arrays.npz"},
        axes={"spectrum": ["channel", "frequency"], "frequency": ["frequency"]},
    )
    loaded = load_result_manifest(bundle)
    assert loaded["analysis_id"] == manifest["analysis_id"]
    assert loaded["analysis_run_id"] == loaded["analysis_id"]
    assert loaded["dataset_id"] == loaded["data_unit_id"] == "d"
    assert loaded["state_id"] == loaded["state_record_id"] == "st"
    assert load_table(loaded, "values").loc[0, "value"] == 1.5
    np.testing.assert_array_equal(load_array(loaded, "spectrum"), [[1.0, 2.0]])
    (bundle / "values.csv").unlink()
    with pytest.raises(ValueError, match="missing_file"):
        load_result_manifest(bundle)


def test_result_manifest_write_failure_does_not_create_completion_marker(tmp_path: Path):
    bundle = tmp_path / "incomplete_bundle"
    with pytest.raises(ValueError, match="missing_file"):
        write_result_manifest(
            bundle,
            identities={"project_id": "p", "subject_id": "s", "session_id": "se", "state_record_id": "st", "data_unit_id": "d"},
            module_name="PSD", method_name="welch", parameters={}, data_fingerprint="data",
            source={"path": "missing.fif"}, selections={}, channel_mapping=[], sampling_rate_hz=1000.0,
            signal_unit="V", tables={"values": "not-written.csv"},
        )
    assert not (bundle / "manifest.json").exists()


def test_five_subject_t100_selection_reports_missing_and_duplicates(tmp_path: Path):
    project = tmp_path / "project"
    store = ProjectStore.create(project, "Synthetic five-subject project")
    included_ids: list[str] = []
    for index in range(5):
        source = tmp_path / f"subject_{index}.fif"
        source.write_bytes(f"synthetic-{index}".encode())
        data_id = _hierarchy(store, source, subject_code=f"M{index + 1:02d}", timepoint=80.0 if index == 4 else 100.0)
        if index == 3:
            # A second T100 data unit is intentionally ambiguous.
            second_source = tmp_path / "subject_3_repeat.fif"
            second_source.write_bytes(b"repeat")
            session_id = store.sessions(store.subjects()[index]["subject_id"])[0]["session_id"]
            state_id = store.add_state_record(session_id, "T100 repeat", condition_label="L-DOPA", timepoint_value=100.0)
            second_id = store.add_data_unit(state_id, second_source)
        else:
            second_id = None
        for current_data_id in [data_id, second_id]:
            if current_data_id is None:
                continue
            aid = f"analysis_{current_data_id}"
            bundle = project / "results" / current_data_id / "psd"
            bundle.mkdir(parents=True)
            pd.DataFrame({"channel_name": ["A"], "psd_value": [float(index)]}).to_csv(bundle / "psd_channel_summary.csv", index=False)
            result = write_result_manifest(
                bundle,
                identities={"project_id": store.project["project_id"], "subject_id": store.data_units(data_unit_ids=[current_data_id])[0]["subject_id"], "session_id": store.data_units(data_unit_ids=[current_data_id])[0]["session_id"], "state_record_id": store.data_units(data_unit_ids=[current_data_id])[0]["state_record_id"], "data_unit_id": current_data_id},
                module_name="PSD", method_name="welch", parameters={"same": True}, data_fingerprint=current_data_id,
                source={"path": "synthetic"}, selections={}, channel_mapping=[], sampling_rate_hz=1000.0, signal_unit="V",
                tables={"psd_channel_summary": "psd_channel_summary.csv"}, analysis_identifier=aid,
            )
            store.register_analysis({
                "analysis_id": aid, "data_unit_id": current_data_id, "module_name": "PSD", "method_name": "welch",
                "result_path": str(bundle.relative_to(project)), "schema_version": result["schema_version"],
                "parameter_fingerprint": result["parameter_fingerprint"], "data_fingerprint": result["data_fingerprint"],
                "parameters_json": "{\"same\": true}", "calculation_status": "completed", "save_status": "saved",
                "review_status": "approved", "review_notes": None, "created_at_utc": result["created_at_utc"],
                "completed_at_utc": result["created_at_utc"], "active": 1, "warnings_json": "[]", "error_message": None,
            })
            included_ids.append(aid)

    selection = select_results(store, {"session_key": "Day7", "condition_label": "L-DOPA", "timepoint_value": 100.0, "module_name": "PSD"})
    assert set(selection.included["subject_code"]) == {"M01", "M02", "M03"}
    assert set(selection.excluded["subject_code"]) == {"M04"}
    assert "M05" not in set(pd.concat([selection.included, selection.excluded])["subject_code"])
    chosen_duplicate = selection.excluded.iloc[0]["analysis_id"]
    explicit = select_results(
        store,
        {"session_key": "Day7", "condition_label": "L-DOPA", "timepoint_value": 100.0, "module_name": "PSD"},
        selected_analysis_ids=[chosen_duplicate],
    )
    assert explicit.included["analysis_id"].tolist() == [chosen_duplicate]
    ranged = store.analysis_results({"session_key": "Day7", "timepoint_min": 99.0, "timepoint_max": 101.0, "module_name": "PSD"})
    assert all(float(row["timepoint_value"]) == 100.0 for row in ranged)


def test_project_workspace_constructs_with_project_rows_offscreen(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication, QTableWidgetItem

    from lfp_analysis.project_gui import (
        ClipboardTableWidget,
        ImportPreviewDialog,
        ProjectWorkspace,
    )

    source = tmp_path / "synthetic.fif"
    source.write_bytes(b"synthetic")
    store = ProjectStore.create(tmp_path / "project", "GUI project")
    _hierarchy(store, source)
    app = QApplication.instance() or QApplication([])
    window = ProjectWorkspace(store, Path("configs/luna.yaml"), Path("metadata"))
    window.show()
    app.processEvents()
    assert window.data_table.rowCount() == 1
    assert window.tabs.count() == 1
    assert window.hierarchy.columnCount() == 1
    state_item = window.hierarchy.topLevelItem(0).child(0).child(0).child(0)
    assert state_item.childCount() == 1
    assert state_item.child(0).data(0, 256)[0] == "data"
    assert window.data_table.isColumnHidden(10)
    assert window.acceptDrops()
    assert ProjectWorkspace._expand_import_paths([str(tmp_path)]) == [str(source.resolve())]
    assert ImportPreviewDialog._parse_epoch_indices("0, 2, 4-6") == [0, 2, 4, 5, 6]
    unit = store.data_units()[0]
    preview = ImportPreviewDialog(
        store,
        [str(source)],
        Path("configs/luna.yaml"),
        Path("metadata"),
        inherited={"state_record_id": unit["state_record_id"]},
    )
    assert preview.rows()[0]["state_record_id"] == unit["state_record_id"]
    preview.close()
    paste_table = ClipboardTableWidget(2, 2)
    for row in range(2):
        for column in range(2):
            paste_table.setItem(row, column, QTableWidgetItem())
    paste_table.paste_text("M01\tDay1\nM02\tDay7", 0, 0)
    assert [[paste_table.item(row, column).text() for column in range(2)] for row in range(2)] == [["M01", "Day1"], ["M02", "Day7"]]
    window.close()


def test_named_project_portable_import_template_and_inspection(tmp_path: Path):
    parent = tmp_path / "projects"
    source = tmp_path / "record.fif"
    source.write_bytes(b"portable-source")
    store = ProjectStore.create_named(parent, "LID:LDN")
    assert store.paths.root.name == normalize_project_folder_name("LID:LDN")
    assert store.paths.raw_data.is_dir()

    template = {
        "subjects": [{"subject_code": "M01"}, {"subject_code": "M02"}],
        "sessions": [{"session_key": "Day1"}, {"session_key": "Day7"}],
        "states": [
            {"display_name": "Baseline", "condition_label": "", "timepoint_value": None, "timepoint_unit": "min"},
            {"display_name": "T20", "condition_label": "L-DOPA", "timepoint_value": 20.0, "timepoint_unit": "min"},
        ],
    }
    store.save_structure_template("LID schedule", template)
    first = store.apply_structure_template(template)
    second = store.apply_structure_template(template)
    assert first["subjects_created"] == 2
    assert first["sessions_created"] == 4
    assert first["states_created"] == 8
    assert second["subjects_created"] == second["sessions_created"] == second["states_created"] == 0

    session = store.sessions(store.subjects()[0]["subject_id"])[0]
    state = store.state_records(session["session_id"])[0]
    data_id, copied = store.import_data_unit(state["state_record_id"], source)
    assert copied
    unit = store.data_units(data_unit_ids=[data_id])[0]
    assert unit["source_path_kind"] == "project_relative"
    assert not Path(unit["source_path"]).is_absolute()
    assert store.resolve_source_path(unit).read_bytes() == source.read_bytes()
    store.save_inspection(
        data_id,
        {"selected_channel_names": ["A"], "selected_epoch_indices": [0, 2], "time_selection": {"start_s": 0.0, "end_s": 1.0}},
        notes="reviewed",
        channel_mapping=[{"channel_name": "A", "region": "CTX"}],
    )
    inspected = store.data_units(data_unit_ids=[data_id])[0]
    assert inspected["inspection_status"] == "checked"
    assert inspected["epoch_selection"] == {"indices": [0, 2]}
    assert inspected["inspection_revision"] == 1
    assert inspected["inspection_fingerprint"]
    assert store.inspection_history(data_id)[0]["action"] == "inspection_edit"

    moved = tmp_path / "moved_project"
    shutil.copytree(store.paths.root, moved)
    reopened = ProjectStore(moved)
    reopened_unit = reopened.data_units(data_unit_ids=[data_id])[0]
    assert reopened.resolve_source_path(reopened_unit).read_bytes() == b"portable-source"


def test_import_targets_existing_state_id_and_never_creates_same_label_state(tmp_path: Path):
    source_a = tmp_path / "first.fif"
    source_b = tmp_path / "second.fif"
    source_a.write_bytes(b"first")
    source_b.write_bytes(b"second")
    store = ProjectStore.create(tmp_path / "project", "Stable target")
    first_subject = store.add_subject("Mouse01")
    second_subject = store.add_subject("Mouse02")
    first_session = store.add_session(first_subject, "Day1")
    second_session = store.add_session(second_subject, "Day1")
    first_t0 = store.add_state_record(first_session, "T0", timepoint_value=0.0)
    second_t0 = store.add_state_record(second_session, "T0", timepoint_value=0.0)

    first_data, _ = store.import_data_unit(first_t0, source_a)
    second_data, _ = store.import_data_unit(second_t0, source_b)

    assert len(store.state_records()) == 2
    assert store.data_units(data_unit_ids=[first_data])[0]["state_record_id"] == first_t0
    assert store.data_units(data_unit_ids=[second_data])[0]["state_record_id"] == second_t0
    with pytest.raises(ValueError, match="already registered"):
        store.import_data_unit(first_t0, source_a)
    assert len(store.state_records()) == 2


def test_inspection_change_preserves_successful_run_and_marks_validity(tmp_path: Path):
    source = tmp_path / "record.fif"
    source.write_bytes(b"record")
    store = ProjectStore.create(tmp_path / "project", "Inspection validity")
    data_id = _hierarchy(store, source)
    store.register_analysis(
        {
            "analysis_id": "analysis_old", "data_unit_id": data_id, "module_name": "PSD", "method_name": "welch",
            "result_path": "results/old", "schema_version": "1.0", "parameter_fingerprint": "params",
            "data_fingerprint": "data", "parameters_json": "{}", "calculation_status": "completed",
            "save_status": "saved", "review_status": "pending", "review_notes": None,
            "created_at_utc": "2026-01-01T00:00:00+00:00", "completed_at_utc": "2026-01-01T00:00:01+00:00",
            "active": 1, "warnings_json": "[]", "error_message": None,
        }
    )
    saved = store.save_inspection(
        data_id,
        {"selected_channel_names": ["A"], "selected_epoch_indices": [0]},
        status="in_progress",
        action="epoch_edit",
    )
    result = store.analysis_results({"analysis_id": "analysis_old"})[0]
    assert result["calculation_status"] == "completed"
    assert result["save_status"] == "saved"
    assert result["active"] == 1
    assert result["result_validity"] == "needs_recompute"
    assert saved["revision"] == 1


def test_exact_duplicate_state_merge_is_backed_up_and_preserves_data(tmp_path: Path):
    source = tmp_path / "record.fif"
    source.write_bytes(b"record")
    store = ProjectStore.create(tmp_path / "project", "Duplicate migration")
    subject = store.add_subject("Mouse01")
    session = store.add_session(subject, "Day1")
    store.add_state_record(session, "T0", timepoint_value=0.0)
    second = store.add_state_record(session, "T0", timepoint_value=0.0)
    data_id = store.add_data_unit(second, source)

    preview = store.duplicate_state_preview()
    assert len(preview) == 1
    assert preview[0]["safe_to_merge"] is True
    outcome = store.merge_duplicate_states(preview[0]["state_ids"])
    assert Path(outcome["backup_path"]).is_file()
    assert len(store.state_records()) == 1
    assert store.data_units(data_unit_ids=[data_id])[0]["state_record_id"] == outcome["canonical_state_id"]


def test_structure_template_creates_persistent_idempotent_hierarchy_folders(tmp_path: Path):
    parent = tmp_path / "中文 项目根目录"
    store = ProjectStore.create_named(parent, "中文 模板项目")
    template = {
        "subjects": [{"subject_code": "Mouse01"}, {"subject_code": "Mouse02"}],
        "sessions": [{"session_key": "Day1"}, {"session_key": "Day7"}],
        "states": [
            {"display_name": "T20", "timepoint_value": 20.0, "timepoint_unit": "min"},
            {"display_name": "T40", "timepoint_value": 40.0, "timepoint_unit": "min"},
            {"display_name": "T60", "timepoint_value": 60.0, "timepoint_unit": "min"},
        ],
    }

    plan = store.preview_structure_template(template)
    assert (plan["subjects_created"], plan["sessions_created"], plan["states_created"]) == (2, 4, 12)
    first = store.apply_structure_template(template)
    assert (first["subjects_created"], first["sessions_created"], first["states_created"]) == (2, 4, 12)
    assert len(store.subjects()) == 2
    assert len(store.sessions()) == 4
    assert len(store.state_records()) == 12
    assert all((store.paths.root / row["relative_path"]).is_dir() for row in store.subjects())
    assert all((store.paths.root / row["relative_path"]).is_dir() for row in store.sessions())
    assert all((store.paths.root / row["relative_path"]).is_dir() for row in store.state_records())
    assert (store.paths.subjects / "Mouse01" / "Day1" / "T20").is_dir()
    assert (store.paths.subjects / "Mouse02" / "Day7" / "T60").is_dir()

    reopened = ProjectStore(store.paths.root)
    assert (len(reopened.subjects()), len(reopened.sessions()), len(reopened.state_records())) == (2, 4, 12)
    repeated = reopened.apply_structure_template(template)
    assert (repeated["subjects_created"], repeated["sessions_created"], repeated["states_created"]) == (0, 0, 0)
    assert (repeated["subjects_reused"], repeated["sessions_reused"], repeated["states_reused"]) == (2, 4, 12)

    extended = {**template, "states": [*template["states"], {"display_name": "T80", "timepoint_value": 80.0, "timepoint_unit": "min"}]}
    incremental = reopened.apply_structure_template(extended)
    assert (incremental["subjects_created"], incremental["sessions_created"], incremental["states_created"]) == (0, 0, 4)
    assert len(reopened.state_records()) == 16
    assert all((reopened.paths.root / row["relative_path"]).is_dir() for row in reopened.state_records())

    other = ProjectStore.create_named(parent, "第二个 项目")
    other.apply_structure_template(template)
    assert len(other.state_records()) == 12
    assert len(reopened.state_records()) == 16


def test_structure_template_folder_failure_rolls_back_records(tmp_path: Path, monkeypatch):
    store = ProjectStore.create(tmp_path / "project", "Failure project")
    template = {
        "subjects": [{"subject_code": "Mouse01"}],
        "sessions": [{"session_key": "Day1"}],
        "states": [{"display_name": "T20", "timepoint_value": 20.0, "timepoint_unit": "min"}],
    }
    original = store._create_structure_directories
    calls = 0

    def fail_during_apply(paths):
        nonlocal calls
        calls += 1
        if calls == 1:
            return original(paths)
        raise OSError("simulated folder write failure")

    monkeypatch.setattr(store, "_create_structure_directories", fail_during_apply)
    with pytest.raises(OSError, match="simulated folder write failure"):
        store.apply_structure_template(template)
    assert store.subjects() == []
    assert store.sessions() == []
    assert store.state_records() == []


def test_structure_template_reuses_stale_empty_folder_but_not_nonempty_folder(tmp_path: Path):
    template = {
        "subjects": [{"subject_code": "Mouse01"}],
        "sessions": [{"session_key": "Day1"}],
        "states": [{"display_name": "T20", "timepoint_value": 20.0, "timepoint_unit": "min"}],
    }
    empty_store = ProjectStore.create(tmp_path / "empty", "Empty folder retry")
    stale = empty_store.paths.subjects / "Mouse01"
    stale.mkdir()
    empty_store.apply_structure_template(template)
    assert empty_store.subjects()[0]["relative_path"] == "subjects/Mouse01"
    assert (stale / "Day1" / "T20").is_dir()

    occupied_store = ProjectStore.create(tmp_path / "occupied", "Occupied folder")
    occupied = occupied_store.paths.subjects / "Mouse01"
    occupied.mkdir()
    (occupied / "keep.txt").write_text("do not overwrite", encoding="utf-8")
    occupied_store.apply_structure_template(template)
    assert occupied_store.subjects()[0]["relative_path"] == "subjects/Mouse01 (2)"
    assert (occupied / "keep.txt").read_text(encoding="utf-8") == "do not overwrite"


def test_opening_schema_two_project_backfills_hierarchy_paths_and_folders(tmp_path: Path):
    store = ProjectStore.create(tmp_path / "project", "Migration project")
    store.apply_structure_template(
        {
            "subjects": [{"subject_code": "Mouse01"}],
            "sessions": [{"session_key": "Day1"}],
            "states": [{"display_name": "T20", "timepoint_value": 20.0, "timepoint_unit": "min"}],
        }
    )
    with store.transaction() as connection:
        connection.execute("UPDATE subjects SET relative_path=NULL")
        connection.execute("UPDATE sessions SET relative_path=NULL")
        connection.execute("UPDATE state_records SET relative_path=NULL")
        connection.execute("UPDATE projects SET schema_version=2")
        connection.execute("UPDATE schema_info SET version=2")
    shutil.rmtree(store.paths.subjects)

    reopened = ProjectStore(store.paths.root)
    assert reopened.project["schema_version"] == 6
    assert reopened.subjects()[0]["relative_path"] == "subjects/Mouse01"
    assert reopened.sessions()[0]["relative_path"] == "subjects/Mouse01/Day1"
    assert reopened.state_records()[0]["relative_path"] == "subjects/Mouse01/Day1/T20"
    assert (reopened.paths.subjects / "Mouse01" / "Day1" / "T20").is_dir()


def test_project_tree_shows_empty_template_nodes_and_reveals_applied_branch(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6 import QtCore
    from PySide6.QtWidgets import QApplication, QTreeWidgetItemIterator

    from lfp_analysis.project_gui import ProjectWorkspace

    store = ProjectStore.create(tmp_path / "project", "Template tree")
    result = store.apply_structure_template(
        {
            "subjects": [{"subject_code": "Mouse01"}, {"subject_code": "Mouse02"}],
            "sessions": [{"session_key": "Day1"}, {"session_key": "Day7"}],
            "states": [
                {"display_name": "T20", "timepoint_value": 20.0, "timepoint_unit": "min"},
                {"display_name": "T40", "timepoint_value": 40.0, "timepoint_unit": "min"},
                {"display_name": "T60", "timepoint_value": 60.0, "timepoint_unit": "min"},
            ],
        }
    )
    app = QApplication.instance() or QApplication([])
    window = ProjectWorkspace(store, Path("configs/luna.yaml"), Path("metadata"))
    window.show()
    app.processEvents()
    identities: list[tuple[str, str]] = []
    texts: list[str] = []
    iterator = QTreeWidgetItemIterator(window.hierarchy)
    while iterator.value() is not None:
        item = iterator.value()
        identity = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if isinstance(identity, tuple):
            identities.append((str(identity[0]), str(identity[1])))
        texts.append(item.text(0))
        iterator += 1
    assert sum(kind == "subject" for kind, _ in identities) == 2
    assert sum(kind == "session" for kind, _ in identities) == 4
    assert sum(kind == "state" for kind, _ in identities) == 12
    assert sum("未导入数据" in text for text in texts) == 12
    window._reveal_hierarchy_nodes(result["state_ids"])
    selected = window.hierarchy.currentItem()
    assert selected is not None
    assert selected.parent().isExpanded()
    assert selected.parent().parent().isExpanded()
    assert Path(selected.toolTip(0)).is_dir()
    window.close()


def test_apply_template_button_uses_current_editor_and_logs_result(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication, QDialog

    from lfp_analysis.project_gui import StructureTemplateDialog

    store = ProjectStore.create(tmp_path / "project", "Button project")
    app = QApplication.instance() or QApplication([])
    dialog = StructureTemplateDialog(store)
    dialog.subjects_edit.setPlainText("Mouse01\nMouse02")
    dialog.sessions_edit.setPlainText("Day1\nDay7")
    dialog.states_edit.setPlainText("T20,20,min\nT40,40,min\nT60,60,min")
    dialog.apply_button.click()
    app.processEvents()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.apply_result is not None
    assert dialog.apply_result["states_created"] == 12
    assert len(store.state_records()) == 12
    operation_log = store.paths.logs / "project_operations.jsonl"
    assert operation_log.is_file()
    assert '"status": "completed"' in operation_log.read_text(encoding="utf-8")


def test_project_workspace_separates_manage_batch_filter_and_review(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    from lfp_analysis.project_gui import ProjectFilterExportDialog, ProjectWorkspace

    source = tmp_path / "synthetic.fif"
    source.write_bytes(b"synthetic")
    store = ProjectStore.create(tmp_path / "project", "GUI roles")
    data_id = _hierarchy(store, source)
    app = QApplication.instance() or QApplication([])
    manage = ProjectWorkspace(store, Path("configs/luna.yaml"), Path("metadata"), mode="manage")
    batch = ProjectWorkspace(store, Path("configs/luna.yaml"), Path("metadata"), mode="batch", initial_data_unit_ids=[data_id])
    filter_view = ProjectWorkspace(store, Path("configs/luna.yaml"), Path("metadata"), mode="filter")
    review = ProjectWorkspace(store, Path("configs/luna.yaml"), Path("metadata"), mode="review")
    for window in (manage, batch, filter_view, review):
        window.show()
    app.processEvents()
    assert [manage.tabs.tabText(0), batch.tabs.tabText(0), filter_view.tabs.tabText(0), review.tabs.tabText(0)] == [
        "Project data", "Batch analysis", "Filter / export list", "Review results",
    ]
    assert batch.batch_data_table.columnCount() == 9
    assert filter_view.filter_export_dialog.table.columnCount() == len(ProjectFilterExportDialog.COLUMNS)
    assert filter_view.filter_export_dialog.table.rowCount() == 1
    for window in (manage, batch, filter_view, review):
        window.close()


def test_paired_summary_matches_stable_subject_id_not_row_order(tmp_path: Path):
    store = ProjectStore.create(tmp_path / "project", "Paired project")
    project = store.paths.root
    for subject_index in range(2):
        subject_id = store.add_subject(f"M{subject_index + 1:02d}", "paired")
        session_id = store.add_session(subject_id, "Day7")
        for timepoint in (80.0, 100.0):
            source = tmp_path / f"M{subject_index + 1:02d}_T{int(timepoint)}.fif"
            source.write_bytes(f"{subject_index}-{timepoint}".encode())
            state_id = store.add_state_record(session_id, f"T{int(timepoint)}", condition_label="L-DOPA", timepoint_value=timepoint)
            data_id = store.add_data_unit(state_id, source)
            bundle = project / "results" / data_id / "band_power"
            bundle.mkdir(parents=True)
            value = subject_index + timepoint / 100.0
            pd.DataFrame({"channel_name": ["A"], "band": ["delta"], "absolute_power": [value]}).to_csv(bundle / "band_power_summary.csv", index=False)
            aid = f"analysis_{data_id}"
            result = write_result_manifest(
                bundle,
                identities={"project_id": store.project["project_id"], "subject_id": subject_id, "session_id": session_id, "state_record_id": state_id, "data_unit_id": data_id},
                module_name="Band Power", method_name="welch", parameters={"same": True}, data_fingerprint=data_id,
                source={"path": str(source)}, selections={}, channel_mapping=[], sampling_rate_hz=1000.0, signal_unit="V",
                tables={"band_power_summary": "band_power_summary.csv"}, analysis_identifier=aid,
            )
            store.register_analysis({
                "analysis_id": aid, "data_unit_id": data_id, "module_name": "Band Power", "method_name": "welch",
                "result_path": str(bundle.relative_to(project)), "schema_version": result["schema_version"],
                "parameter_fingerprint": result["parameter_fingerprint"], "data_fingerprint": result["data_fingerprint"],
                "parameters_json": "{\"same\": true}", "calculation_status": "completed", "save_status": "saved",
                "review_status": "approved", "review_notes": None, "created_at_utc": result["created_at_utc"],
                "completed_at_utc": result["created_at_utc"], "active": 1, "warnings_json": "[]", "error_message": None,
            })

    common = {"session_key": "Day7", "condition_label": "L-DOPA", "module_name": "Band Power"}
    first = select_results(store, {**common, "timepoint_value": 80.0})
    second = select_results(store, {**common, "timepoint_value": 100.0})
    paired = paired_subject_summary(
        store,
        first,
        second,
        "band_power_summary",
        "absolute_power",
        [],
        first_filters={"band": "delta"},
        second_filters={"band": "delta"},
    )
    assert paired["subject_code"].tolist() == ["M01", "M02"]
    assert paired["absolute_power_first"].tolist() == [0.8, 1.8]
    assert paired["absolute_power_second"].tolist() == [1.0, 2.0]
    reader = ProjectResults(project)
    long = reader.to_long_table([first.included.iloc[0]["analysis_id"]], "band_power_summary", ["absolute_power"])
    assert {"subject_id", "analysis_id", "metric", "value", "value_unit", "summary_level", "quality_flag"}.issubset(long.columns)
