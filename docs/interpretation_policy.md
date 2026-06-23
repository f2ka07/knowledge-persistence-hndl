# Interpretation Policy

This document governs claims that may be made from the Knowledge Persistence (HNDL) dataset.

## Proxy distinction

- **K(t)** — citation-based persistence and influence decay (observed in this dataset)
- **V(t)** — trade secret or strategic information value (not observed)

**Do not** equate citation metrics with trade secret value, classified capability, or adversary harvest utility.

## Causal claims

**Do not** claim that HNDL sector membership *causes* longer or shorter persistence without:

1. Matched null-model controls (at minimum year-only; preferably fully matched)
2. Survival analysis accounting for censoring
3. Acknowledgement that citation intensity is partly endogenous

Observed tier-C neutrality (fully matched baseline) indicates domain labels alone do not explain persistence differences after matching on influence proxies.

## HNDL and PQC implications

Any HNDL risk implication is **model-based**, not directly observed:

- The dataset informs priors on how long *cited technical knowledge* remains influential
- It does not observe classified systems, key material, or operational secrets
- Downstream HNDL models must propagate uncertainty from censoring and small event counts

## Statistical guardrails

- Do not interpret raw cohort medians without survival context (~80% decay censoring in HNDL)
- Do not tune decay thresholds to maximise significance or event counts
- Prefer stable parameter regions (10–15% peak threshold, 3 consecutive years) over single p-values
- Treat `dataset_v0.1` as exploratory only (predates cited_doi fix)

## Recommended framing

> How should long-horizon information persistence be operationalised?

Not:

> Which HNDL sectors remain most valuable?

## Review checklist

Before publication, confirm:

- [ ] Matched baseline comparison included
- [ ] K(t) vs V(t) distinction stated
- [ ] Censoring and event counts reported
- [ ] No causal sector claims without matching
- [ ] Threshold rule justified via sensitivity analysis
