# Kaivu Project Structure

Kaivu is organized as a local-first scientific agent workspace. The codebase and the research workspace live together, but they have different responsibilities.

## Top-Level Layout

```text
kaivu-agent/
  kaivu/                 # Python scientific agent core
  service/               # FastAPI service layer
  web/                   # Interactive workbench frontend
  scripts/               # Local CLI and maintenance scripts
  config/                # Human-editable runtime configuration
  literature/            # Literature research workspace
  memory/                # Personal, project, group, agent, and session memory
  artifacts/             # Durable research outputs and generated packages
  reports/               # Human-readable reports
  test_artifacts/        # Test fixtures and ignored temporary outputs
  .state/                # Ignored runtime state, indexes, manifests, registries
  docs/                  # Architecture and operating documentation
```

## Python Core

```text
kaivu/
  agents/                # Agent configs, subagent runtime, role execution
  ai_research/           # AI research workflow, evaluation, ablation, executor scaffold
  benchmarks/            # Built-in benchmark and replay cases
  experiments/           # Experiment records, protocols, observations, quality control
  graph/                 # Typed provenance graph registry
  mcp/                   # MCP client, registry, and tool adapters
  prompts/               # Prompt section builder
  runtime/               # Runtime memory, context compression, manifests, trajectories
  skills/                # User/project scientific skill manager
  skills_builtin/        # Built-in scientific skills
```

Root-level modules under `kaivu/` are still allowed for cross-cutting scientific kernels, but new domain-specific code should usually go into a package directory.

Recommended placement:

```text
kaivu/ai_research/       # AI discipline and task execution planning
kaivu/experiments/       # Discipline-neutral experiment records
kaivu/runtime/           # Runtime observability, session, context, replay
kaivu/graph/             # Source-of-truth provenance graph
kaivu/agents/            # Agent role/config/runtime concerns
```

## Research Workspace

These directories are research assets, not library source code.

```text
literature/
  disciplines/<discipline>/projects/<project>/
    raw_sources/         # Immutable source documents
    ingest_drafts/       # Reviewable ingest digests
    ingest_proposals/    # High-risk or review-gated ingest proposals
    wiki/                # Maintained literature wiki
    review_records/      # Screening, evidence tables, exclusion records
    exports/             # Review or report exports

memory/
  disciplines/<discipline>/projects/<project>/
    personal/            # User-scoped memory
    projects/            # Project-scoped memory
    groups/              # Research group memory
    agents/              # Role-specific agent memory
    session/             # Current or recent session memory
    public/              # Public or broadly shareable memory

artifacts/
  experiments/           # Durable experiment outputs
  ai_research/           # AI research generated plans and packages
  submissions/           # Competition or benchmark submission artifacts
```

## Runtime State

`.state/` is intentionally ignored by git. It can contain:

```text
.state/
  disciplines/<discipline>/projects/<project>/
    graph/               # Typed graph facts, nodes, edges, snapshots
    events/              # Event ledger
    experiments/         # Local experiment registry
    programs/            # Research program snapshots
    runtime_manifests/   # Per-run runtime manifests
    ai_research/         # Generated AIResearchWorkflow state
  service/               # Service thread and collaboration state
```

New workflow, memory, literature, graph, event, program, and runtime-manifest writes should use
`ResearchWorkspaceLayout` and include `discipline`, `project_id`, `group_id`, and `user_id` when
available. The legacy root folders remain readable for compatibility, but different discipline
agents should not write into the same root-level `literature/`, `memory/`, or `.state/` namespace.

Rule of thumb:

```text
Durable human-readable research artifact -> artifacts/, literature/, memory/, reports/
Runtime cache or registry state           -> .state/
Temporary test output                     -> test_artifacts/tmp/
Python package code                       -> kaivu/
Service API code                          -> service/
Frontend code                             -> web/
```

## Adapter Layering

Discipline and task adapters should follow this hierarchy:

```text
Kaivu Core
  -> General Scientific Adapter
  -> Discipline Adapter
  -> Task Adapter
  -> Toolchain Adapter
```

Examples:

```text
AI Research
  -> Kaggle Competition
  -> Python / sklearn / LightGBM

Chemistry
  -> Reaction Optimization
  -> RDKit / ELN / instrument handoff

Mathematics
  -> Theorem Proving
  -> Lean / symbolic search
```

Do not duplicate memory, scheduler, graph, runtime manifest, or permission systems inside each adapter. Adapters should contribute domain-specific contracts, not reinvent the agent runtime.

## Temporary Files

All throwaway checks should write under:

```text
test_artifacts/tmp/
```

Avoid creating new `.tmp*` directories at the repository root. If a local test needs a temporary workspace, use:

```text
test_artifacts/tmp/<short-purpose-name>/
```

This keeps the project root readable and prevents generated state from looking like source code.
