from __future__ import annotations

import argparse
import json
from pathlib import Path

from .app_info import APP_FULL_NAME, APP_NAME
from .pipeline import run_batch, run_single_file
from .resources import packaged_resource_path
from .synthetic import validate_synthetic


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=f"{APP_NAME} — {APP_FULL_NAME}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    single = subparsers.add_parser("single-file", help="run file-level FIF QC, PSD and band power")
    single.add_argument("--input", required=True, type=Path)
    single.add_argument("--config", default=packaged_resource_path("configs/luna.yaml"), type=Path)
    single.add_argument("--output", required=True, type=Path)
    single.add_argument("--metadata-dir", default=Path("metadata"), type=Path)

    batch = subparsers.add_parser("batch", help="run registered files one by one")
    batch.add_argument("--files", default=Path("metadata/files.csv"), type=Path)
    batch.add_argument("--config", default=packaged_resource_path("configs/luna.yaml"), type=Path)
    batch.add_argument("--output", required=True, type=Path)
    batch.add_argument("--metadata-dir", default=Path("metadata"), type=Path)

    synthetic = subparsers.add_parser("validate-synthetic", help="run explicitly synthetic algorithm checks")
    synthetic.add_argument("--output", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "single-file":
        manifest = run_single_file(args.input, args.config, args.output, args.metadata_dir)
        print(json.dumps(manifest, ensure_ascii=False, indent=2, default=str))
        return 0
    if args.command == "batch":
        manifest = run_batch(args.files, args.config, args.output, args.metadata_dir)
        print(manifest.to_string(index=False))
        return 0 if not manifest.empty and not (manifest["status"] == "failed").any() else 1
    result = validate_synthetic(args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
