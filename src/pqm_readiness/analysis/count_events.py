"""Count survival events across cohorts."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import polars as pl
from loguru import logger

from pqm_readiness.config import PipelineConfig
from pqm_readiness.transform.persistence import DECAY_CONSECUTIVE_YEARS, DECAY_THRESHOLD_RATIO

COHORT_FILES = {
    "hndl": "persistence.parquet",
    "baseline_random": "baseline_random_sample.parquet",
    "baseline_year_only": "baseline_year_only.parquet",
    "baseline_matched": "baseline_matched.parquet",
}

MIN_EFFECTIVE_EVENTS = 50


def _cohort_event_counts(path: Path) -> dict[str, int | float | None]:
    if not path.exists():
        return {
            "records": 0,
            "citation_stop_events": 0,
            "influence_decay_events": 0,
            "citation_stop_censoring_share": None,
            "influence_decay_censoring_share": None,
        }
    frame = pl.read_parquet(path)
    if frame.height == 0:
        return {
            "records": 0,
            "citation_stop_events": 0,
            "influence_decay_events": 0,
            "citation_stop_censoring_share": None,
            "influence_decay_censoring_share": None,
        }

    stop_events = 0
    decay_events = 0
    stop_censoring: float | None = None
    decay_censoring: float | None = None

    if "censoring_flag" in frame.columns:
        stop_events = int(frame.filter(~pl.col("censoring_flag")).height)
        stop_censoring = float(frame.select(pl.col("censoring_flag").mean()).item() or 0.0)
    if "influence_decay_event" in frame.columns:
        decay_events = int(frame.filter(pl.col("influence_decay_event")).height)
        decay_censoring = float(
            frame.select(pl.col("influence_decay_censored").mean()).item() or 0.0
        )

    return {
        "records": frame.height,
        "citation_stop_events": stop_events,
        "influence_decay_events": decay_events,
        "citation_stop_censoring_share": stop_censoring,
        "influence_decay_censoring_share": decay_censoring,
    }


def count_effective_events(
    config: PipelineConfig,
    *,
    min_events: int = MIN_EFFECTIVE_EVENTS,
) -> Path:
    """Report event counts and scaling readiness (primary gate: influence decay)."""
    config.ensure_dirs()
    output = config.metadata_dir / "effective_events.json"

    cohorts: dict[str, dict[str, int | float | None]] = {}
    for name, filename in COHORT_FILES.items():
        cohorts[name] = _cohort_event_counts(config.processed_dir / filename)

    hndl_decay = int(cohorts.get("hndl", {}).get("influence_decay_events") or 0)
    hndl_stop = int(cohorts.get("hndl", {}).get("citation_stop_events") or 0)
    ready_to_scale = hndl_decay >= min_events

    if ready_to_scale:
        scaling_guidance = (
            f"HNDL cohort has {hndl_decay} influence-decay events (>= {min_events}). "
            "Scaling to --limit-per-group 100 is reasonable."
        )
    else:
        scaling_guidance = (
            f"HNDL cohort has {hndl_decay} influence-decay events and {hndl_stop} "
            f"citation-stop events (< {min_events}). Do not broaden years further; "
            "refine event definitions or modelling before scaling."
        )

    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "min_events_threshold": min_events,
        "primary_event_definition": "influence_decay",
        "decay_rule": (
            f"annual_rate < {DECAY_THRESHOLD_RATIO} * peak_rate "
            f"for {DECAY_CONSECUTIVE_YEARS} consecutive years"
        ),
        "cohorts": cohorts,
        "hndl_influence_decay_events": hndl_decay,
        "hndl_citation_stop_events": hndl_stop,
        "ready_to_scale": ready_to_scale,
        "scaling_guidance": scaling_guidance,
        "note": (
            "Influence decay measures strategic relevance loss, not citation extinction. "
            "dataset_v0.1 predates cited_doi fix; use post-fix builds for inference."
        ),
    }
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    logger.success(
        "Effective events written to {} (HNDL decay={}, stop={}, ready={})",
        output,
        hndl_decay,
        hndl_stop,
        ready_to_scale,
    )
    return output
