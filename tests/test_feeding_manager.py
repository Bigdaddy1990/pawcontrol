"""Tests for the lightweight FeedingManager."""
from __future__ import annotations

import sys
from datetime import datetime
from datetime import timedelta
from importlib import util
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

SPEC = util.spec_from_file_location(
    "feeding_manager",
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "pawcontrol"
    / "feeding_manager.py",
)

feeding_manager = util.module_from_spec(SPEC)
sys.modules[SPEC.name] = feeding_manager
SPEC.loader.exec_module(feeding_manager)

FeedingManager = feeding_manager.FeedingManager
FeedingConfig = feeding_manager.FeedingConfig
MealType = feeding_manager.MealType


@pytest.mark.asyncio
async def test_feeding_manager_returns_consistent_feedings_today() -> None:
    """Ensure feedings_today is always a dict with integer counts."""

    manager = FeedingManager()
    await manager.async_add_feeding("dog", 1.0, meal_type="breakfast")
    await manager.async_add_feeding("dog", 1.0, meal_type="dinner")

    data = await manager.async_get_feeding_data("dog")

    assert isinstance(data["feedings_today"], dict)
    assert data["feedings_today"]["breakfast"] == 1
    assert data["feedings_today"]["dinner"] == 1
    assert data["total_feedings_today"] == 2


@pytest.mark.asyncio
async def test_feeding_manager_empty_history() -> None:
    """Verify empty histories return empty mappings and zero totals."""

    manager = FeedingManager()
    data = await manager.async_get_feeding_data("dog")

    assert data["feedings_today"] == {}
    assert data["total_feedings_today"] == 0


@pytest.mark.asyncio
async def test_feeding_manager_unknown_meal_type() -> None:
    """Feeding with None meal_type is categorized as 'unknown'."""

    manager = FeedingManager()
    await manager.async_add_feeding("dog", 1.0, meal_type=None)

    data = await manager.async_get_feeding_data("dog")

    assert data["feedings_today"]["unknown"] == 1
    assert data["total_feedings_today"] == 1


@pytest.mark.asyncio
async def test_feeding_manager_ignores_feedings_from_previous_days() -> None:
    """Feedings from earlier days should not appear in today's counts."""

    fixed_now = datetime(2023, 1, 1, 12, 0, 0)
    yesterday = fixed_now - timedelta(days=1)

    with patch("feeding_manager.datetime") as mock_datetime:
        mock_datetime.utcnow.return_value = fixed_now

        manager = FeedingManager()

        # Feeding yesterday should be ignored
        await manager.async_add_feeding(
            "dog", 1.0, meal_type="breakfast", time=yesterday
        )
        # Feeding today should be counted (uses patched utcnow)
        await manager.async_add_feeding("dog", 1.0, meal_type="dinner")

        data = await manager.async_get_feeding_data("dog")

    assert data["feedings_today"] == {"dinner": 1}
    assert data["total_feedings_today"] == 1


@patch("feeding_manager.FeedingConfig._estimate_calories_per_gram", return_value=1.0)
@patch(
    "feeding_manager.HealthCalculator.calculate_portion_adjustment_factor",
    return_value=1.0,
)
@patch("feeding_manager.HealthCalculator.calculate_daily_calories", return_value=1000)
def test_single_meal_portion_not_clamped(
    mock_calories: Any, mock_adjust: Any, mock_estimate: Any
) -> None:
    """Single daily meal should not be reduced by max safety factor."""

    config = FeedingConfig(
        dog_id="dog",
        meals_per_day=1,
        dog_weight=10.0,
        ideal_weight=10.0,
        age_months=24,
    )

    portion = config.calculate_portion_size()

    assert portion == 1000.0


