"""Recompute influence-decay outcomes at arbitrary threshold parameters."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import polars as pl

from pqm_readiness.config import PipelineConfig
from pqm_readiness.transform.build import _build_citations_df
from pqm_readiness.transform.persistence import build_citations_by_year, influence_decay_metrics

COHORT_SOURCES: dict[str, tuple[str, str]] = {
    "hndl": ("openalex_works.parquet", "opencitations_citations.parquet"),
    "baseline_random": ("baseline_works.parquet", "baseline_opencitations_citations.parquet"),
    "baseline_year_only": (
        "baseline_year_only_works.parquet",
        "baseline_year_only_opencitations_citations.parquet",
    ),
    "baseline_matched": (
        "baseline_matched_works.parquet",
        "baseline_matched_opencitations_citations.parquet",
    ),
}


def _works_decay_input(works_path: Path) -> pl.DataFrame:
    works = pl.read_parquet(works_path)
    year_col = "publication_year" if "publication_year" in works.columns else "year"
    select = [
        pl.col("work_id"),
        pl.col("doi"),
        pl.col(year_col).cast(pl.Int64).alias("publication_year"),
    ]
    if "concept_group" in works.columns:
        select.append(pl.col("concept_group"))
    frame = works.select(select).unique(subset=["work_id"], keep="first")
    return frame.with_columns(pl.col("publication_year").alias("year"))


def load_citations_by_year(
    config: PipelineConfig,
    cohort: str,
    *,
    use_processed_hndl: bool = True,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Return (works, citations_by_year) for a cohort."""
    works_name, oc_name = COHORT_SOURCES[cohort]
    works_path = config.raw_dir / works_name
    if not works_path.exists():
        raise FileNotFoundError(f"Missing raw works for {cohort}: {works_path}")

    works_df = _works_decay_input(works_path)
    if cohort == "hndl" and use_processed_hndl:
        cby_path = config.processed_dir / "citations_by_year.parquet"
        if cby_path.exists():
            return works_df, pl.read_parquet(cby_path)

    oc_path = config.raw_dir / oc_name
    citations_df = _build_citations_df(works_path, oc_path)
    cby_df = build_citations_by_year(works_df, citations_df, config.observation_year)
    return works_df, cby_df


def decay_frame_at_params(
    works_df: pl.DataFrame,
    citations_by_year_df: pl.DataFrame,
    *,
    threshold_ratio: float,
    consecutive_years: int,
) -> pl.DataFrame:
    """Build minimal decay outcome columns for one threshold configuration."""
    rows: list[dict[str, Any]] = []
    for work in works_df.iter_rows(named=True):
        series = citations_by_year_df.filter(pl.col("work_id") == work["work_id"]).sort("age_years")
        pub_year = int(work["publication_year"])
        if series.height == 0:
            metrics = influence_decay_metrics(
                [],
                [],
                pub_year,
                threshold_ratio=threshold_ratio,
                consecutive_years=consecutive_years,
            )
        else:
            ages = series.get_column("age_years").to_list()
            annual = series.get_column("annual_citations").to_list()
            metrics = influence_decay_metrics(
                ages,
                annual,
                pub_year,
                threshold_ratio=threshold_ratio,
                consecutive_years=consecutive_years,
            )
        row: dict[str, Any] = {
            "work_id": work["work_id"],
            "publication_year": pub_year,
            "time_to_decay_years": metrics["time_to_decay_years"],
            "influence_decay_event": metrics["influence_decay_event"],
            "influence_decay_censored": metrics["influence_decay_censored"],
        }
        if "concept_group" in work:
            row["concept_group"] = work["concept_group"]
        rows.append(row)

    return pl.DataFrame(rows)


def survival_ready_frame(frame: pl.DataFrame) -> pl.DataFrame:
    """Filter to positive durations and attach survival column aliases."""
    return (
        frame.filter(
            pl.col("time_to_decay_years").is_not_null() & (pl.col("time_to_decay_years") > 0)
        )
        .with_columns(
            pl.col("time_to_decay_years").alias("duration"),
            pl.col("influence_decay_event").cast(pl.Int64).alias("event"),
            pl.col("influence_decay_censored").alias("censoring_flag"),
        )
        .select("work_id", "duration", "event", "censoring_flag")
    )
