"""High-signal unit tests for the health calculator helpers."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from custom_components.pawcontrol.types import DietValidationResult, FeedingHistoryEvent
from tests.unit.test_health_metrics import (
    HealthCalculator,
    HealthMetrics,
    health_calculator,
)

dt_util = health_calculator.dt_util  # type: ignore[attr-defined]
ActivityLevel = health_calculator.ActivityLevel
BodyConditionScore = health_calculator.BodyConditionScore
LifeStage = health_calculator.LifeStage
dt_util.now = lambda: datetime.now(UTC)


def create_metrics(**overrides: object) -> HealthMetrics:
    """Create a ``HealthMetrics`` instance with sensible defaults for tests."""
    defaults: dict[str, object] = {
        "current_weight": 25.0,
        "ideal_weight": 22.0,
        "age_months": 36,
        "body_condition_score": BodyConditionScore.IDEAL,
        "activity_level": ActivityLevel.MODERATE,
        "health_conditions": [],
        "special_diet": [],
    }
    defaults.update(overrides)
    return HealthMetrics(**defaults)


class TestHealthMetricsValidation:
    """Validation-centric tests for :class:`HealthMetrics`."""

    def test_validate_breed_normalizes_whitespace(self) -> None:
        """Breed values are normalised and validated."""
        metrics = create_metrics(breed="  golden   retriever  ")
        assert metrics.breed == "golden retriever"

    @pytest.mark.parametrize("invalid", ["", "x", "Poodle!", 123])
    def test_validate_breed_rejects_invalid_values(self, invalid: object) -> None:
        """Invalid breed values raise a descriptive error."""
        with pytest.raises((TypeError, ValueError)):
            create_metrics(breed=invalid)


class TestLifeStageCalculation:
    """Tests for ``calculate_life_stage`` thresholds and validation."""

    def test_life_stage_thresholds(self) -> None:
        """Life stage thresholds account for breed size."""
        assert HealthCalculator.calculate_life_stage(10, "medium") == LifeStage.PUPPY
        assert (
            HealthCalculator.calculate_life_stage(20, "medium") == LifeStage.YOUNG_ADULT
        )
        assert HealthCalculator.calculate_life_stage(70, "large") == LifeStage.ADULT
        assert HealthCalculator.calculate_life_stage(90, "medium") == LifeStage.SENIOR
        assert (
            HealthCalculator.calculate_life_stage(130, "medium") == LifeStage.GERIATRIC
        )

    def test_life_stage_negative_age_raises(self) -> None:
        """Negative ages are rejected instead of silently classified."""
        with pytest.raises(ValueError):
            HealthCalculator.calculate_life_stage(-1)


class TestCoreHealthCalculations:
    """Tests for the calculator's numeric helper methods."""

    @pytest.mark.parametrize(
        ("current_weight", "ideal_weight", "visual_assessment", "expected"),
        [
            (10.0, None, None, BodyConditionScore.IDEAL),
            (10.0, 10.0, 9, BodyConditionScore.SEVERELY_OBESE),
            (6.5, 10.0, None, BodyConditionScore.EMACIATED),
            (7.5, 10.0, None, BodyConditionScore.VERY_THIN),
            (8.5, 10.0, None, BodyConditionScore.THIN),
            (9.2, 10.0, None, BodyConditionScore.UNDERWEIGHT),
            (10.3, 10.0, None, BodyConditionScore.IDEAL),
            (11.2, 10.0, None, BodyConditionScore.OVERWEIGHT),
            (12.3, 10.0, None, BodyConditionScore.HEAVY),
            (13.5, 10.0, None, BodyConditionScore.OBESE),
            (15.0, 10.0, None, BodyConditionScore.SEVERELY_OBESE),
        ],
    )
    def test_estimate_body_condition_score_covers_thresholds(
        self,
        current_weight: float,
        ideal_weight: float | None,
        visual_assessment: int | None,
        expected: BodyConditionScore,
    ) -> None:
        """Estimated scores should honor visual overrides and ratio thresholds."""
        result = HealthCalculator.estimate_body_condition_score(
            current_weight=current_weight,
            ideal_weight=ideal_weight,
            visual_assessment=visual_assessment,
        )

        assert result is expected

    def test_calculate_bmi_handles_zero_height(self) -> None:
        """BMI should safely fall back to zero for invalid heights."""
        assert HealthCalculator.calculate_bmi(20.0, 50.0) == pytest.approx(80.0)
        assert HealthCalculator.calculate_bmi(20.0, 0.0) == 0.0

    def test_calculate_daily_calories_spay_neuter_adjustment_is_stage_specific(
        self,
    ) -> None:
        """Adult and senior dogs get the neuter reduction, puppies do not."""
        adult_intact = HealthCalculator.calculate_daily_calories(
            weight=20.0,
            life_stage=LifeStage.ADULT,
            activity_level=ActivityLevel.MODERATE,
            spayed_neutered=False,
        )
        adult_fixed = HealthCalculator.calculate_daily_calories(
            weight=20.0,
            life_stage=LifeStage.ADULT,
            activity_level=ActivityLevel.MODERATE,
            spayed_neutered=True,
        )
        puppy_intact = HealthCalculator.calculate_daily_calories(
            weight=20.0,
            life_stage=LifeStage.PUPPY,
            activity_level=ActivityLevel.MODERATE,
            spayed_neutered=False,
        )
        puppy_fixed = HealthCalculator.calculate_daily_calories(
            weight=20.0,
            life_stage=LifeStage.PUPPY,
            activity_level=ActivityLevel.MODERATE,
            spayed_neutered=True,
        )

        assert adult_fixed == pytest.approx(adult_intact * 0.9, abs=0.1)
        assert puppy_fixed == puppy_intact


