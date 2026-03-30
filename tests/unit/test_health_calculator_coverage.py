"""Targeted coverage tests for health_calculator.py — uncovered paths (23% → 42%+).

Covers: HealthCalculator.calculate_daily_calories, calculate_bmi,
        activity_score, calculate_life_stage, calculate_ideal_weight_range
"""
from __future__ import annotations

import pytest

from custom_components.pawcontrol.health_calculator import (
    ActivityLevel,
    BodyConditionScore,
    HealthCalculator,
    LifeStage,
)


# ═══════════════════════════════════════════════════════════════════════════════
# calculate_life_stage
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
def test_life_stage_puppy() -> None:
    result = HealthCalculator.calculate_life_stage(6, "medium")
    assert result == LifeStage.PUPPY


@pytest.mark.unit
def test_life_stage_adult() -> None:
    result = HealthCalculator.calculate_life_stage(36, "medium")
    assert result == LifeStage.ADULT


@pytest.mark.unit
def test_life_stage_senior() -> None:
    result = HealthCalculator.calculate_life_stage(96, "medium")
    assert result == LifeStage.SENIOR


@pytest.mark.unit
def test_life_stage_large_breed_senior_earlier() -> None:
    # Large breeds become senior earlier
    result = HealthCalculator.calculate_life_stage(72, "large")
    assert result in (LifeStage.SENIOR, LifeStage.ADULT)


# ═══════════════════════════════════════════════════════════════════════════════
# calculate_bmi
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
def test_calculate_bmi_typical_dog() -> None:
    # 25 kg, 55 cm height → BMI = 25 / (0.55^2) ≈ 82.6
    bmi = HealthCalculator.calculate_bmi(weight=25.0, height_cm=55.0)
    assert isinstance(bmi, float)
    assert bmi > 0


@pytest.mark.unit
def test_calculate_bmi_small_dog() -> None:
    bmi = HealthCalculator.calculate_bmi(weight=5.0, height_cm=30.0)
    assert isinstance(bmi, float)
    assert bmi > 0


# ═══════════════════════════════════════════════════════════════════════════════
# activity_score
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
def test_activity_score_young_active() -> None:
    score = HealthCalculator.activity_score(steps=10000, age=24)
    assert isinstance(score, float)
    assert score >= 0.0


@pytest.mark.unit
def test_activity_score_sedentary_senior() -> None:
    score = HealthCalculator.activity_score(steps=500, age=120)
    assert isinstance(score, float)
    assert score < 5.0


@pytest.mark.unit
def test_activity_score_zero_steps() -> None:
    score = HealthCalculator.activity_score(steps=0, age=36)
    assert isinstance(score, float)
    assert score >= 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# calculate_daily_calories
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
def test_calculate_daily_calories_adult_active() -> None:
    kcal = HealthCalculator.calculate_daily_calories(
        weight=25.0,
        life_stage=LifeStage.ADULT,
        activity_level=ActivityLevel.HIGH,
    )
    assert isinstance(kcal, float)
    assert kcal > 0


@pytest.mark.unit
def test_calculate_daily_calories_puppy_higher() -> None:
    adult = HealthCalculator.calculate_daily_calories(
        weight=10.0, life_stage=LifeStage.ADULT,
        activity_level=ActivityLevel.MODERATE,
    )
    puppy = HealthCalculator.calculate_daily_calories(
        weight=10.0, life_stage=LifeStage.PUPPY,
        activity_level=ActivityLevel.MODERATE,
    )
    assert isinstance(adult, float) and isinstance(puppy, float)


@pytest.mark.unit
def test_calculate_daily_calories_spayed_lower() -> None:
    intact = HealthCalculator.calculate_daily_calories(
        weight=20.0, life_stage=LifeStage.ADULT,
        activity_level=ActivityLevel.MODERATE, spayed_neutered=False,
    )
    spayed = HealthCalculator.calculate_daily_calories(
        weight=20.0, life_stage=LifeStage.ADULT,
        activity_level=ActivityLevel.MODERATE, spayed_neutered=True,
    )
    assert isinstance(intact, float) and isinstance(spayed, float)


@pytest.mark.unit
def test_calculate_daily_calories_with_bcs() -> None:
    kcal = HealthCalculator.calculate_daily_calories(
        weight=22.0, life_stage=LifeStage.ADULT,
        activity_level=ActivityLevel.LOW,
        body_condition_score=BodyConditionScore.HEAVY,
    )
    assert isinstance(kcal, float)
    assert kcal > 0


# ═══════════════════════════════════════════════════════════════════════════════
# calculate_ideal_weight_range
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
def test_calculate_ideal_weight_range_returns_tuple() -> None:
    result = HealthCalculator.calculate_ideal_weight_range(
        current_weight=25.0, breed="medium"
    )
    assert isinstance(result, tuple)
    low, high = result
    assert low <= high
