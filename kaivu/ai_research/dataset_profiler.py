from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path
from typing import Any


def build_dataset_profile(
    *,
    dataset_path: str | None,
    target_column: str = "",
    id_column: str = "",
    sample_rows: int = 1000,
) -> dict[str, Any]:
    if not dataset_path:
        return {
            "profile_state": "missing_dataset",
            "path": "",
            "row_count_sampled": 0,
            "column_count": 0,
            "columns": [],
            "warnings": ["dataset_path not provided; profile is planning-only"],
        }
    path = Path(dataset_path).resolve()
    if not path.exists():
        return {
            "profile_state": "dataset_not_found",
            "path": str(path),
            "row_count_sampled": 0,
            "column_count": 0,
            "columns": [],
            "warnings": [f"dataset not found: {path}"],
        }
    if path.suffix.lower() != ".csv":
        return {
            "profile_state": "unsupported_format",
            "path": str(path),
            "row_count_sampled": 0,
            "column_count": 0,
            "columns": [],
            "warnings": ["first MVP supports CSV profiling only"],
        }

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = [str(name) for name in (reader.fieldnames or [])]
        stats = {
            name: {
                "non_null": 0,
                "missing": 0,
                "unique_sample": set(),
                "numeric_count": 0,
                "examples": [],
            }
            for name in fieldnames
        }
        row_count = 0
        duplicate_ids = 0
        id_seen: set[str] = set()
        for row in reader:
            row_count += 1
            if row_count > sample_rows:
                break
            if id_column and id_column in row:
                value = str(row.get(id_column, "")).strip()
                if value in id_seen:
                    duplicate_ids += 1
                if value:
                    id_seen.add(value)
            for name in fieldnames:
                value = str(row.get(name, "")).strip()
                item = stats[name]
                if value == "":
                    item["missing"] += 1
                    continue
                item["non_null"] += 1
                if len(item["examples"]) < 3:
                    item["examples"].append(value[:80])
                if len(item["unique_sample"]) < 2000:
                    item["unique_sample"].add(value)
                try:
                    float(value)
                    item["numeric_count"] += 1
                except Exception:
                    pass

    columns: list[dict[str, Any]] = []
    type_counts: Counter[str] = Counter()
    for name, item in stats.items():
        observed = int(item["non_null"]) + int(item["missing"])
        unique_count = len(item["unique_sample"])
        inferred_type = "numeric" if item["numeric_count"] >= max(1, int(item["non_null"]) * 0.8) else "categorical_or_text"
        if unique_count > max(20, observed * 0.5):
            inferred_type = "high_cardinality_" + inferred_type
        if name == target_column:
            inferred_type = "target"
        if name == id_column:
            inferred_type = "identifier"
        type_counts[inferred_type] += 1
        columns.append(
            {
                "name": name,
                "inferred_type": inferred_type,
                "missing_count_sample": int(item["missing"]),
                "non_null_count_sample": int(item["non_null"]),
                "unique_count_sample": unique_count,
                "examples": item["examples"],
            }
        )

    warnings: list[str] = []
    if target_column and target_column not in fieldnames:
        warnings.append(f"target_column not found: {target_column}")
    if id_column and id_column not in fieldnames:
        warnings.append(f"id_column not found: {id_column}")
    if duplicate_ids:
        warnings.append(f"duplicate id values found in sample: {duplicate_ids}")
    high_missing = [item["name"] for item in columns if item["missing_count_sample"] > max(10, row_count * 0.2)]
    if high_missing:
        warnings.append("columns with high missingness: " + ", ".join(high_missing[:10]))

    return {
        "profile_state": "profiled",
        "path": str(path),
        "row_count_sampled": row_count,
        "column_count": len(fieldnames),
        "target_column": target_column,
        "id_column": id_column,
        "column_type_counts": dict(type_counts),
        "columns": columns,
        "warnings": warnings,
    }