class TestDietValidationIntegration:
    """Test diet validation integration with feeding manager."""

    @pytest.fixture
    def sample_diet_validation(self) -> dict:
        """Sample diet validation data for testing."""
        return {
            "conflicts": [
                {
                    "type": "age_conflict",
                    "message": "Puppy formula with senior formula",
                    "diets": ["puppy_formula", "senior_formula"],
                }
            ],
            "warnings": [
                {
                    "type": "multiple_prescription_warning",
                    "message": "Multiple prescription diets need coordination",
                    "diets": ["diabetic", "kidney_support"],
                }
            ],
            "total_diets": 4,
            "recommended_vet_consultation": True,
        }

    @pytest.fixture
    def feeding_config_with_validation(self, sample_diet_validation) -> FeedingConfig:
        """Create feeding config with diet validation."""
        return FeedingConfig(
            dog_id="test_dog",
            meals_per_day=2,
            daily_food_amount=400.0,
            special_diet=[
                "puppy_formula",
                "senior_formula",
                "diabetic",
                "kidney_support",
            ],
            health_aware_portions=True,
            dog_weight=15.0,
            ideal_weight=15.0,
            age_months=8,
            diet_validation=sample_diet_validation,
        )

    def test_feeding_config_stores_diet_validation(
        self, sample_diet_validation
    ) -> None:
        """FeedingConfig should store diet validation data."""
        config = FeedingConfig(
            dog_id="test_dog", diet_validation=sample_diet_validation
        )

        assert config.diet_validation == sample_diet_validation
        assert config.diet_validation["recommended_vet_consultation"] is True

    def test_portion_calculation_uses_diet_validation(
        self, feeding_config_with_validation
    ) -> None:
        """Portion calculation should incorporate diet validation adjustments."""
        # Calculate portion with diet validation
        portion_with_validation = feeding_config_with_validation.calculate_portion_size(
            MealType.BREAKFAST
        )

        # Create config without validation for comparison
        config_without_validation = FeedingConfig(
            dog_id="test_dog",
            meals_per_day=2,
            daily_food_amount=400.0,
            special_diet=[
                "puppy_formula",
                "senior_formula",
                "diabetic",
                "kidney_support",
            ],
            health_aware_portions=True,
            dog_weight=15.0,
            ideal_weight=15.0,
            age_months=8,
            diet_validation=None,  # No validation
        )

        portion_without_validation = config_without_validation.calculate_portion_size(
            MealType.BREAKFAST
        )

        # Diet validation should reduce portion due to conflicts
        assert portion_with_validation < portion_without_validation
        assert portion_with_validation > 0  # Should still be reasonable

    def test_diet_validation_summary_generation(
        self, feeding_config_with_validation
    ) -> None:
        """Diet validation summary should provide useful information."""
        summary = feeding_config_with_validation._get_diet_validation_summary()

        assert summary["has_adjustments"] is True
        assert summary["conflict_count"] == 1
        assert summary["warning_count"] == 1
        assert summary["vet_consultation_recommended"] is True
        assert "age_conflict" in summary["adjustment_info"]
        assert "multiple_prescription_warning" in summary["adjustment_info"]

    def test_update_diet_validation_method(
        self, feeding_config_with_validation
    ) -> None:
        """update_diet_validation should update stored validation data."""
        new_validation = {
            "conflicts": [],
            "warnings": [{"type": "hypoallergenic_warning"}],
            "total_diets": 2,
            "recommended_vet_consultation": False,
        }

        feeding_config_with_validation.update_diet_validation(new_validation)

        assert feeding_config_with_validation.diet_validation == new_validation
        summary = feeding_config_with_validation._get_diet_validation_summary()
        assert summary["conflict_count"] == 0
        assert summary["warning_count"] == 1
        assert summary["vet_consultation_recommended"] is False

    def test_special_diet_info_includes_validation(
        self, feeding_config_with_validation
    ) -> None:
        """get_special_diet_info should include validation data."""
        diet_info = feeding_config_with_validation.get_special_diet_info()

        assert diet_info["has_special_diet"] is True
        assert "validation" in diet_info
        assert diet_info["validation"] == feeding_config_with_validation.diet_validation
        assert diet_info["priority_level"] == "high"  # Has prescription diets

    def test_health_summary_includes_validation_status(
        self, feeding_config_with_validation
    ) -> None:
        """get_health_summary should indicate if validation is applied."""
        health_summary = feeding_config_with_validation.get_health_summary()

        assert health_summary["diet_validation_applied"] is True

        # Test without validation
        config_no_validation = FeedingConfig(
            dog_id="test", diet_validation=None)
        health_summary_no_val = config_no_validation.get_health_summary()
        assert health_summary_no_val["diet_validation_applied"] is False


