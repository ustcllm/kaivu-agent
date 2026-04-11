from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def format_citation(citation: dict[str, Any]) -> str:
    authors = ", ".join(citation.get("authors", [])[:4])
    title = citation.get("title") or "Untitled"
    journal = citation.get("journal") or citation.get("source_type") or "unknown source"
    published = citation.get("published") or "n.d."
    doi = citation.get("doi")
    url = citation.get("url")
    tail = doi or url or ""
    bits = [part for part in [authors, f'"{title}"', journal, published, tail] if part]
    return " | ".join(bits)


def _render_claims(parsed_output: dict[str, Any]) -> list[str]:
    claims = parsed_output.get("claims", [])
    if not isinstance(claims, list) or not claims:
        return []
    lines = ["Claims:", ""]
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        statement = claim.get("statement", "")
        claim_id = claim.get("claim_id", "")
        claim_type = claim.get("claim_type", "")
        confidence = claim.get("confidence", "")
        supports = ", ".join(claim.get("supports", []))
        direction = claim.get("evidence_direction", "")
        boundary_conditions = ", ".join(claim.get("boundary_conditions", []))
        failure_modes = ", ".join(claim.get("failure_modes", []))
        lines.append(
            f"- {claim_id} [{claim_type}/{direction}] ({confidence}): {statement}"
            + (f" | evidence: {supports}" if supports else "")
            + (f" | boundary: {boundary_conditions}" if boundary_conditions else "")
            + (f" | failure: {failure_modes}" if failure_modes else "")
        )
    lines.append("")
    return lines


def _render_evidence(parsed_output: dict[str, Any]) -> list[str]:
    evidence = parsed_output.get("evidence", [])
    if not isinstance(evidence, list) or not evidence:
        return []
    lines = ["Evidence:", ""]
    for item in evidence:
        if not isinstance(item, dict):
            continue
        limitations = ", ".join(item.get("limitations", []))
        lines.append(
            f"- {item.get('evidence_id', '')} "
            f"[{item.get('evidence_kind', '')}/{item.get('study_type', '')}/{item.get('strength', '')}] "
            f"{item.get('summary', '')} | source: {item.get('source_ref', '')}"
            + (f" | quality: {item.get('quality_grade', '')}" if item.get("quality_grade") else "")
            + (f" | bias: {item.get('bias_risk', '')}" if item.get("bias_risk") else "")
            + (f" | model: {item.get('model_system', '')}" if item.get("model_system") else "")
            + (f" | direction: {item.get('evidence_direction', '')}" if item.get("evidence_direction") else "")
            + (f" | applicability: {item.get('applicability', '')}" if item.get("applicability") else "")
            + (f" | conflict_group: {item.get('conflict_group', '')}" if item.get("conflict_group") else "")
            + (f" | conflict_note: {item.get('conflict_note', '')}" if item.get("conflict_note") else "")
            + (f" | limitations: {limitations}" if limitations else "")
        )
    lines.append("")
    return lines


def _render_uncertainties(parsed_output: dict[str, Any]) -> list[str]:
    uncertainties = parsed_output.get("uncertainties", [])
    if not isinstance(uncertainties, list) or not uncertainties:
        return []
    lines = ["Uncertainties:", ""]
    for item in uncertainties:
        if isinstance(item, dict):
            lines.append(
                f"- {item.get('issue', '')} | impact: {item.get('impact', '')} | next: {item.get('next_action', '')}"
            )
        else:
            lines.append(f"- {item}")
    lines.append("")
    return lines


def _render_negative_results(parsed_output: dict[str, Any]) -> list[str]:
    negative_results = parsed_output.get("negative_results", [])
    if not isinstance(negative_results, list) or not negative_results:
        return []
    lines = ["Negative Results And Failed Attempts:", ""]
    for item in negative_results:
        if not isinstance(item, dict):
            continue
        affected = ", ".join(item.get("affected_hypothesis_ids", []))
        lines.append(
            f"- {item.get('result', '')} | why: {item.get('why_it_failed_or_did_not_support', '')} | implication: {item.get('implication', '')}"
            + (f" | challenges: {affected}" if affected else "")
        )
    lines.append("")
    return lines


def _render_stage_assessment(parsed_output: dict[str, Any]) -> list[str]:
    stage = parsed_output.get("stage_assessment", {})
    if not isinstance(stage, dict) or not stage:
        return []
    blockers = ", ".join(stage.get("stage_blockers", []))
    allowed_next = ", ".join(stage.get("allowed_next_stages", []))
    missing = ", ".join(stage.get("missing_prerequisites", []))
    lines = [
        "Stage Assessment:",
        "",
        f"- current stage: {stage.get('current_stage', 'unknown')}",
        f"- next stage: {stage.get('next_stage', 'unknown')}",
        f"- stage goal: {stage.get('stage_goal', 'unknown')}",
    ]
    if allowed_next:
        lines.append(f"- allowed next stages: {allowed_next}")
    if missing:
        lines.append(f"- missing prerequisites: {missing}")
    if blockers:
        lines.append(f"- blockers: {blockers}")
    lines.append("")
    return lines


def _render_hypotheses(parsed_output: dict[str, Any]) -> list[str]:
    hypotheses = parsed_output.get("hypotheses", [])
    if not isinstance(hypotheses, list) or not hypotheses:
        return []
    lines = ["Hypothesis Versions:", ""]
    for item in hypotheses:
        if not isinstance(item, dict):
            continue
        challenge_count = item.get("challenge_count", 0)
        auto_note = " | workflow-updated" if item.get("status_updated_by_workflow") else ""
        lines.append(
            f"- {item.get('hypothesis_id', '')} v{item.get('version', '')} [{item.get('status', '')}] "
            f"{item.get('name', '')} | prediction: {item.get('prediction', '')} | falsify via: {item.get('falsifiability_test', '')}"
            + (f" | challenge_count: {challenge_count}" if challenge_count else "")
            + auto_note
        )
    lines.append("")
    return lines


