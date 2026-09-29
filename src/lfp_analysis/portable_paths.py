"""Platform-neutral parsing and resolution for persisted relative paths."""

from __future__ import annotations

from pathlib import Path, PurePosixPath, PureWindowsPath


def portable_path_name(value: str | Path) -> str:
    """Return the final path component for either Windows or POSIX text."""
    raw = str(value) if value is not None else ""
    return PureWindowsPath(raw.replace("/", "\\")).name


def parse_portable_relative_path(
    value: str | Path,
    *,
    label: str = "project-relative path",
    allow_empty: bool = False,
) -> PurePosixPath:
    """Parse a stored relative path regardless of the host OS separators.

    Paths written by older Windows runs may use backslashes. They are treated
    as separators, while drive-qualified/UNC paths and traversal are rejected
    rather than being reinterpreted relative to the current working directory.
    """
    raw = str(value) if value is not None else ""
    if not raw or raw == ".":
        if allow_empty:
            return PurePosixPath()
        raise ValueError(f"{label} must name a relative item")

    windows = PureWindowsPath(raw)
    relative = PurePosixPath(raw.replace("\\", "/"))
    if windows.drive or windows.root or relative.is_absolute():
        raise ValueError(f"{label} must be relative: {value}")
    if ".." in relative.parts:
        raise ValueError(f"{label} escapes its containing directory: {value}")
    if not relative.parts:
        if allow_empty:
            return relative
        raise ValueError(f"{label} must name a relative item")
    return relative


def resolve_portable_relative_path(
    root: str | Path,
    value: str | Path,
    *,
    label: str = "project-relative path",
    allow_empty: bool = False,
) -> Path:
    """Resolve a portable relative path under ``root`` and prevent escape."""
    base = Path(root).expanduser().resolve()
    relative = parse_portable_relative_path(value, label=label, allow_empty=allow_empty)
    candidate = base.joinpath(*relative.parts) if relative.parts else base
    resolved = candidate.resolve()
    try:
        resolved.relative_to(base)
    except ValueError as exc:
        raise ValueError(f"{label} escapes its containing directory: {value}") from exc
    return resolved
