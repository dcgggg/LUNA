# LUNA project workflow

## Hierarchy

LUNA project management uses:

```text
Project → Subject → Session → Experimental state record → Data unit
```

A session is one experimental recording session, not one epoch. `session_key` (for example `Day7`) is the cross-subject matching label. Experimental conditions, numerical timepoints, units and reference events live in state records. A data unit points to one source plus an explicit channel/epoch/time selection. Repeated captures at the same state remain separate data units.

## Create or open a project

Start `scripts/run_gui.py`, then choose **Project → New project…** or **Project → Open project…**. New-project creation asks for a project name and parent folder and previews the exact target path. Existing folders are never overwritten silently. The last opened project path is remembered locally. The project folder contains:

```text
project.sqlite3     authoritative identities, relationships and task/result index
data/raw/           verified read-only-semantic copies of imported recordings
data/derived/       project-owned derived data, separate from raw copies
results/            immutable analysis bundles
configs/            optional project templates
comparisons/        saved comparison snapshots
exports/            user exports
logs/               project-local operational records
subjects/           readable subject/session/state hierarchy folders
```

New imports copy the source into `data/raw/<fingerprint-prefix>/`, verify size and SHA-256, and store a project-relative path. The original source path is retained for provenance and is not modified or moved. Multiple data units may reference one project copy while keeping distinct epoch/time selections. Projects created with schema version 1 remain readable; their external references are preserved until the user explicitly chooses **Organize data into project**. Moving the whole project keeps project-relative sources and saved results resolvable.

Use **Structure template** to paste or generate multiple subjects, define reusable session keys, and create baseline, regular or irregular numerical state timepoints without editing JSON. **Save template** only stores the reusable definition. **Apply current structure** uses the current editor contents to create persistent metadata records and readable `subjects/<subject>/<session>/<state>/` folders. The preview reports planned additions and reuses. Applying a template is idempotent for existing matching records, preserves imported data and historical results, and makes empty states visible as `未导入数据` after reopening the project.

## Import

Select an existing state and use **Import to selected state** (or its right-click action) for the shortest path. The target is frozen as a stable `state_record_id`; changing the tree selection later cannot redirect the import. Project-level multi-file import exposes one row per file and requires every included row to map to an existing state:

```text
file → existing subject/session/state ID → optional epoch/time subset
```

Import never creates a subject, session or state. Unassigned rows remain visibly pending and cannot be committed until mapped; creating a state is a separate explicit action. The same display label may exist under different subjects/sessions because display text is never used as a foreign key. Content duplicates are reported; repeated captures with different content remain separate and are not automatically merged.

The preview supports tab/newline clipboard paste, filling the current cell down, and duplicating a row for another explicit state or epoch/time selection. Read-only source, duplicate, target and match columns cannot be overwritten by pasted metadata.

For a single source that contains more than one explicitly known state, duplicate its import-preview row and enter a distinct epoch-index list and/or within-epoch time range for each state. The source fingerprint may repeat, but the complete source-plus-selection identity may not. Epoch indices are validated against the retained FIF epochs; they are not converted into drug timepoints or continuous recording time.

The project tree displays readable names, counts and inspection/import status; UUIDs remain internal. It supports editing subject, session and state display metadata without changing stable IDs. **Relocate source** accepts only a file whose SHA-256 and size match the registered source. **Previous**, **Next** and **Next unchecked** navigate adjacent data units in the existing single-record workspace.

The state tree contains persistent data child nodes. A new import starts as `待检查`; import success never means human inspection is complete. The data-unit table shows module status as `calculation/save/validity/review`, keeping completed calculation, successful save, current compatibility and human review distinct.

### Explicit project save and recovery

Project structure edits, imports, metadata edits and future behavior metadata are separate from inspection autosave and analysis-result autosave. In the Project Manager, use **Save project** or `Ctrl+S` to formalize the current project draft. The manager shows a dirty marker; closing a dirty manager offers **Save**, **Discard** or **Cancel**. Before the first draft mutation LUNA keeps a project-local SQLite backup and a recovery marker under `logs/`; this permits recovery after an interrupted session and makes Discard recoverable without touching pre-existing raw data, result bundles or non-empty directories. The current implementation writes metadata while editing and uses the backup/journal as the save boundary; it is not a cross-process transactional workspace.

### Saved-result restore

Opening a persistent data unit first checks its indexed, saved `luna-result-bundle` records. Readable completed results are loaded directly into the existing analysis result viewer; PSD, Band Power, FOOOF, Connectivity, Time Delay and Quality use the same bundle contract when present. This path does not invoke an analysis function. The newest readable current result is selected by default, while **历史版本** can open another saved version read-only. **结果参数** shows the historical effective parameters, selection, inspection snapshot and quality metadata; **应用为待运行参数** copies those values into the pending configuration but does not modify the history. Failed or malformed newest candidates are logged and do not hide an older readable success. If the raw FIF is unavailable, saved results can still be browsed; raw-dependent inspection or recomputation remains unavailable.

