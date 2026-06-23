# Knowledge Persistence (HNDL) Dataset

Open citation-based dataset for studying **long-horizon technical information persistence** relevant to harvest-now-decrypt-later (HNDL) and post-quantum cryptography (PQC) risk modelling.

**Frozen release:** `dataset_v0.2_candidate` (collection closed; analysis only).

## What this dataset measures

We operationalise persistence as **citation-stream influence over time**, not as direct economic or cryptographic value:

- **K(t)** — observable citation persistence and influence decay from OpenAlex metadata + OpenCitations edges
- **Influence decay event** — annual citation rate falls below 10% of peak for 3 consecutive years (see `docs/provenance.md`)

## What this dataset does NOT measure

- **V(t)** — trade secret value, classified capability, or adversary utility
- Causal effects of sector membership on persistence (requires matched controls and careful interpretation)
- Full-text content of publications (metadata and citation edges only)

> **Warning:** Citation persistence is a proxy K(t). It does not equal trade secret value V(t).

## Repository layout

```
dataset_v0.2_candidate/   # Frozen snapshot (canonical for analysis)
data/processed/           # Analysis-ready parquet tables
data/metadata/            # Survival, threshold sensitivity, provenance JSON
analysis/                 # Jupyter notebooks (no API required)
src/pqm_readiness/        # Python package (analysis commands)
docs/                     # Schema, provenance, interpretation policy
```

## Quick start (analysis only)

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -e ".[dev,analysis]"
jupyter notebook analysis/
```

Re-run packaged analysis on local files:

```bash
python -m pqm_readiness threshold-sensitivity
python -m pqm_readiness fit-decay-regression
python -m pqm_readiness fit-survival-preview
```

No API keys required. **Do not run ingestion** for public reproduction; use the frozen snapshot.

## Key findings (v0.2_candidate)

- **188** HNDL works (1995–2012 window, stratified concept groups)
- **37** influence-decay events in HNDL cohort (~80% censored)
- Three-tier baseline decomposition: random significant → year-only significant → **fully matched neutral**
- Threshold sensitivity: **10–15% / 3-year rule stable** for tier-C conclusions

See `data/metadata/survival_preview.json` and `data/metadata/threshold_sensitivity.json`.

## Reproduce release packaging

From the development workspace (parent repo):

```bash
python scripts/audit_data_accessibility.py
python scripts/summarize_dataset.py
python scripts/prepare_release.py
```

## Documentation

| Document | Description |
| --- | --- |
| [dataset_card.md](dataset_card.md) | Dataset card for archivists and reviewers |
| [docs/schema.md](docs/schema.md) | Table and column reference |
| [docs/provenance.md](docs/provenance.md) | Sources, matching, transforms |
| [docs/interpretation_policy.md](docs/interpretation_policy.md) | Claims policy |
| [docs/reproducibility.md](docs/reproducibility.md) | Analysis reproduction steps |
| [docs/data_accessibility_audit.md](docs/data_accessibility_audit.md) | File-level release audit |

## Citation

See [CITATION.cff](CITATION.cff). Suggested BibTeX:

```bibtex
@dataset{knowledge_persistence_hndl_2026,
  title  = {Knowledge Persistence (HNDL) Citation Dataset},
  version = {0.2.0},
  year   = {2026},
  license = {CC-BY-4.0}
}
```

## License

Code and documentation: **CC-BY-4.0**. Upstream metadata retains OpenAlex (CC0) and OpenCitations (CC-BY-4.0) terms.
