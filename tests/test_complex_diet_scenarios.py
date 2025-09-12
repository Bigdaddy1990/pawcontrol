"""Comprehensive tests for complex multi-diet scenarios with health-aware feeding.

Quality Scale: Platinum
Home Assistant: 2025.9.0+
Python: 3.13+

Tests complex real-world scenarios combining multiple special diets,
health conditions, age factors, and validation conflicts to ensure
robust portion calculation and safety validation.
"""

from __future__ import annotations

import sys
from importlib import util
from pathlib import Path
from unittest.mock import patch

import pytest

# Import modules
FEEDING_SPEC = util.spec_from_file_location(
    "feeding_manager",
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "pawcontrol"
    / "feeding_manager.py",
)

HEALTH_SPEC = util.spec_from_file_location(
    "health_calculator",
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "pawcontrol"
    / "health_calculator.py",
)

CONFIG_DOGS_SPEC = util.spec_from_file_location(
    "config_flow_dogs",
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "pawcontrol"
    / "config_flow_dogs.py",
)

feeding_manager = util.module_from_spec(FEEDING_SPEC)
sys.modules[FEEDING_SPEC.name] = feeding_manager
FEEDING_SPEC.loader.exec_module(feeding_manager)

health_calculator = util.module_from_spec(HEALTH_SPEC)
sys.modules[HEALTH_SPEC.name] = health_calculator
HEALTH_SPEC.loader.exec_module(health_calculator)

config_flow_dogs = util.module_from_spec(CONFIG_DOGS_SPEC)
sys.modules[CONFIG_DOGS_SPEC.name] = config_flow_dogs
CONFIG_DOGS_SPEC.loader.exec_module(config_flow_dogs)

FeedingManager = feeding_manager.FeedingManager
FeedingConfig = feeding_manager.FeedingConfig
MealType = feeding_manager.MealType
HealthCalculator = health_calculator.HealthCalculator
HealthMetrics = health_calculator.HealthMetrics
BodyConditionScore = health_calculator.BodyConditionScore
LifeStage = health_calculator.LifeStage
ActivityLevel = health_calculator.ActivityLevel


