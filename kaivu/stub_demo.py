from __future__ import annotations

import asyncio
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from kaivu.data_tools import BasicStatsTool, ReadTableTool
    from kaivu.engine import ToolCallingAgent
    from kaivu.memory import MemoryManager
    from kaivu.model import StubScienceModel
    from kaivu.permissions import PermissionPolicy
    from kaivu.tools import (
        ForgetMemoryTool,
        IngestLiteratureSourceTool,
        LintLiteratureWorkspaceTool,
        NotebookTool,
        PythonExecTool,
        QueryLiteratureWikiTool,
        ReadFileTool,
        ReviewMemoryTool,
        SaveMemoryTool,
        SearchMemoryTool,
        TypedGraphQueryTool,
        ToolRegistry,
        WriteFileTool,
    )
else:
    from .data_tools import BasicStatsTool, ReadTableTool
    from .engine import ToolCallingAgent
    from .memory import MemoryManager
    from .model import StubScienceModel
    from .permissions import PermissionPolicy
    from .tools import (
        ForgetMemoryTool,
        IngestLiteratureSourceTool,
        LintLiteratureWorkspaceTool,
        NotebookTool,
        PythonExecTool,
        QueryLiteratureWikiTool,
        ReadFileTool,
        ReviewMemoryTool,
        SaveMemoryTool,
        SearchMemoryTool,
        TypedGraphQueryTool,
        ToolRegistry,
        WriteFileTool,
    )


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
    build_demo_workspace(root)

    agent = ToolCallingAgent(
        model=StubScienceModel(),
        tools=ToolRegistry(
            [
                ReadFileTool(),
                WriteFileTool(),
                PythonExecTool(),
                NotebookTool(),
                ReadTableTool(),
                BasicStatsTool(),
                SaveMemoryTool(),
                SearchMemoryTool(),
                TypedGraphQueryTool(),
                IngestLiteratureSourceTool(),
                QueryLiteratureWikiTool(),
                LintLiteratureWorkspaceTool(),
                ForgetMemoryTool(),
                ReviewMemoryTool(),
            ]
        ),
        cwd=root,
        system_prompt=(
            "You are a scientific research agent. "
            "Use tools when needed, keep a lab notebook, and ground conclusions in evidence."
        ),
        permission_policy=PermissionPolicy(mode="deny_destructive"),
        memory_manager=MemoryManager(root),
    )

    result = await agent.run("请先读取实验文件，然后总结里面最重要的观察。")
    print("FINAL:")
    print(result.final_text)
    print("\nMESSAGES:")
    for msg in result.state.messages:
        print(f"[{msg.role}] {msg.content}")


if __name__ == "__main__":
    asyncio.run(main())



