# Reproducibility

## Analysis-phase reproduction (public release)

Collection is **closed**. Reproduce analysis from the frozen `dataset_v0.2_candidate` snapshot without API access.

### 1. Install

```bash
python -m venv .venv
source .venv/bin/activate   # Linux/macOS
# .venv\Scripts\activate    # Windows
pip install -e ".[dev,analysis]"
```

### 2. Verify frozen snapshot

```bash
# Compare file hashes to manifest
python -c "
import json, hashlib
from pathlib import Path
m = json.loads(Path('dataset_v0.2_candidate/manifest.json').read_text())
for rel, expected in sorted(m['files'].items()):
    p = Path('dataset_v0.2_candidate') / rel
    if not p.exists(): print('MISSING', rel); continue
    h = hashlib.sha256(p.read_bytes()).hexdigest()
    ok = 'OK' if h == expected else 'MISMATCH'
    print(ok, rel)
"
```

### 3. Run notebooks

```bash
jupyter notebook analysis/
```

Notebooks read only local parquet and JSON files.

### 4. Re-run packaged analysis

```bash
python -m pqm_readiness threshold-sensitivity
python -m pqm_readiness fit-survival-preview
python -m pqm_readiness fit-decay-regression
python -m pqm_readiness count-events
```

Outputs land in `data/metadata/` and `data/processed/threshold_sensitivity.parquet`.

### 5. Unit tests

```bash
python -m pytest tests/ -q
```

## Provenance artifacts

| File | Purpose |
| --- | --- |
| `dataset_v0.2_candidate/manifest.json` | Frozen file hashes and query |
| `data/metadata/provenance.json` | Source APIs and filters |
| `data/release/release_manifest.json` | Public release manifest |
| `data/metadata/data_accessibility_audit.json` | Per-file release classification |

## Determinism notes

- Fixed random seed (42) for baseline sampling
- Deterministic OpenAlex sort (`cited_by_count:desc`)
- Observation year set at pipeline run time; decay outcomes depend on citation window available in frozen data

## What is NOT reproducible from this repo alone

- Re-ingesting from OpenAlex/OpenCitations APIs (raw dumps excluded from release)
- Exact replication of interrupted ingest checkpoints

For new collection, use the development workspace with explicit API access and updated provenance.
