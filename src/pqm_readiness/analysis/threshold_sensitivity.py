"""Grid stability analysis for influence-decay threshold parameters."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl
from loguru import logger

from pqm_readiness.analysis.decay_series import (
    COHORT_SOURCES,
    decay_frame_at_params,
    load_citations_by_year,
    survival_ready_frame,
)
from pqm_readiness.analysis.survival_compare import cohort_km_median, compare_decay_survival
from pqm_readiness.config import PipelineConfig

THRESHOLD_GRID: list[tuple[float, int]] = [
    (0.05, 2),
    (0.05, 3),
    (0.10, 2),
    (0.10, 3),
    (0.15, 3),
    (0.20, 3),
]

PRIMARY_BASELINE = "baseline_matched"


def _stability_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Classify whether 10-15% threshold region yields similar tier-C conclusions."""
    by_key = {(r["threshold_ratio"], r["consecutive_years"]): r for r in rows}
    ref = by_key.get((0.10, 3))
    region = [by_key.get((0.10, 3)), by_key.get((0.15, 3))]
    region = [r for r in region if r is not None]

    def tier_c_neutral(row: dict[str, Any]) -> bool | None:
        p = row.get("logrank_p_matched")
        if p is None:
            return None
        return p >= 0.05

    ref_neutral = tier_c_neutral(ref) if ref else None
    region_neutral = [tier_c_neutral(r) for r in region]
    stable = ref_neutral is not None and all(n == ref_neutral for n in region_neutral if n is not None)

    p_values = [r["logrank_p_matched"] for r in rows if r.get("logrank_p_matched") is not None]
    p_range = (min(p_values), max(p_values)) if p_values else (None, None)

    return {
        "reference_configuration": {"threshold_ratio": 0.10, "consecutive_years": 3},
        "tier_c_neutral_at_reference": ref_neutral,
        "ten_to_fifteen_percent_region_stable": stable,
        "logrank_p_range_matched": {"min": p_range[0], "max": p_range[1]},
        "decision_guidance": (
            "Choose the most stable region (10-15%), not the most significant. "
            "If conclusions flip across the grid, treat the decay metric as unstable."
        ),
        "stable_region_recommendation": (
            "10-15% thresholds with 3 consecutive years"
            if stable
            else "Conclusions vary across grid; interpret decay metric cautiously"
        ),
    }


def _evaluate_grid_cell(
    config: PipelineConfig,
    cohort_data: dict[str, tuple[pl.DataFrame, pl.DataFrame]],
    *,
    threshold_ratio: float,
    consecutive_years: int,
) -> dict[str, Any]:
    decay_by_cohort: dict[str, pl.DataFrame] = {}
    for cohort, (works_df, cby_df) in cohort_data.items():
        decay_by_cohort[cohort] = decay_frame_at_params(
            works_df,
            cby_df,
            threshold_ratio=threshold_ratio,
            consecutive_years=consecutive_years,
        )

    hndl_surv = survival_ready_frame(decay_by_cohort["hndl"]).to_pandas()
    matched_surv = survival_ready_frame(decay_by_cohort[PRIMARY_BASELINE]).to_pandas()

    row: dict[str, Any] = {
        "threshold_ratio": threshold_ratio,
        "consecutive_years": consecutive_years,
        "event_count": int(hndl_surv["event"].sum()) if not hndl_surv.empty else 0,
        "censoring_rate": float(hndl_surv["censoring_flag"].mean()) if not hndl_surv.empty else None,
        "median_time_to_decay": cohort_km_median(hndl_surv) if not hndl_surv.empty else None,
    }

    if hndl_surv.empty or matched_surv.empty:
        row.update(
            {
                "logrank_p": None,
                "cox_hr": None,
                "logrank_p_matched": None,
                "cox_hr_matched": None,
                "matched_event_count": None,
                "matched_censoring_rate": None,
            }
        )
        return row

    comparison = compare_decay_survival(hndl_surv, matched_surv)
    row.update(
        {
            "logrank_p": comparison["logrank_p"],
            "cox_hr": comparison["cox_hr"],
            "logrank_p_matched": comparison["logrank_p"],
            "cox_hr_matched": comparison["cox_hr"],
            "matched_event_count": comparison["other_event_count"],
            "matched_censoring_rate": comparison["other_censoring_rate"],
        }
    )

    for label, tier_key in (
        ("baseline_random", "logrank_p_random"),
        ("baseline_year_only", "logrank_p_year_only"),
    ):
        other_surv = survival_ready_frame(decay_by_cohort[label]).to_pandas()
        if hndl_surv.empty or other_surv.empty:
            row[tier_key] = None
            continue
        other_cmp = compare_decay_survival(hndl_surv, other_surv)
        row[tier_key] = other_cmp["logrank_p"]

    return row


def run_threshold_sensitivity(config: PipelineConfig) -> Path:
    """Evaluate decay-threshold grid and write threshold_sensitivity.parquet."""
    config.ensure_dirs()
    output = config.processed_dir / "threshold_sensitivity.parquet"
    meta_path = config.metadata_dir / "threshold_sensitivity.json"

    cohort_data: dict[str, tuple[pl.DataFrame, pl.DataFrame]] = {}
    for cohort in COHORT_SOURCES:
        try:
            cohort_data[cohort] = load_citations_by_year(config, cohort)
        except FileNotFoundError:
            logger.warning("Skipping cohort {} (missing raw inputs)", cohort)

    if "hndl" not in cohort_data or PRIMARY_BASELINE not in cohort_data:
        raise FileNotFoundError(
            "Need HNDL and baseline_matched raw inputs for threshold sensitivity."
        )

    rows: list[dict[str, Any]] = []
    for threshold_ratio, consecutive_years in THRESHOLD_GRID:
        rows.append(
            _evaluate_grid_cell(
                config,
                cohort_data,
                threshold_ratio=threshold_ratio,
                consecutive_years=consecutive_years,
            )
        )

    pl.DataFrame(rows).write_parquet(output)
    summary = _stability_summary(rows)
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "grid": [{"threshold_ratio": t, "consecutive_years": c} for t, c in THRESHOLD_GRID],
        "primary_comparison": f"hndl_vs_{PRIMARY_BASELINE}",
        "rows": rows,
        "stability": summary,
        "note": (
            "Do not tune thresholds to hit event-count gates. "
            "Select the most stable parameter region, not the most significant."
        ),
    }
    meta_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    logger.success("Threshold sensitivity -> {} (stable region: {})", output, summary["stable_region_recommendation"])
    return output
