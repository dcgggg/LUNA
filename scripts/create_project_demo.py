"""Create a clearly labelled synthetic multi-subject LUNA demonstration project.

This script never reads or copies experimental data.  It creates inspectable
metadata and saved-result bundles for GUI/project-management validation.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from lfp_analysis.project_store import ProjectStore, utc_now
from lfp_analysis.result_contract import RESULT_SCHEMA_VERSION, write_result_manifest


def create_demo(output: str | Path) -> ProjectStore:
    root = Path(output).expanduser().resolve()
    store = ProjectStore.create(root, "SYNTHETIC LUNA project demo", "Five virtual subjects; not experimental data")
    sources = root / "synthetic_sources"
    sources.mkdir()
    bands = ["delta", "theta", "beta"]
    for subject_index in range(1, 6):
        subject_code = f"SYN{subject_index:02d}"
        subject_id = store.add_subject(subject_code, "synthetic_control" if subject_index <= 2 else "synthetic_treatment", {"synthetic": True})
        session_id = store.add_session(subject_id, "Day7", "Synthetic repeated-state demonstration")
        timepoints = [80.0] if subject_index == 5 else [80.0, 100.0]
        for timepoint in timepoints:
            repeats = 2 if subject_index == 4 and timepoint == 100.0 else 1
            for repeat in range(repeats):
                state_id = store.add_state_record(
                    session_id,
                    f"T{int(timepoint)}" + (f" repeat {repeat + 1}" if repeats > 1 else ""),
                    condition_label="SYNTHETIC_DRUG",
                    timepoint_value=timepoint,
                    timepoint_unit="min",
                    reference_event="synthetic administration",
                    attributes={"synthetic": True, "repeat_index": repeat},
                )
                source = sources / f"{subject_code}_Day7_T{int(timepoint)}_{repeat + 1}.synthetic"
                source.write_text("SYNTHETIC PLACEHOLDER - NOT ELECTROPHYSIOLOGY DATA\n", encoding="utf-8")
                mapping = [
                    {"channel_name": "SYN_CH1", "physical_channel_number": "1", "region": "CTX", "label": ""},
                    {"channel_name": "SYN_CH2", "physical_channel_number": "2", "region": "CTX", "label": ""},
                    {"channel_name": "SYN_CH3", "physical_channel_number": "3", "region": "STR", "label": ""},
                    {"channel_name": "SYN_CH4", "physical_channel_number": "4", "region": "ALT" if subject_index == 5 else "STR", "label": ""},
                ]
                data_id = store.add_data_unit(state_id, source, channel_mapping=mapping, sampling_rate_hz=1000.0, signal_unit="V", validity_status="synthetic_demo")
                bundle = root / "results" / data_id / "band_power"
                bundle.mkdir(parents=True)
                values = pd.DataFrame(
                    [
                        {
                            "channel_name": channel["channel_name"],
                            "region": channel["region"],
                            "band": band,
                            "band_low_hz": {"delta": 1.0, "theta": 4.0, "beta": 12.0}[band],
                            "band_high_hz": {"delta": 4.0, "theta": 8.0, "beta": 30.0}[band],
                            "absolute_power": (subject_index + timepoint / 100.0 + repeat * 0.2) * (band_index + 1) * (channel_index + 1) * 1e-7,
                            "relative_power": 0.1 * (band_index + 1),
                            "n_epochs": 24 - subject_index,
                            "status": "ok",
                        }
                        for channel_index, channel in enumerate(mapping)
                        for band_index, band in enumerate(bands)
                    ]
                )
                values.to_csv(bundle / "band_power_summary.csv", index=False)
                params = {"bands": {"delta": [1.0, 4.0], "theta": [4.0, 8.0], "beta": [12.0, 30.0]}, "epoch_aggregation": "median" if subject_index == 3 else "mean", "synthetic": True}
                manifest = write_result_manifest(
                    bundle,
                    identities={"project_id": store.project["project_id"], "subject_id": subject_id, "session_id": session_id, "state_record_id": state_id, "data_unit_id": data_id},
                    module_name="Band Power",
                    method_name="integrated_psd",
                    parameters=params,
                    data_fingerprint=data_id,
                    source={"path": str(source), "synthetic": True},
                    selections={"epoch_indices": list(range(24 - subject_index))},
                    channel_mapping=mapping,
                    sampling_rate_hz=1000.0,
                    signal_unit="V",
                    tables={"band_power_summary": "band_power_summary.csv"},
                    quality={"n_epochs": 24 - subject_index, "synthetic": True},
                    warnings=["Synthetic demonstration result; never use for biological inference"],
                )
                store.register_analysis(
                    {
                        "analysis_id": manifest["analysis_id"], "data_unit_id": data_id, "module_name": "Band Power", "method_name": "integrated_psd",
                        "result_path": str(bundle.relative_to(root)), "schema_version": RESULT_SCHEMA_VERSION,
                        "parameter_fingerprint": manifest["parameter_fingerprint"], "data_fingerprint": manifest["data_fingerprint"],
                        "parameters_json": json.dumps(params, sort_keys=True), "calculation_status": "completed", "save_status": "saved",
                        "review_status": "approved", "review_notes": "Synthetic demo review", "created_at_utc": manifest["created_at_utc"],
                        "completed_at_utc": utc_now(), "active": 1, "warnings_json": json.dumps(manifest["warnings"]), "error_message": None,
                    }
                )
    first_data_id = store.data_units()[0]["data_unit_id"]
    failed_job = store.create_batch_job("Synthetic failed-task example", ["PSD"], {}, [first_data_id], {first_data_id: {}})
    store.set_batch_job_status(failed_job, "completed_with_errors", started=True, finished=True)
    store.set_batch_item_status(failed_job, first_data_id, "failed", error_message="Synthetic failure for interface validation", started=True, finished=True)
    return store


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, help="New project directory; must not already contain project.sqlite3")
    args = parser.parse_args()
    store = create_demo(args.output)
    print(json.dumps({"project_root": str(store.paths.root), "project_id": store.project["project_id"], "subjects": len(store.subjects()), "data_units": len(store.data_units()), "results": len(store.analysis_results())}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
