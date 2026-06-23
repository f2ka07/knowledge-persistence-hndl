#!/usr/bin/env python3
"""Summarize released dataset tables from local files (no API access)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

PROCESSED_CANDIDATES = (
    ROOT / "dataset_v0.2_candidate" / "processed",
    ROOT / "data" / "processed",
)
METADATA_CANDIDATES = (
    ROOT / "dataset_v0.2_candidate" / "metadata",
    ROOT / "data" / "metadata",
)

TABLES = (
    "works.parquet",
    "citations.parquet",
    "citations_by_year.parquet",
    "persistence.parquet",
    "citation_persistence_panel.parquet",
    "baseline_random_sample.parquet",
    "baseline_matched.parquet",
    "baseline_year_only.parquet",
    "threshold_sensitivity.parquet",
)


def _resolve_dir(candidates: tuple[Path, ...]) -> Path | None:
    for path in candidates:
        if path.exists():
            return path
    return None


def _load_parquet(path: Path):
    import polars as pl

    return pl.read_parquet(path)


def summarize() -> dict[str, Any]:
    processed_dir = _resolve_dir(PROCESSED_CANDIDATES)
    metadata_dir = _resolve_dir(METADATA_CANDIDATES)
    if processed_dir is None:
        raise FileNotFoundError("No processed directory found")

    table_stats: dict[str, Any] = {}
    for name in TABLES:
        path = processed_dir / name
        if not path.exists():
            continue
        frame = _load_parquet(path)
        table_stats[name] = {"rows": frame.height, "columns": list(frame.columns)}

    sector_distribution: dict[str, int] = {}
    year_distribution: dict[str, int] = {}
    decay_summary: dict[str, Any] = {}

    works_path = processed_dir / "works.parquet"
    persistence_path = processed_dir / "persistence.parquet"
    if works_path.exists():
        works = _load_parquet(works_path)
        if "concept_group" in works.columns:
            sector_distribution = {
                str(k): int(v)
                for k, v in works.group_by("concept_group").len().sort("concept_group").iter_rows()
            }
        year_col = "year" if "year" in works.columns else "publication_year"
        if year_col in works.columns:
            year_distribution = {
                str(k): int(v)
                for k, v in works.group_by(year_col).len().sort(year_col).iter_rows()
            }

    if persistence_path.exists():
        persistence = _load_parquet(persistence_path)
        decay_summary = {
            "records": persistence.height,
            "influence_decay_events": int(persistence["influence_decay_event"].sum())
            if "influence_decay_event" in persistence.columns
            else None,
            "influence_decay_censoring_share": float(persistence["influence_decay_censored"].mean())
            if "influence_decay_censored" in persistence.columns
            else None,
            "citation_stop_censoring_share": float(persistence["censoring_flag"].mean())
            if "censoring_flag" in persistence.columns
            else None,
        }

    effective_events: dict[str, Any] = {}
    if metadata_dir:
        events_path = metadata_dir / "effective_events.json"
        if events_path.exists():
            effective_events = json.loads(events_path.read_text(encoding="utf-8"))

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "processed_dir": str(processed_dir.relative_to(ROOT)),
        "tables": table_stats,
        "sector_distribution": sector_distribution,
        "year_distribution": year_distribution,
        "persistence_summary": decay_summary,
        "effective_events": effective_events,
    }


def main() -> None:
    summary = summarize()
    out_path = ROOT / "data" / "metadata" / "dataset_summary.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"Dataset summary -> {out_path}")
    for name, stats in summary["tables"].items():
        print(f"  {name}: {stats['rows']} rows")
    if summary.get("persistence_summary"):
        ps = summary["persistence_summary"]
        print(f"  influence_decay_events: {ps.get('influence_decay_events')}")


if __name__ == "__main__":
    main()
