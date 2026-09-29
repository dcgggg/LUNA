<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/branding/luna-logo-on-white.svg">
    <img src="assets/branding/luna-logo.svg" alt="LUNA — Local field potential Unified Network Analysis platform" width="760">
  </picture>
</p>

<h1 align="center">LUNA</h1>
<p align="center"><strong>Local field potential Unified Network Analysis platform</strong></p>
<p align="center"><em>From neural signals to insight — without getting lost in code.</em></p>

Neural electrophysiology is already complicated enough. Analyzing it should not have to be.

**LUNA** turns electrophysiological analysis into an intuitive visual workflow, bringing powerful tools for exploring neural signals, oscillations, spectral dynamics, and brain-wide interactions into a researcher-friendly GUI.

Whether you write Python every day or have never written a line of code, LUNA is designed to keep the focus where it belongs: **on the signals, the science, and the questions behind them.**

> **LUNA — let the signals speak.**

## ✨ What can LUNA do?

LUNA provides a visual, interactive workflow for neural electrophysiology analysis, from imported recordings to interpretable neural dynamics.

Instead of building an analysis pipeline from scratch, researchers can configure parameters, inspect each recording, review channel and brain-region views within that recording, and export analysis outputs through the graphical interface. Cross-subject and group-level statistics are intentionally performed by external scripts using the saved result contract.

Current analysis areas include:

- **Signal inspection and quality control** — inspect multichannel recordings, identify invalid or suspicious segments, and retain traceable quality information.
- **Channel and brain-region mapping** — define the relationship between recorded channels and brain regions without relying on a fixed experimental layout.
- **Power spectral density** — estimate spectra with multitaper or Welch methods and summarize configurable frequency bands.
- **Spectral parameterization** — separate periodic peaks from the aperiodic background and retain fitted curves, parameters, residuals, and failure information.
- **Band-power analysis** — compare absolute and relative power across epochs, channels, and regions.
- **Functional connectivity** — examine multiregion interactions with MIC, MIM, wPLI, debiased squared wPLI, and dPLI.
- **Time-delay analysis** — estimate conventional and antisymmetrized bispectral delays with explicit direction conventions.
- **Reproducible export** — save parameters, manifests, tabular results, numerical arrays, figures, and traceability records for each run.

Additional modules and interface refinements will be introduced as they become implemented and validated. Planned functionality is not presented as part of the current stable workflow.

## Why LUNA?

Electrophysiology analysis often requires researchers to move between scripts, file formats, plotting tools, and method-specific packages. This creates unnecessary friction and makes it harder to track how a result was produced.

LUNA brings these steps into one workspace while preserving the scientific choices behind them. Parameters remain visible, outputs remain traceable, and analysis methods remain linked to their established Python implementations.

## A unified workflow

LUNA is organized around a simple research flow:

1. Import electrophysiological recordings.
2. Inspect signal quality and recording metadata.
3. Define channels, brain regions, epochs, and analysis scope.
4. Configure spectral, parameterization, connectivity, or delay methods.
5. Review channel-level and region-level results.
6. Organize subjects, sessions, states and repeated recordings in a local project.
7. Run the same analysis core on one record or a recoverable batch.
8. Review and export saved results without rereading raw files; use the saved result contract for cross-subject or group-level statistics outside LUNA.

## Built for multiregion electrophysiology

LUNA is designed for multichannel local field potential and related neural field recordings, including LFP, EEG, ECoG, and SEEG-like data structures. Brain-region assignments are editable, allowing the same workflow to support different electrode layouts and experimental designs.

The platform focuses on field-potential analysis. Spike sorting and single-unit analysis are outside its present scope.

## A tool, not a black box

LUNA does not replace methodological judgment. It makes analytical decisions easier to inspect.

The platform records input identity, parameters, valid epochs, effective duration, quality status, exclusions, failures, and output provenance. Connectivity estimates are retained at appropriate channel-pair and region levels, and directional measures preserve their sign conventions instead of being silently symmetrized.

## Project status

LUNA is under active development. The current repository provides a traceable workflow for multichannel, multiregion LFP analysis using preprocessed FIF epochs. It includes a PySide6 desktop GUI, command-line analysis components, configurable metadata, synthetic validation, automated tests, and reusable plotting and export modules.

