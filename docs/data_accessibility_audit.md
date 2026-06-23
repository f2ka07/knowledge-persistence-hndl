# Data Accessibility Audit

Generated: 2026-06-23T09:00:02.333610+00:00

## Summary

- Files scanned: 63
- Safe to commit: 41
- Large (review): 0
- Manual review: 22
- Excluded: 0

## File inventory

| Path | Type | Rows | Size (MB) | Classification | Commit? | Reason |
| --- | --- | --- | --- | --- | --- | --- |
| `data/processed/baseline_matched.parquet` | parquet | 188 | 0.020 | commit | yes | Processed analysis table suitable for redistribution |
| `data/processed/baseline_random_sample.parquet` | parquet | 188 | 0.021 | commit | yes | Processed analysis table suitable for redistribution |
| `data/processed/baseline_year_only.parquet` | parquet | 188 | 0.021 | commit | yes | Processed analysis table suitable for redistribution |
| `data/processed/citation_persistence_panel.parquet` | parquet | 3819 | 0.099 | commit | yes | Processed analysis table suitable for redistribution |
| `data/processed/citations.parquet` | parquet | 452219 | 5.629 | commit | yes | Processed analysis table suitable for redistribution |
| `data/processed/citations_by_year.parquet` | parquet | 3819 | 0.091 | commit | yes | Processed analysis table suitable for redistribution |
| `data/processed/null_model_comparison.json` | json | - | 0.001 | commit | yes | Derived analysis or provenance metadata |
| `data/processed/persistence.parquet` | parquet | 188 | 0.014 | commit | yes | Processed analysis table suitable for redistribution |
| `data/processed/threshold_sensitivity.parquet` | parquet | 6 | 0.005 | commit | yes | Processed analysis table suitable for redistribution |
| `data/processed/works.parquet` | parquet | 188 | 0.010 | commit | yes | Processed analysis table suitable for redistribution |
| `data/metadata/_debug.txt` | txt | - | 0.000 | move_to_release_review | no | Pilot or debug artifact |
| `data/metadata/checkpoint_baseline.json` | json | - | 0.001 | move_to_release_review | no | Ingestion resume checkpoint; not needed for frozen analysis |
| `data/metadata/checkpoint_baseline_matched.json` | json | - | 0.066 | move_to_release_review | no | Ingestion resume checkpoint; not needed for frozen analysis |
| `data/metadata/checkpoint_baseline_year_only.json` | json | - | 0.001 | move_to_release_review | no | Ingestion resume checkpoint; not needed for frozen analysis |
| `data/metadata/checkpoint_openalex.json` | json | - | 0.000 | move_to_release_review | no | Ingestion resume checkpoint; not needed for frozen analysis |
| `data/metadata/checkpoint_opencitations.json` | json | - | 0.000 | move_to_release_review | no | Ingestion resume checkpoint; not needed for frozen analysis |
| `data/metadata/checkpoint_opencitations_baseline.json` | json | - | 0.000 | move_to_release_review | no | Ingestion resume checkpoint; not needed for frozen analysis |
| `data/metadata/checkpoint_opencitations_baseline_matched.json` | json | - | 0.000 | move_to_release_review | no | Ingestion resume checkpoint; not needed for frozen analysis |
| `data/metadata/checkpoint_opencitations_baseline_year_only.json` | json | - | 0.000 | move_to_release_review | no | Ingestion resume checkpoint; not needed for frozen analysis |
| `data/metadata/citation_audit.json` | json | - | 0.002 | commit | yes | Derived analysis or provenance metadata |
| `data/metadata/data_accessibility_audit.json` | json | - | 0.045 | commit | yes | Derived analysis or provenance metadata |
| `data/metadata/dataset_doi_template.json` | json | - | 0.000 | commit | yes | Metadata JSON without raw API payload |
| `data/metadata/dataset_summary.json` | json | - | 0.008 | commit | yes | Metadata JSON without raw API payload |
| `data/metadata/decay_regression.json` | json | - | 0.005 | commit | yes | Derived analysis or provenance metadata |
| `data/metadata/effective_events.json` | json | - | 0.002 | commit | yes | Derived analysis or provenance metadata |
| `data/metadata/insight_pilot_summary.json` | json | - | 0.003 | move_to_release_review | no | Pilot or debug artifact |
| `data/metadata/outlier_report.json` | json | - | 0.006 | commit | yes | Metadata JSON without raw API payload |
| `data/metadata/pilot_sample.json` | json | - | 0.005 | move_to_release_review | no | Pilot or debug artifact |
| `data/metadata/provenance.json` | json | - | 0.001 | commit | yes | Derived analysis or provenance metadata |
| `data/metadata/quality_report.json` | json | - | 0.002 | commit | yes | Derived analysis or provenance metadata |
| `data/metadata/survival_preview.json` | json | - | 0.008 | commit | yes | Derived analysis or provenance metadata |
| `data/metadata/threshold_sensitivity.json` | json | - | 0.004 | commit | yes | Derived analysis or provenance metadata |
| `dataset_v0.2_candidate/manifest.json` | json | - | 0.004 | commit | yes | Derived analysis or provenance metadata |
| `dataset_v0.2_candidate/metadata/_debug.txt` | txt | - | 0.000 | move_to_release_review | no | Pilot or debug artifact |
| `dataset_v0.2_candidate/metadata/checkpoint_baseline.json` | json | - | 0.001 | move_to_release_review | no | Ingestion resume checkpoint; not needed for frozen analysis |
| `dataset_v0.2_candidate/metadata/checkpoint_baseline_matched.json` | json | - | 0.066 | move_to_release_review | no | Ingestion resume checkpoint; not needed for frozen analysis |
| `dataset_v0.2_candidate/metadata/checkpoint_baseline_year_only.json` | json | - | 0.001 | move_to_release_review | no | Ingestion resume checkpoint; not needed for frozen analysis |
| `dataset_v0.2_candidate/metadata/checkpoint_openalex.json` | json | - | 0.000 | move_to_release_review | no | Ingestion resume checkpoint; not needed for frozen analysis |
| `dataset_v0.2_candidate/metadata/checkpoint_opencitations.json` | json | - | 0.000 | move_to_release_review | no | Ingestion resume checkpoint; not needed for frozen analysis |
| `dataset_v0.2_candidate/metadata/checkpoint_opencitations_baseline.json` | json | - | 0.000 | move_to_release_review | no | Ingestion resume checkpoint; not needed for frozen analysis |
| `dataset_v0.2_candidate/metadata/checkpoint_opencitations_baseline_matched.json` | json | - | 0.000 | move_to_release_review | no | Ingestion resume checkpoint; not needed for frozen analysis |
| `dataset_v0.2_candidate/metadata/checkpoint_opencitations_baseline_year_only.json` | json | - | 0.000 | move_to_release_review | no | Ingestion resume checkpoint; not needed for frozen analysis |
| `dataset_v0.2_candidate/metadata/citation_audit.json` | json | - | 0.002 | commit | yes | Derived analysis or provenance metadata |
| `dataset_v0.2_candidate/metadata/dataset_doi_template.json` | json | - | 0.000 | commit | yes | Metadata JSON without raw API payload |
| `dataset_v0.2_candidate/metadata/decay_regression.json` | json | - | 0.005 | commit | yes | Derived analysis or provenance metadata |
| `dataset_v0.2_candidate/metadata/effective_events.json` | json | - | 0.002 | commit | yes | Derived analysis or provenance metadata |
| `dataset_v0.2_candidate/metadata/insight_pilot_summary.json` | json | - | 0.003 | move_to_release_review | no | Pilot or debug artifact |
| `dataset_v0.2_candidate/metadata/outlier_report.json` | json | - | 0.006 | commit | yes | Metadata JSON without raw API payload |
| `dataset_v0.2_candidate/metadata/pilot_sample.json` | json | - | 0.005 | move_to_release_review | no | Pilot or debug artifact |
| `dataset_v0.2_candidate/metadata/provenance.json` | json | - | 0.001 | commit | yes | Derived analysis or provenance metadata |
| `dataset_v0.2_candidate/metadata/quality_report.json` | json | - | 0.002 | commit | yes | Derived analysis or provenance metadata |
| `dataset_v0.2_candidate/metadata/survival_preview.json` | json | - | 0.008 | commit | yes | Derived analysis or provenance metadata |
| `dataset_v0.2_candidate/metadata/threshold_sensitivity.json` | json | - | 0.004 | commit | yes | Derived analysis or provenance metadata |
| `dataset_v0.2_candidate/processed/baseline_matched.parquet` | parquet | 188 | 0.020 | commit | yes | Processed analysis table suitable for redistribution |
| `dataset_v0.2_candidate/processed/baseline_random_sample.parquet` | parquet | 188 | 0.021 | commit | yes | Processed analysis table suitable for redistribution |
| `dataset_v0.2_candidate/processed/baseline_year_only.parquet` | parquet | 188 | 0.021 | commit | yes | Processed analysis table suitable for redistribution |
| `dataset_v0.2_candidate/processed/citation_persistence_panel.parquet` | parquet | 3819 | 0.099 | commit | yes | Processed analysis table suitable for redistribution |
| `dataset_v0.2_candidate/processed/citations.parquet` | parquet | 452219 | 5.629 | commit | yes | Processed analysis table suitable for redistribution |
| `dataset_v0.2_candidate/processed/citations_by_year.parquet` | parquet | 3819 | 0.091 | commit | yes | Processed analysis table suitable for redistribution |
| `dataset_v0.2_candidate/processed/null_model_comparison.json` | json | - | 0.001 | commit | yes | Derived analysis or provenance metadata |
| `dataset_v0.2_candidate/processed/persistence.parquet` | parquet | 188 | 0.014 | commit | yes | Processed analysis table suitable for redistribution |
| `dataset_v0.2_candidate/processed/threshold_sensitivity.parquet` | parquet | 6 | 0.005 | commit | yes | Processed analysis table suitable for redistribution |
| `dataset_v0.2_candidate/processed/works.parquet` | parquet | 188 | 0.010 | commit | yes | Processed analysis table suitable for redistribution |

## Flags

- `contains_copyrighted_full_text`: not detected in tabular release files
- Raw OpenAlex/OpenCitations API dumps are excluded from public release
- Citation persistence K(t) is metadata only; no full-text PDFs included
