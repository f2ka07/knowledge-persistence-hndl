"""Rebuild persistence tables with influence-decay fields (no API calls)."""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from pqm_readiness.config import PipelineConfig
from pqm_readiness.transform.baseline import (
    build_baseline_matched_sample,
    build_baseline_random_sample,
    build_baseline_year_only_sample,
)
from pqm_readiness.transform.build import build_tables


def rebuild_persistence(config: PipelineConfig) -> None:
    """Recompute persistence metrics for HNDL and all baseline cohorts."""
    config.ensure_dirs()
    raw = config.raw_dir
    processed = config.processed_dir
    observation_year = config.observation_year

    openalex_path = raw / "openalex_works.parquet"
    opencitations_path = raw / "opencitations_citations.parquet"
    if not openalex_path.exists() or not opencitations_path.exists():
        raise FileNotFoundError("Missing raw openalex_works or opencitations_citations parquet")

    build_tables(config, openalex_path, opencitations_path)

    baseline_specs = (
        ("baseline_works.parquet", "baseline_opencitations_citations.parquet", build_baseline_random_sample),
        ("baseline_matched_works.parquet", "baseline_matched_opencitations_citations.parquet", build_baseline_matched_sample),
        ("baseline_year_only_works.parquet", "baseline_year_only_opencitations_citations.parquet", build_baseline_year_only_sample),
    )
    for works_name, oc_name, builder in baseline_specs:
        works_path = raw / works_name
        oc_path = raw / oc_name
        if works_path.exists() and oc_path.exists():
            builder(works_path, oc_path, processed, observation_year)

    logger.success("Rebuilt persistence with influence-decay fields")
