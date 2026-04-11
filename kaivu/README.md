# Kaivu（开物）

Kaivu（开物）is a Python framework for literature review, hypothesis generation, experiment execution loops, memory, provenance graphs, and multi-researcher collaboration.

The name comes from “开物”: uncovering the principles and practical workings of things through observation, reasoning, and experiment.

It now includes:

- multi-turn agent loop and task tracking
- tool registry, permission policy, and mixed serial/concurrent tool execution
- OpenAI Responses API backend
- three-layer memory design: instruction memory, persistent scientific memory, and rolling session memory
- structured outputs with local salvage and model-based repair
- dynamic multi-specialist routing
- file-based skills loading and prompt injection
- minimal MCP stdio client, registry, and MCP-to-tool adapter
- prompt section builder
- subagent runtime for specialist execution
- literature tools for PubMed, arXiv, Crossref, and DOI/PMID resolution
- data tools for CSV/XLSX reading, descriptive stats, and plotting
- Markdown report generation with aggregated references
- per-agent model policies with config-file and environment overrides
- an `experiments/` submodule with experiment objects, research asset registry, and discipline-specific quality-control checklists

## Files

- `messages.py`: message and tool-call structures
- `state.py`: session state and task records
- `tools.py`: base tools plus memory tools
- `memory.py`: instruction memory, persistent memory index, session memory
- `literature_tools.py`: literature search, DOI/PMID resolution, abstract enrichment
- `data_tools.py`: table reading, stats, plotting
- `permissions.py`: permission policy
- `mcp/`: MCP client, registry, tool adapter, and types
- `skills/`: skill loading, runtime selection, and types
- `skills_builtin/`: bundled example skills
- `prompts/`: prompt sections and prompt builder
- `agents/`: subagent runtime and specs
- `structured_output.py`: schema instruction, parsing, salvage, repair prompt
- `profiles.py`: specialist profiles and required output schemas
- `model.py`: stub model and OpenAI Responses API backend
- `engine.py`: single-agent runtime
- `workflow.py`: multi-agent scientific workflow with dynamic routing
- `reporting.py`: Markdown report rendering and persistence
- `experiments/`: experiment specifications, protocols, runs, observations, quality control, interpretations, and asset registry helpers
- `demo.py`: real OpenAI API workflow entry
- `stub_demo.py`: local no-key demo

## Experiment objects

The `experiments/` module now includes:

- `ExperimentSpecification`
- `ExperimentalProtocol`
- `ExperimentRun`
- `ObservationRecord`
- `QualityControlReview`
- `InterpretationRecord`
- `ResearchAssetRecord`
- `ExperimentRegistry`

It also includes discipline-specific quality-control checklists for:

- `chemistry`
- `chemical_engineering`
- `physics`
- `artificial_intelligence`
- `mathematics`

## Specialist agents

- `literature_reviewer`
- `data_curator`
- `hypothesis_generator`
- `experiment_designer`
- `data_analyst`
- `critic`
- `safety_ethics_reviewer`
- `coordinator`
- `report_writer`

## Memory design

Kaivu now mirrors the most useful memory layers from `cc`:

- instruction memory:
  reads `CLAUDE.md`, `.agent/CLAUDE.md`, and `.agent/rules/*.md`
- persistent scientific memory:
  uses `memory/MEMORY.md` as an index and per-topic `.md` files as the real memory bodies
- session memory:
  uses `memory/session/current_session.md` as a rolling session summary

### Scientific memory schema

Persistent scientific memories now support these fields:

- `type`: `fact`, `hypothesis`, `method`, `decision`, `dataset_note`, `warning`, `preference`, `reference`
- `scope`: `instruction`, `project`, `agent`, `team`, `session`
- `summary`
- `tags`
- `source_refs`
- `evidence_level`
- `confidence`
- `status`
- `owner_agent`
- `created_at`
- `last_verified_at`
- `supersedes`
- `superseded_by`

This is meant to prevent a research agent from confusing hypotheses with facts, or stale notes with active knowledge.

### Memory tools

- `save_memory`
- `search_memory`
- `forget_memory`

Recall is no longer plain keyword match. It now combines:

- query overlap
- memory type weighting
- evidence level
- confidence
- status
- recency from `last_verified_at`

Long-term memory is now also partially automatic:

- after an agent run, the framework can extract durable user preferences
- it can capture candidate hypotheses, decisions, warnings, and dataset notes
- extraction is intentionally conservative and deduplicates by title

## Prompt and subagent architecture

Prompt assembly is now section-based rather than ad hoc string concatenation.

Current prompt sections include:

- role
- memory
- workflow state
- skills
- structured output
- MCP
- safety

Specialist execution now runs through a dedicated subagent runtime:

- each specialist is executed as a subagent spec
- prompt building is centralized
- memory is shared through the runtime
- this is a stepping stone toward a fuller `cc`-style multi-agent runtime

## Run

Real model workflow:

```bash
set OPENAI_API_KEY=your_key_here
python C:/Users/liand/Documents/agent/scripts/run_demo.py
```

Optional environment variables:

- `KAIVU_MODEL`
- `KAIVU_TOPIC`
- `KAIVU_REPORT_PATH`
- `KAIVU_DYNAMIC_ROUTING`
- `KAIVU_MCP_CONFIG`
- `KAIVU_MODEL_CONFIG`

Per-agent model policy can now be loaded from `config/agents.json`, or from a custom path via `KAIVU_MODEL_CONFIG`.

Example:

```json
{
  "agents": {
    "literature_reviewer": {
      "model": "gpt-5",
      "reasoning_effort": "high",
      "max_output_tokens": 2200,
      "allow_web_search": true
    },
    "report_writer": {
      "model": "gpt-5-mini",
      "reasoning_effort": "low",
      "max_output_tokens": 1400
    }
  }
}
```

Environment variables still override the file when needed. For example:

- `KAIVU_CRITIC_MODEL`
- `KAIVU_CRITIC_REASONING`
- `KAIVU_REPORT_WRITER_MODEL`

Local stub demo:

```bash
python C:/Users/liand/Documents/agent/kaivu/stub_demo.py
```

## Notes

- `plot_csv` requires local `matplotlib`
- `read_table` supports `.csv` and `.xlsx`
- literature tools require network access
- the real workflow requires `OPENAI_API_KEY`
- structured outputs are first locally salvaged when possible, then repaired with a model if needed
- dynamic routing now uses completed specialist outputs to decide what should run next
- final reports automatically include aggregated references
- bundled skills are loaded from `kaivu/skills_builtin`
- MCP config is expected as a JSON file describing stdio servers

## Good next upgrades

1. Add a small-model memory selector closer to `cc`'s `findRelevantMemories` design.
2. Add automatic long-term memory extraction from conversation outcomes, corrections, and project decisions.
3. Add stronger evidence grading and source-quality scoring.
4. Add team memory and agent-scope memory snapshots for collaborative research workflows.

