# Changelog

All notable changes to LUNA are documented here.

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
