# Changelog

## [0.3.0.dev1] — 2026-09-24 (prerelease)

- Removed the in-app cross-record A/B comparison entry point. The project manager now provides hierarchy, import, metadata, filter and CSV/JSON list export; cross-subject statistics and scientific comparison figures use the saved result contract externally.
- Added explicit per-subject session ordering and project schema 6 migration so labels such as Day3 and Day10 retain the user's order.
- Added stable-ID project scope filtering, auxiliary-window lifecycle cleanup, recoverable project-draft regression coverage and architecture/handoff documentation.
- Scientific algorithms and default estimator parameters are unchanged.

## [0.3.0.dev0] — 2026-09-23 (prerelease)

- Added a local SQLite project model with stable project, subject, session, experimental-state and data-unit identities.
- Added editable import preview, content-fingerprint duplicate detection, channel-mapping confirmation and source relocation checks.
- Added project batch orchestration over the existing single-record computation core, frozen parameter snapshots, per-item status, cancellation/resume support and exact cache reuse.
- Added versioned per-module result manifests, GUI-independent result reading/long-table export, manual review state and saved-result comparison previews.
- Added a five-subject synthetic project demonstration with missing, duplicate, incompatible and failed-task cases.
- Simplified project creation so a readable project name becomes the actual folder name, and new imports are verified copies addressed by project-relative paths.
- Added reusable subject/session/state structure templates, inherited-context multi-file import, persistent per-data inspection decisions, and project portability after moving the root folder.
- Fixed the template Apply button binding and made template application persist matching subject/session/state records together with readable project folders; repeated application is idempotent and empty states remain visible in the project tree.
- Moved batch execution, review and A/B comparison entry points back to the main analysis GUI while keeping the project manager focused on hierarchy and import management.
- Scientific algorithms and default estimator parameters are unchanged.

All notable changes to LUNA are documented here.

## [0.2.2] — 2026-09-13 (prerelease)

### Changed

- Integrated the latest LUNA README introduction and official seven-star Indigo/Lavender branding assets from the canonical `dcgggg/LUNA` repository.
- Added the high-resolution `luna-logo-600dpi.tiff` release asset alongside the SVG web resources.
- Published the complete current local implementation, tests, development records, packaged resources, and GUI/connectivity refinements under the canonical repository location.

### Validation

- Re-ran the local test suite, Ruff, Python compilation, dependency checks, package version import, and wheel build for version `0.2.2`.
- The release source excludes raw FIF files, virtual environments, caches, generated results, and local screenshots.

### Known limitations

- The supplied sample does not resolve animal/session identity, so animal-level inference and treatment/behavior conclusions remain disabled.
- Native desktop mouse/DPI inspection is environment-dependent; offscreen Qt checks do not replace manual verification on every Windows display configuration.

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
