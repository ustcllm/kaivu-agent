from __future__ import annotations

from dataclasses import dataclass, field

from .sections import PromptSection, render_sections


@dataclass(slots=True)
class PromptBuildInput:
    base_role: str
    memory: str = ""
    workflow_state: str = ""
    skill_prompt: str = ""
    schema_instruction: str = ""
    tool_policy: str = ""
    mcp_instructions: str = ""
    safety_policy: str = ""
    extra_sections: list[PromptSection] = field(default_factory=list)


class PromptBuilder:
    def build(self, data: PromptBuildInput) -> str:
        sections = [
            PromptSection("Role", data.base_role),
            PromptSection("Memory", data.memory, optional=True),
            PromptSection("Workflow State", data.workflow_state, optional=True),
            PromptSection("Skills", data.skill_prompt, optional=True),
            PromptSection("Structured Output", data.schema_instruction, optional=True),
            PromptSection("Tool Policy", data.tool_policy, optional=True),
            PromptSection("MCP", data.mcp_instructions, optional=True),
            PromptSection("Safety", data.safety_policy, optional=True),
            *data.extra_sections,
        ]
        return render_sections(sections)
