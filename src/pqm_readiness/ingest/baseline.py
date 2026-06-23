"""Null-model baseline: random and citation-count matched OpenAlex samples."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl
import pyarrow as pa
import pyarrow.parquet as pq
from loguru import logger

from pqm_readiness.checkpoint import Checkpoint, load_checkpoint, save_checkpoint
from pqm_readiness.concept_groups import HNDL_CONCEPT_GROUPS
from pqm_readiness.config import PipelineConfig
from pqm_readiness.http import RateLimitedClient
from pqm_readiness.ingest.openalex import _normalize_work, _write_batch
from pqm_readiness.matching import (
    candidate_matches_stratum,
    candidate_matches_year_stratum,
    match_stratum_from_row,
    openalex_filter_for_stratum,
    openalex_filter_for_year_stratum,
    stratum_key,
)

OPENALEX_BASE = "https://api.openalex.org"
BASELINE_RANDOM_GROUP = "baseline_random"
BASELINE_MATCHED_GROUP = "baseline_matched"
BASELINE_YEAR_ONLY_GROUP = "baseline_year_only"
HNDL_CONCEPT_IDS = {group.openalex_id for group in HNDL_CONCEPT_GROUPS}


def _baseline_filter(config: PipelineConfig, year: int) -> str:
    if config.max_cited_by_count is None:
        citation_filter = f"cited_by_count:>{config.min_cited_by_count}"
    else:
        citation_filter = (
            f"cited_by_count:{config.min_cited_by_count}-{config.max_cited_by_count}"
        )
    return f"publication_year:{year},{citation_filter},has_doi:true,type:article"


def _is_hndl_work(raw: dict[str, Any]) -> bool:
    for concept in raw.get("concepts") or []:
        concept_id = (concept.get("id") or "").rsplit("/", 1)[-1]
        if concept_id in HNDL_CONCEPT_IDS:
            return True
    return False


def ingest_baseline_sample(config: PipelineConfig, hndl_openalex_path: Path) -> Path:
    """Draw a year-matched random sample excluding HNDL concept groups."""
    config.ensure_dirs()
    output_path = config.raw_dir / "baseline_works.parquet"
    checkpoint_path = config.checkpoint_path("baseline")
    checkpoint = (
        load_checkpoint(checkpoint_path, "baseline")
        if config.resume
        else Checkpoint(stage="baseline")
    )

    if checkpoint.completed and output_path.exists():
        logger.info("Baseline sample already complete; skipping")
        return output_path

    if not config.resume and output_path.exists():
        output_path.unlink()

    hndl = pl.read_parquet(hndl_openalex_path)
    if hndl.height == 0:
        logger.warning("No HNDL works found; skipping baseline sample")
        return output_path

    year_targets = (
        hndl.group_by("year")
        .len()
        .rename({"len": "target_count"})
        .sort("year")
    )
    completed_years = set(checkpoint.extra.get("completed_years", []))
    all_rows: list[dict[str, Any]] = []
    existing_ids: set[str] = set()

    with RateLimitedClient(
        base_url=OPENALEX_BASE,
        mailto=config.mailto,
        requests_per_second=config.requests_per_second,
    ) as client:
        for row in year_targets.iter_rows(named=True):
            year = int(row["year"])
            if year in completed_years:
                continue

            target_count = int(row["target_count"])
            collected: list[dict[str, Any]] = []
            sample_size = max(target_count * 3, 25)
            params = {
                "filter": _baseline_filter(config, year),
                "select": config.openalex_select,
                "sample": sample_size,
                "seed": config.seed + year,
            }
            payload = client.get_json("/works", params=params)
            for item in payload.get("results") or []:
                if _is_hndl_work(item):
                    continue
                normalized = _normalize_work(
                    item,
                    concept_group=BASELINE_RANDOM_GROUP,
                    group_openalex_id=None,
                )
                normalized["classification_source"] = "openalex_random_sample"
                normalized["classification_confidence"] = None
                if normalized["work_id"] in existing_ids:
                    continue
                collected.append(normalized)
                existing_ids.add(normalized["work_id"])
                if len(collected) >= target_count:
                    break

            all_rows.extend(collected)
            completed_years.add(year)
            checkpoint = checkpoint.touch(
                records_processed=len(all_rows),
                extra={"completed_years": sorted(completed_years), "last_year": year},
            )
            save_checkpoint(checkpoint_path, checkpoint)
            logger.info(
                "Baseline sampled {} works for year {} (target={})",
                len(collected),
                year,
                target_count,
            )

    if all_rows:
        overwrite = not (config.resume and output_path.exists())
        _write_batch(output_path, all_rows, overwrite=overwrite)

    checkpoint = checkpoint.touch(completed=True)
    save_checkpoint(checkpoint_path, checkpoint)
    logger.success("Baseline sample complete: {} records -> {}", len(all_rows), output_path)
    return output_path


def _pick_controls_for_stratum(
    client: RateLimitedClient,
    config: PipelineConfig,
    stratum: dict[str, Any],
    needed: int,
    *,
    used_ids: set[str],
    relax_source_type: bool = False,
    relax_concept_depth: bool = False,
) -> list[dict[str, Any]]:
    sample_size = max(needed * 5, 25)
    params = {
        "filter": openalex_filter_for_stratum(stratum),
        "select": config.openalex_select,
        "sample": sample_size,
        "seed": config.seed + hash(stratum_key(stratum)) % 1_000_000,
    }
    payload = client.get_json("/works", params=params)
    picked: list[dict[str, Any]] = []
    for item in payload.get("results") or []:
        if _is_hndl_work(item):
            continue
        if not candidate_matches_stratum(
            item,
            stratum,
            relax_source_type=relax_source_type,
            relax_concept_depth=relax_concept_depth,
        ):
            continue
        normalized = _normalize_work(
            item,
            concept_group=BASELINE_MATCHED_GROUP,
            group_openalex_id=None,
        )
        normalized["classification_source"] = "openalex_matched_sample"
        normalized["classification_confidence"] = None
        normalized["match_stratum_json"] = json.dumps(stratum)
        if normalized["work_id"] in used_ids:
            continue
        picked.append(normalized)
        used_ids.add(normalized["work_id"])
        if len(picked) >= needed:
            break
    return picked


def ingest_baseline_matched(config: PipelineConfig, hndl_openalex_path: Path) -> Path:
    """Draw citation-count matched controls for each HNDL work."""
    config.ensure_dirs()
    output_path = config.raw_dir / "baseline_matched_works.parquet"
    checkpoint_path = config.checkpoint_path("baseline_matched")
    checkpoint = (
        load_checkpoint(checkpoint_path, "baseline_matched")
        if config.resume
        else Checkpoint(stage="baseline_matched")
    )

    if checkpoint.completed and output_path.exists():
        logger.info("Matched baseline already complete; skipping")
        return output_path

    if not config.resume and output_path.exists():
        output_path.unlink()

    hndl = pl.read_parquet(hndl_openalex_path)
    if hndl.height == 0:
        logger.warning("No HNDL works found; skipping matched baseline")
        return output_path

    strata_rows: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in hndl.iter_rows(named=True):
        stratum = match_stratum_from_row(row)
        strata_rows[stratum_key(stratum)].append({"hndl_row": row, "stratum": stratum})

    completed_strata = set(checkpoint.extra.get("completed_strata", []))
    all_rows: list[dict[str, Any]] = []
    used_ids: set[str] = set(hndl.get_column("work_id").to_list())
    assignments: list[dict[str, Any]] = []

    with RateLimitedClient(
        base_url=OPENALEX_BASE,
        mailto=config.mailto,
        requests_per_second=config.requests_per_second,
    ) as client:
        for key, entries in sorted(strata_rows.items()):
            if key in completed_strata:
                continue

            stratum = entries[0]["stratum"]
            needed = len(entries)
            collected: list[dict[str, Any]] = []
            collected.extend(
                _pick_controls_for_stratum(
                    client,
                    config,
                    stratum,
                    needed,
                    used_ids=used_ids,
                )
            )
            if len(collected) < needed:
                collected.extend(
                    _pick_controls_for_stratum(
                        client,
                        config,
                        stratum,
                        needed - len(collected),
                        used_ids=used_ids,
                        relax_source_type=True,
                    )
                )
            if len(collected) < needed:
                collected.extend(
                    _pick_controls_for_stratum(
                        client,
                        config,
                        stratum,
                        needed - len(collected),
                        used_ids=used_ids,
                        relax_source_type=True,
                        relax_concept_depth=True,
                    )
                )

            for control, entry in zip(collected, entries, strict=False):
                control = dict(control)
                control["matched_hndl_work_id"] = entry["hndl_row"]["work_id"]
                all_rows.append(control)
                assignments.append(
                    {
                        "hndl_work_id": entry["hndl_row"]["work_id"],
                        "control_work_id": control["work_id"],
                        "stratum": stratum,
                    }
                )

            completed_strata.add(key)
            checkpoint = checkpoint.touch(
                records_processed=len(all_rows),
                extra={
                    "completed_strata": [list(item) for item in sorted(completed_strata)],
                    "assignments": assignments,
                },
            )
            save_checkpoint(checkpoint_path, checkpoint)
            logger.info(
                "Matched baseline stratum {}: {} controls for {} HNDL works",
                key,
                len(collected),
                needed,
            )

    if all_rows:
        overwrite = not (config.resume and output_path.exists())
        _write_batch(output_path, all_rows, overwrite=overwrite)

    checkpoint = checkpoint.touch(completed=True)
    save_checkpoint(checkpoint_path, checkpoint)
    logger.success("Matched baseline complete: {} records -> {}", len(all_rows), output_path)
    return output_path


def _pick_year_controls(
    client: RateLimitedClient,
    config: PipelineConfig,
    year: int,
    needed: int,
    *,
    used_ids: set[str],
) -> list[dict[str, Any]]:
    stratum = {"year": year}
    sample_size = max(needed * 5, 25)
    params = {
        "filter": openalex_filter_for_year_stratum(
            stratum,
            min_cited_by_count=config.min_cited_by_count,
            max_cited_by_count=config.max_cited_by_count,
        ),
        "select": config.openalex_select,
        "sample": sample_size,
        "seed": config.seed + year + 10_000,
    }
    payload = client.get_json("/works", params=params)
    picked: list[dict[str, Any]] = []
    for item in payload.get("results") or []:
        if _is_hndl_work(item):
            continue
        if not candidate_matches_year_stratum(item, stratum):
            continue
        normalized = _normalize_work(
            item,
            concept_group=BASELINE_YEAR_ONLY_GROUP,
            group_openalex_id=None,
        )
        normalized["classification_source"] = "openalex_year_matched_sample"
        normalized["classification_confidence"] = None
        normalized["match_stratum_json"] = json.dumps(stratum)
        if normalized["work_id"] in used_ids:
            continue
        picked.append(normalized)
        used_ids.add(normalized["work_id"])
        if len(picked) >= needed:
            break
    return picked


def ingest_baseline_year_only(config: PipelineConfig, hndl_openalex_path: Path) -> Path:
    """Draw year+DOI matched controls without citation-count matching."""
    config.ensure_dirs()
    output_path = config.raw_dir / "baseline_year_only_works.parquet"
    checkpoint_path = config.checkpoint_path("baseline_year_only")
    checkpoint = (
        load_checkpoint(checkpoint_path, "baseline_year_only")
        if config.resume
        else Checkpoint(stage="baseline_year_only")
    )

    if checkpoint.completed and output_path.exists():
        logger.info("Year-only baseline already complete; skipping")
        return output_path

    if not config.resume and output_path.exists():
        output_path.unlink()

    hndl = pl.read_parquet(hndl_openalex_path)
    if hndl.height == 0:
        logger.warning("No HNDL works found; skipping year-only baseline")
        return output_path

    year_groups: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in hndl.iter_rows(named=True):
        year_groups[int(row["year"])].append(row)

    completed_years = set(checkpoint.extra.get("completed_years", []))
    all_rows: list[dict[str, Any]] = []
    used_ids: set[str] = set(hndl.get_column("work_id").to_list())

    with RateLimitedClient(
        base_url=OPENALEX_BASE,
        mailto=config.mailto,
        requests_per_second=config.requests_per_second,
    ) as client:
        for year in sorted(year_groups):
            if year in completed_years:
                continue

            hndl_rows = year_groups[year]
            needed = len(hndl_rows)
            collected = _pick_year_controls(client, config, year, needed, used_ids=used_ids)

            for control, hndl_row in zip(collected, hndl_rows, strict=False):
                control = dict(control)
                control["matched_hndl_work_id"] = hndl_row["work_id"]
                all_rows.append(control)

            completed_years.add(year)
            checkpoint = checkpoint.touch(
                records_processed=len(all_rows),
                extra={"completed_years": sorted(completed_years), "last_year": year},
            )
            save_checkpoint(checkpoint_path, checkpoint)
            logger.info(
                "Year-only baseline year {}: {} controls for {} HNDL works",
                year,
                len(collected),
                needed,
            )

    if all_rows:
        overwrite = not (config.resume and output_path.exists())
        _write_batch(output_path, all_rows, overwrite=overwrite)

    checkpoint = checkpoint.touch(completed=True)
    save_checkpoint(checkpoint_path, checkpoint)
    logger.success("Year-only baseline complete: {} records -> {}", len(all_rows), output_path)
    return output_path
