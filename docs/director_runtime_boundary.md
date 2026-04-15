# ResearchDirector / ScientificAgentRuntime Boundary

Kaivu uses composition rather than inheritance between the project director and the single-agent runtime.

## Core Rule

Let the language model handle scientific reasoning. Let Kaivu handle scientific governance.

In code terms:

- `ResearchDirector` owns project-level research governance.
- `ScientificAgentRuntime` owns single-agent lifecycle execution and runtime observability.
- `ScientificAgent` owns scientific lifecycle semantics and prompt-driven hooks.
- `director_services/` owns pure state transformation helpers.

## ResearchDirector Owns

- Research campaign coordination.
- Multi-specialist routing and lab-meeting style coordination.
- Project, group, and user collaboration context.
- Claim graph and research state aggregation.
- Project-level memory and graph approval/landing.
- Reports, manifests, ledgers, and release artifacts.
- Cross-agent consensus, conflict handling, and decision closure.

`ResearchDirector` may request a single-agent runtime summary, but it should not construct agent runtime internals directly. Use `DirectorRuntimeBridge`.

## ScientificAgentRuntime Owns

- Running one `ScientificAgent` lifecycle.
- Stage execution records.
- Tool capability resolution.
- Tool execution policy enforcement.
- Memory and graph update requests proposed by an agent.
- External execution requests.
- Trajectory events for replay, benchmark, and future training.

The runtime should not write project reports, decide group consensus, or own project-level memory promotion.

## ScientificAgent Owns

- Stable scientific lifecycle hooks.
- Problem framing, literature plan, hypothesis generation, experiment design, result interpretation, failure classification, and next-action proposal.
- Discipline profile and prompt-driven scientific semantics.
- Capability declarations, not direct tool execution.

## Director Services Own

- Pure transformations over existing state.
- Literature summaries, experiment summaries, memory/graph summaries, run manifests, and research-state input aggregation.
- No tool calls.
- No filesystem writes.
- No model calls.

## Bridge Pattern

`DirectorRuntimeBridge` is the only project-level adapter that should translate `ResearchDirector` context into `ScientificAgentRuntime` calls.

This keeps the direction clear:

```text
ResearchDirector
  -> DirectorRuntimeBridge
    -> ScientificAgentRuntime
      -> ScientificAgent
```

The reverse direction should not happen. Runtime results can be summarized back into project state, but `ScientificAgentRuntime` should not reach up into `ResearchDirector`.
