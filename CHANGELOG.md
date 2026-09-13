# Changelog

All notable changes to LUNA are documented here.

## [0.2.1] — 2026-09-13 (prerelease)

### Changed

- Refined the GUI configuration and result-view layout, including method-specific PSD controls, independent scrolling for plots, compact result-table previews, and responsive channel/region controls.
- Added packaged LUNA resources, stable color/style helpers, identity handling, and expanded saved-run metadata needed for reproducible reloads.
- Extended connectivity result handling and plotting diagnostics while preserving the existing MIC, MIM, wPLI, dPLI, and time-delay result semantics.
- Clarified the README and development records for the verified Windows/Python environment, real FIF checks, and the limits of file-level analysis when animal identity is unresolved.

### Fixed

- Fixed connectivity spectrum display gaps caused by plotting-time line-noise masking being coupled to the optional background marker. Marker display and explicit plot exclusion are now independent, and the default display preserves finite returned values.
- Fixed GUI refresh, mapping, plotting, export, and quality-alignment regressions covered by the expanded test suite.

### Validation

- The full local test suite, Ruff checks, Python compilation, and dependency checks were run against the current workspace.
- The fixed read-only T80 FIF sample was reloaded and used for file-level validation; raw experimental data and generated results are not included in the release source tree.

### Known limitations

- The supplied sample does not resolve animal/session identity, so animal-level inference and treatment/behavior conclusions remain disabled.
- Native desktop mouse/DPI inspection is environment-dependent; offscreen Qt checks do not replace manual verification on every Windows display configuration.

## [0.2.0] — 2026-09-10 (prerelease)

### Added

- LUNA branding and the official Indigo/Lavender SVG logo.
- A desktop GUI workflow for importing FIF files, inspecting raw waveforms, and reviewing quality and effective duration.
- Editable channel-to-region mapping with JSON save/load support.
- Dynamic region and region-pair selection based on the active mapping, including custom region names.
- Top-level run, stop, save-result, and figure-export controls.
- Collapsible configuration panels and responsive checkbox layouts for bands and region pairs.
- GUI views and result handling for PSD, band power, specparam/FOOOF, MIC, MIM, wPLI, dPLI, and time-delay analysis already present in the project.

### Documentation

- Updated the README, startup defaults, project metadata, and user-facing application identity to LUNA.
- Added a LUNA configuration entry point at `configs/luna.yaml`, which inherits the existing scientific defaults for compatibility.

### Validation

- 31 automated tests pass.
- Ruff and Python compilation checks pass.
- The supplied T80 FIF sample was loaded and checked: 21 retained epochs, 16 channels, 1000 Hz, and 105 seconds of effective valid duration.
- Custom `CTX` / `STR_CUSTOM` mapping was applied through the GUI and analysis engine and saved/reloaded as JSON.

### Known limitations

- The supplied sample has unresolved animal/session identity, so animal-level inference is not run automatically.
- Native Windows desktop scaling at every system setting was not manually inspected in this environment; Qt offscreen rendering was checked at 1366×768, 1920×1080, minimum window size, and 150% Qt scale.
- Raw experimental FIF files, virtual environments, caches, and generated results are not included in the release source tree.
