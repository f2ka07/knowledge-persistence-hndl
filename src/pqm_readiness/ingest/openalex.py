"""Stage 1: OpenAlex work ingestion."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

import pyarrow as pa
import pyarrow.parquet as pq
from loguru import logger

from pqm_readiness.checkpoint import Checkpoint, load_checkpoint, save_checkpoint
from pqm_readiness.config import PipelineConfig
from pqm_readiness.concept_groups import ConceptGroup
from pqm_readiness.http import RateLimitedClient
from pqm_readiness.models import extract_doi, extract_openalex_id, institution_count, primary_concept

OPENALEX_BASE = "https://api.openalex.org"
CLASSIFICATION_SOURCE = "openalex_concepts.id_filter"


def _concept_score(raw: dict[str, Any], openalex_id: str) -> float | None:
    for concept in raw.get("concepts") or []:
        concept_id = concept.get("id") or ""
        if concept_id.endswith(openalex_id):
            score = concept.get("score")
            return float(score) if score is not None else None
    return None


def _normalize_work(
    raw: dict[str, Any],
    *,
    concept_group: str | None = None,
    group_openalex_id: str | None = None,
) -> dict[str, Any]:
    return {
        "work_id": extract_openalex_id(raw.get("id")),
        "doi": extract_doi(raw.get("doi")),
        "year": raw.get("publication_year"),
        "concept": primary_concept(raw.get("concepts")),
        "concept_group": concept_group,
        "classification_source": CLASSIFICATION_SOURCE if concept_group else None,
        "classification_confidence": _concept_score(raw, group_openalex_id) if group_openalex_id else None,
        "citation_count": raw.get("cited_by_count") or 0,
        "institution_count": institution_count(raw.get("authorships")),
        "referenced_work_count": len(raw.get("referenced_works") or []),
        "primary_location": json.dumps(raw.get("primary_location") or {}),
        "authorships_json": json.dumps(raw.get("authorships") or []),
        "concepts_json": json.dumps(raw.get("concepts") or []),
        "source": "openalex",
        "ingested_at": datetime.now(UTC).isoformat(),
    }


def _write_batch(path: Path, rows: list[dict[str, Any]], *, overwrite: bool = False) -> None:
    if not rows:
        return
    table = pa.Table.from_pylist(rows)
    if path.exists() and not overwrite:
        existing = pq.read_table(path)
        table = pa.concat_tables([existing, table])
    pq.write_table(table, path, compression="snappy")


def _fetch_group_works(
    client: RateLimitedClient,
    config: PipelineConfig,
    group: ConceptGroup,
    limit: int,
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {
        "filter": config.openalex_filter_for_concept(group.openalex_id),
        "select": config.openalex_select,
        "per_page": min(config.per_page, limit),
        "sort": "cited_by_count:desc",
        "cursor": "*",
    }
    payload = client.get_json("/works", params=params)
    results = (payload.get("results") or [])[:limit]
    return [_normalize_work(item, concept_group=group.name, group_openalex_id=group.openalex_id) for item in results]


def ingest_openalex(config: PipelineConfig) -> Path:
    """Fetch works from OpenAlex and store normalized raw parquet."""
    config.ensure_dirs()
    output_path = config.raw_dir / "openalex_works.parquet"
    checkpoint_path = config.checkpoint_path("openalex")
    checkpoint = load_checkpoint(checkpoint_path, "openalex") if config.resume else Checkpoint(stage="openalex")

    if checkpoint.completed and output_path.exists():
        logger.info("OpenAlex stage already complete; skipping")
        return output_path

    if not config.resume and output_path.exists():
        output_path.unlink()

    if config.use_concept_groups:
        return _ingest_stratified(config, output_path, checkpoint_path, checkpoint)

    return _ingest_single_filter(config, output_path, checkpoint_path, checkpoint)


def _ingest_stratified(
    config: PipelineConfig,
    output_path: Path,
    checkpoint_path: Path,
    checkpoint: Checkpoint,
) -> Path:
    groups = config.selected_concept_groups
    completed_groups = set(checkpoint.extra.get("completed_groups", []))
    per_group_limit = config.limit_per_group
    if per_group_limit is None and config.limit is not None:
        per_group_limit = max(1, config.limit // len(groups))

    records_fetched = checkpoint.records_processed
    all_rows: list[dict[str, Any]] = []

    with RateLimitedClient(
        base_url=OPENALEX_BASE,
        mailto=config.mailto,
        requests_per_second=config.requests_per_second,
    ) as client:
        for group in groups:
            if group.name in completed_groups:
                continue
            if per_group_limit is None:
                raise ValueError("Set --limit or --limit-per-group for stratified sampling")

            rows = _fetch_group_works(client, config, group, per_group_limit)
            existing_ids = {row["work_id"] for row in all_rows}
            rows = [row for row in rows if row["work_id"] not in existing_ids]
            all_rows.extend(rows)
            records_fetched += len(rows)
            completed_groups.add(group.name)
            checkpoint = checkpoint.touch(
                records_processed=records_fetched,
                extra={"completed_groups": sorted(completed_groups), "last_group": group.name},
            )
            save_checkpoint(checkpoint_path, checkpoint)
            logger.info(
                "OpenAlex fetched {} works for {} (total={})",
                len(rows),
                group.name,
                records_fetched,
            )

    if all_rows:
        overwrite = not (config.resume and output_path.exists())
        _write_batch(output_path, all_rows, overwrite=overwrite)
    checkpoint = checkpoint.touch(completed=True)
    save_checkpoint(checkpoint_path, checkpoint)
    logger.success("OpenAlex stratified ingestion complete: {} records -> {}", records_fetched, output_path)
    return output_path


def _ingest_single_filter(
    config: PipelineConfig,
    output_path: Path,
    checkpoint_path: Path,
    checkpoint: Checkpoint,
) -> Path:
    params: dict[str, Any] = {
        "filter": config.openalex_filter,
        "select": config.openalex_select,
        "per_page": config.per_page,
        "sort": "publication_year:desc,cited_by_count:asc",
    }

    if checkpoint.cursor:
        params["cursor"] = checkpoint.cursor
    else:
        params["cursor"] = "*"

    records_fetched = checkpoint.records_processed
    limit = config.limit

    with RateLimitedClient(
        base_url=OPENALEX_BASE,
        mailto=config.mailto,
        requests_per_second=config.requests_per_second,
    ) as client:
        while True:
            if limit is not None and records_fetched >= limit:
                break

            payload = client.get_json("/works", params=params)
            results = payload.get("results") or []
            if not results:
                break

            if limit is not None:
                remaining = limit - records_fetched
                results = results[:remaining]

            normalized = [_normalize_work(item) for item in results]
            _write_batch(output_path, normalized)
            records_fetched += len(normalized)

            next_cursor = payload.get("meta", {}).get("next_cursor")
            checkpoint = checkpoint.touch(
                records_processed=records_fetched,
                cursor=next_cursor,
                completed=not next_cursor or (limit is not None and records_fetched >= limit),
            )
            save_checkpoint(checkpoint_path, checkpoint)
            logger.info("OpenAlex fetched {} works (total={})", len(normalized), records_fetched)

            if not next_cursor or (limit is not None and records_fetched >= limit):
                break
            params["cursor"] = next_cursor

    checkpoint = checkpoint.touch(completed=True)
    save_checkpoint(checkpoint_path, checkpoint)
    logger.success("OpenAlex ingestion complete: {} records -> {}", records_fetched, output_path)
    return output_path


def iter_dois_from_openalex(path: Path) -> Iterator[str]:
    table = pq.read_table(path, columns=["doi"])
    for value in table.column("doi").to_pylist():
        if value:
            yield value
