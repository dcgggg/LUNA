"""Local project metadata store for LUNA.

The SQLite database is the authoritative source for project identities and
relationships.  Display names never act as foreign keys.  Numerical analysis
outputs remain in versioned result bundles on disk and are indexed here.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import stat
import uuid
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_SCHEMA_VERSION = 5
PROJECT_DATABASE = "project.sqlite3"
WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL", *(f"COM{index}" for index in range(1, 10)), *(f"LPT{index}" for index in range(1, 10)),
}


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def file_fingerprint(path: str | Path, chunk_size: int = 1024 * 1024) -> dict[str, Any]:
    source = Path(path).expanduser().resolve()
    digest = hashlib.sha256()
    with source.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    stat = source.stat()
    return {"sha256": digest.hexdigest(), "size_bytes": int(stat.st_size)}


def _json(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, sort_keys=True, default=_json_default)


def _json_default(value: Any) -> Any:
    if hasattr(value, "item"):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Not JSON serializable: {type(value).__name__}")


def _loads(value: str | None, default: Any) -> Any:
    if value in (None, ""):
        return default
    return json.loads(value)


def _fingerprint_json(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=_json_default).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class ProjectPaths:
    root: Path
    database: Path
    results: Path
    configs: Path
    snapshots: Path
    raw_data: Path
    derived_data: Path
    exports: Path
    logs: Path
    templates: Path
    subjects: Path


def normalize_project_folder_name(name: str) -> str:
    """Return a visible Windows-safe folder name derived from ``name``."""
    candidate = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name.strip()).rstrip(" .")
    candidate = re.sub(r"\s+", "_", candidate)
    if not candidate:
        raise ValueError("Project name must contain at least one valid character")
    if candidate.upper() in WINDOWS_RESERVED_NAMES:
        candidate = f"{candidate}_project"
    return candidate


def normalize_structure_folder_name(name: str, fallback: str) -> str:
    """Return a readable Windows-safe hierarchy folder name."""
    candidate = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name.strip()).rstrip(" .")
    if not candidate:
        candidate = fallback
    if candidate.upper() in WINDOWS_RESERVED_NAMES:
        candidate = f"{candidate}_node"
    return candidate


class ProjectStore:
    """Create, query, and update one local LUNA project."""

    def __init__(self, root: str | Path) -> None:
        project_root = Path(root).expanduser().resolve()
        self.paths = ProjectPaths(
            root=project_root,
            database=project_root / PROJECT_DATABASE,
            results=project_root / "results",
            configs=project_root / "configs",
            snapshots=project_root / "comparisons",
            raw_data=project_root / "data" / "raw",
            derived_data=project_root / "data" / "derived",
            exports=project_root / "exports",
            logs=project_root / "logs",
            templates=project_root / "templates",
            subjects=project_root / "subjects",
        )
        if not self.paths.database.is_file():
            raise FileNotFoundError(f"LUNA project database not found: {self.paths.database}")
        self._ensure_schema()
        self._ensure_directories()
        self.ensure_structure_directories()
        with self.transaction() as connection:
            connection.execute("UPDATE projects SET root_path=?,schema_version=?", (str(project_root), PROJECT_SCHEMA_VERSION))

    @classmethod
    def create_named(cls, parent: str | Path, name: str, description: str = "") -> ProjectStore:
        """Create ``parent / normalized(name)`` without overwriting a folder."""
        parent_path = Path(parent).expanduser().resolve()
        folder_name = normalize_project_folder_name(name)
        target = parent_path / folder_name
        if target.exists():
            raise FileExistsError(f"Project folder already exists: {target}")
        return cls.create(target, name, description)

    @classmethod
    def create(cls, root: str | Path, name: str, description: str = "") -> ProjectStore:
        project_root = Path(root).expanduser().resolve()
        project_root.mkdir(parents=True, exist_ok=True)
        database = project_root / PROJECT_DATABASE
        if database.exists():
            raise FileExistsError(f"Project already exists: {database}")
        store = object.__new__(cls)
        store.paths = ProjectPaths(
            root=project_root,
            database=database,
            results=project_root / "results",
            configs=project_root / "configs",
            snapshots=project_root / "comparisons",
            raw_data=project_root / "data" / "raw",
            derived_data=project_root / "data" / "derived",
            exports=project_root / "exports",
            logs=project_root / "logs",
            templates=project_root / "templates",
            subjects=project_root / "subjects",
        )
        store._ensure_directories()
        store._initialize_schema()
        project_id = new_id("project")
        with store.transaction() as connection:
            connection.execute(
                "INSERT INTO projects(project_id,name,description,created_at_utc,root_path,schema_version,analysis_template_json) VALUES(?,?,?,?,?,?,?)",
                (project_id, name.strip() or "Untitled project", description.strip(), utc_now(), str(project_root), PROJECT_SCHEMA_VERSION, "{}"),
            )
        return store

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.paths.database, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def backup_database(self, target: str | Path) -> Path:
        """Create a consistent SQLite snapshot for a Project Manager draft.

        The snapshot is metadata-only and never includes raw recordings or
        result bundles.  SQLite's backup API is used so a live WAL database is
        captured consistently.
        """
        destination = Path(target).expanduser().resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            destination.unlink()
        source_connection = sqlite3.connect(self.paths.database)
        target_connection = sqlite3.connect(destination)
        try:
            source_connection.backup(target_connection)
            target_connection.commit()
        finally:
            target_connection.close()
            source_connection.close()
        return destination

    def restore_database_backup(self, source: str | Path) -> None:
        """Restore a Project Manager draft snapshot without touching data files."""
        snapshot = Path(source).expanduser().resolve()
        if not snapshot.is_file():
            raise FileNotFoundError(f"Project draft backup not found: {snapshot}")
        source_connection = sqlite3.connect(snapshot)
        target_connection = sqlite3.connect(self.paths.database)
        try:
            source_connection.backup(target_connection)
            target_connection.commit()
        finally:
            target_connection.close()
            source_connection.close()
        self._ensure_schema()
        self._ensure_directories()
        self.ensure_structure_directories()

    def _initialize_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE schema_info(version INTEGER NOT NULL);
                INSERT INTO schema_info(version) VALUES(5);
                CREATE TABLE projects(
                    project_id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
                    created_at_utc TEXT NOT NULL, root_path TEXT NOT NULL, schema_version INTEGER NOT NULL,
                    analysis_template_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE subjects(
                    subject_id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
                    subject_code TEXT NOT NULL, group_label TEXT, attributes_json TEXT NOT NULL DEFAULT '{}',
                    created_at_utc TEXT NOT NULL, relative_path TEXT, UNIQUE(project_id,subject_code)
                );
                CREATE TABLE sessions(
                    session_id TEXT PRIMARY KEY, subject_id TEXT NOT NULL REFERENCES subjects(subject_id) ON DELETE CASCADE,
                    session_key TEXT NOT NULL, experiment_name TEXT, session_date TEXT, notes TEXT,
                    created_at_utc TEXT NOT NULL, relative_path TEXT
                );
                CREATE INDEX idx_sessions_subject_key ON sessions(subject_id,session_key);
                CREATE TABLE state_records(
                    state_record_id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
                    condition_label TEXT, timepoint_value REAL, timepoint_unit TEXT, reference_event TEXT,
                    display_name TEXT NOT NULL, actual_start TEXT, actual_end TEXT, attributes_json TEXT NOT NULL DEFAULT '{}',
                    created_at_utc TEXT NOT NULL, relative_path TEXT
                );
                CREATE INDEX idx_states_session_time ON state_records(session_id,condition_label,timepoint_value,timepoint_unit);
                CREATE TABLE data_units(
                    data_unit_id TEXT PRIMARY KEY, state_record_id TEXT NOT NULL REFERENCES state_records(state_record_id) ON DELETE CASCADE,
                    source_path TEXT NOT NULL, source_path_kind TEXT NOT NULL DEFAULT 'external', source_sha256 TEXT NOT NULL,
                    source_size_bytes INTEGER NOT NULL, file_format TEXT NOT NULL, channel_mapping_json TEXT NOT NULL DEFAULT '{}',
                    epoch_selection_json TEXT NOT NULL DEFAULT '{}', time_selection_json TEXT NOT NULL DEFAULT '{}',
                    sampling_rate_hz REAL, signal_unit TEXT, validity_status TEXT NOT NULL DEFAULT 'unchecked',
                    validity_message TEXT, analysis_override_json TEXT NOT NULL DEFAULT '{}', created_at_utc TEXT NOT NULL,
                    original_source_path TEXT, inspection_status TEXT NOT NULL DEFAULT 'unchecked',
                    inspection_json TEXT NOT NULL DEFAULT '{}', inspection_notes TEXT,
                    inspection_updated_at_utc TEXT, import_status TEXT NOT NULL DEFAULT 'ready',
                    inspection_revision INTEGER NOT NULL DEFAULT 0, inspection_fingerprint TEXT,
                    inspection_save_status TEXT NOT NULL DEFAULT 'saved',
                    source_structure_json TEXT NOT NULL DEFAULT '{}', source_structure_fingerprint TEXT
                );
                CREATE INDEX idx_data_units_fingerprint ON data_units(source_sha256,source_size_bytes);
                CREATE TABLE analysis_runs(
                    analysis_id TEXT PRIMARY KEY, data_unit_id TEXT NOT NULL REFERENCES data_units(data_unit_id) ON DELETE CASCADE,
                    module_name TEXT NOT NULL, method_name TEXT, result_path TEXT NOT NULL, schema_version TEXT NOT NULL,
                    parameter_fingerprint TEXT NOT NULL, data_fingerprint TEXT NOT NULL, parameters_json TEXT NOT NULL,
                    calculation_status TEXT NOT NULL, save_status TEXT NOT NULL, review_status TEXT NOT NULL DEFAULT 'pending',
                    review_notes TEXT, created_at_utc TEXT NOT NULL, completed_at_utc TEXT, active INTEGER NOT NULL DEFAULT 1,
                    warnings_json TEXT NOT NULL DEFAULT '[]', error_message TEXT,
                    result_validity TEXT NOT NULL DEFAULT 'current', inspection_revision INTEGER NOT NULL DEFAULT 0,
                    inspection_fingerprint TEXT
                );
                CREATE INDEX idx_analysis_lookup ON analysis_runs(data_unit_id,module_name,active,calculation_status,save_status);
                CREATE TABLE batch_jobs(
                    batch_job_id TEXT PRIMARY KEY, name TEXT NOT NULL, status TEXT NOT NULL, modules_json TEXT NOT NULL,
                    task_config_json TEXT NOT NULL, created_at_utc TEXT NOT NULL, started_at_utc TEXT, finished_at_utc TEXT,
                    cancellation_requested INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE batch_items(
                    batch_item_id TEXT PRIMARY KEY, batch_job_id TEXT NOT NULL REFERENCES batch_jobs(batch_job_id) ON DELETE CASCADE,
                    data_unit_id TEXT NOT NULL REFERENCES data_units(data_unit_id) ON DELETE CASCADE,
                    status TEXT NOT NULL, effective_parameters_json TEXT NOT NULL, error_message TEXT,
                    started_at_utc TEXT, finished_at_utc TEXT
                );
                CREATE TABLE comparison_snapshots(
                    comparison_id TEXT PRIMARY KEY, name TEXT NOT NULL, filters_json TEXT NOT NULL,
                    included_json TEXT NOT NULL, excluded_json TEXT NOT NULL, settings_json TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL, snapshot_path TEXT NOT NULL
                );
                CREATE TABLE structure_templates(
                    template_id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, template_json TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL, updated_at_utc TEXT NOT NULL
                );
                CREATE TABLE inspection_history(
                    history_id TEXT PRIMARY KEY,
                    data_unit_id TEXT NOT NULL REFERENCES data_units(data_unit_id) ON DELETE CASCADE,
                    revision INTEGER NOT NULL, action TEXT NOT NULL, before_json TEXT NOT NULL,
                    after_json TEXT NOT NULL, created_at_utc TEXT NOT NULL
                );
                CREATE INDEX idx_inspection_history_unit ON inspection_history(data_unit_id,revision);
                CREATE TABLE behavior_attachments(
                    attachment_id TEXT PRIMARY KEY,
                    state_record_id TEXT NOT NULL REFERENCES state_records(state_record_id) ON DELETE CASCADE,
                    data_unit_id TEXT REFERENCES data_units(data_unit_id) ON DELETE SET NULL,
                    resource_type TEXT NOT NULL, file_format TEXT, source_path TEXT NOT NULL,
                    source_path_kind TEXT NOT NULL DEFAULT 'external', original_source_path TEXT,
                    time_unit TEXT, notes TEXT, sync_metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at_utc TEXT NOT NULL
                );
                CREATE INDEX idx_behavior_attachment_state ON behavior_attachments(state_record_id,created_at_utc);
                CREATE TABLE behavior_scores(
                    score_id TEXT PRIMARY KEY,
                    state_record_id TEXT NOT NULL REFERENCES state_records(state_record_id) ON DELETE CASCADE,
                    data_unit_id TEXT REFERENCES data_units(data_unit_id) ON DELETE SET NULL,
                    measure_name TEXT NOT NULL, value REAL, unit_or_scale TEXT,
                    observed_start TEXT, observed_end TEXT, rater TEXT, notes TEXT,
                    created_at_utc TEXT NOT NULL
                );
                CREATE INDEX idx_behavior_score_state ON behavior_scores(state_record_id,measure_name,created_at_utc);
                CREATE TABLE synchronization_records(
                    sync_id TEXT PRIMARY KEY,
                    state_record_id TEXT NOT NULL REFERENCES state_records(state_record_id) ON DELETE CASCADE,
                    data_unit_id TEXT REFERENCES data_units(data_unit_id) ON DELETE SET NULL,
                    attachment_id TEXT REFERENCES behavior_attachments(attachment_id) ON DELETE SET NULL,
                    lfp_time_unit TEXT, behavior_time_unit TEXT, start_offset_s REAL,
                    anchor_metadata_json TEXT NOT NULL DEFAULT '{}', clock_drift_json TEXT NOT NULL DEFAULT '{}',
                    method TEXT, quality TEXT, confirmed INTEGER NOT NULL DEFAULT 0, notes TEXT,
                    created_at_utc TEXT NOT NULL
                );
                CREATE INDEX idx_sync_state ON synchronization_records(state_record_id,created_at_utc);
                """
            )

    def _ensure_directories(self) -> None:
        for directory in (
            self.paths.results,
            self.paths.configs,
            self.paths.snapshots,
            self.paths.raw_data,
            self.paths.derived_data,
            self.paths.exports,
            self.paths.logs,
            self.paths.templates,
            self.paths.subjects,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            row = connection.execute("SELECT version FROM schema_info").fetchone()
        if row is None:
            raise ValueError("Project schema metadata is missing")
        version = int(row[0])
        if version == 1:
            self._migrate_v1_to_v2()
            version = 2
        if version == 2:
            self._migrate_v2_to_v3()
            version = 3
        if version == 3:
            self._migrate_v3_to_v4()
            version = 4
        if version == 4:
            self._migrate_v4_to_v5()
            version = 5
        if version != PROJECT_SCHEMA_VERSION:
            raise ValueError(f"Unsupported project schema: {version}")

    def _migrate_v1_to_v2(self) -> None:
        """Non-destructively add portable paths, inspection records and templates."""
        with self.transaction() as connection:
            columns = {row[1] for row in connection.execute("PRAGMA table_info(data_units)").fetchall()}
            additions = {
                "original_source_path": "TEXT",
                "inspection_status": "TEXT NOT NULL DEFAULT 'unchecked'",
                "inspection_json": "TEXT NOT NULL DEFAULT '{}'",
                "inspection_notes": "TEXT",
                "inspection_updated_at_utc": "TEXT",
                "import_status": "TEXT NOT NULL DEFAULT 'ready'",
            }
            for name, declaration in additions.items():
                if name not in columns:
                    connection.execute(f"ALTER TABLE data_units ADD COLUMN {name} {declaration}")
            connection.execute(
                """CREATE TABLE IF NOT EXISTS structure_templates(
                    template_id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, template_json TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL, updated_at_utc TEXT NOT NULL
                )"""
            )
            connection.execute("UPDATE projects SET schema_version=2")
            connection.execute("UPDATE schema_info SET version=2")

    def _migrate_v2_to_v3(self) -> None:
        """Add persistent readable hierarchy paths without changing identities."""
        with self.transaction() as connection:
            for table in ("subjects", "sessions", "state_records"):
                columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}
                if "relative_path" not in columns:
                    connection.execute(f"ALTER TABLE {table} ADD COLUMN relative_path TEXT")
            connection.execute("UPDATE projects SET schema_version=3")
            connection.execute("UPDATE schema_info SET version=3")

    def _migrate_v3_to_v4(self) -> None:
        """Add versioned inspection snapshots and independent result validity."""
        with self.transaction() as connection:
            data_columns = {row[1] for row in connection.execute("PRAGMA table_info(data_units)").fetchall()}
            data_additions = {
                "inspection_revision": "INTEGER NOT NULL DEFAULT 0",
                "inspection_fingerprint": "TEXT",
                "inspection_save_status": "TEXT NOT NULL DEFAULT 'saved'",
                "source_structure_json": "TEXT NOT NULL DEFAULT '{}'",
                "source_structure_fingerprint": "TEXT",
            }
            for name, declaration in data_additions.items():
                if name not in data_columns:
                    connection.execute(f"ALTER TABLE data_units ADD COLUMN {name} {declaration}")
            run_columns = {row[1] for row in connection.execute("PRAGMA table_info(analysis_runs)").fetchall()}
            run_additions = {
                "result_validity": "TEXT NOT NULL DEFAULT 'current'",
                "inspection_revision": "INTEGER NOT NULL DEFAULT 0",
                "inspection_fingerprint": "TEXT",
            }
            for name, declaration in run_additions.items():
                if name not in run_columns:
                    connection.execute(f"ALTER TABLE analysis_runs ADD COLUMN {name} {declaration}")
            connection.execute(
                """CREATE TABLE IF NOT EXISTS inspection_history(
                       history_id TEXT PRIMARY KEY,
                       data_unit_id TEXT NOT NULL REFERENCES data_units(data_unit_id) ON DELETE CASCADE,
                       revision INTEGER NOT NULL, action TEXT NOT NULL, before_json TEXT NOT NULL,
                       after_json TEXT NOT NULL, created_at_utc TEXT NOT NULL
                   )"""
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_inspection_history_unit ON inspection_history(data_unit_id,revision)"
            )
            connection.execute("UPDATE projects SET schema_version=4")
            connection.execute("UPDATE schema_info SET version=4")

    def _migrate_v4_to_v5(self) -> None:
        """Reserve versioned behavior attachments, scores, and synchronization links."""
        with self.transaction() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS behavior_attachments(
                    attachment_id TEXT PRIMARY KEY,
                    state_record_id TEXT NOT NULL REFERENCES state_records(state_record_id) ON DELETE CASCADE,
                    data_unit_id TEXT REFERENCES data_units(data_unit_id) ON DELETE SET NULL,
                    resource_type TEXT NOT NULL, file_format TEXT, source_path TEXT NOT NULL,
                    source_path_kind TEXT NOT NULL DEFAULT 'external', original_source_path TEXT,
                    time_unit TEXT, notes TEXT, sync_metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at_utc TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_behavior_attachment_state ON behavior_attachments(state_record_id,created_at_utc);
                CREATE TABLE IF NOT EXISTS behavior_scores(
                    score_id TEXT PRIMARY KEY,
                    state_record_id TEXT NOT NULL REFERENCES state_records(state_record_id) ON DELETE CASCADE,
                    data_unit_id TEXT REFERENCES data_units(data_unit_id) ON DELETE SET NULL,
                    measure_name TEXT NOT NULL, value REAL, unit_or_scale TEXT,
                    observed_start TEXT, observed_end TEXT, rater TEXT, notes TEXT,
                    created_at_utc TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_behavior_score_state ON behavior_scores(state_record_id,measure_name,created_at_utc);
                CREATE TABLE IF NOT EXISTS synchronization_records(
                    sync_id TEXT PRIMARY KEY,
                    state_record_id TEXT NOT NULL REFERENCES state_records(state_record_id) ON DELETE CASCADE,
                    data_unit_id TEXT REFERENCES data_units(data_unit_id) ON DELETE SET NULL,
                    attachment_id TEXT REFERENCES behavior_attachments(attachment_id) ON DELETE SET NULL,
                    lfp_time_unit TEXT, behavior_time_unit TEXT, start_offset_s REAL,
                    anchor_metadata_json TEXT NOT NULL DEFAULT '{}', clock_drift_json TEXT NOT NULL DEFAULT '{}',
                    method TEXT, quality TEXT, confirmed INTEGER NOT NULL DEFAULT 0, notes TEXT,
                    created_at_utc TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_sync_state ON synchronization_records(state_record_id,created_at_utc);
                """
            )
            connection.execute("UPDATE projects SET schema_version=5")
            connection.execute("UPDATE schema_info SET version=5")

    def _allocate_structure_relative_path(
        self,
        parent_relative: str,
        display_name: str,
        fallback: str,
        used_paths: set[str],
    ) -> str:
        base = normalize_structure_folder_name(display_name, fallback)
        index = 1
        while True:
            folder = base if index == 1 else f"{base} ({index})"
            candidate = (Path(parent_relative) / folder).as_posix()
            target = self.paths.root / Path(candidate)
            existing_can_be_reused = target.is_dir() and not any(target.iterdir())
            if candidate.casefold() not in used_paths and (not target.exists() or existing_can_be_reused):
                used_paths.add(candidate.casefold())
                return candidate
            used_paths.add(candidate.casefold())
            index += 1

    def _used_structure_paths(self, connection: sqlite3.Connection) -> set[str]:
        """Return metadata and on-disk hierarchy paths reserved in this project."""
        used = {
            str(row[0]).casefold()
            for table in ("subjects", "sessions", "state_records")
            for row in connection.execute(
                f"SELECT relative_path FROM {table} WHERE relative_path IS NOT NULL AND relative_path<>''"
            )
        }
        return used

    def _create_structure_directories(self, relative_paths: Iterable[str]) -> list[Path]:
        """Create hierarchy directories and return only directories created now."""
        root = self.paths.root.resolve()
        created: list[Path] = []
        try:
            for relative in sorted(set(relative_paths), key=lambda value: len(Path(value).parts)):
                target = (root / Path(relative)).resolve()
                if os.path.commonpath((str(root), str(target))) != str(root):
                    raise ValueError(f"Hierarchy path escapes the project root: {relative}")
                if target.exists():
                    if not target.is_dir():
                        raise FileExistsError(f"Hierarchy path is not a directory: {target}")
                    continue
                missing: list[Path] = []
                current = target
                while current != root and not current.exists():
                    missing.append(current)
                    current = current.parent
                target.mkdir(parents=True, exist_ok=False)
                created.extend(reversed(missing))
        except Exception:
            for directory in reversed(created):
                try:
                    directory.rmdir()
                except OSError:
                    pass
            raise
        return created

    @staticmethod
    def _remove_created_empty_directories(created: Iterable[Path]) -> None:
        for directory in sorted(set(created), key=lambda value: len(value.parts), reverse=True):
            try:
                directory.rmdir()
            except OSError:
                pass

    def ensure_structure_directories(self) -> dict[str, int]:
        """Backfill missing hierarchy paths and create their readable folders."""
        created_directories: list[Path] = []
        updated = {"subjects": 0, "sessions": 0, "states": 0}
        try:
            with self.transaction() as connection:
                used = self._used_structure_paths(connection)
                subject_paths: dict[str, str] = {}
                for row in connection.execute("SELECT subject_id,subject_code,relative_path FROM subjects ORDER BY created_at_utc"):
                    relative = str(row["relative_path"] or "")
                    if not relative:
                        relative = self._allocate_structure_relative_path("subjects", str(row["subject_code"]), "subject", used)
                        connection.execute("UPDATE subjects SET relative_path=? WHERE subject_id=?", (relative, row["subject_id"]))
                        updated["subjects"] += 1
                    subject_paths[str(row["subject_id"])] = relative
                session_paths: dict[str, str] = {}
                for row in connection.execute("SELECT session_id,subject_id,session_key,relative_path FROM sessions ORDER BY created_at_utc"):
                    relative = str(row["relative_path"] or "")
                    if not relative:
                        relative = self._allocate_structure_relative_path(subject_paths[str(row["subject_id"])], str(row["session_key"]), "session", used)
                        connection.execute("UPDATE sessions SET relative_path=? WHERE session_id=?", (relative, row["session_id"]))
                        updated["sessions"] += 1
                    session_paths[str(row["session_id"])] = relative
                all_paths = list(subject_paths.values()) + list(session_paths.values())
                for row in connection.execute("SELECT state_record_id,session_id,display_name,relative_path FROM state_records ORDER BY created_at_utc"):
                    relative = str(row["relative_path"] or "")
                    if not relative:
                        relative = self._allocate_structure_relative_path(session_paths[str(row["session_id"])], str(row["display_name"]), "state", used)
                        connection.execute("UPDATE state_records SET relative_path=? WHERE state_record_id=?", (relative, row["state_record_id"]))
                        updated["states"] += 1
                    all_paths.append(relative)
                created_directories = self._create_structure_directories(all_paths)
        except Exception:
            self._remove_created_empty_directories(created_directories)
            raise
        updated["directories_created"] = len(created_directories)
        return updated

    @property
    def project(self) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM projects LIMIT 1").fetchone()
        if row is None:
            raise ValueError("Project record is missing")
        result = dict(row)
        result["analysis_template"] = _loads(result.pop("analysis_template_json"), {})
        return result

    def update_project(self, *, name: str | None = None, description: str | None = None, analysis_template: dict[str, Any] | None = None) -> None:
        current = self.project
        template_changed = analysis_template is not None and analysis_template != current["analysis_template"]
        with self.transaction() as connection:
            connection.execute(
                "UPDATE projects SET name=?,description=?,analysis_template_json=? WHERE project_id=?",
                (name if name is not None else current["name"], description if description is not None else current["description"], _json(analysis_template if analysis_template is not None else current["analysis_template"]), current["project_id"]),
            )
            if template_changed:
                connection.execute("UPDATE analysis_runs SET result_validity='needs_recompute' WHERE active=1")

    def add_subject(self, subject_code: str, group_label: str = "", attributes: dict[str, Any] | None = None) -> str:
        code = subject_code.strip()
        if not code:
            raise ValueError("Subject code is required")
        subject_id = new_id("subject")
        created_directories: list[Path] = []
        try:
            with self.transaction() as connection:
                project_row = connection.execute("SELECT project_id FROM projects LIMIT 1").fetchone()
                if project_row is None:
                    raise ValueError("Project record is missing")
                relative_path = self._allocate_structure_relative_path(
                    "subjects", code, "subject", self._used_structure_paths(connection)
                )
                created_directories = self._create_structure_directories([relative_path])
                connection.execute(
                    """INSERT INTO subjects(
                           subject_id,project_id,subject_code,group_label,attributes_json,created_at_utc,relative_path
                       ) VALUES(?,?,?,?,?,?,?)""",
                    (subject_id, project_row["project_id"], code, group_label.strip() or None, _json(attributes), utc_now(), relative_path),
                )
        except Exception:
            self._remove_created_empty_directories(created_directories)
            raise
        return subject_id

    def update_subject(self, subject_id: str, *, subject_code: str, group_label: str = "", attributes: dict[str, Any] | None = None) -> None:
        if attributes is None:
            current = self.query("SELECT attributes_json FROM subjects WHERE subject_id=?", (subject_id,))
            if not current:
                raise KeyError(subject_id)
            attributes = _loads(current[0]["attributes_json"], {})
        with self.transaction() as connection:
            connection.execute(
                "UPDATE subjects SET subject_code=?,group_label=?,attributes_json=? WHERE subject_id=?",
                (subject_code.strip(), group_label.strip() or None, _json(attributes), subject_id),
            )

    def add_session(self, subject_id: str, session_key: str, experiment_name: str = "", session_date: str = "", notes: str = "") -> str:
        key = session_key.strip()
        if not key:
            raise ValueError("Session key is required")
        session_id = new_id("session")
        created_directories: list[Path] = []
        try:
            with self.transaction() as connection:
                subject = connection.execute(
                    "SELECT relative_path FROM subjects WHERE subject_id=?", (subject_id,)
                ).fetchone()
                if subject is None:
                    raise KeyError(subject_id)
                relative_path = self._allocate_structure_relative_path(
                    str(subject["relative_path"]), key, "session", self._used_structure_paths(connection)
                )
                created_directories = self._create_structure_directories([relative_path])
                connection.execute(
                    """INSERT INTO sessions(
                           session_id,subject_id,session_key,experiment_name,session_date,notes,created_at_utc,relative_path
                       ) VALUES(?,?,?,?,?,?,?,?)""",
                    (session_id, subject_id, key, experiment_name.strip() or None, session_date.strip() or None, notes.strip() or None, utc_now(), relative_path),
                )
        except Exception:
            self._remove_created_empty_directories(created_directories)
            raise
        return session_id

    def update_session(self, session_id: str, *, session_key: str, experiment_name: str = "", session_date: str = "", notes: str = "") -> None:
        with self.transaction() as connection:
            connection.execute(
                "UPDATE sessions SET session_key=?,experiment_name=?,session_date=?,notes=? WHERE session_id=?",
                (session_key.strip(), experiment_name.strip() or None, session_date.strip() or None, notes.strip() or None, session_id),
            )

    def add_state_record(
        self,
        session_id: str,
        display_name: str,
        *,
        condition_label: str = "",
        timepoint_value: float | None = None,
        timepoint_unit: str = "min",
        reference_event: str = "",
        actual_start: str = "",
        actual_end: str = "",
        attributes: dict[str, Any] | None = None,
    ) -> str:
        label = display_name.strip()
        if not label:
            raise ValueError("State display name is required")
        state_record_id = new_id("state")
        created_directories: list[Path] = []
        try:
            with self.transaction() as connection:
                session = connection.execute(
                    "SELECT relative_path FROM sessions WHERE session_id=?", (session_id,)
                ).fetchone()
                if session is None:
                    raise KeyError(session_id)
                relative_path = self._allocate_structure_relative_path(
                    str(session["relative_path"]), label, "state", self._used_structure_paths(connection)
                )
                created_directories = self._create_structure_directories([relative_path])
                connection.execute(
                    """INSERT INTO state_records(
                           state_record_id,session_id,condition_label,timepoint_value,timepoint_unit,reference_event,
                           display_name,actual_start,actual_end,attributes_json,created_at_utc,relative_path
                       ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        state_record_id, session_id, condition_label.strip() or None, timepoint_value,
                        timepoint_unit.strip() or None, reference_event.strip() or None, label,
                        actual_start.strip() or None, actual_end.strip() or None, _json(attributes), utc_now(), relative_path,
                    ),
                )
        except Exception:
            self._remove_created_empty_directories(created_directories)
            raise
        return state_record_id

    def update_state_record(
        self,
        state_record_id: str,
        *,
        display_name: str,
        condition_label: str = "",
        timepoint_value: float | None = None,
        timepoint_unit: str = "min",
        reference_event: str = "",
        actual_start: str = "",
        actual_end: str = "",
        attributes: dict[str, Any] | None = None,
    ) -> None:
        if attributes is None:
            current = self.query("SELECT attributes_json FROM state_records WHERE state_record_id=?", (state_record_id,))
            if not current:
                raise KeyError(state_record_id)
            attributes = _loads(current[0]["attributes_json"], {})
        with self.transaction() as connection:
            connection.execute(
                """UPDATE state_records SET condition_label=?,timepoint_value=?,timepoint_unit=?,reference_event=?,
                   display_name=?,actual_start=?,actual_end=?,attributes_json=? WHERE state_record_id=?""",
                (
                    condition_label.strip() or None,
                    timepoint_value,
                    timepoint_unit.strip() or None,
                    reference_event.strip() or None,
                    display_name.strip(),
                    actual_start.strip() or None,
                    actual_end.strip() or None,
                    _json(attributes),
                    state_record_id,
                ),
            )

    def add_behavior_attachment(
        self,
        state_record_id: str,
        source_path: str | Path,
        *,
        resource_type: str = "behavior",
        file_format: str = "",
        data_unit_id: str | None = None,
        source_path_kind: str = "external",
        original_source_path: str | Path | None = None,
        time_unit: str = "",
        notes: str = "",
        sync_metadata: dict[str, Any] | None = None,
    ) -> str:
        """Register a behavior resource without assuming it is synchronized.

        This is intentionally a metadata-only reservation.  Resource copying,
        video decoding, event extraction, and synchronization confirmation are
        separate future workflows.
        """
        if not self.query("SELECT 1 FROM state_records WHERE state_record_id=?", (state_record_id,)):
            raise KeyError(state_record_id)
        if data_unit_id and not self.query("SELECT 1 FROM data_units WHERE data_unit_id=? AND state_record_id=?", (data_unit_id, state_record_id)):
            raise ValueError("Behavior attachment data_unit_id must belong to the same state")
        attachment_id = new_id("behavior")
        with self.transaction() as connection:
            connection.execute(
                """INSERT INTO behavior_attachments(
                    attachment_id,state_record_id,data_unit_id,resource_type,file_format,source_path,
                    source_path_kind,original_source_path,time_unit,notes,sync_metadata_json,created_at_utc
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    attachment_id, state_record_id, data_unit_id, resource_type.strip() or "behavior",
                    file_format.strip() or None, str(Path(source_path).expanduser().resolve()) if source_path_kind == "external" else str(Path(source_path)),
                    source_path_kind, str(Path(original_source_path).expanduser().resolve()) if original_source_path else None,
                    time_unit.strip() or None, notes.strip() or None, _json(sync_metadata), utc_now(),
                ),
            )
        return attachment_id

    def behavior_attachments(self, state_record_id: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM behavior_attachments"
        parameters: tuple[Any, ...] = ()
        if state_record_id:
            sql += " WHERE state_record_id=?"
            parameters = (state_record_id,)
        sql += " ORDER BY created_at_utc,attachment_id"
        rows = self.query(sql, parameters)
        for row in rows:
            row["sync_metadata"] = _loads(row.pop("sync_metadata_json"), {})
        return rows

    def add_behavior_score(
        self,
        state_record_id: str,
        measure_name: str,
        value: float | None = None,
        *,
        unit_or_scale: str = "",
        data_unit_id: str | None = None,
        observed_start: str = "",
        observed_end: str = "",
        rater: str = "",
        notes: str = "",
    ) -> str:
        """Store one score; ``None`` remains missing and zero remains zero."""
        if not measure_name.strip():
            raise ValueError("Score measure_name is required")
        if not self.query("SELECT 1 FROM state_records WHERE state_record_id=?", (state_record_id,)):
            raise KeyError(state_record_id)
        if data_unit_id and not self.query("SELECT 1 FROM data_units WHERE data_unit_id=? AND state_record_id=?", (data_unit_id, state_record_id)):
            raise ValueError("Behavior score data_unit_id must belong to the same state")
        score_id = new_id("score")
        with self.transaction() as connection:
            connection.execute(
                """INSERT INTO behavior_scores(
                    score_id,state_record_id,data_unit_id,measure_name,value,unit_or_scale,
                    observed_start,observed_end,rater,notes,created_at_utc
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (score_id, state_record_id, data_unit_id, measure_name.strip(), value, unit_or_scale.strip() or None,
                 observed_start.strip() or None, observed_end.strip() or None, rater.strip() or None, notes.strip() or None, utc_now()),
            )
        return score_id

    def behavior_scores(self, state_record_id: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM behavior_scores"
        parameters: tuple[Any, ...] = ()
        if state_record_id:
            sql += " WHERE state_record_id=?"
            parameters = (state_record_id,)
        return self.query(sql + " ORDER BY created_at_utc,score_id", parameters)

    def add_synchronization_record(
        self,
        state_record_id: str,
        *,
        data_unit_id: str | None = None,
        attachment_id: str | None = None,
        lfp_time_unit: str = "s",
        behavior_time_unit: str = "s",
        start_offset_s: float | None = None,
        anchor_metadata: dict[str, Any] | None = None,
        clock_drift: dict[str, Any] | None = None,
        method: str = "",
        quality: str = "unreviewed",
        confirmed: bool = False,
        notes: str = "",
    ) -> str:
        if not self.query("SELECT 1 FROM state_records WHERE state_record_id=?", (state_record_id,)):
            raise KeyError(state_record_id)
        if data_unit_id and not self.query("SELECT 1 FROM data_units WHERE data_unit_id=? AND state_record_id=?", (data_unit_id, state_record_id)):
            raise ValueError("Synchronization data_unit_id must belong to the same state")
        if attachment_id and not self.query("SELECT 1 FROM behavior_attachments WHERE attachment_id=? AND state_record_id=?", (attachment_id, state_record_id)):
            raise ValueError("Synchronization attachment_id must belong to the same state")
        sync_id = new_id("sync")
        with self.transaction() as connection:
            connection.execute(
                """INSERT INTO synchronization_records(
                    sync_id,state_record_id,data_unit_id,attachment_id,lfp_time_unit,behavior_time_unit,
                    start_offset_s,anchor_metadata_json,clock_drift_json,method,quality,confirmed,notes,created_at_utc
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (sync_id, state_record_id, data_unit_id, attachment_id, lfp_time_unit.strip() or None,
                 behavior_time_unit.strip() or None, start_offset_s, _json(anchor_metadata), _json(clock_drift),
                 method.strip() or None, quality.strip() or None, int(bool(confirmed)), notes.strip() or None, utc_now()),
            )
        return sync_id

    def synchronization_records(self, state_record_id: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM synchronization_records"
        parameters: tuple[Any, ...] = ()
        if state_record_id:
            sql += " WHERE state_record_id=?"
            parameters = (state_record_id,)
        rows = self.query(sql + " ORDER BY created_at_utc,sync_id", parameters)
        for row in rows:
            row["anchor_metadata"] = _loads(row.pop("anchor_metadata_json"), {})
            row["clock_drift"] = _loads(row.pop("clock_drift_json"), {})
        return rows

    def add_data_unit(
        self,
        state_record_id: str,
        source_path: str | Path,
        *,
        channel_mapping: dict[str, Any] | list[dict[str, Any]] | None = None,
        epoch_selection: dict[str, Any] | None = None,
        time_selection: dict[str, Any] | None = None,
        sampling_rate_hz: float | None = None,
        signal_unit: str = "",
        validity_status: str = "unchecked",
        validity_message: str = "",
        analysis_override: dict[str, Any] | None = None,
        source_path_kind: str = "external",
        original_source_path: str | Path | None = None,
        import_status: str = "ready",
        source_structure: dict[str, Any] | None = None,
    ) -> str:
        if not self.query("SELECT 1 FROM state_records WHERE state_record_id=?", (state_record_id,)):
            raise KeyError(f"Unknown target state_record_id: {state_record_id}")
        source = self.resolve_source_path_value(source_path, source_path_kind)
        fingerprint = file_fingerprint(source)
        data_unit_id = new_id("data")
        structure = dict(source_structure or {})
        structure_fingerprint = _fingerprint_json(structure) if structure else None
        with self.transaction() as connection:
            connection.execute(
                """INSERT INTO data_units(
                    data_unit_id,state_record_id,source_path,source_path_kind,source_sha256,source_size_bytes,
                    file_format,channel_mapping_json,epoch_selection_json,time_selection_json,sampling_rate_hz,
                    signal_unit,validity_status,validity_message,analysis_override_json,created_at_utc,
                    original_source_path,inspection_status,inspection_json,inspection_notes,
                    inspection_updated_at_utc,import_status,inspection_revision,inspection_fingerprint,
                    inspection_save_status,source_structure_json,source_structure_fingerprint
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    data_unit_id, state_record_id,
                    str(Path(source_path)) if source_path_kind == "project_relative" else str(source),
                    source_path_kind, fingerprint["sha256"], fingerprint["size_bytes"],
                    source.suffix.lower().lstrip("."), _json(channel_mapping), _json(epoch_selection),
                    _json(time_selection), sampling_rate_hz, signal_unit.strip() or None, validity_status,
                    validity_message.strip() or None, _json(analysis_override), utc_now(),
                    str(Path(original_source_path).expanduser().resolve()) if original_source_path else None,
                    "unchecked", "{}", None, None, import_status, 0, None, "saved",
                    _json(structure), structure_fingerprint,
                ),
            )
        return data_unit_id

    def resolve_source_path_value(self, source_path: str | Path, source_path_kind: str = "external") -> Path:
        path = Path(source_path).expanduser()
        if source_path_kind == "project_relative":
            resolved = (self.paths.root / path).resolve()
            resolved.relative_to(self.paths.root)
            return resolved
        return path.resolve()

    def resolve_source_path(self, data_unit: str | dict[str, Any]) -> Path:
        if isinstance(data_unit, str):
            rows = self.query("SELECT source_path,source_path_kind FROM data_units WHERE data_unit_id=?", (data_unit,))
            if not rows:
                raise KeyError(data_unit)
            record = rows[0]
        else:
            record = data_unit
        return self.resolve_source_path_value(record["source_path"], str(record.get("source_path_kind") or "external"))

    def copy_source_into_project(self, source_path: str | Path) -> tuple[str, dict[str, Any], bool]:
        """Copy a source once into the project and return its relative path."""
        source = Path(source_path).expanduser().resolve()
        fingerprint = file_fingerprint(source)
        safe_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", source.name).rstrip(" .") or "recording.fif"
        target_dir = self.paths.raw_data / fingerprint["sha256"][:16]
        target = target_dir / safe_name
        if target.exists():
            existing = file_fingerprint(target)
            if existing == fingerprint:
                return target.relative_to(self.paths.root).as_posix(), fingerprint, False
            target = target_dir / f"{fingerprint['sha256'][:8]}_{safe_name}"
        target_dir.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
        try:
            shutil.copy2(source, temporary)
            copied = file_fingerprint(temporary)
            if copied != fingerprint:
                raise OSError("Copied file fingerprint does not match the source")
            os.replace(temporary, target)
            try:
                target.chmod(stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)
            except OSError:
                pass
        finally:
            if temporary.exists():
                temporary.unlink()
        return target.relative_to(self.paths.root).as_posix(), fingerprint, True

    def import_data_unit(
        self,
        state_record_id: str,
        source_path: str | Path,
        **kwargs: Any,
    ) -> tuple[str, bool]:
        """Copy one file into the project, verify it, then register the unit."""
        if not self.query("SELECT 1 FROM state_records WHERE state_record_id=?", (state_record_id,)):
            raise KeyError(f"Unknown target state_record_id: {state_record_id}")
        epoch_selection = kwargs.get("epoch_selection") or {}
        time_selection = kwargs.get("time_selection") or {}
        duplicates = self.duplicate_selection_candidates(
            source_path,
            epoch_selection=epoch_selection,
            time_selection=time_selection,
        )
        if duplicates:
            existing = ", ".join(str(row["data_unit_id"]) for row in duplicates)
            raise ValueError(f"Identical source and selection are already registered: {existing}")
        relative_path, _fingerprint, copied = self.copy_source_into_project(source_path)
        try:
            data_unit_id = self.add_data_unit(
                state_record_id,
                relative_path,
                source_path_kind="project_relative",
                original_source_path=source_path,
                import_status="ready",
                **kwargs,
            )
        except Exception:
            if copied:
                target = self.resolve_source_path_value(relative_path, "project_relative")
                references = self.query("SELECT 1 FROM data_units WHERE source_path=? AND source_path_kind='project_relative'", (relative_path,))
                if not references and target.is_file():
                    target.chmod(stat.S_IWRITE | stat.S_IREAD)
                    target.unlink()
                    try:
                        target.parent.rmdir()
                    except OSError:
                        pass
            raise
        return data_unit_id, copied

    def organize_external_data(self, data_unit_id: str) -> dict[str, Any]:
        """Copy an existing external source into the project without changing identity."""
        rows = self.data_units(data_unit_ids=[data_unit_id])
        if len(rows) != 1:
            raise KeyError(data_unit_id)
        unit = rows[0]
        if unit.get("source_path_kind") == "project_relative":
            return {"data_unit_id": data_unit_id, "status": "already_internal", "path": unit["source_path"]}
        source = self.resolve_source_path(unit)
        relative_path, fingerprint, copied = self.copy_source_into_project(source)
        if fingerprint["sha256"] != unit["source_sha256"] or fingerprint["size_bytes"] != int(unit["source_size_bytes"]):
            raise ValueError("External source changed and cannot be organized without review")
        with self.transaction() as connection:
            connection.execute(
                "UPDATE data_units SET source_path=?,source_path_kind='project_relative',original_source_path=?,import_status='ready' WHERE data_unit_id=?",
                (relative_path, str(source), data_unit_id),
            )
        return {"data_unit_id": data_unit_id, "status": "copied" if copied else "reused", "path": relative_path}

    def duplicate_candidates(self, source_path: str | Path) -> list[dict[str, Any]]:
        fingerprint = file_fingerprint(source_path)
        return self.query(
            "SELECT * FROM data_units WHERE source_sha256=? AND source_size_bytes=?",
            (fingerprint["sha256"], fingerprint["size_bytes"]),
        )

    def duplicate_selection_candidates(
        self,
        source_path: str | Path,
        *,
        epoch_selection: dict[str, Any] | None = None,
        time_selection: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Return records with identical content and identical explicit selection."""
        expected_epochs = epoch_selection or {}
        expected_time = time_selection or {}
        matches: list[dict[str, Any]] = []
        for row in self.duplicate_candidates(source_path):
            if _loads(row.get("epoch_selection_json"), {}) == expected_epochs and _loads(row.get("time_selection_json"), {}) == expected_time:
                matches.append(row)
        return matches

    def query(self, sql: str, parameters: Iterable[Any] = ()) -> list[dict[str, Any]]:
        with self._connect() as connection:
            return [dict(row) for row in connection.execute(sql, tuple(parameters)).fetchall()]

    def subjects(self) -> list[dict[str, Any]]:
        return self.query("SELECT * FROM subjects ORDER BY subject_code")

    def sessions(self, subject_id: str | None = None) -> list[dict[str, Any]]:
        if subject_id:
            return self.query("SELECT * FROM sessions WHERE subject_id=? ORDER BY session_key,created_at_utc", (subject_id,))
        return self.query("SELECT * FROM sessions ORDER BY session_key,created_at_utc")

    def state_records(self, session_id: str | None = None) -> list[dict[str, Any]]:
        if session_id:
            return self.query("SELECT * FROM state_records WHERE session_id=? ORDER BY timepoint_value,display_name", (session_id,))
        return self.query("SELECT * FROM state_records ORDER BY timepoint_value,display_name")

    def state_targets(self) -> list[dict[str, Any]]:
        """Return existing import targets with stable identities and readable ancestry."""
        return self.query(
            """SELECT r.*,s.session_key,s.experiment_name,u.subject_id,u.subject_code,u.group_label
               FROM state_records r JOIN sessions s ON s.session_id=r.session_id
               JOIN subjects u ON u.subject_id=s.subject_id
               ORDER BY u.subject_code,s.session_key,r.timepoint_value,r.display_name"""
        )

    @staticmethod
    def _state_semantic_signature(row: dict[str, Any]) -> tuple[Any, ...]:
        return (
            str(row.get("session_id") or ""),
            str(row.get("display_name") or "").strip().casefold(),
            str(row.get("condition_label") or "").strip().casefold(),
            row.get("timepoint_value"),
            str(row.get("timepoint_unit") or "").strip().casefold(),
            str(row.get("reference_event") or "").strip().casefold(),
            str(row.get("actual_start") or ""),
            str(row.get("actual_end") or ""),
            str(row.get("attributes_json") or "{}"),
        )

    def duplicate_state_preview(self) -> list[dict[str, Any]]:
        """List same-parent duplicate-looking states without changing them."""
        states = self.query(
            """SELECT r.*,s.session_key,u.subject_code,
                      (SELECT COUNT(*) FROM data_units d WHERE d.state_record_id=r.state_record_id) AS data_count,
                      (SELECT COUNT(*) FROM analysis_runs a JOIN data_units d ON d.data_unit_id=a.data_unit_id
                       WHERE d.state_record_id=r.state_record_id) AS result_count
               FROM state_records r JOIN sessions s ON s.session_id=r.session_id
               JOIN subjects u ON u.subject_id=s.subject_id
               ORDER BY u.subject_code,s.session_key,r.created_at_utc"""
        )
        grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for row in states:
            key = (str(row["session_id"]), str(row["display_name"]).strip().casefold())
            grouped.setdefault(key, []).append(row)
        result: list[dict[str, Any]] = []
        for rows in grouped.values():
            if len(rows) < 2:
                continue
            signatures = {self._state_semantic_signature(row) for row in rows}
            result.append(
                {
                    "subject_code": rows[0]["subject_code"],
                    "session_key": rows[0]["session_key"],
                    "display_name": rows[0]["display_name"],
                    "state_ids": [row["state_record_id"] for row in rows],
                    "nodes": rows,
                    "safe_to_merge": len(signatures) == 1,
                    "reason": "exact same-parent semantic duplicate" if len(signatures) == 1 else "same label but metadata differ; manual review required",
                }
            )
        return result

    def merge_duplicate_states(self, state_record_ids: Iterable[str]) -> dict[str, Any]:
        """Merge one proven exact duplicate group after a recoverable DB backup."""
        ids = list(dict.fromkeys(map(str, state_record_ids)))
        if len(ids) < 2:
            raise ValueError("At least two state IDs are required")
        placeholders = ",".join("?" for _ in ids)
        rows = self.query(
            f"SELECT * FROM state_records WHERE state_record_id IN ({placeholders}) ORDER BY created_at_utc,state_record_id",
            ids,
        )
        if len(rows) != len(ids):
            raise KeyError("One or more duplicate state IDs no longer exist")
        if len({self._state_semantic_signature(row) for row in rows}) != 1:
            raise ValueError("The selected states are not exact same-parent semantic duplicates")
        backup_dir = self.paths.logs / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        backup_path = backup_dir / f"project-before-state-merge-{stamp}-{uuid.uuid4().hex[:8]}.sqlite3"
        source = self._connect()
        destination = sqlite3.connect(backup_path)
        try:
            source.backup(destination)
        finally:
            destination.close()
            source.close()
        canonical = rows[0]
        duplicate_ids = [str(row["state_record_id"]) for row in rows[1:]]
        moved = 0
        with self.transaction() as connection:
            for duplicate_id in duplicate_ids:
                moved += int(
                    connection.execute(
                        "UPDATE data_units SET state_record_id=? WHERE state_record_id=?",
                        (canonical["state_record_id"], duplicate_id),
                    ).rowcount
                )
                connection.execute("DELETE FROM state_records WHERE state_record_id=?", (duplicate_id,))
        removed_directories: list[str] = []
        for row in rows[1:]:
            relative = str(row.get("relative_path") or "")
            if not relative:
                continue
            target = (self.paths.root / relative).resolve()
            try:
                target.relative_to(self.paths.root)
                target.rmdir()
                removed_directories.append(relative)
            except OSError:
                pass
        return {
            "canonical_state_id": canonical["state_record_id"],
            "removed_state_ids": duplicate_ids,
            "moved_data_units": moved,
            "backup_path": str(backup_path),
            "removed_empty_directories": removed_directories,
        }

    def data_units(self, *, data_unit_ids: Iterable[str] | None = None) -> list[dict[str, Any]]:
        sql = """
            SELECT d.*,r.display_name AS state_display_name,r.condition_label,r.timepoint_value,r.timepoint_unit,r.reference_event,
                   s.session_id,s.session_key,s.experiment_name,s.session_date,u.subject_id,u.subject_code,u.group_label,
                   p.project_id,p.name AS project_name
            FROM data_units d JOIN state_records r ON r.state_record_id=d.state_record_id
            JOIN sessions s ON s.session_id=r.session_id JOIN subjects u ON u.subject_id=s.subject_id
            JOIN projects p ON p.project_id=u.project_id
        """
        parameters: tuple[Any, ...] = ()
        ids = list(data_unit_ids or [])
        if ids:
            sql += f" WHERE d.data_unit_id IN ({','.join('?' for _ in ids)})"
            parameters = tuple(ids)
        sql += " ORDER BY u.subject_code,s.session_key,r.timepoint_value,r.display_name,d.created_at_utc"
        rows = self.query(sql, parameters)
        for row in rows:
            for key, default in (
                ("channel_mapping_json", {}),
                ("epoch_selection_json", {}),
                ("time_selection_json", {}),
                ("analysis_override_json", {}),
                ("inspection_json", {}),
                ("source_structure_json", {}),
            ):
                row[key.removesuffix("_json")] = _loads(row.pop(key), default)
            row["dataset_id"] = row["data_unit_id"]
            row["resolved_source_path"] = str(self.resolve_source_path(row))
        return rows

    def save_structure_template(self, name: str, template: dict[str, Any]) -> str:
        template_name = name.strip()
        if not template_name:
            raise ValueError("Template name is required")
        existing = self.query("SELECT template_id FROM structure_templates WHERE name=?", (template_name,))
        now = utc_now()
        if existing:
            template_id = str(existing[0]["template_id"])
            with self.transaction() as connection:
                connection.execute(
                    "UPDATE structure_templates SET template_json=?,updated_at_utc=? WHERE template_id=?",
                    (_json(template), now, template_id),
                )
        else:
            template_id = new_id("template")
            with self.transaction() as connection:
                connection.execute(
                    "INSERT INTO structure_templates VALUES(?,?,?,?,?)",
                    (template_id, template_name, _json(template), now, now),
                )
        target = self.paths.templates / f"{template_id}.json"
        temporary = target.with_suffix(".json.tmp")
        temporary.write_text(json.dumps({"schema_version": 1, "template_id": template_id, "name": template_name, "template": template}, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, target)
        return template_id

    def structure_templates(self) -> list[dict[str, Any]]:
        rows = self.query("SELECT * FROM structure_templates ORDER BY name")
        for row in rows:
            row["template"] = _loads(row.pop("template_json"), {})
        return rows

    def preview_structure_template(self, template: dict[str, Any]) -> dict[str, Any]:
        """Build a read-only plan for applying ``template`` to this project."""
        subject_specs = list(template.get("subjects", []))
        session_specs = list(template.get("sessions", []))
        state_specs = list(template.get("states", []))
        plan: dict[str, Any] = {
            "subjects_created": 0, "sessions_created": 0, "states_created": 0,
            "subjects_reused": 0, "sessions_reused": 0, "states_reused": 0,
            "target_paths": [],
        }
        if not subject_specs or not session_specs or not state_specs:
            return plan
        with self._connect() as connection:
            used = self._used_structure_paths(connection)
            subjects = {
                str(row["subject_code"]): dict(row)
                for row in connection.execute("SELECT * FROM subjects")
            }
            sessions = {
                (str(row["subject_id"]), str(row["session_key"])): dict(row)
                for row in connection.execute("SELECT * FROM sessions")
            }
            states: dict[str, list[dict[str, Any]]] = {}
            for row in connection.execute("SELECT * FROM state_records"):
                states.setdefault(str(row["session_id"]), []).append(dict(row))
            for subject_spec in subject_specs:
                code = str(subject_spec.get("subject_code", "") if isinstance(subject_spec, dict) else subject_spec).strip()
                if not code:
                    raise ValueError("Template contains an empty subject code")
                subject = subjects.get(code)
                if subject is None:
                    subject_id = f"planned-subject:{code}"
                    subject_path = self._allocate_structure_relative_path("subjects", code, "subject", used)
                    subject = {"subject_id": subject_id, "relative_path": subject_path}
                    subjects[code] = subject
                    plan["subjects_created"] += 1
                else:
                    subject_id = str(subject["subject_id"])
                    subject_path = str(subject["relative_path"])
                    plan["subjects_reused"] += 1
                plan["target_paths"].append(subject_path)
                for session_spec in session_specs:
                    key = str(session_spec.get("session_key", "") if isinstance(session_spec, dict) else session_spec).strip()
                    if not key:
                        raise ValueError("Template contains an empty session key")
                    session = sessions.get((subject_id, key))
                    if session is None:
                        session_id = f"planned-session:{subject_id}:{key}"
                        session_path = self._allocate_structure_relative_path(subject_path, key, "session", used)
                        session = {"session_id": session_id, "relative_path": session_path}
                        sessions[(subject_id, key)] = session
                        states[session_id] = []
                        plan["sessions_created"] += 1
                    else:
                        session_id = str(session["session_id"])
                        session_path = str(session["relative_path"])
                        plan["sessions_reused"] += 1
                    plan["target_paths"].append(session_path)
                    existing_states = states.setdefault(session_id, [])
                    for raw_state_spec in state_specs:
                        state_spec = raw_state_spec if isinstance(raw_state_spec, dict) else {"display_name": str(raw_state_spec)}
                        timepoint = state_spec.get("timepoint_value")
                        label = str(state_spec.get("display_name", "")).strip()
                        if not label:
                            label = "Baseline" if timepoint is None else f"T{float(timepoint):g}"
                        unit = str(state_spec.get("timepoint_unit", "min") or "min")
                        condition = str(state_spec.get("condition_label", "") or "")
                        match = next(
                            (
                                row for row in existing_states
                                if str(row.get("display_name") or "") == label
                                and row.get("timepoint_value") == timepoint
                                and str(row.get("timepoint_unit") or "") == unit
                                and str(row.get("condition_label") or "") == condition
                            ),
                            None,
                        )
                        if match is None:
                            state_path = self._allocate_structure_relative_path(session_path, label, "state", used)
                            match = {
                                "display_name": label, "timepoint_value": timepoint, "timepoint_unit": unit,
                                "condition_label": condition or None, "relative_path": state_path,
                            }
                            existing_states.append(match)
                            plan["states_created"] += 1
                        else:
                            state_path = str(match["relative_path"])
                            plan["states_reused"] += 1
                        plan["target_paths"].append(state_path)
        plan["target_paths"] = list(dict.fromkeys(plan["target_paths"]))
        return plan

    def apply_structure_template(self, template: dict[str, Any]) -> dict[str, Any]:
        """Atomically instantiate a template as metadata records and folders."""
        subject_specs = list(template.get("subjects", []))
        session_specs = list(template.get("sessions", []))
        state_specs = list(template.get("states", []))
        if not subject_specs or not session_specs or not state_specs:
            raise ValueError("Subjects, sessions, and states must each contain at least one item")
        self.ensure_structure_directories()
        counts: dict[str, Any] = {
            "subjects_created": 0, "sessions_created": 0, "states_created": 0,
            "subjects_reused": 0, "sessions_reused": 0, "states_reused": 0,
            "directories_created": 0, "subject_ids": [], "session_ids": [], "state_ids": [],
            "relative_paths": [],
        }
        created_directories: list[Path] = []
        try:
            with self.transaction() as connection:
                project_row = connection.execute("SELECT project_id FROM projects LIMIT 1").fetchone()
                if project_row is None:
                    raise ValueError("Project record is missing")
                used = self._used_structure_paths(connection)
                subjects = {
                    str(row["subject_code"]): dict(row)
                    for row in connection.execute("SELECT * FROM subjects WHERE project_id=?", (project_row["project_id"],))
                }
                sessions = {
                    (str(row["subject_id"]), str(row["session_key"])): dict(row)
                    for row in connection.execute("SELECT * FROM sessions")
                }
                states: dict[str, list[dict[str, Any]]] = {}
                for row in connection.execute("SELECT * FROM state_records"):
                    states.setdefault(str(row["session_id"]), []).append(dict(row))
                affected_paths: list[str] = []
                for subject_spec in subject_specs:
                    code = str(subject_spec.get("subject_code", "") if isinstance(subject_spec, dict) else subject_spec).strip()
                    group = str(subject_spec.get("group_label", "") if isinstance(subject_spec, dict) else "").strip()
                    if not code:
                        raise ValueError("Template contains an empty subject code")
                    subject = subjects.get(code)
                    if subject is None:
                        subject_id = new_id("subject")
                        relative_path = self._allocate_structure_relative_path("subjects", code, "subject", used)
                        connection.execute(
                            """INSERT INTO subjects(
                                   subject_id,project_id,subject_code,group_label,attributes_json,created_at_utc,relative_path
                               ) VALUES(?,?,?,?,?,?,?)""",
                            (subject_id, project_row["project_id"], code, group or None, _json(subject_spec.get("attributes") if isinstance(subject_spec, dict) else None), utc_now(), relative_path),
                        )
                        subject = {"subject_id": subject_id, "subject_code": code, "relative_path": relative_path}
                        subjects[code] = subject
                        counts["subjects_created"] += 1
                    else:
                        counts["subjects_reused"] += 1
                    subject_id = str(subject["subject_id"])
                    subject_path = str(subject["relative_path"])
                    counts["subject_ids"].append(subject_id)
                    affected_paths.append(subject_path)
                    for session_spec in session_specs:
                        key = str(session_spec.get("session_key", "") if isinstance(session_spec, dict) else session_spec).strip()
                        if not key:
                            raise ValueError("Template contains an empty session key")
                        session = sessions.get((subject_id, key))
                        if session is None:
                            session_id = new_id("session")
                            relative_path = self._allocate_structure_relative_path(subject_path, key, "session", used)
                            experiment = str(session_spec.get("experiment_name", "") if isinstance(session_spec, dict) else "").strip()
                            connection.execute(
                                """INSERT INTO sessions(
                                       session_id,subject_id,session_key,experiment_name,session_date,notes,created_at_utc,relative_path
                                   ) VALUES(?,?,?,?,?,?,?,?)""",
                                (session_id, subject_id, key, experiment or None, None, None, utc_now(), relative_path),
                            )
                            session = {"session_id": session_id, "subject_id": subject_id, "session_key": key, "relative_path": relative_path}
                            sessions[(subject_id, key)] = session
                            states[session_id] = []
                            counts["sessions_created"] += 1
                        else:
                            counts["sessions_reused"] += 1
                        session_id = str(session["session_id"])
                        session_path = str(session["relative_path"])
                        counts["session_ids"].append(session_id)
                        affected_paths.append(session_path)
                        existing_states = states.setdefault(session_id, [])
                        for raw_state_spec in state_specs:
                            state_spec = raw_state_spec if isinstance(raw_state_spec, dict) else {"display_name": str(raw_state_spec)}
                            timepoint = state_spec.get("timepoint_value")
                            label = str(state_spec.get("display_name", "")).strip()
                            if not label:
                                label = "Baseline" if timepoint is None else f"T{float(timepoint):g}"
                            unit = str(state_spec.get("timepoint_unit", "min") or "min")
                            condition = str(state_spec.get("condition_label", "") or "")
                            match = next(
                                (
                                    row for row in existing_states
                                    if str(row.get("display_name") or "") == label
                                    and row.get("timepoint_value") == timepoint
                                    and str(row.get("timepoint_unit") or "") == unit
                                    and str(row.get("condition_label") or "") == condition
                                ),
                                None,
                            )
                            if match is None:
                                state_id = new_id("state")
                                relative_path = self._allocate_structure_relative_path(session_path, label, "state", used)
                                connection.execute(
                                    """INSERT INTO state_records(
                                           state_record_id,session_id,condition_label,timepoint_value,timepoint_unit,
                                           reference_event,display_name,actual_start,actual_end,attributes_json,
                                           created_at_utc,relative_path
                                       ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                                    (
                                        state_id, session_id, condition or None, timepoint, unit,
                                        str(state_spec.get("reference_event", "") or "") or None, label, None, None,
                                        _json(state_spec.get("attributes")), utc_now(), relative_path,
                                    ),
                                )
                                match = {
                                    "state_record_id": state_id, "session_id": session_id,
                                    "display_name": label, "condition_label": condition or None,
                                    "timepoint_value": timepoint, "timepoint_unit": unit,
                                    "relative_path": relative_path,
                                }
                                existing_states.append(match)
                                counts["states_created"] += 1
                            else:
                                counts["states_reused"] += 1
                            counts["state_ids"].append(str(match["state_record_id"]))
                            affected_paths.append(str(match["relative_path"]))
                created_directories = self._create_structure_directories(affected_paths)
                counts["relative_paths"] = list(dict.fromkeys(affected_paths))
                counts["directories_created"] = len(created_directories)
        except Exception:
            self._remove_created_empty_directories(created_directories)
            raise
        counts["subject_ids"] = list(dict.fromkeys(counts["subject_ids"]))
        counts["session_ids"] = list(dict.fromkeys(counts["session_ids"]))
        counts["state_ids"] = list(dict.fromkeys(counts["state_ids"]))
        return counts

    def save_inspection(
        self,
        data_unit_id: str,
        inspection: dict[str, Any],
        *,
        status: str = "checked",
        notes: str = "",
        channel_mapping: dict[str, Any] | list[dict[str, Any]] | None = None,
        action: str = "inspection_edit",
        expected_structure_fingerprint: str | None = None,
    ) -> dict[str, Any]:
        """Persist one auditable inspection revision and mark dependent results stale.

        The source FIF is never changed.  The returned revision/fingerprint can
        be frozen into an analysis run so later edits cannot be confused with
        the configuration that actually produced that run.
        """
        if status not in {"unchecked", "in_progress", "checked", "needs_review"}:
            raise ValueError(f"Unsupported inspection status: {status}")
        current = self.data_units(data_unit_ids=[data_unit_id])
        if len(current) != 1:
            raise KeyError(data_unit_id)
        row = current[0]
        stored_structure_fingerprint = str(row.get("source_structure_fingerprint") or "")
        if expected_structure_fingerprint and stored_structure_fingerprint and expected_structure_fingerprint != stored_structure_fingerprint:
            raise ValueError("The source channel/epoch structure changed; this inspection cannot be applied without review")
        mapping = channel_mapping if channel_mapping is not None else row.get("channel_mapping", {})
        normalized = json.loads(json.dumps(inspection, ensure_ascii=False, sort_keys=True, default=_json_default))
        selected_epochs = normalized.get("selected_epoch_indices")
        selected_time = inspection.get("time_selection")
        if selected_epochs is not None:
            selected_epochs = [int(value) for value in selected_epochs]
            if len(selected_epochs) != len(set(selected_epochs)) or any(value < 0 for value in selected_epochs):
                raise ValueError("Selected epoch indices must be unique non-negative original indices")
            n_epochs = row.get("source_structure", {}).get("n_epochs")
            if n_epochs is not None and selected_epochs and max(selected_epochs) >= int(n_epochs):
                raise ValueError(f"Inspection epoch index exceeds current source structure ({n_epochs} epochs)")
            normalized["selected_epoch_indices"] = selected_epochs
        known_channels = {str(value) for value in row.get("source_structure", {}).get("channel_names", [])}
        selected_channels = {str(value) for value in normalized.get("selected_channel_names", [])}
        if known_channels and not selected_channels.issubset(known_channels):
            unknown = sorted(selected_channels - known_channels)
            raise ValueError(f"Inspection references channels absent from the current source: {unknown}")
        now = utc_now()
        revision = int(row.get("inspection_revision") or 0) + 1
        inspection_fingerprint = _fingerprint_json(
            {"inspection": normalized, "mapping": mapping, "status": status, "notes": notes.strip()}
        )
        before = {
            "revision": int(row.get("inspection_revision") or 0),
            "fingerprint": row.get("inspection_fingerprint"),
            "status": row.get("inspection_status"),
            "inspection": row.get("inspection", {}),
            "channel_mapping": row.get("channel_mapping", {}),
            "epoch_selection": row.get("epoch_selection", {}),
            "time_selection": row.get("time_selection", {}),
            "notes": row.get("inspection_notes") or "",
        }
        after = {
            "revision": revision,
            "fingerprint": inspection_fingerprint,
            "status": status,
            "inspection": normalized,
            "channel_mapping": mapping,
            "epoch_selection": {"indices": list(selected_epochs)} if selected_epochs is not None else row.get("epoch_selection", {}),
            "time_selection": selected_time if selected_time is not None else row.get("time_selection", {}),
            "notes": notes.strip(),
        }
        scientific_changed = (
            mapping != row.get("channel_mapping", {})
            or (selected_epochs is not None and {"indices": list(selected_epochs)} != row.get("epoch_selection", {}))
            or (selected_time is not None and selected_time != row.get("time_selection", {}))
            or normalized != row.get("inspection", {})
        )
        with self.transaction() as connection:
            connection.execute(
                """UPDATE data_units SET channel_mapping_json=?,epoch_selection_json=?,time_selection_json=?,
                   inspection_status=?,inspection_json=?,inspection_notes=?,inspection_updated_at_utc=?,
                   validity_status=?,inspection_revision=?,inspection_fingerprint=?,inspection_save_status='saved'
                   WHERE data_unit_id=?""",
                (
                    _json(mapping),
                    _json({"indices": list(selected_epochs)} if selected_epochs is not None else row.get("epoch_selection", {})),
                    _json(selected_time if selected_time is not None else row.get("time_selection", {})),
                    status, _json(normalized), notes.strip() or None, now,
                    "ready" if status == "checked" else row.get("validity_status", "unchecked"),
                    revision, inspection_fingerprint, data_unit_id,
                ),
            )
            connection.execute(
                "INSERT INTO inspection_history VALUES(?,?,?,?,?,?,?)",
                (new_id("inspection"), data_unit_id, revision, action, _json(before), _json(after), now),
            )
            if scientific_changed:
                connection.execute(
                    "UPDATE analysis_runs SET result_validity='needs_recompute' WHERE data_unit_id=? AND active=1",
                    (data_unit_id,),
                )
        return {"revision": revision, "fingerprint": inspection_fingerprint, "scientific_changed": scientific_changed}

    def inspection_history(self, data_unit_id: str) -> list[dict[str, Any]]:
        rows = self.query(
            "SELECT * FROM inspection_history WHERE data_unit_id=? ORDER BY revision,created_at_utc",
            (data_unit_id,),
        )
        for row in rows:
            row["before"] = _loads(row.pop("before_json"), {})
            row["after"] = _loads(row.pop("after_json"), {})
        return rows

    def register_analysis(self, record: dict[str, Any]) -> None:
        fields = (
            "analysis_id", "data_unit_id", "module_name", "method_name", "result_path", "schema_version",
            "parameter_fingerprint", "data_fingerprint", "parameters_json", "calculation_status", "save_status",
            "review_status", "review_notes", "created_at_utc", "completed_at_utc", "active", "warnings_json", "error_message",
            "result_validity", "inspection_revision", "inspection_fingerprint",
        )
        defaults = {"result_validity": "current", "inspection_revision": 0}
        requested_active = bool(int(record.get("active", 1)))
        activate = bool(
            requested_active
            and record.get("calculation_status") == "completed"
            and record.get("save_status") == "saved"
            and record.get("result_validity", "current") == "current"
        )
        normalized = {**record, "active": int(activate)}
        values = [normalized.get(field, defaults.get(field)) for field in fields]
        with self.transaction() as connection:
            if activate:
                connection.execute("UPDATE analysis_runs SET active=0 WHERE data_unit_id=? AND module_name=?", (record["data_unit_id"], record["module_name"]))
            connection.execute(
                f"INSERT INTO analysis_runs({','.join(fields)}) VALUES({','.join('?' for _ in fields)})",
                values,
            )

    def create_batch_job(self, name: str, modules: list[str], task_config: dict[str, Any], data_unit_ids: list[str], effective_parameters: dict[str, dict[str, Any]]) -> str:
        batch_job_id = new_id("batch")
        with self.transaction() as connection:
            connection.execute(
                "INSERT INTO batch_jobs VALUES(?,?,?,?,?,?,?,?,?)",
                (batch_job_id, name, "queued", _json(modules), _json(task_config), utc_now(), None, None, 0),
            )
            for data_unit_id in data_unit_ids:
                connection.execute(
                    "INSERT INTO batch_items VALUES(?,?,?,?,?,?,?,?)",
                    (new_id("item"), batch_job_id, data_unit_id, "queued", _json(effective_parameters[data_unit_id]), None, None, None),
                )
        return batch_job_id

    def set_batch_job_status(self, batch_job_id: str, status: str, *, started: bool = False, finished: bool = False) -> None:
        updates = ["status=?"]
        parameters: list[Any] = [status]
        if started:
            updates.append("started_at_utc=?")
            parameters.append(utc_now())
        if finished:
            updates.append("finished_at_utc=?")
            parameters.append(utc_now())
        parameters.append(batch_job_id)
        with self.transaction() as connection:
            connection.execute(f"UPDATE batch_jobs SET {','.join(updates)} WHERE batch_job_id=?", parameters)

    def set_batch_item_status(self, batch_job_id: str, data_unit_id: str, status: str, *, error_message: str = "", started: bool = False, finished: bool = False) -> None:
        updates = ["status=?", "error_message=?"]
        parameters: list[Any] = [status, error_message or None]
        if started:
            updates.append("started_at_utc=?")
            parameters.append(utc_now())
        if finished:
            updates.append("finished_at_utc=?")
            parameters.append(utc_now())
        parameters.extend([batch_job_id, data_unit_id])
        with self.transaction() as connection:
            connection.execute(f"UPDATE batch_items SET {','.join(updates)} WHERE batch_job_id=? AND data_unit_id=?", parameters)

    def request_batch_cancel(self, batch_job_id: str) -> None:
        with self.transaction() as connection:
            connection.execute("UPDATE batch_jobs SET cancellation_requested=1 WHERE batch_job_id=?", (batch_job_id,))

    def batch_cancel_requested(self, batch_job_id: str) -> bool:
        rows = self.query("SELECT cancellation_requested FROM batch_jobs WHERE batch_job_id=?", (batch_job_id,))
        return bool(rows and rows[0]["cancellation_requested"])

    def prepare_batch_resume(self, batch_job_id: str) -> None:
        """Queue unfinished items while preserving completed/reused outputs."""
        with self.transaction() as connection:
            connection.execute(
                "UPDATE batch_jobs SET status='queued',cancellation_requested=0,finished_at_utc=NULL WHERE batch_job_id=?",
                (batch_job_id,),
            )
            connection.execute(
                """UPDATE batch_items SET status='queued',error_message=NULL,started_at_utc=NULL,finished_at_utc=NULL
                   WHERE batch_job_id=? AND status NOT IN ('completed','reused')""",
                (batch_job_id,),
            )

    def batch_jobs(self) -> list[dict[str, Any]]:
        jobs = self.query("SELECT * FROM batch_jobs ORDER BY created_at_utc DESC")
        for job in jobs:
            job["modules"] = _loads(job.pop("modules_json"), [])
            job["task_config"] = _loads(job.pop("task_config_json"), {})
            job["items"] = self.query("SELECT * FROM batch_items WHERE batch_job_id=? ORDER BY started_at_utc,data_unit_id", (job["batch_job_id"],))
        return jobs

    def analysis_results(self, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        filters = filters or {}
        sql = """
            SELECT a.*,d.state_record_id,d.source_path,d.signal_unit,r.display_name AS state_display_name,
                   r.condition_label,r.timepoint_value,r.timepoint_unit,r.reference_event,
                   s.session_id,s.session_key,s.experiment_name,s.session_date,u.subject_id,u.subject_code,u.group_label
            FROM analysis_runs a JOIN data_units d ON d.data_unit_id=a.data_unit_id
            JOIN state_records r ON r.state_record_id=d.state_record_id
            JOIN sessions s ON s.session_id=r.session_id JOIN subjects u ON u.subject_id=s.subject_id
        """
        clauses: list[str] = []
        parameters: list[Any] = []
        mapping = {
            "data_unit_id": "a.data_unit_id", "analysis_id": "a.analysis_id",
            "subject_id": "u.subject_id", "subject_code": "u.subject_code", "group_label": "u.group_label",
            "session_id": "s.session_id", "session_key": "s.session_key", "condition_label": "r.condition_label",
            "timepoint_value": "r.timepoint_value", "module_name": "a.module_name", "review_status": "a.review_status",
            "calculation_status": "a.calculation_status", "save_status": "a.save_status", "active": "a.active",
            "result_validity": "a.result_validity",
        }
        for key, column in mapping.items():
            if key in filters and filters[key] not in (None, ""):
                clauses.append(f"{column}=?")
                parameters.append(filters[key])
        if filters.get("timepoint_min") not in (None, ""):
            clauses.append("r.timepoint_value>=?")
            parameters.append(filters["timepoint_min"])
        if filters.get("timepoint_max") not in (None, ""):
            clauses.append("r.timepoint_value<=?")
            parameters.append(filters["timepoint_max"])
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY u.subject_code,s.session_key,r.timepoint_value,a.created_at_utc DESC"
        rows = self.query(sql, parameters)
        for row in rows:
            row["parameters"] = _loads(row.pop("parameters_json"), {})
            row["warnings"] = _loads(row.pop("warnings_json"), [])
        return rows

    def latest_analysis(
        self,
        data_unit_id: str,
        module_name: str,
        *,
        successful: bool = False,
        compatible: bool = False,
    ) -> dict[str, Any] | None:
        """Return the newest run, or newest saved/current successful run."""
        filters: dict[str, Any] = {"data_unit_id": data_unit_id, "module_name": module_name}
        if successful:
            filters.update({"calculation_status": "completed", "save_status": "saved"})
        if compatible:
            filters["result_validity"] = "current"
        rows = self.analysis_results(filters)
        return rows[0] if rows else None

    def set_review(self, analysis_id: str, review_status: str, notes: str = "") -> None:
        if review_status not in {"pending", "approved", "excluded"}:
            raise ValueError(f"Unsupported review status: {review_status}")
        with self.transaction() as connection:
            connection.execute("UPDATE analysis_runs SET review_status=?,review_notes=? WHERE analysis_id=?", (review_status, notes, analysis_id))

    def relocate_source(self, data_unit_id: str, new_path: str | Path) -> None:
        source = Path(new_path).expanduser().resolve()
        fingerprint = file_fingerprint(source)
        current = self.query("SELECT source_sha256,source_size_bytes FROM data_units WHERE data_unit_id=?", (data_unit_id,))
        if not current:
            raise KeyError(data_unit_id)
        if current[0]["source_sha256"] != fingerprint["sha256"] or int(current[0]["source_size_bytes"]) != fingerprint["size_bytes"]:
            raise ValueError("Relocated source does not match the registered content fingerprint")
        with self.transaction() as connection:
            connection.execute(
                "UPDATE data_units SET source_path=?,source_path_kind='external',original_source_path=? WHERE data_unit_id=?",
                (str(source), str(source), data_unit_id),
            )

    def update_data_unit_mapping(self, data_unit_id: str, channel_mapping: dict[str, Any] | list[dict[str, Any]], *, validity_status: str = "ready", validity_message: str = "") -> None:
        with self.transaction() as connection:
            connection.execute(
                "UPDATE data_units SET channel_mapping_json=?,validity_status=?,validity_message=? WHERE data_unit_id=?",
                (_json(channel_mapping), validity_status, validity_message or None, data_unit_id),
            )
            connection.execute(
                "UPDATE analysis_runs SET result_validity='needs_recompute' WHERE data_unit_id=? AND active=1",
                (data_unit_id,),
            )

    def update_data_unit_override(self, data_unit_id: str, analysis_override: dict[str, Any]) -> None:
        with self.transaction() as connection:
            connection.execute("UPDATE data_units SET analysis_override_json=? WHERE data_unit_id=?", (_json(analysis_override), data_unit_id))
            connection.execute(
                "UPDATE analysis_runs SET result_validity='needs_recompute' WHERE data_unit_id=? AND active=1",
                (data_unit_id,),
            )

    def source_status(self, data_unit_id: str) -> dict[str, Any]:
        rows = self.query("SELECT source_path,source_path_kind,source_sha256,source_size_bytes FROM data_units WHERE data_unit_id=?", (data_unit_id,))
        if not rows:
            raise KeyError(data_unit_id)
        record = rows[0]
        source = self.resolve_source_path(record)
        if not source.is_file():
            return {"status": "missing", "path": str(source)}
        fingerprint = file_fingerprint(source)
        matches = fingerprint["sha256"] == record["source_sha256"] and fingerprint["size_bytes"] == int(record["source_size_bytes"])
        return {"status": "ok" if matches else "changed", "path": str(source), **fingerprint}

    def create_comparison_snapshot(self, name: str, filters: dict[str, Any], included: list[dict[str, Any]], excluded: list[dict[str, Any]], settings: dict[str, Any]) -> str:
        comparison_id = new_id("comparison")
        payload = {
            "schema_version": 1,
            "comparison_id": comparison_id,
            "project_id": self.project["project_id"],
            "name": name,
            "filters": filters,
            "included": included,
            "excluded": excluded,
            "settings": settings,
            "created_at_utc": utc_now(),
        }
        target = self.paths.snapshots / f"{comparison_id}.json"
        temporary = target.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")
        os.replace(temporary, target)
        with self.transaction() as connection:
            connection.execute(
                "INSERT INTO comparison_snapshots VALUES(?,?,?,?,?,?,?,?)",
                (comparison_id, name, _json(filters), _json(included), _json(excluded), _json(settings), payload["created_at_utc"], str(target.relative_to(self.paths.root))),
            )
        return comparison_id

    def load_comparison_snapshot(self, comparison_id: str) -> dict[str, Any]:
        rows = self.query("SELECT snapshot_path FROM comparison_snapshots WHERE comparison_id=?", (comparison_id,))
        if not rows:
            raise KeyError(comparison_id)
        path = (self.paths.root / rows[0]["snapshot_path"]).resolve()
        path.relative_to(self.paths.root)
        return json.loads(path.read_text(encoding="utf-8"))

    def comparison_snapshots(self) -> list[dict[str, Any]]:
        rows = self.query("SELECT * FROM comparison_snapshots ORDER BY created_at_utc DESC")
        for row in rows:
            row["filters"] = _loads(row.pop("filters_json"), {})
            row["included"] = _loads(row.pop("included_json"), [])
            row["excluded"] = _loads(row.pop("excluded_json"), [])
            row["settings"] = _loads(row.pop("settings_json"), {})
        return rows
