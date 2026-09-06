import pandas as pd

from lfp_analysis.metadata import merge_behavior_at_node, validate_metadata_tables


def test_metadata_validation_finds_duplicate_file_paths_and_unmatched_behavior():
    tables = {
        "animals": pd.DataFrame({"animal_id": ["A01"], "group": ["LID"]}),
        "records": pd.DataFrame({"session_id": ["S01"], "animal_id": ["A01"]}),
        "files": pd.DataFrame(
            {
                "file_id": ["F01", "F02"],
                "session_id": ["S01", "S01"],
                "animal_id": ["A01", "A01"],
                "file_path": ["same.fif", "same.fif"],
            }
        ),
        "epochs": pd.DataFrame(),
        "behavior": pd.DataFrame({"animal_id": ["A01"], "session_id": ["S01"], "nominal_dose_time_min": [80]}),
        "channel_map": pd.DataFrame(),
    }
    issues = validate_metadata_tables(tables)
    assert (issues["code"] == "duplicate_file_path").any()


def test_behavior_merge_is_node_level():
    metrics = pd.DataFrame({"animal_id": ["A01"], "session_id": ["S01"], "nominal_dose_time_min": [80], "metric": [1.2]})
    behavior = pd.DataFrame({"animal_id": ["A01"], "session_id": ["S01"], "nominal_dose_time_min": [80], "aims_total": [4]})
    merged, unmatched = merge_behavior_at_node(metrics, behavior)
    assert merged["aims_total"].iloc[0] == 4
    assert unmatched.empty

