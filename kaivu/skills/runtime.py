from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .types import SkillDefinition


@dataclass(slots=True)
class SkillSelection:
    selected: list[SkillDefinition]
    prompt_block: str
    allowed_tools: list[str]


class SkillRuntime:
    def __init__(self, skills: Iterable[SkillDefinition]) -> None:
        self.skills = list(skills)

    def select_for_query(self, query: str, limit: int = 3) -> SkillSelection:
        query_terms = {term for term in query.lower().split() if len(term) >= 3}
        scored: list[tuple[int, SkillDefinition]] = []
        for skill in self.skills:
            haystack = f"{skill.name} {skill.description} {skill.when_to_use} {skill.prompt}".lower()
            score = sum(1 for term in query_terms if term in haystack)
            if score > 0:
                scored.append((score, skill))
        scored.sort(key=lambda item: item[0], reverse=True)
        chosen = [skill for _, skill in scored[:limit]]
        prompt_block = self._build_prompt_block(chosen)
        allowed_tools = sorted({tool for skill in chosen for tool in skill.allowed_tools})
        return SkillSelection(
            selected=chosen,
            prompt_block=prompt_block,
            allowed_tools=allowed_tools,
        )

    @staticmethod
    def _build_prompt_block(skills: list[SkillDefinition]) -> str:
        if not skills:
            return ""
        lines = ["Relevant skills:"]
        for skill in skills:
            lines.extend(
                [
                    f"## {skill.name}",
                    f"Description: {skill.description}",
                    f"When to use: {skill.when_to_use}",
                    skill.prompt,
                    "",
                ]
            )
        return "\n".join(lines).strip()


