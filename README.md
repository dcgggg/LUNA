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

Instead of building an analysis pipeline from scratch, researchers can configure parameters, inspect results, compare channels and brain regions, and export analysis outputs through the graphical interface.

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
6. Export figures, tables, parameters, and provenance records.

Detailed operating tutorials will be maintained separately in the project documentation.

## Built for multiregion electrophysiology

LUNA is designed for multichannel local field potential and related neural field recordings, including LFP, EEG, ECoG, and SEEG-like data structures. Brain-region assignments are editable, allowing the same workflow to support different electrode layouts and experimental designs.

The platform focuses on field-potential analysis. Spike sorting and single-unit analysis are outside its present scope.

## Designed for researchers

LUNA aims to support researchers who need rigorous electrophysiology analysis without requiring every user to assemble and maintain a complete Python pipeline. The GUI exposes the settings that affect computation, while saved manifests and structured outputs support later review and reproduction.

The software is intended to remain useful for experienced programmers as well: the computational layer is modular, scriptable, and independent of the graphical interface.

## A tool, not a black box

LUNA does not replace methodological judgment. It makes analytical decisions easier to inspect.

The platform records input identity, parameters, valid epochs, effective duration, quality status, exclusions, failures, and output provenance. Connectivity estimates are retained at appropriate channel-pair and region levels, and directional measures preserve their sign conventions instead of being silently symmetrized.

## Project status

LUNA is under active development. The current repository provides a traceable workflow for multichannel, multiregion LFP analysis using preprocessed FIF epochs. It includes a PySide6 desktop GUI, command-line analysis components, configurable metadata, synthetic validation, automated tests, and reusable plotting and export modules.

The current implementation has been checked with a real T80 FIF example at the single-file descriptive level. Raw experimental data are not stored in this repository and are never overwritten by the software. Animal-level inference is intentionally withheld when animal identity, session, treatment time point, or behavioral linkage is incomplete.

Current methodological safeguards include:

- preservation of `events`, `selection`, `drop_log`, and epoch provenance;
- checks for NaN/Inf values, flat signals, abnormal amplitude, saturation, duplicate segments, and residual line noise;
- no concatenation of discontinuous epochs into a false continuous recording;
- retention of full channel-pair information for connectivity analysis;
- explicit reporting of rank, dimensionality, stability, and method failures;
- separation of file-level description from animal-level statistical inference.

## The idea behind the name

**LUNA** stands for **Local field potential Unified Network Analysis platform**.

The name reflects the platform's goal: bringing local field potential signals, spectral dynamics, and multiregion network analysis into one coherent environment.

> **LUNA — let the signals speak.**

## Project structure

```text
configs/                Editable analysis configuration (default: configs/luna.yaml)
assets/branding/        LUNA branding assets
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

- Windows 10/11 (the current version has been validated on Windows)
- Python 3.11; project constraint: `>=3.11,<3.13`
- `pip` and a project-local `.venv`

Create the environment and install LUNA from the repository root:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[all]"
```

If PowerShell blocks script activation, call the environment interpreter directly:

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[all]"
```

To reproduce the currently recorded dependency snapshot:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m pip install -e .
```

`requirements-lock.txt` is an auditable snapshot of the current Windows/Python 3.11 environment. For cross-platform installation, prefer the dependency ranges in `pyproject.toml`.

The default configuration is [`configs/luna.yaml`](configs/luna.yaml), which extends the analysis settings in [`configs/default.yaml`](configs/default.yaml).

Official environment references:

- [Python downloads](https://www.python.org/downloads/)
- [Python virtual environments](https://docs.python.org/3.11/library/venv.html)
- [Python Packaging Guide: install packages in a virtual environment](https://packaging.python.org/en/latest/guides/installing-using-pip-and-virtual-environments/)

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
.[dev]                pytest and Ruff
.[all]                All optional analysis, notebook, and development dependencies
```

## Analysis conventions and limitations

- Connectivity is estimated within the same animal, recording session, and treatment time point using multiple valid epochs. Data are not mixed across animals, days, or time points.
- Channels, epochs, and channel pairs are repeated measurements within an animal and must not be treated as independent animals.
- MIC retains signed raw values. Absolute magnitude may be used for clearly labelled visualization but does not establish causal direction.
- MIM retains its original unnormalized interaction value and is not forced into a 0–1 range.
- wPLI, dPLI, and debiased squared wPLI retain all valid channel pairs. dPLI uses 0.5 as the neutral reference and is not mirrored as a second estimate.
- Time-delay signs follow the declared seed-to-target convention and do not prove anatomical or causal direction.
- Quality flags do not silently delete data.
- Frequency bands, thresholds, rank settings, and delay ranges are editable starting points rather than universally validated physiological boundaries.

## Documentation

Detailed guides and method notes are maintained outside the main README:

- [GUI guide](docs/gui_guide.md)
- [Analysis plan and implementation notes](docs/analysis_plan.md)
- [Metadata definitions](metadata/README.md)

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
