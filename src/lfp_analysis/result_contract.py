"""Versioned, GUI-independent result bundle contract."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import uuid
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from . import __version__

RESULT_SCHEMA_VERSION = "1.0"
REQUIRED_IDENTITIES = ("project_id", "subject_id", "session_id", "state_record_id", "data_unit_id")


def canonical_fingerprint(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def analysis_id() -> str:
    return f"analysis_{uuid.uuid4().hex}"


def _dependencies() -> dict[str, str]:
    result = {"python": platform.python_version()}
    for name in ("numpy", "pandas", "scipy", "mne", "mne-connectivity", "specparam", "fooof", "pybispectra"):
        try:
            result[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            result[name] = "not_installed"
    return result


def describe_npz(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    descriptors: list[dict[str, Any]] = []
    with np.load(path, allow_pickle=False) as arrays:
        for name in arrays.files:
            value = arrays[name]
            descriptors.append({"name": name, "shape": list(value.shape), "dtype": str(value.dtype)})
    return descriptors


def write_result_manifest(
    bundle_dir: str | Path,
    *,
    identities: dict[str, str],
    module_name: str,
    method_name: str,
    parameters: dict[str, Any],
    data_fingerprint: str,
    source: dict[str, Any],
    selections: dict[str, Any],
    channel_mapping: list[dict[str, Any]] | dict[str, Any],
    sampling_rate_hz: float | None,
    signal_unit: str | None,
    tables: dict[str, str],
    arrays: dict[str, str] | None = None,
    axes: dict[str, list[str]] | None = None,
    units: dict[str, str] | None = None,
    numeric_spaces: dict[str, str] | None = None,
    quality: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
    upstream_analysis_ids: list[str] | None = None,
    status: str = "completed",
    save_status: str = "saved",
    analysis_identifier: str | None = None,
    inspection_snapshot: dict[str, Any] | None = None,
    condition_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = Path(bundle_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    missing = [field for field in REQUIRED_IDENTITIES if not str(identities.get(field, "")).strip()]
    if missing:
        raise ValueError(f"Missing stable result identities: {missing}")
    aid = analysis_identifier or analysis_id()
    array_records: list[dict[str, Any]] = []
    for label, relative in (arrays or {}).items():
        path = (root / relative).resolve()
        path.relative_to(root)
        for item in describe_npz(path):
            array_records.append({"file": relative, "label": label, **item, "axes": (axes or {}).get(item["name"], []), "unit": (units or {}).get(item["name"], ""), "numeric_space": (numeric_spaces or {}).get(item["name"], "linear")})
    manifest = {
        "schema_name": "luna-result-bundle",
        "schema_version": RESULT_SCHEMA_VERSION,
        "software_version": __version__,
        "analysis_id": aid,
        "analysis_run_id": aid,
        **{field: str(identities[field]) for field in REQUIRED_IDENTITIES},
        "state_id": str(identities["state_record_id"]),
        "dataset_id": str(identities["data_unit_id"]),
        "module_name": module_name,
        "method_name": method_name,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "calculation_status": status,
        "save_status": save_status,
        "data_fingerprint": data_fingerprint,
        "parameter_fingerprint": canonical_fingerprint(parameters),
        "effective_parameters": parameters,
        "source": source,
        "selection": selections,
        "inspection_snapshot": inspection_snapshot or {},
        "condition_metadata": condition_metadata or {},
        "channel_mapping": channel_mapping,
        "sampling_rate_hz": sampling_rate_hz,
        "signal_unit": signal_unit,
        "tables": tables,
        "arrays": array_records,
        "quality_summary": quality or {},
        "warnings": warnings or [],
        "invalid_value_policy": "NaN and explicit status fields are distinct from true zero",
        "upstream_analysis_ids": upstream_analysis_ids or [],
        "dependencies": _dependencies(),
        "bundle_complete": save_status == "saved" and status == "completed",
    }
    validate_manifest(manifest, root, require_files=True)
    target = root / "manifest.json"
    temporary = root / "manifest.json.tmp"
    temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temporary, target)
    return manifest


def validate_manifest(manifest: dict[str, Any], root: str | Path | None = None, *, require_files: bool = False) -> list[str]:
    errors: list[str] = []
    required = ("schema_name", "schema_version", "analysis_id", *REQUIRED_IDENTITIES, "module_name", "effective_parameters", "parameter_fingerprint", "data_fingerprint", "tables")
    for field in required:
        if field not in manifest or manifest[field] in (None, ""):
            errors.append(f"missing:{field}")
    if manifest.get("schema_name") != "luna-result-bundle":
        errors.append("invalid:schema_name")
    if str(manifest.get("schema_version")) != RESULT_SCHEMA_VERSION:
        errors.append(f"unsupported:schema_version={manifest.get('schema_version')}")
    if manifest.get("effective_parameters") is not None and canonical_fingerprint(manifest.get("effective_parameters")) != manifest.get("parameter_fingerprint"):
        errors.append("mismatch:parameter_fingerprint")
    aliases = {
        "analysis_run_id": "analysis_id",
        "state_id": "state_record_id",
        "dataset_id": "data_unit_id",
    }
    for alias, canonical in aliases.items():
        if alias in manifest and str(manifest[alias]) != str(manifest.get(canonical, "")):
            errors.append(f"mismatch:{alias}")
    if require_files and root is not None:
        base = Path(root).resolve()
        paths = list((manifest.get("tables") or {}).values()) + [item.get("file", "") for item in manifest.get("arrays", [])]
        for relative in paths:
            try:
                target = (base / str(relative)).resolve()
                target.relative_to(base)
            except ValueError:
                errors.append(f"unsafe_path:{relative}")
                continue
            if not target.is_file():
                errors.append(f"missing_file:{relative}")
    if errors:
        raise ValueError("Invalid LUNA result manifest: " + ", ".join(errors))
    return errors


def load_result_manifest(path: str | Path) -> dict[str, Any]:
    manifest_path = Path(path).expanduser().resolve()
    if manifest_path.is_dir():
        manifest_path = manifest_path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    validate_manifest(manifest, manifest_path.parent, require_files=True)
    manifest["bundle_dir"] = str(manifest_path.parent)
    return manifest


def load_table(manifest: dict[str, Any], table_name: str) -> pd.DataFrame:
    if table_name not in manifest.get("tables", {}):
        raise KeyError(f"Result table not found: {table_name}")
    root = Path(manifest["bundle_dir"]).resolve()
    path = (root / manifest["tables"][table_name]).resolve()
    path.relative_to(root)
    return pd.read_csv(path, low_memory=False)


def load_array(manifest: dict[str, Any], array_name: str) -> np.ndarray:
    matches = [item for item in manifest.get("arrays", []) if item.get("name") == array_name]
    if len(matches) != 1:
        raise KeyError(f"Expected one array named {array_name!r}; found {len(matches)}")
    root = Path(manifest["bundle_dir"]).resolve()
    path = (root / matches[0]["file"]).resolve()
    path.relative_to(root)
    with np.load(path, allow_pickle=False) as arrays:
        return np.asarray(arrays[array_name]).copy()
