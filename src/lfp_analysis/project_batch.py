"""Project-aware batch orchestration using the existing single-record core."""

from __future__ import annotations

import copy
import json
import threading
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .config import load_config
from .gui_engine import build_runtime_config, inspect_file, run_gui_analysis
from .mapping import mapping_rows
from .project_store import ProjectStore, utc_now
from .result_contract import (
    RESULT_SCHEMA_VERSION,
    canonical_fingerprint,
    write_result_manifest,
)

Progress = Callable[[str, int, int, str, str], None]

MODULE_TO_INDICATORS = {
    "Quality": ["Quality"],
    "PSD": ["PSD"],
    "Band Power": ["Band Power"],
    "FOOOF": ["FOOOF"],
    "MIC": ["MIC"],
    "MIM": ["MIM"],
    "wPLI": ["wpli"],
    "wPLI2 Debiased": ["wpli2_debiased"],
    "dPLI": ["dpli"],
    "Time Delay": ["Time Delay"],
}

INDICATOR_TO_RESULT_MODULE = {
    "Quality": "Quality", "PSD": "PSD", "Band Power": "Band Power", "FOOOF": "FOOOF",
    "MIC": "Connectivity", "MIM": "Connectivity", "wpli": "Connectivity",
    "wpli2_debiased": "Connectivity", "dpli": "Connectivity", "Time Delay": "Time Delay",
}


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def effective_parameters(project_template: dict[str, Any], task_config: dict[str, Any], data_override: dict[str, Any]) -> dict[str, Any]:
    """Apply the documented precedence: project -> task -> data-unit."""
    return deep_merge(deep_merge(project_template, task_config), data_override)


def _indicators(modules: list[str]) -> list[str]:
    selected: list[str] = []
    for module in modules:
        for indicator in MODULE_TO_INDICATORS.get(module, [module]):
            if indicator not in selected:
                selected.append(indicator)
    return selected


def _method_for(metric: str, parameters: dict[str, Any]) -> str:
    if metric == "PSD":
        return str(parameters.get("psd", {}).get("method", ""))
    if metric == "FOOOF":
        return str(parameters.get("parameterization", {}).get("backend", ""))
    if metric == "Connectivity":
        return ",".join(map(str, parameters.get("connectivity", {}).get("methods", [])))
    if metric == "Time Delay":
        return ",".join(map(str, parameters.get("time_delay", {}).get("methods", [])))
    return metric


def _array_paths(metric_record: dict[str, Any]) -> dict[str, str]:
    value = metric_record.get("paths", {}).get("arrays")
    if not value:
        return {}
    return {"primary": Path(str(value)).name}


def _axes_for(metric: str) -> dict[str, list[str]]:
    if metric == "PSD":
        return {
            "selected_data": ["epoch", "channel", "time"],
            "psd": ["epoch", "channel", "frequency"],
            "frequencies": ["frequency"],
            "epoch_indices": ["epoch"],
            "channel_array_indices": ["channel"],
            "sfreq": ["scalar"],
        }
    if metric == "Connectivity":
        return {name: ["connection_frequency_row"] for name in ("frequency_hz", "value_raw", "value_strength", "component_index", "method", "region_a", "region_b", "seed_region", "target_region", "direction_order", "seed_channel", "target_channel", "n_epochs", "rank_seed", "rank_target")}
    return {}


