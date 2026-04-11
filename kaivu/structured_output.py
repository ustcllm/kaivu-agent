from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class StructuredSchema:
    name: str
    description: str
    schema: dict[str, Any]


def schema_instruction(schema: StructuredSchema) -> str:
    return (
        f"Return valid JSON only. Do not wrap it in markdown fences.\n"
        f"Schema name: {schema.name}\n"
        f"Schema description: {schema.description}\n"
        f"JSON schema:\n{json.dumps(schema.schema, ensure_ascii=False, indent=2)}"
    )


def repair_instruction(schema: StructuredSchema, raw_text: str, error_message: str) -> str:
    return (
        "The previous answer did not satisfy the required JSON schema.\n"
        "Rewrite it as valid JSON only. Do not add commentary, markdown fences, or explanations.\n"
        f"Validation error: {error_message}\n\n"
        f"Original answer:\n{raw_text}\n\n"
        f"Required schema:\n{json.dumps(schema.schema, ensure_ascii=False, indent=2)}"
    )


def parse_structured_output(text: str, schema: StructuredSchema) -> dict[str, Any]:
    candidate = _extract_json_object(text)
    data = json.loads(candidate)
    _validate_schema(data, schema.schema, path="$")
    return data


def salvage_structured_output(text: str, schema: StructuredSchema) -> dict[str, Any]:
    candidate = _extract_json_object(text)
    data = json.loads(candidate)
    repaired = _coerce_to_schema(data, schema.schema)
    _validate_schema(repaired, schema.schema, path="$")
    return repaired


def _extract_json_object(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 3:
            stripped = "\n".join(lines[1:-1]).strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in model output")
    return stripped[start : end + 1]


def _validate_schema(value: Any, schema: dict[str, Any], *, path: str) -> None:
    expected = schema.get("type")
    if expected == "object":
        if not isinstance(value, dict):
            raise ValueError(f"{path} must be an object")
        required = schema.get("required", [])
        for key in required:
            if key not in value:
                raise ValueError(f"{path}.{key} is required")
        properties = schema.get("properties", {})
        for key, item in value.items():
            if key in properties:
                _validate_schema(item, properties[key], path=f"{path}.{key}")
    elif expected == "array":
        if not isinstance(value, list):
            raise ValueError(f"{path} must be an array")
        item_schema = schema.get("items")
        if item_schema:
            for index, item in enumerate(value):
                _validate_schema(item, item_schema, path=f"{path}[{index}]")
    elif expected == "string":
        if not isinstance(value, str):
            raise ValueError(f"{path} must be a string")
    elif expected == "number":
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError(f"{path} must be a number")
    elif expected == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError(f"{path} must be an integer")
    elif expected == "boolean":
        if not isinstance(value, bool):
            raise ValueError(f"{path} must be a boolean")


def _coerce_to_schema(value: Any, schema: dict[str, Any]) -> Any:
    expected = schema.get("type")
    if expected == "object":
        source = value if isinstance(value, dict) else {}
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        output: dict[str, Any] = {}
        for key, prop_schema in properties.items():
            if key in source:
                output[key] = _coerce_to_schema(source[key], prop_schema)
            elif key in required:
                output[key] = _default_for_schema(prop_schema)
        return output
    if expected == "array":
        if isinstance(value, list):
            item_schema = schema.get("items", {})
            return [_coerce_to_schema(item, item_schema) for item in value]
        return []
    if expected == "string":
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        return str(value)
    if expected == "number":
        if isinstance(value, bool):
            return 0.0
        if isinstance(value, (int, float)):
            return float(value)
        try:
            return float(str(value))
        except Exception:
            return 0.0
    if expected == "integer":
        if isinstance(value, bool):
            return 0
        if isinstance(value, int):
            return value
        try:
            return int(float(str(value)))
        except Exception:
            return 0
    if expected == "boolean":
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"true", "1", "yes"}
        return bool(value)
    return value


def _default_for_schema(schema: dict[str, Any]) -> Any:
    expected = schema.get("type")
    if expected == "object":
        return _coerce_to_schema({}, schema)
    if expected == "array":
        return []
    if expected == "string":
        return ""
    if expected == "number":
        return 0.0
    if expected == "integer":
        return 0
    if expected == "boolean":
        return False
    return None