@pytest.mark.asyncio
class TestFeedingManagerDietValidation:
    """Test FeedingManager diet validation integration."""

    @pytest.fixture
    async def manager_with_validation(self) -> FeedingManager:
        """Create FeedingManager with diet validation setup."""
        manager = FeedingManager()

        # Setup dog with diet validation
        dogs = [
            {
                "dog_id": "test_dog",
                "feeding_config": {
                    "meals_per_day": 2,
                    "daily_food_amount": 400.0,
                    "special_diet": ["diabetic", "kidney_support"],
                    "health_aware_portions": True,
                    "dog_weight": 20.0,
                    "diet_validation": {
                        "conflicts": [],
                        "warnings": [
                            {
                                "type": "multiple_prescription_warning",
                                "message": "Multiple prescription diets",
                            }
                        ],
                        "recommended_vet_consultation": True,
                    },
                },
            }
        ]

        await manager.async_initialize(dogs)
        return manager

    async def test_async_update_diet_validation(self, manager_with_validation) -> None:
        """async_update_diet_validation should update validation data."""
        new_validation = {
            "conflicts": [{"type": "age_conflict", "message": "Age conflict added"}],
            "warnings": [],
            "recommended_vet_consultation": False,
        }

        result = await manager_with_validation.async_update_diet_validation(
            "test_dog", new_validation
        )

        assert result is True

        # Verify update was applied
        status = await manager_with_validation.async_get_diet_validation_status(
            "test_dog"
        )
        assert status is not None
        assert status["validation_data"] == new_validation
        assert status["summary"]["conflict_count"] == 1
        assert status["summary"]["warning_count"] == 0

    async def test_async_get_diet_validation_status(
        self, manager_with_validation
    ) -> None:
        """async_get_diet_validation_status should return current status."""
        status = await manager_with_validation.async_get_diet_validation_status(
            "test_dog"
        )

        assert status is not None
        assert "validation_data" in status
        assert "summary" in status
        assert "special_diets" in status
        assert "last_updated" in status

        # Verify content
        assert status["special_diets"] == ["diabetic", "kidney_support"]
        assert status["summary"]["warning_count"] == 1
        assert status["summary"]["vet_consultation_recommended"] is True

    async def test_async_get_diet_validation_status_no_validation(self) -> None:
        """Should return None for dogs without diet validation."""
        manager = FeedingManager()
        dogs = [
            {
                "dog_id": "simple_dog",
                "feeding_config": {
                    "meals_per_day": 2,
                    "special_diet": ["grain_free"],
                    "diet_validation": None,
                },
            }
        ]

        await manager.async_initialize(dogs)

        status = await manager.async_get_diet_validation_status("simple_dog")
        assert status is None

    async def test_async_validate_portion_with_diet(
        self, manager_with_validation
    ) -> None:
        """async_validate_portion_with_diet should return comprehensive results."""
        result = await manager_with_validation.async_validate_portion_with_diet(
            "test_dog", "breakfast"
        )

        # Verify structure
        required_keys = [
            "portion",
            "meal_type",
            "safety_validation",
            "diet_validation_summary",
            "health_aware_calculation",
            "config_id",
        ]
        for key in required_keys:
            assert key in result

        # Verify content
        assert result["portion"] > 0
        assert result["meal_type"] == "breakfast"
        assert result["health_aware_calculation"] is True
        assert result["config_id"] == "test_dog"

        # Should have diet validation summary
        assert result["diet_validation_summary"] is not None
        assert result["diet_validation_summary"]["warning_count"] == 1

        # Should have safety validation
        safety = result["safety_validation"]
        assert "safe" in safety
        assert "warnings" in safety
        assert "recommendations" in safety

    async def test_async_validate_portion_with_diet_error_handling(self) -> None:
        """Should handle errors gracefully for invalid dog IDs."""
        manager = FeedingManager()

        result = await manager.async_validate_portion_with_diet(
            "nonexistent_dog", "breakfast"
        )

        assert "error" in result
        assert result["portion"] == 0.0
        assert "No configuration found" in result["error"]

    async def test_health_aware_portion_calculation_with_validation(
        self, manager_with_validation
    ) -> None:
        """Health-aware calculation should use diet validation."""
        # Test with health data override
        override_health = {
            "weight": 22.0,  # Slightly overweight
            "health_conditions": ["diabetes"],
        }

        portion = await manager_with_validation.async_calculate_health_aware_portion(
            "test_dog", "dinner", override_health
        )

        assert portion is not None
        assert portion > 0

        # Should be conservative due to validation warnings and health conditions
        base_portion = 400.0 / 2  # daily_amount / meals_per_day
        assert portion < base_portion  # Health + validation adjustments

    async def test_feeding_with_diet_validation_logging(
        self, manager_with_validation, caplog
    ) -> None:
        """Diet validation adjustments should be logged appropriately."""
        import logging

        caplog.set_level(logging.INFO)

        # Add feeding which triggers portion calculation
        await manager_with_validation.async_add_feeding("test_dog", 180.0, "breakfast")

        # Should log validation information
        log_messages = [record.message for record in caplog.records]
        validation_logs = [
            msg for msg in log_messages if "validation" in msg.lower()]

        # At least one validation-related log should exist
        assert len(validation_logs) > 0


