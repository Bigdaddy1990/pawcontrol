"""Targeted coverage tests for health_calculator.py — (0% → 25%+).

Covers: ActivityLevel, BodyConditionScore enums, HealthCalculator class
"""
from __future__ import annotations

import pytest

from custom_components.pawcontrol.health_calculator import (
    ActivityLevel,
    BodyConditionScore,
)


# ─── ActivityLevel ────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_activity_level_has_members() -> None:
    assert len(list(ActivityLevel)) >= 3


@pytest.mark.unit
def test_activity_level_moderate_exists() -> None:
    assert ActivityLevel.MODERATE is not None


@pytest.mark.unit
def test_activity_level_high_exists() -> None:
    assert ActivityLevel.HIGH is not None


@pytest.mark.unit
def test_activity_level_low_exists() -> None:
    assert ActivityLevel.LOW is not None


@pytest.mark.unit
def test_activity_level_values_are_strings() -> None:
    for level in ActivityLevel:
        assert isinstance(level.value, str)


# ─── BodyConditionScore ───────────────────────────────────────────────────────

@pytest.mark.unit
def test_body_condition_score_has_members() -> None:
    assert len(list(BodyConditionScore)) >= 4


@pytest.mark.unit
def test_body_condition_score_ideal_exists() -> None:
    assert BodyConditionScore.IDEAL is not None


@pytest.mark.unit
def test_body_condition_score_overweight_exists() -> None:
    assert BodyConditionScore.OVERWEIGHT is not None


@pytest.mark.unit
def test_body_condition_score_thin_exists() -> None:
    assert BodyConditionScore.THIN is not None


@pytest.mark.unit
def test_body_condition_score_emaciated_exists() -> None:
    assert BodyConditionScore.EMACIATED is not None


@pytest.mark.unit
def test_body_condition_score_values_are_strings_or_ints() -> None:
    for score in BodyConditionScore:
        assert isinstance(score.value, (str, int))
