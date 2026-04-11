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
