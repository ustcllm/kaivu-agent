from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path


def main() -> None:
    now = datetime.now(timezone.utc).isoformat()
    output_path = Path("demo_data/local_python_executor_metrics.json").resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    metrics = {
        "accuracy": 0.87,
        "loss": 0.31,
        "seed": 13,
        "note": "demo local-python executor output",
    }
    output_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    run_id = "run::local-python::demo"
    payload = {
        "experiment_run": {
            "run_id": run_id,
            "experiment_id": "experiment::local-python-demo",
            "protocol_id": "protocol::local-python-demo",
            "status": "completed",
            "operator": "demo_data/local_python_executor_demo.py",
            "started_at": now,
            "ended_at": now,
            "approval_status": "approved",
            "configuration_snapshot": {"script": "demo_data/local_python_executor_demo.py"},
            "environment_snapshot": {"runtime": "python"},
        },
        "observation_records": [
            {
                "observation_id": "observation::local-python-demo::metrics",
                "observation_type": "metrics",
                "raw_values": metrics,
                "summary": "Local Python demo produced metrics JSON.",
                "files": [str(output_path)],
                "timestamp": now,
            }
        ],
        "quality_control_review": {
            "review_id": "qc::local-python-demo",
            "quality_control_status": "passed",
            "quality_control_checks_run": ["protocol_version_recorded", "artifact_provenance_recorded"],
            "evidence_reliability": "medium",
            "usable_for_interpretation": True,
            "recommended_action": "use as executor interface smoke test",
        },
        "interpretation_record": {
            "interpretation_id": "interpretation::local-python-demo",
            "negative_result": False,
            "confidence": "medium",
            "next_decision": "executor interface is ready for stricter adapters",
        },
        "research_asset_records": [
            {
                "asset_id": "asset::local-python-demo::metrics",
                "asset_type": "metrics",
                "label": "local python demo metrics",
                "path_or_reference": str(output_path),
                "role": "executor_output",
                "experiment_id": "experiment::local-python-demo",
                "run_id": run_id,
                "governance_status": "demo",
                "is_frozen": True,
            }
        ],
    }
    print(json.dumps({"handoff_payload": payload}, ensure_ascii=False))


if __name__ == "__main__":
    main()