The current `0.3.0.dev2` development line adds local project management, portable installation paths, optional-backend diagnostics, and cross-platform packaging checks while preserving the single-file descriptive workflow. Raw experimental data are not stored in this repository and are never overwritten by the software. Animal-level inference remains unavailable when animal identity, session, treatment time point, or behavioral linkage is incomplete.

Current methodological safeguards include:

- preservation of `events`, `selection`, `drop_log`, and epoch provenance;
- checks for NaN/Inf values, flat signals, abnormal amplitude, saturation, duplicate segments, and residual line noise;
- no concatenation of discontinuous epochs into a false continuous recording;
- retention of full channel-pair information for connectivity analysis;
- explicit reporting of rank, dimensionality, stability, and method failures;
- separation of file-level description from animal-level statistical inference.

## Current release and validation boundary

The current source version is `0.3.0.dev2`, published as a GitHub prerelease when the corresponding release tag is created. This is a development snapshot, not a claim that every supported operating system or display configuration has been validated.

Validated for the current release line:

- Windows x64 with Python 3.11.9 in the repository environment and Python 3.12.14 in an isolated wheel environment;
- 136 automated tests with Qt offscreen tests explicitly enabled, plus Ruff, Python compilation, and `pip check`;
- the fixed read-only FIF sample: 21 retained epochs, 16 channels, 1000 Hz, 5-second epochs, and 105 seconds of accumulated valid epoch duration;
- installation-package resource loading, `luna-gui --help`, and `luna-diagnose --self-test-connectivity` on Windows;
- synthetic execution checks for MIC, MIM, wPLI, debiased squared wPLI, dPLI, imcoh, and coherence.

Not yet equivalent to native validation:

- macOS installation, native Qt rendering, and macOS scientific execution;
- native Windows mouse/DPI/multi-monitor inspection;
- real animal-level inference, LDN pairing, AIMs synchronization, and cross-subject statistics when the required metadata are absent.

