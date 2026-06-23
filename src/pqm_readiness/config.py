"""Pipeline configuration and path management."""

from __future__ import annotations

from pathlib import Path
from typing import Self

from pydantic import BaseModel, Field


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


from pqm_readiness.concept_groups import resolve_concept_groups


class PipelineConfig(BaseModel):
    """Runtime configuration for the dataset pipeline."""

    root: Path = Field(default_factory=project_root)
    data_dir: Path | None = None
    limit: int | None = Field(default=None, ge=1, description="Max works to ingest")
    limit_per_group: int | None = Field(
        default=None,
        ge=1,
        description="Max works per concept group when using stratified sampling",
    )
    publication_year_min: int = 2005
    publication_year_max: int = 2018
    concept_id: str = "C41008148"  # Used when stratified sampling is disabled
    concept_groups: list[str] | None = Field(
        default=None,
        description="Named HNDL concept groups; None enables all groups",
    )
    use_concept_groups: bool = True
    min_cited_by_count: int = 30
    max_cited_by_count: int | None = Field(
        default=1000,
        description="Skip works above this OpenAlex cited_by_count during enrichment",
    )
    max_citations_per_doi: int = Field(
        default=5000,
        ge=1,
        description="Cap incoming citation edges stored per DOI",
    )
    per_page: int = Field(default=100, ge=1, le=100)
    requests_per_second: float = Field(default=5.0, gt=0)
    mailto: str = "pqm-readiness@example.org"
    resume: bool = True
    enable_baseline: bool = True
    enable_patent_enrichment: bool = True
    seed: int = 42

    @property
    def base_data_dir(self) -> Path:
        return self.data_dir or (self.root / "data")

    @property
    def raw_dir(self) -> Path:
        return self.base_data_dir / "raw"

    @property
    def intermediate_dir(self) -> Path:
        return self.base_data_dir / "intermediate"

    @property
    def processed_dir(self) -> Path:
        return self.base_data_dir / "processed"

    @property
    def metadata_dir(self) -> Path:
        return self.base_data_dir / "metadata"

    @property
    def docs_dir(self) -> Path:
        return self.root / "docs"

    @property
    def openalex_filter(self) -> str:
        return self.openalex_filter_for_concept(self.concept_id)

    def openalex_filter_for_concept(self, concept_id: str) -> str:
        if self.max_cited_by_count is None:
            citation_filter = f"cited_by_count:>{self.min_cited_by_count}"
        else:
            citation_filter = (
                f"cited_by_count:{self.min_cited_by_count}-{self.max_cited_by_count}"
            )
        return (
            f"publication_year:{self.publication_year_min}-{self.publication_year_max},"
            f"concepts.id:{concept_id},"
            f"{citation_filter},"
            "has_doi:true"
        )

    @property
    def selected_concept_groups(self):
        if not self.use_concept_groups:
            return []
        return resolve_concept_groups(self.concept_groups)

    @property
    def observation_year(self) -> int:
        from datetime import UTC, datetime

        return datetime.now(UTC).year

    @property
    def openalex_select(self) -> str:
        return (
            "id,doi,publication_year,cited_by_count,referenced_works,"
            "authorships,primary_location,concepts"
        )

    def ensure_dirs(self) -> Self:
        for path in (
            self.raw_dir,
            self.intermediate_dir,
            self.processed_dir,
            self.metadata_dir,
            self.docs_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)
        return self

    def checkpoint_path(self, stage: str) -> Path:
        return self.metadata_dir / f"checkpoint_{stage}.json"

    def provenance_path(self) -> Path:
        return self.metadata_dir / "provenance.json"

    def reset_run_artifacts(self) -> None:
        """Remove prior run outputs so a fresh execution does not append stale data."""
        patterns = (
            self.raw_dir.glob("*.parquet"),
            self.processed_dir.glob("*.parquet"),
            self.metadata_dir.glob("checkpoint_*.json"),
            [self.metadata_dir / "quality_report.json"],
            [self.metadata_dir / "citation_audit.json"],
            [self.metadata_dir / "null_model_comparison.json"],
            [self.metadata_dir / "threshold_sensitivity.json"],
            [self.metadata_dir / "decay_regression.json"],
            [self.processed_dir / "threshold_sensitivity.parquet"],
        )
        for pattern in patterns:
            for path in pattern:
                if path.exists():
                    path.unlink()
