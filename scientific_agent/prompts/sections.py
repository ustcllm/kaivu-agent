from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class PromptSection:
    name: str
    content: str
    optional: bool = False


def render_sections(sections: list[PromptSection]) -> str:
    blocks: list[str] = []
    for section in sections:
        if not section.content.strip() and section.optional:
            continue
        blocks.append(f"## {section.name}\n{section.content.strip()}")
    return "\n\n".join(blocks).strip()