def _render_scientific_meta_from_state(research_state: dict[str, Any]) -> list[str]:
    if not research_state:
        return []
    lines: list[str] = []
    autonomy = research_state.get("autonomy_summary", {})
    if autonomy:
        lines.extend(["## Autonomous Research Control", ""])
        lines.append(f"- current objective: {autonomy.get('current_objective', '')}")
        lines.append(f"- autonomy state: {autonomy.get('autonomy_state', 'unknown')}")
        if autonomy.get("active_workstreams"):
            lines.append("- active workstreams:")
            lines.extend(f"  - {item}" for item in autonomy.get("active_workstreams", []))
        if autonomy.get("autonomous_next_actions"):
            lines.append("- autonomous next actions:")
            lines.extend(f"  - {item}" for item in autonomy.get("autonomous_next_actions", []))
        if autonomy.get("monitoring_signals"):
            lines.append("- monitoring signals:")
            lines.extend(f"  - {item}" for item in autonomy.get("monitoring_signals", []))
        if autonomy.get("handoff_points"):
            lines.append("- handoff points:")
            lines.extend(f"  - {item}" for item in autonomy.get("handoff_points", []))
        lines.append("")

    autonomous_controller = research_state.get("autonomous_controller_summary", {})
    if autonomous_controller:
        lines.extend(["## Autonomous Research Controller", ""])
        lines.append(f"- controller state: {autonomous_controller.get('controller_state', '')}")
        lines.append(f"- loop decision: {autonomous_controller.get('loop_decision', '')}")
        lines.append(f"- next cycle stage: {autonomous_controller.get('next_cycle_stage', '')}")
        lines.append(f"- next cycle action: {autonomous_controller.get('next_cycle_action', '')}")
        lines.append(
            f"- can continue autonomously: {autonomous_controller.get('can_continue_autonomously', False)}"
        )
        lines.append(
            f"- must pause for human: {autonomous_controller.get('must_pause_for_human', False)}"
        )
        if autonomous_controller.get("recommended_agents"):
            lines.append("- recommended agents:")
            lines.extend(f"  - {item}" for item in autonomous_controller.get("recommended_agents", []))
        if autonomous_controller.get("pause_reasons"):
            lines.append("- pause reasons:")
            lines.extend(f"  - {item}" for item in autonomous_controller.get("pause_reasons", []))
        if autonomous_controller.get("required_inputs"):
            lines.append("- required inputs:")
            lines.extend(f"  - {item}" for item in autonomous_controller.get("required_inputs", []))
        if autonomous_controller.get("safety_gates"):
            lines.append("- safety gates:")
            lines.extend(f"  - {item}" for item in autonomous_controller.get("safety_gates", []))
        if autonomous_controller.get("continuation_budget"):
            lines.append(
                f"- continuation budget: {json.dumps(autonomous_controller.get('continuation_budget', {}), ensure_ascii=False)}"
            )
        lines.append("")

    research_plan = research_state.get("research_plan_summary", {})
    if research_plan:
        lines.extend(["## Research Plan", ""])
        lines.append(f"- planning horizon: {research_plan.get('planning_horizon', 'unknown')}")
        lines.append(f"- recommended stage gate: {research_plan.get('recommended_stage_gate', 'unknown')}")
        if research_plan.get("priority_questions"):
            lines.append("- priority questions:")
            lines.extend(f"  - {item}" for item in research_plan.get("priority_questions", []))
        if research_plan.get("next_cycle_experiments"):
            lines.append("- next cycle experiments:")
            lines.extend(f"  - {item}" for item in research_plan.get("next_cycle_experiments", []))
        if research_plan.get("decision_gates"):
            lines.append("- decision gates:")
            lines.extend(f"  - {item}" for item in research_plan.get("decision_gates", []))
        if research_plan.get("stop_conditions"):
            lines.append("- stop conditions:")
            lines.extend(f"  - {item}" for item in research_plan.get("stop_conditions", []))
        if research_plan.get("strategy_memory_candidates"):
            lines.append("- strategy memory candidates:")
            lines.extend(f"  - {item}" for item in research_plan.get("strategy_memory_candidates", []))
        lines.append("")

    program_management = research_state.get("program_management_summary", {})
    if program_management:
        lines.extend(["## Program Management", ""])
        lines.append(f"- program objective: {program_management.get('program_objective', '')}")
        lines.append(f"- primary workstream: {program_management.get('primary_workstream', '')}")
        lines.append(f"- review cadence: {program_management.get('review_cadence', '')}")
        lines.append(f"- route temperature: {program_management.get('route_temperature', '')}")
        if program_management.get("secondary_workstreams"):
            lines.append("- secondary workstreams:")
            lines.extend(f"  - {item}" for item in program_management.get("secondary_workstreams", []))
        if program_management.get("milestones"):
            lines.append("- milestones:")
            lines.extend(f"  - {item}" for item in program_management.get("milestones", []))
        if program_management.get("resource_allocations"):
            lines.append("- resource allocations:")
            lines.extend(f"  - {item}" for item in program_management.get("resource_allocations", []))
        if program_management.get("pivot_triggers"):
            lines.append("- pivot triggers:")
            lines.extend(f"  - {item}" for item in program_management.get("pivot_triggers", []))
        lines.append("")

    program_portfolio = research_state.get("program_portfolio_summary", {})
    if program_portfolio:
        lines.extend(["## Program Portfolio", ""])
        lines.append(f"- portfolio pressure: {program_portfolio.get('portfolio_pressure', 'unknown')}")
        lines.append(f"- cost pressure: {program_portfolio.get('cost_pressure', 'medium')}")
        if program_portfolio.get("active_routes"):
            lines.append("- active routes:")
            lines.extend(f"  - {item}" for item in program_portfolio.get("active_routes", []))
        if program_portfolio.get("exploratory_routes"):
            lines.append("- exploratory routes:")
            lines.extend(f"  - {item}" for item in program_portfolio.get("exploratory_routes", []))
        if program_portfolio.get("paused_routes"):
            lines.append("- paused routes:")
            lines.extend(f"  - {item}" for item in program_portfolio.get("paused_routes", []))
        if program_portfolio.get("retired_routes"):
            lines.append("- retired routes:")
            lines.extend(f"  - {item}" for item in program_portfolio.get("retired_routes", []))
        lines.append("")

    termination = research_state.get("termination_strategy_summary", {})
    if termination:
        lines.extend(["## Route Termination Strategy", ""])
        lines.append(f"- recommended action: {termination.get('recommended_action', 'continue')}")
        lines.append(
            f"- human confirmation required: {termination.get('human_confirmation_required', False)}"
        )
        if termination.get("stop_condition_hits"):
            lines.append("- stop condition hits:")
            lines.extend(f"  - {item}" for item in termination.get("stop_condition_hits", []))
        if termination.get("termination_condition_hits"):
            lines.append("- termination condition hits:")
            lines.extend(
                f"  - {item}" for item in termination.get("termination_condition_hits", [])
            )
        if termination.get("paused_workstreams"):
            lines.append("- paused workstreams:")
            lines.extend(
                f"  - {item.get('workstream', '')}: {item.get('reason', '')}"
                for item in termination.get("paused_workstreams", [])
                if isinstance(item, dict)
            )
        if termination.get("retired_routes"):
            lines.append("- retired or retiring routes:")
            lines.extend(
                f"  - {item.get('route_id', '')} [{item.get('status', '')}]: {item.get('reason', '')}"
                for item in termination.get("retired_routes", [])
                if isinstance(item, dict)
            )
        if termination.get("human_confirmation_reasons"):
            lines.append("- human confirmation reasons:")
            lines.extend(
                f"  - {item}" for item in termination.get("human_confirmation_reasons", [])
            )
        lines.append("")

    human_governance = research_state.get("human_governance_checkpoint_summary", {})
    if human_governance:
        lines.extend(["## Human Governance Checkpoints", ""])
        lines.append(
            f"- governance state: {human_governance.get('governance_state', 'clear')}"
        )
        lines.append(
            f"- must pause execution: {human_governance.get('must_pause_execution', False)}"
        )
        if human_governance.get("approval_scope"):
            lines.append("- approval scope:")
            lines.extend(f"  - {item}" for item in human_governance.get("approval_scope", []))
        if human_governance.get("checkpoint_reasons"):
            lines.append("- checkpoint reasons:")
            lines.extend(
                f"  - {item}" for item in human_governance.get("checkpoint_reasons", [])
            )
        if human_governance.get("required_roles"):
            lines.append("- required roles:")
            lines.extend(f"  - {item}" for item in human_governance.get("required_roles", []))
        lines.append("")

    literature = research_state.get("literature_synthesis", {})
    if literature:
        lines.extend(["## Literature Synthesis", ""])
        if literature.get("consensus_findings"):
            lines.append("Consensus findings:")
            lines.extend(f"- {item}" for item in literature.get("consensus_findings", []))
            lines.append("")
        if literature.get("contested_questions"):
            lines.append("Contested questions:")
            lines.extend(f"- {item}" for item in literature.get("contested_questions", []))
            lines.append("")
        if literature.get("evidence_gaps"):
            lines.append("Evidence gaps:")
            lines.extend(f"- {item}" for item in literature.get("evidence_gaps", []))
            lines.append("")

    systematic = research_state.get("systematic_review_summary", {})
    if systematic:
        lines.extend(["## Systematic Review Summary", ""])
        lines.append(f"- review question: {systematic.get('review_question', '')}")
        lines.append(f"- review protocol version: {systematic.get('review_protocol_version', 'draft-v1')}")
        lines.append(f"- screened evidence count: {systematic.get('screened_evidence_count', 0)}")
        if systematic.get("study_type_hierarchy"):
            lines.append("- study hierarchy:")
            lines.extend(f"  - {item}" for item in systematic.get("study_type_hierarchy", []))
        if systematic.get("study_type_counts"):
            lines.append(
                f"- study type counts: {json.dumps(systematic.get('study_type_counts', {}), ensure_ascii=False)}"
            )
        if systematic.get("inclusion_logic"):
            lines.append("- inclusion logic:")
            lines.extend(f"  - {item}" for item in systematic.get("inclusion_logic", []))
        if systematic.get("exclusion_logic"):
            lines.append("- exclusion logic:")
            lines.extend(f"  - {item}" for item in systematic.get("exclusion_logic", []))
        if systematic.get("screening_decisions"):
            lines.append("- screening decisions:")
            lines.extend(f"  - {item}" for item in systematic.get("screening_decisions", []))
        if systematic.get("exclusion_reasons"):
            lines.append("- exclusion reasons:")
            lines.extend(f"  - {item}" for item in systematic.get("exclusion_reasons", []))
        if systematic.get("evidence_balance"):
            lines.append("- evidence balance:")
            lines.extend(f"  - {item}" for item in systematic.get("evidence_balance", []))
        if systematic.get("bias_hotspots"):
            lines.append("- bias hotspots:")
            lines.extend(f"  - {item}" for item in systematic.get("bias_hotspots", []))
        if systematic.get("evidence_table_focus"):
            lines.append("- evidence table focus:")
            lines.extend(f"  - {item}" for item in systematic.get("evidence_table_focus", []))
        if systematic.get("evidence_table_records"):
            lines.append("- evidence table records:")
            lines.extend(f"  - {item}" for item in systematic.get("evidence_table_records", [])[:8])
    if systematic.get("review_protocol_gaps"):
        lines.append("- review protocol gaps:")
        lines.extend(f"  - {item}" for item in systematic.get("review_protocol_gaps", []))
    lines.append("")

    evidence_review = research_state.get("evidence_review_summary", {})
    if evidence_review:
        lines.extend(["## Evidence Review Engine", ""])
        lines.append(f"- review readiness: {evidence_review.get('review_readiness', 'draft')}")
        lines.append(f"- review quality state: {evidence_review.get('review_quality_state', 'needs_review')}")
        lines.append(f"- protocol completeness score: {evidence_review.get('protocol_completeness_score', 0)}")
        lines.append(f"- screening quality score: {evidence_review.get('screening_quality_score', 0)}")
        lines.append(
            f"- evidence grade balance: {json.dumps(evidence_review.get('evidence_grade_balance', {}), ensure_ascii=False)}"
        )
        bias_summary = evidence_review.get("bias_risk_summary", {})
        if bias_summary:
            lines.append(
                f"- bias risk counts: {json.dumps(bias_summary.get('risk_counts', {}), ensure_ascii=False)}"
            )
            if bias_summary.get("bias_hotspots"):
                lines.append("- bias hotspots:")
                lines.extend(f"  - {item}" for item in bias_summary.get("bias_hotspots", []))
        lines.append(f"- conflict resolution state: {evidence_review.get('conflict_resolution_state', 'none')}")
        if evidence_review.get("review_blockers"):
            lines.append("- review blockers:")
            lines.extend(f"  - {item}" for item in evidence_review.get("review_blockers", []))
        if evidence_review.get("recommended_review_actions"):
            lines.append("- recommended review actions:")
            lines.extend(f"  - {item}" for item in evidence_review.get("recommended_review_actions", []))
        lines.append("")

    formal_review = research_state.get("formal_review_record_summary", {})
    if formal_review:
        lines.extend(["## Formal Review Records", ""])
        lines.append(f"- review protocol version: {formal_review.get('review_protocol_version', '')}")
        lines.append(f"- screening record count: {formal_review.get('screening_record_count', 0)}")
        lines.append(f"- evidence table record count: {formal_review.get('evidence_table_record_count', 0)}")
        lines.append(f"- review update count: {formal_review.get('review_update_count', 0)}")
        if formal_review.get("screening_records"):
            lines.append("- screening records:")
            lines.extend(f"  - {item}" for item in formal_review.get("screening_records", []))
        if formal_review.get("evidence_table_records"):
            lines.append("- evidence table records:")
            lines.extend(f"  - {item}" for item in formal_review.get("evidence_table_records", []))
        lines.append("")

    domain_playbook = research_state.get("domain_playbook_summary", {})
    if domain_playbook:
        lines.extend(["## Domain Playbooks", ""])
        lines.append(f"- primary discipline: {domain_playbook.get('primary_discipline', '')}")
        lines.append(f"- playbook count: {domain_playbook.get('playbook_count', 0)}")
        if domain_playbook.get("execution_patterns"):
            lines.append("- execution patterns:")
            lines.extend(f"  - {item}" for item in domain_playbook.get("execution_patterns", []))
        if domain_playbook.get("validation_patterns"):
            lines.append("- validation patterns:")
            lines.extend(f"  - {item}" for item in domain_playbook.get("validation_patterns", []))
        if domain_playbook.get("failure_modes"):
            lines.append("- domain failure modes:")
            lines.extend(f"  - {item}" for item in domain_playbook.get("failure_modes", []))
        lines.append("")

    causal = research_state.get("causal_reasoning", {})
    if causal:
        lines.extend(["## Causal And Confounder Reasoning", ""])
        for label, key in [
            ("Causal assumptions", "causal_assumptions"),
            ("Priority confounders", "priority_confounders"),
            ("Alternative explanations", "alternative_explanations"),
            ("Identification strategies", "identification_strategies"),
        ]:
            values = causal.get(key, [])
            if values:
                lines.append(f"{label}:")
                lines.extend(f"- {item}" for item in values)
                lines.append("")

    causal_graph = research_state.get("causal_graph_summary", {})
    if causal_graph:
        lines.extend(["## Causal Graph Summary", ""])
        lines.append(
            f"- nodes: {causal_graph.get('node_count', 0)} | edges: {causal_graph.get('edge_count', 0)} | confounders: {causal_graph.get('confounder_count', 0)}"
        )
        if causal_graph.get("competing_mechanisms"):
            lines.append("- competing mechanisms:")
            lines.extend(f"  - {item}" for item in causal_graph.get("competing_mechanisms", []))
        if causal_graph.get("counterfactual_queries"):
            lines.append("- counterfactual queries:")
            lines.extend(f"  - {item}" for item in causal_graph.get("counterfactual_queries", []))
        if causal_graph.get("counterfactual_experiments"):
            lines.append("- counterfactual experiments:")
            lines.extend(f"  - {item}" for item in causal_graph.get("counterfactual_experiments", []))
        if causal_graph.get("mechanism_nodes"):
            lines.append("- mechanism nodes:")
            lines.extend(f"  - {item}" for item in causal_graph.get("mechanism_nodes", [])[:8])
        if causal_graph.get("identifiability_risks"):
            lines.append("- identifiability risks:")
            lines.extend(f"  - {item}" for item in causal_graph.get("identifiability_risks", []))
        for item in causal_graph.get("edges", [])[:12]:
            lines.append(
                f"- {item.get('source', '')} -> {item.get('target', '')} [{item.get('relation', '')}]"
            )
        lines.append("")

    discipline = research_state.get("discipline_adaptation_summary", {})
    if discipline:
        lines.extend(["## Discipline Adaptation", ""])
        lines.append(f"- primary discipline: {discipline.get('primary_discipline', 'unknown')}")
        if discipline.get("secondary_disciplines"):
            lines.append(f"- secondary disciplines: {', '.join(discipline.get('secondary_disciplines', []))}")
        if discipline.get("execution_modes"):
            lines.append(f"- execution modes: {', '.join(discipline.get('execution_modes', []))}")
        if discipline.get("adapter_requirements"):
            lines.append("- adapter requirements:")
            lines.extend(f"  - {item}" for item in discipline.get("adapter_requirements", []))
        if discipline.get("validation_norms"):
            lines.append("- validation norms:")
            lines.extend(f"  - {item}" for item in discipline.get("validation_norms", []))
        if discipline.get("discipline_specific_risks"):
            lines.append("- discipline-specific risks:")
            lines.extend(f"  - {item}" for item in discipline.get("discipline_specific_risks", []))
        if discipline.get("artifact_expectations"):
            lines.append("- artifact expectations:")
            lines.extend(f"  - {item}" for item in discipline.get("artifact_expectations", []))
        if discipline.get("artifact_governance_requirements"):
            lines.append("- artifact governance requirements:")
            lines.extend(
                f"  - {item}"
                for item in discipline.get("artifact_governance_requirements", [])
            )
        lines.append("")

    analysis = research_state.get("analysis_rigor", {})
    if analysis:
        lines.extend(["## Analysis Rigor", ""])
        for label, key in [
            ("Power analysis notes", "power_analysis_notes"),
            ("Sensitivity checks", "sensitivity_checks"),
            ("Model comparisons", "model_comparisons"),
            ("Missing-data strategies", "missing_data_strategies"),
        ]:
            values = analysis.get(key, [])
            if values:
                lines.append(f"{label}:")
                lines.extend(f"- {item}" for item in values)
                lines.append("")

    experiment_governance = research_state.get("experiment_governance_summary", {})
    if experiment_governance:
        lines.extend(["## Experiment Governance", ""])
        lines.append(
            f"- approval gate needed: {experiment_governance.get('approval_gate_needed', False)}"
        )
        if experiment_governance.get("run_status_counts"):
            lines.append(
                f"- run status counts: {json.dumps(experiment_governance.get('run_status_counts', {}), ensure_ascii=False)}"
            )
        if experiment_governance.get("quarantine_runs"):
            lines.append("- quarantine runs:")
            lines.extend(f"  - {item}" for item in experiment_governance.get("quarantine_runs", []))
        if experiment_governance.get("rerun_candidates"):
            lines.append("- rerun candidates:")
            lines.extend(f"  - {item}" for item in experiment_governance.get("rerun_candidates", []))
        if experiment_governance.get("governance_risks"):
            lines.append("- governance risks:")
            lines.extend(f"  - {item}" for item in experiment_governance.get("governance_risks", []))
        lines.append("")

    experiment_economics = research_state.get("experiment_economics_summary", {})
    if experiment_economics:
        lines.extend(["## Experiment Economics", ""])
        lines.append(
            f"- cost pressure: {experiment_economics.get('cost_pressure', 'medium')} | time pressure: {experiment_economics.get('time_pressure', 'medium')}"
        )
        lines.append(
            f"- information gain pressure: {experiment_economics.get('information_gain_pressure', 'medium')}"
        )
        if experiment_economics.get("cheapest_discriminative_actions"):
            lines.append("- cheapest discriminative actions:")
            lines.extend(
                f"  - {item}"
                for item in experiment_economics.get("cheapest_discriminative_actions", [])
            )
        if experiment_economics.get("resource_risks"):
            lines.append("- resource risks:")
            lines.extend(f"  - {item}" for item in experiment_economics.get("resource_risks", []))
        if experiment_economics.get("defer_candidates"):
            lines.append("- defer candidates:")
            lines.extend(f"  - {item}" for item in experiment_economics.get("defer_candidates", []))
        if experiment_economics.get("expected_information_gain"):
            lines.append("- expected information gain:")
            lines.extend(
                f"  - {item}" for item in experiment_economics.get("expected_information_gain", [])
            )
        lines.append("")

    experiment_scheduler = research_state.get("experiment_execution_loop_summary", {})
    if experiment_scheduler:
        lines.extend(["## Experiment Execution Loop", ""])
        lines.append(f"- scheduler state: {experiment_scheduler.get('scheduler_state', '')}")
        lines.append(f"- top experiment id: {experiment_scheduler.get('top_experiment_id', '')}")
        lines.append(f"- top action: {experiment_scheduler.get('top_action', '')}")
        lines.append(f"- candidate count: {experiment_scheduler.get('candidate_count', 0)}")
        lines.append(
            f"- parameter optimization supported: {experiment_scheduler.get('parameter_optimization_supported', False)}"
        )
        search = experiment_scheduler.get("mcts_like_search", {})
        if search:
            lines.append(
                f"- mcts-like search: candidates={search.get('candidate_count', 0)} expanded_nodes={search.get('expanded_node_count', 0)} uncertainty_reduction={search.get('uncertainty_reduction_estimate', 0)}"
            )
            if search.get("best_path"):
                lines.append(f"- best path: {' -> '.join(search.get('best_path', []))}")
        if experiment_scheduler.get("execution_queue"):
            lines.append("- execution queue:")
            for item in experiment_scheduler.get("execution_queue", [])[:6]:
                if isinstance(item, dict):
                    lines.append(
                        f"  - {item.get('experiment_id', '')}: {item.get('action', '')} | score={item.get('portfolio_score', '')}"
                    )
        if experiment_scheduler.get("blocked_experiments"):
            lines.append("- blocked experiments:")
            for item in experiment_scheduler.get("blocked_experiments", [])[:6]:
                if isinstance(item, dict):
                    lines.append(
                        f"  - {item.get('experiment_id', '')}: gate={item.get('gate_state', '')}"
                    )
        lines.append("")

    optimization_adapter = research_state.get("optimization_adapter_summary", {})
    if optimization_adapter:
        lines.extend(["## Optimization Adapter", ""])
        lines.append(f"- adapter state: {optimization_adapter.get('adapter_state', '')}")
        lines.append(f"- optimization candidates: {optimization_adapter.get('optimization_candidate_count', 0)}")
        lines.append(f"- plan count: {optimization_adapter.get('plan_count', 0)}")
        boundary = optimization_adapter.get("execution_boundary", {})
        if boundary:
            lines.append(
                f"- execution boundary: {boundary.get('adapter_role', '')}; does not execute heavy jobs={boundary.get('does_not_execute_heavy_jobs', True)}"
            )
        if optimization_adapter.get("plans"):
            lines.append("- tuning plans:")
            for plan in optimization_adapter.get("plans", [])[:5]:
                if isinstance(plan, dict):
                    lines.append(
                        f"  - {plan.get('plan_id', '')}: strategy={plan.get('search_strategy', '')} trials={len(plan.get('exploratory_trials', []))}"
                    )
                    lines.append(
                        f"    confirmatory: {json.dumps(plan.get('confirmatory_protocol', {}), ensure_ascii=False)}"
                    )
        if optimization_adapter.get("best_config_candidates"):
            lines.append("- best config candidates:")
            lines.extend(
                f"  - {json.dumps(item, ensure_ascii=False)}"
                for item in optimization_adapter.get("best_config_candidates", [])[:5]
                if isinstance(item, dict)
            )
        lines.append("")

    execution_registry = research_state.get("execution_adapter_registry_summary", {})
    discipline_adapter = research_state.get("discipline_adapter_summary", {})
    if discipline_adapter:
        lines.extend(["## Discipline Adapters", ""])
        lines.append(f"- adapter state: {discipline_adapter.get('adapter_state', '')}")
        lines.append(f"- primary discipline: {discipline_adapter.get('primary_discipline', '')}")
        lines.append(f"- selected adapter: {discipline_adapter.get('selected_adapter_id', '')}")
        lines.append(f"- bindings: {discipline_adapter.get('binding_count', 0)}")
        lines.append(f"- blocked bindings: {discipline_adapter.get('blocked_binding_count', 0)}")
        boundary = discipline_adapter.get("execution_boundary", {})
        if isinstance(boundary, dict):
            lines.append(
                f"- boundary: {boundary.get('mode', '')}; explicit approval={boundary.get('requires_explicit_execution_approval', True)}"
            )
        if discipline_adapter.get("bindings"):
            lines.append("- bindings:")
            for binding in discipline_adapter.get("bindings", [])[:6]:
                if isinstance(binding, dict):
                    lines.append(
                        f"  - {binding.get('binding_id', '')}: experiment={binding.get('experiment_id', '')} state={binding.get('readiness_state', '')}"
                    )
                    if binding.get("failure_modes_to_watch"):
                        lines.append(
                            f"    failure modes: {', '.join(binding.get('failure_modes_to_watch', [])[:4])}"
                        )
                    if binding.get("scheduler_rules"):
                        lines.append(
                            f"    scheduler rules: {', '.join(binding.get('scheduler_rules', [])[:3])}"
                        )
        lines.append("")

    if execution_registry:
        lines.extend(["## Execution Adapter Registry", ""])
        lines.append(f"- registry state: {execution_registry.get('registry_state', '')}")
        lines.append(f"- primary discipline: {execution_registry.get('primary_discipline', '')}")
        lines.append(f"- selected adapter: {execution_registry.get('selected_adapter_id', '')}")
        lines.append(f"- execution packages: {execution_registry.get('execution_package_count', 0)}")
        lines.append(f"- ready packages: {execution_registry.get('ready_package_count', 0)}")
        lines.append(f"- blocked packages: {execution_registry.get('blocked_package_count', 0)}")
        if execution_registry.get("execution_packages"):
            lines.append("- packages:")
            for package in execution_registry.get("execution_packages", [])[:6]:
                if isinstance(package, dict):
                    lines.append(
                        f"  - {package.get('package_id', '')}: state={package.get('package_state', '')} handoff={package.get('handoff_target', '')}"
                    )
                    if package.get("blocked_reasons"):
                        lines.append(
                            f"    blocked: {', '.join(package.get('blocked_reasons', []))}"
                    )
        lines.append("")

    run_handoff = research_state.get("run_handoff_contract_summary", {})
    if run_handoff:
        lines.extend(["## Run Handoff Contract", ""])
        lines.append(f"- contract state: {run_handoff.get('contract_state', '')}")
        lines.append(f"- contract count: {run_handoff.get('contract_count', 0)}")
        lines.append(f"- normalization function: {run_handoff.get('normalization_function', '')}")
        if run_handoff.get("return_contract"):
            lines.append(
                f"- return contract: {json.dumps(run_handoff.get('return_contract', {}), ensure_ascii=False)}"
            )
        if run_handoff.get("contracts"):
            lines.append("- contract items:")
            for contract in run_handoff.get("contracts", [])[:6]:
                if isinstance(contract, dict):
                    lines.append(
                        f"  - {contract.get('contract_id', '')}: experiment={contract.get('experiment_id', '')}"
                    )
                    if contract.get("required_payload_fields"):
                        lines.append(
                            f"    required fields: {', '.join(contract.get('required_payload_fields', []))}"
                        )
        lines.append("")

    consensus = research_state.get("consensus_state", {})
    if consensus:
        lines.extend(["## Consensus State", ""])
        lines.append(f"- status: {consensus.get('consensus_status', 'partial')}")
        if consensus.get("agreed_points"):
            lines.append("- agreed points:")
            lines.extend(f"  - {item}" for item in consensus.get("agreed_points", []))
        if consensus.get("unresolved_points"):
            lines.append("- unresolved points:")
            lines.extend(f"  - {item}" for item in consensus.get("unresolved_points", []))
        lines.append("")

    consensus_machine = research_state.get("consensus_state_machine", {})
    if consensus_machine:
        lines.extend(["## Consensus State Machine", ""])
        lines.append(f"- current state: {consensus_machine.get('current_state', 'unknown')}")
        lines.append(f"- previous state: {consensus_machine.get('previous_state', 'unknown')}")
        lines.append(f"- suggested action: {consensus_machine.get('suggested_action', 'unknown')}")
        lines.append(f"- freeze recommendation: {consensus_machine.get('freeze_recommendation', False)}")
        if consensus_machine.get("transition_triggers"):
            lines.append("- transition triggers:")
            lines.extend(f"  - {item}" for item in consensus_machine.get("transition_triggers", []))
        lines.append("")

    lab_meeting = research_state.get("lab_meeting_consensus_summary", {})
    if lab_meeting:
        lines.extend(["## Lab Meeting Consensus", ""])
        lines.append(f"- meeting state: {lab_meeting.get('meeting_state', 'forming')}")
        lines.append(
            f"- chair recommendation: {lab_meeting.get('chair_recommendation', 'collect_discriminative_evidence')}"
        )
        if lab_meeting.get("decision_rule"):
            lines.append(f"- decision rule: {lab_meeting.get('decision_rule', '')}")
        if lab_meeting.get("agenda_items"):
            lines.append("- agenda items:")
            lines.extend(f"  - {item}" for item in lab_meeting.get("agenda_items", []))
        if lab_meeting.get("position_summaries"):
            lines.append("- position summaries:")
            lines.extend(f"  - {item}" for item in lab_meeting.get("position_summaries", []))
        if lab_meeting.get("evidence_needed_to_close"):
            lines.append("- evidence needed to close disagreement:")
            lines.extend(f"  - {item}" for item in lab_meeting.get("evidence_needed_to_close", []))
        if lab_meeting.get("blocking_concerns"):
            lines.append("- blocking concerns:")
            lines.extend(f"  - {item}" for item in lab_meeting.get("blocking_concerns", []))
        if lab_meeting.get("provisional_decisions"):
            lines.append("- provisional decisions:")
            lines.extend(f"  - {item}" for item in lab_meeting.get("provisional_decisions", []))
        lines.append("")

    hypothesis_tree = research_state.get("hypothesis_tree_summary", {})
    if hypothesis_tree:
        lines.extend(["## Hypothesis Tree", ""])
        lines.append(f"- hypothesis count: {hypothesis_tree.get('hypothesis_count', 0)}")
        lines.append(f"- relation count: {hypothesis_tree.get('relation_count', 0)}")
        if hypothesis_tree.get("relation_counts"):
            lines.append(f"- relation counts: {json.dumps(hypothesis_tree.get('relation_counts', {}), ensure_ascii=False)}")
        if hypothesis_tree.get("root_hypotheses"):
            lines.append(f"- root hypotheses: {', '.join(hypothesis_tree.get('root_hypotheses', []))}")
        lines.append("")

    systematic_summary = research_state.get("systematic_review_summary", {})
    systematic_engine = (
        systematic_summary.get("engine", {})
        if isinstance(systematic_summary, dict) and isinstance(systematic_summary.get("engine", {}), dict)
        else {}
    )
    if systematic_engine:
        lines.extend(["## Systematic Review", ""])
        lines.append(f"- synthesis state: {systematic_engine.get('synthesis_state', '')}")
        lines.append(f"- protocol state: {systematic_engine.get('protocol_state', '')}")
        lines.append(
            f"- evidence table: {len(systematic_engine.get('evidence_table', []) if isinstance(systematic_engine.get('evidence_table', []), list) else [])} | conflicts: {len(systematic_engine.get('conflict_matrix', []) if isinstance(systematic_engine.get('conflict_matrix', []), list) else [])}"
        )
        lines.append(f"- meta-analysis readiness: {systematic_engine.get('meta_analysis_readiness', '')}")
        if systematic_engine.get("decision_implications"):
            lines.append("- decision implications:")
            lines.extend(f"  - {item}" for item in systematic_engine.get("decision_implications", [])[:6])
        lines.append("")

    theoretical_tree = research_state.get("theoretical_hypothesis_tree_summary", {})
    if theoretical_tree:
        lines.extend(["## Theoretical Hypothesis Tree", ""])
        lines.append(f"- theory maturity: {theoretical_tree.get('theory_maturity', 'flat')}")
        lines.append(f"- family count: {theoretical_tree.get('family_count', 0)}")
        lines.append(
            f"- parent-child relations: {theoretical_tree.get('parent_child_relation_count', 0)} | mechanism relations: {theoretical_tree.get('mechanism_relation_count', 0)}"
        )
        if theoretical_tree.get("family_status_counts"):
            lines.append(
                f"- family status counts: {json.dumps(theoretical_tree.get('family_status_counts', {}), ensure_ascii=False)}"
            )
        if theoretical_tree.get("challenge_frontier"):
            lines.append("- challenge frontier:")
            lines.extend(f"  - {item}" for item in theoretical_tree.get("challenge_frontier", []))
        if theoretical_tree.get("retire_candidates"):
            lines.append("- retire candidates:")
            lines.extend(f"  - {item}" for item in theoretical_tree.get("retire_candidates", []))
        if theoretical_tree.get("revive_candidates"):
            lines.append("- revive candidates:")
            lines.extend(f"  - {item}" for item in theoretical_tree.get("revive_candidates", []))
        lines.append("")

    mechanism_summary = research_state.get("mechanism_reasoning_summary", {})
    if mechanism_summary:
        lines.extend(["## Mechanism Reasoning", ""])
        lines.append(f"- mechanism count: {mechanism_summary.get('mechanism_count', 0)}")
        if mechanism_summary.get("mechanism_families"):
            lines.append(
                f"- mechanism families: {json.dumps(mechanism_summary.get('mechanism_families', {}), ensure_ascii=False)}"
            )
        if mechanism_summary.get("competing_pairs"):
            lines.append("- competing mechanism pairs:")
            lines.extend(f"  - {item}" for item in mechanism_summary.get("competing_pairs", []))
        if mechanism_summary.get("counterfactual_experiments"):
            lines.append("- mechanism-discriminating experiments:")
            lines.extend(f"  - {item}" for item in mechanism_summary.get("counterfactual_experiments", []))
        if mechanism_summary.get("mechanism_status_counts"):
            lines.append(
                f"- mechanism status counts: {json.dumps(mechanism_summary.get('mechanism_status_counts', {}), ensure_ascii=False)}"
            )
        if mechanism_summary.get("challenged_mechanisms"):
            lines.append("- challenged mechanisms:")
            lines.extend(f"  - {item}" for item in mechanism_summary.get("challenged_mechanisms", []))
        if mechanism_summary.get("retire_candidates"):
            lines.append("- mechanism retire candidates:")
            lines.extend(f"  - {item}" for item in mechanism_summary.get("retire_candidates", []))
        if mechanism_summary.get("revive_candidates"):
            lines.append("- mechanism revive candidates:")
            lines.extend(f"  - {item}" for item in mechanism_summary.get("revive_candidates", []))
        lines.append("")

    mechanism_family = research_state.get("mechanism_family_lifecycle_summary", {})
    if mechanism_family:
        lines.extend(["## Mechanism Family Lifecycle", ""])
        lines.append(f"- family count: {mechanism_family.get('family_count', 0)}")
        if mechanism_family.get("family_status_counts"):
            lines.append(
                f"- family status counts: {json.dumps(mechanism_family.get('family_status_counts', {}), ensure_ascii=False)}"
            )
        if mechanism_family.get("retire_candidates"):
            lines.append("- family retire candidates:")
            lines.extend(f"  - {item}" for item in mechanism_family.get("retire_candidates", []))
        if mechanism_family.get("revive_candidates"):
            lines.append("- family revive candidates:")
            lines.extend(f"  - {item}" for item in mechanism_family.get("revive_candidates", []))
        lines.append("")

    family_lifecycle = research_state.get("hypothesis_family_lifecycle_summary", {})
    if family_lifecycle:
        lines.extend(["## Hypothesis Family Lifecycle", ""])
        lines.append(f"- family count: {family_lifecycle.get('family_count', 0)}")
        if family_lifecycle.get("family_action_counts"):
            lines.append(
                f"- family action counts: {json.dumps(family_lifecycle.get('family_action_counts', {}), ensure_ascii=False)}"
            )
        if family_lifecycle.get("retire_candidates"):
            lines.append("- family retire candidates:")
            lines.extend(f"  - {item}" for item in family_lifecycle.get("retire_candidates", []))
        if family_lifecycle.get("revive_candidates"):
            lines.append("- family revive candidates:")
            lines.extend(f"  - {item}" for item in family_lifecycle.get("revive_candidates", []))
        lines.append("")

    hypothesis_validation = research_state.get("hypothesis_validation_summary", {})
    if hypothesis_validation:
        lines.extend(["## Hypothesis Validators", ""])
        lines.append(f"- validation count: {hypothesis_validation.get('validation_count', 0)}")
        lines.append(f"- average novelty score: {hypothesis_validation.get('average_novelty_score', 0)}")
        lines.append(f"- average falsifiability score: {hypothesis_validation.get('average_falsifiability_score', 0)}")
        lines.append(f"- average testability score: {hypothesis_validation.get('average_testability_score', 0)}")
        lines.append(
            f"- average mechanistic coherence score: {hypothesis_validation.get('average_mechanistic_coherence_score', 0)}"
        )
        if hypothesis_validation.get("recommendation_counts"):
            lines.append(
                f"- recommendation counts: {json.dumps(hypothesis_validation.get('recommendation_counts', {}), ensure_ascii=False)}"
            )
        if hypothesis_validation.get("low_novelty_hypotheses"):
            lines.append("- low novelty hypotheses:")
            lines.extend(f"  - {item}" for item in hypothesis_validation.get("low_novelty_hypotheses", []))
        if hypothesis_validation.get("low_falsifiability_hypotheses"):
            lines.append("- low falsifiability hypotheses:")
            lines.extend(f"  - {item}" for item in hypothesis_validation.get("low_falsifiability_hypotheses", []))
        if hypothesis_validation.get("weak_testability_hypotheses"):
            lines.append("- weak testability hypotheses:")
            lines.extend(f"  - {item}" for item in hypothesis_validation.get("weak_testability_hypotheses", []))
        lines.append("")

    hypothesis_gate = research_state.get("hypothesis_gate_summary", {})
    if hypothesis_gate:
        lines.extend(["## Hypothesis Gate", ""])
        lines.append(f"- gate state: {hypothesis_gate.get('gate_state', 'clear')}")
        if hypothesis_gate.get("gate_counts"):
            lines.append(
                f"- gate counts: {json.dumps(hypothesis_gate.get('gate_counts', {}), ensure_ascii=False)}"
            )
        if hypothesis_gate.get("accepted_hypotheses"):
            lines.append("- accepted hypotheses:")
            lines.extend(f"  - {item}" for item in hypothesis_gate.get("accepted_hypotheses", []))
        if hypothesis_gate.get("revise_hypotheses"):
            lines.append("- revise hypotheses:")
            lines.extend(f"  - {item}" for item in hypothesis_gate.get("revise_hypotheses", []))
        if hypothesis_gate.get("blocked_hypotheses"):
            lines.append("- blocked hypotheses:")
            lines.extend(f"  - {item}" for item in hypothesis_gate.get("blocked_hypotheses", []))
        lines.append("")

    assets = research_state.get("asset_registry_summary", {})
    if assets:
        lines.extend(["## Research Asset Registry", ""])
        lines.append(f"- asset count: {assets.get('asset_count', 0)}")
        if assets.get("asset_types"):
            lines.append(f"- asset types: {json.dumps(assets.get('asset_types', {}), ensure_ascii=False)}")
        for item in assets.get("registered_assets", [])[:12]:
            lines.append(
                f"- {item.get('asset_id', '')} [{item.get('asset_type', '')}] {item.get('label', '')} -> {item.get('path_or_ref', '')}"
            )
        lines.append("")

    asset_graph = research_state.get("asset_graph_summary", {})
    if asset_graph:
        lines.extend(["## Research Asset Graph", ""])
        lines.append(
            f"- nodes: {asset_graph.get('node_count', 0)} | edges: {asset_graph.get('edge_count', 0)} | registered assets: {asset_graph.get('registered_asset_count', 0)}"
        )
        lines.append(
            f"- lineage edges: {asset_graph.get('lineage_edge_count', 0)} | ungoverned artifacts: {asset_graph.get('ungoverned_artifact_count', 0)}"
        )
        if asset_graph.get("governed_asset_types"):
            lines.append(
                f"- governed asset types: {json.dumps(asset_graph.get('governed_asset_types', {}), ensure_ascii=False)}"
            )
        if asset_graph.get("artifact_type_counts"):
            lines.append(
                f"- artifact type counts: {json.dumps(asset_graph.get('artifact_type_counts', {}), ensure_ascii=False)}"
            )
        for item in asset_graph.get("edges", [])[:12]:
            lines.append(
                f"- {item.get('source', '')} -> {item.get('target', '')} [{item.get('relation', '')}]"
            )
        lines.append("")

    unified_assets = research_state.get("unified_asset_summary", {})
    if unified_assets:
        lines.extend(["## Unified Scientific Assets", ""])
        lines.append(f"- asset count: {unified_assets.get('asset_count', 0)}")
        lines.append(f"- governed assets: {unified_assets.get('governed_asset_count', 0)}")
        if unified_assets.get("asset_type_counts"):
            lines.append(
                f"- asset types: {json.dumps(unified_assets.get('asset_type_counts', {}), ensure_ascii=False)}"
            )
        if unified_assets.get("source_system_counts"):
            lines.append(
                f"- source systems: {json.dumps(unified_assets.get('source_system_counts', {}), ensure_ascii=False)}"
            )
        if unified_assets.get("review_required_assets"):
            lines.append("- review required assets:")
            lines.extend(f"  - {item}" for item in unified_assets.get("review_required_assets", [])[:10])
        lines.append("")

    graph_references = research_state.get("graph_reference_summary", {})
    if graph_references:
        lines.extend(["## Typed Graph References", ""])
        lines.append(
            f"- node refs: {graph_references.get('node_ref_count', 0)} | edge refs: {graph_references.get('edge_ref_count', 0)}"
        )
        for item in graph_references.get("by_profile", [])[:12]:
            lines.append(
                f"- {item.get('profile_name', '')}: nodes={len(item.get('node_refs', []))} edges={len(item.get('edge_refs', []))}"
            )
            if item.get("usage_note"):
                lines.append(f"  - note: {item.get('usage_note', '')}")
        lines.append("")

    route_temperature = research_state.get("route_temperature_summary", {})
    if route_temperature:
        lines.extend(["## Route Temperature", ""])
        lines.append(f"- global temperature: {route_temperature.get('global_temperature', 'cool')}")
        lines.append(
            f"- challenge pressure: {route_temperature.get('challenge_pressure', 0)} | regression pressure: {route_temperature.get('regression_pressure', 0)}"
        )
        if route_temperature.get("cooling_candidates"):
            lines.append("- cooling candidates:")
            lines.extend(f"  - {item}" for item in route_temperature.get("cooling_candidates", []))
        if route_temperature.get("heating_candidates"):
            lines.append("- heating candidates:")
            lines.extend(f"  - {item}" for item in route_temperature.get("heating_candidates", []))
        lines.append("")

    graph_learning = research_state.get("graph_learning_summary", {})
    if graph_learning:
        lines.extend(["## Graph Learning", ""])
        lines.append(
            f"- learning signal strength: {graph_learning.get('learning_signal_strength', 'low')}"
        )
        lines.append(
            f"- dominant failure class: {graph_learning.get('dominant_failure_class', 'mixed')}"
        )
        if graph_learning.get("high_value_profiles"):
            lines.append("- high value specialist profiles:")
            lines.extend(f"  - {item}" for item in graph_learning.get("high_value_profiles", []))
        if graph_learning.get("recommended_learning_focus"):
            lines.append(f"- recommended learning focus: {graph_learning.get('recommended_learning_focus', '')}")
        lines.append("")

    distill = research_state.get("project_distill", {})
    if distill:
        lines.extend(["## Project Distill", ""])
        lines.append(f"- current consensus: {distill.get('current_consensus', '')}")
        if distill.get("failed_routes"):
            lines.append("- failed routes:")
            lines.extend(f"  - {item}" for item in distill.get("failed_routes", []))
        if distill.get("next_cycle_goals"):
            lines.append("- next cycle goals:")
            lines.extend(f"  - {item}" for item in distill.get("next_cycle_goals", []))
        lines.append("")

    problem_reframer = research_state.get("scientific_problem_reframer_summary", {})
    if problem_reframer:
        lines.extend(["## Scientific Problem Reframer", ""])
        lines.append(f"- reframing state: {problem_reframer.get('reframing_state', '')}")
        selected = problem_reframer.get("selected_frame", {}) if isinstance(problem_reframer.get("selected_frame", {}), dict) else {}
        if selected:
            lines.append(f"- selected frame: {selected.get('frame_type', '')} | {selected.get('question', '')}")
        if problem_reframer.get("triggers"):
            lines.append("- triggers:")
            for item in problem_reframer.get("triggers", [])[:6]:
                if isinstance(item, dict):
                    lines.append(f"  - {item.get('trigger', '')}: {item.get('reason', '')}")
        if problem_reframer.get("representation_shifts"):
            lines.append("- representation shifts:")
            lines.extend(f"  - {item}" for item in problem_reframer.get("representation_shifts", [])[:6])
        lines.append("")

    theory_compiler = research_state.get("theory_prediction_compiler_summary", {})
    if theory_compiler:
        lines.extend(["## Theory Formalizer And Prediction Compiler", ""])
        lines.append(f"- formalization readiness: {theory_compiler.get('formalization_readiness', '')}")
        lines.append(
            f"- compiled theories: {theory_compiler.get('compiled_theory_count', 0)} | predictions: {theory_compiler.get('prediction_count', 0)} | discriminating tests: {theory_compiler.get('discriminating_test_count', 0)}"
        )
        if theory_compiler.get("missing_formal_field_counts"):
            lines.append(
                f"- missing formal fields: {json.dumps(theory_compiler.get('missing_formal_field_counts', {}), ensure_ascii=False)}"
            )
        if theory_compiler.get("discriminating_tests"):
            lines.append("- top discriminating tests:")
            for item in theory_compiler.get("discriminating_tests", [])[:6]:
                if isinstance(item, dict):
                    lines.append(f"  - {item.get('test_id', '')}: {item.get('test_logic', '')}")
        lines.append("")

    anomaly = research_state.get("anomaly_surprise_detector_summary", {})
    if anomaly:
        lines.extend(["## Anomaly And Surprise Detector", ""])
        lines.append(f"- surprise level: {anomaly.get('surprise_level', '')}")
        lines.append(f"- anomaly count: {anomaly.get('anomaly_count', 0)}")
        if anomaly.get("top_anomalies"):
            lines.append("- top anomalies:")
            for item in anomaly.get("top_anomalies", [])[:6]:
                if isinstance(item, dict):
                    lines.append(f"  - {item.get('anomaly_type', '')}: {item.get('description', '')}")
        lines.append("")

    credit = research_state.get("scientific_credit_responsibility_ledger_summary", {})
    if credit:
        lines.extend(["## Scientific Credit And Responsibility Ledger", ""])
        lines.append(f"- record count: {credit.get('record_count', 0)}")
        if credit.get("credit_by_actor"):
            lines.append(f"- credit by actor: {json.dumps(credit.get('credit_by_actor', {}), ensure_ascii=False)}")
        if credit.get("responsibility_by_actor"):
            lines.append(f"- responsibility by actor: {json.dumps(credit.get('responsibility_by_actor', {}), ensure_ascii=False)}")
        lines.append("")

    belief_update = research_state.get("belief_update_summary", {})
    if belief_update:
        lines.extend(["## Belief Update", ""])
        lines.append(f"- consensus status: {belief_update.get('consensus_status', 'partial')}")
        if belief_update.get("current_consensus"):
            lines.append(f"- current consensus: {belief_update.get('current_consensus', '')}")
        if belief_update.get("challenged_hypothesis_count"):
            lines.append(
                f"- challenged hypotheses: {belief_update.get('challenged_hypothesis_count', 0)}"
            )
        if belief_update.get("status_counts"):
            lines.append(
                f"- hypothesis status counts: {json.dumps(belief_update.get('status_counts', {}), ensure_ascii=False)}"
            )
        if belief_update.get("hypothesis_relation_counts"):
            lines.append(
                "- hypothesis relation counts: "
                f"{json.dumps(belief_update.get('hypothesis_relation_counts', {}), ensure_ascii=False)}"
            )
        if belief_update.get("next_cycle_goals"):
            lines.append("- next cycle goals:")
            lines.extend(f"  - {item}" for item in belief_update.get("next_cycle_goals", []))
        lines.append("")

    failure_intelligence = research_state.get("failure_intelligence_summary", {})
    if failure_intelligence:
        lines.extend(["## Failure Intelligence", ""])
        lines.append(
            f"- dominant failure class: {failure_intelligence.get('dominant_failure_class', 'mixed')}"
        )
        if failure_intelligence.get("technical_failures"):
            lines.append("- technical failures:")
            lines.extend(f"  - {item}" for item in failure_intelligence.get("technical_failures", []))
        if failure_intelligence.get("theoretical_failures"):
            lines.append("- theoretical failures:")
            lines.extend(
                f"  - {item}" for item in failure_intelligence.get("theoretical_failures", [])
            )
        if failure_intelligence.get("evidence_failures"):
            lines.append("- evidence failures:")
            lines.extend(f"  - {item}" for item in failure_intelligence.get("evidence_failures", []))
        if failure_intelligence.get("avoid_repeat_routes"):
            lines.append("- avoid repeating these routes:")
            lines.extend(
                f"  - {item}" for item in failure_intelligence.get("avoid_repeat_routes", [])
            )
        lines.append("")

    evaluation = research_state.get("evaluation_summary", {})
    if evaluation:
        lines.extend(["## Evaluation Summary", ""])
        coverage = evaluation.get("hypothesis_coverage", {})
        lines.append(
            f"- hypothesis coverage: hypotheses={coverage.get('hypothesis_count', 0)} claims={coverage.get('claim_count', 0)} evidence={coverage.get('evidence_count', 0)}"
        )
        lines.append(f"- literature strength: {evaluation.get('literature_strength', 'mixed')}")
        lines.append(f"- consensus readiness: {evaluation.get('consensus_readiness', 'forming')}")
        lines.append(f"- benchmark readiness: {evaluation.get('benchmark_readiness', 'low')}")
        lines.append(f"- failure pressure: {evaluation.get('failure_pressure', 'mixed')}")
        lines.append(f"- theory maturity: {evaluation.get('theory_maturity', 'flat')}")
        lines.append(
            f"- systematic review readiness: {evaluation.get('systematic_review_readiness', 'low')}"
        )
        lines.append(
            f"- asset governance readiness: {evaluation.get('asset_governance_readiness', 'low')}"
        )
        lines.append(
            f"- causal identifiability: {evaluation.get('causal_identifiability', 'low')}"
        )
        lines.append(
            f"- graph reference engagement: {evaluation.get('graph_reference_engagement', 'low')}"
        )
        lines.append(f"- graph growth trend: {evaluation.get('graph_growth_trend', 'stable')}")
        lines.append(
            f"- retired route reuse risk: {evaluation.get('retired_route_reuse_risk', 'low')}"
        )
        lines.append(f"- support density: {evaluation.get('support_density', 'low')}")
        lines.append(
            f"- family governance readiness: {evaluation.get('family_governance_readiness', 'low')}"
        )
        lines.append(
            f"- learning signal strength: {evaluation.get('learning_signal_strength', 'low')}"
        )
        lines.append("")

    workflow_control = research_state.get("workflow_control_summary", {})
    if workflow_control:
        lines.extend(["## Workflow Control", ""])
        lines.append(f"- control state: {workflow_control.get('control_state', '')}")
        lines.append(f"- execution gate: {workflow_control.get('execution_gate', '')}")
        if workflow_control.get("blocking_gates"):
            lines.append("- blocking gates:")
            lines.extend(f"  - {item}" for item in workflow_control.get("blocking_gates", [])[:8])
        if workflow_control.get("allowed_next_actions"):
            lines.append("- allowed next actions:")
            lines.extend(f"  - {item}" for item in workflow_control.get("allowed_next_actions", [])[:8])
        lines.append("")

    hypothesis_system = research_state.get("hypothesis_system_summary", {})
    if hypothesis_system:
        lines.extend(["## Hypothesis System", ""])
        lines.append(f"- system state: {hypothesis_system.get('system_state', '')}")
        lines.append(
            f"- hypotheses: {hypothesis_system.get('hypothesis_count', 0)} | theory objects: {hypothesis_system.get('theory_object_count', 0)} | predictions: {hypothesis_system.get('prediction_count', 0)}"
        )
        lines.append(
            f"- accepted: {hypothesis_system.get('accepted_hypothesis_count', 0)} | revise: {hypothesis_system.get('revise_hypothesis_count', 0)} | blocked: {hypothesis_system.get('blocked_hypothesis_count', 0)}"
        )
        if hypothesis_system.get("blocking_reasons"):
            lines.append("- blocking reasons:")
            lines.extend(f"  - {item}" for item in hypothesis_system.get("blocking_reasons", [])[:8])
        lines.append("")

    evaluation_system = research_state.get("scientific_evaluation_system_summary", {})
    if evaluation_system:
        lines.extend(["## Scientific Evaluation System", ""])
        lines.append(f"- system state: {evaluation_system.get('system_state', '')}")
        lines.append(f"- case suite state: {evaluation_system.get('case_suite_state', '')}")
        lines.append(f"- benchmark state: {evaluation_system.get('benchmark_state', '')}")
        lines.append(f"- blocking gates: {evaluation_system.get('blocking_gate_count', 0)}")
        if evaluation_system.get("blocking_reasons"):
            lines.append("- blocking reasons:")
            lines.extend(f"  - {item}" for item in evaluation_system.get("blocking_reasons", [])[:8])
        lines.append("")

    benchmark_harness = research_state.get("benchmark_harness_summary", {})
    if benchmark_harness:
        lines.extend(["## Benchmark Harness", ""])
        lines.append(f"- benchmark ready: {benchmark_harness.get('benchmark_ready', False)}")
        lines.append(
            f"- release readiness: {benchmark_harness.get('release_readiness', 'low')}"
        )
        lines.append(f"- evidence gate: {benchmark_harness.get('evidence_gate', 'low')}")
        lines.append(
            f"- reproducibility gate: {benchmark_harness.get('reproducibility_gate', 'low')}"
        )
        lines.append(
            f"- governance gate: {benchmark_harness.get('governance_gate', 'clear')}"
        )
        if benchmark_harness.get("benchmark_gaps"):
            lines.append("- benchmark gaps:")
            lines.extend(f"  - {item}" for item in benchmark_harness.get("benchmark_gaps", []))
        if benchmark_harness.get("regression_checks"):
            lines.append("- regression checks:")
            lines.extend(
                f"  - {item}" for item in benchmark_harness.get("regression_checks", [])
            )
        if benchmark_harness.get("fail_fast_checks"):
            lines.append("- fail-fast checks:")
            lines.extend(
                f"  - {item}" for item in benchmark_harness.get("fail_fast_checks", [])
            )
        lines.append("")

    benchmark_cases = research_state.get("benchmark_case_suite_summary", {})
    if benchmark_cases:
        lines.extend(["## Benchmark Dataset And Regression Suite", ""])
        dataset = (
            benchmark_cases.get("benchmark_dataset", {})
            if isinstance(benchmark_cases.get("benchmark_dataset", {}), dict)
            else {}
        )
        regression = (
            benchmark_cases.get("benchmark_regression_suite", {})
            if isinstance(benchmark_cases.get("benchmark_regression_suite", {}), dict)
            else {}
        )
        lines.append(f"- dataset id: {dataset.get('dataset_id', '')}")
        lines.append(f"- dataset version: {dataset.get('version', '')}")
        lines.append(f"- dataset cases: {dataset.get('case_count', benchmark_cases.get('case_count', 0))}")
        lines.append(
            f"- case results: passed={benchmark_cases.get('passed_count', 0)} failed={benchmark_cases.get('failed_count', 0)}"
        )
        if dataset.get("category_counts"):
            lines.append(f"- categories: {dataset.get('category_counts', {})}")
        if regression:
            lines.append(
                f"- regression state: {regression.get('release_state', '')}; regressions={regression.get('regression_count', 0)}; improvements={regression.get('improvement_count', 0)}"
            )
            if regression.get("category_matrix"):
                lines.append(f"- category matrix: {regression.get('category_matrix', {})}")
        if benchmark_cases.get("fail_fast_cases"):
            lines.append("- fail-fast cases:")
            lines.extend(f"  - {item}" for item in benchmark_cases.get("fail_fast_cases", [])[:8])
        if benchmark_cases.get("benchmark_gaps"):
            lines.append("- benchmark gaps:")
            lines.extend(f"  - {item}" for item in benchmark_cases.get("benchmark_gaps", [])[:8])
        lines.append("")

    benchmark_summary = research_state.get("benchmark_case_suite_summary", {})
    scientific_benchmark = (
        benchmark_summary.get("scientific_evaluation_benchmark_summary", {})
        if isinstance(benchmark_summary, dict)
        and isinstance(benchmark_summary.get("scientific_evaluation_benchmark_summary", {}), dict)
        else {}
    )
    if scientific_benchmark:
        lines.extend(["## Scientific Evaluation Benchmark", ""])
        lines.append(f"- benchmark state: {scientific_benchmark.get('benchmark_state', '')}")
        lines.append(
            f"- tasks: {scientific_benchmark.get('task_count', 0)} | passed: {scientific_benchmark.get('passed_count', 0)} | failed: {scientific_benchmark.get('failed_count', 0)}"
        )
        lines.append(f"- average quality score: {scientific_benchmark.get('average_quality_score', 0)}")
        if scientific_benchmark.get("failure_modes"):
            lines.append("- failure modes:")
            lines.extend(f"  - {item}" for item in scientific_benchmark.get("failure_modes", [])[:8])
        lines.append("")

    campaign = research_state.get("research_campaign_plan_summary", {})
    if campaign:
        lines.extend(["## Research Campaign Plan", ""])
        lines.append(f"- current campaign stage: {campaign.get('current_campaign_stage', '')}")
        lines.append(f"- next campaign decision: {campaign.get('next_campaign_decision', '')}")
        recommendation = campaign.get("single_step_recommendation", {}) if isinstance(campaign.get("single_step_recommendation", {}), dict) else {}
        if recommendation:
            lines.append(
                f"- route selector: {recommendation.get('next_action', '')} | {recommendation.get('reason', '')}"
            )
        if campaign.get("multi_step_route_plan"):
            lines.append("- multi-step route plan:")
            for item in campaign.get("multi_step_route_plan", [])[:6]:
                if isinstance(item, dict):
                    lines.append(
                        f"  - step {item.get('step_index', '')}: {item.get('campaign_stage', '')} -> {item.get('route_action', '')}"
                    )
        if campaign.get("scheduler_constraints"):
            lines.append("- scheduler constraints:")
            lines.extend(f"  - {item}" for item in campaign.get("scheduler_constraints", [])[:8])
        lines.append("")

    evaluation_harness = research_state.get("kaivu_evaluation_harness_summary", {})
    if evaluation_harness:
        lines.extend(["## Kaivu Evaluation Harness", ""])
        lines.append(f"- overall score: {evaluation_harness.get('overall_score', 0)}")
        lines.append(f"- release state: {evaluation_harness.get('release_state', '')}")
        lines.append(f"- blocking gates: {evaluation_harness.get('blocking_gate_count', 0)}")
        if evaluation_harness.get("axes"):
            lines.append("- axes:")
            for axis in evaluation_harness.get("axes", [])[:10]:
                if isinstance(axis, dict):
                    lines.append(
                        f"  - {axis.get('axis_id', '')}: score={axis.get('score', 0)} state={axis.get('state', '')}"
                    )
        if evaluation_harness.get("blocking_gates"):
            lines.append("- blocking gates:")
            lines.extend(f"  - {item}" for item in evaluation_harness.get("blocking_gates", [])[:8])
        if evaluation_harness.get("regression_suite"):
            lines.append("- regression suite:")
            lines.extend(f"  - {item}" for item in evaluation_harness.get("regression_suite", [])[:8])
        lines.append("")

    research_route_search = research_state.get("research_route_search_summary", {})
    if research_route_search:
        lines.extend(["## Research Route Search", ""])
        lines.append(
            f"- best next action: {research_route_search.get('best_next_action', 'continue_current_route')}"
        )
        search_state = (
            research_route_search.get("search_state", {})
            if isinstance(research_route_search.get("search_state", {}), dict)
            else {}
        )
        if search_state:
            lines.append(
                f"- search state: active_workstreams={search_state.get('active_workstreams', 0)} route_temperature={search_state.get('route_temperature', 'unknown')} benchmark_readiness={search_state.get('benchmark_readiness', 'low')}"
            )
        for item in research_route_search.get("candidate_actions", [])[:6]:
            if not isinstance(item, dict):
                continue
            lines.append(
                f"- {item.get('action_type', '')}: value={item.get('route_value_score', 0)} | info={item.get('information_gain_score', 0)} | cost={item.get('cost_score', 0)} | time={item.get('time_score', 0)} | risk={item.get('risk_score', 0)} | governance={item.get('governance_burden_score', 0)}"
            )
            if item.get("rationale"):
                lines.append(f"  rationale: {item.get('rationale', '')}")
        lines.append("")

    scientific_decision = research_state.get("scientific_decision_summary", {})
    if scientific_decision:
        lines.extend(["## Scientific Decision Engine", ""])
        lines.append(
            f"- recommended next action: {scientific_decision.get('recommended_next_action', 'continue_current_route')}"
        )
        lines.append(f"- recommended target: {scientific_decision.get('recommended_target_id', '')}")
        lines.append(f"- decision state: {scientific_decision.get('decision_state', 'continue')}")
        if scientific_decision.get("evidence_review_readiness"):
            lines.append(
                f"- evidence review readiness: {scientific_decision.get('evidence_review_readiness', '')}"
            )
        if scientific_decision.get("evidence_review_quality_state"):
            lines.append(
                f"- evidence review quality: {scientific_decision.get('evidence_review_quality_state', '')}"
            )
        lines.append(
            f"- must pause for human review: {scientific_decision.get('must_pause_for_human_review', False)}"
        )
        lines.append(f"- provenance traces: {scientific_decision.get('provenance_trace_count', 0)}")
        queue = scientific_decision.get("decision_queue", [])
        if queue:
            lines.append("- top decisions:")
            for item in queue[:5]:
                if not isinstance(item, dict):
                    continue
                lines.append(
                    "  - "
                    + f"{item.get('action', '')} -> {item.get('target_id', '')} "
                    + f"[priority={item.get('priority', '')}, value={item.get('route_value_score', '')}]"
                )
                traces = item.get("evidence_trace", [])
                if traces:
                    trace_bits = [
                        f"{trace.get('source_type', '')}:{trace.get('source_id', '')}"
                        for trace in traces[:3]
                        if isinstance(trace, dict)
                    ]
                    if trace_bits:
                        lines.append(f"    traces: {', '.join(trace_bits)}")
        lines.append("")

    event_ledger = research_state.get("event_ledger_summary", {})
    if event_ledger:
        lines.extend(["## Research Event Ledger", ""])
        lines.append(f"- events written this run: {event_ledger.get('events_written', 0)}")
        lines.append(f"- total topic events: {event_ledger.get('event_count', 0)}")
        lines.append(f"- latest event id: {event_ledger.get('latest_event_id', '')}")
        if event_ledger.get("event_type_counts"):
            lines.append(
                f"- event types: {json.dumps(event_ledger.get('event_type_counts', {}), ensure_ascii=False)}"
            )
        if event_ledger.get("asset_type_counts"):
            lines.append(
                f"- asset types: {json.dumps(event_ledger.get('asset_type_counts', {}), ensure_ascii=False)}"
            )
        if event_ledger.get("ledger_path"):
            lines.append(f"- ledger path: {event_ledger.get('ledger_path', '')}")
        lines.append("")

    execution_cycle = research_state.get("execution_cycle_summary", {})
    if execution_cycle:
        lines.extend(["## Execution Cycle", ""])
        lines.append(f"- experiment runs: {execution_cycle.get('experiment_run_count', 0)}")
        lines.append(f"- quality control reviews: {execution_cycle.get('quality_control_review_count', 0)}")
        lines.append(f"- interpretation records: {execution_cycle.get('interpretation_record_count', 0)}")
        lines.append(
            f"- repeat required count: {execution_cycle.get('repeat_required_count', 0)} | unusable for interpretation: {execution_cycle.get('unusable_for_interpretation_count', 0)}"
        )
        lines.append(
            f"- negative interpretation count: {execution_cycle.get('negative_interpretation_count', 0)}"
        )
        if execution_cycle.get("run_status_counts"):
            lines.append(
                f"- run status counts: {json.dumps(execution_cycle.get('run_status_counts', {}), ensure_ascii=False)}"
            )
        if execution_cycle.get("quality_control_status_counts"):
            lines.append(
                f"- quality control status counts: {json.dumps(execution_cycle.get('quality_control_status_counts', {}), ensure_ascii=False)}"
            )
        if execution_cycle.get("next_decisions"):
            lines.append("- next decisions:")
            lines.extend(f"  - {item}" for item in execution_cycle.get("next_decisions", []))
        lines.append("")

    artifact_provenance = research_state.get("artifact_provenance_summary", {})
    if artifact_provenance:
        lines.extend(["## Artifact Provenance", ""])
        lines.append(f"- artifact count: {artifact_provenance.get('artifact_count', 0)}")
        lines.append(f"- input file count: {artifact_provenance.get('input_file_count', 0)}")
        lines.append(f"- provenance edge count: {artifact_provenance.get('provenance_edge_count', 0)}")
        lines.append(f"- governed artifact count: {artifact_provenance.get('governed_artifact_count', 0)}")
        lines.append(f"- ungoverned artifact count: {artifact_provenance.get('ungoverned_artifact_count', 0)}")
        if artifact_provenance.get("artifact_types"):
            lines.append(
                f"- artifact types: {json.dumps(artifact_provenance.get('artifact_types', {}), ensure_ascii=False)}"
            )
        lines.append("")

    return lines


