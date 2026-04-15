from __future__ import annotations

import csv
import hashlib
from pathlib import Path
from typing import Any

from .models import DataInventory


SUPPORTED_DATA_SUFFIXES = {".csv", ".tsv", ".parquet", ".json", ".jsonl"}


def scan_kaggle_data_dir(data_dir: str | Path) -> DataInventory:
    root = Path(data_dir).resolve()
    warnings: list[str] = []
    if not root.exists():
        return DataInventory(data_dir=str(root), inventory_state="missing", warnings=["data_dir does not exist"])
    files = [_summarize_file(path, root) for path in sorted(root.rglob("*")) if path.is_file() and path.suffix.lower() in SUPPORTED_DATA_SUFFIXES]
    train_file = _detect_file(files, ["train"])
    test_file = _detect_file(files, ["test"])
    sample_submission = _detect_file(files, ["sample_submission", "submission"])
    target = _infer_target_column(files, train_file=train_file, test_file=test_file, sample_submission=sample_submission)
    identifier = _infer_id_column(files, sample_submission=sample_submission)
    task_type = _infer_task_type(files, train_file=train_file, target_column=target)
    if not train_file:
        warnings.append("Could not detect train file")
    if not test_file:
        warnings.append("Could not detect test file")
    if not sample_submission:
        warnings.append("Could not detect sample submission file")
    return DataInventory(
        data_dir=str(root),
        files=files,
        detected_train_file=train_file,
        detected_test_file=test_file,
        detected_sample_submission=sample_submission,
        inferred_target_column=target,
        inferred_id_column=identifier,
        inferred_task_type=task_type,
        inventory_state="scanned",
        warnings=warnings,
    )


def _summarize_file(path: Path, root: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    summary: dict[str, Any] = {
        "path": str(path),
        "relative_path": path.relative_to(root).as_posix(),
        "name": path.name,
        "suffix": suffix,
        "size_bytes": path.stat().st_size,
        "sha256_12": _sha256_12(path),
        "rows": None,
        "columns": [],
        "column_count": None,
    }
    if suffix in {".csv", ".tsv"}:
        delimiter = "\t" if suffix == ".tsv" else ","
        try:
            with path.open("r", encoding="utf-8", newline="") as handle:
                reader = csv.reader(handle, delimiter=delimiter)
                header = next(reader, [])
                row_count = sum(1 for _ in reader)
            summary["rows"] = row_count
            summary["columns"] = [str(item) for item in header]
            summary["column_count"] = len(header)
        except UnicodeDecodeError:
            with path.open("r", encoding="latin-1", newline="") as handle:
                reader = csv.reader(handle, delimiter=delimiter)
                header = next(reader, [])
                row_count = sum(1 for _ in reader)
            summary["rows"] = row_count
            summary["columns"] = [str(item) for item in header]
            summary["column_count"] = len(header)
        except Exception as exc:
            summary["read_error"] = str(exc)
    return summary


def _detect_file(files: list[dict[str, Any]], tokens: list[str]) -> str:
    for item in files:
        name = str(item.get("name", "")).lower()
        stem = Path(name).stem.lower()
        if any(token in stem for token in tokens):
            return str(item.get("path", ""))
    return ""


def _infer_target_column(files: list[dict[str, Any]], *, train_file: str, test_file: str, sample_submission: str) -> str:
    train = _file_by_path(files, train_file)
    test = _file_by_path(files, test_file)
    sample = _file_by_path(files, sample_submission)
    train_cols = set(_columns(train))
    test_cols = set(_columns(test))
    diff = [column for column in _columns(train) if column in train_cols - test_cols]
    if len(diff) == 1:
        return diff[0]
    sample_cols = _columns(sample)
    if len(sample_cols) >= 2:
        return sample_cols[1]
    for candidate in ["target", "label", "y", "Survived", "class"]:
        for column in _columns(train):
            if column.lower() == candidate.lower():
                return column
    return ""


def _infer_id_column(files: list[dict[str, Any]], *, sample_submission: str) -> str:
    sample = _file_by_path(files, sample_submission)
    sample_cols = _columns(sample)
    if sample_cols:
        return sample_cols[0]
    for item in files:
        for column in _columns(item):
            lowered = column.lower()
            if lowered == "id" or lowered.endswith("id") or "id_" in lowered:
                return column
    return ""


def _infer_task_type(files: list[dict[str, Any]], *, train_file: str, target_column: str) -> str:
    if not target_column:
        return "unspecified"
    train = _file_by_path(files, train_file)
    path = Path(str(train.get("path", "")))
    if not path.exists() or path.suffix.lower() not in {".csv", ".tsv"}:
        return "tabular_supervised"
    delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, delimiter=delimiter)
            values = [row.get(target_column, "") for _, row in zip(range(500), reader)]
    except Exception:
        return "tabular_supervised"
    unique = {value for value in values if value != ""}
    if 1 < len(unique) <= 20:
        return "tabular_classification"
    return "tabular_regression"


def _file_by_path(files: list[dict[str, Any]], path: str) -> dict[str, Any]:
    for item in files:
        if str(item.get("path", "")) == path:
            return item
    return {}


def _columns(item: dict[str, Any]) -> list[str]:
    value = item.get("columns", [])
    return [str(column) for column in value] if isinstance(value, list) else []


def _sha256_12(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()[:12]


