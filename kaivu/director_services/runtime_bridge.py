from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..agents import ScientificAgentRunContext, build_discipline_agent
from ..runtime.agent_runtime import ScientificAgentRuntime
from .research_state import context_dict, context_string


@dataclass(slots=True)
class DirectorRuntimeBridge:
    """Project-level adapter from ResearchDirector context to ScientificAgentRuntime."""

    runtime_id: str = "research-director-agent-runtime"

    def summarize_discipline_agent(
        self,
        *,
        topic: str,
        discipline: str,
        task_type: str,
        collaboration_context: dict[str, Any],
        literature_synthesis: dict[str, Any],
        systematic_review_summary: dict[str, Any],
        evidence_review_summary: dict[str, Any],
        project_distill: dict[str, Any],
        failure_intelligence_summary: dict[str, Any],
    ) -> dict[str, Any]:
        agent = build_discipline_agent(discipline)
        runtime = ScientificAgentRuntime(runtime_id=self.runtime_id)
        result = runtime.run_agent(
            agent,
            ScientificAgentRunContext(
                topic=topic,
                project_id=str(collaboration_context.get("project_id", "")).strip(),
                discipline=discipline,
                task_type=task_type,
                dataset_path=context_string(collaboration_context, "dataset_path"),
                target_column=context_string(collaboration_context, "target_column"),
                metric=context_string(collaboration_context, "metric"),
                constraints=context_dict(collaboration_context, "constraints"),
                prior_context={
                    "literature_synthesis": literature_synthesis,
                    "systematic_review_summary": systematic_review_summary,
                    "evidence_review_summary": evidence_review_summary,
                    "project_distill": project_distill,
                    "failure_intelligence_summary": failure_intelligence_summary,
                    "research_program_context": collaboration_context.get("research_program_context", {}),
                    "scheduler_memory_context": collaboration_context.get("scheduler_memory_context", {}),
                },
            ),
        )
        return result.to_dict()


__all__ = ["DirectorRuntimeBridge"]