def _render_execution_records(execution_records: list[dict[str, Any]]) -> list[str]:
    if not execution_records:
        return []
    lines = ["## Reproducibility Log", ""]
    for record in execution_records:
        tool_name = record.get("tool_name", "unknown")
        status = record.get("status", "unknown")
        task_id = record.get("task_id", "")
        lines.append(f"- {tool_name} [{status}] task={task_id}")
        inputs = record.get("inputs", {})
        outputs = record.get("outputs", {})
        artifacts = record.get("artifacts", [])
        if inputs:
            lines.append(f"  inputs: {json.dumps(inputs, ensure_ascii=False)}")
        if outputs:
            lines.append(f"  outputs: {json.dumps(outputs, ensure_ascii=False)}")
        if artifacts:
            lines.append(f"  artifacts: {json.dumps(artifacts, ensure_ascii=False)}")
    lines.append("")
    return lines


def _render_run_manifest(run_manifest: dict[str, Any]) -> list[str]:
    if not run_manifest:
        return []
    lines = [
        "## Run Manifest",
        "",
        f"- generated at: {run_manifest.get('generated_at', 'unknown')}",
        f"- cwd: {run_manifest.get('cwd', 'unknown')}",
        f"- python version: {run_manifest.get('python_version', 'unknown')}",
        f"- platform: {run_manifest.get('platform', 'unknown')}",
        f"- tools used: {', '.join(run_manifest.get('tools_used', [])) or 'none'}",
        f"- seeds: {', '.join(str(item) for item in run_manifest.get('seeds', [])) or 'none'}",
        "",
    ]
    if run_manifest.get("collaboration_context"):
        lines.append(f"- collaboration context: {json.dumps(run_manifest.get('collaboration_context', {}), ensure_ascii=False)}")
        lines.append("")
    input_files = run_manifest.get("input_files", [])
    if input_files:
        lines.append("Input files:")
        lines.append("")
        for item in input_files[:20]:
            lines.append(
                f"- {item.get('path', '')} | exists={item.get('exists', False)} | sha256={item.get('sha256', '')} | scope={item.get('scope', '')}"
            )
        lines.append("")
    artifacts = run_manifest.get("artifacts", [])
    if artifacts:
        lines.append("Artifacts:")
        lines.append("")
        for item in artifacts[:20]:
            lines.append(
                f"- {item.get('path', '')} | kind={item.get('kind', '')} | exists={item.get('exists', False)} | scope={item.get('scope', '')}"
            )
        lines.append("")
    models = run_manifest.get("models_used", [])
    if models:
        lines.append("Models used:")
        lines.append("")
        for item in models[:20]:
            lines.append(
                f"- {item.get('profile_name', 'unknown')}: {item.get('provider', 'unknown')}/{item.get('model', 'unknown')} reasoning={item.get('reasoning_effort', 'unknown')}"
            )
        lines.append("")
    return lines


