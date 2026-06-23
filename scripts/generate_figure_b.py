#!/usr/bin/env python3
"""Figure B: persistence-matching sensitivity as hazard ratio with 95% CI (manuscript Figure 14)."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import polars as pl

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO_ROOT / "figures" / "figure_b_persistence_decomposition.pdf"

FIGURE_CAPTION = (
    "Hazard ratios (HNDL vs baseline) for influence-decay timing under progressively stronger "
    "matching assumptions. Reference line: no apparent persistence effect (HR = 1). Apparent "
    "contrasts attenuate as cohort controls incorporate influence accumulation; full matching "
    "is consistent with a neutral interpretation."
)

TIERS = (
    ("Random", "baseline_random"),
    ("Year matched", "baseline_year_only"),
    ("Fully matched", "baseline_matched"),
)

PUBLISH_RCPARAMS = {
    "font.family": "serif",
    "font.serif": ["Times New Roman", "DejaVu Serif", "serif"],
    "font.size": 12,
    "axes.labelsize": 12,
    "axes.titlesize": 12,
    "legend.fontsize": 11,
    "xtick.labelsize": 11,
    "ytick.labelsize": 11,
    "axes.linewidth": 0.8,
    "grid.linewidth": 0.5,
    "lines.linewidth": 1.6,
    "figure.dpi": 150,
    "savefig.dpi": 300,
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
}


def _processed_dir(repo_root: Path) -> Path:
    for candidate in (
        repo_root / "dataset_v0.2_candidate" / "processed",
        repo_root / "data" / "processed",
    ):
        if (candidate / "persistence.parquet").exists():
            return candidate
    raise FileNotFoundError("processed persistence tables not found")


def _survival_frame(proc: Path) -> pl.DataFrame:
    paths = {
        "hndl": proc / "persistence.parquet",
        "baseline_random": proc / "baseline_random_sample.parquet",
        "baseline_year_only": proc / "baseline_year_only.parquet",
        "baseline_matched": proc / "baseline_matched.parquet",
    }
    frames = [
        pl.read_parquet(path).with_columns(pl.lit(name).alias("cohort"))
        for name, path in paths.items()
        if path.exists()
    ]
    combined = pl.concat(frames, how="diagonal_relaxed")
    return combined.filter(
        pl.col("time_to_decay_years").is_not_null() & (pl.col("time_to_decay_years") > 0)
    ).select(
        "cohort",
        pl.col("time_to_decay_years").alias("duration"),
        pl.col("influence_decay_event").cast(pl.Int64).alias("event"),
    )


def _cox_hr_ci(hndl: pd.DataFrame, other: pd.DataFrame) -> tuple[float, float, float]:
    from lifelines import CoxPHFitter

    frame = pd.concat(
        [
            hndl[["duration", "event"]].assign(is_hndl=1),
            other[["duration", "event"]].assign(is_hndl=0),
        ],
        ignore_index=True,
    )
    cox = CoxPHFitter()
    cox.fit(frame, duration_col="duration", event_col="event")
    row = cox.summary.loc["is_hndl"]
    return (
        float(row["exp(coef)"]),
        float(row["exp(coef) lower 95%"]),
        float(row["exp(coef) upper 95%"]),
    )


def _fit_tiers(survival: pl.DataFrame) -> list[dict]:
    pdf = survival.to_pandas()
    hndl = pdf[pdf["cohort"] == "hndl"]
    rows: list[dict] = []
    for label, baseline in TIERS:
        other = pdf[pdf["cohort"] == baseline]
        hr, lo, hi = _cox_hr_ci(hndl, other)
        rows.append({"label": label, "hr": hr, "lo": lo, "hi": hi})
    return rows


def main(out: Path = DEFAULT_OUT, repo_root: Path = REPO_ROOT) -> None:
    plt.rcParams.update(PUBLISH_RCPARAMS)

    proc = _processed_dir(repo_root)
    survival = _survival_frame(proc)
    results = _fit_tiers(survival)

    x = np.arange(len(results))
    hrs = np.array([r["hr"] for r in results])
    los = np.array([r["lo"] for r in results])
    his = np.array([r["hi"] for r in results])
    labels = [r["label"] for r in results]

    fig, ax = plt.subplots(figsize=(7.2, 4.2))

    ax.axhline(
        1.0,
        color="#888888",
        linestyle=(0, (5, 4)),
        linewidth=1.0,
        zorder=1,
        label="No apparent persistence effect",
    )

    ax.errorbar(
        x,
        hrs,
        yerr=[hrs - los, his - hrs],
        fmt="o-",
        color="#1f1f1f",
        ecolor="#4c72b0",
        elinewidth=1.2,
        capsize=5,
        markersize=8,
        markerfacecolor="white",
        markeredgewidth=1.2,
        markeredgecolor="#1f1f1f",
        zorder=3,
    )

    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_xlabel("Matching strength")
    ax.set_ylabel("Relative persistence hazard\n(HNDL / baseline)")

    for xi, hr, hi in zip(x, hrs, his, strict=True):
        ax.annotate(
            f"{hr:.2f}",
            xy=(xi, hi),
            xytext=(0, 6),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=11,
            color="#1f1f1f",
        )

    y_min = min(los.min(), 0.45)
    y_max = max(his.max(), 1.55)
    ax.set_ylim(y_min - 0.08, y_max + 0.12)
    ax.set_xlim(-0.35, len(x) - 0.65)

    ax.grid(True, axis="y", linestyle=":", linewidth=0.5, alpha=0.7)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.legend(loc="upper right", frameon=True, framealpha=0.95, edgecolor="#cccccc")

    fig.subplots_adjust(left=0.16, right=0.97, top=0.96, bottom=0.16)

    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, pad_inches=0.15)
    fig.savefig(out.with_suffix(".png"), pad_inches=0.15)
    plt.close(fig)

    print(f"Wrote {out}")
    print(f"Wrote {out.with_suffix('.png')}")
    for r in results:
        print(f"  {r['label']}: HR={r['hr']:.3f} [{r['lo']:.3f}, {r['hi']:.3f}]")
    print("\nSuggested caption:\n")
    print(FIGURE_CAPTION)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help="Output PDF path (PNG written alongside)",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=REPO_ROOT,
        help="Repository root containing dataset_v0.2_candidate/",
    )
    args = parser.parse_args()
    main(out=args.out, repo_root=args.repo_root)
