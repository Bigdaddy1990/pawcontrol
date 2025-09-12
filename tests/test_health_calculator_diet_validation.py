"""Tests for health calculator diet validation integration.

Quality Scale: Platinum
Home Assistant: 2025.9.0+
Python: 3.13+

Tests diet validation adjustments, conflict handling, and portion safety.
"""

from __future__ import annotations

import sys
from importlib import util
from pathlib import Path
from unittest.mock import patch

import pytest

# Import health calculator module
HEALTH_CALC_SPEC = util.spec_from_file_location(
    "health_calculator",
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "pawcontrol"
    / "health_calculator.py",
)

health_calculator = util.module_from_spec(HEALTH_CALC_SPEC)
sys.modules[HEALTH_CALC_SPEC.name] = health_calculator
HEALTH_CALC_SPEC.loader.exec_module(health_calculator)

HealthCalculator = health_calculator.HealthCalculator
HealthMetrics = health_calculator.HealthMetrics
BodyConditionScore = health_calculator.BodyConditionScore
LifeStage = health_calculator.LifeStage
ActivityLevel = health_calculator.ActivityLevel


class TestDietValidationAdjustments:
    """Test diet validation adjustment calculations."""

    def test_no_diet_validation_returns_neutral_adjustment(self) -> None:
        """No diet validation should return 1.0 (neutral) adjustment."""
        adjustment = HealthCalculator.calculate_diet_validation_adjustment(
            diet_validation={}, special_diets=["grain_free"]
        )
        assert adjustment == 1.0

    def test_age_conflict_reduces_portion(self) -> None:
        """Age-based diet conflicts should reduce portions conservatively."""
        diet_validation = {
            "conflicts": [
                {
                    "type": "age_conflict",
                    "message": "Puppy formula with senior formula",
                    "diets": ["puppy_formula", "senior_formula"],
                }
            ],
            "warnings": [],
        }

        adjustment = HealthCalculator.calculate_diet_validation_adjustment(
            diet_validation, ["puppy_formula", "senior_formula"]
        )

        assert adjustment == 0.9  # 10% reduction for age conflicts

    def test_multiple_prescription_warning_adjustment(self) -> None:
        """Multiple prescription diets should apply mild portion reduction."""
        diet_validation = {
            "conflicts": [],
            "warnings": [
                {
                    "type": "multiple_prescription_warning",
                    "message": "Multiple prescription diets need vet coordination",
                    "diets": ["diabetic", "kidney_support"],
                }
            ],
        }

        adjustment = HealthCalculator.calculate_diet_validation_adjustment(
            diet_validation, ["diabetic", "kidney_support"]
        )

        assert adjustment == 0.95  # 5% reduction for prescription warning

    def test_raw_medical_warning_adjustment(self) -> None:
        """Raw diet with medical conditions should apply conservative adjustment."""
        diet_validation = {
            "conflicts": [],
            "warnings": [
                {
                    "type": "raw_medical_warning",
                    "message": "Raw diet with kidney disease",
                    "diets": ["raw_diet", "kidney_support"],
                }
            ],
        }

        adjustment = HealthCalculator.calculate_diet_validation_adjustment(
            diet_validation, ["raw_diet", "kidney_support"]
        )

        assert adjustment == 0.95  # 5% reduction for safety

    def test_weight_puppy_warning_increases_portion(self) -> None:
        """Weight control for puppies should slightly increase portions for growth."""
        diet_validation = {
            "conflicts": [],
            "warnings": [
                {
                    "type": "weight_puppy_warning",
                    "message": "Weight control diet for growing puppy",
                    "diets": ["weight_control", "puppy_formula"],
                }
            ],
        }

        adjustment = HealthCalculator.calculate_diet_validation_adjustment(
            diet_validation, ["weight_control", "puppy_formula"]
        )

        assert adjustment == 1.05  # 5% increase for growing puppy

    def test_complex_diet_combination_adjustment(self) -> None:
        """Complex diet combinations should apply additional safety reduction."""
        diet_validation = {
            "conflicts": [],
            "warnings": [
                {
                    "type": "hypoallergenic_warning",
                    "message": "Hypoallergenic with multiple other diets",
                }
            ],
            "total_diets": 5,  # Very complex
            "recommended_vet_consultation": True,
        }

        adjustment = HealthCalculator.calculate_diet_validation_adjustment(
            diet_validation,
            [
                "hypoallergenic",
                "grain_free",
                "senior_formula",
                "joint_support",
                "low_fat",
            ],
        )

        # Should apply: hypoallergenic warning (0.98) + complex diet (0.97) + vet consultation (0.95)
        expected = 0.98 * 0.97 * 0.95
        assert abs(adjustment - expected) < 0.001

    def test_multiple_conflicts_compound_adjustments(self) -> None:
        """Multiple conflicts should compound adjustments within bounds."""
        diet_validation = {
            "conflicts": [
                {"type": "age_conflict", "message": "Age conflict 1"},
                {"type": "age_conflict", "message": "Age conflict 2"},
            ],
            "warnings": [
                {
                    "type": "multiple_prescription_warning",
                    "message": "Prescription warning",
                }
            ],
        }

        adjustment = HealthCalculator.calculate_diet_validation_adjustment(
            diet_validation, ["puppy_formula", "senior_formula", "diabetic"]
        )

        # Should apply multiple 0.9 reductions and one 0.95, but bounded at 0.8
        assert adjustment >= 0.8  # Lower bound
        assert adjustment < 1.0

    def test_adjustment_bounds_enforcement(self) -> None:
        """Adjustment factor should be bounded between 0.8 and 1.1."""
        # Test lower bound with extreme conflicts
        extreme_validation = {
            "conflicts": [{"type": "age_conflict"}] * 10,  # Many conflicts
            "warnings": [{"type": "multiple_prescription_warning"}] * 10,
            "total_diets": 10,
            "recommended_vet_consultation": True,
        }

        adjustment = HealthCalculator.calculate_diet_validation_adjustment(
            extreme_validation, ["multiple", "diets"]
        )

        assert adjustment >= 0.8
        assert adjustment <= 1.1


