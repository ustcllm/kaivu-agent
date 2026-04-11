from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from scientific_agent.data_tools import BasicStatsTool, PlotCsvTool, ReadTableTool
    from scientific_agent.literature_tools import ArxivSearchTool, CrossrefSearchTool, PubMedSearchTool, ResolveCitationTool
    from scientific_agent.memory import MemoryManager
    from scientific_agent.mcp import MCPRegistry, MCPServerConfig
    from scientific_agent.permissions import PermissionPolicy
    from scientific_agent.skills import SkillRuntime, load_skills
    from scientific_agent.model_registry import ModelRegistry
    from scientific_agent.tools import (
        ForgetMemoryTool,
        IngestLiteratureSourceTool,
        NotebookTool,
        PythonExecTool,
        ReadFileTool,
        LintLiteratureWorkspaceTool,
        QueryLiteratureWikiTool,
        ReviewMemoryTool,
        SaveMemoryTool,
        SearchMemoryTool,
        TypedGraphQueryTool,
        ToolRegistry,
        WriteFileTool,
    )
    from scientific_agent.workflow import ScientificWorkflow
else:
    from .data_tools import BasicStatsTool, PlotCsvTool, ReadTableTool
    from .literature_tools import ArxivSearchTool, CrossrefSearchTool, PubMedSearchTool, ResolveCitationTool
    from .memory import MemoryManager
    from .mcp import MCPRegistry, MCPServerConfig
    from .permissions import PermissionPolicy
    from .skills import SkillRuntime, load_skills
    from .model_registry import ModelRegistry
    from .tools import (
        ForgetMemoryTool,
        IngestLiteratureSourceTool,
        NotebookTool,
        PythonExecTool,
        ReadFileTool,
        LintLiteratureWorkspaceTool,
        QueryLiteratureWikiTool,
        ReviewMemoryTool,
        SaveMemoryTool,
        SearchMemoryTool,
        TypedGraphQueryTool,
        ToolRegistry,
        WriteFileTool,
    )
    from .workflow import ScientificWorkflow


def build_demo_workspace(root: Path) -> None:
    data_dir = root / "demo_data"
    data_dir.mkdir(parents=True, exist_ok=True)
    sample = data_dir / "experiment.txt"
    csv_sample = data_dir / "experiment_metrics.csv"
    if not sample.exists():
        sample.write_text(
            "Experiment A\nTemperature: 23.1C\nObservation: cell growth accelerated.\n",
            encoding="utf-8",
        )
    if not csv_sample.exists():
        csv_sample.write_text(
            "time_hr,growth_rate,viability\n0,0.21,0.98\n1,0.25,0.97\n2,0.33,0.95\n3,0.39,0.92\n",
            encoding="utf-8",
        )


