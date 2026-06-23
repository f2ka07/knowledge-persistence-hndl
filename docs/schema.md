# Schema

## works.parquet
| column | type | source |
| --- | --- | --- |
| work_id | string | OpenAlex `id` |
| doi | string | OpenAlex `doi` |
| year | int | OpenAlex `publication_year` |
| concept | string | OpenAlex top-scoring `concepts.display_name` |
| concept_group | string | HNDL sector from OpenAlex `concepts.id` filter |
| classification_source | string | `openalex_concepts.id_filter` |
| classification_confidence | float | OpenAlex concept score for matched sector |
| citation_count | int | OpenAlex `cited_by_count` |
| institution_count | int | derived from `authorships.institutions` |

## citations.parquet
| column | type | source |
| --- | --- | --- |
| source_doi | string | OpenCitations incoming `citing` |
| target_doi | string | OpenCitations incoming `cited` |
| citation_creation_date | string | OpenCitations `creation` |
| citation_lag_years | float | citation_year - publication_year |

## citations_by_year.parquet
| column | type | source |
| --- | --- | --- |
| work_id | string | OpenAlex `work_id` |
| doi | string | OpenAlex `doi` |
| concept_group | string | HNDL sector label |
| publication_year | int | work publication year |
| citation_year | int | year of incoming citation |
| age_years | int | citation_year - publication_year |
| annual_citations | int | count of incoming citations in year |
| cumulative_citations | int | running sum by work |
| normalized_annual_citations | float | annual / max annual for work |
| normalized_cumulative_citations | float | cumulative / total for work |
| expected_citations_at_age | float | mean annual citations for field at age |
| normalized_citation_rate | float | annual / expected(field, age) |
| field_percentile | float | percentile within field at age |
| year_percentile | float | percentile within publication year at age |

## persistence.parquet
| column | type | source |
| --- | --- | --- |
| work_id | string | OpenAlex `work_id` |
| publication_year | int | work publication year |
| last_observed_year | int | latest incoming citation year in window |
| observed_window_years | float | last_observed_year - publication_year |
| first_citation_year | int | earliest incoming citation year |
| last_citation_year | int | latest incoming citation year |
| citation_lifespan_years | float | last - first citation year |
| peak_citation_year | int | year with max annual citations |
| peak_age_years | float | age at peak annual citations |
| estimated_half_life_years | float | age when cumulative reaches 50% |
| half_life_censored | bool | true if right-censored or 50% not reached |
| decay_start_year | int | first year after peak with lower annual count |
| post_peak_decay_rate | float | slope of annual counts after peak |
| long_tail_indicator | bool | citations 5+ years after peak |
| censoring_flag | bool | still cited at observation window end |
| decay_event_year | int | calendar year influence decay detected |
| decay_threshold | float | 0.1 * peak annual citation rate |
| time_to_decay_years | float | age at decay event or last observed age |
| influence_decay_event | bool | true if decay rule triggered |
| influence_decay_censored | bool | true if no decay by observation end |

## baseline_random_sample.parquet
Null-model cohort matched on publication year with random non-HNDL concepts. Schema matches `persistence.parquet`.

## baseline_year_only.parquet
Null-model cohort matched on publication year and DOI only (no citation band). Schema matches `persistence.parquet`.

## baseline_matched.parquet
Fully matched null-model cohort (year, citation band, concept depth, source type). Schema matches `persistence.parquet`.

## threshold_sensitivity.parquet
| column | type | description |
| --- | --- | --- |
| threshold_ratio | float | peak fraction threshold (e.g. 0.1 = 10%) |
| consecutive_years | int | required consecutive low-rate years |
| event_count | int | HNDL influence-decay events at this setting |
| censoring_rate | float | HNDL censoring share |
| median_time_to_decay | float | KM median (nullable) |
| logrank_p | float | HNDL vs fully matched log-rank p-value |
| cox_hr | float | Cox hazard ratio (HNDL indicator) |
| logrank_p_matched | float | same as logrank_p |
| cox_hr_matched | float | same as cox_hr |
| matched_event_count | int | matched cohort events |
| matched_censoring_rate | float | matched cohort censoring |
| logrank_p_random | float | HNDL vs random baseline |
| logrank_p_year_only | float | HNDL vs year-only baseline |

## patent_mentions.parquet
| column | type | source |
| --- | --- | --- |
| doi | string | work DOI |
| patent_mentions | int | Crossref Event Data (cambia-lens) |
| source | string | cambia-lens |
| enrichment_status | string | ok or unavailable |

## citation_persistence_panel.parquet
| column | type | source |
| --- | --- | --- |
| work_id | string | OpenAlex `work_id` |
| concept_group | string | HNDL sector label |
| age_years | int | years since publication |
| observed_citation_rate | float | normalized annual citation rate |
| cumulative_citation_share | float | normalized cumulative share |
| normalized_citation_rate | float | annual / expected(field, age) |
| field_percentile | float | field percentile at age |
| year_percentile | float | publication-year percentile at age |
| citation_share_remaining | float | 1 - cumulative share |
| censoring_flag | bool | right-censoring indicator |
