"""Covariate models for time-to-influence-decay (HNDL cohort)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl
from loguru import logger

from pqm_readiness.config import PipelineConfig
from pqm_readiness.matching import match_stratum_from_row
from pqm_readiness.transform.persistence import DECAY_CONSECUTIVE_YEARS, DECAY_THRESHOLD_RATIO


def _hndl_regression_frame(config: PipelineConfig) -> pl.DataFrame:
    persistence_path = config.processed_dir / "persistence.parquet"
    openalex_path = config.raw_dir / "openalex_works.parquet"
    if not persistence_path.exists():
        raise FileNotFoundError(f"Missing {persistence_path}")
    if not openalex_path.exists():
        raise FileNotFoundError(f"Missing {openalex_path}")

    persistence = pl.read_parquet(persistence_path)
    openalex = pl.read_parquet(openalex_path).select(
        "work_id",
        "citation_count",
        "concepts_json",
        "concept_group",
        pl.col("year").cast(pl.Int64).alias("publication_year"),
    )

    merged = persistence.join(openalex, on="work_id", how="inner", suffix="_oa")
    if "publication_year" not in merged.columns:
        merged = merged.with_columns(pl.col("publication_year_oa").alias("publication_year"))
    elif "publication_year_oa" in merged.columns:
        merged = merged.with_columns(
            pl.coalesce("publication_year", "publication_year_oa").alias("publication_year")
        )

    depth_rows: list[dict[str, Any]] = []
    for row in openalex.iter_rows(named=True):
        stratum = match_stratum_from_row({**row, "year": row["publication_year"]})
        depth_rows.append({"work_id": row["work_id"], "concept_depth": stratum["concept_depth"]})
    depth_df = pl.DataFrame(depth_rows)

    field_col = "concept_group" if "concept_group" in merged.columns else "concept_group_oa"
    frame = (
        merged.join(depth_df, on="work_id", how="left")
        .with_columns(
            pl.col("citation_count").cast(pl.Float64),
            pl.col("publication_year").cast(pl.Float64),
            pl.col("concept_depth").cast(pl.Float64),
            pl.col(field_col).alias("field"),
        )
        .filter(pl.col("time_to_decay_years").is_not_null() & (pl.col("time_to_decay_years") > 0))
        .select(
            "work_id",
            "publication_year",
            "citation_count",
            "field",
            "concept_depth",
            "time_to_decay_years",
            "influence_decay_event",
            "influence_decay_censored",
        )
    )
    return frame


def _fit_weibull_aft(frame: pl.DataFrame) -> dict[str, Any]:
    from lifelines import WeibullAFTFitter

    model_df = frame.drop_nulls(subset=["publication_year", "citation_count", "concept_depth", "field"])
    if model_df.height < 10:
        return {"status": "insufficient_data", "records": int(model_df.height)}

    pandas_df = model_df.to_pandas()
    aft = WeibullAFTFitter()
    formula = "publication_year + citation_count + concept_depth + C(field)"
    aft.fit(
        pandas_df,
        duration_col="time_to_decay_years",
        event_col="influence_decay_event",
        formula=formula,
    )

    coef_rows: list[dict[str, Any]] = []
    for index, row in aft.summary.iterrows():
        param, covariate = index
        coef_rows.append(
            {
                "parameter": param,
                "covariate": covariate,
                "coef": float(row["coef"]),
                "exp_coef": float(row["exp(coef)"]) if param == "lambda_" else None,
                "p_value": float(row["p"]),
            }
        )

    return {
        "status": "ok",
        "formula": f"time_to_decay_years ~ {formula}",
        "records": int(pandas_df.shape[0]),
        "events": int(pandas_df["influence_decay_event"].sum()),
        "coefficients": coef_rows,
        "concordance_index": float(aft.concordance_index_),
    }


def _fit_quantile_regression(frame: pl.DataFrame, *, quantile: float = 0.5) -> dict[str, Any]:
    try:
        import pandas as pd
        import statsmodels.api as sm
        from statsmodels.regression.quantile_regression import QuantReg
    except ImportError as exc:
        return {"status": "missing_dependency", "error": str(exc), "install": "pip install statsmodels"}

    model_df = frame.filter(pl.col("influence_decay_event")).drop_nulls(
        subset=["publication_year", "citation_count", "concept_depth", "field"]
    )
    if model_df.height < 10:
        return {
            "status": "insufficient_events",
            "records": int(model_df.height),
            "note": "Quantile regression fit on observed decay events only.",
        }

    pandas_df = pd.get_dummies(model_df.to_pandas(), columns=["field"], drop_first=True)
    y = pandas_df["time_to_decay_years"].astype(float)
    drop_cols = {"work_id", "time_to_decay_years", "influence_decay_event", "influence_decay_censored"}
    x = pandas_df.drop(columns=[c for c in drop_cols if c in pandas_df.columns]).astype(float)
    x = sm.add_constant(x, has_constant="add")
    model = QuantReg(y, x)
    result = model.fit(q=quantile)

    coef_rows = [
        {"covariate": name, "coef": float(result.params[name]), "p_value": float(result.pvalues[name])}
        for name in result.params.index
    ]
    return {
        "status": "ok",
        "quantile": quantile,
        "formula": "time_to_decay_years ~ publication_year + citation_count + concept_depth + field",
        "records": int(pandas_df.shape[0]),
        "note": "Fit on observed decay events only; does not model censoring.",
        "coefficients": coef_rows,
    }


def fit_decay_regression(config: PipelineConfig) -> Path:
    """Fit AFT Weibull and quantile regression for HNDL decay outcomes."""
    config.ensure_dirs()
    output = config.metadata_dir / "decay_regression.json"

    frame = _hndl_regression_frame(config)
    weibull = _fit_weibull_aft(frame)
    quantile = _fit_quantile_regression(frame)

    citation_dominates = None
    if weibull.get("status") == "ok":
        cite = next(
            (c for c in weibull["coefficients"] if c["covariate"] == "citation_count" and c["parameter"] == "lambda_"),
            None,
        )
        field_terms = [
            c
            for c in weibull["coefficients"]
            if c["parameter"] == "lambda_" and "field" in str(c["covariate"])
        ]
        if cite and field_terms:
            cite_sig = cite["p_value"] < 0.05
            any_field_sig = any(t["p_value"] < 0.05 for t in field_terms)
            citation_dominates = cite_sig and not any_field_sig

    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "cohort": "hndl",
        "outcome": "time_to_decay_years",
        "event_definition": (
            f"annual_citation_rate < {DECAY_THRESHOLD_RATIO} * peak_rate "
            f"for {DECAY_CONSECUTIVE_YEARS} consecutive years"
        ),
        "models": {
            "weibull_aft": weibull,
            "quantile_regression_median": quantile,
        },
        "interpretation": {
            "research_question": "Which variables explain influence decay?",
            "citation_count_dominates_over_field": citation_dominates,
            "paper_framing": (
                "Contribution: how should long-horizon information persistence be operationalised?"
            ),
        },
    }
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    logger.success("Decay regression report -> {}", output)
    return output
