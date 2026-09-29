from pathlib import Path
from types import SimpleNamespace

from lfp_analysis.app_paths import (
    default_config_directory,
    default_metadata_directory,
    default_output_directory,
    user_config_directory,
    user_data_directory,
)
from lfp_analysis.optional_dependencies import optional_method_availability
from lfp_analysis.ui_fonts import choose_ui_font_family


def test_user_directories_follow_platform_conventions_without_touching_system_paths(tmp_path: Path) -> None:
    home = tmp_path / "home"
    assert user_data_directory(system="Darwin", home=home) == home / "Library" / "Application Support" / "LUNA"
    assert user_config_directory(system="Darwin", home=home) == home / "Library" / "Application Support" / "LUNA" / "config"
    assert user_data_directory(system="Windows", home=home, environ={"LOCALAPPDATA": "D:/Local"}) == Path("D:/Local/LUNA")
    assert user_config_directory(system="Windows", home=home, environ={"APPDATA": "D:/Roaming"}) == Path("D:/Roaming/LUNA")
    xdg_data = tmp_path / "xdg-data"
    assert user_data_directory(system="Linux", home=home, environ={"XDG_DATA_HOME": str(xdg_data)}) == xdg_data / "luna"
    assert user_data_directory(system="Linux", home=home, environ={"XDG_DATA_HOME": "relative/data"}) == home / ".local" / "share" / "luna"


def test_checkout_paths_preserve_existing_project_convention_and_installs_use_user_folders(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    (checkout / "src" / "lfp_analysis").mkdir(parents=True)
    (checkout / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    (checkout / "metadata").mkdir()
    (checkout / "configs").mkdir()
    assert default_metadata_directory(checkout) == checkout / "metadata"
    assert default_config_directory(checkout) == checkout / "configs"
    assert default_output_directory(checkout) == checkout / "results" / "luna_gui"
    assert default_output_directory(tmp_path / "installed" / "site-packages") != tmp_path / "installed" / "site-packages" / "results"


def test_optional_method_reports_only_its_own_missing_package() -> None:
    available, hint = optional_method_availability("MIC", module_finder=lambda _name: None)
    assert not available
    assert "mne-connectivity" in hint
    assert ".[connectivity]" in hint
    assert optional_method_availability("PSD", module_finder=lambda _name: None) == (True, "")


def test_optional_method_disables_backend_with_import_error_or_missing_api() -> None:
    def broken_import(_name: str) -> object:
        raise ImportError("incompatible backend API")

    available, hint = optional_method_availability(
        "MIC",
        module_finder=lambda _name: object(),
        module_importer=broken_import,
    )
    assert not available
    assert "cannot be imported" in hint
    assert "mne-connectivity" in hint

    available, hint = optional_method_availability(
        "wpli",
        module_finder=lambda _name: object(),
        module_importer=lambda _name: object(),
    )
    assert not available
    assert "spectral_connectivity_epochs" in hint


def test_parameterization_requires_the_configured_or_supported_fallback_backend() -> None:
    specparam_module = SimpleNamespace(SpectralModel=object())
    fooof_module = SimpleNamespace(FOOOF=object())

    def check_with(modules):
        return optional_method_availability(
            "FOOOF",
            module_finder=lambda name: object() if name in modules else None,
            module_importer=lambda name: modules[name],
        )

    available, hint = check_with({})
    assert not available
    assert ".[parameterization]" in hint
    assert "specparam" in hint.lower() and "fooof" in hint.lower()

    # The default specparam request may use the existing FOOOF compatibility fallback.
    assert check_with({"fooof": fooof_module}) == (True, "")
    assert check_with({"specparam": specparam_module}) == (True, "")

    # An explicitly configured classic FOOOF backend must not be replaced by specparam.
    available, hint = optional_method_availability(
        "FOOOF",
        parameterization_backend="fooof",
        module_finder=lambda name: object() if name == "specparam" else None,
        module_importer=lambda _name: specparam_module,
    )
    assert not available
    assert "FOOOF" in hint


def test_font_selection_uses_installed_platform_family() -> None:
    assert choose_ui_font_family({"PingFang SC", "Arial"}, "Darwin") == "PingFang SC"
    assert choose_ui_font_family({"Segoe UI", "Arial"}, "Windows") == "Segoe UI"
