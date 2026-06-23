"""Stage 2: OpenCitations enrichment."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
from loguru import logger

from pqm_readiness.checkpoint import Checkpoint, load_checkpoint, save_checkpoint
from pqm_readiness.config import PipelineConfig
from pqm_readiness.http import RateLimitedClient
from pqm_readiness.ingest.openalex import iter_dois_from_openalex
from pqm_readiness.models import extract_doi

OPENCITATIONS_BASE = "https://api.opencitations.net/index/v2"
FLUSH_EVERY_DOIS = 25


def _normalize_citation(target_doi: str, raw: dict[str, Any]) -> dict[str, Any] | None:
    citing_doi = extract_doi(raw.get("citing"))
    if not citing_doi:
        return None
    # Incoming citation lookups are keyed by target DOI; trust the query target.
    cited_doi = target_doi
    creation = raw.get("creation")
    return {
        "citing_doi": citing_doi,
        "cited_doi": cited_doi,
        "citation_creation_date": creation,
        "oci": raw.get("oci"),
        "source": "opencitations_index_v2",
        "timespan": raw.get("timespan"),
        "journal_sc": raw.get("journal_sc"),
        "author_sc": raw.get("author_sc"),
        "ingested_at": datetime.now(UTC).isoformat(),
    }


def _chunk_dir(config: PipelineConfig, checkpoint_stage: str) -> Path:
    return config.raw_dir / f"{checkpoint_stage}_chunks"


def _write_chunk(chunk_dir: Path, chunk_index: int, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    chunk_dir.mkdir(parents=True, exist_ok=True)
    path = chunk_dir / f"part_{chunk_index:05d}.parquet"
    pq.write_table(pa.Table.from_pylist(rows), path, compression="snappy")


def _compact_chunks(chunk_dir: Path, output_path: Path) -> None:
    parts = sorted(chunk_dir.glob("part_*.parquet"))
    if not parts:
        if output_path.exists():
            output_path.unlink()
        return
    tables = [pq.read_table(path) for path in parts]
    pq.write_table(pa.concat_tables(tables), output_path, compression="snappy")


def ingest_opencitations(
    config: PipelineConfig,
    openalex_path: Path,
    *,
    output_name: str = "opencitations_citations.parquet",
    checkpoint_stage: str = "opencitations",
) -> Path:
    """Enrich works with incoming citation edges from OpenCitations."""
    config.ensure_dirs()
    output_path = config.raw_dir / output_name
    chunks_path = _chunk_dir(config, checkpoint_stage)
    checkpoint_path = config.checkpoint_path(checkpoint_stage)
    checkpoint = (
        load_checkpoint(checkpoint_path, checkpoint_stage)
        if config.resume
        else Checkpoint(stage=checkpoint_stage)
    )

    dois = list(iter_dois_from_openalex(openalex_path))
    if config.limit is not None:
        dois = dois[: config.limit]

    if checkpoint.completed and output_path.exists():
        logger.info("OpenCitations stage already complete; skipping")
        return output_path

    if not config.resume:
        if output_path.exists():
            output_path.unlink()
        if chunks_path.exists():
            for path in chunks_path.glob("part_*.parquet"):
                path.unlink()
            chunks_path.rmdir()

    start_index = checkpoint.records_processed
    processed = start_index
    pending_rows: list[dict[str, Any]] = []
    chunk_index = len(list(chunks_path.glob("part_*.parquet"))) if chunks_path.exists() else 0

    def _flush_pending() -> None:
        nonlocal chunk_index, pending_rows
        if not pending_rows:
            return
        _write_chunk(chunks_path, chunk_index, pending_rows)
        chunk_index += 1
        pending_rows = []

    with RateLimitedClient(
        base_url=OPENCITATIONS_BASE,
        mailto=config.mailto,
        requests_per_second=config.requests_per_second,
        timeout=30.0,
    ) as client:
        for index, doi in enumerate(dois):
            if index < start_index:
                continue

            encoded = f"doi:{doi}"
            try:
                payload = client.get_json(f"/citations/{encoded}")
            except Exception as exc:  # noqa: BLE001 - log and continue per-DOI
                logger.warning("OpenCitations failed for {}: {}", doi, exc)
                processed += 1
                if processed % FLUSH_EVERY_DOIS == 0:
                    _flush_pending()
                checkpoint = checkpoint.touch(records_processed=processed)
                save_checkpoint(checkpoint_path, checkpoint)
                continue

            if not isinstance(payload, list):
                processed += 1
                if processed % FLUSH_EVERY_DOIS == 0:
                    _flush_pending()
                checkpoint = checkpoint.touch(records_processed=processed)
                save_checkpoint(checkpoint_path, checkpoint)
                continue

            for item in payload[: config.max_citations_per_doi]:
                row = _normalize_citation(doi, item)
                if row:
                    pending_rows.append(row)
            if len(payload) > config.max_citations_per_doi:
                logger.warning(
                    "Truncated citations for {} ({} > cap {})",
                    doi,
                    len(payload),
                    config.max_citations_per_doi,
                )
            processed += 1

            if processed % FLUSH_EVERY_DOIS == 0:
                _flush_pending()
                logger.info("OpenCitations processed {}/{} DOIs", processed, len(dois))

            checkpoint = checkpoint.touch(
                records_processed=processed,
                completed=processed >= len(dois),
                extra={"last_doi": doi, "chunk_count": chunk_index},
            )
            save_checkpoint(checkpoint_path, checkpoint)

    _flush_pending()
    _compact_chunks(chunks_path, output_path)
    checkpoint = checkpoint.touch(completed=True)
    save_checkpoint(checkpoint_path, checkpoint)
    logger.success("OpenCitations enrichment complete: {} DOIs -> {}", processed, output_path)
    return output_path
