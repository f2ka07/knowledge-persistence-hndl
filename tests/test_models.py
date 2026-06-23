"""Unit tests for parsing and schema helpers."""

from pqm_readiness.models import (
    citation_count_band,
    extract_doi,
    extract_openalex_id,
    institution_count,
    max_concept_level,
    primary_concept,
)


def test_citation_count_band() -> None:
    assert citation_count_band(45) == (30, 49)
    assert citation_count_band(997) == (900, 999)


def test_max_concept_level() -> None:
    concepts = [{"level": 2}, {"level": 4}]
    assert max_concept_level(concepts) == 4
    assert max_concept_level([]) == 0


def test_extract_openalex_id() -> None:
    assert extract_openalex_id("https://openalex.org/W123") == "W123"


def test_extract_doi_from_url() -> None:
    assert extract_doi("https://doi.org/10.1038/nature12373") == "10.1038/nature12373"


def test_extract_doi_from_opencitations_blob() -> None:
    blob = "omid:br/06803059652 doi:10.1103/physrevapplied.15.034031 openalex:W3083541403"
    assert extract_doi(blob) == "10.1103/physrevapplied.15.034031"


def test_primary_concept() -> None:
    concepts = [
        {"display_name": "Physics", "score": 0.2},
        {"display_name": "Computer science", "score": 0.9},
    ]
    assert primary_concept(concepts) == "Computer science"


def test_normalize_citation_uses_query_target() -> None:
    from pqm_readiness.ingest.opencitations import _normalize_citation

    row = _normalize_citation(
        "10.1038/nature12373",
        {
            "citing": "omid:br/123 doi:10.1103/physrevapplied.15.034031",
            "cited": "omid:br/456 doi:10.9999/wrong",
            "creation": "2014-01-01",
            "oci": "oci-1",
        },
    )
    assert row is not None
    assert row["cited_doi"] == "10.1038/nature12373"
    assert row["citing_doi"] == "10.1103/physrevapplied.15.034031"


def test_institution_count_unique() -> None:
    authorships = [
        {
            "institutions": [
                {"id": "https://openalex.org/I1"},
                {"id": "https://openalex.org/I2"},
            ]
        },
        {"institutions": [{"id": "https://openalex.org/I1"}]},
    ]
    assert institution_count(authorships) == 2
