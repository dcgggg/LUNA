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
comparisons/        legacy saved comparison snapshots (readable; no current GUI entry)
exports/            user exports
logs/               project-local operational records
subjects/           readable subject/session/state hierarchy folders
```

New imports copy the source into `data/raw/<fingerprint-prefix>/`, verify size and SHA-256, and store a project-relative path. The original source path is retained for provenance and is not modified or moved. Multiple data units may reference one project copy while keeping distinct epoch/time selections. Projects created with schema version 1 remain readable; their external references are preserved until the user explicitly chooses **Organize data**. Moving the whole project keeps project-relative sources and saved results resolvable.

Use **Structure template** to paste or generate multiple subjects, define reusable session keys, and create baseline, regular or irregular numerical state timepoints without editing JSON. **Save template** only stores the reusable definition. **Apply current structure** uses the current editor contents to create persistent metadata records and readable `subjects/<subject>/<session>/<state>/` folders. The preview reports planned additions and reuses. Applying a template is idempotent for existing matching records, preserves imported data and historical results, and makes empty states visible as `未导入数据` after reopening the project.

## Import

Select an existing state and use **Import to selected state** (or its right-click action) for the shortest path. The target is frozen as a stable `state_record_id`; changing the tree selection later cannot redirect the import. Project-level multi-file import exposes one row per file and requires every included row to map to an existing state:

```text
file → existing subject/session/state ID → optional epoch/time subset
```

Import never creates a subject, session or state. Unassigned rows remain visibly pending and cannot be committed until mapped; creating a state is a separate explicit action. The same display label may exist under different subjects/sessions because display text is never used as a foreign key. Content duplicates are reported; repeated captures with different content remain separate and are not automatically merged.

The preview supports tab/newline clipboard paste, filling the current cell down, and duplicating a row for another explicit state or epoch/time selection. Read-only source, duplicate, target and match columns cannot be overwritten by pasted metadata.

For a single source that contains more than one explicitly known state, duplicate its import-preview row and enter a distinct epoch-index list and/or within-epoch time range for each state. The source fingerprint may repeat, but the complete source-plus-selection identity may not. Epoch indices are validated against the retained FIF epochs; they are not converted into drug timepoints or continuous recording time.

The project tree displays readable names, counts and inspection/import status; UUIDs remain internal. It supports editing subject, session and state display metadata without changing stable IDs. **Relocate source** accepts only a file whose SHA-256 and size match the registered source. In Project Manager, **Previous data** and **Next data** open adjacent rows in the currently displayed data list; **Next unchecked** belongs to the single-record analysis workspace, not the Project Manager.

The state tree contains persistent data child nodes. A new import starts as `待检查`; import success never means human inspection is complete. The data-unit table shows module status as `calculation/save/validity/review`, keeping completed calculation, successful save, current compatibility and human review distinct.

### Explicit project save and recovery

Project structure edits, imports, metadata edits and future behavior metadata are separate from inspection autosave and analysis-result autosave. In the Project Manager, use **Save project** or `Ctrl+S` to formalize the current project draft. The manager shows a dirty marker; closing a dirty manager offers **Save**, **Discard** or **Cancel**. Before the first draft mutation LUNA keeps a project-local SQLite backup and a recovery marker under `logs/`; this permits recovery after an interrupted session and makes Discard recoverable without touching pre-existing raw data, result bundles or non-empty directories. The current implementation writes metadata while editing and uses the backup/journal as the save boundary; it is not a cross-process transactional workspace.

### Saved-result restore

Opening a persistent data unit first checks its indexed, saved `luna-result-bundle` records. Readable completed results are loaded directly into the existing analysis result viewer; PSD, Band Power, FOOOF, Connectivity, Time Delay and Quality use the same bundle contract when present. This path does not invoke an analysis function. The newest readable current result is selected by default, while **历史版本** can open another saved version read-only. **结果参数** shows the historical effective parameters, selection, inspection snapshot and quality metadata; **应用为待运行参数** copies those values into the pending configuration but does not modify the history. Failed or malformed newest candidates are logged and do not hide an older readable success. If the raw FIF is unavailable, saved results can still be browsed; raw-dependent inspection or recomputation remains unavailable.

### Behavior metadata

Project schema 6 provides lightweight behavior attachment, score and synchronization records plus explicit per-subject session display order. A score of `0` is a recorded zero; `NULL`/blank is missing. Attachments store provenance and optional state/data-unit links but do not process video. Synchronization records retain method, quality and timing fields; unverified epoch-level alignment remains unassigned rather than inferred.

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

## Review and external analysis

Use **Review** in the main analysis toolbar to mark a result `pending`, `approved` or `excluded`. A new calculation starts as pending; it does not inherit approval from an older result.

Use **Review** to inspect saved results for individual data units. LUNA does not provide an in-app A/B comparison, cross-subject pairing, group statistic, or cross-record scientific plotting page. This prevents a visual comparison page from silently choosing an independent unit, averaging incompatible results, or treating channels/epochs as animals.

Use **Filter / export list** to select records using same-field OR and across-field AND rules for group, subject, session, state, condition, structured time, inspection status and result availability. The view exports a machine-readable CSV or JSON list and does not pair, average, or calculate across records. The saved `ProjectResults` API and `scripts/read_project_results.py` remain the supported interfaces for independent downstream statistics and scientific figures. Historical `comparisons/` snapshots and comparison tables in older projects remain readable for compatibility, but they are not exposed as a current GUI workflow.

## Synthetic demonstration

Create a non-biological demonstration project:

```powershell
.\.venv\Scripts\python.exe scripts\create_project_demo.py --output C:\Temp\luna_project_demo
```

It contains five explicitly synthetic subjects, Day7, T80/T100 states, one missing T100, one duplicate T100, a mapping difference, a parameter-version difference and a failed batch-item example. It must not be used for scientific inference.

## Project Manager browsing scope

The left tree controls the right-side data-record list. Selecting the project root shows all data units in that project; selecting a subject, session, state, or data-unit leaf narrows the list by its stable internal ID and persisted parent relationship. Names such as `D3` and `T80` are labels only and are never used as join keys. Expanding/collapsing a branch does not change the current scope. Empty nodes remain selected and show “当前节点暂无数据”; they do not fall back to the project list.

The range line above the table shows the selected hierarchy path, records currently visible, and the number of records before search/filters. Search, Group, Condition and Inspection filters apply only within that base scope. **Clear filters** resets those filters but stays on the same tree node. **Filter/export list** opens with the current stable-ID scope captured in the dialog; its scope is shown above the table. If a different node is needed, close and reopen the dialog from that node.

The non-modal Filter/export window belongs to the Project Manager that opened it. Closing that individual window clears its owner reference; closing the Project Manager closes and destroys all of its Filter/export windows only after Save or Discard is accepted. Choosing Cancel keeps both manager and auxiliary windows open. Switching projects disposes the previous manager/batch/review workspaces before showing the new project's workspace. A running batch blocks project switching until it is stopped and finished, so its old-project task context is not silently hidden.

Three selections are intentionally separate:

- Left tree selection controls which records are shown.
- Selected table rows control one-record opening or multi-record metadata editing.
- The `Batch` checkbox controls batch inclusion. It starts unchecked and only checked rows in the currently displayed manager list are added. Changing tree scope or filtering does not silently select records.

In the Batch workspace, selections may persist across search/inspection filters. The count says “selected across filters”; **Selected for batch only** exposes hidden selected rows, and **Clear all selected** clears the complete batch selection. The **Checked data only** checkbox means inspection status is checked; it is not the batch checkbox.

Single-clicking a tree node changes the range only. Double-clicking a data leaf or one selected table row, the tree context-menu **Open in analysis**, or the global **Open in analysis** action opens that data unit. A hierarchy parent double-click does not open the current table row. The analysis window restores readable saved result bundles and frozen parameters if present; it does not start a calculation just because a data record was opened. A node with no saved result remains “暂无结果” until the user explicitly runs an analysis.

## Project Manager button reference

The names below are the current labels in the running Python UI. Project Manager text is currently English-first with some existing Chinese status messages; there is no Project Manager language-switch control in the current code. Some tooltips are bilingual and some are English-only; because there is no live language selector, the Project Manager cannot dynamically retranslate controls or hints. This is an existing product limitation, not a hidden button.

### Main-window navigation and Project menu

| Button/menu item | Location | Actual action and precondition | Scope, save, and files | Typical use |
|---|---|---|---|---|
| `Project` | Main analysis toolbar | Shows the active Project Manager; if none is open, tries the remembered project, then offers opening an existing project. | Does not create a project by itself; no data files changed. | Open the project tree. |
| `Batch` | Main analysis toolbar | Opens the batch workspace for the active project. If no project is active, opens the Project Manager flow first. | Uses batch selection/task settings; no source file changes until execution. | Run PSD on selected data units. |
| `Review` | Main analysis toolbar | Opens the active project's saved-result review workspace. | Changes review metadata only after marking selected result rows. | Mark a result approved. |
| `Project → New project…` | Main menu | Opens the name/parent-folder dialog; **Create** validates a non-existing target, creates the project and switches to it. | Creates a new project folder; never overwrites an existing folder. | Create a project under `LUNAProjects`. |
| `Project → Open project…` | Main menu | Selects an existing LUNA project folder and switches active project after existing workspaces close successfully. | Does not copy or move project data. | Open another project. |
| `Project → Show project workspace` | Main menu | Raises the active Project Manager; if absent, attempts the last remembered project, then opens the project chooser. | View/navigation only. | Return to the current project. |
| `Choose parent…` / `Create` / `Cancel` | New-project dialog | Choose the parent path, create the validated project, or dismiss the dialog. | `Create` creates the project directory and database; choosing/canceling does not. | Preview then create `Study A`. |
| `Help → About LUNA` | Main menu | Opens software name, description and version. | Read-only; no project or file changes. | Check which LUNA build is running. |
| `Run Analysis` | Main analysis toolbar | Runs the checked analysis modules on loaded data after required input/selection validation. | Creates analysis outputs; when attached to a project, completed bundles are indexed automatically. It does not change the raw FIF. | Run PSD after checking the selected channels and epochs. |
| `Stop` | Main analysis toolbar | Requests cancellation while a foreground task is running; disabled otherwise. | Completed work/results remain; it does not delete data or completed bundles. | Stop a long analysis after the current safe cancellation point. |
| `Save Result` / `Export Figure` | Main analysis toolbar | Both currently call the same `_export_figure` workflow. Metric-specific exporters may also save CSV tables; the general plot path saves a figure. | Export files only; neither button recalculates or means “save the automatic immutable analysis bundle”. | Export the displayed band-power view and its data table. |

### Project Manager top toolbar

| Button | Actual action and precondition | Scope, save, and files | Typical use |
|---|---|---|---|
| `Import data` | Opens a multi-select FIF file picker and then the import preview. Rows must be assigned to existing state nodes. | Copies verified source bytes into project raw storage and adds data-unit records; external originals are not moved. Changes remain in the project draft until Save project. | Import a recording to an existing T80 state. |
| `Save project` | Validates project-relative sources and hierarchy folders, then confirms the current project draft and removes its recovery backup/marker. `Ctrl+S` invokes the same action. | Project metadata/import links are currently written during editing; Save is the explicit draft boundary. It does not save or export analysis plots. | Confirm a new subject and state. |
| `Filter/export list` | Opens record filters pre-scoped to the currently selected tree node. | Filters/export only data records within that fixed scope; no files are changed unless the user chooses an export destination. | Export records under Mouse01. |
| `Open in analysis` | Opens one selected table row, or the data leaf selected in the tree. Disabled unless exactly one table row or a data leaf is selected. | Loads current source and restores saved results/parameters when available; does not calculate automatically. | Inspect one imported recording. |
| `Add to batch` | Queues only checked rows in the current Project data list. | Adds IDs to the main batch selection; it does not copy/delete source files. Dirty project drafts prompt for Save before queuing. | Check two displayed records, then queue them. |
| `Structure template` | Opens the structure editor for reusable definitions and project instantiation. | No change until Save template or Apply current structure is chosen. | Create multiple subjects and states. |
| `Edit mapping` | Opens channel/region mapping for the selected data unit. Requires one data record. | Saves mapping as project metadata/draft and invalidates dependent current results where appropriate; does not alter FIF. | Confirm channel-to-region associations after import. |
| `Organize data` | For checked records, copies external sources into the project and changes their registered paths after fingerprint checks. | Source originals remain untouched; project copies and metadata links are created/updated. | Make a project self-contained. |
| `Refresh` | Reloads the tree, scoped data list, batch jobs or review table while keeping stable selection/expansion when possible. | Metadata/result-index read only; no FIF array load or file move. | Refresh after an external metadata update. |
| `Check duplicate states` | Shows exact same-parent duplicate-state candidates and applies checked safe merges after confirmation. | Creates a SQLite backup, moves data-unit links to a canonical state and removes only redundant metadata/empty folder. It is not a general delete action and does not delete source/result files. | Merge exact duplicate state nodes within one session. |

### Other Project Manager dialogs and secondary controls

| Button/control | Position | Actual action and precondition | Scope, save behavior, file impact | Example |
|---|---|---|---|---|
| `Save` / `Discard` / `Cancel` | Close prompt when the project draft is dirty | Save validates the project tree/source links and confirms the draft; Discard restores the pre-edit SQLite backup and only cleans safe, newly-created empty paths; Cancel keeps the manager open. | Current project only. Metadata writes are visible in SQLite before Save; Discard is the recovery boundary. Existing raw sources, non-empty folders and result bundles are protected. | Cancel an accidental close, or Discard an unsaved state edit. |
| `Save` / `Cancel` | Channel / brain-region mapping dialog | Save commits the mapping for the selected data unit; Cancel drops dialog edits. | Updates project mapping metadata and may mark dependent results as needing recomputation; never edits the FIF bytes. | Correct a channel's region assignment. |
| `Apply` / `Cancel` | Duplicate-state review dialog | Apply merges only checked groups marked safe by exact same-parent semantic checks; Cancel makes no merge. If nothing is checked, it closes without change. | Project metadata only after a SQLite backup; moves data-unit links but does not delete raw files or saved bundles. | Merge a verified duplicate state within one session. |
| `Apply to all selected records` checkbox and `OK` / `Cancel` | Group/condition editor | Checkbox controls whether the entered value is applied to the selected rows; OK commits the edits to the project draft, Cancel abandons them. | Affects selected record ancestry metadata only; no source files are moved or deleted. | Apply one condition label to two selected rows. |
| `Save template` | Structure template dialog | Immediately stores a reusable template definition in the project database; does not create hierarchy nodes. | Template metadata only; no source or result files. This save is distinct from applying a structure and from the project-structure draft's `Save project`. | Save a “daily recordings” template for later reuse. |
| `Save inspection` | Main single-data analysis workspace, not Project Manager | Saves the current data unit's inspection/mapping/selection/review snapshot. The open record is required. | Immediately records an inspection revision; does not edit raw FIF or replace analysis-result bundle saving. | Save an epoch exclusion before running analysis. |
| Tree expand/collapse arrow | Left project tree | Expands or collapses visible children only; it does not change the current range, open a data unit or check batch boxes. | No save or file effect. | Expand a subject to see sessions without changing the list range. |
| `Ctrl+S` | Project Manager keyboard shortcut | Invokes `Save project`, the same as the toolbar action. | Current project draft only. | Confirm structural edits from the keyboard. |

### Project data, tree, filters, and row selection

| Button/control | Actual action and precondition | Scope, save, and files | Typical use |
|---|---|---|---|
| `Add subject` | Prompts for subject code and optional group; project root is the parent. | Creates a subject row and directory in the project draft. | Add Mouse03. |
| `Add session` | Creates a session under the selected subject; enabled only on a subject node. | Creates metadata and a project folder in the draft. | Add Day14 under Mouse03. |
| `Add state` | Creates a state under the selected session; enabled only on a session node. | Creates metadata and a project folder in the draft; state may remain empty. | Add T80 under Day14. |
| `Edit selected` | Edits the selected subject, session, or state display metadata; stable IDs remain unchanged. | Writes project metadata/draft; directory behavior follows current store rules. | Rename a visible session key. |
| `Edit selected metadata` | Edits group for represented subject(s) and condition for represented state(s). Uses selected table rows; if none, it can use the selected data leaf. | Writes project metadata/draft; does not change the source recording. | Set group/condition on two visible rows. |
| `Apply template` | Opens the same structure template application flow. It applies the current editor contents, not merely the saved definition. | Creates/reuses subject/session/state records and directories; imported files/results are retained. Save the project afterward to formalize the draft. | Apply a template to the open project. |
| `Add to batch` (data row) | Adds only rows with a checked `Batch` box in the visible list. | Does not automatically check all records or affect disk files. | Check one row and add it. |
| `Filter/export list` (data row) | Opens the scoped filter/export dialog for the currently selected tree node. | Same scope and file behavior as the toolbar action. | Filter a state by inspection status. |
| `Relocate source` | Opens a file picker for one selected row/data leaf and accepts only matching SHA-256 and size. | Updates the source reference; it neither copies nor moves nor deletes the selected file. | Point a missing registered source to the same file at its new location. |
| `Previous data` / `Next data` | Opens the adjacent row in the current displayed list; enabled when the list is non-empty. | Opens one record through the existing analysis workspace; does not change batch checks. | Step through the current state’s records. |
| `Clear filters` | Clears search, Group, Condition and Inspection filters without changing tree selection. | View only. | Return to all records under the selected session. |
| `Clear visible batch checks` | Unchecks the manager table's visible `Batch` boxes. | Current visible list only; no records or files are removed. | Reset batch inclusion before selecting a smaller set. |
| `Batch` checkbox | Toggles inclusion for that row in batch queue selection. It is intentionally not a row-selection control. | Current visible rows only in Project data. | Mark one record for batch. |
| Table row selection / double-click | Selecting rows chooses records for details/metadata actions. Double-click opens one selected data record. | Selection alone is not a batch check. Double-click opens/restores but does not calculate. | Select two rows for metadata editing, or double-click one to inspect. |
| Tree single-click / disclosure arrow | Single-click changes stable-ID scope; expand/collapse changes visibility only. | Never checks rows, opens data or runs analysis. | Select a subject, then expand its sessions. |
| Tree right-click: `Import data into this state` | Available on a state node; opens the importer with that exact `state_record_id` fixed as target. | FIF is copied to the project on successful import; source is unchanged. | Import a file directly to the selected state. |
| Tree right-click: `Open in analysis` | Available on a data-unit leaf only. | Same as toolbar Open in analysis; parent-node double-click does nothing. | Open the leaf's saved results. |
| Table right-click: `Edit selected group/condition` | Selects the row under the pointer if it is not already selected, then opens metadata editing. | Same project-draft semantics as Edit selected metadata. | Right-click one row to edit its labels. |

### Import preview and structure templates

| Button/control | Actual action and precondition | Scope, save, and files | Typical use |
|---|---|---|---|
| `Include` checkbox | Includes/excludes one import-preview row from validation and import. | Excluded rows are not imported. | Leave a duplicate out of this import. |
| `Existing target state` dropdown | Selects an existing state by stable ID; target labels are only presentation. | The selected ID is saved with the data-unit link. Does not create a state. | Assign the row to Mouse01/Day7/T80. |
| `Duplicate selected row` | Duplicates the selected source row for a second explicit target or epoch/time selection. | No file copy until import is accepted; validation prevents duplicate source-plus-selection identities. | Assign distinct epoch subsets of one source to two states. |
| `Fill current cell down` | Copies the current editable epoch/time cell to following rows (only its supported selection columns). | Edits preview metadata only. | Reuse one epoch list. |
| `Fill target state down` | Copies the current row's target state to subsequent preview rows. | Edits target assignments only. | Assign a set of files to the same state. |
| `Cancel` / `OK` | Cancel abandons preview; OK validates included rows, sources, selections and targets before import continues. | OK can lead to project file copies and draft metadata; it is not a save-analysis action. | Validate selected FIF files and import them. |
| `Saved template` dropdown | Loads a persisted reusable template into the editor. | Does not apply it to project structure. | Reuse “daily LID” structure. |
| `Generate subject list` | Fills the Subjects editor from prefix/start/count/zero-padding. | Editor only until Save template or Apply current structure. | Generate Mouse01–Mouse08. |
| `Generate timepoints` | Fills the States editor using the entered start/end/step/unit. | Editor only until applied. | Generate T20, T40 … T180. |
| `Save template` | Immediately saves the named reusable structure definition in the project database. | Creates no subject/session/state folders and does not require `Save project`; it is not an application of the template. | Save the current editor as “LID study”. |
| `Apply current structure` | Applies current visible editor values; preview reports additions/reuses and the store creates persistent records/folders. | Writes project structure draft; it does not import FIF or create analysis outputs. | Add missing states from a saved template. |
| `Cancel` (template dialog) | Closes without applying unsaved editor changes. | No structure changes from this dialog. | Exit without applying. |

### Filter/export, Batch, and Review windows

| Button/control | Actual action and precondition | Scope, save, and files | Typical use |
|---|---|---|---|
| `Refresh list` | Rereads metadata/results under the dialog's captured scope and current filters. | Read-only. | Refresh after saving analysis results. |
| `Clear filters` | Resets all dialog filters; keeps the captured scope. | Read-only. | Show all records in the selected session again. |
| `Export CSV` / `Export JSON` | Writes the currently filtered data-record list to the selected export path. | Creates only the requested export file; JSON records the project, scope and filters. Not an analysis result bundle. | Export the Mouse01 T80 list. |
| Batch search | Narrows the batch candidate list by subject/session/condition/state/file text. | Does not change checks. | Find “Mouse01”. |
| `Checked data only` | Filters by inspection status `checked` (selected rows are kept visible). | This is an inspection filter, not a batch-selection checkbox. | Review only inspected data. |
| `Selected for batch only` | Shows the persistent batch selection, including selected units hidden by other filters. | View only; selection remains cross-filter until unchecked or cleared. | Inspect the complete batch input set. |
| `Select filtered` | Checks all currently visible batch rows and retains earlier checks hidden by filters. | Batch task selection only. | Select all results of the current search. |
| `Clear all selected` | Clears the entire batch selection, including hidden rows. | Does not delete project data/files. | Start a new batch selection. |
| Module checkboxes / Run mode | Select analysis modules and choose reuse of missing/outdated results or explicit recalculation. | Affects the next batch only; calculation parameters are frozen in that job. | Run PSD/Band Power on selected records. |
| `View effective parameters` | Inspect/edit the batch task configuration used for the next job. | Configuration only until a job is created; not project data metadata. | Check frequency settings before batch start. |
| `Edit parameters in analysis panel` | Raises the main analysis window to edit its current per-module parameters. | Does not copy values until the separate Use current single-file parameters action. | Adjust PSD parameters. |
| `Use current single-file parameters` | Copies current main-window calculation parameters into batch configuration. | Does not copy per-record channel/epoch inspection decisions. | Reuse current PSD settings for batch. |
| `Save parameter scheme` / `Load parameter scheme` | Saves or loads a named reusable batch parameter scheme. | Config only; does not run or change a data unit. | Reuse a validated module configuration. |
| `Run selected data units` | Performs preflight and starts the selected modules over checked batch units. | Writes new/reused analysis result bundles and project result indexes; sources are read, not modified. | Start the prepared batch. |
| `Stop` | Requests cancellation of the running batch; already completed records remain. | Does not delete completed results. Enabled while a job is running. | Stop after the current unit. |
| `Resume latest interrupted` | Requeues unfinished, failed or cancelled items in the latest interrupted job. | Completed/reused items remain complete. | Continue a cancelled batch. |
| `Mark approved` / `Mark excluded` / `Reset to pending` | Applies a review status and optional note to selected result rows only. | Updates result-review metadata; does not alter result files or rerun analysis. | Exclude one stale result from interpretation. |

### Save and delete semantics, keyboard and icon buttons

`Save project` formalizes project structure/import/metadata drafts; it is separate from automatic analysis-result saving. The main-window `Save Result` and `Export Figure` currently have the same callback (`_export_figure`), so they are duplicate entry points rather than separate save semantics. The selected metric's exporter determines whether a CSV accompanies the figure. Neither button reruns analysis or replaces the automatically saved immutable result bundle. Opening an already analyzed data unit restores its saved result and effective parameters when present, without starting a calculation.

There is currently no generic **Remove project record**, **Delete data unit**, or **Delete source file** button. **Check duplicate states** only performs the exact safe merge described above. **Organize data** copies into project storage and keeps the original; **Relocate source** only changes the registered source path after a content fingerprint match.

The Project Manager toolbar actions are text actions rather than icon-only buttons. The tree disclosure arrows and the table's `Batch` checkboxes are the only non-text selection affordances in its main data view. The explicit shortcut is `Ctrl+S` for **Save project**. The import preview table supports standard `Ctrl+C`/`Ctrl+V` clipboard copying/pasting of editable cells; read-only source/duplicate/target columns are protected. Dialog `Cancel`, `OK`, `Save`, `Apply`, and `Create` buttons have the dialog-local meanings described above; they do not stand in for one another.

### Confirmed interaction issues and limits

- `Save Result` and `Export Figure` are two buttons wired to the same exporter. Their tooltips now state this explicitly; function consolidation/removal is left for a separate product decision.
- This Project Manager currently has no live Chinese/English language switch. Labels are a mixture of English and Chinese status text, and some tooltips are English-only. The entire Project Manager cannot yet follow a language toggle that does not exist.
- The non-modal filter/export window captures the tree scope at the time it opens. Closing the Project Manager now closes every such child window, preventing a list from the previous project from remaining visible after switching projects.
- There is no generic delete-record/delete-source action. Do not treat `Check duplicate states`, `Relocate source`, or `Organize data` as deletion controls.