See [Dependencies and cross-platform support](docs/DEPENDENCIES.md) for the exact environment boundary and diagnostic workflow. The GitHub [release list](https://github.com/dcgggg/LUNA/releases) contains the published prereleases and their wheel assets.

## The idea behind the name

**LUNA** stands for **Local field potential Unified Network Analysis platform**.

The name reflects the platform's goal: bringing local field potential signals, spectral dynamics, and multiregion network analysis into one coherent environment.

## Project structure

```text
configs/                Editable analysis configuration (default: configs/luna.yaml)
assets/branding/        LUNA branding assets, SVG logo, and release TIFF
data/real/              Local real FIF data; excluded from version control
data/synthetic/         Synthetic validation data location
metadata/               Animal, recording, file, epoch, behavior, and channel templates
notebooks/              Reproducible analysis notebooks
scripts/                Python entry points
src/lfp_analysis/       I/O, quality, spectral, connectivity, delay, GUI, and plotting modules
tests/                  Unit tests and synthetic-signal validation
docs/                   Analysis documentation and GUI guide
results/                Local outputs; excluded from version control
pyproject.toml          Project metadata and dependency definitions
requirements-lock.txt   Dependency snapshot for the current Windows environment
CHANGELOG.md            Version history and release validation notes
```

## Requirements and installation

Recommended environment:

- Python 3.11 or 3.12; the declared range is `>=3.11,<3.13`. Windows x64 was tested on Python 3.11.9 and 3.12.14. Native macOS workflow is not yet verified.
- Windows 10/11 is the currently exercised desktop environment. macOS installation paths and CI smoke checks are provided, but native macOS GUI/data workflow has not yet been run on this development machine.
- A dedicated virtual environment. Install and launch LUNA with the same interpreter; avoid mixing a global install, an old `mouse-lfp-analysis` install, and this checkout in one environment because they share the `lfp_analysis` import namespace.

### Windows PowerShell

Create the environment and install the GUI plus all currently implemented analysis backends from the repository root:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[desktop]"
```

Python 3.12 is also validated on Windows x64; replace `py -3.11` with `py -3.12` to create that environment.

If PowerShell blocks script activation, call the environment interpreter directly:

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[all]"
```

To reproduce the recorded dependency snapshot:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m pip install -e .
```

`requirements-lock.txt` is an auditable snapshot of the current Windows/Python 3.11 environment, not a portable macOS lockfile. `pyproject.toml` is the maintained source of Python and package version constraints.

### macOS (Apple Silicon or Intel)

Use Python 3.11 for your machine architecture and a fresh environment:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install ".[desktop]"
python -m lfp_analysis.diagnostics --output luna-diagnostic.json
luna-gui
```

From a source checkout, use `python -m pip install -e ".[desktop]"`. For core analysis without the desktop and optional backends, install `python -m pip install .`; add `.[gui]`, `.[connectivity]`, `.[tde]`, or `.[parameterization]` only for features needed. Exact platform wheel availability is controlled by upstream projects; macOS Apple Silicon and Intel still require native validation (see [Dependencies and cross-platform support](docs/DEPENDENCIES.md)).

The default configuration is [`configs/luna.yaml`](configs/luna.yaml), which extends the analysis settings in [`configs/default.yaml`](configs/default.yaml).

Official environment references:

- [Python downloads](https://www.python.org/downloads/)
- [Python virtual environments](https://docs.python.org/3.11/library/venv.html)
- [Python Packaging Guide](https://packaging.python.org/en/latest/guides/installing-using-pip-and-virtual-environments/)

## Quick start

Start the desktop GUI from PyCharm by opening [`scripts/run_gui.py`](scripts/run_gui.py) and selecting **Run**, or run:

```powershell
.\.venv\Scripts\python.exe scripts\run_gui.py
```

After installing `.[desktop]`, the installed cross-platform command is `luna-gui` (or `python -m lfp_analysis.gui`). To create a shareable, redacted environment report without starting Qt, run `python -m lfp_analysis.diagnostics --output luna-diagnostic.json`; optionally add `--input /path/to/epochs-epo.fif` to inspect FIF header metadata only. To check that the installed connectivity backend can execute each supported MNE-Connectivity method without using study data, add `--self-test-connectivity`; this uses synthetic signals and returns a nonzero exit code if a method fails. The report excludes signal samples and channel names. See [diagnostic and dependency guide](docs/DEPENDENCIES.md).

To confirm that PyCharm or a terminal is using this checkout rather than an older editable installation, run:

```powershell
\.venv\Scripts\python.exe -c "import lfp_analysis, sys; print(sys.executable); print(lfp_analysis.__file__); print(lfp_analysis.__version__)"
```

The reported module path should be this checkout or the intended installed wheel environment. If it points to an older project, create a fresh virtual environment and install LUNA there; do not mix the historical `mouse-lfp-analysis` distribution with this checkout.

For a single FIF file without the GUI:

```powershell
.\.venv\Scripts\python.exe -m lfp_analysis.cli single-file `
  --input "C:\path\to\your-epochs.fif" `
  --config configs\luna.yaml `
  --output results\your-file
```

The same single-file workflow is available in [`scripts/run_single_file.py`](scripts/run_single_file.py) for interactive PyCharm inspection. Do not copy raw FIF data into the repository. Results are written to a separate output directory with input identity, parameters, quality information, and provenance.

After importing data, verify the actual channel names and edit the Channel Mapping table if needed. Region pairs are generated from the active mapping; the historical M1/STR/PF/SNr layout is only a sample template, not a fixed experiment definition.

### Project workflow

Use the **Project** button or **Project** menu in the GUI to create/open a local project. Creating a project asks only for a readable project name and a parent folder; that name becomes the actual project-folder name. Imported recordings are copied into `data/raw/` by default, verified by size and SHA-256, registered with a project-relative path, and never modify the external source. Existing projects that still reference external files can use the explicit **Organize data into project** action. LUNA keeps stable internal identities in `project.sqlite3` but hides them from the normal project tree.

In **Structure template**, **Save template** stores only a reusable definition. **Apply current structure** creates persistent subject/session/state records and matching readable folders under `subjects/`; empty states remain visible as “未导入数据”, and applying the same template again reuses existing nodes.

The project manager is intentionally limited to hierarchy/template management, batch import, metadata/inspection status, filtering and exporting a machine-readable data list, and sending selected data to the main analysis window. Single-record inspection and batch calculation use the same calculation core. LUNA no longer provides an in-app cross-record A/B comparison page or group-statistics workflow; use `ProjectResults` or the exported CSV/JSON list from an independent script. Batch parameters are copied from the visible single-record controls; data-specific channel, epoch and time selections remain attached to each data unit.

Use **Save project** or `Ctrl+S` in the Project Manager to save structure, imports and metadata changes. A dirty project offers Save/Discard/Cancel when the manager closes; inspection autosave and analysis-result autosave remain separate. Opening a project data unit restores readable saved result bundles directly, without rerunning analysis. Use **结果参数** to inspect the saved parameters and **历史版本** to choose another saved run; **应用为待运行参数** only copies a historical configuration into the pending controls. When the source FIF is unavailable, saved results can still be browsed, but raw-dependent inspection and recomputation require the source.

Project schema 6 also stores lightweight behavior attachments, scores and synchronization metadata, and explicit session display order. Missing scores remain blank and a recorded score of zero remains zero; LUNA does not process video or infer unverified epoch-level synchronization. Historical comparison snapshot files remain readable for compatibility, but are not opened by the current GUI.

Saved project results use the versioned LUNA result contract and can be queried without Qt:

```powershell
.\.venv\Scripts\python.exe scripts\read_project_results.py C:\path\to\project `
  --session-key Day7 --condition L-DOPA --timepoint 100 --module "Band Power"
```

See [Project workflow](docs/PROJECT_WORKFLOW.md) and [Result schema](docs/RESULT_SCHEMA.md). A five-subject synthetic demonstration can be created with `scripts/create_project_demo.py`; it is clearly marked and is not experimental data.

## Dependencies

### Core dependencies

| Package | Purpose | Documentation |
|---|---|---|
| NumPy | Array and numerical computation | [numpy.org](https://numpy.org/) |
| SciPy | Spectral estimation, filtering, and signal processing | [scipy.org](https://scipy.org/) |
| pandas | Metadata and result tables | [pandas.pydata.org](https://pandas.pydata.org/) |
| Matplotlib | PNG and SVG figures | [matplotlib.org](https://matplotlib.org/) |
| PyYAML | YAML configuration | [PyYAML documentation](https://pyyaml.org/wiki/PyYAMLDocumentation) |
| MNE-Python | FIF input and electrophysiology data structures | [MNE documentation](https://mne.tools/stable/) |

### Analysis, GUI, and development dependencies

| Package | Purpose | Documentation |
|---|---|---|
| MNE-Connectivity | MIC, MIM, wPLI, dPLI, and related connectivity estimates | [MNE-Connectivity](https://mne.tools/mne-connectivity/stable/) |
| PyBispectra | Bispectral time-delay analysis | [PyBispectra documentation](https://pybispectra.readthedocs.io/) |
| specparam | Periodic and aperiodic spectral parameterization | [specparam on PyPI](https://pypi.org/project/specparam/) |
| FOOOF | Compatibility backend for spectral parameterization | [FOOOF documentation](https://fooof-tools.github.io/fooof/) |
| PySide6 | Desktop GUI and background tasks | [Qt for Python](https://doc.qt.io/qtforpython-6/) |
| JupyterLab | Notebook environment | [jupyter.org](https://jupyter.org/) |
| pytest | Automated tests | [pytest documentation](https://docs.pytest.org/) |
| Ruff | Python linting | [Ruff documentation](https://docs.astral.sh/ruff/) |

Dependency groups are defined in `pyproject.toml`:

```text
.[connectivity]       MNE-Connectivity
.[tde]                PyBispectra
.[parameterization]   specparam and FOOOF
.[notebook]           JupyterLab, Notebook, and ipykernel
.[desktop]            PySide6 + all currently implemented optional analysis backends
.[dev]                pytest and Ruff
.[all]                All optional analysis, notebook, and development dependencies
```

Important: **MNE-Python (`mne`) and MNE-Connectivity (`mne-connectivity`) are separate distributions.** The core install includes MNE-Python for FIF I/O, but MIC, MIM, wPLI, dPLI and the other MNE-Connectivity estimators require the separate `mne-connectivity` package. Install it in the same environment as LUNA with `python -m pip install -e ".[connectivity]"`, or include it via `.[desktop]` / `.[all]`. This project currently requires MNE-Connectivity `>=0.9,<1`; LUNA never silently substitutes another connectivity algorithm when this backend is unavailable. The GUI checks optional backend imports and required API symbols before enabling MIC/MIM/wPLI/dPLI, TDE and FOOOF/specparam; missing methods show the extra needed while core methods remain usable.

MNE-Connectivity brings its own required packages (including `netCDF4`, `xarray` and scikit-learn); PyBispectra brings its numerical dependencies (including Numba/llvmlite and joblib). Install the LUNA extras instead of manually guessing those transitive packages. See the dependency guide for method mapping, platform notes and diagnostics.

## Analysis conventions and limitations

- Connectivity is estimated within the same animal, recording session, and treatment time point using multiple valid epochs. Data are not mixed across animals, days, or time points.
- Channels, epochs, and channel pairs are repeated measurements within an animal and must not be treated as independent animals.
- MIC retains signed raw values. Absolute magnitude may be used for clearly labelled visualization but does not establish causal direction.
- MIM retains its original unnormalized interaction value and is not forced into a 0–1 range.
- wPLI, dPLI, and debiased squared wPLI retain all valid channel pairs. dPLI uses 0.5 as the neutral reference and is not mirrored as a second estimate.
- Time-delay signs follow the declared seed-to-target convention and do not prove anatomical or causal direction.
- Quality flags do not silently delete data.
- Frequency bands, thresholds, rank settings, and delay ranges are editable starting points rather than universally validated physiological boundaries.

For the detailed frequency-axis and line-noise display policy, see [`docs/connectivity_frequency_diagnostics.md`](docs/connectivity_frequency_diagnostics.md). Unknown animal identity, treatment metadata, and behavior linkage remain blank rather than being inferred from filenames.

## Validation

Run the local checks from the project root:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check src tests scripts
.\.venv\Scripts\python.exe -m compileall -q src scripts tests
.\.venv\Scripts\python.exe -m pip check
```

The repository includes synthetic tests for PSD, band power, parameterization, connectivity, time delay, mapping, GUI state, and saved-result handling. The fixed real sample used for file-level checks is not distributed with the repository.

## Documentation

Detailed guides and method notes are maintained outside the main README:

- [GUI guide](docs/gui_guide.md)
- [Analysis plan and implementation notes](docs/analysis_plan.md)
- [Development and reproducibility commands](docs/DEVELOPMENT.md)
- [Dependencies and cross-platform support](docs/DEPENDENCIES.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Developer handoff](docs/HANDOFF.md)
- [Development log](docs/DEV_LOG.md)
- [Metadata definitions](metadata/README.md)
- [Project status](docs/PROJECT_STATUS.md)
- [Project workflow](docs/PROJECT_WORKFLOW.md)
- [Versioned result contract](docs/RESULT_SCHEMA.md)
- [Analysis workflow and figure-reading guide](docs/ANALYSIS_GUIDE.md)
- [Saved result and metric data dictionary](docs/RESULT_DATA_DICTIONARY.md)
- [Figure–field–function index](docs/FIGURE_RESULT_INDEX.md)

Repository: [https://github.com/dcgggg/LUNA.git](https://github.com/dcgggg/LUNA.git)

## References

- [MNE-Connectivity spectral connectivity API](https://mne.tools/mne-connectivity/stable/generated/mne_connectivity.spectral_connectivity_epochs.html)
- [MNE-Connectivity MIC/MIM example](https://mne.tools/mne-connectivity/stable/auto_examples/mic_mim.html)
- [SciPy Welch documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.welch.html)
- [FOOOF model fitting tutorial](https://fooof-tools.github.io/fooof/auto_tutorials/plot_02-FOOOF.html)
- [PyBispectra examples](https://pybispectra.readthedocs.io/latest/examples.html)
- [PyBispectra JOSS article](https://doi.org/10.21105/joss.08504)
- [PyBispectra time-delay paper](https://arxiv.org/abs/2502.17474)

## License

This repository does not yet declare an open-source license. Until a license is added, reuse and redistribution are not automatically granted. Raw experimental data are not distributed with the code.
