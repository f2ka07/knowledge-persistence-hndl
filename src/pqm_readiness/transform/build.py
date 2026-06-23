"""Stage 3: normalized dataset table construction."""

from __future__ import annotations

from pathlib import Path

import duckdb
import polars as pl
from loguru import logger

from pqm_readiness.config import PipelineConfig
from pqm_readiness.models import parse_year
from pqm_readiness.transform.persistence import write_longitudinal_tables


def _build_citations_df(openalex_path: Path, opencitations_path: Path) -> pl.DataFrame:
    if not opencitations_path.exists():
        return pl.DataFrame(
            schema={
                "source_doi": pl.Utf8,
                "target_doi": pl.Utf8,
                "citation_creation_date": pl.Utf8,
                "citation_lag_years": pl.Float64,
            }
        )

    oc_df = pl.read_parquet(opencitations_path).unique(
        subset=["citing_doi", "cited_doi", "citation_creation_date", "oci"],
        keep="first",
    )
    works_lookup = (
        pl.read_parquet(openalex_path, columns=["doi", "year"])
        .filter(pl.col("doi").is_not_null())
        .unique(subset=["doi"])
    )

    return (
        oc_df.select("citing_doi", "cited_doi", "citation_creation_date")
        .rename(
            {
                "citing_doi": "source_doi",
                "cited_doi": "target_doi",
            }
        )
        .filter(pl.col("source_doi").is_not_null() & pl.col("target_doi").is_not_null())
        .join(works_lookup, left_on="target_doi", right_on="doi", how="left")
        .with_columns(
            pl.col("citation_creation_date")
            .map_elements(parse_year, return_dtype=pl.Int64)
            .alias("citation_year")
        )
        .with_columns(
            (pl.col("citation_year") - pl.col("year").cast(pl.Int64))
            .cast(pl.Float64)
            .alias("citation_lag_years")
        )
        .select("source_doi", "target_doi", "citation_creation_date", "citation_lag_years")
        .filter(pl.col("citation_lag_years").is_null() | (pl.col("citation_lag_years") >= 0))
    )


def build_tables(
    config: PipelineConfig,
    openalex_path: Path,
    opencitations_path: Path,
) -> dict[str, Path]:
    """Build normalized and longitudinal dataset tables."""
    config.ensure_dirs()
    works_path = config.processed_dir / "works.parquet"
    citations_path = config.processed_dir / "citations.parquet"

    con = duckdb.connect(database=":memory:")
    con.execute(
        """
        CREATE OR REPLACE TABLE openalex AS
        SELECT * FROM read_parquet(?)
        """,
        [str(openalex_path)],
    )

    works_df = con.execute(
        """
        SELECT
            work_id,
            doi,
            CAST(year AS BIGINT) AS year,
            concept,
            concept_group,
            classification_source,
            classification_confidence,
            CAST(citation_count AS BIGINT) AS citation_count,
            CAST(institution_count AS BIGINT) AS institution_count
        FROM openalex
        WHERE work_id IS NOT NULL
        """
    ).pl().unique(subset=["work_id"], keep="first")
    con.close()

    works_df.write_parquet(works_path)
    citations_df = _build_citations_df(openalex_path, opencitations_path)
    citations_df.write_parquet(citations_path)

    by_year_path, persistence_path, panel_path = write_longitudinal_tables(
        works_df,
        citations_df,
        config.processed_dir,
        config.observation_year,
    )

    logger.success(
        "Built tables: works={}, citations={}, by_year={}, persistence={}, panel={}",
        works_df.height,
        citations_df.height,
        pl.read_parquet(by_year_path).height,
        pl.read_parquet(persistence_path).height,
        pl.read_parquet(panel_path).height,
    )

    return {
        "works": works_path,
        "citations": citations_path,
        "citations_by_year": by_year_path,
        "persistence": persistence_path,
        "citation_persistence_panel": panel_path,
    }
