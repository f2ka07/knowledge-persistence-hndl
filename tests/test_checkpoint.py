"""Tests for checkpoint read/write."""

from pathlib import Path

from pqm_readiness.checkpoint import Checkpoint, load_checkpoint, save_checkpoint


def test_checkpoint_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "checkpoint_openalex.json"
    checkpoint = Checkpoint(stage="openalex", records_processed=42, cursor="abc")
    save_checkpoint(path, checkpoint)
    loaded = load_checkpoint(path, "openalex")
    assert loaded.records_processed == 42
    assert loaded.cursor == "abc"