class TestPortionSafetyValidation:
    """Test portion safety validation with diet considerations."""

    def test_valid_portion_passes_safety_check(self) -> None:
        """Normal portion size should pass safety validation."""
        safety_result = HealthCalculator.validate_portion_safety(
            calculated_portion=200.0,  # 20g/kg for 10kg dog
            dog_weight=10.0,
            life_stage=LifeStage.ADULT,
            special_diets=["grain_free"],
            diet_validation=None,
        )

        assert safety_result["safe"] is True
        assert len(safety_result["warnings"]) == 0
        assert safety_result["portion_per_kg"] == 20.0

    def test_undersized_portion_triggers_warning(self) -> None:
        """Portion too small should trigger warning."""
        safety_result = HealthCalculator.validate_portion_safety(
            calculated_portion=50.0,  # 5g/kg for 10kg dog - too small
            dog_weight=10.0,
            life_stage=LifeStage.ADULT,
            special_diets=[],
            diet_validation=None,
        )

        assert len(safety_result["warnings"]) > 0
        assert "too small" in safety_result["warnings"][0]
        assert "increasing portion" in safety_result["recommendations"][0]

    def test_oversized_portion_fails_safety_check(self) -> None:
        """Portion too large should fail safety check."""
        safety_result = HealthCalculator.validate_portion_safety(
            calculated_portion=600.0,  # 60g/kg for 10kg dog - too large
            dog_weight=10.0,
            life_stage=LifeStage.ADULT,
            special_diets=[],
            diet_validation=None,
        )

        assert safety_result["safe"] is False
        assert len(safety_result["warnings"]) > 0
        assert "too large" in safety_result["warnings"][0]

    def test_puppy_portion_has_different_thresholds(self) -> None:
        """Puppies should have different (higher) portion thresholds."""
        # Same portion size, different life stage
        adult_result = HealthCalculator.validate_portion_safety(
            calculated_portion=400.0,  # 40g/kg
            dog_weight=10.0,
            life_stage=LifeStage.ADULT,
            special_diets=[],
            diet_validation=None,
        )

        puppy_result = HealthCalculator.validate_portion_safety(
            calculated_portion=400.0,  # 40g/kg
            dog_weight=10.0,
            life_stage=LifeStage.PUPPY,
            special_diets=[],
            diet_validation=None,
        )

        # Should be safer for puppies (higher threshold)
        assert len(puppy_result["warnings"]) <= len(adult_result["warnings"])

    def test_prescription_diet_adds_vet_recommendation(self) -> None:
        """Prescription diets should recommend veterinary verification."""
        safety_result = HealthCalculator.validate_portion_safety(
            calculated_portion=200.0,
            dog_weight=10.0,
            life_stage=LifeStage.ADULT,
            special_diets=["prescription", "diabetic"],
            diet_validation=None,
        )

        recommendations = " ".join(safety_result["recommendations"])
        assert "veterinarian" in recommendations.lower()

    def test_diet_conflicts_add_monitoring_warning(self) -> None:
        """Diet conflicts should add monitoring warnings."""
        diet_validation = {
            "conflicts": [{"type": "age_conflict", "message": "Conflicting diets"}],
            "warnings": [],
        }

        safety_result = HealthCalculator.validate_portion_safety(
            calculated_portion=200.0,
            dog_weight=10.0,
            life_stage=LifeStage.ADULT,
            special_diets=["puppy_formula", "senior_formula"],
            diet_validation=diet_validation,
        )

        assert safety_result["safe"] is False  # Conflicts make it unsafe
        warnings_text = " ".join(safety_result["warnings"])
        assert "conflict" in warnings_text.lower()

    def test_vet_consultation_recommended_adds_recommendation(self) -> None:
        """Vet consultation recommendation should be included."""
        diet_validation = {
            "conflicts": [],
            "warnings": [],
            "recommended_vet_consultation": True,
        }

        safety_result = HealthCalculator.validate_portion_safety(
            calculated_portion=200.0,
            dog_weight=10.0,
            life_stage=LifeStage.ADULT,
            special_diets=["raw_diet", "kidney_support"],
            diet_validation=diet_validation,
        )

        recommendations_text = " ".join(safety_result["recommendations"])
        assert "veterinary consultation" in recommendations_text.lower()


