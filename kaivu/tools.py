from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import hashlib
import json
import subprocess
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .graph import ResearchGraphRegistry
from .literature_policy import decide_literature_ingest_policy, render_literature_ingest_digest
from .memory import MemoryManager
from .state import AgentState


@dataclass(slots=True)
class ToolContext:
    state: AgentState
    memory_manager: MemoryManager | None = None


class Tool(ABC):
    name: str
    description: str
    concurrency_safe: bool = False
    read_only: bool = False
    destructive: bool = False
    parameters_schema: dict[str, Any] = {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": False,
    }

    def validate(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return arguments

    @abstractmethod
    async def call(self, arguments: dict[str, Any], context: ToolContext) -> Any:
        raise NotImplementedError


class ToolRegistry:
    def __init__(self, tools: list[Tool] | None = None) -> None:
        self._tools: dict[str, Tool] = {}
        for tool in tools or []:
            self.register(tool)

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        if name not in self._tools:
            raise KeyError(f"unknown tool: {name}")
        return self._tools[name]

    def all(self) -> list[Tool]:
        return list(self._tools.values())

    def subset(self, names: list[str]) -> "ToolRegistry":
        wanted = set(names)
        return ToolRegistry([tool for tool in self.all() if tool.name in wanted])

    def merge(self, other: "ToolRegistry") -> "ToolRegistry":
        merged = ToolRegistry(self.all())
        for tool in other.all():
            merged.register(tool)
        return merged

    def partition(self, tool_names: list[str]) -> list[tuple[bool, list[Tool]]]:
        batches: list[tuple[bool, list[Tool]]] = []
        current_safe: bool | None = None
        current_batch: list[Tool] = []
        for name in tool_names:
            tool = self.get(name)
            safe = tool.concurrency_safe
            if current_safe is None or safe != current_safe or not safe:
                if current_batch:
                    batches.append((bool(current_safe), current_batch))
                current_safe = safe
                current_batch = [tool]
                if not safe:
                    batches.append((False, current_batch))
                    current_safe = None
                    current_batch = []
            else:
                current_batch.append(tool)
        if current_batch:
            batches.append((bool(current_safe), current_batch))
        return batches


def record_execution_log(
    context: ToolContext,
    *,
    task_id: str,
    tool_name: str,
    arguments: dict[str, Any],
    result: Any = None,
    error: str | None = None,
) -> dict[str, Any]:
    record = {
        "task_id": task_id,
        "tool_name": tool_name,
        "status": "failed" if error else "completed",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "inputs": _summarize_inputs(context, arguments),
        "outputs": _summarize_outputs(result),
        "artifacts": _collect_artifacts(context, arguments, result),
        "error": error,
    }
    log = context.state.scratchpad.setdefault("execution_records", [])
    log.append(record)
    return record


def _resolve_workspace_path(cwd: Path, raw_path: str) -> Path:
    root = cwd.resolve()
    target = (root / raw_path).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise PermissionError(f"path escapes workspace: {raw_path}") from exc
    return target


def _summarize_inputs(context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for key, value in arguments.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            summary[key] = value
        elif isinstance(value, list):
            summary[key] = value[:10]
        else:
            summary[key] = str(value)
    path_keys = [key for key in ("path", "output_path") if key in arguments]
    file_inputs: list[dict[str, Any]] = []
    for key in path_keys:
        try:
            resolved = _resolve_workspace_path(context.state.cwd, str(arguments[key]))
            scope = _classify_path_scope(resolved)
            exists = resolved.exists()
            digest = _sha256_file(resolved) if exists and resolved.is_file() else ""
            access_note = ""
        except PermissionError as exc:
            resolved = (context.state.cwd / str(arguments[key])).resolve()
            scope = "outside_workspace"
            exists = False
            digest = ""
            access_note = str(exc)
        file_inputs.append(
            {
                "argument": key,
                "path": str(resolved),
                "exists": exists,
                "scope": scope,
                "sha256": digest,
                **({"access_note": access_note} if access_note else {}),
            }
        )
    if file_inputs:
        summary["file_inputs"] = file_inputs
        summary["data_scopes"] = sorted(
            {
                _classify_path_scope(Path(item["path"]))
                for item in file_inputs
                if item.get("path")
            }
        )
    if "code" in arguments:
        summary["code_sha256"] = hashlib.sha256(
            str(arguments["code"]).encode("utf-8")
        ).hexdigest()
    return summary


def _summarize_outputs(result: Any) -> dict[str, Any]:
    if isinstance(result, dict):
        output = dict(result)
        if "stdout" in output and isinstance(output["stdout"], str) and len(output["stdout"]) > 1000:
            output["stdout"] = output["stdout"][:1000] + "..."
        if "stderr" in output and isinstance(output["stderr"], str) and len(output["stderr"]) > 1000:
            output["stderr"] = output["stderr"][:1000] + "..."
        return output
    if result is None:
        return {}
    return {"value": str(result)}


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(8192)
                if not chunk:
                    break
                hasher.update(chunk)
    except Exception:
        return ""
    return hasher.hexdigest()


def _classify_path_scope(path: Path) -> str:
    lowered = str(path).lower()
    if any(token in lowered for token in ("patient", "subject", "phi", "pii")):
        return "sensitive_human_data"
    if any(token in lowered for token in ("dataset", "data", "table", "csv", "xlsx")):
        return "dataset"
    if any(token in lowered for token in ("report", "artifact", "result", "output")):
        return "artifact"
    if any(token in lowered for token in ("memory", "thread", "audit")):
        return "knowledge"
    return "workspace"


def _collect_artifacts(
    context: ToolContext,
    arguments: dict[str, Any],
    result: Any,
) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    for key in ("path", "output_path"):
        value = arguments.get(key)
        if not isinstance(value, str) or not value.strip():
            continue
        try:
            resolved = _resolve_workspace_path(context.state.cwd, value)
            scope = _classify_path_scope(resolved)
            exists = resolved.exists()
            digest = _sha256_file(resolved) if exists and resolved.is_file() else ""
            access_note = ""
        except PermissionError as exc:
            resolved = (context.state.cwd / value).resolve()
            scope = "outside_workspace"
            exists = False
            digest = ""
            access_note = str(exc)
        write_intent = key == "output_path" or "write" in str(arguments).lower()
        artifacts.append(
            {
                "path": str(resolved),
                "kind": "output" if write_intent else "input",
                "exists": exists,
                "scope": scope,
                "sha256": digest,
                **({"access_note": access_note} if access_note else {}),
            }
        )
    if isinstance(result, dict):
        output_path = result.get("output_path")
        if isinstance(output_path, str) and output_path.strip():
            try:
                resolved = _resolve_workspace_path(context.state.cwd, output_path)
                scope = _classify_path_scope(resolved)
                exists = resolved.exists()
                digest = _sha256_file(resolved) if exists and resolved.is_file() else ""
                access_note = ""
            except PermissionError as exc:
                resolved = (context.state.cwd / output_path).resolve()
                scope = "outside_workspace"
                exists = False
                digest = ""
                access_note = str(exc)
            artifacts.append(
                {
                    "path": str(resolved),
                    "kind": "output",
                    "exists": exists,
                    "scope": scope,
                    "sha256": digest,
                    **({"access_note": access_note} if access_note else {}),
                }
            )
    deduped: dict[tuple[str, str], dict[str, Any]] = {}
    for item in artifacts:
        deduped[(item["path"], item["kind"])] = item
    return list(deduped.values())


class ReadFileTool(Tool):
    name = "read_file"
    description = "Read a UTF-8 text file from the workspace."
    concurrency_safe = True
    read_only = True
    parameters_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path relative to the workspace root."}
        },
        "required": ["path"],
        "additionalProperties": False,
    }

    def validate(self, arguments: dict[str, Any]) -> dict[str, Any]:
        if "path" not in arguments:
            raise ValueError("read_file requires 'path'")
        return arguments

    async def call(self, arguments: dict[str, Any], context: ToolContext) -> str:
        path = _resolve_workspace_path(context.state.cwd, str(arguments["path"]))
        return path.read_text(encoding="utf-8")


