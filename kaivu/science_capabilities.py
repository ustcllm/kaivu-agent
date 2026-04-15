from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class ScientificCapabilitySpec:
    name: str
    description: str
    candidate_tools: list[str] = field(default_factory=list)
    execution_mode: str = "runtime_tool_call"
    pack: str = "core"
    discipline_tags: list[str] = field(default_factory=list)
    requires_approval: bool = False
    read_only_preferred: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ScientificCapabilityRegistry:
    """Scientific equivalent of a toolset registry.

    Agents declare capabilities in scientific language. The runtime resolves
    those declarations into concrete candidate tools and execution policy hints.
    """

    def __init__(self, capabilities: list[ScientificCapabilitySpec] | None = None) -> None:
        self._capabilities: dict[str, ScientificCapabilitySpec] = {}
        for capability in capabilities or default_scientific_capabilities():
            self.register(capability)

    def register(self, capability: ScientificCapabilitySpec) -> None:
        self._capabilities[capability.name] = capability

    def get(self, name: str) -> ScientificCapabilitySpec | None:
        return self._capabilities.get(name)

    def resolve_tools(self, name: str) -> list[str]:
        capability = self.get(name)
        return list(capability.candidate_tools) if capability else []

    def execution_mode(self, name: str) -> str:
        capability = self.get(name)
        return capability.execution_mode if capability else "runtime_tool_call"

    def pack(self, name: str) -> str:
        capability = self.get(name)
        return capability.pack if capability else "unknown"

    def requires_approval(self, name: str) -> bool:
        capability = self.get(name)
        return bool(capability.requires_approval) if capability else False

    def list_pack(self, pack: str) -> list[dict[str, Any]]:
        return [
            capability.to_dict()
            for capability in self._capabilities.values()
            if capability.pack == pack
        ]

    def list_for_discipline(self, discipline: str) -> list[dict[str, Any]]:
        normalized = discipline.strip().lower()
        return [
            capability.to_dict()
            for capability in self._capabilities.values()
            if normalized in capability.discipline_tags or "general_science" in capability.discipline_tags
        ]

    def to_dict(self) -> dict[str, Any]:
        packs: dict[str, list[str]] = {}
        for capability in self._capabilities.values():
            packs.setdefault(capability.pack, []).append(capability.name)
        return {
            "capability_count": len(self._capabilities),
            "packs": {name: sorted(values) for name, values in packs.items()},
            "capabilities": {
                name: capability.to_dict()
                for name, capability in sorted(self._capabilities.items())
            },
        }


def default_scientific_capabilities() -> list[ScientificCapabilitySpec]:
    return [
        ScientificCapabilitySpec(
            name="literature_search",
            description="Retrieve relevant scientific sources for claims, methods, and conflicts.",
            candidate_tools=["arxiv_search", "crossref_search", "pubmed_search"],
            pack="literature_review_pack",
            discipline_tags=["general_science", "artificial_intelligence", "chemistry", "physics", "mathematics"],
        ),
        ScientificCapabilitySpec(
            name="citation_resolution",
            description="Resolve ambiguous citation identifiers into stable source records.",
            candidate_tools=["resolve_citation"],
            pack="literature_review_pack",
            discipline_tags=["general_science"],
        ),
        ScientificCapabilitySpec(
            name="literature_wiki_query",
            description="Search the persistent literature wiki before raw retrieval.",
            candidate_tools=["query_literature_wiki"],
            pack="literature_review_pack",
            discipline_tags=["general_science"],
        ),
        ScientificCapabilitySpec(
            name="data_read",
            description="Read structured data or result tables for evidence interpretation.",
            candidate_tools=["read_table"],
            pack="computation_pack",
            discipline_tags=["general_science", "artificial_intelligence", "kaggle_competition", "physics", "chemical_engineering"],
        ),
        ScientificCapabilitySpec(
            name="python_analysis",
            description="Run reproducible computational checks or statistical analysis.",
            candidate_tools=["python_exec"],
            execution_mode="runtime_policy_checked_code",
            pack="computation_pack",
            discipline_tags=["general_science", "artificial_intelligence", "kaggle_competition", "physics", "mathematics"],
            requires_approval=True,
            read_only_preferred=False,
        ),
        ScientificCapabilitySpec(
            name="executor_handoff",
            description="Handoff an approved protocol to an external research executor.",
            candidate_tools=["scientific_executor"],
            execution_mode="external_executor_handoff",
            pack="execution_pack",
            discipline_tags=["general_science"],
            requires_approval=True,
            read_only_preferred=False,
        ),
        ScientificCapabilitySpec(
            name="memory_write",
            description="Persist validated decisions, failures, and claim updates.",
            candidate_tools=["save_memory", "review_memory"],
            execution_mode="runtime_policy_checked_write",
            pack="knowledge_pack",
            discipline_tags=["general_science"],
            requires_approval=True,
            read_only_preferred=False,
        ),
        ScientificCapabilitySpec(
            name="memory_recall",
            description="Recall relevant personal, project, group, or local memory.",
            candidate_tools=["search_memory"],
            pack="knowledge_pack",
            discipline_tags=["general_science"],
        ),
        ScientificCapabilitySpec(
            name="graph_query",
            description="Query typed scientific provenance graph context.",
            candidate_tools=["query_typed_graph"],
            pack="knowledge_pack",
            discipline_tags=["general_science"],
        ),
        ScientificCapabilitySpec(
            name="graph_update",
            description="Persist provenance links among scientific objects.",
            candidate_tools=["research_graph_registry"],
            execution_mode="runtime_policy_checked_write",
            pack="knowledge_pack",
            discipline_tags=["general_science"],
            requires_approval=True,
            read_only_preferred=False,
        ),
        ScientificCapabilitySpec(
            name="ai_training_execution",
            description="Run an AI training or evaluation scaffold under a frozen protocol.",
            candidate_tools=["ai_training_executor"],
            execution_mode="external_executor_handoff",
            pack="ai_research_pack",
            discipline_tags=["artificial_intelligence", "kaggle_competition"],
            requires_approval=True,
            read_only_preferred=False,
        ),
        ScientificCapabilitySpec(
            name="kaggle_submission_dry_run",
            description="Validate Kaggle submission schema without spending a live submission.",
            candidate_tools=["kaggle_submission_validator"],
            execution_mode="runtime_policy_checked_write",
            pack="kaggle_pack",
            discipline_tags=["kaggle_competition"],
            requires_approval=True,
            read_only_preferred=False,
        ),
        ScientificCapabilitySpec(
            name="proof_checking",
            description="Check proof obligations, hidden assumptions, or formal proof gaps.",
            candidate_tools=["proof_checker"],
            pack="mathematics_pack",
            discipline_tags=["mathematics"],
        ),
        ScientificCapabilitySpec(
            name="counterexample_search",
            description="Search for mathematical counterexamples under bounded assumptions.",
            candidate_tools=["counterexample_search"],
            pack="mathematics_pack",
            discipline_tags=["mathematics"],
        ),
        ScientificCapabilitySpec(
            name="chemistry_safety_review",
            description="Review chemical hazards, safety envelopes, and execution constraints.",
            candidate_tools=["chemistry_safety_checker"],
            execution_mode="runtime_policy_checked_review",
            pack="chemistry_pack",
            discipline_tags=["chemistry", "chemical_engineering"],
            requires_approval=True,
        ),
    ]


def build_default_scientific_capability_registry() -> ScientificCapabilityRegistry:
    return ScientificCapabilityRegistry()
