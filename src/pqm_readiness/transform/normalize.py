"""Field- and year-normalized citation rates."""

from __future__ import annotations

import polars as pl

BASELINE_COHORTS = frozenset({"baseline_random", "baseline_matched", "baseline_year_only"})


def apply_citation_normalization(citations_by_year_df: pl.DataFrame) -> pl.DataFrame:
    """Add expected rates and percentile ranks for fair cross-field comparison."""
    if citations_by_year_df.height == 0:
        return citations_by_year_df.with_columns(
            pl.lit(None, dtype=pl.Float64).alias("expected_citations_at_age"),
            pl.lit(None, dtype=pl.Float64).alias("normalized_citation_rate"),
            pl.lit(None, dtype=pl.Float64).alias("field_percentile"),
            pl.lit(None, dtype=pl.Float64).alias("year_percentile"),
        )

    field_expected = (
        citations_by_year_df.filter(~pl.col("concept_group").is_in(list(BASELINE_COHORTS)))
        .group_by("concept_group", "age_years")
        .agg(pl.col("annual_citations").mean().alias("expected_citations_at_age"))
    )

    year_expected = citations_by_year_df.group_by("publication_year", "age_years").agg(
        pl.col("annual_citations").mean().alias("expected_citations_for_year")
    )

    enriched = (
        citations_by_year_df.join(field_expected, on=["concept_group", "age_years"], how="left")
        .join(year_expected, on=["publication_year", "age_years"], how="left")
        .with_columns(
            pl.when(pl.col("concept_group").is_in(list(BASELINE_COHORTS)))
            .then(
                pl.when(pl.col("expected_citations_for_year") > 0)
                .then(
                    pl.col("annual_citations").cast(pl.Float64)
                    / pl.col("expected_citations_for_year")
                )
                .otherwise(None)
            )
            .when(pl.col("expected_citations_at_age") > 0)
            .then(
                pl.col("annual_citations").cast(pl.Float64) / pl.col("expected_citations_at_age")
            )
            .otherwise(None)
            .alias("normalized_citation_rate"),
        )
        .with_columns(
            (
                pl.col("annual_citations").rank(method="average").over("concept_group", "age_years")
                / pl.max_horizontal(
                    pl.col("annual_citations").count().over("concept_group", "age_years"),
                    pl.lit(1),
                )
            ).alias("field_percentile"),
            (
                pl.col("annual_citations").rank(method="average").over("publication_year", "age_years")
                / pl.max_horizontal(
                    pl.col("annual_citations").count().over("publication_year", "age_years"),
                    pl.lit(1),
                )
            ).alias("year_percentile"),
        )
    )

    return enriched.select(
        *[col for col in citations_by_year_df.columns],
        "expected_citations_at_age",
        "normalized_citation_rate",
        "field_percentile",
        "year_percentile",
    )
