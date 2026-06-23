"""Patent mention enrichment via Crossref Event Data (Cambia Lens source)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import polars as pl
import pyarrow as pa
import pyarrow.parquet as pq
import truststore
from loguru import logger

from pqm_readiness.checkpoint import Checkpoint, load_checkpoint, save_checkpoint
from pqm_readiness.config import PipelineConfig

EVENT_DATA_BASE = "https://api.eventdata.crossref.org/v1"
PATENT_SOURCE = "cambia-lens"
truststore.inject_into_ssl()


def _count_patent_mentions(client: httpx.Client, doi: str) -> tuple[int | None, str]:
    """Return patent mention count and enrichment status."""
    obj_id = f"https://doi.org/{doi}"
    try:
        response = client.get(
            f"{EVENT_DATA_BASE}/events",
            params={"obj-id": obj_id, "source": PATENT_SOURCE, "rows": 0},
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Patent enrichment unavailable for {}: {}", doi, exc)
        return None, "unavailable"

    message = payload.get("message", {}) if isinstance(payload, dict) else {}
    total = message.get("total-results")
    if total is None:
        return None, "unavailable"
    return int(total), "ok"


def ingest_patent_mentions(config: PipelineConfig, openalex_path: Path) -> Path:
    """Count patent citations to each work DOI (Crossref Event Data / Cambia Lens)."""
    config.ensure_dirs()
    output_path = config.raw_dir / "patent_mentions.parquet"
    checkpoint_path = config.checkpoint_path("patents")
    checkpoint = (
        load_checkpoint(checkpoint_path, "patents")
        if config.resume
        else Checkpoint(stage="patents")
    )

    if checkpoint.completed and output_path.exists():
        logger.info("Patent enrichment already complete; skipping")
        return output_path

    if not config.resume:
        if output_path.exists():
            output_path.unlink()
        checkpoint = Checkpoint(stage="patents")

    works = pl.read_parquet(openalex_path, columns=["doi"]).filter(pl.col("doi").is_not_null())
    dois = works.get_column("doi").to_list()
    start_index = checkpoint.records_processed
    rows: list[dict[str, Any]] = []

    headers = {
        "User-Agent": f"pqm-readiness/0.1.0 (mailto:{config.mailto})",
        "Accept": "application/json",
    }
    with httpx.Client(headers=headers, timeout=8.0, follow_redirects=True) as client:
        for index, doi in enumerate(dois):
            if index < start_index:
                continue
            count, status = _count_patent_mentions(client, doi)
            rows.append(
                {
                    "doi": doi,
                    "patent_mentions": count,
                    "source": PATENT_SOURCE,
                    "enrichment_status": status,
                    "ingested_at": datetime.now(UTC).isoformat(),
                }
            )
            checkpoint = checkpoint.touch(
                records_processed=index + 1,
                completed=index + 1 >= len(dois),
                extra={"last_doi": doi},
            )
            save_checkpoint(checkpoint_path, checkpoint)

    if rows:
        pq.write_table(pa.Table.from_pylist(rows), output_path, compression="snappy")

    checkpoint = checkpoint.touch(completed=True)
    save_checkpoint(checkpoint_path, checkpoint)
    logger.success("Patent enrichment complete: {} DOIs -> {}", len(rows), output_path)
    return output_path
