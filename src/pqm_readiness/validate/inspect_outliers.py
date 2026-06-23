"""Identify citation-volume outliers before scaling."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import polars as pl
from loguru import logger

from pqm_readiness.config import PipelineConfig


def inspect_outliers(config: PipelineConfig, top_n: int = 20) -> Path:
    """Flag works with extreme incoming citation edge counts."""
    config.ensure_dirs()
    works = pl.read_parquet(config.processed_dir / "works.parquet")
    citations = pl.read_parquet(config.processed_dir / "citations.parquet")
    panel_path = config.processed_dir / "citation_persistence_panel.parquet"
    panel = pl.read_parquet(panel_path) if panel_path.exists() else None

    edge_counts = (
        citations.group_by("target_doi")
        .len()
        .rename({"len": "incoming_citation_edges", "target_doi": "doi"})
    )
    mean_field_pct = None
    if panel is not None:
        mean_field_pct = (
            panel.group_by("work_id")
            .agg(pl.col("field_percentile").mean().alias("field_percentile"))
        )

    report_df = (
        works.join(edge_counts, on="doi", how="left")
        .with_columns(pl.col("incoming_citation_edges").fill_null(0))
        .sort("incoming_citation_edges", descending=True)
    )
    if mean_field_pct is not None:
        report_df = report_df.join(mean_field_pct, on="work_id", how="left")

    mean_edges = float(report_df["incoming_citation_edges"].mean() or 0)
    outliers = report_df.head(top_n).select(
        pl.col("doi"),
        pl.col("concept").alias("title"),
        pl.col("concept_group").alias("sector"),
        pl.col("year").alias("pub_year"),
        pl.col("citation_count").alias("openalex_cited_by_count"),
        pl.col("incoming_citation_edges").alias("citations"),
        pl.col("field_percentile"),
        (pl.col("incoming_citation_edges") / pl.lit(max(mean_edges, 1))).alias("edge_ratio_to_mean"),
    )

    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "summary": {
            "works_count": works.height,
            "mean_incoming_edges": round(mean_edges, 2),
            "max_incoming_edges": int(report_df["incoming_citation_edges"].max() or 0),
            "outlier_threshold_suggestion": round(mean_edges * 5, 0),
            "interpretation_warning": (
                "Do not scale until outliers are reviewed for remove, winsorize, or keep."
            ),
        },
        "top_outliers": outliers.to_dicts(),
        "recommendations": [
            "Compare incoming_citation_edges to openalex_cited_by_count for consistency.",
            "Check whether max_citations_per_doi cap was exceeded in raw ingestion.",
            "Decide handling before --limit-per-group 100.",
        ],
    }

    output = config.metadata_dir / "outlier_report.json"
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    logger.success("Outlier report written to {} (mean edges={})", output, round(mean_edges, 1))
    return output
