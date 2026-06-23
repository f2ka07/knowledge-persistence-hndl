#!/usr/bin/env python3
"""Figure A: citation-based persistence indicator (manuscript Figure 13)."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import polars as pl

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO_ROOT / "figures" / "figure_a_influence_decay_operationalisation.pdf"

THRESHOLD = 0.1
CONSECUTIVE = 3
MAX_AGE = 30

FIGURE_CAPTION = (
    "Citation-based persistence indicator from HNDL-relevant technical literature "
    "(OpenAlex + OpenCitations, n=188). Dashed line: 10% of peak annual influence; "
    "shading: influence-decay event (rate below threshold for three consecutive years). "
    "The main paper assumes V(t) = (1 - lambda)^t; K(t) is not equivalent to trade secret value V(t)."
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
        if (candidate / "citations_by_year.parquet").exists():
            return candidate
    raise FileNotFoundError("citations_by_year.parquet not found under frozen snapshot")


def _exemplar_series(
    cby: pl.DataFrame, persistence: pl.DataFrame
) -> tuple[np.ndarray, np.ndarray]:
    decay_ids = persistence.filter(pl.col("influence_decay_event"))["work_id"].to_list()
    best: tuple[float, list[float]] | None = None

    for wid in decay_ids:
        series = cby.filter(pl.col("work_id") == wid).sort("age_years")
        if series.height < 10:
            continue
        age_to_norm = dict(
            zip(
                series["age_years"].to_list(),
                series["normalized_annual_citations"].to_list(),
                strict=True,
            )
        )
        ages = list(range(0, min(int(series["age_years"].max()), MAX_AGE) + 1))
        norms = [age_to_norm.get(a, 0.0) for a in ages]
        peak_age = ages[max(range(len(norms)), key=lambda i: norms[i])]
        if peak_age < 3 or peak_age > 18:
            continue

        streak = 0
        has_decay = False
        for norm in norms:
            if norm < THRESHOLD:
                streak += 1
                if streak >= CONSECUTIVE:
                    has_decay = True
                    break
            else:
                streak = 0
        if not has_decay:
            continue

        score = (18 - abs(peak_age - 6)) + len(ages)
        if best is None or score > best[0]:
            best = (score, norms)

    if best is None:
        ages, norms, _ = _cohort_median_series(cby)
        return ages, norms

    _, norms_list = best
    ages_out = np.arange(0, MAX_AGE + 1)
    norms_out = np.zeros(MAX_AGE + 1)
    norms_out[: len(norms_list)] = norms_list
    return ages_out, norms_out


def _cohort_median_series(cby: pl.DataFrame) -> tuple[np.ndarray, np.ndarray, int]:
    med = (
        cby.filter(pl.col("age_years") <= MAX_AGE)
        .group_by("age_years")
        .agg(pl.col("normalized_annual_citations").median().alias("med"))
        .sort("age_years")
    )
    age_to_med = dict(zip(med["age_years"].to_list(), med["med"].to_list(), strict=True))
    ages = np.arange(0, MAX_AGE + 1)
    norms = np.array([age_to_med.get(int(a), 0.0) for a in ages])
    return ages, norms, int(cby["work_id"].n_unique())


def _decay_shade_range(ages: np.ndarray, norms: np.ndarray) -> tuple[int | None, int | None]:
    streak = 0
    decay_start: int | None = None
    for age, norm in zip(ages, norms, strict=True):
        if norm < THRESHOLD:
            streak += 1
            if streak >= CONSECUTIVE:
                decay_start = int(age - CONSECUTIVE + 1)
                break
        else:
            streak = 0
    if decay_start is None:
        return None, None
    last_obs = int(max(np.where(norms > 0)[0])) if np.any(norms > 0) else int(ages[-1])
    return decay_start, last_obs


def _save(fig: plt.Figure, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, pad_inches=0.2)
    fig.savefig(path.with_suffix(".png"), pad_inches=0.2)


def main(out: Path = DEFAULT_OUT, repo_root: Path = REPO_ROOT) -> None:
    plt.rcParams.update(PUBLISH_RCPARAMS)

    proc = _processed_dir(repo_root)
    cby = pl.read_parquet(proc / "citations_by_year.parquet")
    persistence = pl.read_parquet(proc / "persistence.parquet")
    ages, norms = _exemplar_series(cby, persistence)

    fig, ax = plt.subplots(figsize=(7.2, 4.0))

    observed = norms > 0
    ax.plot(
        ages[observed],
        norms[observed],
        color="#1f1f1f",
        marker="o",
        markersize=5.0,
        markerfacecolor="white",
        markeredgewidth=0.9,
        markeredgecolor="#1f1f1f",
        zorder=3,
    )

    peak_idx = int(np.argmax(norms))
    ax.scatter(
        [ages[peak_idx]],
        [norms[peak_idx]],
        s=52,
        color="#1f1f1f",
        zorder=4,
        label="Peak influence",
    )

    ax.axhline(
        THRESHOLD,
        color="#a61c1c",
        linestyle=(0, (4, 3)),
        linewidth=1.0,
        label="10% of peak",
        zorder=1,
    )

    shade_start, shade_end = _decay_shade_range(ages, norms)
    if shade_start is not None and shade_end is not None:
        ax.axvspan(shade_start, shade_end, color="#d4e8d4", alpha=0.55, zorder=0, label="Decay event")
        shade_mid = shade_start + (shade_end - shade_start) / 2
        target_y = float(norms[int(shade_mid)]) if int(shade_mid) < len(norms) else 0.1
        ax.annotate(
            "Influence decay",
            xy=(shade_mid, max(target_y, 0.06)),
            xytext=(MAX_AGE - 0.5, 0.62),
            fontsize=11,
            ha="right",
            va="center",
            color="#2d5a2d",
            arrowprops=dict(
                arrowstyle="->",
                color="#2d5a2d",
                lw=0.9,
                connectionstyle="arc3,rad=-0.15",
            ),
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor="none", alpha=0.9),
        )

    ax.set_xlim(-0.8, MAX_AGE + 0.8)
    ax.set_ylim(0, 1.05)
    ax.set_xlabel("Years since publication")
    ax.set_ylabel("Normalized annual citations")
    ax.set_xticks(np.arange(0, MAX_AGE + 1, 5))
    ax.set_yticks(np.arange(0, 1.01, 0.2))
    ax.grid(True, which="major", linestyle=":", linewidth=0.5, alpha=0.7)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    ax.legend(
        loc="upper right",
        bbox_to_anchor=(0.99, 0.99),
        frameon=True,
        framealpha=0.95,
        edgecolor="#cccccc",
        borderaxespad=0.5,
    )

    fig.subplots_adjust(left=0.11, right=0.98, top=0.97, bottom=0.14)

    _save(fig, out)
    plt.close(fig)

    print(f"Wrote {out}")
    print(f"Wrote {out.with_suffix('.png')}")
    if shade_start is not None:
        print(f"  Decay shading: ages {shade_start}-{shade_end}")
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