@pytest.mark.asyncio
class TestComplexDietScenarios:
    """Test complex multi-diet scenarios with validation."""

    async def test_senior_diabetic_dog_complex_diet(self) -> None:
        """Test senior diabetic dog with multiple special diets."""
        manager = FeedingManager()

        complex_validation = {
            "conflicts": [],
            "warnings": [
                {"type": "multiple_prescription_warning"},
                {"type": "low_fat_activity_warning"},
            ],
            "total_diets": 5,
            "recommended_vet_consultation": True,
        }

        dogs = [
            {
                "dog_id": "senior_diabetic",
                "feeding_config": {
                    "meals_per_day": 3,  # More frequent meals for diabetic
                    "daily_food_amount": 350.0,
                    "special_diet": [
                        "senior_formula",
                        "diabetic",
                        "low_fat",
                        "joint_support",
                        "prescription",
                    ],
                    "health_aware_portions": True,
                    "dog_weight": 18.0,
                    "ideal_weight": 16.0,  # Slightly overweight
                    "age_months": 108,  # 9 years old
                    "activity_level": "low",
                    "body_condition_score": 6,  # Overweight
                    "health_conditions": ["diabetes", "arthritis"],
                    "diet_validation": complex_validation,
                },
            }
        ]

        await manager.async_initialize(dogs)

        # Test portion calculation
        result = await manager.async_validate_portion_with_diet(
            "senior_diabetic", "breakfast"
        )

        # Should be quite conservative due to multiple factors
        base_portion = 350.0 / 3  # ~117g base
        calculated_portion = result["portion"]

        assert calculated_portion < base_portion  # Should be reduced
        assert calculated_portion > 50  # But not too small

        # Should recommend vet consultation
        recommendations = " ".join(
            result["safety_validation"]["recommendations"])
        assert "veterinary" in recommendations.lower()

    async def test_puppy_with_conflicting_diets(self) -> None:
        """Test puppy with conflicting diet requirements."""
        manager = FeedingManager()

        conflict_validation = {
            "conflicts": [
                {
                    "type": "age_conflict",
                    "message": "Puppy formula conflicts with weight control",
                    "diets": ["puppy_formula", "weight_control"],
                }
            ],
            "warnings": [{"type": "weight_puppy_warning"}],
            "recommended_vet_consultation": True,
        }

        dogs = [
            {
                "dog_id": "conflicted_puppy",
                "feeding_config": {
                    "meals_per_day": 4,  # Puppy needs frequent meals
                    "daily_food_amount": 300.0,
                    "special_diet": ["puppy_formula", "weight_control"],
                    "health_aware_portions": True,
                    "dog_weight": 8.0,
                    "ideal_weight": 6.0,  # Overweight puppy
                    "age_months": 6,  # Young puppy
                    "body_condition_score": 7,  # Heavy
                    "diet_validation": conflict_validation,
                },
            }
        ]

        await manager.async_initialize(dogs)

        # Test validation status
        status = await manager.async_get_diet_validation_status("conflicted_puppy")
        assert status["summary"]["conflict_count"] == 1
        assert status["summary"]["vet_consultation_recommended"] is True

        # Portion calculation should balance growth needs vs weight management
        result = await manager.async_validate_portion_with_diet(
            "conflicted_puppy", "breakfast"
        )

        # Should flag as unsafe due to conflicts
        assert result["safety_validation"]["safe"] is False

        # But portion should still support growth (puppy warning increases portions)
        base_portion = 300.0 / 4  # 75g base
        assert result["portion"] >= base_portion * 0.8  # Not too restrictive

    async def test_raw_diet_with_medical_conditions(self) -> None:
        """Test raw diet with medical conditions requiring caution."""
        manager = FeedingManager()

        medical_validation = {
            "conflicts": [],
            "warnings": [
                {
                    "type": "raw_medical_warning",
                    "message": "Raw diet with kidney disease requires monitoring",
                },
                {"type": "multiple_prescription_warning"},
            ],
            "recommended_vet_consultation": True,
        }

        dogs = [
            {
                "dog_id": "raw_medical",
                "feeding_config": {
                    "meals_per_day": 2,
                    "daily_food_amount": 450.0,
                    "special_diet": ["raw_diet", "kidney_support", "prescription"],
                    "health_aware_portions": True,
                    "dog_weight": 25.0,
                    "ideal_weight": 25.0,
                    "age_months": 72,  # 6 years
                    "health_conditions": ["kidney_disease"],
                    "diet_validation": medical_validation,
                },
            }
        ]

        await manager.async_initialize(dogs)

        # Should apply conservative adjustments
        result = await manager.async_validate_portion_with_diet("raw_medical", "dinner")

        # Multiple warnings should reduce portion
        base_portion = 450.0 / 2  # 225g base
        assert result["portion"] < base_portion

        # Should strongly recommend vet consultation
        diet_summary = result["diet_validation_summary"]
        assert diet_summary["vet_consultation_recommended"] is True
        assert diet_summary["warning_count"] == 2

        # Safety validation should include medical monitoring
        safety_recs = " ".join(result["safety_validation"]["recommendations"])
        assert (
            "monitoring" in safety_recs.lower() or "veterinary" in safety_recs.lower()
        )
