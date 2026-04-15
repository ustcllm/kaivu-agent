from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .models import (
    ExperimentRun,
    ExperimentSpecification,
    ExperimentalProtocol,
    InterpretationRecord,
    ObservationRecord,
    QualityControlReview,
    ResearchAssetRecord,
)


class ExperimentRegistry:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def save_experiment_specification(self, item: ExperimentSpecification) -> Path:
        return self._save("experiment_specifications", item.experiment_id, asdict(item))

    def save_experimental_protocol(self, item: ExperimentalProtocol) -> Path:
        return self._save("experimental_protocols", item.protocol_id, asdict(item))

    def save_experiment_run(self, item: ExperimentRun) -> Path:
        return self._save("experiment_runs", item.run_id, asdict(item))

    def save_observation_record(self, item: ObservationRecord) -> Path:
        return self._save("observation_records", item.observation_id, asdict(item))

    def save_quality_control_review(self, item: QualityControlReview) -> Path:
        return self._save("quality_control_reviews", item.review_id, asdict(item))

    def save_interpretation_record(self, item: InterpretationRecord) -> Path:
        return self._save("interpretation_records", item.interpretation_id, asdict(item))

    def save_research_asset_record(self, item: ResearchAssetRecord) -> Path:
        return self._save("research_assets", item.asset_id, asdict(item))

    def load_collection(self, collection: str) -> list[dict[str, Any]]:
        directory = self.root / collection
        if not directory.exists():
            return []
        items: list[dict[str, Any]] = []
        for path in sorted(directory.glob("*.json")):
            try:
                items.append(json.loads(path.read_text(encoding="utf-8")))
            except Exception:
                continue
        return items

    def get_record(self, collection: str, identifier: str) -> dict[str, Any] | None:
        target = self.root / collection / f"{self._slugify(identifier)}.json"
        if not target.exists():
            return None
        try:
            payload = json.loads(target.read_text(encoding="utf-8"))
        except Exception:
            return None
        return payload if isinstance(payload, dict) else None

    def save_record(self, collection: str, identifier: str, payload: dict[str, Any]) -> Path:
        return self._save(collection, identifier, payload)

    def _save(self, collection: str, identifier: str, payload: dict[str, Any]) -> Path:
        directory = self.root / collection
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f"{self._slugify(identifier)}.json"
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return target

    @staticmethod
    def _slugify(value: str) -> str:
        safe = "".join(ch.lower() if ch.isalnum() else "-" for ch in value.strip())
        while "--" in safe:
            safe = safe.replace("--", "-")
        slug = safe.strip("-") or "record"
        if len(slug) <= 140:
            return slug
        digest = hashlib.sha1(str(value).encode("utf-8")).hexdigest()[:12]
        return f"{slug[:127].rstrip('-')}-{digest}"


