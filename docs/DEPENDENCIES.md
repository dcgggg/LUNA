# Dependencies, installation and platform support

This guide describes dependencies actually used by the current LUNA code. The version ranges are declared in `pyproject.toml`; package installation must happen in the same Python environment used to launch LUNA.

## Install groups

| Install | Enables | Extra packages |
|---|---|---|
| `pip install .` | FIF input, quality checks, PSD, band power and core GUI-independent analysis APIs | Core NumPy, SciPy, pandas, Matplotlib, PyYAML, MNE-Python |
| `pip install ".[gui]"` | PySide6 desktop GUI | PySide6 |
| `pip install ".[connectivity]"` | MIC, MIM, wPLI, debiased squared wPLI, dPLI and other implemented MNE-Connectivity estimators | **MNE-Connectivity (`mne-connectivity`), a separate distribution from MNE-Python (`mne`)** |
| `pip install ".[tde]"` | Time-delay analysis | PyBispectra |
| `pip install ".[parameterization]"` | specparam and the compatibility FOOOF backend | specparam 2.0.0rc7, FOOOF 1.1.x |
| `pip install ".[desktop]"` | GUI and every currently implemented optional analysis method | PySide6, MNE-Connectivity, PyBispectra, specparam, FOOOF |
| `pip install ".[dev]"` | Tests and linting | pytest, Ruff |
| `pip install ".[all]"` | All optional methods plus notebooks and developer tools | Includes JupyterLab and test/lint packages; larger than a normal user install |

MNE-Python is used for FIF reading and signal structures. It does **not** include the separately distributed MNE-Connectivity algorithms. The LUNA `connectivity` extra explicitly installs `mne-connectivity`; installing only the core package or GUI extra is insufficient for those indicators. The GUI checks optional imports and required API symbols before enabling MIC/MIM/wPLI/dPLI, TDE, and FOOOF/specparam. A missing optional backend disables only its affected method and provides the installation extra; PSD, quality checks, and other installed methods remain available. LUNA does not replace a missing connectivity estimator with another metric.

FOOOF/specparam availability follows the configured `parameterization.backend`: an explicit `fooof` selection requires the `fooof` package; the default `specparam` selection accepts specparam or the existing FOOOF compatibility fallback. If both are absent, the GUI disables FOOOF and points to `.[parameterization]`. When the compatibility fallback is used, the saved fit rows identify `backend_used` and include `backend_warning`; this is a backend fallback within the parameterization module, not a different analysis indicator.

## Transitive dependencies and API compatibility

The code directly depends on the core packages and optional backends listed above. Their package metadata declares additional requirements that pip resolves automatically. For the currently declared optional methods, these include:

- MNE-Connectivity: `netCDF4`, `xarray`, scikit-learn, `tqdm`, and its compatible MNE/NumPy/SciPy requirements. Its installed 0.9.0 package metadata was checked locally; the upstream install guide confirms that `mne-connectivity` is installed as its own distribution, separate from MNE-Python.
- PyBispectra: Numba/llvmlite, joblib, scikit-learn, and its compatible MNE/NumPy/SciPy requirements.
- PySide6: matching `shiboken6`, `PySide6_Essentials`, and `PySide6_Addons` wheels.
- specparam/FOOOF: NumPy and SciPy; plotting/data extras are supplied by LUNA's own core requirements.

These are transitive package requirements, not packages the user should install by guessing. If an import fails despite a successful resolver, export diagnostics: a missing module, an API mismatch, or a binary-load error is recorded separately. The tested API in this checkout is MNE-Connectivity 0.9.0. Its documented API adds `fdecim` and `n_components` in 0.8. In an isolated Python 3.11 environment with MNE 1.13.2, an exploratory `--no-deps` import check of MNE-Connectivity 0.8.0 and 0.8.1 failed (`mne.fixes.jit` is unavailable), although package metadata checks did not flag the API mismatch. This observation is not evidence about another user's machine; it motivated the conservative optional lower bound `>=0.9,<1`. A normal fresh install of the current LUNA desktop extra resolved 0.9.0, which imported and completed the real-file method run. PyBispectra 1.3.2, specparam 2.0.0rc7 and FOOOF 1.1.1 are installed in the local test environment.

`threadpoolctl` is an optional diagnostic aid for reporting loaded numerical thread pools; it is not a required analysis dependency. `numba`, `llvmlite`, `netCDF4`, `xarray`, `joblib` and scikit-learn should normally arrive through their owning backend's dependency metadata.

