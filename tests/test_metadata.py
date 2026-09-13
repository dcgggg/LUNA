import pandas as pd

from lfp_analysis.behavior import node_level_behavior_status
from lfp_analysis.metadata import merge_behavior_at_node, validate_metadata_tables
from lfp_analysis.stats import animal_level_descriptive, paired_pre_post


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


def test_behavior_status_merges_by_node_key_when_rows_are_shuffled():
    behavior = pd.DataFrame(
        {
            "animal_id": ["A2", "A1", "A1"],
            "session_id": ["S2", "S1", "S1"],
            "nominal_dose_time_min": [80, 40, 80],
            "aims_total": [3, None, 5],
        }
    )
    result = node_level_behavior_status(behavior).set_index(["animal_id", "session_id", "nominal_dose_time_min"])
    assert bool(result.loc[("A1", "S1", 40), "has_any_aims_score"]) is False
    assert bool(result.loc[("A1", "S1", 80), "has_any_aims_score"]) is True
    assert bool(result.loc[("A2", "S2", 80), "has_any_aims_score"]) is True


def test_animal_descriptive_gives_each_animal_equal_weight_across_nodes():
    nodes = pd.DataFrame(
        {
            "animal_id": ["A1", "A1", "A1", "A2"],
            "group": ["LID"] * 4,
            "value": [0.0, 0.0, 0.0, 10.0],
        }
    )
    result = animal_level_descriptive(nodes, "value", ["group"])
    assert result.loc[0, "mean"] == 5.0
    assert result.loc[0, "n_animals"] == 2


def test_paired_pre_post_requires_explicit_day_and_session_and_rejects_duplicates():
    incomplete = pd.DataFrame({"animal_id": ["A1"], "ldn_status": ["pre"], "nominal_dose_time_min": [80], "value": [1.0]})
    assert paired_pre_post(incomplete, "value").loc[0, "status"] == "not_run_missing_record_day"
    complete = pd.DataFrame(
        {
            "animal_id": ["A1", "A1"],
            "session_id": ["S1", "S1"],
            "l_dopa_day": [10, 10],
            "nominal_dose_time_min": [80, 80],
            "ldn_status": ["pre", "post"],
            "value": [1.0, 2.0],
        }
    )
    result = paired_pre_post(complete, "value")
    assert result.loc[0, "difference"] == 1.0
