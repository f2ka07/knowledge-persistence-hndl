"""Stage 5: research outputs and provenance artifacts."""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from loguru import logger

from pqm_readiness import __version__
from pqm_readiness.config import PipelineConfig


def _git_commit(root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def export_research_outputs(config: PipelineConfig) -> None:
    """Generate dataset card, provenance, and reproducibility docs."""
    config.ensure_dirs()
    now = datetime.now(UTC).isoformat()
    commit = _git_commit(config.root)

    provenance = {
        "pipeline_version": __version__,
        "generated_at": now,
        "git_commit": commit,
        "sources": [
            {"name": "OpenAlex", "api": "https://api.openalex.org", "license": "CC0"},
            {
                "name": "OpenCitations Index",
                "api": "https://api.opencitations.net/index/v2",
                "license": "CC-BY-4.0",
            },
        ],
        "query": {
            "openalex_filter": config.openalex_filter,
            "openalex_select": config.openalex_select,
            "limit": config.limit,
        },
    }
    provenance_path = config.provenance_path()
    provenance_path.write_text(json.dumps(provenance, indent=2), encoding="utf-8")

    dataset_card = f"""# PQM Readiness Dataset

Generated: {now}

## Description
Longitudinal citation persistence dataset built from OpenAlex works metadata and
OpenCitations incoming citation edges. Citation persistence is treated as an
observable proxy for technical knowledge persistence K(t), not as a direct
measurement of trade secret value V(t).

## Tables
- `works.parquet`
- `citations.parquet`
- `citations_by_year.parquet`
- `persistence.parquet`
- `citation_persistence_panel.parquet`
- `baseline_random_sample.parquet`
- `patent_mentions.parquet`

## Sources
- OpenAlex API (CC0)
- OpenCitations Index API v2 (CC-BY-4.0)

## License
Metadata is redistributable under the source licenses noted above.
"""
    (config.root / "dataset_card.md").write_text(dataset_card, encoding="utf-8")

    methods = f"""# Methods

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
`{config.openalex_filter}`

Record limit: `{config.limit}`

Pipeline version: `{__version__}`
Git commit: `{commit}`
"""
    (config.docs_dir / "methods.md").write_text(methods, encoding="utf-8")

    schema_doc = """# Schema

## works.parquet
| column | type | source |
| --- | --- | --- |
| work_id | string | OpenAlex `id` |
| doi | string | OpenAlex `doi` |
| year | int | OpenAlex `publication_year` |
| concept | string | OpenAlex top-scoring `concepts.display_name` |
| concept_group | string | HNDL sector from OpenAlex `concepts.id` filter |
| classification_source | string | `openalex_concepts.id_filter` |
| classification_confidence | float | OpenAlex concept score for matched sector |
| citation_count | int | OpenAlex `cited_by_count` |
| institution_count | int | derived from `authorships.institutions` |

## citations.parquet
| column | type | source |
| --- | --- | --- |
| source_doi | string | OpenCitations incoming `citing` |
| target_doi | string | OpenCitations incoming `cited` |
| citation_creation_date | string | OpenCitations `creation` |
| citation_lag_years | float | citation_year - publication_year |

## citations_by_year.parquet
| column | type | source |
| --- | --- | --- |
| work_id | string | OpenAlex `work_id` |
| doi | string | OpenAlex `doi` |
| concept_group | string | HNDL sector label |
| publication_year | int | work publication year |
| citation_year | int | year of incoming citation |
| age_years | int | citation_year - publication_year |
| annual_citations | int | count of incoming citations in year |
| cumulative_citations | int | running sum by work |
| normalized_annual_citations | float | annual / max annual for work |
| normalized_cumulative_citations | float | cumulative / total for work |
| expected_citations_at_age | float | mean annual citations for field at age |
| normalized_citation_rate | float | annual / expected(field, age) |
| field_percentile | float | percentile within field at age |
| year_percentile | float | percentile within publication year at age |

## persistence.parquet
| column | type | source |
| --- | --- | --- |
| work_id | string | OpenAlex `work_id` |
| publication_year | int | work publication year |
| last_observed_year | int | latest incoming citation year in window |
| observed_window_years | float | last_observed_year - publication_year |
| first_citation_year | int | earliest incoming citation year |
| last_citation_year | int | latest incoming citation year |
| citation_lifespan_years | float | last - first citation year |
| peak_citation_year | int | year with max annual citations |
| peak_age_years | float | age at peak annual citations |
| estimated_half_life_years | float | age when cumulative reaches 50% |
| half_life_censored | bool | true if right-censored or 50% not reached |
| decay_start_year | int | first year after peak with lower annual count |
| post_peak_decay_rate | float | slope of annual counts after peak |
| long_tail_indicator | bool | citations 5+ years after peak |
| censoring_flag | bool | still cited at observation window end |

## baseline_random_sample.parquet
Null-model cohort matched on publication year with random non-HNDL concepts.

## patent_mentions.parquet
| column | type | source |
| --- | --- | --- |
| doi | string | work DOI |
| patent_mentions | int | Crossref Event Data (cambia-lens) |
| source | string | cambia-lens |
| enrichment_status | string | ok or unavailable |

## citation_persistence_panel.parquet
| column | type | source |
| --- | --- | --- |
| work_id | string | OpenAlex `work_id` |
| concept_group | string | HNDL sector label |
| age_years | int | years since publication |
| observed_citation_rate | float | normalized annual citation rate |
| cumulative_citation_share | float | normalized cumulative share |
| normalized_citation_rate | float | annual / expected(field, age) |
| field_percentile | float | field percentile at age |
| year_percentile | float | publication-year percentile at age |
| citation_share_remaining | float | 1 - cumulative share |
| censoring_flag | bool | right-censoring indicator |
"""
    (config.docs_dir / "schema.md").write_text(schema_doc, encoding="utf-8")

    reproducibility = """# Reproducibility

- Deterministic query filters and sort order (`cited_by_count:desc`)
- Checkpoint files in `data/metadata/checkpoint_*.json`
- Full provenance in `data/metadata/provenance.json`
- Quality report in `data/metadata/quality_report.json`
"""
    (config.docs_dir / "reproducibility.md").write_text(reproducibility, encoding="utf-8")

    citation_cff = f"""cff-version: 1.2.0
title: PQM Readiness Dataset
version: {__version__}
date-released: {now[:10]}
license: CC-BY-4.0
"""
    (config.root / "CITATION.cff").write_text(citation_cff, encoding="utf-8")

    license_text = """CC-BY-4.0

This repository code and generated documentation are released under Creative Commons
Attribution 4.0 International. Source metadata retains upstream licenses (OpenAlex CC0,
OpenCitations CC-BY-4.0).
"""
    (config.root / "LICENSE.md").write_text(license_text, encoding="utf-8")

    doi_template = {
        "title": "PQM Readiness Dataset",
        "creators": [],
        "publication_year": datetime.now(UTC).year,
        "resource_type": "Dataset",
        "version": __version__,
        "notes": "Assign DOI via Zenodo/Figshare before publication.",
    }
    (config.metadata_dir / "dataset_doi_template.json").write_text(
        json.dumps(doi_template, indent=2),
        encoding="utf-8",
    )

    requirements = """pandas>=2.2
polars>=1.0
pyarrow>=17.0
duckdb>=1.0
httpx>=0.27
tenacity>=9.0
pydantic>=2.8
typer>=0.12
rich>=13.7
loguru>=0.7
truststore>=0.9
certifi>=2024.0
"""
    (config.root / "requirements.txt").write_text(requirements, encoding="utf-8")

    environment = f"""name: pqm-readiness
channels:
  - conda-forge
dependencies:
  - python=3.12
  - pip
  - pip:
      - -e .
"""
    (config.root / "environment.yml").write_text(environment, encoding="utf-8")

    logger.success("Research outputs exported to project root and docs/")
