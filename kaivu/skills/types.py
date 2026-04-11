from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class SkillDefinition:
    name: str
    description: str
    when_to_use: str
    prompt: str
    allowed_tools: list[str] = field(default_factory=list)
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    path: Path | None = None
