"""Citation edge auditing utilities."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl
from loguru import logger

from pqm_readiness.config import PipelineConfig


def _edges_per_work(citations: pl.DataFrame, works: pl.DataFrame) -> pl.DataFrame:
    if citations.height == 0:
        return pl.DataFrame(schema={"target_doi": pl.Utf8, "edge_count": pl.UInt32})
    return (
        citations.group_by("target_doi")
        .len()
        .rename({"len": "edge_count"})
        .join(works.select("doi", "work_id", "concept_group"), left_on="target_doi", right_on="doi", how="left")
    )


def audit_citations(config: PipelineConfig) -> Path:
    """Audit citation edge density, duplication, and directionality."""
    config.ensure_dirs()
    raw_path = config.raw_dir / "opencitations_citations.parquet"
    proc_path = config.processed_dir / "citations.parquet"
    works_path = config.processed_dir / "works.parquet"

    report: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "direction": "incoming_only",
        "direction_note": "OpenCitations /citations/{doi} returns incoming citations only.",
        "raw": {},
        "processed": {},
        "warnings": [],
    }

    if works_path.exists():
        works = pl.read_parquet(works_path)
        report["works_count"] = works.height
        report["unique_work_dois"] = int(works.filter(pl.col("doi").is_not_null()).height)
    else:
        works = pl.DataFrame()

    if raw_path.exists():
        raw = pl.read_parquet(raw_path)
        raw_unique_edges = raw.unique(subset=["citing_doi", "cited_doi", "citation_creation_date", "oci"])
        report["raw"] = {
            "row_count": raw.height,
            "unique_oci": int(raw["oci"].n_unique()) if "oci" in raw.columns else None,
            "unique_edges": raw_unique_edges.height,
            "duplicate_rate": round(1 - (raw_unique_edges.height / raw.height), 4) if raw.height else 0.0,
            "unique_cited_dois": int(raw["cited_doi"].n_unique()),
            "unique_citing_dois": int(raw["citing_doi"].n_unique()),
        }
        if works.height:
            per_work = _edges_per_work(
                raw.rename({"citing_doi": "source_doi", "cited_doi": "target_doi"}),
                works,
            )
            report["raw"]["mean_edges_per_work"] = round(float(per_work["edge_count"].mean()), 2)
            report["raw"]["max_edges_per_work"] = int(per_work["edge_count"].max())
            report["raw"]["edges_per_work"] = per_work.sort("edge_count", descending=True).to_dicts()

    if proc_path.exists():
        proc = pl.read_parquet(proc_path)
        proc_unique = proc.unique(subset=["source_doi", "target_doi", "citation_creation_date"])
        report["processed"] = {
            "row_count": proc.height,
            "unique_edges": proc_unique.height,
            "duplicate_rate": round(1 - (proc_unique.height / proc.height), 4) if proc.height else 0.0,
        }
        if works.height:
            per_work = _edges_per_work(proc, works)
            report["processed"]["mean_edges_per_work"] = round(float(per_work["edge_count"].mean()), 2)
            report["processed"]["max_edges_per_work"] = int(per_work["edge_count"].max())

    if report.get("raw", {}).get("duplicate_rate", 0) > 0:
        report["warnings"].append(
            "Raw OpenCitations parquet contains duplicate edges; likely appended across runs."
        )
    max_edges = report.get("raw", {}).get("max_edges_per_work", 0)
    if max_edges and max_edges > 5000:
        report["warnings"].append(
            f"At least one work has {max_edges} edges, exceeding default per-DOI cap of 5000."
        )

    output = config.metadata_dir / "citation_audit.json"
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    logger.success("Citation audit written to {}", output)
    return output
