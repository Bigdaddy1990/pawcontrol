"""High-signal unit tests for the health calculator helpers."""

from datetime import UTC, datetime, timedelta, timezone

import pytest
from tests.unit.test_health_metrics import (
    HealthCalculator,
    HealthMetrics,
    health_calculator,
)

from custom_components.pawcontrol.types import DietValidationResult, FeedingHistoryEvent

dt_util = health_calculator.dt_util  # type: ignore[attr-defined]
ActivityLevel = health_calculator.ActivityLevel
BodyConditionScore = health_calculator.BodyConditionScore
LifeStage = health_calculator.LifeStage
dt_util.now = lambda: datetime.now(UTC)


def create_metrics(**overrides: object) -> HealthMetrics:
    """Create a ``HealthMetrics`` instance with sensible defaults for tests."""  # noqa: E111

    defaults: dict[str, object] = {  # noqa: E111
        "current_weight": 25.0,
        "ideal_weight": 22.0,
        "age_months": 36,
        "body_condition_score": BodyConditionScore.IDEAL,
        "activity_level": ActivityLevel.MODERATE,
        "health_conditions": [],
        "special_diet": [],
    }
    defaults.update(overrides)  # noqa: E111
    return HealthMetrics(**defaults)  # noqa: E111


class TestHealthMetricsValidation:
    """Validation-centric tests for :class:`HealthMetrics`."""  # noqa: E111

    def test_validate_breed_normalizes_whitespace(self) -> None:  # noqa: E111
        """Breed values are normalised and validated."""

        metrics = create_metrics(breed="  golden   retriever  ")
        assert metrics.breed == "golden retriever"

    @pytest.mark.parametrize("invalid", ["", "x", "Poodle!", 123])  # noqa: E111
    def test_validate_breed_rejects_invalid_values(self, invalid: object) -> None:  # noqa: E111
        """Invalid breed values raise a descriptive error."""

        with pytest.raises((TypeError, ValueError)):
            create_metrics(breed=invalid)  # noqa: E111


class TestLifeStageCalculation:
    """Tests for ``calculate_life_stage`` thresholds and validation."""  # noqa: E111

    def test_life_stage_thresholds(self) -> None:  # noqa: E111
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

    def test_life_stage_negative_age_raises(self) -> None:  # noqa: E111
        """Negative ages are rejected instead of silently classified."""

        with pytest.raises(ValueError):
            HealthCalculator.calculate_life_stage(-1)  # noqa: E111


class TestPortionCalculations:
    """Tests for the complex portion adjustment logic."""  # noqa: E111

    def test_portion_adjustment_factor_combines_all_modifiers(self) -> None:  # noqa: E111
        """BCS, conditions and diets influence the portion multiplier."""

        metrics = create_metrics(
            body_condition_score=BodyConditionScore.OVERWEIGHT,
            health_conditions=["Diabetes"],
            special_diet=["weight_control"],
        )

        factor = HealthCalculator.calculate_portion_adjustment_factor(metrics)
        assert factor == pytest.approx(0.69)

    def test_portion_adjustment_respects_lower_bound(self) -> None:  # noqa: E111
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

    def test_diet_validation_adjustment_applies_conflicts_and_warnings(self) -> None:  # noqa: E111
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

    def test_diet_interactions_detects_risk_levels(self) -> None:  # noqa: E111
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


class TestFeedingHistoryAnalysis:
    """Behavioural tests for ``analyze_feeding_history``."""  # noqa: E111

    def test_analyze_feeding_history_handles_no_events(self) -> None:  # noqa: E111
        """No events returns a helpful guidance payload."""

        result = HealthCalculator.analyze_feeding_history([], 600.0)
        assert result["status"] == "no_data"

    def test_analyze_feeding_history_requires_recent_data(self) -> None:  # noqa: E111
        """Only recent events are considered for analysis."""

        old_event_time = dt_util.now() - timedelta(days=10)
        result = HealthCalculator.analyze_feeding_history(
            [FeedingHistoryEvent(time=old_event_time, amount=200.0)],
            600.0,
        )
        assert result["status"] == "insufficient_data"

    def test_analyze_feeding_history_balanced_plan(self) -> None:  # noqa: E111
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