@pytest.mark.asyncio
class TestComplexMultiDietScenarios:
    """Test complex real-world multi-diet scenarios."""

    async def test_senior_diabetic_dog_with_multiple_conditions(self) -> None:
        """Test senior diabetic dog with kidney disease and multiple special diets."""
        manager = FeedingManager()

        # Complex senior dog scenario
        diet_validation = {
            "conflicts": [],
            "warnings": [
                {
                    "type": "multiple_prescription_warning",
                    "message": "Multiple prescription diets require coordination",
                    "diets": ["diabetic", "kidney_support", "prescription"],
                },
                {
                    "type": "low_fat_activity_warning",
                    "message": "Low fat diet with joint support needs",
                    "diets": ["low_fat", "joint_support"],
                },
            ],
            "total_diets": 6,
            "recommended_vet_consultation": True,
        }

        dogs = [
            {
                "dog_id": "senior_complex",
                "feeding_config": {
                    "meals_per_day": 3,  # More frequent meals for diabetic management
                    "daily_food_amount": 320.0,  # Reduced for weight management
                    "special_diet": [
                        "senior_formula",
                        "diabetic",
                        "kidney_support",
                        "low_fat",
                        "joint_support",
                        "prescription",
                    ],
                    "health_aware_portions": True,
                    "dog_weight": 22.0,
                    "ideal_weight": 18.0,  # Overweight
                    "age_months": 120,  # 10 years old
                    "breed_size": "large",
                    "activity_level": "low",
                    "body_condition_score": 7,  # Overweight
                    "health_conditions": ["diabetes", "kidney_disease", "arthritis"],
                    "weight_goal": "lose",
                    "spayed_neutered": True,
                    "diet_validation": diet_validation,
                    "medication_with_meals": True,
                },
            }
        ]

        await manager.async_initialize(dogs)

        # Test comprehensive portion validation
        result = await manager.async_validate_portion_with_diet(
            "senior_complex", "breakfast"
        )

        # Should be very conservative due to multiple factors
        calculated_portion = result["portion"]
        base_portion = 320.0 / 3  # ~107g base

        # Portion should be significantly reduced
        assert calculated_portion < base_portion * 0.8, (
            "Should be reduced for multiple conditions"
        )
        assert calculated_portion > 50, (
            "Should not be too restrictive for nutritional needs"
        )

        # Should flag safety concerns
        safety = result["safety_validation"]
        assert len(safety["warnings"]) > 0 or not safety["safe"], (
            "Should have safety warnings"
        )

        # Should recommend vet consultation
        diet_summary = result["diet_validation_summary"]
        assert diet_summary["vet_consultation_recommended"] is True
        assert diet_summary["warning_count"] == 2

        # Should include prescription diet recommendations
        recommendations = " ".join(safety["recommendations"])
        assert "veterinarian" in recommendations.lower()

    async def test_young_puppy_conflicting_diets_growth_needs(self) -> None:
        """Test young puppy with conflicting weight control vs growth needs."""
        manager = FeedingManager()

        # Challenging puppy scenario - overweight but still growing
        conflict_validation = {
            "conflicts": [
                {
                    "type": "age_conflict",
                    "message": "Weight control diet conflicts with puppy growth needs",
                    "diets": ["puppy_formula", "weight_control"],
                }
            ],
            "warnings": [
                {
                    "type": "weight_puppy_warning",
                    "message": "Weight management in growing puppies requires careful monitoring",
                    "diets": ["weight_control", "puppy_formula"],
                }
            ],
            "total_diets": 3,
            "recommended_vet_consultation": True,
        }

        dogs = [
            {
                "dog_id": "puppy_conflict",
                "feeding_config": {
                    "meals_per_day": 4,  # Frequent meals for puppy
                    "daily_food_amount": 400.0,
                    "special_diet": [
                        "puppy_formula",
                        "weight_control",
                        "sensitive_stomach",
                    ],
                    "health_aware_portions": True,
                    "dog_weight": 12.0,
                    "ideal_weight": 10.0,  # Slightly overweight puppy
                    "age_months": 8,  # Young puppy
                    "breed_size": "medium",
                    "activity_level": "high",  # Active puppy
                    "body_condition_score": 6,  # Slightly overweight
                    "health_conditions": [],
                    "weight_goal": "lose",  # But needs growth support
                    "spayed_neutered": False,  # Too young
                    "diet_validation": conflict_validation,
                },
            }
        ]

        await manager.async_initialize(dogs)

        # Test conflict handling
        result = await manager.async_validate_portion_with_diet(
            "puppy_conflict", "breakfast"
        )

        # Should balance growth needs vs weight management
        calculated_portion = result["portion"]
        base_portion = 400.0 / 4  # 100g base

        # Should not be too restrictive for growing puppy
        assert calculated_portion >= base_portion * 0.85, (
            "Should support growth despite weight goal"
        )

        # Should flag as unsafe due to conflicts
        safety = result["safety_validation"]
        assert safety["safe"] is False, "Conflicts should flag as unsafe"

        # Should have conflict information
        diet_summary = result["diet_validation_summary"]
        assert diet_summary["conflict_count"] == 1
        assert diet_summary["warning_count"] == 1
        assert diet_summary["vet_consultation_recommended"] is True

    async def test_raw_diet_with_medical_conditions_complex_warnings(self) -> None:
        """Test raw diet combined with multiple medical conditions requiring warnings."""
        manager = FeedingManager()

        # Raw diet with medical complexity
        medical_validation = {
            "conflicts": [],
            "warnings": [
                {
                    "type": "raw_medical_warning",
                    "message": "Raw diet with kidney disease and diabetes requires strict monitoring",
                    "diets": ["raw_diet", "kidney_support", "diabetic"],
                },
                {
                    "type": "multiple_prescription_warning",
                    "message": "Multiple prescription diets with raw feeding",
                    "diets": ["prescription", "diabetic", "kidney_support"],
                },
                {
                    "type": "hypoallergenic_warning",
                    "message": "Hypoallergenic requirements with raw diet complexity",
                    "diets": ["hypoallergenic", "raw_diet"],
                },
            ],
            "total_diets": 6,
            "recommended_vet_consultation": True,
        }

        dogs = [
            {
                "dog_id": "raw_medical_complex",
                "feeding_config": {
                    "meals_per_day": 3,  # Frequent monitoring needed
                    "daily_food_amount": 380.0,
                    "special_diet": [
                        "raw_diet",
                        "prescription",
                        "diabetic",
                        "kidney_support",
                        "hypoallergenic",
                        "organic",
                    ],
                    "health_aware_portions": True,
                    "dog_weight": 28.0,
                    "ideal_weight": 26.0,  # Slightly overweight
                    "age_months": 84,  # 7 years old
                    "breed_size": "large",
                    "activity_level": "moderate",
                    "body_condition_score": 6,
                    "health_conditions": ["diabetes", "kidney_disease", "allergies"],
                    "weight_goal": "lose",
                    "spayed_neutered": True,
                    "diet_validation": medical_validation,
                },
            }
        ]

        await manager.async_initialize(dogs)

        # Test medical warning handling
        result = await manager.async_validate_portion_with_diet(
            "raw_medical_complex", "dinner"
        )

        # Should be very conservative with medical conditions
        calculated_portion = result["portion"]
        base_portion = 380.0 / 3  # ~127g base

        # Multiple warnings should reduce portion
        assert calculated_portion < base_portion * 0.9, (
            "Medical warnings should reduce portions"
        )

        # Should have extensive warnings
        diet_summary = result["diet_validation_summary"]
        assert diet_summary["warning_count"] == 3
        assert diet_summary["vet_consultation_recommended"] is True

        # Should recommend careful monitoring
        safety = result["safety_validation"]
        recommendations = " ".join(safety["recommendations"])
        assert (
            "monitoring" in recommendations.lower()
            or "veterinary" in recommendations.lower()
        )

    async def test_giant_breed_puppy_multiple_support_diets(self) -> None:
        """Test giant breed puppy with multiple support diets for development."""
        manager = FeedingManager()

        # Giant breed puppy - special growth needs
        support_validation = {
            "conflicts": [],
            "warnings": [],  # These should be synergistic
            "total_diets": 4,
            "recommended_vet_consultation": False,  # Good combination
        }

        dogs = [
            {
                "dog_id": "giant_puppy",
                "feeding_config": {
                    "meals_per_day": 4,  # Frequent meals for growth
                    "daily_food_amount": 800.0,  # Large amount for giant breed
                    "special_diet": [
                        "puppy_formula",
                        "joint_support",
                        "organic",
                        "dental_care",
                    ],
                    "health_aware_portions": True,
                    "dog_weight": 35.0,  # Large puppy
                    "ideal_weight": 35.0,  # Perfect weight
                    "age_months": 12,  # 1 year old
                    "breed_size": "giant",
                    "activity_level": "high",
                    "body_condition_score": 5,  # Ideal
                    "health_conditions": [],
                    "weight_goal": "maintain",
                    "spayed_neutered": False,  # Too young
                    "diet_validation": support_validation,
                },
            }
        ]

        await manager.async_initialize(dogs)

        # Test synergistic diet handling
        result = await manager.async_validate_portion_with_diet(
            "giant_puppy", "breakfast"
        )

        # Should support growth with no major reductions
        calculated_portion = result["portion"]
        base_portion = 800.0 / 4  # 200g base

        # Should maintain or slightly increase for growth
        assert calculated_portion >= base_portion * 0.95, (
            "Should support giant breed growth"
        )

        # Should be safe with good diet combination
        safety = result["safety_validation"]
        assert safety["safe"] is True, "Good diet combinations should be safe"

        # Should not require vet consultation for synergistic diets
        diet_summary = result["diet_validation_summary"]
        assert diet_summary["vet_consultation_recommended"] is False

    async def test_senior_with_all_age_related_conditions(self) -> None:
        """Test very senior dog with comprehensive age-related conditions."""
        manager = FeedingManager()

        # Maximum complexity senior scenario
        senior_validation = {
            "conflicts": [],
            "warnings": [
                {
                    "type": "multiple_prescription_warning",
                    "message": "Complex prescription diet management",
                    "diets": ["prescription", "kidney_support"],
                }
            ],
            "total_diets": 7,
            "recommended_vet_consultation": True,
        }

        dogs = [
            {
                "dog_id": "senior_comprehensive",
                "feeding_config": {
                    "meals_per_day": 4,  # Small frequent meals for senior
                    "daily_food_amount": 250.0,  # Reduced for low activity
                    "special_diet": [
                        "senior_formula",
                        "prescription",
                        "kidney_support",
                        "low_fat",
                        "joint_support",
                        "dental_care",
                        "sensitive_stomach",
                    ],
                    "health_aware_portions": True,
                    "dog_weight": 8.0,
                    # Slightly underweight (common in seniors)
                    "ideal_weight": 9.0,
                    "age_months": 168,  # 14 years old
                    "breed_size": "small",
                    "activity_level": "very_low",
                    "body_condition_score": 4,  # Slightly underweight
                    "health_conditions": [
                        "kidney_disease",
                        "arthritis",
                        "dental_problems",
                        "digestive_issues",
                        "heart_disease",
                    ],
                    "weight_goal": "gain",  # Need to gain weight
                    "spayed_neutered": True,
                    "diet_validation": senior_validation,
                    "medication_with_meals": True,
                },
            }
        ]

        await manager.async_initialize(dogs)

        # Test comprehensive senior care
        result = await manager.async_validate_portion_with_diet(
            "senior_comprehensive", "breakfast"
        )

        # Should be carefully calculated for senior needs
        calculated_portion = result["portion"]
        base_portion = 250.0 / 4  # 62.5g base

        # Should account for multiple conditions but support weight gain
        assert calculated_portion >= base_portion * 0.8, "Should not be too restrictive"
        assert calculated_portion <= base_portion * 1.2, "Should not be excessive"

        # Should require careful monitoring
        diet_summary = result["diet_validation_summary"]
        assert diet_summary["vet_consultation_recommended"] is True

        # Should have appropriate portion size for small senior
        safety = result["safety_validation"]
        portion_per_kg = safety["portion_per_kg"]
        assert portion_per_kg >= 7, "Should meet minimum for small senior dog"
        assert portion_per_kg <= 15, "Should not exceed maximum for senior"

    async def test_extreme_diet_complexity_boundary_testing(self) -> None:
        """Test extreme diet complexity to validate boundary conditions."""
        manager = FeedingManager()

        # Maximum complexity scenario
        extreme_validation = {
            "conflicts": [
                {
                    "type": "age_conflict",
                    "message": "Age-based diet conflict",
                    "diets": ["puppy_formula", "senior_formula"],
                }
            ],
            "warnings": [
                {
                    "type": "multiple_prescription_warning",
                    "message": "Too many prescription diets",
                    "diets": ["prescription", "diabetic", "kidney_support"],
                },
                {
                    "type": "raw_medical_warning",
                    "message": "Raw diet with medical issues",
                    "diets": ["raw_diet", "prescription"],
                },
                {
                    "type": "hypoallergenic_warning",
                    "message": "Hypoallergenic conflicts",
                    "diets": ["hypoallergenic", "raw_diet"],
                },
            ],
            "total_diets": 10,  # Maximum complexity
            "recommended_vet_consultation": True,
        }

        dogs = [
            {
                "dog_id": "extreme_complexity",
                "feeding_config": {
                    "meals_per_day": 5,  # Maximum frequency
                    "daily_food_amount": 600.0,
                    "special_diet": [
                        "puppy_formula",
                        "senior_formula",  # Conflicting
                        "prescription",
                        "diabetic",
                        "kidney_support",  # Multiple prescriptions
                        "raw_diet",
                        "hypoallergenic",
                        "organic",  # Conflicting approaches
                        "weight_control",
                        "joint_support",  # Additional complexity
                    ],
                    "health_aware_portions": True,
                    "dog_weight": 25.0,
                    "ideal_weight": 22.0,
                    "age_months": 60,  # 5 years old
                    "breed_size": "medium",
                    "activity_level": "moderate",
                    "body_condition_score": 7,  # Overweight
                    "health_conditions": ["diabetes", "allergies", "arthritis"],
                    "weight_goal": "lose",
                    "spayed_neutered": True,
                    "diet_validation": extreme_validation,
                },
            }
        ]

        await manager.async_initialize(dogs)

        # Test extreme complexity handling
        result = await manager.async_validate_portion_with_diet(
            "extreme_complexity", "lunch"
        )

        # Should handle extreme complexity gracefully
        calculated_portion = result["portion"]
        base_portion = 600.0 / 5  # 120g base

        # Should be very conservative due to conflicts and warnings
        assert calculated_portion < base_portion * 0.7, "Should be very conservative"
        assert calculated_portion >= 50, "Should maintain minimum nutritional needs"

        # Should flag as unsafe due to conflicts
        safety = result["safety_validation"]
        assert safety["safe"] is False, "Extreme conflicts should be unsafe"

        # Should have maximum warning levels
        diet_summary = result["diet_validation_summary"]
        assert diet_summary["conflict_count"] == 1
        assert diet_summary["warning_count"] == 3
        assert diet_summary["vet_consultation_recommended"] is True

        # Should recommend immediate veterinary attention
        recommendations = " ".join(safety["recommendations"])
        assert "veterinary" in recommendations.lower()

    async def test_diet_validation_adjustment_factor_calculations(self) -> None:
        """Test that diet validation adjustment factors are correctly calculated."""

        # Test various validation scenarios and their adjustment factors
        test_scenarios = [
            {
                "name": "no_validation",
                "diet_validation": None,
                "expected_adjustment": 1.0,
            },
            {
                "name": "single_conflict",
                "diet_validation": {
                    "conflicts": [{"type": "age_conflict"}],
                    "warnings": [],
                    "recommended_vet_consultation": False,
                },
                "expected_adjustment": 0.9,  # 10% reduction
            },
            {
                "name": "multiple_warnings",
                "diet_validation": {
                    "conflicts": [],
                    "warnings": [
                        {"type": "multiple_prescription_warning"},
                        {"type": "raw_medical_warning"},
                    ],
                    "recommended_vet_consultation": True,
                },
                "expected_adjustment": 0.95 * 0.95 * 0.95,  # Compound reductions
            },
            {
                "name": "complex_combination",
                "diet_validation": {
                    "conflicts": [{"type": "age_conflict"}],
                    "warnings": [{"type": "multiple_prescription_warning"}],
                    "total_diets": 5,
                    "recommended_vet_consultation": True,
                },
                "expected_adjustment": 0.9 * 0.95 * 0.97 * 0.95,  # All factors
            },
        ]

        for scenario in test_scenarios:
            # Create health metrics
            health_metrics = HealthMetrics(
                current_weight=20.0,
                ideal_weight=20.0,
                body_condition_score=BodyConditionScore.IDEAL,
                health_conditions=[],
                special_diet=["grain_free", "senior_formula"],
            )

            # Calculate adjustment factor
            calculated_adjustment = (
                HealthCalculator.calculate_diet_validation_adjustment(
                    scenario["diet_validation"] or {}, health_metrics.special_diet
                )
            )

            # Verify within reasonable bounds and close to expected
            assert 0.8 <= calculated_adjustment <= 1.1, (
                f"Adjustment out of bounds for {scenario['name']}"
            )

            if scenario["expected_adjustment"] != 1.0:
                # Allow some variance for complex calculations
                assert (
                    abs(calculated_adjustment - scenario["expected_adjustment"]) < 0.1
                ), (
                    f"Adjustment factor mismatch for {scenario['name']}: expected {scenario['expected_adjustment']}, got {calculated_adjustment}"
                )

    async def test_portion_safety_validation_complex_scenarios(self) -> None:
        """Test portion safety validation with complex diet scenarios."""

        # Test safety validation with various complex scenarios
        safety_scenarios = [
            {
                "name": "safe_senior_portion",
                "portion": 150.0,
                "weight": 15.0,
                "life_stage": LifeStage.SENIOR,
                "special_diets": ["senior_formula", "joint_support"],
                "diet_validation": None,
                "expected_safe": True,
            },
            {
                "name": "unsafe_tiny_portion",
                "portion": 30.0,  # Too small
                "weight": 20.0,
                "life_stage": LifeStage.ADULT,
                "special_diets": ["grain_free"],
                "diet_validation": None,
                "expected_safe": True,  # Warning but not unsafe
            },
            {
                "name": "unsafe_huge_portion",
                "portion": 800.0,  # Too large
                "weight": 10.0,
                "life_stage": LifeStage.ADULT,
                "special_diets": [],
                "diet_validation": None,
                "expected_safe": False,
            },
            {
                "name": "prescription_diet_safety",
                "portion": 200.0,
                "weight": 25.0,
                "life_stage": LifeStage.ADULT,
                "special_diets": ["prescription", "diabetic"],
                "diet_validation": None,
                "expected_safe": True,
            },
            {
                "name": "conflict_diet_unsafe",
                "portion": 150.0,
                "weight": 15.0,
                "life_stage": LifeStage.PUPPY,
                "special_diets": ["puppy_formula", "senior_formula"],
                "diet_validation": {
                    "conflicts": [{"type": "age_conflict"}],
                    "warnings": [],
                },
                "expected_safe": False,
            },
        ]

        for scenario in safety_scenarios:
            safety_result = HealthCalculator.validate_portion_safety(
                calculated_portion=scenario["portion"],
                dog_weight=scenario["weight"],
                life_stage=scenario["life_stage"],
                special_diets=scenario["special_diets"],
                diet_validation=scenario["diet_validation"],
            )

            assert safety_result["safe"] == scenario["expected_safe"], (
                f"Safety validation failed for {scenario['name']}: expected {scenario['expected_safe']}, got {safety_result['safe']}"
            )

            # Check that portion per kg is calculated
            expected_portion_per_kg = scenario["portion"] / scenario["weight"]
            assert (
                abs(safety_result["portion_per_kg"] - expected_portion_per_kg) < 0.1
            ), f"Portion per kg calculation incorrect for {scenario['name']}"

            # Prescription diets should have vet recommendations
            if "prescription" in scenario["special_diets"]:
                recommendations = " ".join(safety_result["recommendations"])
                assert "veterinarian" in recommendations.lower(), (
                    f"Prescription diet should recommend vet consultation in {scenario['name']}"
                )

    async def test_health_aware_feeding_integration_end_to_end(self) -> None:
        """Test complete end-to-end health-aware feeding with diet validation."""
        manager = FeedingManager()

        # Realistic complex scenario
        dogs = [
            {
                "dog_id": "integration_test",
                "feeding_config": {
                    "meals_per_day": 2,
                    "daily_food_amount": 400.0,
                    "special_diet": ["senior_formula", "joint_support", "low_fat"],
                    "health_aware_portions": True,
                    "dog_weight": 25.0,
                    "ideal_weight": 23.0,
                    "age_months": 96,  # 8 years old
                    "breed_size": "large",
                    "activity_level": "moderate",
                    "body_condition_score": 6,  # Slightly overweight
                    "health_conditions": ["arthritis"],
                    "weight_goal": "lose",
                    "spayed_neutered": True,
                    "diet_validation": {
                        "conflicts": [],
                        "warnings": [],
                        "total_diets": 3,
                        "recommended_vet_consultation": False,
                    },
                },
            }
        ]

        await manager.async_initialize(dogs)

        # Test complete feeding workflow

        # 1. Calculate health-aware portion
        breakfast_portion = await manager.async_calculate_health_aware_portion(
            "integration_test", "breakfast"
        )
        assert breakfast_portion is not None, "Should calculate health-aware portion"
        assert breakfast_portion > 0, "Portion should be positive"

        # 2. Validate portion with diet considerations
        validation_result = await manager.async_validate_portion_with_diet(
            "integration_test", "breakfast"
        )
        assert validation_result["portion"] == breakfast_portion, (
            "Portions should match"
        )
        assert validation_result["safety_validation"]["safe"] is True, "Should be safe"

        # 3. Record actual feeding
        feeding_event = await manager.async_add_feeding(
            "integration_test", breakfast_portion, "breakfast"
        )
        assert feeding_event.amount == breakfast_portion, (
            "Feeding amount should match calculated portion"
        )
        assert feeding_event.portion_size == breakfast_portion, (
            "Portion size should be calculated"
        )

        # 4. Get feeding analysis
        feeding_analysis = await manager.async_analyze_feeding_health(
            "integration_test", 7
        )
        assert feeding_analysis["status"] != "insufficient_data", (
            "Should have feeding data"
        )

        # 5. Generate health report
        health_report = await manager.async_generate_health_report("integration_test")
        assert health_report is not None, "Should generate health report"
        assert "feeding_insights" in health_report, "Should include feeding insights"

        # 6. Update health data and verify portion recalculation
        update_success = await manager.async_update_health_data(
            "integration_test",
            {"weight": 24.0},  # Weight loss progress
        )
        assert update_success is True, "Should update health data successfully"

        # 7. Verify portion adjustment after weight change
        new_portion = await manager.async_calculate_health_aware_portion(
            "integration_test", "dinner"
        )
        # Portion might change slightly with weight update
        assert new_portion is not None, "Should recalculate with new weight"

    async def test_diet_compatibility_matrix_validation(self) -> None:
        """Test diet compatibility matrix validation from config flow."""

        # Import diet validation logic from config flow
        validation_logic = config_flow_dogs.DogManagementMixin()

        # Test various diet combinations
        compatibility_tests = [
            {
                "diets": ["puppy_formula", "senior_formula"],
                "should_have_conflicts": True,
                "conflict_type": "age_conflict",
            },
            {
                "diets": ["prescription", "diabetic", "kidney_support"],
                "should_have_conflicts": False,
                "should_have_warnings": True,
                "warning_type": "multiple_prescription_warning",
            },
            {
                "diets": ["raw_diet", "prescription"],
                "should_have_conflicts": False,
                "should_have_warnings": True,
                "warning_type": "raw_medical_warning",
            },
            {
                "diets": ["senior_formula", "joint_support", "low_fat"],
                "should_have_conflicts": False,
                "should_have_warnings": False,
                "should_recommend_vet": False,
            },
            {
                "diets": ["weight_control", "puppy_formula"],
                "should_have_conflicts": False,
                "should_have_warnings": True,
                "warning_type": "weight_puppy_warning",
            },
        ]

        for test_case in compatibility_tests:
            validation_result = validation_logic._validate_diet_combinations(
                test_case["diets"]
            )

            # Check conflicts
            if test_case.get("should_have_conflicts", False):
                assert len(validation_result["conflicts"]) > 0, (
                    f"Should have conflicts for diets: {test_case['diets']}"
                )
                if "conflict_type" in test_case:
                    conflict_types = [c["type"] for c in validation_result["conflicts"]]
                    assert test_case["conflict_type"] in conflict_types, (
                        f"Should have {test_case['conflict_type']} for diets: {test_case['diets']}"
                    )
            else:
                assert len(validation_result["conflicts"]) == 0, (
                    f"Should not have conflicts for diets: {test_case['diets']}"
                )

            # Check warnings
            if test_case.get("should_have_warnings", False):
                assert len(validation_result["warnings"]) > 0, (
                    f"Should have warnings for diets: {test_case['diets']}"
                )
                if "warning_type" in test_case:
                    warning_types = [w["type"] for w in validation_result["warnings"]]
                    assert test_case["warning_type"] in warning_types, (
                        f"Should have {test_case['warning_type']} for diets: {test_case['diets']}"
                    )
            else:
                assert len(validation_result["warnings"]) == 0, (
                    f"Should not have warnings for diets: {test_case['diets']}"
                )

            # Check vet consultation recommendation
            if "should_recommend_vet" in test_case:
                assert (
                    validation_result["recommended_vet_consultation"]
                    == test_case["should_recommend_vet"]
                ), (
                    f"Vet consultation recommendation incorrect for diets: {test_case['diets']}"
                )


if __name__ == "__main__":
    pytest.main([__file__])