A source-import audit on 2026-09-29 found no undeclared direct third-party imports in the production Python modules and launch scripts: imports map to the core requirements or the GUI/connectivity/TDE/parameterization extras. `shiboken6` is used with Qt and is supplied as a PySide6 dependency; it should not be installed as a separately guessed package. The dependency list intentionally distinguishes direct requirements from transitive packages.

Core-only wheel smoke check (Windows x64/Python 3.11, isolated temporary venv): with no GUI or analysis extras installed, the standalone diagnostic module still generated a report and marked PySide6/MNE-Connectivity `not_installed`. Its connectivity self-test correctly returned `dependency_unavailable`, named the `connectivity` install extra and exited nonzero (2); `pip check` remained clean. This verifies dependency-missing diagnostics, not the connectivity algorithms or macOS runtime.

## Clean installation

Python metadata allows `>=3.11,<3.13`. Windows x64 has been exercised on both Python 3.11.9 and a clean Python 3.12.14 environment. The latest full suite for the current checkout passed 136 tests on both versions with the declared dependencies; Python 3.12 also passed the fixed-FIF connectivity/save/reload smoke test. Ruff, compileall and dependency consistency checks passed. The GUI checks used Qt's offscreen backend, not native mouse/display interaction. This does not establish macOS support; macOS still requires its own CI/native validation.

Windows PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install ".[desktop]"
luna-gui
```

macOS Terminal (run under the native architecture's Python, not an unintended Rosetta interpreter):

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install ".[desktop]"
luna-gui
```

To add test tools, install `.[desktop,dev]`. To install only one missing method into an already-active environment, use the matching extra, for example `python -m pip install ".[connectivity]"`. Confirm the interpreter before diagnosing mixed installs with:

```text
python -c "import sys, lfp_analysis; print(sys.executable); print(lfp_analysis.__file__)"
```

The repository's `requirements-lock.txt` is a snapshot from the Windows/Python 3.11 developer environment. It is not a cross-platform lock and may contain platform-specific packages. For local exact reproduction, a user can record the resolved environment *after* installation with `python -m pip freeze > requirements-local.txt`; keep such a snapshot specific to its OS, architecture and Python version. `pyproject.toml` remains the maintained cross-platform constraint source.

## Launch and diagnosis without the GUI

From a source checkout on Windows, use `python scripts/run_gui.py`; after installation, use `luna-gui` or `python -m lfp_analysis.gui`. `lfp-analysis` and `luna` remain the analysis CLI entry points. Installed wheels use packaged YAML/logo resources and default writable data/config/result/log directories under the operating system's user application directories; source checkouts keep the repository's existing `metadata/`, `configs/` and `results/` conventions.

Generate a privacy-conscious diagnostic report without starting Qt:

```text
python -m lfp_analysis.diagnostics --output luna-diagnostic.json
```

Equivalent installed command: `luna-diagnose --output luna-diagnostic.json`. Optional flags:

```text
python -m lfp_analysis.diagnostics --output luna-diagnostic.json --output-dir /path/to/results
python -m lfp_analysis.diagnostics --output luna-diagnostic.json --input /path/to/epochs-epo.fif
```

If the installed `luna-diagnose` command is missing in a source-checkout development environment, first use the module form above with the intended interpreter. Then regenerate the current checkout's console scripts in that same environment with `python -m pip install --no-deps -e .`; this refreshes LUNA's editable installation without changing its dependencies. For a normal user installation, rerun the documented `python -m pip install ".[desktop]"` command in the environment used to launch LUNA. Do not switch interpreters or remove an older distribution solely to make the command appear. If diagnostics report multiple distributions owning `lfp_analysis`, compare `sys.executable` and `lfp_analysis.__file__` and resolve the environment intentionally; LUNA reports the condition but does not uninstall packages automatically. When it is unclear which editable installation is active, use a fresh virtual environment rather than deleting package records or shared launchers by hand.

The FIF option reads header/epoch metadata with preload disabled; it does not export signal samples or channel names. Reports include platform/Python/architecture, package versions/import status/API symbols, LUNA and optional module locations, duplicate distribution ownership of the `lfp_analysis` namespace, numerical thread pools, selected safe thread settings, and writable-directory probes. Home/custom paths are redacted. Never attach raw data, tokens, or a full environment dump.

Each failed GUI analysis writes a JSON report in its run directory's `diagnostics/` folder. Unhandled worker failures go under the user's LUNA log directory; the GUI log points to the report. Connectivity failure tables retain the failed stage and traceback alongside method, shape, sampling rate, effective parameters and rank diagnostics; no signal samples are included.

## Platform status

