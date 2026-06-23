"""Build null-model comparison table for H0: K_HNDL = K_random."""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl
from loguru import logger

from pqm_readiness.transform.persistence import (
    build_citation_persistence_panel,
    build_citations_by_year,
    build_persistence_metrics,
)
from pqm_readiness.transform.normalize import apply_citation_normalization


def _build_baseline_sample(
    baseline_openalex_path: Path,
    baseline_opencitations_path: Path,
    processed_dir: Path,
    observation_year: int,
    *,
    cohort_name: str,
    output_filename: str,
) -> Path:
    """Build a baseline cohort with the same longitudinal schema as the HNDL sample."""
    output_path = processed_dir / output_filename
    if not baseline_openalex_path.exists():
        logger.warning("No baseline raw works; skipping {}", output_filename)
        return output_path

    works_df = pl.read_parquet(baseline_openalex_path).select(
        pl.col("work_id"),
        pl.col("doi"),
        pl.col("year").cast(pl.Int64),
        pl.col("concept"),
        pl.col("concept_group"),
        pl.col("classification_source"),
        pl.col("classification_confidence"),
        pl.col("citation_count").cast(pl.Int64),
        pl.col("institution_count").cast(pl.Int64),
    ).unique(subset=["work_id"], keep="first")

    if baseline_opencitations_path.exists():
        from pqm_readiness.transform.build import _build_citations_df

        citations_df = _build_citations_df(baseline_openalex_path, baseline_opencitations_path)
    else:
        citations_df = pl.DataFrame(
            schema={
                "source_doi": pl.Utf8,
                "target_doi": pl.Utf8,
                "citation_creation_date": pl.Utf8,
                "citation_lag_years": pl.Float64,
            }
        )

    citations_by_year = apply_citation_normalization(
        build_citations_by_year(works_df, citations_df, observation_year)
    )
    persistence = build_persistence_metrics(works_df, citations_by_year, observation_year)
    panel = build_citation_persistence_panel(citations_by_year, persistence)

    summary = (
        persistence.with_columns(pl.lit(cohort_name).alias("sample_cohort"))
        .join(
            panel.group_by("work_id").agg(
                pl.col("normalized_citation_rate").mean().alias("mean_normalized_citation_rate"),
                pl.col("field_percentile").mean().alias("mean_field_percentile"),
                pl.col("year_percentile").mean().alias("mean_year_percentile"),
            ),
            on="work_id",
            how="left",
        )
    )

    summary.write_parquet(output_path)
    logger.success("Built {}: {} records", output_filename, summary.height)
    return output_path


def build_baseline_random_sample(
    baseline_openalex_path: Path,
    baseline_opencitations_path: Path,
    processed_dir: Path,
    observation_year: int,
) -> Path:
    return _build_baseline_sample(
        baseline_openalex_path,
        baseline_opencitations_path,
        processed_dir,
        observation_year,
        cohort_name="baseline_random",
        output_filename="baseline_random_sample.parquet",
    )


def build_baseline_matched_sample(
    baseline_openalex_path: Path,
    baseline_opencitations_path: Path,
    processed_dir: Path,
    observation_year: int,
) -> Path:
    return _build_baseline_sample(
        baseline_openalex_path,
        baseline_opencitations_path,
        processed_dir,
        observation_year,
        cohort_name="baseline_matched",
        output_filename="baseline_matched.parquet",
    )


def build_baseline_year_only_sample(
    baseline_openalex_path: Path,
    baseline_opencitations_path: Path,
    processed_dir: Path,
    observation_year: int,
) -> Path:
    return _build_baseline_sample(
        baseline_openalex_path,
        baseline_opencitations_path,
        processed_dir,
        observation_year,
        cohort_name="baseline_year_only",
        output_filename="baseline_year_only.parquet",
    )


def build_null_model_comparison(
    hndl_persistence_path: Path,
    baseline_sample_path: Path,
    processed_dir: Path,
    panel_path: Path | None = None,
    *,
    baseline_label: str = "baseline_random",
) -> Path:
    """Summarize HNDL vs baseline half-life and normalized rate differences."""
    output_path = processed_dir / "null_model_comparison.json"
    if not hndl_persistence_path.exists() or not baseline_sample_path.exists():
        return output_path

    hndl = pl.read_parquet(hndl_persistence_path).with_columns(pl.lit("hndl").alias("cohort"))
    baseline = pl.read_parquet(baseline_sample_path).with_columns(
        pl.lit(baseline_label).alias("cohort")
    )
    panel_rates: pl.DataFrame | None = None
    if panel_path and panel_path.exists():
        panel_rates = (
            pl.read_parquet(panel_path)
            .group_by("work_id")
            .agg(pl.col("normalized_citation_rate").mean().alias("mean_normalized_citation_rate"))
        )
        hndl = hndl.join(panel_rates, on="work_id", how="left")

    def _cohort_stats(df: pl.DataFrame, name: str) -> dict[str, object]:
        stats: dict[str, object] = {
            "cohort": name,
            "n": df.height,
            "median_half_life": df.select(pl.col("estimated_half_life_years").median()).item(),
            "median_peak_age": df.select(pl.col("peak_age_years").median()).item(),
            "censored_share": float(df.select(pl.col("censoring_flag").mean()).item() or 0.0),
        }
        if "mean_normalized_citation_rate" in df.columns:
            stats["mean_normalized_rate"] = df.select(
                pl.col("mean_normalized_citation_rate").mean()
            ).item()
        return stats

    existing: dict[str, object] = {}
    if output_path.exists():
        existing = json.loads(output_path.read_text(encoding="utf-8"))

    report = {
        "hypothesis": existing.get("hypothesis", "H0: K_HNDL = K_random"),
        "hndl": existing.get("hndl") or _cohort_stats(hndl, "hndl"),
        baseline_label: _cohort_stats(baseline, baseline_label),
        "note": (
            "Formal test deferred to modelling stage. "
            "Do NOT interpret median differences: censoring rates differ across cohorts. "
            "Run fit-survival-preview before any narrative."
        ),
    }
    for key, value in existing.items():
        if key not in report and key not in {"hypothesis", "hndl", "note"}:
            report[key] = value

    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    logger.success("Null model comparison written to {}", output_path)
    return output_path
