"""Longitudinal citation persistence transforms."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import polars as pl
from loguru import logger

from pqm_readiness.models import parse_year
from pqm_readiness.transform.normalize import apply_citation_normalization

DECAY_THRESHOLD_RATIO = 0.1
DECAY_CONSECUTIVE_YEARS = 3


def influence_decay_metrics(
    ages: list[int],
    annual: list[int],
    publication_year: int,
    *,
    threshold_ratio: float = DECAY_THRESHOLD_RATIO,
    consecutive_years: int = DECAY_CONSECUTIVE_YEARS,
) -> dict[str, Any]:
    """Detect influence decay: rate < threshold * peak for N consecutive years."""
    if not ages or not annual:
        return {
            "decay_event_year": None,
            "decay_threshold": 0.0,
            "time_to_decay_years": None,
            "influence_decay_event": False,
            "influence_decay_censored": True,
        }

    peak_rate = max(annual)
    decay_threshold = threshold_ratio * peak_rate
    age_to_rate = dict(zip(ages, annual, strict=True))
    max_age = max(ages)

    streak = 0
    decay_event_year: int | None = None
    time_to_decay: float | None = None

    for age in range(0, max_age + 1):
        rate = age_to_rate.get(age, 0)
        if rate < decay_threshold:
            streak += 1
            if streak >= consecutive_years:
                time_to_decay = float(age)
                decay_event_year = publication_year + age
                break
        else:
            streak = 0

    if decay_event_year is None:
        return {
            "decay_event_year": None,
            "decay_threshold": decay_threshold,
            "time_to_decay_years": float(max_age),
            "influence_decay_event": False,
            "influence_decay_censored": True,
        }

    return {
        "decay_event_year": decay_event_year,
        "decay_threshold": decay_threshold,
        "time_to_decay_years": time_to_decay,
        "influence_decay_event": True,
        "influence_decay_censored": False,
    }


def _half_life_age(ages: list[int], cumulative: list[int], total: int) -> float | None:
    if total <= 0 or not ages:
        return None
    target = total / 2
    for age, cum in zip(ages, cumulative, strict=True):
        if cum >= target:
            return float(age)
    return None


def _post_peak_decay_rate(ages: list[int], annual: list[int], peak_age: int) -> float | None:
    post = [(age, count) for age, count in zip(ages, annual, strict=True) if age > peak_age]
    if len(post) < 2:
        return None
    x = [point[0] - peak_age for point in post]
    y = [point[1] for point in post]
    n = len(x)
    x_mean = sum(x) / n
    y_mean = sum(y) / n
    numerator = sum((xi - x_mean) * (yi - y_mean) for xi, yi in zip(x, y, strict=True))
    denominator = sum((xi - x_mean) ** 2 for xi in x)
    if denominator == 0:
        return None
    return numerator / denominator


def build_citations_by_year(
    works_df: pl.DataFrame,
    citations_df: pl.DataFrame,
    observation_year: int,
) -> pl.DataFrame:
    if citations_df.height == 0:
        return pl.DataFrame(
            schema={
                "work_id": pl.Utf8,
                "doi": pl.Utf8,
                "concept_group": pl.Utf8,
                "publication_year": pl.Int64,
                "citation_year": pl.Int64,
                "age_years": pl.Int64,
                "annual_citations": pl.Int64,
                "cumulative_citations": pl.Int64,
                "normalized_annual_citations": pl.Float64,
                "normalized_cumulative_citations": pl.Float64,
            }
        )

    joined = (
        citations_df.join(
            works_df.select("work_id", "doi", "concept_group", "year"),
            left_on="target_doi",
            right_on="doi",
            how="inner",
        )
        .with_columns(
            pl.col("citation_creation_date")
            .map_elements(parse_year, return_dtype=pl.Int64)
            .alias("citation_year")
        )
        .filter(pl.col("citation_year").is_not_null())
        .with_columns(
            (pl.col("citation_year") - pl.col("year").cast(pl.Int64))
            .cast(pl.Int64)
            .alias("age_years")
        )
        .filter(pl.col("age_years") >= 0)
        .with_columns(pl.col("target_doi").alias("doi"))
    )

    by_year = (
        joined.group_by("work_id", "doi", "concept_group", "year", "citation_year", "age_years")
        .agg(pl.len().alias("annual_citations"))
        .rename({"year": "publication_year"})
        .sort("work_id", "citation_year")
    )

    return (
        by_year.with_columns(
            pl.col("annual_citations")
            .cum_sum()
            .over("work_id")
            .alias("cumulative_citations")
        )
        .with_columns(
            (
                pl.col("annual_citations").cast(pl.Float64)
                / pl.col("annual_citations").max().over("work_id")
            ).alias("normalized_annual_citations"),
            (
                pl.col("cumulative_citations").cast(pl.Float64)
                / pl.col("cumulative_citations").max().over("work_id")
            ).alias("normalized_cumulative_citations"),
        )
        .with_columns(
            pl.col("publication_year").cast(pl.Int64),
            pl.col("citation_year").cast(pl.Int64),
            pl.col("age_years").cast(pl.Int64),
            pl.col("annual_citations").cast(pl.Int64),
            pl.col("cumulative_citations").cast(pl.Int64),
        )
    )


def build_persistence_metrics(
    works_df: pl.DataFrame,
    citations_by_year_df: pl.DataFrame,
    observation_year: int,
) -> pl.DataFrame:
    rows: list[dict[str, object]] = []
    for work in works_df.iter_rows(named=True):
        series = citations_by_year_df.filter(pl.col("work_id") == work["work_id"]).sort("age_years")
        if series.height == 0:
            rows.append(
                {
                    "work_id": work["work_id"],
                    "doi": work["doi"],
                    "concept_group": work.get("concept_group"),
                    "publication_year": work["year"],
                    "last_observed_year": None,
                    "observed_window_years": None,
                    "first_citation_year": None,
                    "last_citation_year": None,
                    "citation_lifespan_years": None,
                    "peak_citation_year": None,
                    "peak_age_years": None,
                    "estimated_half_life_years": None,
                    "half_life_censored": True,
                    "decay_start_year": None,
                    "post_peak_decay_rate": None,
                    "long_tail_indicator": False,
                    "censoring_flag": True,
                    "decay_event_year": None,
                    "decay_threshold": 0.0,
                    "time_to_decay_years": None,
                    "influence_decay_event": False,
                    "influence_decay_censored": True,
                }
            )
            continue

        ages = series.get_column("age_years").to_list()
        citation_years = series.get_column("citation_year").to_list()
        annual = series.get_column("annual_citations").to_list()
        cumulative = series.get_column("cumulative_citations").to_list()
        total = cumulative[-1]
        peak_idx = max(range(len(annual)), key=lambda i: annual[i])
        peak_age = ages[peak_idx]
        peak_year = citation_years[peak_idx]
        last_year = citation_years[-1]
        censored = last_year >= observation_year - 1
        half_life = _half_life_age(ages, cumulative, total)
        half_life_censored = censored or half_life is None
        estimated_half_life = None if (censored and half_life is None) else half_life

        decay_start_year = None
        for idx in range(peak_idx + 1, len(annual)):
            if annual[idx] < annual[peak_idx]:
                decay_start_year = citation_years[idx]
                break

        tail_threshold = 5
        long_tail = any(
            age >= peak_age + tail_threshold and count > 0 for age, count in zip(ages, annual, strict=True)
        )

        decay = influence_decay_metrics(ages, annual, int(work["year"]))

        rows.append(
            {
                "work_id": work["work_id"],
                "doi": work["doi"],
                "concept_group": work.get("concept_group"),
                "publication_year": work["year"],
                "last_observed_year": last_year,
                "observed_window_years": float(last_year - work["year"]),
                "first_citation_year": citation_years[0],
                "last_citation_year": last_year,
                "citation_lifespan_years": float(last_year - citation_years[0]),
                "peak_citation_year": peak_year,
                "peak_age_years": float(peak_age),
                "estimated_half_life_years": estimated_half_life,
                "half_life_censored": half_life_censored,
                "decay_start_year": decay_start_year,
                "post_peak_decay_rate": _post_peak_decay_rate(ages, annual, peak_age),
                "long_tail_indicator": long_tail,
                "censoring_flag": censored,
                **decay,
            }
        )

    return pl.DataFrame(rows)


def build_citation_persistence_panel(
    citations_by_year_df: pl.DataFrame,
    persistence_df: pl.DataFrame,
) -> pl.DataFrame:
    """Panel of citation influence over age; K(t) is derived downstream."""
    if citations_by_year_df.height == 0:
        return pl.DataFrame(
            schema={
                "work_id": pl.Utf8,
                "concept_group": pl.Utf8,
                "age_years": pl.Int64,
                "observed_citation_rate": pl.Float64,
                "cumulative_citation_share": pl.Float64,
                "normalized_citation_rate": pl.Float64,
                "field_percentile": pl.Float64,
                "year_percentile": pl.Float64,
                "citation_share_remaining": pl.Float64,
                "censoring_flag": pl.Boolean,
            }
        )

    panel = citations_by_year_df.select(
        "work_id",
        "concept_group",
        "age_years",
        pl.col("normalized_annual_citations").alias("observed_citation_rate"),
        pl.col("normalized_cumulative_citations").alias("cumulative_citation_share"),
        pl.col("normalized_citation_rate").alias("normalized_citation_rate"),
        pl.col("field_percentile").alias("field_percentile"),
        pl.col("year_percentile").alias("year_percentile"),
        (1.0 - pl.col("normalized_cumulative_citations")).alias("citation_share_remaining"),
    )

    censoring = persistence_df.select("work_id", "censoring_flag")
    return panel.join(censoring, on="work_id", how="left").with_columns(
        pl.col("age_years").cast(pl.Int64),
        pl.col("censoring_flag").fill_null(True),
    )


def write_longitudinal_tables(
    works_df: pl.DataFrame,
    citations_df: pl.DataFrame,
    processed_dir: Path,
    observation_year: int,
) -> tuple[Path, Path, Path]:
    citations_by_year_path = processed_dir / "citations_by_year.parquet"
    persistence_path = processed_dir / "persistence.parquet"
    panel_path = processed_dir / "citation_persistence_panel.parquet"

    citations_by_year_df = apply_citation_normalization(
        build_citations_by_year(works_df, citations_df, observation_year)
    )
    persistence_df = build_persistence_metrics(works_df, citations_by_year_df, observation_year)
    panel_df = build_citation_persistence_panel(citations_by_year_df, persistence_df)

    citations_by_year_df.write_parquet(citations_by_year_path)
    persistence_df.write_parquet(persistence_path)
    panel_df.write_parquet(panel_path)

    logger.success(
        "Built longitudinal tables: by_year={}, persistence={}, panel={}",
        citations_by_year_df.height,
        persistence_df.height,
        panel_df.height,
    )
    return citations_by_year_path, persistence_path, panel_path
