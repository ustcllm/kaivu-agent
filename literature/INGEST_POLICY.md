# Literature Ingest Policy

- `autonomous`: default for ordinary project/personal intake. The source is written to `raw_sources/{papers,reports,web}/` and can later update wiki pages, review records, graph nodes, and memory.
- `guided`: used when the paper is high-impact, high-conflict, low-confidence, or explicitly requested by the researcher. The system writes a digest to `ingest_drafts/` first; the wiki is updated only after the digest direction is accepted.
- `review_gated`: used for group/public knowledge when the caller is not a curator/admin, or when shared high-impact/high-conflict sources could rewrite group consensus. The system writes a proposal to `ingest_proposals/`.
- Papers go to `raw_sources/papers/` after autonomous approval and should produce paper pages.
- Reports go to `raw_sources/reports/` after autonomous approval and should be marked as report-style evidence.
- Web articles go to `raw_sources/web/` after autonomous approval and should be downweighted unless they provide primary evidence.
- Dataset cards and benchmark notes should update `wiki/datasets/` only after the selected ingest mode allows promotion.
- Each ingest, draft, or proposal updates `wiki/log.md`.
- Confirmed literature writes should update `wiki/index.md`.
- Contradictions should update controversy or mechanism pages instead of being buried in summaries.
