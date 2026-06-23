"""Stratum keys for citation-count matched baseline sampling."""

from __future__ import annotations

import json
from typing import Any

from pqm_readiness.models import (
    citation_count_band,
    extract_doi,
    extract_source_type,
    max_concept_level,
)


def match_stratum_from_row(row: dict[str, Any]) -> dict[str, Any]:
    """Build matching stratum from a normalized OpenAlex work row."""
    concepts = json.loads(row.get("concepts_json") or "[]")
    location = json.loads(row.get("primary_location") or "{}")
    cite_lo, cite_hi = citation_count_band(int(row.get("citation_count") or 0))
    return {
        "year": int(row["year"]),
        "citation_band_lo": cite_lo,
        "citation_band_hi": cite_hi,
        "concept_depth": max_concept_level(concepts),
        "source_type": extract_source_type(location),
    }


def stratum_key(stratum: dict[str, Any]) -> tuple[Any, ...]:
    return (
        stratum["year"],
        stratum["citation_band_lo"],
        stratum["citation_band_hi"],
        stratum["concept_depth"],
        stratum["source_type"],
    )


def openalex_filter_for_stratum(stratum: dict[str, Any]) -> str:
    return (
        f"publication_year:{stratum['year']},"
        f"cited_by_count:{stratum['citation_band_lo']}-{stratum['citation_band_hi']},"
        "has_doi:true"
    )


def openalex_filter_for_year_stratum(
    stratum: dict[str, Any],
    *,
    min_cited_by_count: int = 30,
    max_cited_by_count: int | None = 1000,
) -> str:
    """OpenAlex filter for year+DOI matching without citation-count bands."""
    if max_cited_by_count is None:
        citation_filter = f"cited_by_count:>{min_cited_by_count}"
    else:
        citation_filter = f"cited_by_count:{min_cited_by_count}-{max_cited_by_count}"
    return f"publication_year:{stratum['year']},{citation_filter},has_doi:true"


def year_stratum_from_row(row: dict[str, Any]) -> dict[str, Any]:
    return {"year": int(row["year"])}


def year_stratum_key(stratum: dict[str, Any]) -> tuple[Any, ...]:
    return (stratum["year"],)


def candidate_matches_year_stratum(raw: dict[str, Any], stratum: dict[str, Any]) -> bool:
    if raw.get("publication_year") != stratum["year"]:
        return False
    return extract_doi(raw.get("doi")) is not None


def candidate_matches_stratum(
    raw: dict[str, Any],
    stratum: dict[str, Any],
    *,
    relax_source_type: bool = False,
    relax_concept_depth: bool = False,
) -> bool:
    concepts = raw.get("concepts") or []
    location = raw.get("primary_location") or {}
    depth = max_concept_level(concepts)
    source_type = extract_source_type(location)

    if raw.get("publication_year") != stratum["year"]:
        return False
    cited_by = int(raw.get("cited_by_count") or 0)
    if cited_by < stratum["citation_band_lo"] or cited_by > stratum["citation_band_hi"]:
        return False
    if not extract_doi(raw.get("doi")):
        return False

    if not relax_concept_depth and depth != stratum["concept_depth"]:
        return False
    if relax_concept_depth and abs(depth - stratum["concept_depth"]) > 1:
        return False

    if not relax_source_type and source_type != stratum["source_type"]:
        return False
    return True
