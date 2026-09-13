"""Packaged LUNA resources and safe access helpers."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path


def packaged_resource_path(relative_path: str) -> Path:
    """Return a packaged resource path for a normal wheel installation."""
    parts = tuple(part for part in Path(relative_path).parts if part not in {"", "."})
    if any(part == ".." for part in parts):
        raise ValueError("resource path must not contain '..'")
    resource = files(__name__).joinpath(*parts)
    if not resource.is_file():
        raise FileNotFoundError(f"Packaged LUNA resource not found: {relative_path}")
    if not isinstance(resource, Path):
        raise TypeError("Packaged resources are not available as filesystem paths in this installation")
    return resource