class WriteFileTool(Tool):
    name = "write_file"
    description = "Write UTF-8 text to a workspace file."
    destructive = True
    parameters_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path relative to the workspace root."},
            "content": {"type": "string", "description": "UTF-8 text content to write."},
        },
        "required": ["path", "content"],
        "additionalProperties": False,
    }

    def validate(self, arguments: dict[str, Any]) -> dict[str, Any]:
        if "path" not in arguments or "content" not in arguments:
            raise ValueError("write_file requires 'path' and 'content'")
        return arguments

    async def call(self, arguments: dict[str, Any], context: ToolContext) -> str:
        path = _resolve_workspace_path(context.state.cwd, str(arguments["path"]))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(arguments["content"], encoding="utf-8")
        return f"wrote {path}"


class PythonExecTool(Tool):
    name = "python_exec"
    description = "Execute a Python snippet for computation or data analysis."
    parameters_schema = {
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "Python code to execute."},
            "timeout": {"type": "number", "description": "Optional timeout in seconds."},
            "seed": {"type": "integer", "description": "Optional random seed for reproducibility."},
        },
        "required": ["code"],
        "additionalProperties": False,
    }

    def validate(self, arguments: dict[str, Any]) -> dict[str, Any]:
        if "code" not in arguments:
            raise ValueError("python_exec requires 'code'")
        return arguments

    async def call(self, arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        seed = arguments.get("seed")
        code = arguments["code"]
        if seed is not None:
            code = (
                "import random\n"
                f"random.seed({int(seed)})\n"
                "try:\n"
                "    import numpy as _np\n"
                f"    _np.random.seed({int(seed)})\n"
                "except Exception:\n"
                "    pass\n\n"
                + code
            )
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            code,
            cwd=str(context.state.cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(),
            timeout=float(arguments.get("timeout", 20)),
        )
        return {
            "returncode": proc.returncode,
            "stdout": stdout.decode("utf-8", errors="replace"),
            "stderr": stderr.decode("utf-8", errors="replace"),
            "seed": seed,
        }


class ShellTool(Tool):
    name = "shell"
    description = "Run a shell command in the workspace."
    parameters_schema = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Shell command to execute."},
            "timeout": {"type": "number", "description": "Optional timeout in seconds."},
        },
        "required": ["command"],
        "additionalProperties": False,
    }

    def validate(self, arguments: dict[str, Any]) -> dict[str, Any]:
        if "command" not in arguments:
            raise ValueError("shell requires 'command'")
        return arguments

    async def call(self, arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        completed = await asyncio.to_thread(
            subprocess.run,
            arguments["command"],
            cwd=str(context.state.cwd),
            shell=True,
            capture_output=True,
            text=True,
            timeout=float(arguments.get("timeout", 20)),
        )
        return {
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }


class NotebookTool(Tool):
    name = "record_observation"
    description = "Persist a structured scientific note into the agent scratchpad."
    concurrency_safe = True
    parameters_schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Short note title."},
            "observation": {"type": "string", "description": "Scientific observation or summary."},
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional tags for later retrieval.",
            },
        },
        "required": ["title", "observation"],
        "additionalProperties": False,
    }

    def validate(self, arguments: dict[str, Any]) -> dict[str, Any]:
        if "title" not in arguments or "observation" not in arguments:
            raise ValueError("record_observation requires 'title' and 'observation'")
        if "tags" in arguments and not isinstance(arguments["tags"], list):
            raise ValueError("'tags' must be a list of strings")
        return arguments

    async def call(self, arguments: dict[str, Any], context: ToolContext) -> str:
        notebook = context.state.scratchpad.setdefault("lab_notebook", [])
        notebook.append(
            {
                "title": arguments["title"],
                "observation": arguments["observation"],
                "tags": arguments.get("tags", []),
            }
        )
        return json.dumps(notebook[-1], ensure_ascii=False)


