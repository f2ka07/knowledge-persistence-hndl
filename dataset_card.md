# Dataset Card: Knowledge Persistence (HNDL)

## Dataset name

Knowledge Persistence (HNDL) Citation Dataset — `v0.2_candidate`

## Motivation

Long-horizon cryptographic risk models need estimates of how long technical information remains strategically relevant. This dataset provides an open, reproducible citation-based operationalisation of **influence persistence** for HNDL-relevant technical sectors, with matched null-model baselines.

## Sources

| Source | API | License |
| --- | --- | --- |
| OpenAlex | https://api.openalex.org | CC0 |
| OpenCitations Index | https://api.opencitations.net/index/v2 | CC-BY-4.0 |

Collection used only bibliographic metadata and citation edges. No Scopus, Web of Science, or paywalled full text.

## Schema

See [docs/schema.md](docs/schema.md). Primary tables:

- `works.parquet` — HNDL-stratified works sample
- `citations_by_year.parquet` — annual incoming citation counts by work age
- `persistence.parquet` — half-life, censoring, and influence-decay outcomes
- `baseline_{random,year_only,matched}.parquet` — three-tier null-model cohorts
- `threshold_sensitivity.parquet` — decay-threshold grid stability analysis

## Intended use

- Survival analysis of influence decay P(T_decay > t)
- Matched cohort comparisons (random / year-only / fully matched)
- Sensitivity analysis of decay-threshold parameters
- Parameterising citation-based persistence proxies K(t) in HNDL risk models

## Out of scope

- Direct measurement of trade secret or classified information value V(t)
- Sector-level causal claims without matched controls
- Real-time ingestion or API-dependent reproduction (use frozen snapshot)
- Scaling inference beyond the fixed 188-work pilot (event count gate not met)

## Ethical and legal notes

- Public metadata and citation graph only; no author PII beyond bibliographic fields
- OpenAlex and OpenCitations attribution required for redistribution
- Raw API dumps are excluded from public release; processed derivatives only

## Limitations

- 188 HNDL works; 37 influence-decay events; high censoring (~80%)
- Citation count is partly endogenous to persistence
- `dataset_v0.1` predates a cited_doi linkage fix and is excluded
- Influence decay rule is heuristic (10% peak, 3 consecutive years); stability verified 10–15%

## Citation

```bibtex
@dataset{knowledge_persistence_hndl_2026,
  title  = {Knowledge Persistence (HNDL) Citation Dataset},
  version = {0.2.0},
  year   = {2026},
  license = {CC-BY-4.0}
}
```

## Files

Frozen bundle: `dataset_v0.2_candidate/manifest.json` (SHA-256 per file).
