"""Freeze a reproducible dataset snapshot."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from loguru import logger

from pqm_readiness import __version__
from pqm_readiness.config import PipelineConfig


def _git_commit(root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def freeze_dataset(config: PipelineConfig, version: str = "v0.1") -> Path:
    """Copy processed outputs and metadata into a frozen dataset directory."""
    config.ensure_dirs()
    freeze_dir = config.root / f"dataset_{version}"
    freeze_dir.mkdir(parents=True, exist_ok=True)

    for sub in ("processed", "metadata"):
        src = config.base_data_dir / sub if sub == "processed" else config.metadata_dir
        dst = freeze_dir / sub
        if dst.exists():
            shutil.rmtree(dst)
        if src.exists():
            shutil.copytree(src, dst)

    provenance_path = config.provenance_path()
    provenance = {}
    if provenance_path.exists():
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))

    file_hashes: dict[str, str] = {}
    for path in sorted(freeze_dir.rglob("*")):
        if path.is_file():
            rel = str(path.relative_to(freeze_dir)).replace("\\", "/")
            file_hashes[rel] = _file_sha256(path)

    manifest = {
        "dataset_version": version,
        "frozen_at": datetime.now(UTC).isoformat(),
        "pipeline_version": __version__,
        "git_commit": _git_commit(config.root),
        "seed": config.seed,
        "api_versions": {
            "openalex": "https://api.openalex.org",
            "opencitations": "https://api.opencitations.net/index/v2",
            "crossref_event_data": "https://api.eventdata.crossref.org/v1 (optional)",
        },
        "query": provenance.get("query", {}),
        "interpretation_policy": (
            "Citation persistence is proxy K(t), not trade secret value V(t). "
            "Do not interpret cohort medians without survival analysis."
        ),
        "analysis_phase": version.startswith("v0.2"),
        "paper_framing": (
            "How should long-horizon information persistence be operationalised?"
            if version.startswith("v0.2")
            else None
        ),
        "files": file_hashes,
    }
    manifest_path = freeze_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    logger.success("Frozen dataset {} -> {}", version, freeze_dir)
    return freeze_dir
