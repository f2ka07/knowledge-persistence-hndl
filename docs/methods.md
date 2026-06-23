# Methods

## Interpretation

Citation persistence is treated as an observable proxy for technical knowledge
persistence K(t), not as a direct measurement of trade secret value V(t).

Sector labels use OpenAlex `concepts.id` filters with stored
`classification_source` and `classification_confidence` per work.

## Reproducibility

1. Install dependencies with `pip install -e .` or `uv sync`.
2. Run `python -m pqm_readiness insight-pilot` for a quick stratified check.
3. Audit edges with `python -m pqm_readiness audit-citations`.
4. Scale with `python -m pqm_readiness run --limit-per-group 20`.

## Query definition

OpenAlex filter:
`publication_year:1995-2012,concepts.id:C41008148,cited_by_count:30-1000,has_doi:true`

Record limit: `None`

Pipeline version: `0.1.0`
Git commit: `None`
