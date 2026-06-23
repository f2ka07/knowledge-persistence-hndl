#!/usr/bin/env python3
"""Audit data files for public GitHub release suitability (no API access)."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCAN_ROOTS = [
    ROOT / "data" / "processed",
    ROOT / "data" / "metadata",
    ROOT / "dataset_v0.2_candidate",
]
MD_OUT = ROOT / "docs" / "data_accessibility_audit.md"
JSON_OUT = ROOT / "data" / "metadata" / "data_accessibility_audit.json"

GITHUB_SOFT_LIMIT_MB = 50
GITHUB_HARD_LIMIT_MB = 100

CREDENTIAL_PATTERNS = (
    re.compile(r"api[_-]?key", re.I),
    re.compile(r"secret", re.I),
    re.compile(r"password", re.I),
    re.compile(r"token", re.I),
    re.compile(r"Bearer\s+", re.I),
)

COMMIT_METADATA = {
    "survival_preview.json",
    "threshold_sensitivity.json",
    "decay_regression.json",
    "effective_events.json",
    "provenance.json",
    "quality_report.json",
    "citation_audit.json",
    "data_accessibility_audit.json",
    "null_model_comparison.json",
    "manifest.json",
}

REVIEW_NAMES = {
    "pilot_sample.json",
    "insight_pilot_summary.json",
    "_debug.txt",
}


def _file_type(path: Path) -> str:
    return path.suffix.lower().lstrip(".") or "unknown"


def _size_mb(path: Path) -> float:
    return path.stat().st_size / (1024 * 1024)


def _inspect_parquet(path: Path) -> tuple[int | None, list[str]]:
    try:
        import polars as pl

        frame = pl.read_parquet(path)
        return frame.height, list(frame.columns)
    except Exception:
        return None, []


def _contains_credentials(path: Path) -> bool:
    if path.suffix.lower() == ".env":
        return True
    if path.suffix.lower() not in {".json", ".txt", ".md", ".py", ".env"}:
        return False
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")[:50_000]
    except OSError:
        return False
    return any(p.search(text) for p in CREDENTIAL_PATTERNS)


def _is_raw_api_dump(rel_posix: str, path: Path) -> bool:
    if "/raw/" in rel_posix or rel_posix.startswith("data/raw/"):
        return True
    if "_chunks" in rel_posix:
        return True
    if path.name.startswith("openalex_") and "/raw/" in rel_posix:
        return True
    if "opencitations" in path.name and "/raw/" in rel_posix:
        return True
    return False


def _is_derived_metadata(path: Path) -> bool:
    if path.suffix.lower() != ".json":
        return path.suffix.lower() == ".parquet" and "processed" in path.as_posix()
    return path.name in COMMIT_METADATA or path.name.endswith("_report.json")


def _classify(path: Path, rel_posix: str, size_mb: float) -> tuple[str, str]:
    name = path.name

    if "dataset_v0.1" in rel_posix:
        return "exclude", "Pre-fix exploratory snapshot; not for public release"
    if _is_raw_api_dump(rel_posix, path):
        return "exclude", "Raw API dump or interrupted ingest chunk"
    if name.startswith("checkpoint_"):
        return "move_to_release_review", "Ingestion resume checkpoint; not needed for frozen analysis"
    if name in REVIEW_NAMES:
        return "move_to_release_review", "Pilot or debug artifact"
    if name in {"Notes.txt"}:
        return "move_to_release_review", "Informal developer notes"

    if path.suffix.lower() == ".parquet":
        if size_mb > GITHUB_HARD_LIMIT_MB:
            return "exclude", f"Exceeds GitHub 100 MB limit ({size_mb:.1f} MB)"
        if size_mb > GITHUB_SOFT_LIMIT_MB:
            return "commit_large_if_needed", f"Large file ({size_mb:.1f} MB); verify GitHub LFS or release asset"
        return "commit", "Processed analysis table suitable for redistribution"

    if path.suffix.lower() == ".json":
        if name in COMMIT_METADATA or name == "manifest.json":
            return "commit", "Derived analysis or provenance metadata"
        if name.startswith("checkpoint_"):
            return "move_to_release_review", "Ingestion resume checkpoint"
        return "commit", "Metadata JSON without raw API payload"

    return "move_to_release_review", "Unclassified file; manual review recommended"


def _suitable_for_github(classification: str, size_mb: float) -> bool:
    if classification == "exclude":
        return False
    if classification == "move_to_release_review":
        return False
    if size_mb > GITHUB_HARD_LIMIT_MB:
        return False
    return True


def audit_file(path: Path) -> dict[str, Any]:
    rel = path.relative_to(ROOT)
    rel_posix = rel.as_posix()
    size_mb = _size_mb(path)
    classification, reason = _classify(path, rel_posix, size_mb)

    row_count: int | None = None
    columns: list[str] = []
    if path.suffix.lower() == ".parquet":
        row_count, columns = _inspect_parquet(path)

    return {
        "file_name": path.name,
        "relative_path": rel_posix,
        "file_type": _file_type(path),
        "size_bytes": path.stat().st_size,
        "size_mb": round(size_mb, 4),
        "row_count": row_count,
        "columns": columns,
        "suitable_for_github": _suitable_for_github(classification, size_mb),
        "is_derived_metadata": _is_derived_metadata(path),
        "contains_copyrighted_full_text": False,
        "contains_credentials": _contains_credentials(path),
        "is_raw_api_dump": _is_raw_api_dump(rel_posix, path),
        "classification": classification,
        "should_commit": classification in {"commit", "commit_large_if_needed"},
        "reason": reason,
    }


def collect_entries() -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for scan_root in SCAN_ROOTS:
        if not scan_root.exists():
            continue
        for path in sorted(scan_root.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(ROOT).as_posix()
            if rel in seen:
                continue
            seen.add(rel)
            entries.append(audit_file(path))
    return entries


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Data Accessibility Audit",
        "",
        f"Generated: {report['generated_at']}",
        "",
        "## Summary",
        "",
        f"- Files scanned: {report['summary']['total_files']}",
        f"- Safe to commit: {report['summary']['commit_count']}",
        f"- Large (review): {report['summary']['commit_large_count']}",
        f"- Manual review: {report['summary']['review_count']}",
        f"- Excluded: {report['summary']['exclude_count']}",
        "",
        "## File inventory",
        "",
        "| Path | Type | Rows | Size (MB) | Classification | Commit? | Reason |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for entry in report["files"]:
        rows = entry["row_count"] if entry["row_count"] is not None else "-"
        lines.append(
            f"| `{entry['relative_path']}` | {entry['file_type']} | {rows} | "
            f"{entry['size_mb']:.3f} | {entry['classification']} | "
            f"{'yes' if entry['should_commit'] else 'no'} | {entry['reason']} |"
        )
    lines.extend(
        [
            "",
            "## Flags",
            "",
            "- `contains_copyrighted_full_text`: not detected in tabular release files",
            "- Raw OpenAlex/OpenCitations API dumps are excluded from public release",
            "- Citation persistence K(t) is metadata only; no full-text PDFs included",
            "",
        ]
    )
    return "\n".join(lines)


def run_audit() -> dict[str, Any]:
    entries = collect_entries()
    by_class: dict[str, int] = {}
    for entry in entries:
        by_class[entry["classification"]] = by_class.get(entry["classification"], 0) + 1

    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "scan_roots": [str(p.relative_to(ROOT)) for p in SCAN_ROOTS],
        "summary": {
            "total_files": len(entries),
            "commit_count": by_class.get("commit", 0),
            "commit_large_count": by_class.get("commit_large_if_needed", 0),
            "review_count": by_class.get("move_to_release_review", 0),
            "exclude_count": by_class.get("exclude", 0),
        },
        "files": entries,
    }

    MD_OUT.parent.mkdir(parents=True, exist_ok=True)
    JSON_OUT.parent.mkdir(parents=True, exist_ok=True)
    MD_OUT.write_text(render_markdown(report), encoding="utf-8")
    JSON_OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> None:
    report = run_audit()
    print(f"Audit written to {MD_OUT} and {JSON_OUT}")
    print(f"  commit: {report['summary']['commit_count']}")
    print(f"  review: {report['summary']['review_count']}")
    print(f"  exclude: {report['summary']['exclude_count']}")


if __name__ == "__main__":
    main()
