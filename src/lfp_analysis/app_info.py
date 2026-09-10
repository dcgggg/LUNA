"""Application identity and user-facing defaults for LUNA."""

from __future__ import annotations

from . import __version__

APP_NAME = "LUNA"
APP_FULL_NAME = "Local field potential Unified Network Analysis platform"
APP_DESCRIPTION = "A modular GUI-based platform for multichannel local field potential analysis."
APP_VERSION = __version__
DEFAULT_OUTPUT_DIRNAME = "luna_gui"
DEFAULT_MAPPING_FILENAME = "experiment_mapping.json"
DEFAULT_CONFIG_FILENAME = "luna.yaml"


def window_title() -> str:
    return f"{APP_NAME} — {APP_FULL_NAME}"
