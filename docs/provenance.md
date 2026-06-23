# Provenance

## Data sources

### OpenAlex

- **API:** https://api.openalex.org
- **License:** CC0
- **Fields used:** work ID, DOI, publication year, cited-by count, concepts, authorships, primary location
- **Query window:** publication years 1995–2012, `cited_by_count` 30–1000, `has_doi:true`
- **Sampling:** stratified by eight HNDL concept groups (cybersecurity, cryptography, quantum computing, etc.)

### OpenCitations Index

- **API:** https://api.opencitations.net/index/v2
- **License:** CC-BY-4.0
- **Fields used:** citing DOI, cited DOI, citation creation date
- **Direction:** incoming citations to each sampled work DOI

Raw API responses are stored in the development workspace only (`data/raw/`). The public release ships processed tables.

## Transformations

1. **Works normalisation** — OpenAlex records to `works.parquet` with `concept_group` labels
2. **Citation linkage** — OpenCitations edges joined to works via cited DOI (`target_doi`)
3. **Annual series** — `citations_by_year.parquet` with age since publication, cumulative counts, normalised rates
4. **Persistence metrics** — half-life, censoring flags, peak age, long-tail indicators
5. **Influence decay** — event when annual rate < 10% of peak for 3 consecutive years (missing years = 0)

## Matching strategy (three-tier baselines)

| Tier | Label | Matching dimensions |
| --- | --- | --- |
| A | `baseline_random` | Publication year + random non-HNDL concepts |
| B | `baseline_year_only` | Publication year + DOI only |
| C | `baseline_matched` | Year + citation band + concept depth + source type |

Decomposition pattern: random significant → year-only still significant → fully matched neutral suggests influence accumulation explains apparent persistence differences.

## Influence decay event definition

Primary survival outcome (v0.2):

```
annual_citation_rate < 0.1 * peak_annual_rate
for 3 consecutive age-years
```

Threshold sensitivity grid (see `threshold_sensitivity.parquet`) confirms tier-C neutrality is stable in the 10–15% region with 3 consecutive years.

## Freeze

- **Version:** `v0.2_candidate`
- **Frozen at:** see `dataset_v0.2_candidate/manifest.json`
- **Collection status:** closed; no further API ingestion for this release

## Pipeline

Python package `pqm_readiness` (v0.1.0). Analysis-phase commands run on local files only.
