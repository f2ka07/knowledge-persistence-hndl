"""Shared schema models and parsing helpers."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

DOI_PATTERN = re.compile(r"doi:([^\s]+)", re.IGNORECASE)


def extract_openalex_id(url_or_id: str | None) -> str | None:
    if not url_or_id:
        return None
    if url_or_id.startswith("https://openalex.org/"):
        return url_or_id.rsplit("/", 1)[-1]
    return url_or_id


def extract_doi(value: str | None) -> str | None:
    if not value:
        return None
    if value.startswith("https://doi.org/"):
        return value.removeprefix("https://doi.org/")
    match = DOI_PATTERN.search(value)
    if match:
        return match.group(1)
    if value.startswith("10."):
        return value
    return None


def parse_year(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(value[:4])
    except ValueError:
        return None


def primary_concept(concepts: list[dict[str, Any]] | None) -> str | None:
    if not concepts:
        return None
    ranked = sorted(concepts, key=lambda c: c.get("score") or 0.0, reverse=True)
    return ranked[0].get("display_name")


def citation_count_band(count: int, *, min_count: int = 30, max_count: int = 1000) -> tuple[int, int]:
    """Return inclusive OpenAlex cited_by_count band for matched controls."""
    width = 50 if count < 200 else 100
    lo = (count // width) * width
    hi = lo + width - 1
    return max(lo, min_count), min(hi, max_count)


def max_concept_level(concepts: list[dict[str, Any]] | None) -> int:
    if not concepts:
        return 0
    return max(int(c.get("level") or 0) for c in concepts)


def extract_source_type(primary_location: dict[str, Any] | None) -> str:
    if not primary_location:
        return "unknown"
    return str(primary_location.get("raw_type") or "unknown")


def institution_count(authorships: list[dict[str, Any]] | None) -> int:
    if not authorships:
        return 0
    institutions: set[str] = set()
    for authorship in authorships:
        for institution in authorship.get("institutions") or []:
            inst_id = institution.get("id")
            if inst_id:
                institutions.add(inst_id)
    return len(institutions)


class WorkRecord(BaseModel):
    work_id: str
    doi: str | None = None
    year: int | None = None
    concept: str | None = None
    citation_count: int = 0
    institution_count: int = 0
    referenced_work_count: int = 0
    source: str = "openalex"


class CitationRecord(BaseModel):
    source_doi: str
    target_doi: str
    citation_creation_date: str | None = None
    citation_lag_years: float | None = None
    oci: str | None = None
    source_api: str = "opencitations_index_v2"


class PersistenceRecord(BaseModel):
    entity_id: str
    first_year: int | None = None
    last_citation_year: int | None = None
    lifespan_years: float | None = None
    citation_half_life: float | None = None
