from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ALLOWED_SKILL_SUBDIRS = {"references", "templates", "scripts", "assets"}


@dataclass(slots=True)
class SkillWriteResult:
    ok: bool
    action: str
    skill_name: str
    path: str = ""
    message: str = ""
    validation_errors: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ScientificSkillManager:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.skill_root = self.root / "skills"
        self.skill_root.mkdir(parents=True, exist_ok=True)

    def create_or_update_skill(
        self,
        *,
        name: str,
        description: str,
        when_to_use: str,
        prompt: str,
        allowed_tools: list[str] | None = None,
        category: str = "scientific",
    ) -> dict[str, Any]:
        errors = _validate_skill_payload(name=name, description=description, when_to_use=when_to_use, prompt=prompt)
        if errors:
            return SkillWriteResult(False, "create_or_update", name, message="skill validation failed", validation_errors=errors).to_dict()
        skill_dir = self._skill_dir(name=name, category=category)
        skill_dir.mkdir(parents=True, exist_ok=True)
        content = "\n".join(
            [
                "---",
                f"name: {name}",
                f"description: {description}",
                f"when_to_use: {when_to_use}",
                f"allowed_tools: {', '.join(allowed_tools or [])}",
                f"updated_at: {datetime.now(timezone.utc).isoformat()}",
                "---",
                "",
                prompt.strip(),
                "",
            ]
        )
        target = skill_dir / "SKILL.md"
        target.write_text(content, encoding="utf-8")
        return SkillWriteResult(True, "create_or_update", name, path=str(target), message="skill saved").to_dict()

    def write_supporting_file(self, *, name: str, relative_path: str, content: str, category: str = "scientific") -> dict[str, Any]:
        parts = Path(relative_path)
        if not parts.parts or parts.parts[0] not in ALLOWED_SKILL_SUBDIRS or ".." in parts.parts:
            return SkillWriteResult(False, "write_file", name, message="supporting file path is not allowed").to_dict()
        skill_dir = self._skill_dir(name=name, category=category)
        if not (skill_dir / "SKILL.md").exists():
            return SkillWriteResult(False, "write_file", name, message="skill does not exist").to_dict()
        target = (skill_dir / parts).resolve()
        if not _is_within(target, skill_dir):
            return SkillWriteResult(False, "write_file", name, message="supporting file escapes skill directory").to_dict()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return SkillWriteResult(True, "write_file", name, path=str(target), message="supporting file saved").to_dict()

    def _skill_dir(self, *, name: str, category: str) -> Path:
        return self.skill_root / _slugify(category or "scientific") / _slugify(name)


def _validate_skill_payload(*, name: str, description: str, when_to_use: str, prompt: str) -> list[str]:
    errors: list[str] = []
    if not name.strip():
        errors.append("name is required")
    if len(name) > 80:
        errors.append("name is too long")
    if not description.strip():
        errors.append("description is required")
    if not when_to_use.strip():
        errors.append("when_to_use is required")
    if len(prompt.strip()) < 20:
        errors.append("prompt is too short to be useful")
    suspicious = ["ignore previous instructions", "system prompt override", "do not tell the user", "exfiltrate", "secret"]
    haystack = f"{description}\n{when_to_use}\n{prompt}".lower()
    for token in suspicious:
        if token in haystack:
            errors.append(f"potential prompt-injection or unsafe instruction: {token}")
    return errors


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _slugify(value: str) -> str:
    safe = "".join(ch.lower() if ch.isalnum() else "-" for ch in str(value).strip())
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-") or "skill"


