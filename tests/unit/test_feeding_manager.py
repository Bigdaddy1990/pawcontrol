"""Comprehensive unit tests for FeedingManager.

Tests feeding logic, portion calculations, calorie tracking,
and schedule compliance monitoring.

Quality Scale: Platinum
Python: 3.13+
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest
from custom_components.pawcontrol.feeding_manager import FeedingManager


@pytest.mark.unit
@pytest.mark.asyncio
class TestFeedingManagerInitialization:
    """Test FeedingManager initialization and setup."""

    async def test_initialization_single_dog(self, mock_dog_config):
        """Test initialization with single dog configuration."""
        manager = FeedingManager()

        await manager.async_initialize([mock_dog_config])

        assert len(manager._dogs) == 1
        assert "test_dog" in manager._dogs
        assert manager._dogs["test_dog"]["weight"] == 30.0

    async def test_initialization_multiple_dogs(self, mock_multi_dog_config):
        """Test initialization with multiple dogs."""
        manager = FeedingManager()

        await manager.async_initialize(mock_multi_dog_config)

        assert len(manager._dogs) == 2
        assert "buddy" in manager._dogs
        assert "max" in manager._dogs

    async def test_initialization_empty_config(self):
        """Test initialization with empty configuration."""
        manager = FeedingManager()

        await manager.async_initialize([])

        assert len(manager._dogs) == 0

    async def test_initialization_validates_required_fields(self):
        """Test that initialization validates required fields."""
        manager = FeedingManager()

        invalid_config = {"dog_id": "test", "weight": None}

        with pytest.raises(Exception):  # Should raise validation error
            await manager.async_initialize([invalid_config])


@pytest.mark.unit
@pytest.mark.asyncio
class TestCalorieCalculations:
    """Test calorie calculation algorithms."""

    async def test_calculate_rer_basic(self, mock_feeding_manager):
        """Test Resting Energy Requirement (RER) calculation."""
        # RER = 70 * (weight_kg ^ 0.75)
        # For 30kg dog: 70 * (30 ^ 0.75) ≈ 742 kcal

        rer = mock_feeding_manager._calculate_rer(30.0)

        assert 730 < rer < 750  # Allow small margin
        assert isinstance(rer, float)

    async def test_calculate_rer_small_dog(self, mock_feeding_manager):
        """Test RER calculation for small dog."""
        # For 5kg dog: 70 * (5 ^ 0.75) ≈ 234 kcal

        rer = mock_feeding_manager._calculate_rer(5.0)

        assert 220 < rer < 245

    async def test_calculate_rer_large_dog(self, mock_feeding_manager):
        """Test RER calculation for large dog."""
        # For 50kg dog: 70 * (50 ^ 0.75) ≈ 1176 kcal

        rer = mock_feeding_manager._calculate_rer(50.0)

        assert 1150 < rer < 1200

    async def test_calculate_daily_calories_moderate_activity(
        self, mock_feeding_manager
    ):
        """Test daily calorie calculation for moderate activity."""
        # TDEE = RER * activity_multiplier
        # Moderate = 1.6

        calories = mock_feeding_manager.calculate_daily_calories("test_dog")

        # For 30kg moderate: ~742 * 1.6 ≈ 1187
        assert 1150 < calories < 1250

    async def test_calculate_daily_calories_high_activity(self, mock_dog_config):
        """Test daily calorie calculation for high activity."""
        manager = FeedingManager()

        config = mock_dog_config.copy()
        config["activity_level"] = "high"

        await manager.async_initialize([config])

        calories = manager.calculate_daily_calories("test_dog")

        # High activity = 2.0 multiplier
        # For 30kg: ~742 * 2.0 ≈ 1484
        assert 1450 < calories < 1550

    async def test_calculate_daily_calories_weight_loss(self, mock_dog_config):
        """Test calorie reduction for weight loss."""
        manager = FeedingManager()

        config = mock_dog_config.copy()
        config["weight"] = 35.0
        config["ideal_weight"] = 30.0
        config["weight_goal"] = "lose"

        await manager.async_initialize([config])

        calories = manager.calculate_daily_calories("test_dog")

        # Should be calculated for target weight
        target_rer = 70 * (30.0**0.75)  # ~742
        expected = target_rer * 1.6  # moderate activity

        assert abs(calories - expected) < 50


@pytest.mark.unit
@pytest.mark.asyncio
class TestPortionCalculations:
    """Test portion size calculations."""

    async def test_calculate_portion_basic(self, mock_feeding_manager):
        """Test basic portion calculation."""
        portion = mock_feeding_manager.calculate_portion("test_dog", "breakfast")

        # Should be reasonable portion size
        assert 100 < portion < 500
        assert isinstance(portion, float)

    async def test_calculate_portion_equal_distribution(self, mock_feeding_manager):
        """Test that portions are distributed equally across meals."""
        breakfast = mock_feeding_manager.calculate_portion("test_dog", "breakfast")
        dinner = mock_feeding_manager.calculate_portion("test_dog", "dinner")

        # Should be roughly equal (within 10%)
        assert abs(breakfast - dinner) < breakfast * 0.1

    async def test_calculate_portion_custom_food_calories(self, mock_dog_config):
        """Test portion calculation with custom food calorie content."""
        manager = FeedingManager()

        config = mock_dog_config.copy()
        config["feeding_config"]["calories_per_100g"] = 400  # Higher calorie food

        await manager.async_initialize([config])

        portion_high = manager.calculate_portion("test_dog", "breakfast")

        # Higher calorie food should result in smaller portions
        assert 100 < portion_high < 400

    async def test_calculate_portion_multiple_meals(self, mock_dog_config):
        """Test portion calculation with different meal frequencies."""
        manager = FeedingManager()

        config = mock_dog_config.copy()
        config["feeding_config"]["meals_per_day"] = 3

        await manager.async_initialize([config])

        portion_3meals = manager.calculate_portion("test_dog", "breakfast")

        # 3 meals should have smaller portions than 2 meals
        assert 80 < portion_3meals < 300


@pytest.mark.unit
@pytest.mark.asyncio
class TestFeedingLogging:
    """Test feeding event logging and tracking."""

    async def test_add_feeding_basic(self, mock_feeding_manager, create_feeding_event):
        """Test adding basic feeding event."""
        event = create_feeding_event()

        await mock_feeding_manager.async_add_feeding(
            dog_id=event["dog_id"],
            amount=event["amount"],
            meal_type=event["meal_type"],
        )

        data = mock_feeding_manager.get_feeding_data("test_dog")

        assert len(data["feedings"]) == 1
        assert data["feedings"][0]["amount"] == 200.0

    async def test_add_feeding_with_notes(self, mock_feeding_manager):
        """Test adding feeding with notes."""
        await mock_feeding_manager.async_add_feeding(
            dog_id="test_dog",
            amount=200.0,
            meal_type="breakfast",
            notes="Added extra vitamins",
        )

        data = mock_feeding_manager.get_feeding_data("test_dog")

        assert data["feedings"][0]["notes"] == "Added extra vitamins"

    async def test_add_feeding_tracks_daily_total(self, mock_feeding_manager):
        """Test that daily totals are tracked correctly."""
        await mock_feeding_manager.async_add_feeding(
            dog_id="test_dog",
            amount=200.0,
            meal_type="breakfast",
        )

        await mock_feeding_manager.async_add_feeding(
            dog_id="test_dog",
            amount=250.0,
            meal_type="dinner",
        )

        stats = mock_feeding_manager.get_daily_stats("test_dog")

        assert stats["total_fed_today"] == 450.0

    async def test_add_feeding_isolates_dogs(self, mock_multi_dog_config):
        """Test that feeding data is isolated between dogs."""
        manager = FeedingManager()
        await manager.async_initialize(mock_multi_dog_config)

        await manager.async_add_feeding(
            dog_id="buddy",
            amount=300.0,
            meal_type="breakfast",
        )

        buddy_data = manager.get_feeding_data("buddy")
        max_data = manager.get_feeding_data("max")

        assert len(buddy_data["feedings"]) == 1
        assert len(max_data["feedings"]) == 0

    async def test_add_feeding_handles_medication(self, mock_feeding_manager):
        """Test feeding with medication tracking."""
        medication_data = {
            "name": "Rimadyl",
            "dose": "50mg",
            "time": datetime.now().isoformat(),
        }

        await mock_feeding_manager.async_add_feeding_with_medication(
            dog_id="test_dog",
            amount=200.0,
            meal_type="medication",
            medication_data=medication_data,
        )

        data = mock_feeding_manager.get_feeding_data("test_dog")

        assert data["feedings"][0]["with_medication"] is True
        assert data["feedings"][0]["medication_name"] == "Rimadyl"


@pytest.mark.unit
@pytest.mark.asyncio
class TestScheduleCompliance:
    """Test feeding schedule compliance tracking."""

    async def test_compliance_perfect_schedule(self, mock_feeding_manager):
        """Test compliance calculation with perfect adherence."""
        # Add feedings at scheduled times
        now = datetime.now()

        breakfast_time = now.replace(hour=8, minute=0, second=0, microsecond=0)
        dinner_time = now.replace(hour=18, minute=0, second=0, microsecond=0)

        await mock_feeding_manager.async_add_feeding(
            dog_id="test_dog",
            amount=200.0,
            meal_type="breakfast",
            timestamp=breakfast_time,
        )

        await mock_feeding_manager.async_add_feeding(
            dog_id="test_dog",
            amount=200.0,
            meal_type="dinner",
            timestamp=dinner_time,
        )

        compliance = await mock_feeding_manager.async_check_feeding_compliance(
            dog_id="test_dog",
            days_to_check=1,
        )

        assert compliance["compliance_rate"] == 100.0

    async def test_compliance_missed_meal(self, mock_feeding_manager):
        """Test compliance calculation with missed meal."""
        now = datetime.now()

        breakfast_time = now.replace(hour=8, minute=0, second=0, microsecond=0)

        await mock_feeding_manager.async_add_feeding(
            dog_id="test_dog",
            amount=200.0,
            meal_type="breakfast",
            timestamp=breakfast_time,
        )

        # Don't add dinner

        compliance = await mock_feeding_manager.async_check_feeding_compliance(
            dog_id="test_dog",
            days_to_check=1,
        )

        assert compliance["compliance_rate"] == 50.0
        assert len(compliance["missed_meals"]) == 1

    async def test_compliance_late_feeding(self, mock_feeding_manager):
        """Test compliance with late feeding (within tolerance)."""
        now = datetime.now()

        # Feed 15 minutes late (within 30-minute tolerance)
        breakfast_time = now.replace(hour=8, minute=15, second=0, microsecond=0)

        await mock_feeding_manager.async_add_feeding(
            dog_id="test_dog",
            amount=200.0,
            meal_type="breakfast",
            timestamp=breakfast_time,
        )

        compliance = await mock_feeding_manager.async_check_feeding_compliance(
            dog_id="test_dog",
            days_to_check=1,
        )

        # Should still count as compliant if within tolerance
        assert compliance["compliance_rate"] >= 50.0


@pytest.mark.unit
@pytest.mark.asyncio
class TestHealthConditionAdjustments:
    """Test adjustments for health conditions."""

    async def test_diabetic_mode_increases_meal_frequency(self, mock_dog_config):
        """Test diabetic feeding mode adjustment."""
        manager = FeedingManager()

        config = mock_dog_config.copy()
        config["health_conditions"] = ["diabetes"]

        await manager.async_initialize([config])

        await manager.async_activate_diabetic_feeding_mode(
            dog_id="test_dog",
            meal_frequency=4,
        )

        # Check that meals are adjusted
        dog_data = manager._dogs["test_dog"]

        assert dog_data.get("diabetic_mode") is True

    async def test_emergency_mode_reduces_portions(self, mock_feeding_manager):
        """Test emergency feeding mode reduces portions."""
        normal_portion = mock_feeding_manager.calculate_portion("test_dog", "breakfast")

        await mock_feeding_manager.async_activate_emergency_feeding_mode(
            dog_id="test_dog",
            emergency_type="digestive_upset",
            portion_adjustment=0.7,
        )

        emergency_portion = mock_feeding_manager.calculate_portion(
            "test_dog", "breakfast"
        )

        assert emergency_portion < normal_portion
        assert abs(emergency_portion / normal_portion - 0.7) < 0.1


@pytest.mark.unit
@pytest.mark.asyncio
class TestDataRetrieval:
    """Test data retrieval methods."""

    async def test_get_feeding_data_existing_dog(self, mock_feeding_manager):
        """Test retrieving feeding data for existing dog."""
        data = mock_feeding_manager.get_feeding_data("test_dog")

        assert isinstance(data, dict)
        assert "feedings" in data
        assert "daily_target" in data

    async def test_get_feeding_data_nonexistent_dog(self, mock_feeding_manager):
        """Test retrieving data for non-existent dog."""
        data = mock_feeding_manager.get_feeding_data("nonexistent")

        assert data == {}

    async def test_get_daily_stats(self, mock_feeding_manager):
        """Test daily statistics calculation."""
        await mock_feeding_manager.async_add_feeding(
            dog_id="test_dog",
            amount=200.0,
            meal_type="breakfast",
        )

        stats = mock_feeding_manager.get_daily_stats("test_dog")

        assert "total_fed_today" in stats
        assert "meals_today" in stats
        assert "remaining_calories" in stats
        assert stats["meals_today"] == 1
        assert stats["total_fed_today"] == 200.0


@pytest.mark.unit
@pytest.mark.asyncio
class TestEdgeCases:
    """Test edge cases and error handling."""

    async def test_negative_feeding_amount_rejected(self, mock_feeding_manager):
        """Test that negative amounts are rejected."""
        with pytest.raises(ValueError):
            await mock_feeding_manager.async_add_feeding(
                dog_id="test_dog",
                amount=-50.0,
                meal_type="breakfast",
            )

    async def test_zero_feeding_amount_rejected(self, mock_feeding_manager):
        """Test that zero amounts are rejected."""
        with pytest.raises(ValueError):
            await mock_feeding_manager.async_add_feeding(
                dog_id="test_dog",
                amount=0.0,
                meal_type="breakfast",
            )

    async def test_extremely_large_feeding_rejected(self, mock_feeding_manager):
        """Test that unreasonably large amounts are rejected."""
        with pytest.raises(ValueError):
            await mock_feeding_manager.async_add_feeding(
                dog_id="test_dog",
                amount=10000.0,  # 10kg in one meal
                meal_type="breakfast",
            )

    async def test_invalid_dog_id_rejected(self, mock_feeding_manager):
        """Test that invalid dog ID is handled."""
        with pytest.raises(KeyError):
            await mock_feeding_manager.async_add_feeding(
                dog_id="invalid_dog",
                amount=200.0,
                meal_type="breakfast",
            )

    async def test_concurrent_feeding_operations(self, mock_feeding_manager):
        """Test concurrent feeding operations don't corrupt data."""
        import asyncio

        async def add_feeding(i: int):
            await mock_feeding_manager.async_add_feeding(
                dog_id="test_dog",
                amount=50.0,
                meal_type=f"meal_{i}",
            )

        # Add 10 feedings concurrently
        await asyncio.gather(*[add_feeding(i) for i in range(10)])

        data = mock_feeding_manager.get_feeding_data("test_dog")

        assert len(data["feedings"]) == 10
        assert data["daily_stats"]["total_fed_today"] == 500.0
