"""Availability checks for optional analysis backends."""

from collections.abc import Callable
from importlib import import_module
from importlib.util import find_spec

OPTIONAL_METHOD_DEPENDENCIES = {
    "MIC": ("mne_connectivity", "mne-connectivity", "connectivity", ("spectral_connectivity_epochs",)),
    "MIM": ("mne_connectivity", "mne-connectivity", "connectivity", ("spectral_connectivity_epochs",)),
    "wpli": ("mne_connectivity", "mne-connectivity", "connectivity", ("spectral_connectivity_epochs",)),
    "dpli": ("mne_connectivity", "mne-connectivity", "connectivity", ("spectral_connectivity_epochs",)),
    "wpli2_debiased": ("mne_connectivity", "mne-connectivity", "connectivity", ("spectral_connectivity_epochs",)),
    "Time Delay": ("pybispectra", "pybispectra", "tde", ("TDE", "compute_fft")),
}
_FAILED_DEFAULT_IMPORTS: dict[tuple[str, tuple[str, ...]], str] = {}


def _dependency_status(
    module_name: str,
    package_name: str,
    required_symbols: tuple[str, ...],
    *,
    module_finder: Callable[[str], object],
    module_importer: Callable[[str], object],
) -> tuple[bool, str]:
    try:
        if module_finder(module_name) is None:
            return False, f"{package_name} is not installed."
    except (ImportError, ModuleNotFoundError, ValueError, OSError) as exc:
        return False, f"{package_name} cannot be located ({type(exc).__name__})."

    cache_key = (module_name, required_symbols)
    uses_default_importers = module_finder is find_spec and module_importer is import_module
    if uses_default_importers and cache_key in _FAILED_DEFAULT_IMPORTS:
        return False, _FAILED_DEFAULT_IMPORTS[cache_key]
    try:
        module = module_importer(module_name)
    except Exception as exc:  # noqa: BLE001 - catch optional backend binary/API import failures
        hint = f"{package_name} is present but cannot be imported ({type(exc).__name__}); run LUNA diagnostics and check compatible versions."
        if uses_default_importers:
            _FAILED_DEFAULT_IMPORTS[cache_key] = hint
        return False, hint
    missing_symbols = [symbol for symbol in required_symbols if not hasattr(module, symbol)]
    if missing_symbols:
        hint = f"{package_name} is present but lacks required API symbols {', '.join(missing_symbols)}."
        if uses_default_importers:
            _FAILED_DEFAULT_IMPORTS[cache_key] = hint
        return False, hint
    return True, ""


def optional_method_availability(
    method: str,
    *,
    parameterization_backend: str = "specparam",
    module_finder: Callable[[str], object] = find_spec,
    module_importer: Callable[[str], object] = import_module,
) -> tuple[bool, str]:
    """Return dependency availability and an actionable method-specific hint."""
    if method == "FOOOF":
        backend = str(parameterization_backend).strip().casefold()
        candidates = (
            (("fooof", "FOOOF", ("FOOOF",)),)
            if backend == "fooof"
            else (("specparam", "specparam", ("SpectralModel",)), ("fooof", "FOOOF", ("FOOOF",)))
        )
        failures: list[str] = []
        for module_name, package_name, required_symbols in candidates:
            available, reason = _dependency_status(
                module_name,
                package_name,
                required_symbols,
                module_finder=module_finder,
                module_importer=module_importer,
            )
            if available:
                return True, ""
            failures.append(reason)
        backend_names = "FOOOF" if backend == "fooof" else "specparam or FOOOF"
        details = " ".join(item for item in failures if item)
        return (
            False,
            f"This method requires the configured {backend_names} parameterization backend; install LUNA with .[parameterization]. {details}".strip(),
        )

    dependency = OPTIONAL_METHOD_DEPENDENCIES.get(method)
    if dependency is None:
        return True, ""
    module_name, package_name, extra_name, required_symbols = dependency
    available, hint = _dependency_status(
        module_name,
        package_name,
        required_symbols,
        module_finder=module_finder,
        module_importer=module_importer,
    )
    if available:
        return True, ""
    return False, f"This method requires the separate {package_name} package; install LUNA with .[{extra_name}]. {hint}"