class SaveMemoryTool(Tool):
    name = "save_memory"
    description = "Save an evidence-aware scientific memory and update MEMORY.md."
    destructive = True
    parameters_schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "summary": {"type": "string"},
            "memory_type": {"type": "string"},
            "scope": {"type": "string"},
            "content": {"type": "string"},
            "tags": {"type": "array", "items": {"type": "string"}},
            "source_refs": {"type": "array", "items": {"type": "string"}},
            "evidence_level": {"type": "string"},
            "confidence": {"type": "string"},
            "status": {"type": "string"},
            "owner_agent": {"type": "string"},
            "user_id": {"type": "string"},
            "project_id": {"type": "string"},
            "group_id": {"type": "string"},
            "visibility": {"type": "string"},
            "promotion_status": {"type": "string"},
            "last_verified_at": {"type": "string"},
            "needs_review": {"type": "boolean"},
            "review_due_at": {"type": "string"},
            "supersedes": {"type": "array", "items": {"type": "string"}},
            "superseded_by": {"type": "string"},
            "derived_from": {"type": "array", "items": {"type": "string"}},
            "conflicts_with": {"type": "array", "items": {"type": "string"}},
            "validated_by": {"type": "array", "items": {"type": "string"}},
            "filename": {"type": "string"},
        },
        "required": ["title", "summary", "memory_type", "scope", "content"],
        "additionalProperties": False,
    }

    def validate(self, arguments: dict[str, Any]) -> dict[str, Any]:
        for key in ["title", "summary", "memory_type", "scope", "content"]:
            if key not in arguments:
                raise ValueError(f"save_memory requires '{key}'")
        return arguments

    async def call(self, arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        if context.memory_manager is None:
            raise RuntimeError("memory manager is not configured")
        target = context.memory_manager.save_memory(
            title=arguments["title"],
            summary=arguments["summary"],
            kind=arguments["memory_type"],
            scope=arguments["scope"],
            content=arguments["content"],
            tags=arguments.get("tags", []),
            filename=arguments.get("filename"),
            source_refs=arguments.get("source_refs", []),
            evidence_level=arguments.get("evidence_level", "medium"),
            confidence=arguments.get("confidence", "medium"),
            status=arguments.get("status", "active"),
            owner_agent=arguments.get("owner_agent", "unknown"),
            user_id=arguments.get("user_id", ""),
            project_id=arguments.get("project_id", ""),
            group_id=arguments.get("group_id", ""),
            visibility=arguments.get("visibility"),
            promotion_status=arguments.get("promotion_status"),
            last_verified_at=arguments.get("last_verified_at"),
            needs_review=bool(arguments.get("needs_review", False)),
            review_due_at=arguments.get("review_due_at"),
            supersedes=arguments.get("supersedes", []),
            superseded_by=arguments.get("superseded_by"),
            derived_from=arguments.get("derived_from", []),
            conflicts_with=arguments.get("conflicts_with", []),
            validated_by=arguments.get("validated_by", []),
        )
        return {"saved": True, "path": str(target)}


class SearchMemoryTool(Tool):
    name = "search_memory"
    description = "Search persistent memories relevant to a query."
    concurrency_safe = True
    read_only = True
    parameters_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "max_results": {"type": "integer"},
            "user_id": {"type": "string"},
            "project_id": {"type": "string"},
            "group_id": {"type": "string"},
            "scopes": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["query"],
        "additionalProperties": False,
    }

    def validate(self, arguments: dict[str, Any]) -> dict[str, Any]:
        if "query" not in arguments:
            raise ValueError("search_memory requires 'query'")
        arguments.setdefault("max_results", 5)
        return arguments

    async def call(self, arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        if context.memory_manager is None:
            raise RuntimeError("memory manager is not configured")
        matches = context.memory_manager.find_relevant_memories(
            arguments["query"],
            max_memories=int(arguments.get("max_results", 5)),
            user_id=arguments.get("user_id"),
            project_id=arguments.get("project_id"),
            group_id=arguments.get("group_id"),
            scopes=arguments.get("scopes"),
        )
        return {
            "results": [
                {
                    "path": str(item.path),
                    "title": item.title,
                    "summary": item.summary,
                    "memory_type": item.kind,
                    "scope": item.scope,
                    "tags": item.tags,
                    "source_refs": item.source_refs,
                    "evidence_level": item.evidence_level,
                    "confidence": item.confidence,
                    "status": item.status,
                    "user_id": item.user_id,
                    "project_id": item.project_id,
                    "group_id": item.group_id,
                    "visibility": item.visibility,
                    "promotion_status": item.promotion_status,
                    "last_verified_at": item.last_verified_at,
                    "needs_review": item.needs_review,
                    "review_due_at": item.review_due_at,
                    "derived_from": item.derived_from,
                    "conflicts_with": item.conflicts_with,
                    "validated_by": item.validated_by,
                }
                for item in matches
            ]
        }


class ForgetMemoryTool(Tool):
    name = "forget_memory"
    description = "Delete a persistent memory file and rebuild MEMORY.md."
    destructive = True
    parameters_schema = {
        "type": "object",
        "properties": {"filename": {"type": "string"}},
        "required": ["filename"],
        "additionalProperties": False,
    }

    def validate(self, arguments: dict[str, Any]) -> dict[str, Any]:
        if "filename" not in arguments:
            raise ValueError("forget_memory requires 'filename'")
        return arguments

    async def call(self, arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        if context.memory_manager is None:
            raise RuntimeError("memory manager is not configured")
        deleted = context.memory_manager.forget_memory(arguments["filename"])
        return {"deleted": deleted, "filename": arguments["filename"]}


class ReviewMemoryTool(Tool):
    name = "review_memory"
    description = "Update review status, validation state, or supersession metadata for a memory."
    destructive = True
    parameters_schema = {
        "type": "object",
        "properties": {
            "filename": {"type": "string"},
            "status": {"type": "string"},
            "needs_review": {"type": "boolean"},
            "review_due_at": {"type": "string"},
            "superseded_by": {"type": "string"},
            "conflicts_with": {"type": "array", "items": {"type": "string"}},
            "validated_by": {"type": "array", "items": {"type": "string"}},
            "last_verified_at": {"type": "string"},
            "visibility": {"type": "string"},
            "promotion_status": {"type": "string"},
        },
        "required": ["filename"],
        "additionalProperties": False,
    }

    def validate(self, arguments: dict[str, Any]) -> dict[str, Any]:
        if "filename" not in arguments:
            raise ValueError("review_memory requires 'filename'")
        return arguments

    async def call(self, arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        if context.memory_manager is None:
            raise RuntimeError("memory manager is not configured")
        updated = context.memory_manager.review_memory(
            arguments["filename"],
            status=arguments.get("status"),
            needs_review=arguments.get("needs_review"),
            review_due_at=arguments.get("review_due_at"),
            superseded_by=arguments.get("superseded_by"),
            conflicts_with=arguments.get("conflicts_with"),
            validated_by=arguments.get("validated_by"),
            last_verified_at=arguments.get("last_verified_at"),
            visibility=arguments.get("visibility"),
            promotion_status=arguments.get("promotion_status"),
        )
        return {"updated": updated, "filename": arguments["filename"]}


class TypedGraphQueryTool(Tool):
    name = "query_typed_graph"
    description = "Query the persistent typed research graph by project, topic, node type, relation, or keywords."
    concurrency_safe = True
    read_only = True
    parameters_schema = {
        "type": "object",
        "properties": {
            "project_id": {"type": "string"},
            "topic": {"type": "string"},
            "node_type": {"type": "string"},
            "relation": {"type": "string"},
            "search": {"type": "string"},
            "limit": {"type": "integer"},
            "source_node_id": {"type": "string"},
            "target_node_id": {"type": "string"},
            "specialist_name": {"type": "string"},
            "include_consulted_only": {"type": "boolean"},
        },
        "required": ["project_id"],
        "additionalProperties": False,
    }

    def validate(self, arguments: dict[str, Any]) -> dict[str, Any]:
        if "project_id" not in arguments or not str(arguments["project_id"]).strip():
            raise ValueError("query_typed_graph requires 'project_id'")
        arguments.setdefault("limit", 25)
        return arguments

    async def call(self, arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        registry = ResearchGraphRegistry(context.state.cwd / ".state" / "graph")
        return registry.query(
            project_id=str(arguments["project_id"]).strip(),
            topic=str(arguments.get("topic", "")).strip(),
            node_type=str(arguments.get("node_type", "")).strip(),
            relation=str(arguments.get("relation", "")).strip(),
            search=str(arguments.get("search", "")).strip(),
            limit=max(1, min(int(arguments.get("limit", 25)), 100)),
            source_node_id=str(arguments.get("source_node_id", "")).strip(),
            target_node_id=str(arguments.get("target_node_id", "")).strip(),
            specialist_name=str(arguments.get("specialist_name", "")).strip(),
            include_consulted_only=bool(arguments.get("include_consulted_only", False)),
        )


class IngestLiteratureSourceTool(Tool):
    name = "ingest_literature_source"
    description = "Register a literature source using autonomous, guided, or review-gated ingest policy."
    destructive = True
    parameters_schema = {
        "type": "object",
        "properties": {
            "source_type": {"type": "string"},
            "title": {"type": "string"},
            "content": {"type": "string"},
            "filename": {"type": "string"},
            "target_scope": {"type": "string"},
            "user_mode": {"type": "string"},
            "impact_level": {"type": "string"},
            "conflict_level": {"type": "string"},
            "confidence": {"type": "string"},
            "group_role": {"type": "string"},
        },
        "required": ["source_type", "title", "content"],
        "additionalProperties": False,
    }

    async def call(self, arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        source_type = str(arguments["source_type"]).strip().lower()
        title = str(arguments["title"]).strip()
        content = str(arguments["content"])
        filename = str(arguments.get("filename", "")).strip()
        bucket = {
            "paper": "papers",
            "papers": "papers",
            "report": "reports",
            "reports": "reports",
            "web": "web",
            "article": "web",
        }.get(source_type, "web")
        literature_root = context.state.cwd / "literature"
        safe_name = filename or f"{_slugify_name(title)}.md"
        policy = decide_literature_ingest_policy(
            source_type=source_type,
            title=title,
            target_scope=str(arguments.get("target_scope", "project")),
            user_mode=str(arguments.get("user_mode", "auto")),
            impact_level=str(arguments.get("impact_level", "medium")),
            conflict_level=str(arguments.get("conflict_level", "low")),
            confidence=str(arguments.get("confidence", "medium")),
            group_role=str(arguments.get("group_role", "")),
        )
        if policy.mode == "autonomous":
            target_dir = literature_root / "raw_sources" / bucket
            target = target_dir / safe_name
            relative_target = f"raw_sources/{bucket}/{safe_name}"
            artifact_text = content
        elif policy.mode == "guided":
            target_dir = literature_root / "ingest_drafts"
            target = target_dir / safe_name
            relative_target = f"ingest_drafts/{safe_name}"
            artifact_text = render_literature_ingest_digest(
                title=title,
                source_type=source_type,
                content=content,
                policy=policy,
            )
        else:
            target_dir = literature_root / "ingest_proposals"
            target = target_dir / safe_name
            relative_target = f"ingest_proposals/{safe_name}"
            artifact_text = render_literature_ingest_digest(
                title=title,
                source_type=source_type,
                content=content,
                policy=policy,
            )
        target_dir.mkdir(parents=True, exist_ok=True)
        target.write_text(artifact_text, encoding="utf-8")

        log_path = literature_root / "wiki" / "log.md"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        entry = "\n".join(
            [
                "",
                f"## [{timestamp}] ingest-tool | {title}",
                "",
                f"- Mode: `{policy.mode}`.",
                f"- Target: `{relative_target}`.",
                f"- Requires confirmation: `{str(policy.requires_confirmation).lower()}`.",
                f"- Needs review: `{str(policy.needs_review).lower()}`.",
            ]
        )
        existing = log_path.read_text(encoding="utf-8") if log_path.exists() else "# Literature Log\n"
        log_path.write_text(existing.rstrip() + entry + "\n", encoding="utf-8")
        return {
            "saved": True,
            "path": str(target),
            "bucket": bucket,
            "mode": policy.mode,
            "requires_confirmation": policy.requires_confirmation,
            "needs_review": policy.needs_review,
            "policy": policy.to_dict(),
        }


class QueryLiteratureWikiTool(Tool):
    name = "query_literature_wiki"
    description = "Search the literature wiki pages by keyword and return matching markdown files."
    concurrency_safe = True
    read_only = True
    parameters_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "limit": {"type": "integer"},
            "sections": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["query"],
        "additionalProperties": False,
    }

    async def call(self, arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        query = str(arguments["query"]).strip().lower()
        limit = max(1, min(int(arguments.get("limit", 10)), 50))
        requested_sections = [
            str(item).strip()
            for item in arguments.get("sections", [])
            if str(item).strip()
        ]
        wiki_root = context.state.cwd / "literature" / "wiki"
        section_dirs = requested_sections or [
            "papers",
            "claims",
            "concepts",
            "mechanisms",
            "controversies",
            "methods",
            "datasets",
            "reviews",
        ]
        results: list[dict[str, Any]] = []
        for section in section_dirs:
            directory = wiki_root / section
            if not directory.exists():
                continue
            for path in sorted(directory.glob("*.md")):
                if path.name.upper() == "TEMPLATE.MD":
                    continue
                text = path.read_text(encoding="utf-8")
                lowered = text.lower()
                if query not in lowered:
                    continue
                score = lowered.count(query)
                results.append(
                    {
                        "path": str(path),
                        "section": section,
                        "score": score,
                        "title": _first_heading_or_title(text, fallback=path.stem),
                        "summary": _first_bullet(text),
                    }
                )
        results.sort(key=lambda item: (-int(item.get("score", 0)), str(item.get("title", ""))))
        return {"results": results[:limit]}


class LintLiteratureWorkspaceTool(Tool):
    name = "lint_literature_workspace"
    description = "Run a lightweight health check over the literature wiki and write lint.md."
    destructive = True
    parameters_schema = {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": False,
    }

    async def call(self, arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        literature_root = context.state.cwd / "literature"
        wiki_root = literature_root / "wiki"
        findings: list[str] = []
        index_path = wiki_root / "index.md"
        index_text = index_path.read_text(encoding="utf-8") if index_path.exists() else ""
        for section in ["papers", "claims", "concepts", "mechanisms", "controversies", "methods", "datasets", "reviews"]:
            directory = wiki_root / section
            pages = [p for p in directory.glob("*.md") if p.name.upper() != "TEMPLATE.MD"] if directory.exists() else []
            if not pages:
                findings.append(f"No pages found in {section}/")
                continue
            for page in pages:
                relative = page.relative_to(wiki_root).as_posix()
                if relative not in index_text:
                    findings.append(f"Index missing page link: {relative}")
        lint_path = wiki_root / "lint.md"
        lint_path.write_text(
            "\n".join(
                [
                    "# Literature Lint",
                    "",
                    *([f"- {item}" for item in findings] if findings else ["- No major issues detected."]),
                ]
            ).strip()
            + "\n",
            encoding="utf-8",
        )
        return {"findings": findings, "lint_path": str(lint_path)}


def _slugify_name(value: str) -> str:
    safe = "".join(ch.lower() if ch.isalnum() else "-" for ch in value.strip())
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-") or "literature-item"


def _first_heading_or_title(text: str, *, fallback: str) -> str:
    for line in text.splitlines():
        if line.startswith("title:"):
            return line.split(":", 1)[1].strip().strip('"')
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def _first_bullet(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- ") and len(stripped) > 2:
            return stripped[2:180]
    return ""

