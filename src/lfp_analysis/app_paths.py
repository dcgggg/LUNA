"""Cross-platform writable paths used by the LUNA desktop application."""

from __future__ import annotations

import os
import platform
from pathlib import Path

APP_DIRECTORY_NAME = "LUNA"


def _is_source_checkout(root: str | Path | None) -> bool:
    if root is None:
        return False
    path = Path(root).expanduser().resolve()
    return (path / "pyproject.toml").is_file() and (path / "src" / "lfp_analysis").is_dir()


def user_data_directory(*, system: str | None = None, home: str | Path | None = None, environ: dict[str, str] | None = None) -> Path:
    """Return the conventional per-user application data directory."""
    system = system or platform.system()
    home_path = Path(home).expanduser() if home is not None else Path.home()
    env = os.environ if environ is None else environ
    if system == "Windows":
        return Path(env.get("LOCALAPPDATA") or home_path / "AppData" / "Local") / APP_DIRECTORY_NAME
    if system == "Darwin":
        return home_path / "Library" / "Application Support" / APP_DIRECTORY_NAME
    root = _xdg_root(env.get("XDG_DATA_HOME"), home_path / ".local" / "share")
    return root / APP_DIRECTORY_NAME.lower()


def user_config_directory(*, system: str | None = None, home: str | Path | None = None, environ: dict[str, str] | None = None) -> Path:
    """Return the conventional per-user configuration directory."""
    system = system or platform.system()
    home_path = Path(home).expanduser() if home is not None else Path.home()
    env = os.environ if environ is None else environ
    if system == "Windows":
        return Path(env.get("APPDATA") or home_path / "AppData" / "Roaming") / APP_DIRECTORY_NAME
    if system == "Darwin":
        return home_path / "Library" / "Application Support" / APP_DIRECTORY_NAME / "config"
    root = _xdg_root(env.get("XDG_CONFIG_HOME"), home_path / ".config")
    return root / APP_DIRECTORY_NAME.lower()


def _xdg_root(value: str | None, fallback: Path) -> Path:
    """Honor XDG base directories only when they are absolute as specified."""
    if value:
        configured = Path(value).expanduser()
        if configured.is_absolute():
            return configured
    return fallback


def default_metadata_directory(project_root: str | Path | None = None) -> Path:
    """Use editable checkout metadata, or an empty writable user directory in installs."""
    if _is_source_checkout(project_root):
        metadata = Path(project_root).expanduser().resolve() / "metadata"
        if metadata.is_dir():
            return metadata
    return user_data_directory() / "metadata"


def default_config_directory(project_root: str | Path | None = None) -> Path:
    """Return a writable config destination without targeting site-packages."""
    if _is_source_checkout(project_root):
        config_dir = Path(project_root).expanduser().resolve() / "configs"
        if config_dir.is_dir():
            return config_dir
    return user_config_directory()


def default_output_directory(project_root: str | Path | None = None) -> Path:
    """Keep source-checkout behavior; installed applications write per-user."""
    if _is_source_checkout(project_root):
        return Path(project_root).expanduser().resolve() / "results" / "luna_gui"
    return user_data_directory() / "results" / "luna_gui"


def default_log_directory(project_root: str | Path | None = None) -> Path:
    """Return a writable application log directory."""
    if _is_source_checkout(project_root):
        return Path(project_root).expanduser().resolve() / "logs"
    return user_data_directory() / "logs"
