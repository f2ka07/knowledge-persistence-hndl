# Analysis notebooks

Lightweight notebooks that read **only local files** from the frozen release. No API access required.

| Notebook | Purpose |
| --- | --- |
| [01_dataset_overview.ipynb](01_dataset_overview.ipynb) | Row counts, sector/year distributions, censoring summary |
| [02_survival_preview.ipynb](02_survival_preview.ipynb) | Three-tier survival comparison with interpretation guardrails |
| [03_threshold_sensitivity.ipynb](03_threshold_sensitivity.ipynb) | Decay-threshold grid and 10–15% stability region |

## Run

```bash
pip install -e ".[analysis]"
jupyter notebook analysis/
```

Outputs may be saved under `../results/figures/` and `../results/tables/`.
