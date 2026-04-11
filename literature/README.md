# Literature Workspace

This directory is the persistent literature layer for the scientific agent.

It follows a three-layer pattern:

1. Raw sources are stored under `raw_sources/` and are never modified.
2. The wiki under `wiki/` is LLM-maintained markdown that accumulates synthesis.
3. Formal review records under `review_records/` preserve screening, evidence tables, and review protocol updates.

The typed research graph and the scientific agent memory system should treat this directory as a human-readable companion layer, not a replacement.

## Main Directories

- `raw_sources/`: immutable source documents
- `wiki/`: interlinked markdown pages
- `review_records/`: structured review workflow records
- `exports/`: generated outputs such as reports or slide decks

## Expected Agent Operations

- Ingest a source into `raw_sources/`
- Create or update a page in `wiki/papers/`
- Update linked pages in `wiki/concepts/`, `wiki/mechanisms/`, `wiki/controversies/`, `wiki/methods/`, `wiki/datasets/`, or `wiki/reviews/`
- Update `wiki/index.md`
- Append an entry to `wiki/log.md`
- Update `review_records/` when screening decisions, exclusion reasons, evidence table rows, or review protocol changes occur
- Sync key entities and relations into the typed research graph

## Design Principles

- Raw sources remain the source of truth
- Wiki pages are persistent synthesis artifacts
- Review records are auditable and versionable
- Contradictions should be surfaced, not hidden
- Hypotheses, mechanisms, experiments, and evidence should stay linked
