#!/usr/bin/env python3
"""Regenerate manuscript Figures 13 and 14 from the frozen dataset."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=SCRIPTS_DIR.parent / "figures",
        help="Directory for PDF and PNG outputs",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=SCRIPTS_DIR.parent,
        help="Repository root containing dataset_v0.2_candidate/",
    )
    args = parser.parse_args()

    runners = (
        ("generate_figure_a.py", "figure_a_influence_decay_operationalisation.pdf"),
        ("generate_figure_b.py", "figure_b_persistence_decomposition.pdf"),
    )
    for script_name, filename in runners:
        out = args.out_dir / filename
        cmd = [
            sys.executable,
            str(SCRIPTS_DIR / script_name),
            "--out",
            str(out),
            "--repo-root",
            str(args.repo_root),
        ]
        subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