class TestPortionAdjustmentFactorIntegration:
    """Test integration of diet validation into portion adjustment factor."""

    def test_clean_health_metrics_no_diet_validation(self) -> None:
        """Healthy dog with no diet validation should get neutral adjustment."""
        health_metrics = HealthMetrics(
            current_weight=20.0,
            ideal_weight=20.0,
            body_condition_score=BodyConditionScore.IDEAL,
            health_conditions=[],
            special_diet=[],
        )

        adjustment = HealthCalculator.calculate_portion_adjustment_factor(
            health_metrics, feeding_goals=None, diet_validation=None
        )

        assert adjustment == 1.0

    def test_overweight_dog_with_diet_conflicts_compounds_reduction(self) -> None:
        """Overweight dog with diet conflicts should get compounded reduction."""
        health_metrics = HealthMetrics(
            current_weight=25.0,
            ideal_weight=20.0,
            body_condition_score=BodyConditionScore.OVERWEIGHT,
            health_conditions=[],
            special_diet=["weight_control", "senior_formula"],
        )

        diet_validation = {"conflicts": [
            {"type": "age_conflict"}], "warnings": []}

        adjustment = HealthCalculator.calculate_portion_adjustment_factor(
            health_metrics, feeding_goals=None, diet_validation=diet_validation
        )

        # Should be less than 1.0 due to both BCS and diet conflicts
        assert adjustment < 1.0
        assert adjustment >= 0.5  # Reasonable lower bound

    def test_underweight_puppy_with_weight_warning_balances_factors(self) -> None:
        """Underweight puppy with weight control warning should balance factors."""
        health_metrics = HealthMetrics(
            current_weight=8.0,
            ideal_weight=12.0,
            body_condition_score=BodyConditionScore.UNDERWEIGHT,
            life_stage=LifeStage.PUPPY,
            health_conditions=[],
            special_diet=["weight_control", "puppy_formula"],
        )

        diet_validation = {
            "conflicts": [],
            "warnings": [{"type": "weight_puppy_warning"}],
        }

        adjustment = HealthCalculator.calculate_portion_adjustment_factor(
            health_metrics, feeding_goals=None, diet_validation=diet_validation
        )

        # Underweight BCS increases portions, puppy warning also increases
        # Should be above 1.0 despite weight control diet
        assert adjustment >= 1.0

    def test_diabetic_dog_with_prescription_warning_conservative_approach(self) -> None:
        """Diabetic dog with prescription diet warnings should be conservative."""
        health_metrics = HealthMetrics(
            current_weight=15.0,
            ideal_weight=15.0,
            body_condition_score=BodyConditionScore.IDEAL,
            health_conditions=["diabetes"],
            special_diet=["diabetic", "prescription"],
        )

        diet_validation = {
            "conflicts": [],
            "warnings": [{"type": "multiple_prescription_warning"}],
            "recommended_vet_consultation": True,
        }

        adjustment = HealthCalculator.calculate_portion_adjustment_factor(
            health_metrics, feeding_goals=None, diet_validation=diet_validation
        )

        # Multiple reductions: diabetes (0.9), diabetic diet (0.85),
        # prescription warning (0.95), vet consultation (0.95)
        assert adjustment < 0.9  # Should be quite conservative

    def test_weight_loss_goal_with_diet_conflicts_extra_conservative(self) -> None:
        """Weight loss goal with diet conflicts should be extra conservative."""
        health_metrics = HealthMetrics(
            current_weight=30.0,
            ideal_weight=25.0,
            body_condition_score=BodyConditionScore.HEAVY,
            health_conditions=[],
            special_diet=["weight_control", "low_fat"],
        )

        diet_validation = {"conflicts": [
            {"type": "age_conflict"}], "warnings": []}

        feeding_goals = {"weight_goal": "lose"}

        adjustment = HealthCalculator.calculate_portion_adjustment_factor(
            health_metrics, feeding_goals, diet_validation
        )

        # Should combine: BCS reduction (0.8), weight loss goal (0.8),
        # age conflict (0.9), special diets (0.85 * 0.9)
        assert adjustment < 0.7  # Should be quite low for weight loss

    def test_adjustment_factor_bounds_are_enforced(self) -> None:
        """Adjustment factor should always be within reasonable bounds."""
        # Test extreme case
        health_metrics = HealthMetrics(
            current_weight=5.0,
            ideal_weight=20.0,  # Severely underweight
            body_condition_score=BodyConditionScore.EMACIATED,
            health_conditions=["cancer"],  # Increases calories
            special_diet=["puppy_formula"],  # Increases calories
        )

        diet_validation = {
            "conflicts": [],
            "warnings": [{"type": "weight_puppy_warning"}],  # Increases
            "recommended_vet_consultation": False,
        }

        feeding_goals = {"weight_goal": "gain"}  # Increases

        adjustment = HealthCalculator.calculate_portion_adjustment_factor(
            health_metrics, feeding_goals, diet_validation
        )

        # Even with many increases, should be bounded
        assert adjustment <= 2.0
        assert adjustment >= 0.5