class TestPortionCalculations:
    """Tests for the complex portion adjustment logic."""

    def test_portion_adjustment_factor_combines_all_modifiers(self) -> None:
        """BCS, conditions and diets influence the portion multiplier."""
        metrics = create_metrics(
            body_condition_score=BodyConditionScore.OVERWEIGHT,
            health_conditions=["Diabetes"],
            special_diet=["weight_control"],
        )

        factor = HealthCalculator.calculate_portion_adjustment_factor(metrics)
        assert factor == pytest.approx(0.69)

    def test_portion_adjustment_respects_lower_bound(self) -> None:
        """Extreme adjustments are clamped to the safe lower bound."""
        metrics = create_metrics(
            body_condition_score=BodyConditionScore.SEVERELY_OBESE,
            health_conditions=["diabetes", "heart_disease"],
            special_diet=["weight_control", "diabetic"],
        )
        factor = HealthCalculator.calculate_portion_adjustment_factor(
            metrics,
            feeding_goals={"weight_goal": "lose", "weight_loss_rate": "aggressive"},
        )
        assert factor == 0.5

    def test_diet_validation_adjustment_applies_conflicts_and_warnings(self) -> None:
        """Conflicts and warnings reduce the adjustment factor cumulatively."""
        validation: DietValidationResult = {
            "valid": False,
            "conflicts": [
                {
                    "type": "age_conflict",
                    "diets": ["puppy_formula"],
                    "message": "Age conflict",
                }
            ],
            "warnings": [
                {
                    "type": "multiple_prescription_warning",
                    "diets": ["prescription"],
                    "message": "Multiple prescription diets",
                }
            ],
            "recommended_vet_consultation": False,
            "total_diets": 2,
        }

        adjustment = HealthCalculator.calculate_diet_validation_adjustment(
            validation,
            ["prescription"],
        )

        assert adjustment == pytest.approx(0.855)

    def test_diet_interactions_detects_risk_levels(self) -> None:
        """Diet interactions categorise combinations correctly."""
        interactions = HealthCalculator.get_diet_interaction_effects([
            "senior_formula",
            "joint_support",
            "raw_diet",
            "prescription",
            "weight_control",
            "puppy_formula",
            "low_fat",
        ])

        assert len(interactions["synergistic"]) == 3
        assert len(interactions["caution"]) == 2
        assert len(interactions["conflicting"]) == 2
        assert interactions["risk_level"] == "high"

    def test_validate_portion_safety_reports_large_high_risk_conflicting_portions(
        self,
    ) -> None:
        """Unsafe large portions should accumulate warnings and vet guidance."""
        validation: DietValidationResult = {
            "valid": False,
            "conflicts": [
                {
                    "type": "age_conflict",
                    "diets": ["puppy_formula"],
                    "message": "Age conflict",
                }
            ],
            "warnings": [],
            "recommended_vet_consultation": True,
            "total_diets": 1,
        }

        result = HealthCalculator.validate_portion_safety(
            calculated_portion=1200.0,
            dog_weight=20.0,
            life_stage=LifeStage.ADULT,
            special_diets=["prescription"],
            diet_validation=validation,
        )

        assert result["safe"] is False
        assert result["portion_per_kg"] == 60.0
        assert any("too large" in warning for warning in result["warnings"])
        assert (
            "Diet conflicts detected - extra monitoring recommended"
            in result["warnings"]
        )
        assert (
            "Prescription diet detected - verify portions with veterinarian"
            in result["recommendations"]
        )
        assert (
            "Veterinary consultation recommended due to diet complexity"
            in result["recommendations"]
        )

    def test_validate_portion_safety_handles_small_portions_and_zero_weight(
        self,
    ) -> None:
        """Small portions warn without becoming unsafe, and zero weight stays stable."""
        small_result = HealthCalculator.validate_portion_safety(
            calculated_portion=100.0,
            dog_weight=20.0,
            life_stage=LifeStage.SENIOR,
            special_diets=[],
        )
        zero_weight_result = HealthCalculator.validate_portion_safety(
            calculated_portion=100.0,
            dog_weight=0.0,
            life_stage=LifeStage.ADULT,
            special_diets=[],
        )

        assert small_result["safe"] is True
        assert any("too small" in warning for warning in small_result["warnings"])
        assert any(
            "Consider increasing portion size" in recommendation
            for recommendation in small_result["recommendations"]
        )
        assert zero_weight_result == {
            "safe": True,
            "warnings": [],
            "recommendations": [],
            "portion_per_kg": 0.0,
        }