async def main() -> None:
    root = Path(__file__).resolve().parent.parent
    if any(arg in {"-h", "--help"} for arg in sys.argv[1:]):
        print(
            "\n".join(
                [
                    "Usage: python -m scientific_agent.demo [research topic]",
                    "",
                    "Environment:",
                    "  OPENAI_API_KEY is required for the real model demo.",
                    "  SCIENTIFIC_AGENT_MODEL optionally overrides the default model.",
                    "  SCIENTIFIC_AGENT_MODEL_CONFIG optionally points to per-agent model config JSON.",
                    "  SCIENTIFIC_AGENT_MCP_CONFIG optionally points to MCP server config JSON.",
                ]
            )
        )
        return
    build_demo_workspace(root)

    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit(
            "OPENAI_API_KEY is not set.\n"
            "Run this demo with a real model like:\n"
            "  set OPENAI_API_KEY=your_key_here\n"
            "  python C:\\Users\\liand\\Documents\\agent\\scientific_agent\\demo.py"
        )

    skills = load_skills(root / "scientific_agent" / "skills_builtin")
    skill_runtime = SkillRuntime(skills)

    mcp_registry = MCPRegistry(_load_mcp_configs_from_env())
    if mcp_registry.configs:
        await mcp_registry.start()

    model_registry = ModelRegistry(
        default_model=os.getenv("SCIENTIFIC_AGENT_MODEL", "gpt-5"),
        default_base_url=os.getenv(
            "SCIENTIFIC_AGENT_BASE_URL",
            "https://api.openai.com/v1/responses",
        ),
    )
    model_config_path = _resolve_model_config_path(root)
    if model_config_path is not None:
        model_registry.load_config_file(model_config_path)

    workflow = ScientificWorkflow(
        cwd=root,
        model_name=os.getenv("SCIENTIFIC_AGENT_MODEL", "gpt-5"),
        permission_policy=PermissionPolicy(
            mode="deny_destructive",
            allow_tools={"write_file"},
        ),
        report_path=os.getenv(
            "SCIENTIFIC_AGENT_REPORT_PATH",
            str(root / "reports" / "scientific_report.md"),
        ),
        dynamic_routing=os.getenv("SCIENTIFIC_AGENT_DYNAMIC_ROUTING", "1") != "0",
        skill_runtime=skill_runtime,
        mcp_registry=mcp_registry,
        model_registry=model_registry,
    )
    memory_manager = MemoryManager(root)
    memory_manager.save_memory(
        title="preferred research style",
        summary="Default expectation for evidence-driven scientific collaboration",
        kind="preference",
        scope="project",
        content=(
            "Prefer explicit uncertainty, cite sources when possible, "
            "distinguish established findings from hypotheses, and avoid overstating claims."
        ),
        tags=["style", "evidence"],
        evidence_level="high",
        confidence="high",
        status="active",
        owner_agent="coordinator",
        filename="preferred_research_style.md",
    )
    tools = ToolRegistry(
        [
            ReadFileTool(),
            WriteFileTool(),
            PythonExecTool(),
            NotebookTool(),
            ReadTableTool(),
            BasicStatsTool(),
            PlotCsvTool(),
            PubMedSearchTool(),
            ArxivSearchTool(),
            CrossrefSearchTool(),
            ResolveCitationTool(),
            SaveMemoryTool(),
            SearchMemoryTool(),
            TypedGraphQueryTool(),
            IngestLiteratureSourceTool(),
            QueryLiteratureWikiTool(),
            LintLiteratureWorkspaceTool(),
            ForgetMemoryTool(),
            ReviewMemoryTool(),
        ]
    )

    topic = os.getenv(
        "SCIENTIFIC_AGENT_TOPIC",
        "Can mild hypothermia improve post-ischemic neuronal recovery, and what would be the most discriminative next experiment?",
    )

    all_tools = tools
    if mcp_registry.clients:
        all_tools = all_tools.merge(await mcp_registry.build_tool_registry())

    try:
        result = await workflow.run(topic, tools=all_tools)
    finally:
        await mcp_registry.close()
    print("TOPIC:")
    print(result.topic)
    print("\nWORKFLOW:")
    for step in result.steps:
        print(f"\n## {step.profile_name}")
        print(step.raw_output)
    print("\nFINAL REPORT:")
    print(result.final_report)
    print("\nREPORT PATH:")
    print(result.report_path)


def _load_mcp_configs_from_env() -> list[MCPServerConfig]:
    config_path = os.getenv("SCIENTIFIC_AGENT_MCP_CONFIG")
    if not config_path:
        return []
    path = Path(config_path).resolve()
    payload = json.loads(path.read_text(encoding="utf-8"))
    configs: list[MCPServerConfig] = []
    for item in payload:
        configs.append(
            MCPServerConfig(
                name=item["name"],
                transport=item.get("transport", "stdio"),
                command=item["command"],
                cwd=item.get("cwd"),
                env=item.get("env", {}),
                timeout_seconds=float(item.get("timeout_seconds", 60.0)),
                read_only_tools=[
                    str(tool).strip()
                    for tool in item.get("read_only_tools", [])
                    if str(tool).strip()
                ],
                destructive_tools=[
                    str(tool).strip()
                    for tool in item.get("destructive_tools", [])
                    if str(tool).strip()
                ],
            )
        )
    return configs


def _resolve_model_config_path(root: Path) -> Path | None:
    explicit = os.getenv("SCIENTIFIC_AGENT_MODEL_CONFIG")
    if explicit:
        path = Path(explicit).resolve()
        return path if path.exists() else None
    default_path = root / "scientific_agent_config.json"
    return default_path if default_path.exists() else None


if __name__ == "__main__":
    asyncio.run(main())
