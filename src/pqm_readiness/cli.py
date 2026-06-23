"""Command-line interface."""

from __future__ import annotations

from typing import Annotated, Optional

import typer
from loguru import logger
from rich.console import Console

from pqm_readiness.config import PipelineConfig
from pqm_readiness.pipeline import run_pipeline

app = typer.Typer(help="PQM Readiness dataset pipeline")
console = Console()


def _configure_logging(verbose: bool) -> None:
    logger.remove()
    level = "DEBUG" if verbose else "INFO"
    logger.add(lambda msg: console.print(msg, end=""), level=level)


def _build_config(
    *,
    limit: int | None,
    limit_per_group: int | None,
    data_dir: str | None,
    no_resume: bool,
    year_min: int,
    year_max: int,
    concept_id: str,
    min_citations: int,
    max_citations: int | None,
    max_citations_per_doi: int,
    mailto: str,
    use_concept_groups: bool,
    enable_baseline: bool = True,
    enable_patent_enrichment: bool = True,
) -> PipelineConfig:
    return PipelineConfig(
        limit=limit,
        limit_per_group=limit_per_group,
        data_dir=data_dir,
        publication_year_min=year_min,
        publication_year_max=year_max,
        concept_id=concept_id,
        min_cited_by_count=min_citations,
        max_cited_by_count=max_citations,
        max_citations_per_doi=max_citations_per_doi,
        mailto=mailto,
        resume=not no_resume,
        use_concept_groups=use_concept_groups,
        enable_baseline=enable_baseline,
        enable_patent_enrichment=enable_patent_enrichment,
    )