class TestFeedingHistoryAnalysis:
    """Behavioural tests for ``analyze_feeding_history``."""

    def test_analyze_feeding_history_handles_no_events(self) -> None:
        """No events returns a helpful guidance payload."""
        result = HealthCalculator.analyze_feeding_history([], 600.0)
        assert result["status"] == "no_data"

    def test_analyze_feeding_history_requires_recent_data(self) -> None:
        """Only recent events are considered for analysis."""
        old_event_time = dt_util.now() - timedelta(days=10)
        result = HealthCalculator.analyze_feeding_history(
            [FeedingHistoryEvent(time=old_event_time, amount=200.0)],
            600.0,
        )
        assert result["status"] == "insufficient_data"

    def test_analyze_feeding_history_balanced_plan(self) -> None:
        """Balanced meals surface a 'good' status and actionable tips."""
        now = dt_util.now()
        events = [
            FeedingHistoryEvent(time=now - timedelta(days=1), amount=100.0),
            FeedingHistoryEvent(
                time=now - timedelta(days=1) + timedelta(hours=1), amount=100.0
            ),
            FeedingHistoryEvent(time=now - timedelta(days=2), amount=100.0),
            FeedingHistoryEvent(
                time=now - timedelta(days=2) + timedelta(hours=2), amount=100.0
            ),
        ]
        result = HealthCalculator.analyze_feeding_history(events, 700.0)

        assert result["status"] == "good"
        assert result["avg_daily_calories"] == pytest.approx(700.0)
        assert result["calorie_variance_percent"] == pytest.approx(0.0)
        assert any(
            "well balanced" in recommendation
            for recommendation in result["recommendations"]
        )