@pytest.mark.asyncio
class TestDietInteractionEffects:
    """Test diet interaction analysis functionality."""

    def test_synergistic_diets_detected(self) -> None:
        """Synergistic diet combinations should be detected."""
        special_diets = ["senior_formula", "joint_support", "low_fat"]

        interactions = HealthCalculator.get_diet_interaction_effects(
            special_diets)

        # Should detect senior + joint support and senior + low fat synergies
        assert len(interactions["synergistic"]) >= 2
        assert interactions["risk_level"] == "low"

    def test_conflicting_diets_detected(self) -> None:
        """Conflicting diet combinations should be detected."""
        special_diets = ["puppy_formula", "senior_formula"]

        interactions = HealthCalculator.get_diet_interaction_effects(
            special_diets)

        # Should detect puppy vs senior conflict
        assert len(interactions["conflicting"]) >= 1
        assert interactions["risk_level"] == "high"

    def test_caution_combinations_detected(self) -> None:
        """Combinations requiring caution should be detected."""
        special_diets = ["raw_diet", "prescription"]

        interactions = HealthCalculator.get_diet_interaction_effects(
            special_diets)

        # Should detect raw + prescription caution
        assert len(interactions["caution"]) >= 1
        assert interactions["risk_level"] == "medium"

    def test_complex_diet_combination_analysis(self) -> None:
        """Complex diet combinations should be properly analyzed."""
        special_diets = [
            "senior_formula",
            "joint_support",  # Synergistic
            "low_fat",
            "weight_control",  # Synergistic
            "raw_diet",
            "prescription",  # Caution
        ]

        interactions = HealthCalculator.get_diet_interaction_effects(
            special_diets)

        assert interactions["overall_complexity"] == 6
        assert len(interactions["synergistic"]) >= 2
        assert len(interactions["caution"]) >= 1
        assert len(interactions["recommendations"]) >= 2


if __name__ == "__main__":
    pytest.main([__file__])