def _render_usage_summary(usage_summary: dict[str, Any]) -> list[str]:
    if not usage_summary:
        return []
    total = usage_summary.get("total", {})
    by_profile = usage_summary.get("by_profile", [])
    lines = [
        "## Token And Cost Summary",
        "",
        f"- total input tokens: {int(total.get('input_tokens', 0))}",
        f"- total output tokens: {int(total.get('output_tokens', 0))}",
        f"- total tokens: {int(total.get('total_tokens', 0))}",
        f"- total rounds: {int(total.get('rounds', 0))}",
        f"- total estimated cost usd: {float(total.get('estimated_cost_usd', 0.0)):.6f}",
        "",
    ]
    if by_profile:
        lines.append("Per specialist:")
        lines.append("")
        for item in by_profile:
            lines.append(
                f"- {item.get('profile_name', 'unknown')} [{item.get('model', 'unknown')}]: "
                f"in={item.get('input_tokens', 0)} out={item.get('output_tokens', 0)} "
                f"total={item.get('total_tokens', 0)} rounds={item.get('rounds', 0)} "
                f"cost=${float(item.get('estimated_cost_usd', 0.0)):.6f}"
            )
        lines.append("")
    return lines


def _render_claim_graph(claim_graph: dict[str, Any]) -> list[str]:
    if not claim_graph:
        return []
    claim_count = len(claim_graph.get("claims", []))
    evidence_count = len(claim_graph.get("evidence", []))
    edge_count = len(claim_graph.get("edges", []))
    hypothesis_count = len(claim_graph.get("hypotheses", []))
    hypothesis_relation_count = len(claim_graph.get("hypothesis_relations", []))
    negative_count = len(claim_graph.get("negative_results", []))
    negative_link_count = len(claim_graph.get("negative_result_links", []))
    asset_count = len(claim_graph.get("asset_registry", []))
    execution_cycle_summary = claim_graph.get("execution_cycle_summary", {})
    lines = [
        "## Claim Graph",
        "",
        f"- claims: {claim_count}",
        f"- evidence nodes: {evidence_count}",
        f"- hypothesis nodes: {hypothesis_count}",
        f"- hypothesis relations: {hypothesis_relation_count}",
        f"- negative result nodes: {negative_count}",
        f"- support edges: {edge_count}",
        f"- negative-result challenge edges: {negative_link_count}",
        f"- registered assets: {asset_count}",
    ]
    if execution_cycle_summary:
        lines.append(
            f"- execution cycle: runs={execution_cycle_summary.get('experiment_run_count', 0)} quality_reviews={execution_cycle_summary.get('quality_control_review_count', 0)} interpretations={execution_cycle_summary.get('interpretation_record_count', 0)}"
        )
    memory_updates = claim_graph.get("memory_updates", [])
    if memory_updates:
        lines.append(f"- memory updates: {len(memory_updates)}")
    lines.append("")
    if claim_graph.get("claims"):
        lines.append("Top claim nodes:")
        lines.append("")
        for claim in claim_graph["claims"][:10]:
            lines.append(
                f"- {claim.get('global_claim_id', '')} [{claim.get('profile_name', '')}] "
                f"{claim.get('statement', '')}"
            )
        lines.append("")
    if claim_graph.get("negative_result_links"):
        lines.append("Negative result to hypothesis links:")
        lines.append("")
        for item in claim_graph["negative_result_links"][:12]:
            lines.append(
                f"- {item.get('negative_result_id', '')} -> {item.get('hypothesis_id', '')} [{item.get('relation', 'challenges')}]"
            )
        lines.append("")
    if claim_graph.get("hypothesis_relations"):
        lines.append("Hypothesis relations:")
        lines.append("")
        for item in claim_graph["hypothesis_relations"][:12]:
            lines.append(
                f"- {item.get('source', '')} -> {item.get('target', '')} [{item.get('relation', '')}]"
                + (f" | {item.get('note', '')}" if item.get("note") else "")
            )
        lines.append("")
    if memory_updates:
        lines.append("Conflict-driven memory updates:")
        lines.append("")
        for item in memory_updates:
            lines.append(
                f"- {item.get('filename', '')} updated_by={item.get('updated_by', '')}"
            )
        lines.append("")
    return lines