| Platform | Current evidence | Status |
|---|---|---|
| Windows x64, Python 3.11 | Python 3.11.9 developer environment; current full suite 136 passed, connectivity synthetic tests, optional backend tests, fixed-FIF analysis and Qt offscreen GUI tests run locally | Exercised; this does not prove the separate user's computer is the same environment |
| Windows x64, Python 3.12 | Clean Python 3.12.14 venv installed from the current wheel with `.[desktop,dev]`; current full suite 136 passed, dependency consistency, Ruff, compileall and fixed-FIF five-method connection/save/reload smoke all passed | Exercised in a temporary isolated environment; Qt tests were offscreen, not native desktop interaction |
| macOS Apple Silicon | `uv pip compile --only-binary :all:` resolved the declared `.[desktop,dev]` dependency set for arm64 on Python 3.11 and 3.12; CI smoke job targets `macos-15` | Dependency wheel resolution only; not installed or executed on macOS, GUI/data/save/reopen remain unverified |
| macOS Intel | The same wheel-only resolver check succeeded for x86_64 on Python 3.11 and 3.12; CI smoke job targets `macos-15-intel` | Dependency wheel resolution only; no Intel Mac runtime, GUI/data/save/reopen remain unverified. GitHub currently plans this Intel runner label through August 2027 |
| Linux | Path helpers have an XDG user-directory branch; no native desktop deployment test is included in this task | Not validated as a desktop platform |

Across Windows/macOS, user data, configuration, results, logs and temp directories avoid writing to an installed package directory. Project-internal source references remain project-relative; an external source path that no longer exists still requires explicit user relocation and is never resolved by selecting a same-named file automatically.

## Validation entry points

The repository's `.github/workflows/platform-smoke.yml` installs declared desktop/method extras on Windows x64, macOS Apple Silicon (`macos-15`) and macOS Intel (`macos-15-intel`), then runs the standalone synthetic connectivity diagnostic, synthetic connection compute/save/reload test, an offscreen GUI import→PSD→save→history-reload test, Qt window regressions, API checks, general diagnostics, entry-point help and the full automated suite. Qt tests are explicitly opted in with `LUNA_RUN_QT_TESTS=1`; without it, four pre-existing window tests remain skipped when `CI=true`. Each matrix job is configured to retain the two sanitized diagnostic JSON reports as a downloadable artifact for seven days, including after test failures; reports contain no study signal samples. These jobs are configured but have not run because this local-only task does not push the branch. Separately, on 2026-09-28, `uv pip compile --only-binary :all:` resolved all 52 packages in `.[desktop,dev]` for macOS arm64 and x86_64 on each of Python 3.11 and 3.12. This confirms compatible prebuilt distributions were found under the tested package-index state; it does not install/import those macOS binaries or test runtime behavior. A passing headless CI test will not validate native mouse/keyboard behavior, display scaling or a real desktop session. GitHub's runner reference lists the two macOS labels as separate architectures; see the official runner reference below.

## Official references checked

- [MNE-Connectivity installation requirements and separate pip installation](https://mne.tools/mne-connectivity/stable/install.html)
- [MNE-Connectivity spectral connectivity API](https://mne.tools/mne-connectivity/stable/generated/mne_connectivity.spectral_connectivity_epochs.html)
- [GitHub-hosted runner image labels and architectures](https://github.com/actions/runner-images/blob/main/README.md)
- [GitHub Actions macOS Intel runner lifecycle announcement](https://github.com/actions/runner-images/issues/13045)
- [PyBispectra installation and Python/Numba compatibility note](https://pybispectra.readthedocs.io/latest/installation.html)
- [Qt for Python supported platforms](https://doc.qt.io/qtforpython-6/overviews/qtdoc-supported-platforms.html)
- [GitHub-hosted runner images and macOS architectures](https://github.com/actions/runner-images)

## Optional synthetic connectivity self-test

Run python -m lfp_analysis.diagnostics --self-test-connectivity --output luna-diagnostic.json to exercise the installed LUNA connectivity core without using a study recording. The test uses six 3-second synthetic epochs, four channels split into two explicitly synthetic regions, 500 Hz sampling, and all currently implemented MNE-Connectivity methods. It records per-method status, frequency-grid bounds, estimator-call count, rank pairs, parameters and elapsed time; signal samples are not written to the report.

This checks execution/API compatibility, not scientific accuracy or another computer's real-data behavior. It does not read a study FIF unless --input is separately supplied. A missing backend is reported as dependency_unavailable; estimator failures include their stage and redacted traceback. The report is written even when the self-test fails, and the command returns exit code 2.
