import json


payload = {
    "experiment_run": {
        "run_id": "run::semantic-real-executor",
        "experiment_id": "exp::semantic-real-executor",
        "status": "completed",
        "operator": "local-python-fixture",
        "approval_status": "approved",
        "configuration_snapshot": {"seed": 7, "parameter": 0.42},
        "environment_snapshot": {"fixture": True},
    },
    "observation_records": [
        {
            "observation_id": "obs::semantic-real-executor::1",
            "observation_type": "metric",
            "summary": "Observed target metric decreased relative to prediction.",
            "raw_values": {"metric": 0.12, "baseline": 0.31},
        }
    ],
    "quality_control_review": {
        "review_id": "qc::semantic-real-executor",
        "quality_control_status": "passed",
        "quality_control_checks_run": [
            "protocol_version_recorded",
            "success_failure_criteria_recorded",
            "artifact_provenance_recorded",
        ],
        "evidence_reliability": "medium",
        "usable_for_interpretation": True,
    },
    "interpretation_record": {
        "interpretation_id": "interp::semantic-real-executor",
        "negative_result": True,
        "weakened_hypothesis_ids": ["hypothesis::semantic-target"],
        "confidence": "medium",
        "next_decision": "revise mechanism and schedule discriminating follow-up",
    },
    "research_asset_records": [
        {
            "asset_id": "asset::semantic-real-executor::metrics",
            "asset_type": "metrics",
            "label": "semantic executor metrics",
            "path_or_reference": "executor://semantic-real-executor/metrics.json",
            "role": "run_output",
            "experiment_id": "exp::semantic-real-executor",
            "run_id": "run::semantic-real-executor",
            "governance_status": "fixture",
            "is_frozen": True,
        }
    ],
}

if __name__ == "__main__":
    print(json.dumps(payload))
