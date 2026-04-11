from __future__ import annotations

import csv
import math
import statistics
import zipfile
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET

from .tools import Tool, ToolContext


def _resolve_path(context: ToolContext, relative_path: str) -> Path:
    return (context.state.cwd / relative_path).resolve()


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader)


def _read_xlsx_rows(path: Path, sheet_name: str | None = None) -> list[dict[str, str]]:
    with zipfile.ZipFile(path) as archive:
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            ns = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
            for si in root.findall("main:si", ns):
                text = "".join(node.text or "" for node in si.iterfind(".//main:t", ns))
                shared_strings.append(text)

        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        ns = {
            "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
            "rel": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
        }
        rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        rel_map = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels}

        selected_target = None
        for sheet in workbook.findall("main:sheets/main:sheet", ns):
            if sheet_name is None or sheet.attrib.get("name") == sheet_name:
                selected_target = rel_map[sheet.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]]
                break
        if selected_target is None:
            raise ValueError(f"Sheet not found: {sheet_name}")

        worksheet = ET.fromstring(archive.read(f"xl/{selected_target}"))
        rows: list[list[str]] = []
        for row in worksheet.findall(".//main:sheetData/main:row", ns):
            cells: list[str] = []
            for cell in row.findall("main:c", ns):
                value = cell.find("main:v", ns)
                if value is None:
                    cells.append("")
                    continue
                cell_text = value.text or ""
                if cell.attrib.get("t") == "s":
                    cells.append(shared_strings[int(cell_text)])
                else:
                    cells.append(cell_text)
            rows.append(cells)
        if not rows:
            return []
        header = rows[0]
        return [{header[i]: row[i] if i < len(row) else "" for i in range(len(header))} for row in rows[1:]]


def _load_tabular(path: Path, sheet_name: str | None = None) -> list[dict[str, str]]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return _read_csv_rows(path)
    if suffix == ".xlsx":
        return _read_xlsx_rows(path, sheet_name=sheet_name)
    raise ValueError(f"Unsupported tabular file type: {suffix}")


def _numeric_columns(rows: list[dict[str, str]]) -> dict[str, list[float]]:
    numeric: dict[str, list[float]] = {}
    if not rows:
        return numeric
    for key in rows[0]:
        values: list[float] = []
        for row in rows:
            raw = (row.get(key) or "").strip()
            if not raw:
                continue
            try:
                values.append(float(raw))
            except ValueError:
                values = []
                break
        if values:
            numeric[key] = values
    return numeric


class ReadTableTool(Tool):
    name = "read_table"
    description = "Read a CSV or XLSX table and return a preview."
    concurrency_safe = True
    read_only = True
    parameters_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "sheet_name": {"type": "string"},
            "max_rows": {"type": "integer"},
        },
        "required": ["path"],
        "additionalProperties": False,
    }

    def validate(self, arguments: dict[str, Any]) -> dict[str, Any]:
        if "path" not in arguments:
            raise ValueError("read_table requires 'path'")
        arguments.setdefault("max_rows", 10)
        return arguments

    async def call(self, arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        path = _resolve_path(context, arguments["path"])
        rows = _load_tabular(path, sheet_name=arguments.get("sheet_name"))
        return {
            "path": str(path),
            "row_count": len(rows),
            "columns": list(rows[0].keys()) if rows else [],
            "preview": rows[: int(arguments.get("max_rows", 10))],
        }


class BasicStatsTool(Tool):
    name = "basic_table_stats"
    description = "Compute basic descriptive statistics for numeric columns in a CSV or XLSX file."
    concurrency_safe = True
    read_only = True
    parameters_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "sheet_name": {"type": "string"},
        },
        "required": ["path"],
        "additionalProperties": False,
    }

    def validate(self, arguments: dict[str, Any]) -> dict[str, Any]:
        if "path" not in arguments:
            raise ValueError("basic_table_stats requires 'path'")
        return arguments

    async def call(self, arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        path = _resolve_path(context, arguments["path"])
        rows = _load_tabular(path, sheet_name=arguments.get("sheet_name"))
        numeric = _numeric_columns(rows)
        stats = {}
        for key, values in numeric.items():
            stats[key] = {
                "count": len(values),
                "mean": statistics.fmean(values),
                "median": statistics.median(values),
                "min": min(values),
                "max": max(values),
                "stdev": statistics.stdev(values) if len(values) > 1 else 0.0,
            }
        return {"path": str(path), "numeric_columns": stats}


class PlotCsvTool(Tool):
    name = "plot_csv"
    description = "Generate a plot from two columns of a CSV or XLSX file."
    destructive = True
    parameters_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "x_column": {"type": "string"},
            "y_column": {"type": "string"},
            "output_path": {"type": "string"},
            "sheet_name": {"type": "string"},
            "kind": {"type": "string"},
        },
        "required": ["path", "x_column", "y_column", "output_path"],
        "additionalProperties": False,
    }

    def validate(self, arguments: dict[str, Any]) -> dict[str, Any]:
        required = ["path", "x_column", "y_column", "output_path"]
        for key in required:
            if key not in arguments:
                raise ValueError(f"plot_csv requires '{key}'")
        arguments.setdefault("kind", "line")
        return arguments

    async def call(self, arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
        except Exception as exc:
            raise RuntimeError("matplotlib is required for plot_csv") from exc

        path = _resolve_path(context, arguments["path"])
        rows = _load_tabular(path, sheet_name=arguments.get("sheet_name"))
        x_values = [row[arguments["x_column"]] for row in rows]
        y_values = [float(row[arguments["y_column"]]) for row in rows if row.get(arguments["y_column"])]

        if len(x_values) != len(y_values):
            x_values = x_values[: len(y_values)]

        plt.figure(figsize=(8, 4))
        if arguments.get("kind") == "bar":
            plt.bar(x_values, y_values)
        else:
            plt.plot(x_values, y_values, marker="o")
        plt.xlabel(arguments["x_column"])
        plt.ylabel(arguments["y_column"])
        plt.tight_layout()

        output_path = _resolve_path(context, arguments["output_path"])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(output_path)
        plt.close()
        return {"output_path": str(output_path), "points": len(y_values)}
