from __future__ import annotations

from .base import ScientificAgent


DISCIPLINE_AGENT_DEFAULTS: dict[str, dict[str, str]] = {
    "general_science": {
        "agent_family": "scientific_agent",
        "experiment_unit": "one approved scientific test",
        "handoff_target": "run_manager",
    },
    "artificial_intelligence": {
        "agent_family": "ai_research_agent",
        "experiment_unit": "one reproducible training, evaluation, ablation, or benchmark run",
        "handoff_target": "ai_training_runner",
    },
    "chemistry": {
        "agent_family": "chemistry_research_agent",
        "experiment_unit": "one controlled reaction, synthesis, characterization, or condition-screen run",
        "handoff_target": "domain_lab_adapter",
    },
    "chemical_engineering": {
        "agent_family": "chemical_engineering_research_agent",
        "experiment_unit": "one process run, simulation, or operating-window sweep",
        "handoff_target": "domain_lab_adapter",
    },
    "physics": {
        "agent_family": "physics_research_agent",
        "experiment_unit": "one calibrated measurement, simulation, or parameter sweep",
        "handoff_target": "domain_lab_adapter",
    },
    "mathematics": {
        "agent_family": "mathematics_research_agent",
        "experiment_unit": "one proof attempt, formalization step, search run, or counterexample test",
        "handoff_target": "proof_search_adapter",
    },
}


DISCIPLINE_ALIASES: dict[str, str] = {
    "ai": "artificial_intelligence",
    "artificial_intelligence": "artificial_intelligence",
    "kaggle": "artificial_intelligence",
    "kaggle_competition": "artificial_intelligence",
    "chemistry": "chemistry",
    "chemical_engineering": "chemical_engineering",
    "physics": "physics",
    "mathematics": "mathematics",
    "math": "mathematics",
}


class ProfiledScientificAgent(ScientificAgent):
    """Generic scientific agent whose semantics come from DisciplineProfile."""

    def __init__(self, discipline: str = "general_science") -> None:
        normalized = normalize_discipline(discipline)
        defaults = DISCIPLINE_AGENT_DEFAULTS.get(normalized, DISCIPLINE_AGENT_DEFAULTS["general_science"])
        self.discipline = normalized
        self.agent_family = defaults["agent_family"]
        self.experiment_unit = defaults["experiment_unit"]
        self.handoff_target = defaults["handoff_target"]


def build_discipline_agent(discipline: str) -> ScientificAgent:
    return ProfiledScientificAgent(normalize_discipline(discipline))


def normalize_discipline(discipline: str) -> str:
    normalized = discipline.strip().lower()
    return DISCIPLINE_ALIASES.get(normalized, normalized or "general_science")


