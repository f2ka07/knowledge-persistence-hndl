"""Tests for threshold sensitivity grid."""

from pqm_readiness.analysis.threshold_sensitivity import THRESHOLD_GRID, _stability_summary


def test_threshold_grid_matches_feedback8_spec() -> None:
    assert THRESHOLD_GRID == [
        (0.05, 2),
        (0.05, 3),
        (0.10, 2),
        (0.10, 3),
        (0.15, 3),
        (0.20, 3),
    ]


def test_stability_summary_flags_stable_ten_to_fifteen_region() -> None:
    rows = [
        {"threshold_ratio": 0.10, "consecutive_years": 3, "logrank_p_matched": 0.27},
        {"threshold_ratio": 0.15, "consecutive_years": 3, "logrank_p_matched": 0.31},
        {"threshold_ratio": 0.05, "consecutive_years": 2, "logrank_p_matched": 0.01},
    ]
    summary = _stability_summary(rows)
    assert summary["ten_to_fifteen_percent_region_stable"] is True
    assert summary["tier_c_neutral_at_reference"] is True


def test_stability_summary_detects_unstable_region() -> None:
    rows = [
        {"threshold_ratio": 0.10, "consecutive_years": 3, "logrank_p_matched": 0.27},
        {"threshold_ratio": 0.15, "consecutive_years": 3, "logrank_p_matched": 0.02},
    ]
    summary = _stability_summary(rows)
    assert summary["ten_to_fifteen_percent_region_stable"] is False
