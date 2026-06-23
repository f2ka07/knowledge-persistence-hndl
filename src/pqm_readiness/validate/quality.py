"""Stage 4: dataset quality validation."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl
from loguru import logger

from pqm_readiness.config import PipelineConfig


def _null_ratio(df: pl.DataFrame, column: str) -> float:
    if df.height == 0:
        return 0.0
    return float(df.select(pl.col(column).is_null().mean()).item())


def _duplicate_ratio(df: pl.DataFrame, columns: list[str]) -> float:
    if df.height == 0:
        return 0.0
    dupes = df.height - df.unique(subset=columns, maintain_order=True).height
    return dupes / df.height


def _distribution(df: pl.DataFrame, column: str) -> dict[str, int]:
    if column not in df.columns or df.height == 0:
        return {}
    return dict(df.group_by(column).len().sort(column).rows())


def validate_dataset(config: PipelineConfig) -> Path:
    """Run quality checks and emit quality_report.json."""
    config.ensure_dirs()
    processed = config.processed_dir
    works = pl.read_parquet(processed / "works.parquet")
    citations = pl.read_parquet(processed / "citations.parquet")
    citations_by_year = pl.read_parquet(processed / "citations_by_year.parquet")
    persistence = pl.read_parquet(processed / "persistence.parquet")
    panel = pl.read_parquet(processed / "citation_persistence_panel.parquet")
    baseline_path = processed / "baseline_random_sample.parquet"
    baseline = pl.read_parquet(baseline_path) if baseline_path.exists() else None
    patent_path = processed / "patent_mentions.parquet"
    patents = pl.read_parquet(patent_path) if patent_path.exists() else None

    doi_coverage = float(works.filter(pl.col("doi").is_not_null()).height / works.height) if works.height else 0.0
    cited_dois = set(citations.get_column("target_doi").drop_nulls().to_list())
    opencitations_match_rate = (
        float(works.filter(pl.col("doi").is_in(list(cited_dois))).height / works.height)
        if works.height
        else 0.0
    )
    censored_count = int(persistence.filter(pl.col("censoring_flag")).height) if "censoring_flag" in persistence.columns else 0

    report: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "metrics": {
            "coverage": {
                "works_count": works.height,
                "citations_count": citations.height,
                "citations_by_year_count": citations_by_year.height,
                "persistence_count": persistence.height,
                "panel_count": panel.height,
                "doi_coverage": round(doi_coverage, 4),
                "opencitations_match_rate": round(opencitations_match_rate, 4),
                "coverage_by_concept_group": _distribution(works, "concept_group"),
            },
            "distributions": {
                "publication_year": _distribution(works, "year"),
                "citation_count_bins": _distribution(
                    works.with_columns(
                        pl.when(pl.col("citation_count") < 100)
                        .then(pl.lit("<100"))
                        .when(pl.col("citation_count") < 500)
                        .then(pl.lit("100-499"))
                        .otherwise(pl.lit("500+"))
                        .alias("citation_bin")
                    ),
                    "citation_bin",
                ),
            },
            "completeness": {
                "works_null_ratios": {col: round(_null_ratio(works, col), 4) for col in works.columns},
                "citations_null_ratios": {
                    col: round(_null_ratio(citations, col), 4) for col in citations.columns
                },
            },
            "censoring": {
                "censored_record_count": censored_count,
                "baseline_sample_count": baseline.height if baseline is not None else 0,
            },
            "patent_enrichment": {
                "records": patents.height if patents is not None else 0,
                "available_share": float(
                    patents.filter(pl.col("enrichment_status") == "ok").height / patents.height
                )
                if patents is not None and patents.height
                else 0.0,
            },
        },
        "integrity": {
            "duplicates": {
                "works_work_id_ratio": round(_duplicate_ratio(works, ["work_id"]), 4),
                "citations_edge_ratio": round(
                    _duplicate_ratio(citations, ["source_doi", "target_doi", "citation_creation_date"]),
                    4,
                ),
            },
            "date_consistency": {
                "negative_lag_count": int(
                    citations.filter(pl.col("citation_lag_years") < 0).height
                ),
            },
        },
        "passed": True,
    }

    if report["integrity"]["date_consistency"]["negative_lag_count"] > 0:
        report["passed"] = False
    if doi_coverage < 1.0:
        report["passed"] = False

    output = config.metadata_dir / "quality_report.json"
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    logger.success("Quality report written to {} (passed={})", output, report["passed"])
    return output