@app.command()
def run(
    limit: Annotated[
        Optional[int],
        typer.Option("--limit", "-n", help="Maximum number of works to ingest"),
    ] = None,
    limit_per_group: Annotated[
        Optional[int],
        typer.Option("--limit-per-group", help="Works per HNDL concept group"),
    ] = None,
    data_dir: Annotated[
        Optional[str],
        typer.Option("--data-dir", help="Override data directory"),
    ] = None,
    no_resume: Annotated[
        bool,
        typer.Option("--no-resume", help="Ignore checkpoints and start fresh"),
    ] = False,
    year_min: Annotated[int, typer.Option("--year-min")] = 2005,
    year_max: Annotated[int, typer.Option("--year-max")] = 2018,
    concept_id: Annotated[str, typer.Option("--concept-id")] = "C41008148",
    min_citations: Annotated[int, typer.Option("--min-citations")] = 30,
    max_citations: Annotated[
        Optional[int], typer.Option("--max-citations", help="Max OpenAlex cited_by_count")
    ] = 1000,
    max_citations_per_doi: Annotated[
        int, typer.Option("--max-citations-per-doi", help="Cap OpenCitations edges per DOI")
    ] = 5000,
    mailto: Annotated[str, typer.Option("--mailto")] = "pqm-readiness@example.org",
    single_concept: Annotated[
        bool, typer.Option("--single-concept", help="Disable stratified concept-group sampling")
    ] = False,
    skip_patents: Annotated[
        bool, typer.Option("--skip-patents", help="Skip patent mention enrichment (faster)")
    ] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    """Run the full dataset pipeline."""
    _configure_logging(verbose)
    config = _build_config(
        limit=limit,
        limit_per_group=limit_per_group,
        data_dir=data_dir,
        no_resume=no_resume,
        year_min=year_min,
        year_max=year_max,
        concept_id=concept_id,
        min_citations=min_citations,
        max_citations=max_citations,
        max_citations_per_doi=max_citations_per_doi,
        mailto=mailto,
        use_concept_groups=not single_concept,
        enable_patent_enrichment=not skip_patents,
    )
    run_pipeline(config)


@app.command("insight-pilot")
def insight_pilot_cmd(
    limit_per_group: Annotated[
        int, typer.Option("--limit-per-group", help="Works per HNDL sector")
    ] = 1,
    no_resume: Annotated[bool, typer.Option("--no-resume")] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    """Quick stratified pilot across HNDL sectors (default: 1 work x 8 groups)."""
    _configure_logging(verbose)
    config = _build_config(
        limit=None,
        limit_per_group=limit_per_group,
        data_dir=None,
        no_resume=True,
        year_min=2005,
        year_max=2018,
        concept_id="C41008148",
        min_citations=30,
        max_citations=1000,
        max_citations_per_doi=5000,
        mailto="pqm-readiness@example.org",
        use_concept_groups=True,
    )
    run_pipeline(config)


@app.command("ingest-openalex")
def ingest_openalex_cmd(
    limit: Annotated[Optional[int], typer.Option("--limit", "-n")] = None,
    no_resume: Annotated[bool, typer.Option("--no-resume")] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    """Run only OpenAlex ingestion."""
    _configure_logging(verbose)
    from pqm_readiness.ingest.openalex import ingest_openalex

    config = PipelineConfig(limit=limit, resume=not no_resume)
    ingest_openalex(config)


@app.command("audit-citations")
def audit_citations_cmd(verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False) -> None:
    """Audit citation edge density, duplication, and directionality."""
    _configure_logging(verbose)
    from pqm_readiness.validate.audit_citations import audit_citations

    audit_citations(PipelineConfig())


@app.command("validate")
def validate_cmd(verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False) -> None:
    """Validate processed tables and emit quality report."""
    _configure_logging(verbose)
    config = PipelineConfig()
    from pqm_readiness.validate.quality import validate_dataset

    validate_dataset(config)


@app.command("inspect-outliers")
def inspect_outliers_cmd(
    top_n: Annotated[int, typer.Option("--top-n")] = 20,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    """Inspect citation-volume outliers before scaling."""
    _configure_logging(verbose)
    from pqm_readiness.validate.inspect_outliers import inspect_outliers

    inspect_outliers(PipelineConfig(), top_n=top_n)


@app.command("build-year-baseline")
def build_year_baseline_cmd(
    no_resume: Annotated[bool, typer.Option("--no-resume")] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    """Ingest year+DOI matched baseline (no citation-count matching)."""
    _configure_logging(verbose)
    from pqm_readiness.ingest.baseline import ingest_baseline_year_only
    from pqm_readiness.ingest.opencitations import ingest_opencitations
    from pqm_readiness.transform.baseline import (
        build_baseline_year_only_sample,
        build_null_model_comparison,
    )

    config = PipelineConfig(resume=not no_resume)
    config.ensure_dirs()
    openalex_path = config.raw_dir / "openalex_works.parquet"
    if not openalex_path.exists():
        raise typer.BadParameter("Missing data/raw/openalex_works.parquet; run pipeline first.")

    year_path = ingest_baseline_year_only(config, openalex_path)
    year_oc_path = config.raw_dir / "baseline_year_only_opencitations_citations.parquet"
    if year_path.exists():
        ingest_opencitations(
            config,
            year_path,
            output_name="baseline_year_only_opencitations_citations.parquet",
            checkpoint_stage="opencitations_baseline_year_only",
        )
        build_baseline_year_only_sample(
            year_path,
            year_oc_path,
            config.processed_dir,
            config.observation_year,
        )
        build_null_model_comparison(
            config.processed_dir / "persistence.parquet",
            config.processed_dir / "baseline_year_only.parquet",
            config.processed_dir,
            config.processed_dir / "citation_persistence_panel.parquet",
            baseline_label="baseline_year_only",
        )


@app.command("rebuild-persistence")
def rebuild_persistence_cmd(verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False) -> None:
    """Recompute persistence tables with influence-decay fields (no API)."""
    _configure_logging(verbose)
    from pqm_readiness.analysis.rebuild_persistence import rebuild_persistence

    rebuild_persistence(PipelineConfig())


@app.command("count-events")
def count_events_cmd(
    min_events: Annotated[int, typer.Option("--min-events")] = 50,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    """Count influence-decay and citation-stop events; assess scaling readiness."""
    _configure_logging(verbose)
    from pqm_readiness.analysis.count_events import count_effective_events

    count_effective_events(PipelineConfig(), min_events=min_events)


@app.command("build-matched-baseline")
def build_matched_baseline_cmd(
    no_resume: Annotated[bool, typer.Option("--no-resume")] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    """Ingest citation-count matched baseline and rebuild processed tables."""
    _configure_logging(verbose)
    from pqm_readiness.analysis.survival_preview import fit_survival_preview
    from pqm_readiness.ingest.baseline import ingest_baseline_matched
    from pqm_readiness.ingest.opencitations import ingest_opencitations
    from pqm_readiness.transform.baseline import (
        build_baseline_matched_sample,
        build_null_model_comparison,
    )

    config = PipelineConfig(resume=not no_resume)
    config.ensure_dirs()
    openalex_path = config.raw_dir / "openalex_works.parquet"
    if not openalex_path.exists():
        raise typer.BadParameter("Missing data/raw/openalex_works.parquet; run pipeline first.")

    matched_path = ingest_baseline_matched(config, openalex_path)
    matched_oc_path = config.raw_dir / "baseline_matched_opencitations_citations.parquet"
    if matched_path.exists():
        ingest_opencitations(
            config,
            matched_path,
            output_name="baseline_matched_opencitations_citations.parquet",
            checkpoint_stage="opencitations_baseline_matched",
        )
        build_baseline_matched_sample(
            matched_path,
            matched_oc_path,
            config.processed_dir,
            config.observation_year,
        )
        build_null_model_comparison(
            config.processed_dir / "persistence.parquet",
            config.processed_dir / "baseline_matched.parquet",
            config.processed_dir,
            config.processed_dir / "citation_persistence_panel.parquet",
            baseline_label="baseline_matched",
        )
    fit_survival_preview(config)


@app.command("fit-survival-preview")
def fit_survival_preview_cmd(verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False) -> None:
    """Kaplan-Meier / log-rank / Cox / Weibull preview (no median interpretation)."""
    _configure_logging(verbose)
    from pqm_readiness.analysis.survival_preview import fit_survival_preview

    fit_survival_preview(PipelineConfig())


@app.command("threshold-sensitivity")
def threshold_sensitivity_cmd(verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False) -> None:
    """Grid stability analysis for influence-decay threshold parameters (no API)."""
    _configure_logging(verbose)
    from pqm_readiness.analysis.threshold_sensitivity import run_threshold_sensitivity

    run_threshold_sensitivity(PipelineConfig())


@app.command("fit-decay-regression")
def fit_decay_regression_cmd(verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False) -> None:
    """AFT Weibull and quantile regression for HNDL time-to-decay (no API)."""
    _configure_logging(verbose)
    from pqm_readiness.analysis.decay_regression import fit_decay_regression

    fit_decay_regression(PipelineConfig())


@app.command("enter-analysis-phase")
def enter_analysis_phase_cmd(
    version: Annotated[str, typer.Option("--version")] = "v0.2_candidate",
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    """Run threshold sensitivity, decay regression, then freeze (no ingestion)."""
    _configure_logging(verbose)
    from pqm_readiness.analysis.decay_regression import fit_decay_regression
    from pqm_readiness.analysis.threshold_sensitivity import run_threshold_sensitivity
    from pqm_readiness.export.freeze import freeze_dataset

    config = PipelineConfig()
    run_threshold_sensitivity(config)
    fit_decay_regression(config)
    freeze_dataset(config, version=version)


@app.command("freeze-dataset")
def freeze_dataset_cmd(
    version: Annotated[str, typer.Option("--version")] = "v0.1",
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    """Freeze current processed outputs with manifest (e.g. v0.2_candidate)."""
    _configure_logging(verbose)
    from pqm_readiness.export.freeze import freeze_dataset

    freeze_dataset(PipelineConfig(), version=version)


if __name__ == "__main__":
    app()
