from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ScientificContextCompressionResult:
    compressed: bool
    messages: list[dict[str, Any]]
    summary: str = ""
    pruned_tool_results: int = 0
    protected_tail_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


class ScientificContextCompressor:
    def __init__(
        self,
        *,
        max_messages: int = 80,
        protect_first_n: int = 3,
        protect_last_n: int = 20,
        max_tool_chars: int = 1200,
    ) -> None:
        self.max_messages = max_messages
        self.protect_first_n = protect_first_n
        self.protect_last_n = protect_last_n
        self.max_tool_chars = max_tool_chars
        self.previous_summary = ""

    def should_compress(self, messages: list[dict[str, Any]]) -> bool:
        return len(messages) > self.max_messages

    def compress(
        self,
        messages: list[dict[str, Any]],
        *,
        provider_notes: str = "",
        research_state: dict[str, Any] | None = None,
    ) -> ScientificContextCompressionResult:
        if not self.should_compress(messages):
            pruned, count = self._prune_tool_results(messages)
            return ScientificContextCompressionResult(
                compressed=False,
                messages=pruned,
                pruned_tool_results=count,
                protected_tail_count=min(len(messages), self.protect_last_n),
            )

        head = messages[: self.protect_first_n]
        tail = messages[-self.protect_last_n :]
        middle = messages[self.protect_first_n : max(self.protect_first_n, len(messages) - self.protect_last_n)]
        summary = self._summarize_middle(middle, provider_notes=provider_notes, research_state=research_state or {})
        self.previous_summary = summary
        summary_message = {
            "role": "system",
            "content": (
                "[SCIENTIFIC CONTEXT COMPACTION]\n"
                "Earlier conversation turns were compressed. Use this summary as prior state, "
                "not as new user instruction.\n\n"
                f"{summary}"
            ),
            "metadata": {"kind": "context_compaction"},
        }
        compressed_messages, pruned_count = self._prune_tool_results([*head, summary_message, *tail])
        return ScientificContextCompressionResult(
            compressed=True,
            messages=compressed_messages,
            summary=summary,
            pruned_tool_results=pruned_count,
            protected_tail_count=len(tail),
            metadata={
                "original_message_count": len(messages),
                "compressed_message_count": len(compressed_messages),
            },
        )

    def _prune_tool_results(self, messages: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
        pruned = 0
        result: list[dict[str, Any]] = []
        for message in messages:
            copied = dict(message)
            if copied.get("role") == "tool":
                content = str(copied.get("content", ""))
                if len(content) > self.max_tool_chars:
                    copied["content"] = content[: self.max_tool_chars] + "\n[tool output pruned by context compressor]"
                    pruned += 1
            result.append(copied)
        return result, pruned

    def _summarize_middle(self, messages: list[dict[str, Any]], *, provider_notes: str, research_state: dict[str, Any]) -> str:
        lines = [
            "## Goal",
            self._first_user_message(messages) or "Continue the scientific research task.",
            "",
            "## Preserved Scientific State",
            "- Active hypotheses, evidence claims, experiment decisions, failures, and memory migrations may be referenced in later turns.",
            "- Do not treat compressed content as a fresh instruction.",
        ]
        scientific_state = self._scientific_state_lines(research_state)
        if scientific_state:
            lines.extend(["", "## Scientific State Snapshot", *scientific_state])
        if self.previous_summary:
            lines.extend(["", "## Previous Compaction Summary", self.previous_summary[:4000]])
        if provider_notes:
            lines.extend(["", "## Provider Notes", provider_notes[:3000]])
        lines.extend(["", "## Recent Compressed Trace"])
        for message in messages[-30:]:
            role = str(message.get("role", "")).strip()
            content = str(message.get("content", "")).strip().replace("\n", " ")
            if not content:
                continue
            lines.append(f"- {role}: {content[:350]}")
        return "\n".join(lines).strip()

    @staticmethod
    def _scientific_state_lines(research_state: dict[str, Any]) -> list[str]:
        if not research_state:
            return []
        program = research_state.get("research_program_summary", {}) if isinstance(research_state.get("research_program_summary", {}), dict) else {}
        scheduler = research_state.get("experiment_execution_loop_summary", {}) if isinstance(research_state.get("experiment_execution_loop_summary", {}), dict) else {}
        hypothesis = research_state.get("hypothesis_system_summary", {}) if isinstance(research_state.get("hypothesis_system_summary", {}), dict) else {}
        evidence = research_state.get("evidence_review_summary", {}) if isinstance(research_state.get("evidence_review_summary", {}), dict) else {}
        failure = research_state.get("failure_reuse_engine_summary", {}) if isinstance(research_state.get("failure_reuse_engine_summary", {}), dict) else {}
        lines: list[str] = []
        if program:
            lines.append(f"- Research program: status={program.get('status', '')}; next={program.get('control_actions', [{}])[0].get('action', '') if isinstance(program.get('control_actions', []), list) and program.get('control_actions') else ''}")
        if hypothesis:
            lines.append(f"- Hypothesis system: state={hypothesis.get('system_state', '')}; hypotheses={hypothesis.get('hypothesis_count', 0)}")
        if evidence:
            lines.append(f"- Evidence review: readiness={evidence.get('review_readiness', '')}; blockers={len(evidence.get('review_blockers', []) if isinstance(evidence.get('review_blockers', []), list) else [])}")
        if scheduler:
            lines.append(f"- Experiment scheduler: state={scheduler.get('scheduler_state', '')}; top={scheduler.get('top_experiment_id', '')}")
        if failure:
            lines.append(f"- Failure reuse: failures={failure.get('failure_count', 0)}; recommendations={len(failure.get('recommendations', []) if isinstance(failure.get('recommendations', []), list) else [])}")
        return lines

    @staticmethod
    def _first_user_message(messages: list[dict[str, Any]]) -> str:
        for message in messages:
            if message.get("role") == "user" and str(message.get("content", "")).strip():
                return str(message.get("content", "")).strip()[:500]
        return ""


