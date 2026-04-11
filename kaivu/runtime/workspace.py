from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class WorkspaceBoundary:
    root: str
    project_id: str = ""
    user_id: str = ""
    group_id: str = ""
    read_roots: list[str] = field(default_factory=list)
    write_roots: list[str] = field(default_factory=list)
    protected_roots: list[str] = field(default_factory=list)
    transient_roots: list[str] = field(default_factory=lambda: ["test_artifacts/tmp", ".state/tmp"])
    artifact_roots: list[str] = field(default_factory=lambda: [".state", "literature", "reports", "artifacts"])

    @classmethod
    def for_project(
        cls,
        root: str | Path,
        *,
        project_id: str = "",
        user_id: str = "",
        group_id: str = "",
    ) -> "WorkspaceBoundary":
        resolved = Path(root).resolve()
        return cls(
            root=str(resolved),
            project_id=project_id,
            user_id=user_id,
            group_id=group_id,
            read_roots=[str(resolved)],
            write_roots=[str(resolved)],
            protected_roots=[
                str(resolved / ".git"),
                str(resolved / ".venv"),
                str(resolved / "venv"),
                str(resolved / "__pycache__"),
            ],
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def resolve(self, raw_path: str | Path) -> Path:
        candidate = Path(raw_path)
        if not candidate.is_absolute():
            candidate = Path(self.root) / candidate
        return candidate.resolve()

    def classify(self, raw_path: str | Path) -> dict[str, Any]:
        path = self.resolve(raw_path)
        root = Path(self.root).resolve()
        scope = "outside_workspace"
        relative = ""
        try:
            relative = path.relative_to(root).as_posix()
            scope = "workspace"
        except ValueError:
            pass
        lowered = relative.lower()
        if lowered.startswith(".state/") or lowered == ".state":
            scope = "runtime_state"
        elif lowered.startswith("literature/"):
            scope = "literature_workspace"
        elif lowered.startswith("reports/") or lowered.startswith("artifacts/"):
            scope = "research_artifact"
        elif lowered.startswith("test_artifacts/tmp/") or lowered.startswith(".state/tmp/"):
            scope = "transient"
        elif any(token in lowered for token in ("patient", "subject", "phi", "pii", "secret", ".env")):
            scope = "sensitive_or_secret"
        protected = any(_is_within(path, Path(item).resolve()) for item in self.protected_roots)
        return {
            "path": str(path),
            "relative_path": relative,
            "scope": scope,
            "inside_workspace": bool(relative),
            "protected": protected,
        }

    def permission_roots(self) -> dict[str, list[str]]:
        return {
            "read_roots": self.read_roots or [self.root],
            "write_roots": self.write_roots or [self.root],
            "protected_roots": self.protected_roots,
        }


def build_workspace_boundary_summary(boundary: WorkspaceBoundary) -> dict[str, Any]:
    return {
        "root": boundary.root,
        "project_id": boundary.project_id,
        "user_id": boundary.user_id,
        "group_id": boundary.group_id,
        "read_root_count": len(boundary.read_roots),
        "write_root_count": len(boundary.write_roots),
        "protected_root_count": len(boundary.protected_roots),
        "artifact_roots": boundary.artifact_roots,
        "transient_roots": boundary.transient_roots,
    }


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


@dataclass(slots=True)
class ResearchWorkspaceLayout:
    root: str
    discipline: str = "general_science"
    project_id: str = "default-project"
    group_id: str = ""
    user_id: str = ""
    layout_version: str = "discipline_project_v1"

    @classmethod
    def for_context(
        cls,
        root: str | Path,
        *,
        discipline: str = "",
        project_id: str = "",
        group_id: str = "",
        user_id: str = "",
    ) -> "ResearchWorkspaceLayout":
        return cls(
            root=str(Path(root).resolve()),
            discipline=_slugify(discipline or "general_science"),
            project_id=_slugify(project_id or "default-project"),
            group_id=_slugify(group_id or ""),
            user_id=_slugify(user_id or ""),
        )

    @property
    def base(self) -> Path:
        return Path(self.root).resolve()

    @property
    def namespace_parts(self) -> list[str]:
        parts = ["disciplines", self.discipline, "projects", self.project_id]
        if self.group_id:
            parts.extend(["groups", self.group_id])
        return parts

    @property
    def namespace_path(self) -> Path:
        path = self.base
        for part in self.namespace_parts:
            path = path / part
        return path

    @property
    def state_root(self) -> Path:
        return self.base / ".state" / self.namespace_path.relative_to(self.base)

    @property
    def memory_root(self) -> Path:
        return self.base / "memory" / self.namespace_path.relative_to(self.base)

    @property
    def literature_root(self) -> Path:
        return self.base / "literature" / self.namespace_path.relative_to(self.base)

    @property
    def artifact_root(self) -> Path:
        return self.base / "artifacts" / self.namespace_path.relative_to(self.base)

    @property
    def reports_root(self) -> Path:
        return self.base / "reports" / self.namespace_path.relative_to(self.base)

    @property
    def test_tmp_root(self) -> Path:
        return self.base / "test_artifacts" / "tmp" / self.namespace_path.relative_to(self.base)

    def ensure(self) -> None:
        for path in [
            self.state_root,
            self.memory_root,
            self.literature_root,
            self.artifact_root,
            self.reports_root,
            self.test_tmp_root,
        ]:
            path.mkdir(parents=True, exist_ok=True)

    def to_dict(self) -> dict[str, Any]:
        return {
            "layout_version": self.layout_version,
            "root": self.root,
            "discipline": self.discipline,
            "project_id": self.project_id,
            "group_id": self.group_id,
            "user_id": self.user_id,
            "state_root": str(self.state_root),
            "memory_root": str(self.memory_root),
            "literature_root": str(self.literature_root),
            "artifact_root": str(self.artifact_root),
            "reports_root": str(self.reports_root),
            "test_tmp_root": str(self.test_tmp_root),
            "legacy_roots": {
                "state": str(self.base / ".state"),
                "memory": str(self.base / "memory"),
                "literature": str(self.base / "literature"),
                "reports": str(self.base / "reports"),
                "artifacts": str(self.base / "artifacts"),
            },
        }


def build_research_workspace_layout_summary(layout: ResearchWorkspaceLayout) -> dict[str, Any]:
    data = layout.to_dict()
    return {
        **data,
        "partition_policy": "discipline/project/group scoped runtime assets",
        "shared_assets_policy": (
            "Global roots remain readable for compatibility, but new scoped runtime "
            "state should write under discipline/project namespace roots."
        ),
    }


def _slugify(value: str) -> str:
    safe = "".join(ch.lower() if ch.isalnum() else "-" for ch in str(value).strip())
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-")
