"""Checkpoint persistence for resumable pipeline stages."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class Checkpoint(BaseModel):
    stage: str
    updated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    records_processed: int = 0
    cursor: str | None = None
    page: int = 1
    completed: bool = False
    extra: dict[str, Any] = Field(default_factory=dict)

    def touch(self, **fields: Any) -> Checkpoint:
        data = self.model_dump()
        data.update(fields)
        data["updated_at"] = datetime.now(UTC).isoformat()
        return Checkpoint.model_validate(data)


def load_checkpoint(path: Path, stage: str) -> Checkpoint:
    if not path.exists():
        return Checkpoint(stage=stage)
    payload = json.loads(path.read_text(encoding="utf-8"))
    return Checkpoint.model_validate(payload)


def save_checkpoint(path: Path, checkpoint: Checkpoint) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(checkpoint.model_dump_json(indent=2), encoding="utf-8")