### Behavior metadata

Project schema 5 provides lightweight behavior attachment, score and synchronization records. A score of `0` is a recorded zero; `NULL`/blank is missing. Attachments store provenance and optional state/data-unit links but do not process video. Synchronization records retain method, quality and timing fields; unverified epoch-level alignment remains unassigned rather than inferred.

Channel mappings imported from the current file/registry are marked `needs_mapping_confirmation`. Region-level connectivity and delay analysis are blocked until the mapping is opened and saved in **Edit mapping**.

## Single-data analysis

Double-click a data child/row or choose **Open in analysis**. The existing single-record workspace is reused and displays project, subject, session, state and source context. Inspection edits are debounced and saved as versioned project-local records; switching data or closing flushes pending edits. The saved snapshot includes channel inclusion/exclusion, manual bad-channel flags, mapping, retained/original epoch indices, reversible exclusion reasons, time selection, status and notes. It never modifies the source FIF. A successful run receives stable identities and the inspection revision/fingerprint frozen at task start, writes the same result contract as batch mode, and is indexed back into the project.

Exact same-parent duplicate-looking states can be reviewed with **Check duplicate states**. Only exact semantic duplicates are automatically eligible; the database is backed up first, data-unit links are moved by ID, and ambiguous same-label states remain unchanged.

## Batch analysis

Check data units in **Project data**, choose **Add to batch**, then use **Batch** in the main analysis window. Filter/search and select actual data units, choose modules, copy the current single-file calculation controls or load a saved parameter scheme, inspect the frozen effective task preview, and select either:

- **Calculate missing/outdated**: reuse only results whose data and effective-parameter fingerprints match exactly.
- **Recalculate selected**: create new result versions; previous bundles remain on disk and in history.

Batch calculation settings come from the main single-file controls or a named batch scheme. Data-specific inspection decisions are never copied from the currently viewed file: each unit contributes its own saved channel, epoch, time and mapping selection. Each task stores the fully merged effective snapshot before the worker starts; later GUI edits do not change a running task.

The preflight reports selected units/modules, existing results, missing sources and unconfirmed mappings. Execution is sequential across data units to avoid multiplying file-level workers by algorithm-internal parallelism. Failures are isolated per data unit, cancellation preserves completed bundles, and a repeated job can resume without rerunning completed items.

**Resume latest interrupted** requeues only unfinished, failed or cancelled items. Already completed or exactly reused items stay complete.

## Review and comparison

Use **Review** in the main analysis toolbar to mark a result `pending`, `approved` or `excluded`. A new calculation starts as pending; it does not inherit approval from an older result.

Use **Compare** in the main analysis toolbar. The A/B comparison reads the active project's indexed, saved results and filters them by subject/group, session key or a specific stable session, condition, exact numerical timepoint or range, module, metric/band and channel/region target. Its preview reports one row per subject:

- included;
- missing/not eligible;
- duplicate, requiring an explicit `analysis_id` choice.

The preview keeps A and B session, condition/timepoint, source filename, effective epoch/duration summary, result identity, status, compatibility and exclusion reason visible before plotting. The exported preview CSV contains the same inspectable membership fields.

Compatibility checks include module/method, signal unit, sampling rate, effective parameters and channel mapping. Incompatible results can be inspected but are not silently pooled. Subject-level representatives are calculated before group summaries; epochs never become the group sample size.

The comparison page can additionally filter a loaded result table by channel, region or region pair. For scalar summaries, **Pair with second timepoint** matches records by stable `subject_id`, never by row position. Missing or duplicate records on either side are not converted to pairs. Saved comparison snapshots retain exact `analysis_id` membership and can be reopened without silently switching to newer analyses.

Connectivity comparisons can switch between one selected region-pair spectrum and one region matrix per included subject. These views read saved `spectrum`/`band_summary` tables only. Matrices use one shared normalization for the comparison and retain method-specific semantics (including a 0.5-centered dPLI scale); each displayed matrix owns its colorbar.

## Synthetic demonstration

Create a non-biological demonstration project:

```powershell
.\.venv\Scripts\python.exe scripts\create_project_demo.py --output C:\Temp\luna_project_demo
```

It contains five explicitly synthetic subjects, Day7, T80/T100 states, one missing T100, one duplicate T100, a mapping difference, a parameter-version difference and a failed batch-item example. It must not be used for scientific inference.
