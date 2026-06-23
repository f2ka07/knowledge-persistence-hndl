"""Tests for influence decay event detection."""

from pqm_readiness.transform.persistence import influence_decay_metrics


def test_influence_decay_detects_three_low_years() -> None:
    ages = [0, 1, 2, 3, 4, 5]
    annual = [100, 80, 5, 4, 3, 2]
    result = influence_decay_metrics(ages, annual, publication_year=2000, threshold_ratio=0.1)
    assert result["influence_decay_event"] is True
    assert result["decay_event_year"] == 2004
    assert result["time_to_decay_years"] == 4.0


def test_influence_decay_censored_when_still_influential() -> None:
    ages = [0, 1, 2, 3]
    annual = [50, 45, 40, 35]
    result = influence_decay_metrics(ages, annual, publication_year=2010)
    assert result["influence_decay_event"] is False
    assert result["influence_decay_censored"] is True
    assert result["time_to_decay_years"] == 3.0


def test_influence_decay_fills_missing_years_as_zero() -> None:
    ages = [0, 2, 4]
    annual = [100, 5, 4]
    result = influence_decay_metrics(ages, annual, publication_year=2005, consecutive_years=3)
    assert result["influence_decay_event"] is True
    assert result["decay_event_year"] == 2008
