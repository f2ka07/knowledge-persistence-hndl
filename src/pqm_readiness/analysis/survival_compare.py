"""Shared survival comparison helpers (log-rank, Cox HR, KM median)."""

from __future__ import annotations

from typing import Any

import pandas as pd


def compare_decay_survival(hndl: pd.DataFrame, other: pd.DataFrame) -> dict[str, Any]:
    """Log-rank and Cox hazard ratio for HNDL vs another cohort."""
    from lifelines import CoxPHFitter, KaplanMeierFitter
    from lifelines.statistics import logrank_test

    logrank = logrank_test(
        hndl["duration"],
        other["duration"],
        event_observed_A=hndl["event"],
        event_observed_B=other["event"],
    )

    cox_df = pd.concat(
        [
            hndl[["duration", "event"]].assign(is_hndl=1),
            other[["duration", "event"]].assign(is_hndl=0),
        ],
        ignore_index=True,
    )
    cox = CoxPHFitter()
    cox.fit(cox_df, duration_col="duration", event_col="event")

    km = KaplanMeierFitter()
    km.fit(hndl["duration"], event_observed=hndl["event"])
    median = km.median_survival_time_
    median_value = float(median) if median == median and median != float("inf") else None

    return {
        "logrank_p": float(logrank.p_value),
        "cox_hr": float(cox.summary.loc["is_hndl", "exp(coef)"]),
        "cox_p": float(cox.summary.loc["is_hndl", "p"]),
        "hndl_event_count": int(hndl["event"].sum()),
        "hndl_censoring_rate": float(hndl["censoring_flag"].mean()),
        "hndl_median_time_to_decay": median_value,
        "other_event_count": int(other["event"].sum()),
        "other_censoring_rate": float(other["censoring_flag"].mean()),
    }


def cohort_km_median(frame: pd.DataFrame) -> float | None:
    from lifelines import KaplanMeierFitter

    km = KaplanMeierFitter()
    km.fit(frame["duration"], event_observed=frame["event"])
    median = km.median_survival_time_
    if median != median or median == float("inf"):
        return None
    return float(median)
