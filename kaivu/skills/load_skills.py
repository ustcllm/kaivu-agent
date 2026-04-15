from __future__ import annotations

from pathlib import Path
from typing import Any

from .types import SkillDefinition


def load_skills(skill_dir: str | Path) -> list[SkillDefinition]:
    base = Path(skill_dir).resolve()
    if not base.exists():
        return []
    skills: list[SkillDefinition] = []
    for path in sorted(base.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        frontmatter, body = _parse_frontmatter(text)
        if not frontmatter:
            continue
        skills.append(
            SkillDefinition(
                name=str(frontmatter.get("name", path.stem)),
                description=str(frontmatter.get("description", "")),
                when_to_use=str(frontmatter.get("when_to_use", "")),
                prompt=body.strip(),
                allowed_tools=_parse_csv(frontmatter.get("allowed_tools", "")),
                input_schema=_parse_jsonish(frontmatter.get("input_schema")),
                output_schema=_parse_jsonish(frontmatter.get("output_schema")),
                path=path,
            )
        )
    return skills


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        return {}, text
    parts = text.split("\n---\n", 1)
    if len(parts) != 2:
        return {}, text
    raw_meta = parts[0].replace("---\n", "", 1)
    body = parts[1]
    meta: dict[str, str] = {}
    for line in raw_meta.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        meta[key.strip()] = value.strip()
    return meta, body


def _parse_csv(value: str) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _parse_jsonish(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    return None