def _render_research_state(research_state: dict[str, Any]) -> list[str]:
    if not research_state:
        return []
    blockers = ", ".join(research_state.get("blockers", []))
    open_questions = ", ".join(research_state.get("open_questions", []))
    lines = [
        "## Research State",
        "",
        f"- current stage: {research_state.get('current_stage', 'unknown')}",
        f"- recommended next stage: {research_state.get('recommended_next_stage', 'unknown')}",
        f"- allowed next stages: {', '.join(research_state.get('allowed_next_stages', [])) or 'unknown'}",
        f"- active hypotheses: {research_state.get('active_hypothesis_count', 0)}",
        f"- negative results tracked: {research_state.get('negative_result_count', 0)}",
        f"- evidence strength summary: {research_state.get('evidence_strength_summary', 'unknown')}",
    ]
    if blockers:
        lines.append(f"- blockers: {blockers}")
    if open_questions:
        lines.append(f"- open questions: {open_questions}")
    missing = ", ".join(research_state.get("missing_prerequisites", []))
    if missing:
        lines.append(f"- missing prerequisites: {missing}")
    invalid = ", ".join(research_state.get("invalid_transitions", []))
    if invalid:
        lines.append(f"- invalid transitions: {invalid}")
    challenged = ", ".join(research_state.get("challenged_hypothesis_ids", []))
    if challenged:
        lines.append(f"- challenged hypothesis ids: {challenged}")
    literature_quality = research_state.get("literature_quality_summary", {})
    if literature_quality:
        lines.append(
            f"- literature quality: {literature_quality.get('dominant_grade', 'unclear')} {json.dumps(literature_quality.get('counts', {}), ensure_ascii=False)}"
        )
    conflict_attribution = research_state.get("conflict_attribution", {})
    if conflict_attribution:
        lines.append(
            f"- conflict groups: {conflict_attribution.get('conflict_group_count', 0)} | directional conflicts: {conflict_attribution.get('directional_conflict_count', 0)}"
        )
    lines.append("")
    return lines


