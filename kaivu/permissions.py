from __future__ import annotations

from pathlib import Path
import re
from dataclasses import dataclass, field
from typing import Any, Literal


PermissionMode = Literal["default", "accept_all", "deny_destructive"]


@dataclass(slots=True)
class PermissionDecision:
    allowed: bool
    reason: str
    updated_input: dict[str, Any] = field(default_factory=dict)


@dataclass
class PermissionPolicy:
    mode: PermissionMode = "deny_destructive"
    allow_tools: set[str] = field(default_factory=set)
    deny_tools: set[str] = field(default_factory=set)
    scientific_autonomy_level: str = "L2"
    enforce_scientific_tool_policy: bool = False
    allowed_read_roots: list[str] = field(default_factory=list)
    allowed_write_roots: list[str] = field(default_factory=list)
    denied_path_prefixes: list[str] = field(default_factory=list)
    blocked_extensions: set[str] = field(
        default_factory=lambda: {".key", ".pem", ".pfx", ".sqlite", ".db"}
    )
    sensitive_path_keywords: set[str] = field(
        default_factory=lambda: {
            ".env",
            "credential",
            "secret",
            "token",
            "patient",
            "subject",
            "phi",
            "pii",
        }
    )
    blocked_shell_patterns: tuple[str, ...] = (
        "curl ",
        "wget ",
        "invoke-webrequest",
        "remove-item",
        "del ",
        "rm ",
        "format ",
    )

    def summary(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "allow_tools": sorted(self.allow_tools),
            "deny_tools": sorted(self.deny_tools),
            "allowed_read_roots": self.allowed_read_roots,
            "allowed_write_roots": self.allowed_write_roots,
            "denied_path_prefixes": self.denied_path_prefixes,
            "blocked_extensions": sorted(self.blocked_extensions),
            "scientific_autonomy_level": self.scientific_autonomy_level,
            "enforce_scientific_tool_policy": self.enforce_scientific_tool_policy,
        }

    def evaluate(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        is_destructive: bool,
        cwd: str | Path | None = None,
    ) -> PermissionDecision:
        if tool_name in self.deny_tools:
            return PermissionDecision(False, f"tool '{tool_name}' is deny-listed")
        if tool_name in self.allow_tools:
            return PermissionDecision(True, f"tool '{tool_name}' is allow-listed", arguments)
        if self.mode == "accept_all":
            return PermissionDecision(True, "policy allows all tools", arguments)
        scoped = self._evaluate_scoped_access(
            tool_name=tool_name,
            arguments=arguments,
            cwd=cwd,
        )
        if not scoped.allowed:
            return scoped
        if self.mode == "deny_destructive" and is_destructive:
            return PermissionDecision(False, "destructive tool blocked by policy")
        return PermissionDecision(True, "tool allowed by default policy", arguments)

    def _evaluate_scoped_access(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        cwd: str | Path | None,
    ) -> PermissionDecision:
        cwd_path = Path(cwd).resolve() if cwd else Path.cwd().resolve()
        read_paths = self._extract_candidate_paths(tool_name, arguments, cwd_path, write=False)
        write_paths = self._extract_candidate_paths(tool_name, arguments, cwd_path, write=True)
        for path in read_paths:
            denied = self._check_path(path, write=False, cwd=cwd_path)
            if denied is not None:
                return PermissionDecision(False, denied)
        for path in write_paths:
            denied = self._check_path(path, write=True, cwd=cwd_path)
            if denied is not None:
                return PermissionDecision(False, denied)

        if tool_name == "shell":
            command = str(arguments.get("command", "")).lower()
            for pattern in self.blocked_shell_patterns:
                if pattern in command:
                    return PermissionDecision(
                        False,
                        f"shell command blocked by scientific data/file policy: '{pattern.strip()}'",
                    )

        if tool_name == "python_exec":
            code = str(arguments.get("code", ""))
            denied = self._check_inline_code_access(code, cwd_path)
            if denied is not None:
                return PermissionDecision(False, denied)

        return PermissionDecision(True, "tool allowed by scoped policy", arguments)

    def _extract_candidate_paths(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        cwd: Path,
        *,
        write: bool,
    ) -> list[Path]:
        keys: list[str] = []
        if tool_name in {"read_file"} and not write:
            keys.append("path")
        if tool_name in {"write_file"} and write:
            keys.append("path")
        if write and "output_path" in arguments:
            keys.append("output_path")
        if not write and "path" in arguments and tool_name not in {"read_file"}:
            keys.append("path")
        paths: list[Path] = []
        for key in keys:
            value = arguments.get(key)
            if isinstance(value, str) and value.strip():
                paths.append((cwd / value).resolve())
        return paths

    def _check_inline_code_access(self, code: str, cwd: Path) -> str | None:
        quoted_paths = re.findall(r"['\"]([^'\"]+\.[A-Za-z0-9]{1,8})['\"]", code)
        for token in quoted_paths[:20]:
            lowered = token.lower()
            if any(keyword in lowered for keyword in self.sensitive_path_keywords):
                return f"python_exec blocked sensitive file reference '{token}'"
            candidate = Path(token)
            resolved = (cwd / candidate).resolve() if not candidate.is_absolute() else candidate.resolve()
            denied = self._check_path(resolved, write=False, cwd=cwd)
            if denied is not None:
                return denied
        return None

    def _check_path(self, path: Path, *, write: bool, cwd: Path) -> str | None:
        path_lower = str(path).lower()
        if any(keyword in path_lower for keyword in self.sensitive_path_keywords):
            return f"path blocked by sensitive-data policy: {path}"
        for denied_prefix in self.denied_path_prefixes:
            denied_root = Path(denied_prefix).resolve()
            if self._is_within(path, denied_root):
                return f"path blocked by deny-listed prefix: {path}"
        if path.suffix.lower() in self.blocked_extensions:
            return f"path blocked by restricted file extension: {path.suffix}"

        allowed_roots = self.allowed_write_roots if write else self.allowed_read_roots
        candidate_roots = [Path(root).resolve() for root in allowed_roots if root]
        if not candidate_roots:
            candidate_roots = [cwd]
        if not any(self._is_within(path, root) for root in candidate_roots):
            action = "write" if write else "read"
            return f"{action} path outside allowed roots: {path}"
        return None

    @staticmethod
    def _is_within(path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            return False


