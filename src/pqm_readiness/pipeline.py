"""End-to-end pipeline orchestration."""

from __future__ import annotations

from pathlib import Path

import polars as pl
from loguru import logger

from pqm_readiness.config import PipelineConfig
from pqm_readiness.export.outputs import export_research_outputs
from pqm_readiness.ingest.baseline import ingest_baseline_matched, ingest_baseline_sample
from pqm_readiness.ingest.openalex import ingest_openalex
from pqm_readiness.ingest.opencitations import ingest_opencitations
from pqm_readiness.ingest.patents import ingest_patent_mentions
from pqm_readiness.transform.baseline import (
    build_baseline_matched_sample,
    build_baseline_random_sample,
    build_null_model_comparison,
)
from pqm_readiness.transform.build import build_tables
from pqm_readiness.validate.quality import validate_dataset


def _copy_patent_mentions(config: PipelineConfig, raw_path: Path) -> Path:
    processed_path = config.processed_dir / "patent_mentions.parquet"
    if raw_path.exists():
        pl.read_parquet(raw_path).write_parquet(processed_path)
    return processed_path


def run_pipeline(config: PipelineConfig) -> None:
    """Execute all pipeline stages in order."""
    config.ensure_dirs()
    if not config.resume:
        config.reset_run_artifacts()
    logger.info(
        "Starting pipeline (limit={}, filter={})",
        config.limit,
        config.openalex_filter,
    )

    openalex_path = ingest_openalex(config)
    baseline_path = config.raw_dir / "baseline_works.parquet"
    baseline_matched_path = config.raw_dir / "baseline_matched_works.parquet"
    if config.enable_baseline:
        baseline_path = ingest_baseline_sample(config, openalex_path)
        baseline_matched_path = ingest_baseline_matched(config, openalex_path)
    opencitations_path = ingest_opencitations(config, openalex_path)
    baseline_opencitations_path = config.raw_dir / "baseline_opencitations_citations.parquet"
    baseline_matched_opencitations_path = (
        config.raw_dir / "baseline_matched_opencitations_citations.parquet"
    )
    if config.enable_baseline and baseline_path.exists():
        ingest_opencitations(
            config,
            baseline_path,
            output_name="baseline_opencitations_citations.parquet",
            checkpoint_stage="opencitations_baseline",
        )
    if config.enable_baseline and baseline_matched_path.exists():
        ingest_opencitations(
            config,
            baseline_matched_path,
            output_name="baseline_matched_opencitations_citations.parquet",
            checkpoint_stage="opencitations_baseline_matched",
        )
    patent_raw_path = (
        ingest_patent_mentions(config, openalex_path)
        if config.enable_patent_enrichment
        else config.raw_dir / "patent_mentions.parquet"
    )
    build_tables(config, openalex_path, opencitations_path)
    if config.enable_baseline and baseline_path.exists():
        build_baseline_random_sample(
            baseline_path,
            baseline_opencitations_path,
            config.processed_dir,
            config.observation_year,
        )
        build_null_model_comparison(
            config.processed_dir / "persistence.parquet",
            config.processed_dir / "baseline_random_sample.parquet",
            config.processed_dir,
            config.processed_dir / "citation_persistence_panel.parquet",
            baseline_label="baseline_random",
        )
    if config.enable_baseline and baseline_matched_path.exists():
        build_baseline_matched_sample(
            baseline_matched_path,
            baseline_matched_opencitations_path,
            config.processed_dir,
            config.observation_year,
        )
        build_null_model_comparison(
            config.processed_dir / "persistence.parquet",
            config.processed_dir / "baseline_matched.parquet",
            config.processed_dir,
            config.processed_dir / "citation_persistence_panel.parquet",
            baseline_label="baseline_matched",
        )
    if config.enable_patent_enrichment:
        _copy_patent_mentions(config, patent_raw_path)
    validate_dataset(config)
    from pqm_readiness.validate.audit_citations import audit_citations

    audit_citations(config)
    export_research_outputs(config)

    logger.success("Pipeline complete")
