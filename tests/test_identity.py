from pathlib import Path

import pandas as pd

from lfp_analysis.identity import resolve_registry_match, stable_file_uid


def test_exact_path_match_wins_over_same_basename(tmp_path: Path):
    first = tmp_path / "one" / "sample.fif"
    second = tmp_path / "two" / "sample.fif"
    files = pd.DataFrame(
        {
            "file_id": ["one_sample", "two_sample"],
            "file_path": [str(first), str(second)],
            "animal_id": ["A1", "A2"],
        }
    )

    match = resolve_registry_match(files, second, tmp_path / "metadata")

    assert match["status"] == "exact_unique"
    assert match["registry_file_id"] == "two_sample"
    assert match["registry_row"]["animal_id"] == "A2"


def test_ambiguous_basename_does_not_attach_registry_row(tmp_path: Path):
    files = pd.DataFrame(
        {
            "file_id": ["first", "second"],
            "file_path": ["records/first/sample.fif", "records/second/sample.fif"],
            "animal_id": ["A1", "A2"],
        }
    )

    match = resolve_registry_match(files, tmp_path / "unlisted" / "sample.fif", tmp_path / "metadata")

    assert match["status"] == "basename_conflict"
    assert match["registry_row"] is None
    assert match["candidate_file_ids"] == ["first", "second"]


def test_stable_file_uid_changes_for_path_or_content(tmp_path: Path):
    first = tmp_path / "one" / "sample.fif"
    second = tmp_path / "two" / "sample.fif"

    assert stable_file_uid(first, "abc") != stable_file_uid(second, "abc")
    assert stable_file_uid(first, "abc") != stable_file_uid(first, "def")
    assert stable_file_uid(first, "abc") == stable_file_uid(first, "abc")
