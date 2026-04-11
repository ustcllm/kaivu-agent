# Literature Wiki Schema

This directory is maintained as a persistent literature wiki for the scientific agent.

## Core Rules

1. Never modify files in `raw_sources/`.
2. Prefer updating existing wiki pages over creating duplicates.
3. Every new source should update:
   - at least one paper page
   - `wiki/index.md`
   - `wiki/log.md`
4. Important claims must carry source links or identifiers such as DOI, PMID, arXiv id, URL, or local source path.
5. Contradictions must be recorded explicitly in controversy or mechanism pages.
6. Literature pages must distinguish:
   - claim
   - evidence
   - limitation
   - conflict
   - relevance to current hypotheses
7. If a new source weakens an older synthesis, revise the synthesis instead of silently appending.
8. Good answers to literature questions may be filed back into `wiki/reviews/` or `wiki/controversies/`.

## Directory Conventions

- `wiki/papers/`: one page per source
- `wiki/concepts/`: concept and topic pages
- `wiki/mechanisms/`: mechanism or explanation pages
- `wiki/controversies/`: disagreement tracking pages
- `wiki/methods/`: methods and protocol-related pages
- `wiki/datasets/`: benchmark and dataset pages
- `wiki/reviews/`: topic-level synthesis pages
- `review_records/screening/`: include or exclude decisions
- `review_records/evidence_tables/`: evidence rows
- `review_records/exclusion_records/`: explicit exclusions
- `review_records/protocols/`: review protocol versions

## Ingest Workflow

1. Read the raw source.
2. Create or update a page in `wiki/papers/`.
3. Update linked concept, mechanism, controversy, method, dataset, or review pages.
4. Update `wiki/index.md`.
5. Append a timestamped entry to `wiki/log.md`.
6. If the source is part of a formal review, update the screening and evidence records.
7. If the source changes current understanding, note what was strengthened, weakened, challenged, or superseded.

## Query Workflow

1. Read `wiki/index.md` first.
2. Open the most relevant pages from the wiki.
3. Use raw sources only when the wiki is missing detail or when verification is needed.
4. If the answer creates durable synthesis, save it back into the wiki.

## Lint Workflow

Look for:

- orphan pages
- stale claims
- unsupported summaries
- missing mechanism pages
- unresolved controversies
- missing inbound links
- repeated concepts with inconsistent naming

## Metadata Guidance

Use YAML frontmatter when helpful. Common keys:

- `title`
- `kind`
- `source_id`
- `doi`
- `pmid`
- `arxiv_id`
- `year`
- `study_type`
- `quality_grade`
- `bias_risk`
- `tags`
- `status`

Do not invent metadata that is not supported by the source or synthesis.
