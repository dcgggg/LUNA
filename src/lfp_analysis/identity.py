"""Stable file identity and metadata-registry matching helpers.

These helpers deliberately keep file identity separate from experimental identity.
An input file can be analysed at file level when its animal/session is unknown,
but a basename or upload prefix is never used to invent those fields.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

import pandas as pd


def normalize_path(value: str | Path, base_dir: str | Path | None = None) -> Path:
    """Return an absolute, normalized path without touching the file."""
    path = Path(value).expanduser()
    if not path.is_absolute() and base_dir is not None:
        path = Path(base_dir).expanduser() / path
    return path.resolve(strict=False)


def _path_key(value: str | Path, base_dir: str | Path | None = None) -> str:
    return os.path.normcase(str(normalize_path(value, base_dir)))


def stable_file_uid(path: str | Path, sha256: str) -> str:
    """Create a deterministic UID from normalized path and content hash.

    The path component prevents two same-named files in different folders from
    colliding, while the hash makes replacement content a new file identity.
    This is an internal file key, not an animal identifier.
    """
    canonical = f"{_path_key(path)}\0{str(sha256).strip().lower()}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def resolve_registry_match(
    files: pd.DataFrame,
    input_path: str | Path,
    metadata_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Resolve a file-table row without ambiguous basename matching.

    Exact normalized paths are preferred. A basename fallback is accepted only
    when it has exactly one candidate. Ambiguous matches intentionally return no
    registry row so callers can continue a file-only analysis with an explicit
    warning rather than attaching the wrong animal/session.
    """
    normalized_input = normalize_path(input_path)
    result: dict[str, Any] = {
        "status": "unregistered",
        "normalized_path": str(normalized_input),
        "candidate_file_ids": [],
        "registry_row": None,
    }
    if files is None or files.empty or "file_path" not in files.columns:
        return result

    metadata_base = normalize_path(metadata_dir) if metadata_dir is not None else None
    frame = files.copy()
    input_key = _path_key(normalized_input)

    def registry_path_matches(value: Any) -> bool:
        candidates = {_path_key(value)}
        if metadata_base is not None:
            candidates.add(_path_key(value, metadata_base))
            candidates.add(_path_key(value, metadata_base.parent))
        return input_key in candidates

    exact = frame.loc[frame["file_path"].map(registry_path_matches)]
    if len(exact) == 1:
        row = exact.iloc[0].to_dict()
        result.update(
            {
                "status": "exact_unique",
                "registry_row": row,
                "registry_file_id": row.get("file_id", ""),
                "candidate_file_ids": [row.get("file_id", "")],
            }
        )
        return result
    if len(exact) > 1:
        result.update(
            {
                "status": "exact_conflict",
                "candidate_file_ids": exact.get("file_id", pd.Series(dtype=object)).fillna("").astype(str).tolist(),
            }
        )
        return result

    basename = normalized_input.name.casefold()
    fallback = frame.loc[frame["file_path"].map(lambda value: Path(str(value)).name.casefold() == basename)]
    candidate_ids = fallback.get("file_id", pd.Series(dtype=object)).fillna("").astype(str).tolist()
    if len(fallback) == 1:
        row = fallback.iloc[0].to_dict()
        result.update(
            {
                "status": "basename_unique_fallback",
                "registry_row": row,
                "registry_file_id": row.get("file_id", ""),
                "candidate_file_ids": candidate_ids,
            }
        )
    elif len(fallback) > 1:
        result.update({"status": "basename_conflict", "candidate_file_ids": candidate_ids})
    return result