class ProjectBatchRunner:
    """Sequential, restartable batch runner.

    Sequential data-unit execution intentionally avoids multiplying data-level
    parallelism by algorithm-internal workers.  Each unit is loaded and released
    independently.
    """

    def __init__(self, store: ProjectStore, config_path: str | Path, metadata_dir: str | Path) -> None:
        self.store = store
        self.config_path = Path(config_path).resolve()
        self.metadata_dir = Path(metadata_dir).resolve()

    def create_job(self, data_unit_ids: list[str], modules: list[str], task_config: dict[str, Any] | None = None, name: str = "Batch analysis", *, reuse_existing: bool = True) -> str:
        if not data_unit_ids:
            raise ValueError("No data units selected")
        task_config = copy.deepcopy(task_config or {})
        project_template = self.store.project.get("analysis_template", {})
        scientific_task_config = {key: value for key, value in task_config.items() if key != "_luna_batch"}
        units = {row["data_unit_id"]: row for row in self.store.data_units(data_unit_ids=data_unit_ids)}
        missing = sorted(set(data_unit_ids) - set(units))
        if missing:
            raise KeyError(f"Unknown data units: {missing}")
        snapshots = {
            data_unit_id: effective_parameters(project_template, scientific_task_config, units[data_unit_id].get("analysis_override", {}))
            for data_unit_id in data_unit_ids
        }
        stored_task_config = {**task_config, "_luna_batch": {"reuse_existing": bool(reuse_existing)}}
        return self.store.create_batch_job(name, modules, stored_task_config, data_unit_ids, snapshots)

    def run(self, batch_job_id: str, progress: Progress | None = None, cancel_event: threading.Event | None = None) -> dict[str, Any]:
        progress = progress or (lambda _message, _done, _total, _data, _module: None)
        cancel_event = cancel_event or threading.Event()
        job_matches = [job for job in self.store.batch_jobs() if job["batch_job_id"] == batch_job_id]
        if not job_matches:
            raise KeyError(batch_job_id)
        job = job_matches[0]
        modules = list(job["modules"])
        reuse_existing = bool(job.get("task_config", {}).get("_luna_batch", {}).get("reuse_existing", True))
        items = list(job["items"])
        unit_records = {row["data_unit_id"]: row for row in self.store.data_units(data_unit_ids=[item["data_unit_id"] for item in items])}
        self.store.set_batch_job_status(batch_job_id, "running", started=True)
        completed = 0
        errors: list[dict[str, str]] = []
        for item in items:
            data_unit_id = item["data_unit_id"]
            if item["status"] in {"completed", "reused"}:
                completed += 1
                progress("item_already_completed", completed, len(items), data_unit_id, "")
                continue
            if cancel_event.is_set() or self.store.batch_cancel_requested(batch_job_id):
                self.store.set_batch_item_status(batch_job_id, data_unit_id, "cancelled", finished=True)
                continue
            unit = unit_records[data_unit_id]
            source = self.store.resolve_source_path(unit)
            if not source.is_file():
                message = "source_file_missing"
                self.store.set_batch_item_status(batch_job_id, data_unit_id, "failed", error_message=message, finished=True)
                errors.append({"data_unit_id": data_unit_id, "error": message})
                completed += 1
                continue
            effective = json.loads(item["effective_parameters_json"])
            self.store.set_batch_item_status(batch_job_id, data_unit_id, "running", started=True)
            progress(f"{unit['subject_code']} / {unit['session_key']} / {unit['state_display_name']}", completed, len(items), data_unit_id, "")
            try:
                inspected = inspect_file(source, self.metadata_dir, self.config_path)
                mapping = unit.get("channel_mapping") or mapping_rows(inspected["channel_table"])
                mapping_list = mapping.get("channels", []) if isinstance(mapping, dict) else mapping
                inspection = dict(unit.get("inspection") or {})
                inspected_channels = [str(value) for value in inspection.get("selected_channel_names", []) if str(value)]
                if inspected_channels:
                    allowed = set(inspected_channels)
                    mapping_list = [row for row in mapping_list if str(row.get("channel_name", "")) in allowed]
                epoch_selection = unit.get("epoch_selection", {})
                epoch_indices = epoch_selection.get("indices", list(range(int(inspected["n_epochs"]))))
                time_selection = unit.get("time_selection", {})
                selection = {
                    "time_start_s": float(time_selection.get("start_s", inspected["tmin"])),
                    "time_end_s": float(time_selection.get("end_s", inspected["tmax"] + 1.0 / inspected["sfreq"])),
                }
                regions = []
                for row in mapping_list:
                    region = str(row.get("region", "")).strip()
                    if region and region not in regions:
                        regions.append(region)
                pairs = [[regions[a], regions[b]] for a in range(len(regions)) for b in range(a + 1, len(regions))]
                snapshot = {
                    # Stable identities live in manifests/SQLite.  Keep the
                    # physical run directory short enough for Windows tools
                    # that still observe the traditional path-length limit.
                    "run_id": f"run_{uuid.uuid4().hex[:12]}",
                    "input_files": [str(source)],
                    "output_dir": str(self.store.paths.results / data_unit_id),
                    "indicators": _indicators(modules),
                    "selected_channel_names": [str(row.get("channel_name", "")) for row in mapping_list if row.get("channel_name")],
                    "selected_epoch_indices": list(map(int, epoch_indices)),
                    "selected_region_pairs": pairs,
                    "selection": selection,
                    "channel_mapping": mapping_list,
                    "values": effective,
                    "project_context": {
                        key: unit.get(key)
                        for key in (
                            "project_id", "subject_id", "session_id", "state_record_id", "data_unit_id",
                            "subject_code", "group_label", "session_key", "experiment_name", "session_date",
                            "condition_label", "timepoint_value", "timepoint_unit", "reference_event", "state_display_name",
                        )
                    },
                    "inspection_snapshot": {
                        "status": unit.get("inspection_status", "unchecked"),
                        "notes": unit.get("inspection_notes", ""),
                        "revision": int(unit.get("inspection_revision") or 0),
                        "fingerprint": unit.get("inspection_fingerprint"),
                        "source_structure_fingerprint": unit.get("source_structure_fingerprint"),
                        **inspection,
                    },
                }
                n_times = max(1, round((selection["time_end_s"] - selection["time_start_s"]) * float(inspected["sfreq"])))
                runtime = build_runtime_config(load_config(self.config_path), snapshot, float(inspected["sfreq"]), n_times)
                data_fingerprint = canonical_fingerprint({
                    "sha256": unit["source_sha256"], "selection": list(map(int, epoch_indices)),
                    "time": [selection["time_start_s"], selection["time_end_s"]], "mapping": mapping_list,
                    "inspection_fingerprint": unit.get("inspection_fingerprint"),
                })
                expected = self._expected_metric_parameters(runtime, snapshot["indicators"])
                if reuse_existing:
                    existing = self.store.analysis_results({
                        "active": 1,
                        "calculation_status": "completed",
                        "save_status": "saved",
                        "result_validity": "current",
                    })
                    reusable_modules = {
                        record["module_name"]
                        for record in existing
                        if record["data_unit_id"] == data_unit_id
                        and record["data_fingerprint"] == data_fingerprint
                        and record["module_name"] in expected
                        and record["parameter_fingerprint"] == canonical_fingerprint(expected[record["module_name"]])
                    }
                    snapshot["indicators"] = [indicator for indicator in snapshot["indicators"] if INDICATOR_TO_RESULT_MODULE[indicator] not in reusable_modules]
                    if not snapshot["indicators"]:
                        self.store.set_batch_item_status(batch_job_id, data_unit_id, "reused", finished=True)
                        completed += 1
                        progress("all requested results reused", completed, len(items), data_unit_id, "cache_hit")
                        continue
                result = run_gui_analysis(
                    snapshot,
                    self.config_path,
                    self.metadata_dir,
                    progress=lambda message, percent, done=completed, current=data_unit_id: progress(message, done, len(items), current, str(percent)),
                    cancel_event=cancel_event,
                )
                if result["manifest"]["status"] not in {"completed", "completed_with_errors"}:
                    raise RuntimeError(f"analysis_core_status={result['manifest']['status']}")
                if not result["manifest"].get("files"):
                    details = "; ".join(str(item.get("error", "")) for item in result["manifest"].get("errors", []))
                    raise RuntimeError(f"analysis core produced no successful file record: {details or 'unknown error'}")
                self._index_run(unit, effective, Path(result["run_dir"]), result["manifest"])
                self.store.set_batch_item_status(batch_job_id, data_unit_id, "completed", finished=True)
            except Exception as exc:  # noqa: BLE001 - one failed unit must not stop independent units
                message = f"{type(exc).__name__}: {exc}"
                errors.append({"data_unit_id": data_unit_id, "error": message})
                self.store.set_batch_item_status(batch_job_id, data_unit_id, "failed", error_message=message, finished=True)
            completed += 1
            progress("item_finished", completed, len(items), data_unit_id, "")
        cancelled = cancel_event.is_set() or self.store.batch_cancel_requested(batch_job_id)
        final_status = "cancelled" if cancelled else ("completed_with_errors" if errors else "completed")
        self.store.set_batch_job_status(batch_job_id, final_status, finished=True)
        return {"batch_job_id": batch_job_id, "status": final_status, "completed": completed, "total": len(items), "errors": errors}

    @staticmethod
    def _expected_metric_parameters(runtime: dict[str, Any], indicators: list[str]) -> dict[str, dict[str, Any]]:
        expected: dict[str, dict[str, Any]] = {}
        selected = set(indicators)
        if "Quality" in selected:
            expected["Quality"] = {}
        if selected.intersection({"PSD", "Band Power", "FOOOF"}):
            expected["PSD"] = runtime.get("psd", {})
        if "Band Power" in selected:
            expected["Band Power"] = {"bands": runtime.get("bands", {}), "relative_power": runtime.get("relative_power", {}), "epoch_aggregation": runtime.get("psd", {}).get("epoch_aggregation", "mean")}
        if "FOOOF" in selected:
            expected["FOOOF"] = {**runtime.get("parameterization", {}), "display_bands": runtime.get("bands", {})}
        if selected.intersection({"MIC", "MIM", "wpli", "dpli", "wpli2_debiased"}):
            expected["Connectivity"] = runtime.get("connectivity", {})
        if "Time Delay" in selected:
            expected["Time Delay"] = runtime.get("time_delay", {})
        return expected

    def _index_run(self, unit: dict[str, Any], parameters: dict[str, Any], run_dir: Path, run_manifest: dict[str, Any]) -> None:
        identities = {key: str(unit[key]) for key in ("project_id", "subject_id", "session_id", "state_record_id", "data_unit_id")}
        for file_record in run_manifest.get("files", []):
            file_dir = run_dir / file_record["file_dir"]
            file_manifest = json.loads((file_dir / "file_manifest.json").read_text(encoding="utf-8"))
            frozen_inspection = dict(file_manifest.get("inspection_snapshot") or {})
            frozen_context = dict(file_manifest.get("project_context") or {})
            frozen_fingerprint = frozen_inspection.get("fingerprint")
            result_validity = "current" if frozen_fingerprint == unit.get("inspection_fingerprint") else "needs_recompute"
            mapping_value = unit.get("channel_mapping", {})
            if isinstance(mapping_value, dict) and "channels" in mapping_value:
                mapping_value = mapping_value["channels"]
            selected_names = set(map(str, file_manifest.get("selected_channel_names", [])))
            effective_mapping = [
                row for row in mapping_value
                if not selected_names or str(row.get("channel_name", "")) in selected_names
            ]
            for metric_record in file_record.get("metrics", []):
                metric = str(metric_record["metric"])
                metric_dir_name = {"Band Power": "band_power", "Time Delay": "time_delay"}.get(metric, metric.lower())
                bundle_dir = file_dir / metric_dir_name
                table_paths = dict(metric_record.get("paths", {}).get("tables", {}))
                arrays = _array_paths(metric_record)
                aid = f"analysis_{Path(run_dir).name}_{metric_dir_name}"
                algorithm_status = str(metric_record.get("status", "completed"))
                calculation_status = "completed" if algorithm_status in {"ok", "completed"} else "failed"
                metric_parameters = dict(metric_record.get("parameters", {}))
                metric_parameters.pop("estimation_call_count", None)
                manifest = write_result_manifest(
                    bundle_dir,
                    identities=identities,
                    module_name=metric,
                    method_name=_method_for(metric, parameters),
                    parameters=metric_parameters,
                    data_fingerprint=canonical_fingerprint({
                        "sha256": unit["source_sha256"],
                        "selection": file_manifest.get("selected_epoch_indices"),
                        "time": [file_manifest.get("time_start_s"), file_manifest.get("time_end_s")],
                        "mapping": effective_mapping,
                        "inspection_fingerprint": frozen_inspection.get("fingerprint", unit.get("inspection_fingerprint")),
                    }),
                    source={
                        "path": unit["source_path"],
                        "path_kind": unit.get("source_path_kind", "external"),
                        "original_path": unit.get("original_source_path"),
                        "sha256": unit["source_sha256"],
                        "size_bytes": unit["source_size_bytes"],
                    },
                    selections={
                        "epoch_indices": file_manifest.get("selected_epoch_indices", []),
                        "channel_names": file_manifest.get("selected_channel_names", []),
                        "time_start_s": file_manifest.get("time_start_s"),
                        "time_end_s": file_manifest.get("time_end_s"),
                        "inspection_status": frozen_inspection.get("status", unit.get("inspection_status", "unchecked")),
                        "inspection": frozen_inspection.get("inspection", unit.get("inspection", {})),
                    },
                    inspection_snapshot=frozen_inspection or {
                        "revision": int(unit.get("inspection_revision") or 0),
                        "fingerprint": unit.get("inspection_fingerprint"),
                        "status": unit.get("inspection_status", "unchecked"),
                        "notes": unit.get("inspection_notes", ""),
                        "source_structure_fingerprint": unit.get("source_structure_fingerprint"),
                        "inspection": unit.get("inspection", {}),
                    },
                    condition_metadata={
                        "condition_label": frozen_context.get("condition_label", unit.get("condition_label")),
                        "timepoint_value": frozen_context.get("timepoint_value", unit.get("timepoint_value")),
                        "timepoint_unit": frozen_context.get("timepoint_unit", unit.get("timepoint_unit")),
                        "reference_event": frozen_context.get("reference_event", unit.get("reference_event")),
                        "session_key": frozen_context.get("session_key", unit.get("session_key")),
                    },
                    channel_mapping=effective_mapping,
                    sampling_rate_hz=unit.get("sampling_rate_hz") or file_manifest.get("runtime_config", {}).get("sampling_rate_hz"),
                    signal_unit=unit.get("signal_unit"),
                    tables=table_paths,
                    arrays=arrays,
                    axes=_axes_for(metric),
                    quality={"n_epochs": file_record.get("n_epochs"), "effective_duration_s": file_record.get("effective_valid_duration_s"), "algorithm_status": algorithm_status},
                    warnings=list(run_manifest.get("warnings", [])),
                    status=calculation_status,
                    analysis_identifier=aid,
                )
                self.store.register_analysis(
                    {
                        "analysis_id": aid,
                        "data_unit_id": unit["data_unit_id"],
                        "module_name": metric,
                        "method_name": manifest["method_name"],
                        "result_path": str(bundle_dir.relative_to(self.store.paths.root)),
                        "schema_version": RESULT_SCHEMA_VERSION,
                        "parameter_fingerprint": manifest["parameter_fingerprint"],
                        "data_fingerprint": manifest["data_fingerprint"],
                        "parameters_json": json.dumps(manifest["effective_parameters"], ensure_ascii=False, sort_keys=True),
                        "calculation_status": manifest["calculation_status"],
                        "save_status": manifest["save_status"],
                        "review_status": "pending",
                        "review_notes": None,
                        "created_at_utc": manifest["created_at_utc"],
                        "completed_at_utc": utc_now(),
                        "active": 1,
                        "warnings_json": json.dumps(manifest["warnings"], ensure_ascii=False),
                        "error_message": None,
                        "result_validity": result_validity,
                        "inspection_revision": int(frozen_inspection.get("revision", unit.get("inspection_revision") or 0)),
                        "inspection_fingerprint": frozen_inspection.get("fingerprint", unit.get("inspection_fingerprint")),
                    }
                )

    def index_completed_run(self, data_unit_id: str, parameters: dict[str, Any], run_dir: str | Path, run_manifest: dict[str, Any]) -> None:
        """Index a manually launched single-data-unit run in the project."""
        matches = self.store.data_units(data_unit_ids=[data_unit_id])
        if len(matches) != 1:
            raise KeyError(data_unit_id)
        self._index_run(matches[0], parameters, Path(run_dir).resolve(), run_manifest)
