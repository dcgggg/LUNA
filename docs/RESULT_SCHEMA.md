# LUNA result contract

Current schema: `luna-result-bundle` version `1.0`.

Each analysis module is saved as an independent directory. A bundle is not considered successfully saved until its numerical files exist, `manifest.json` passes validation, and the project SQLite transaction indexes it.

## Files

- `manifest.json`: stable identities, actual parameters, provenance, dimensions, units, quality and dependency versions.
- Named CSV tables: long or tidy tables used for inspection and statistical export.
- Named NPZ arrays where the module has dense numerical arrays. Keys are descriptive; `arr_0` style unnamed values are forbidden.
- Figures remain derived outputs. They are never the only saved result.

The SQLite project index is authoritative for relationships and queries. The bundle manifest is authoritative for the immutable analysis snapshot. Display names are not keys.

Schema 2 project imports normally store `source.path` as a project-relative path and retain `source.original_path` plus SHA-256/size provenance. Legacy external paths remain valid until the user explicitly organizes them into the project. Moving the project root does not rewrite immutable result manifests; relative paths are resolved against the newly opened project root.

## Required identities

Every new project result has:

```text
project_id
subject_id
session_id
state_record_id
data_unit_id
analysis_id
```

Manifests also expose the clearer aliases `state_id`, `dataset_id`, and `analysis_run_id`; each must exactly equal its canonical ID above.

Renaming or reordering a project item therefore does not change its result links.

`selection` and `inspection_snapshot` freeze the inspection status, revision, fingerprint, source-structure fingerprint, effective channel/mapping, retained/original epoch identities and within-epoch time selection used by that run. Later inspection edits set `result_validity=needs_recompute` without changing the historical `calculation_status=completed` or `save_status=saved`. The old bundle remains readable; automatic reuse and current-result queries require `result_validity=current`. Cross-record pairing, group statistics and scientific comparison figures are intentionally performed outside LUNA from these saved bundles.

## Required provenance

The manifest records:

- `schema_name`, `schema_version`, LUNA version and dependency versions;
- module and method name;
- source path, SHA-256 and size where available;
- epoch, channel and within-epoch time selection;
- channel/region mapping snapshot, sampling rate and signal unit;
- effective parameters and their canonical SHA-256 fingerprint;
- data/preprocessing-selection fingerprint;
- calculation/save status, quality summary, warnings and upstream analysis IDs;
- every NPZ field's name, shape, dtype, axes, unit and numerical space.

NaN/status values remain distinct from a real zero. Complex arrays, when introduced by a method, must retain their complex dtype and declared meaning.

## Module dimensions

- PSD keeps epoch × channel × frequency values plus channel/region summaries.
- Band power keeps epoch, channel and band values with band bounds and relative-power denominator metadata.
- Spectral parameterization uses separate model, peaks and curves tables so zero, one or many peaks remain representable.
- Cross-epoch connectivity keeps connection/region pair, optional component and frequency dimensions. It does not invent a per-epoch connectivity axis.
- Time-delay results retain channel/region pairs, delay/frequency dimensions and the declared seed-target sign convention.

## Compatibility

Legacy GUI run schema versions 1 and 2 remain readable through `load_saved_run()`. A legacy run can be attached to a registered project data unit with `ProjectBatchRunner.index_completed_run(...)`; identities are taken from the project data unit, never inferred from a filename. There is no automatic assignment of an unregistered legacy result to an animal/session.

Schema `1.x` may add optional fields. Renaming a field or changing its meaning requires a new schema version and an explicit migration reader. The current loader rejects unsupported versions rather than guessing.

## Minimal Python extraction

```python
from lfp_analysis.results_api import ProjectResults

results = ProjectResults(r"C:\path\to\luna_project")
index = results.list(
    session_key="Day7",
    condition_label="L-DOPA",
    timepoint_value=100.0,
    module_name="Band Power",
)

analysis_id = index.iloc[0]["analysis_id"]
table = results.table(analysis_id, "band_power_summary")
long_table = results.to_long_table(
    index["analysis_id"].tolist(),
    "band_power_summary",
    ["absolute_power", "relative_power"],
)
```

The long export adds stable project/subject/session/state/data/analysis identities, `metric`, `value`, `value_unit`, `summary_level`, review state and a quality flag while preserving applicable channel, region, pair, band and frequency columns from the source table.

This reader does not start Qt, does not run an analysis, and can load saved tables after the source FIF has moved or become unavailable.
