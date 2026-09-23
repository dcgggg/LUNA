"""List or export saved LUNA project results without starting the GUI."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from lfp_analysis.results_api import ProjectResults


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", help="LUNA project directory")
    parser.add_argument("--subject")
    parser.add_argument("--session-key")
    parser.add_argument("--session-id")
    parser.add_argument("--condition")
    parser.add_argument("--timepoint", type=float)
    parser.add_argument("--timepoint-min", type=float)
    parser.add_argument("--timepoint-max", type=float)
    parser.add_argument("--module")
    parser.add_argument("--review-status", choices=["pending", "approved", "excluded"])
    parser.add_argument("--analysis-id", action="append", default=[])
    parser.add_argument("--table", help="Table name to export as a long CSV")
    parser.add_argument("--output", help="CSV output path")
    args = parser.parse_args()
    reader = ProjectResults(args.project)
    filters = {
        "subject_code": args.subject,
        "session_key": args.session_key,
        "session_id": args.session_id,
        "condition_label": args.condition,
        "timepoint_value": args.timepoint,
        "timepoint_min": args.timepoint_min,
        "timepoint_max": args.timepoint_max,
        "module_name": args.module,
        "review_status": args.review_status,
    }
    results = reader.list(**{key: value for key, value in filters.items() if value not in (None, "")})
    if args.analysis_id and args.table and args.output:
        target = reader.export_long_table(args.analysis_id, args.table, args.output)
        print(target)
    else:
        columns = [column for column in ("subject_code", "group_label", "session_key", "condition_label", "timepoint_value", "module_name", "analysis_id", "review_status", "result_path") if column in results]
        print(results[columns].to_string(index=False) if not results.empty else "No matching saved results")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
