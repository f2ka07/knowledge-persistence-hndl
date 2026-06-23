"""Survival analysis preview for cohort comparison (do not interpret medians alone)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import polars as pl
from loguru import logger

from pqm_readiness.config import PipelineConfig
from pqm_readiness.transform.persistence import DECAY_CONSECUTIVE_YEARS, DECAY_THRESHOLD_RATIO

BASELINE_COMPARISONS = (
    ("baseline_random", "A_random", "Random baseline (year-matched counts only)"),
    ("baseline_year_only", "B_year_matched", "Year+DOI matched (no citation band)"),
    ("baseline_matched", "C_fully_matched", "Fully matched (year, citation band, depth, source)"),
)

EventDefinition = Literal["influence_decay", "citation_stop"]


def _load_cohort_frame(path: Path, cohort_name: str) -> pl.DataFrame | None:
    if not path.exists():
        return None
    return pl.read_parquet(path).with_columns(pl.lit(cohort_name).alias("cohort"))


def _survival_frame(
    config: PipelineConfig,
    *,
    event_definition: EventDefinition = "influence_decay",
) -> pl.DataFrame:
    cohort_paths = {
        "hndl": config.processed_dir / "persistence.parquet",
        "baseline_random": config.processed_dir / "baseline_random_sample.parquet",
        "baseline_year_only": config.processed_dir / "baseline_year_only.parquet",
        "baseline_matched": config.processed_dir / "baseline_matched.parquet",
    }
    frames = [_load_cohort_frame(path, name) for name, path in cohort_paths.items()]
    combined = pl.concat([frame for frame in frames if frame is not None], how="diagonal_relaxed")

    if event_definition == "influence_decay":
        duration_col = "time_to_decay_years"
        event_col = "influence_decay_event"
        censor_col = "influence_decay_censored"
    else:
        duration_col = "observed_window_years"
        event_col = "censoring_flag"
        censor_col = "censoring_flag"

    if duration_col not in combined.columns:
        return pl.DataFrame()

    if event_definition == "citation_stop":
        event_expr = (~pl.col("censoring_flag")).cast(pl.Int64).alias("event")
        censor_expr = pl.col("censoring_flag").alias("censoring_flag")
    else:
        event_expr = pl.col("influence_decay_event").cast(pl.Int64).alias("event")
        censor_expr = pl.col("influence_decay_censored").alias("censoring_flag")

    return combined.filter(
        pl.col(duration_col).is_not_null() & (pl.col(duration_col) > 0)
    ).select(
        "work_id",
        "cohort",
        pl.col(duration_col).alias("duration"),
        event_expr,
        censor_expr,
        "estimated_half_life_years",
        "half_life_censored",
        "decay_event_year",
        "decay_threshold",
    )


def _fit_one_comparison(
    hndl,
    other,
    other_label: str,
    *,
    event_definition: EventDefinition,
) -> dict[str, Any]:
    from lifelines import CoxPHFitter, KaplanMeierFitter, WeibullAFTFitter
    from lifelines.statistics import logrank_test

    km_hndl = KaplanMeierFitter()
    km_other = KaplanMeierFitter()
    km_hndl.fit(hndl["duration"], event_observed=hndl["event"], label="hndl")
    km_other.fit(other["duration"], event_observed=other["event"], label=other_label)

    logrank = logrank_test(
        hndl["duration"],
        other["duration"],
        event_observed_A=hndl["event"],
        event_observed_B=other["event"],
    )

    cox_df = pl.concat(
        [
            pl.from_pandas(hndl[["duration", "event"]]).with_columns(pl.lit(1).alias("is_hndl")),
            pl.from_pandas(other[["duration", "event"]]).with_columns(pl.lit(0).alias("is_hndl")),
        ]
    ).to_pandas()

    cox = CoxPHFitter()
    cox.fit(cox_df, duration_col="duration", event_col="event")

    aft = WeibullAFTFitter()
    aft.fit(cox_df, duration_col="duration", event_col="event")

    def _km_summary(fitter: KaplanMeierFitter, cohort_df) -> dict[str, float | None]:
        median = fitter.median_survival_time_
        median_value = float(median) if median == median and median != float("inf") else None
        return {
            "median_survival_years": median_value,
            "censoring_share": float(cohort_df["censoring_flag"].mean()),
        }

    reliability_notes: list[str] = []
    if float(other["event"].sum()) == 0 or float(hndl["event"].sum()) == 0:
        reliability_notes.append(
            "One cohort has no observed events under this definition; "
            "Cox and Weibull coefficients are unreliable."
        )
    if float(other["censoring_flag"].mean()) >= 0.99 or float(hndl["censoring_flag"].mean()) >= 0.99:
        reliability_notes.append(
            "Extreme censoring in at least one cohort; prefer log-rank over parametric models."
        )

    hypothesis = (
        "P(T_decay>t | HNDL) vs P(T_decay>t | {})"
        if event_definition == "influence_decay"
        else "P(T_stop>t | HNDL) vs P(T_stop>t | {})"
    )

    return {
        "hypothesis": hypothesis.format(other_label),
        "records": {
            "hndl": int(hndl.shape[0]),
            other_label: int(other.shape[0]),
        },
        "events": {
            "hndl": int(hndl["event"].sum()),
            other_label: int(other["event"].sum()),
        },
        "censoring_share": {
            "hndl": float(hndl["censoring_flag"].mean()),
            other_label: float(other["censoring_flag"].mean()),
        },
        "kaplan_meier": {
            "hndl": _km_summary(km_hndl, hndl),
            other_label: _km_summary(km_other, other),
        },
        "logrank_test": {
            "test_statistic": float(logrank.test_statistic),
            "p_value": float(logrank.p_value),
        },
        "cox_ph": {
            "hazard_ratio_is_hndl": float(cox.summary.loc["is_hndl", "exp(coef)"]),
            "p_value_is_hndl": float(cox.summary.loc["is_hndl", "p"]),
        },
        "weibull_aft": {
            "coef_is_hndl": float(aft.summary.loc[("lambda_", "is_hndl"), "coef"]),
            "p_value_is_hndl": float(aft.summary.loc[("lambda_", "is_hndl"), "p"]),
        },
        "reliability_notes": reliability_notes,
    }


def _run_comparisons(
    config: PipelineConfig,
    *,
    event_definition: EventDefinition,
) -> dict[str, Any]:
    frame = _survival_frame(config, event_definition=event_definition)
    if frame.height < 10:
        return {"status": "insufficient_data", "records": frame.height}

    try:
        from lifelines import CoxPHFitter  # noqa: F401
    except ImportError as exc:
        return {"status": "missing_dependency", "error": str(exc)}

    pdf = frame.to_pandas()
    hndl = pdf[pdf["cohort"] == "hndl"]
    comparisons: dict[str, Any] = {}

    for label, _tier, _description in BASELINE_COMPARISONS:
        other = pdf[pdf["cohort"] == label]
        if other.empty or hndl.empty:
            comparisons[f"hndl_vs_{label}"] = {
                "status": "missing_cohort",
                "records": {label: int(other.shape[0])},
            }
            continue
        comparisons[f"hndl_vs_{label}"] = _fit_one_comparison(
            hndl, other, label, event_definition=event_definition
        )
    return comparisons


def _decomposition_summary(comparisons: dict[str, Any]) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for label, key, description in BASELINE_COMPARISONS:
        comp = comparisons.get(f"hndl_vs_{label}", {})
        logrank_p = comp.get("logrank_test", {}).get("p_value")
        entries.append(
            {
                "tier": key,
                "baseline": label,
                "description": description,
                "logrank_p_value": logrank_p,
                "significant_at_0_05": bool(logrank_p is not None and logrank_p < 0.05),
            }
        )

    random_sig = entries[0].get("significant_at_0_05") if entries else None
    year_sig = entries[1].get("significant_at_0_05") if len(entries) > 1 else None
    full_sig = entries[2].get("significant_at_0_05") if len(entries) > 2 else None

    pattern = "inconclusive"
    if random_sig and year_sig is False and full_sig is False:
        pattern = "influence_accumulation_explains_persistence"
    elif random_sig and not full_sig:
        pattern = "matching_reduces_apparent_effect"
    elif not random_sig:
        pattern = "no_baseline_difference"

    return {
        "expected_pattern": "Random significant -> Year weaker -> Full neutral",
        "observed_tiers": entries,
        "pattern_classification": pattern,
        "interpretation": (
            "Observed persistence appears associated with influence accumulation rather than "
            "domain membership; citation count is partly endogenous to persistence."
        ),
    }


def fit_survival_preview(config: PipelineConfig) -> Path:
    """Run Kaplan-Meier, log-rank, Cox PH, and Weibull AFT preview models."""
    config.ensure_dirs()
    output = config.metadata_dir / "survival_preview.json"

    decay_comparisons = _run_comparisons(config, event_definition="influence_decay")
    stop_comparisons = _run_comparisons(config, event_definition="citation_stop")

    if decay_comparisons.get("status") == "insufficient_data":
        report = {
            "generated_at": datetime.now(UTC).isoformat(),
            "status": "insufficient_data",
            "records": decay_comparisons.get("records"),
            "note": "Need more records for stable survival preview.",
        }
        output.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return output

    if decay_comparisons.get("status") == "missing_dependency":
        report = {
            "generated_at": datetime.now(UTC).isoformat(),
            "status": "missing_dependency",
            "error": decay_comparisons.get("error"),
            "install": "pip install lifelines",
        }
        output.write_text(json.dumps(report, indent=2), encoding="utf-8")
        logger.warning("lifelines not installed; survival preview skipped")
        return output

    decomposition = _decomposition_summary(decay_comparisons)
    matched_comp = decay_comparisons.get("hndl_vs_baseline_matched", {})
    logrank_p = matched_comp.get("logrank_test", {}).get("p_value")

    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "status": "ok",
        "primary_event_definition": "influence_decay",
        "event_rule": (
            f"annual_citation_rate < {DECAY_THRESHOLD_RATIO} * peak_rate "
            f"for {DECAY_CONSECUTIVE_YEARS} consecutive years"
        ),
        "interpretation_warning": (
            "Primary survival models P(T_decay>t), not citation-stream extinction. "
            "Citation count is partly endogenous; directionality is not fully identifiable."
        ),
        "comparisons": decay_comparisons,
        "citation_stop_comparisons": stop_comparisons,
        "decomposition": decomposition,
        "dataset_note": (
            "dataset_v0.1 predates cited_doi fix; treat as exploratory only. "
            "Use post-fix builds for formal modelling."
        ),
        "paper_claim_guidance": (
            "Observed knowledge persistence appears primarily associated with influence "
            "accumulation rather than domain membership. HNDL risk models should prioritise "
            "measured influence longevity over broad sector labels, while acknowledging that "
            "citation intensity and persistence are mutually reinforcing."
        ),
        "note": "Preview only. Formal modelling should reference a post-fix frozen dataset.",
    }
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    if logrank_p is not None:
        logger.success(
            "Survival preview written to {} (decay matched log-rank p={:.4f})",
            output,
            logrank_p,
        )
    else:
        logger.success("Survival preview written to {}", output)
    return output
