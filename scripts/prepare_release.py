#!/usr/bin/env python3
"""Assemble knowledge-persistence-hndl public release (no API access)."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RELEASE_DIR = ROOT / "knowledge-persistence-hndl"
REVIEW_DIR = ROOT / "data" / "release_review"

sys.path.insert(0, str(ROOT / "scripts"))
from audit_data_accessibility import run_audit  # noqa: E402
from summarize_dataset import summarize  # noqa: E402

DATASET_VERSION = "v0.2_candidate"
COMMIT_CLASSES = {"commit", "commit_large_if_needed"}

COPY_DIRS = (
    ("src/pqm_readiness", "src/pqm_readiness"),
    ("tests", "tests"),
    ("docs", "docs"),
    ("analysis", "analysis"),
    ("results", "results"),
    ("scripts", "scripts"),
)

COPY_FILES = (
    "pyproject.toml",
    "requirements.txt",
    "dataset_card.md",
    "CITATION.cff",
    "LICENSE.md",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_commit(path: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=path,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def _write_release_gitignore() -> None:
    content = """__pycache__/
*.py[cod]
*.egg-info/
.venv/
venv/
.env
.env.*
.pytest_cache/
.ruff_cache/
.mypy_cache/
*.log

# Raw ingestion (not redistributed)
data/raw/
data/intermediate/
data/release_review/
**/*_chunks/

# Ingestion resume checkpoints
**/checkpoint_*.json

dist/
build/
"""
    (RELEASE_DIR / ".gitignore").write_text(content, encoding="utf-8")


def _copy_audit_files(audit: dict[str, Any]) -> tuple[list[str], list[str], list[str]]:
    commit_files: list[str] = []
    excluded: list[str] = []
    review_files: list[str] = []

    for entry in audit["files"]:
        rel = entry["relative_path"]
        src = ROOT / rel
        classification = entry["classification"]
        if classification in COMMIT_CLASSES:
            dst = RELEASE_DIR / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            commit_files.append(rel)
        elif classification == "move_to_release_review":
            review_dst = REVIEW_DIR / rel
            review_dst.parent.mkdir(parents=True, exist_ok=True)
            if src.exists():
                shutil.copy2(src, review_dst)
            review_files.append(rel)
        else:
            excluded.append(f"{rel}: {entry['reason']}")

    return commit_files, excluded, review_files


def _copy_frozen_snapshot() -> None:
    src = ROOT / "dataset_v0.2_candidate"
    dst = RELEASE_DIR / "dataset_v0.2_candidate"
    if dst.exists():
        shutil.rmtree(dst)
    if src.exists():
        shutil.copytree(
            src,
            dst,
            ignore=shutil.ignore_patterns("checkpoint_*.json", "_debug.txt"),
        )


def _copy_package_and_docs() -> None:
    for src_rel, dst_rel in COPY_DIRS:
        src = ROOT / src_rel
        dst = RELEASE_DIR / dst_rel
        if not src.exists():
            continue
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(
            src,
            dst,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"),
        )

    for name in COPY_FILES:
        src = ROOT / name
        if not src.exists():
            continue
        dst_name = "LICENSE" if name == "LICENSE.md" else name
        shutil.copy2(src, RELEASE_DIR / dst_name)

    readme_src = ROOT / "README_RELEASE.md"
    if readme_src.exists():
        shutil.copy2(readme_src, RELEASE_DIR / "README.md")


def _build_release_manifest(summary: dict[str, Any]) -> dict[str, Any]:
    file_hashes: dict[str, str] = {}
    total_bytes = 0
    for path in sorted(RELEASE_DIR.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(RELEASE_DIR).as_posix()
        if rel.startswith(".git/"):
            continue
        file_hashes[rel] = _sha256(path)
        total_bytes += path.stat().st_size

    frozen_manifest = RELEASE_DIR / "dataset_v0.2_candidate" / "manifest.json"
    frozen_at = None
    if frozen_manifest.exists():
        frozen_at = json.loads(frozen_manifest.read_text(encoding="utf-8")).get("frozen_at")

    return {
        "dataset_version": DATASET_VERSION,
        "created_at": datetime.now(UTC).isoformat(),
        "frozen_at": frozen_at,
        "pipeline_version": "0.1.0",
        "git_commit": _git_commit(RELEASE_DIR),
        "row_counts": {name: stats["rows"] for name, stats in summary.get("tables", {}).items()},
        "file_hashes": file_hashes,
        "total_release_bytes": total_bytes,
        "source_apis": [
            {"name": "OpenAlex", "url": "https://api.openalex.org", "license": "CC0"},
            {
                "name": "OpenCitations Index",
                "url": "https://api.opencitations.net/index/v2",
                "license": "CC-BY-4.0",
            },
        ],
        "licence_status": "Code and documentation CC-BY-4.0; upstream metadata retains source licenses",
        "redistribution_status": "Processed tables and derived metadata are redistributable; raw API dumps excluded",
        "known_limitations": [
            "Collection closed; analysis-only reproduction from frozen snapshot",
            "188 HNDL works; 37 influence-decay events (below 50-event scaling gate)",
            "~80% influence-decay censoring in HNDL cohort",
            "Matched controls required for cohort comparisons",
            "Citation persistence K(t) is a proxy; not trade secret value V(t)",
            "dataset_v0.1 predates cited_doi fix and is excluded from release",
        ],
        "interpretation_policy": (
            "Do not claim trade secret value from citation metrics. "
            "Do not claim sector membership causally determines persistence."
        ),
    }


def _print_report(
    commit_files: list[str],
    excluded: list[str],
    review_files: list[str],
    manifest: dict[str, Any],
) -> None:
    total_mb = manifest["total_release_bytes"] / (1024 * 1024)
    print("\n=== Release preparation complete ===\n")
    print(f"Release directory: {RELEASE_DIR}")
    print(f"Total release size: {total_mb:.2f} MB")
    print(f"Files to commit: {len(commit_files)} (+ package/docs/frozen snapshot)")
    print(f"Files excluded: {len(excluded)}")
    print(f"Files in release_review: {len(review_files)}")

    print("\n--- Safe to commit (data audit) ---")
    for path in commit_files[:30]:
        print(f"  {path}")
    if len(commit_files) > 30:
        print(f"  ... and {len(commit_files) - 30} more")

    if excluded:
        print("\n--- Excluded ---")
        for line in excluded:
            print(f"  {line}")

    if review_files:
        print("\n--- Manual review (copied to data/release_review/) ---")
        for path in review_files:
            print(f"  {path}")

    print("\n--- Proposed git commands ---")
    print("cd knowledge-persistence-hndl")
    print("git status")
    print('git add .')
    print(f'git commit -m "Release dataset {DATASET_VERSION} for public analysis"')
    print("git remote add origin <GITHUB_URL>")
    print("git branch -M main")
    print("git push -u origin main")


def prepare_release() -> None:
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    RELEASE_DIR.mkdir(parents=True, exist_ok=True)

    audit = run_audit()
    summary = summarize()

    if RELEASE_DIR.exists():
        for child in RELEASE_DIR.iterdir():
            if child.name == ".git":
                continue
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()

    _copy_package_and_docs()
    _copy_frozen_snapshot()
    commit_files, excluded, review_files = _copy_audit_files(audit)
    _write_release_gitignore()

    manifest = _build_release_manifest(summary)
    manifest_path = RELEASE_DIR / "data" / "release" / "release_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    summary_path = RELEASE_DIR / "data" / "metadata" / "dataset_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    _print_report(commit_files, excluded, review_files, manifest)


def main() -> None:
    prepare_release()


if __name__ == "__main__":
    main()