def render_markdown_report(
    topic: str,
    steps: list[dict[str, Any]],
    citations: list[dict[str, Any]] | None = None,
    execution_records: list[dict[str, Any]] | None = None,
    usage_summary: dict[str, Any] | None = None,
    claim_graph: dict[str, Any] | None = None,
    research_state: dict[str, Any] | None = None,
    run_manifest: dict[str, Any] | None = None,
) -> str:
    lines = [f"# Kaivu Scientific Research Report", "", f"## Topic", "", topic, ""]
    if research_state:
        lines.extend(_render_research_state(research_state))
        lines.extend(_render_scientific_meta_from_state(research_state))
    if run_manifest:
        lines.extend(_render_run_manifest(run_manifest))
    for step in steps:
        parsed_output = step["parsed_output"]
        lines.append(f"## {step['profile_name']}")
        lines.append("")
        model_meta = step.get("model_meta", {})
        if model_meta:
            lines.append(
                f"Model: {model_meta.get('provider', 'unknown')}/{model_meta.get('model', 'unknown')} "
                f"(reasoning={model_meta.get('reasoning_effort', 'unknown')})"
            )
            lines.append("")
        lines.append(f"Confidence: {parsed_output.get('confidence', 'unknown')}")
        lines.append("")
        lines.extend(_render_stage_assessment(parsed_output))
        lines.extend(_render_hypotheses(parsed_output))
        lines.extend(_render_claims(parsed_output))
        lines.extend(_render_evidence(parsed_output))
        lines.extend(_render_uncertainties(parsed_output))
        lines.extend(_render_negative_results(parsed_output))
        lines.append("Structured JSON:")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(parsed_output, ensure_ascii=False, indent=2))
        lines.append("```")
        lines.append("")
        if step.get("raw_output"):
            lines.append("Model text:")
            lines.append("")
            lines.append(step["raw_output"])
            lines.append("")
    if execution_records:
        lines.extend(_render_execution_records(execution_records))
    if usage_summary:
        lines.extend(_render_usage_summary(usage_summary))
    if claim_graph:
        lines.extend(_render_claim_graph(claim_graph))
    if citations:
        lines.append("## References")
        lines.append("")
        for citation in citations:
            lines.append(f"- {format_citation(citation)}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def write_markdown_report(path: str | Path, content: str) -> Path:
    target = Path(path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target

