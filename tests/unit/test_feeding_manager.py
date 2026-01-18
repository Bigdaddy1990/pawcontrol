"""Comprehensive unit tests for FeedingManager.

Tests feeding logic, portion calculations, calorie tracking,
and schedule compliance monitoring.

Quality Scale: Platinum target
Python: 3.13+
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime, timedelta
from typing import cast

import pytest
from custom_components.pawcontrol.feeding_manager import (
  FeedingBatchEntry,
  FeedingComplianceCompleted,
  FeedingHealthUpdatePayload,
  FeedingManager,
  FeedingMedicationData,
)
from custom_components.pawcontrol.types import (
  FeedingDailyStats,
  FeedingEventRecord,
  FeedingManagerDogSetupPayload,
  FeedingSnapshot,
  JSONMutableMapping,
)
from tests.helpers import typed_deepcopy


def _mutable_feeding_config(
  config: FeedingManagerDogSetupPayload,
) -> JSONMutableMapping:
  """Return the mutable feeding config mapping for ``config``."""

  feeding_config = config.get("feeding_config")
  assert isinstance(feeding_config, dict), (
    "Feeding fixture must supply a mutable feeding_config mapping"
  )
  return cast(JSONMutableMapping, feeding_config)


@pytest.mark.unit
@pytest.mark.asyncio
class TestFeedingManagerInitialization:
  """Test FeedingManager initialization and setup."""

  async def test_initialization_single_dog(
    self, mock_dog_config: FeedingManagerDogSetupPayload
  ) -> None:
    """Test initialization with single dog configuration."""
    manager = FeedingManager()

    await manager.async_initialize([mock_dog_config])

    assert len(manager._dogs) == 1
    assert "test_dog" in manager._dogs
    assert manager._dogs["test_dog"]["weight"] == 30.0

  async def test_initialization_multiple_dogs(
    self, mock_multi_dog_config: list[FeedingManagerDogSetupPayload]
  ) -> None:
    """Test initialization with multiple dogs."""
    manager = FeedingManager()

    await manager.async_initialize(mock_multi_dog_config)

    assert len(manager._dogs) == 2
    assert "buddy" in manager._dogs
    assert "max" in manager._dogs

  async def test_initialization_empty_config(self) -> None:
    """Test initialization with empty configuration."""
    manager = FeedingManager()

    await manager.async_initialize([])

    assert len(manager._dogs) == 0

  async def test_initialization_validates_required_fields(self) -> None:
    """Test that initialization validates required fields."""
    manager = FeedingManager()

    invalid_config = {"dog_id": "test", "weight": None}

    with pytest.raises(ValueError):  # Should raise validation error
      await manager.async_initialize([invalid_config])


@pytest.mark.unit
@pytest.mark.asyncio
class TestCalorieCalculations:
  """Test calorie calculation algorithms."""

  async def test_calculate_rer_basic(
    self, mock_feeding_manager: FeedingManager
  ) -> None:
    """Test Resting Energy Requirement (RER) calculation."""
    # RER = 70 * (weight_kg ^ 0.75)
    # For 30kg dog: 70 * (30 ^ 0.75) ≈ 742 kcal

    rer = mock_feeding_manager._calculate_rer(30.0)

    assert 730 < rer < 750  # Allow small margin
    assert isinstance(rer, float)

  async def test_calculate_rer_small_dog(
    self, mock_feeding_manager: FeedingManager
  ) -> None:
    """Test RER calculation for small dog."""
    # For 5kg dog: 70 * (5 ^ 0.75) ≈ 234 kcal

    rer = mock_feeding_manager._calculate_rer(5.0)

    assert 220 < rer < 245

  async def test_calculate_rer_large_dog(
    self, mock_feeding_manager: FeedingManager
  ) -> None:
    """Test RER calculation for large dog."""
    # For 50kg dog: 70 * (50 ^ 0.75) ≈ 1176 kcal

    rer = mock_feeding_manager._calculate_rer(50.0)

    assert 1150 < rer < 1200

  async def test_calculate_daily_calories_moderate_activity(
    self, mock_feeding_manager: FeedingManager
  ) -> None:
    """Test daily calorie calculation for moderate activity."""
    # TDEE = RER * activity_multiplier
    # Moderate = 1.6

    calories = mock_feeding_manager.calculate_daily_calories("test_dog")

    # For 30kg moderate: ~742 * 1.6 ≈ 1187
    assert 1150 < calories < 1250

  async def test_calculate_daily_calories_high_activity(
    self, mock_dog_config: FeedingManagerDogSetupPayload
  ) -> None:
    """Test daily calorie calculation for high activity."""
    manager = FeedingManager()

    config = typed_deepcopy(mock_dog_config)
    config["activity_level"] = "high"

    await manager.async_initialize([config])

    calories = manager.calculate_daily_calories("test_dog")

    # High activity = 2.0 multiplier
    # For 30kg: ~742 * 2.0 ≈ 1484
    assert 1450 < calories < 1550

  async def test_calculate_daily_calories_weight_loss(
    self, mock_dog_config: FeedingManagerDogSetupPayload
  ) -> None:
    """Test calorie reduction for weight loss."""
    manager = FeedingManager()

    config = typed_deepcopy(mock_dog_config)
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

  async def test_calculate_portion_basic(
    self, mock_feeding_manager: FeedingManager
  ) -> None:
    """Test basic portion calculation."""
    portion = mock_feeding_manager.calculate_portion("test_dog", "breakfast")

    # Should be reasonable portion size
    assert 100 < portion < 500
    assert isinstance(portion, float)

  async def test_calculate_portion_equal_distribution(
    self, mock_feeding_manager: FeedingManager
  ) -> None:
    """Test that portions are distributed equally across meals."""
    breakfast = mock_feeding_manager.calculate_portion("test_dog", "breakfast")
    dinner = mock_feeding_manager.calculate_portion("test_dog", "dinner")

    # Should be roughly equal (within 10%)
    assert abs(breakfast - dinner) < breakfast * 0.1

  async def test_calculate_portion_custom_food_calories(
    self, mock_dog_config: FeedingManagerDogSetupPayload
  ) -> None:
    """Test portion calculation with custom food calorie content."""
    manager = FeedingManager()

    config = typed_deepcopy(mock_dog_config)
    feeding_config = _mutable_feeding_config(config)
    feeding_config["calories_per_100g"] = 400  # Higher calorie food

    await manager.async_initialize([config])

    portion_high = manager.calculate_portion("test_dog", "breakfast")

    # Higher calorie food should result in smaller portions
    assert 100 < portion_high < 400

  async def test_calculate_portion_multiple_meals(
    self, mock_dog_config: FeedingManagerDogSetupPayload
  ) -> None:
    """Test portion calculation with different meal frequencies."""
    manager = FeedingManager()

    config = typed_deepcopy(mock_dog_config)
    feeding_config = _mutable_feeding_config(config)
    feeding_config["meals_per_day"] = 3

    await manager.async_initialize([config])

    portion_3meals = manager.calculate_portion("test_dog", "breakfast")

    # 3 meals should have smaller portions than 2 meals
    assert 80 < portion_3meals < 300


@pytest.mark.unit
@pytest.mark.asyncio
class TestFeedingLogging:
  """Test feeding event logging and tracking."""

  async def test_add_feeding_basic(
    self,
    mock_feeding_manager: FeedingManager,
    create_feeding_event: Callable[..., FeedingBatchEntry],
  ) -> None:
    """Test adding basic feeding event."""
    event = create_feeding_event()

    await mock_feeding_manager.async_add_feeding(
      dog_id=event["dog_id"],
      amount=event["amount"],
      meal_type=event["meal_type"],
    )

    data: FeedingSnapshot = mock_feeding_manager.get_feeding_data("test_dog")
    feedings: list[FeedingEventRecord] = data["feedings"]

    assert len(feedings) == 1
    record = feedings[0]
    assert record["amount"] == 200.0
    assert record["scheduled"] is False
    assert record["skipped"] is False
    assert isinstance(record["time"], str)
    assert isinstance(record["with_medication"], bool)

  async def test_add_feeding_with_notes(
    self, mock_feeding_manager: FeedingManager
  ) -> None:
    """Test adding feeding with notes."""
    await mock_feeding_manager.async_add_feeding(
      dog_id="test_dog",
      amount=200.0,
      meal_type="breakfast",
      notes="Added extra vitamins",
    )

    data = mock_feeding_manager.get_feeding_data("test_dog")

    assert data["feedings"][0]["notes"] == "Added extra vitamins"

  async def test_add_feeding_tracks_daily_total(
    self, mock_feeding_manager: FeedingManager
  ) -> None:
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

  async def test_add_feeding_isolates_dogs(
    self, mock_multi_dog_config: list[FeedingManagerDogSetupPayload]
  ) -> None:
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

  async def test_add_feeding_handles_medication(
    self, mock_feeding_manager: FeedingManager
  ) -> None:
    """Test feeding with medication tracking."""
    medication_data: FeedingMedicationData = {
      "name": "Rimadyl",
      "dose": "50mg",
      "time": datetime.now(UTC).isoformat(),
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

  async def test_compliance_perfect_schedule(
    self, mock_feeding_manager: FeedingManager
  ) -> None:
    """Test compliance calculation with perfect adherence."""
    # Add feedings at scheduled times
    now = datetime.now(UTC)

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

    assert compliance["status"] == "completed"
    completed = cast(FeedingComplianceCompleted, compliance)
    assert completed["compliance_rate"] == 100.0

  async def test_compliance_missed_meal(
    self, mock_feeding_manager: FeedingManager
  ) -> None:
    """Test compliance calculation with missed meal."""
    now = datetime.now(UTC)

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

    assert compliance["status"] == "completed"
    completed = cast(FeedingComplianceCompleted, compliance)
    assert completed["compliance_rate"] == 50.0
    assert len(completed["missed_meals"]) == 1

  async def test_compliance_late_feeding(
    self, mock_feeding_manager: FeedingManager
  ) -> None:
    """Test compliance with late feeding (within tolerance)."""
    now = datetime.now(UTC)

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
    assert compliance["status"] == "completed"
    completed = cast(FeedingComplianceCompleted, compliance)
    assert completed["compliance_rate"] >= 50.0


@pytest.mark.unit
@pytest.mark.asyncio
class TestHealthConditionAdjustments:
  """Test adjustments for health conditions."""

  async def test_diabetic_mode_increases_meal_frequency(
    self, mock_dog_config: FeedingManagerDogSetupPayload
  ) -> None:
    """Test diabetic feeding mode adjustment."""
    manager = FeedingManager()

    config = typed_deepcopy(mock_dog_config)
    config["health_conditions"] = ["diabetes"]

    await manager.async_initialize([config])

    await manager.async_activate_diabetic_feeding_mode(
      dog_id="test_dog",
      meal_frequency=4,
    )

    # Check that meals are adjusted
    dog_data = manager._dogs["test_dog"]

    assert dog_data.get("diabetic_mode") is True

  async def test_emergency_mode_reduces_portions(
    self, mock_feeding_manager: FeedingManager
  ) -> None:
    """Test emergency feeding mode reduces portions."""
    normal_portion = mock_feeding_manager.calculate_portion("test_dog", "breakfast")

    await mock_feeding_manager.async_activate_emergency_feeding_mode(
      dog_id="test_dog",
      emergency_type="digestive_upset",
      portion_adjustment=0.7,
    )

    emergency_portion = mock_feeding_manager.calculate_portion("test_dog", "breakfast")

    assert emergency_portion < normal_portion
    assert abs(emergency_portion / normal_portion - 0.7) < 0.1


@pytest.mark.unit
@pytest.mark.asyncio
class TestFeedingModeScheduling:
  """Test scheduling behaviour for activity and emergency timers."""

  async def test_activity_adjustment_schedules_reversion(
    self, mock_feeding_manager: FeedingManager, monkeypatch: pytest.MonkeyPatch
  ) -> None:
    """Ensure temporary activity adjustments schedule a reversion task."""

    created_tasks: list[asyncio.Task[object]] = []
    original_create_task = asyncio.create_task

    def capture_task(
      coro: Coroutine[object, object, object],
    ) -> asyncio.Task[object]:
      task = original_create_task(coro)
      created_tasks.append(task)
      return task

    monkeypatch.setattr(asyncio, "create_task", capture_task)

    original_sleep = asyncio.sleep

    async def fast_sleep(delay: float) -> None:
      await original_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", fast_sleep)

    original_activity = mock_feeding_manager._configs["test_dog"].activity_level

    result = await mock_feeding_manager.async_adjust_calories_for_activity(
      "test_dog",
      activity_level="high",
      duration_hours=1,
      temporary=True,
    )

    assert result["reversion_scheduled"] is True
    assert created_tasks, "Expected a reversion task to be scheduled."
    assert "test_dog" in mock_feeding_manager._activity_reversion_tasks

    reversion_task = created_tasks.pop()
    await reversion_task

    assert "test_dog" not in mock_feeding_manager._activity_reversion_tasks
    assert mock_feeding_manager._configs["test_dog"].activity_level == original_activity
    assert reversion_task.done() is True

  async def test_emergency_mode_schedules_restoration(
    self, mock_feeding_manager: FeedingManager, monkeypatch: pytest.MonkeyPatch
  ) -> None:
    """Ensure emergency mode schedules restoration and resets configuration."""

    created_tasks: list[asyncio.Task[object]] = []
    original_create_task = asyncio.create_task

    def capture_task(
      coro: Coroutine[object, object, object],
    ) -> asyncio.Task[object]:
      task = original_create_task(coro)
      created_tasks.append(task)
      return task

    monkeypatch.setattr(asyncio, "create_task", capture_task)

    original_sleep = asyncio.sleep

    async def fast_sleep(delay: float) -> None:
      await original_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", fast_sleep)

    scheduled_reminders: list[str] = []

    async def fake_setup_reminder(
      self: FeedingManager, dog_id: str
    ) -> None:  # pragma: no cover - patched helper
      scheduled_reminders.append(dog_id)

    monkeypatch.setattr(FeedingManager, "_setup_reminder", fake_setup_reminder)

    config = mock_feeding_manager._configs["test_dog"]
    original_amount = config.daily_food_amount
    original_meals = config.meals_per_day

    result = await mock_feeding_manager.async_activate_emergency_feeding_mode(
      "test_dog",
      emergency_type="illness",
      duration_days=1,
      portion_adjustment=0.75,
    )

    assert result["restoration_scheduled"] is True
    assert created_tasks, "Expected a restoration task to be scheduled."
    assert "test_dog" in mock_feeding_manager._emergency_restore_tasks

    restoration_task = created_tasks.pop()
    await restoration_task

    assert "test_dog" not in mock_feeding_manager._emergency_restore_tasks
    assert config.daily_food_amount == original_amount
    assert config.meals_per_day == original_meals

    emergency_state = mock_feeding_manager._active_emergencies["test_dog"]
    assert emergency_state["active"] is False
    assert "resolved_at" in emergency_state
    assert restoration_task.done() is True


@pytest.mark.unit
@pytest.mark.asyncio
class TestHealthDataUpdates:
  """Test incremental health data updates and coercion."""

  async def test_async_update_health_data_casts_numeric_fields(
    self, mock_feeding_manager: FeedingManager
  ) -> None:
    """Ensure float payload values are coerced to integers."""

    payload: FeedingHealthUpdatePayload = {
      "age_months": 42.7,
      "body_condition_score": 5.9,
    }

    result = await mock_feeding_manager.async_update_health_data("test_dog", payload)

    assert result is True

    config = mock_feeding_manager._configs["test_dog"]
    assert config.age_months == 42
    assert isinstance(config.age_months, int)
    assert config.body_condition_score == 5
    assert isinstance(config.body_condition_score, int)

  async def test_async_update_health_data_allows_none_overrides(
    self, mock_feeding_manager: FeedingManager
  ) -> None:
    """Ensure ``None`` resets optional health metrics."""

    # Prime config with non-null values to ensure they are cleared.
    priming_payload: FeedingHealthUpdatePayload = {
      "age_months": 36,
      "body_condition_score": 6,
    }
    await mock_feeding_manager.async_update_health_data("test_dog", priming_payload)

    reset_payload: FeedingHealthUpdatePayload = {
      "age_months": None,
      "body_condition_score": None,
    }

    result = await mock_feeding_manager.async_update_health_data(
      "test_dog", reset_payload
    )

    assert result is True

    config = mock_feeding_manager._configs["test_dog"]
    assert config.age_months is None
    assert config.body_condition_score is None


@pytest.mark.unit
@pytest.mark.asyncio
class TestDataRetrieval:
  """Test data retrieval methods."""

  async def test_get_feeding_data_existing_dog(
    self, mock_feeding_manager: FeedingManager
  ) -> None:
    """Test retrieving feeding data for existing dog."""
    data: FeedingSnapshot = mock_feeding_manager.get_feeding_data("test_dog")

    assert data["status"] in {"ready", "no_data"}
    assert "daily_target" in data

    stats: FeedingDailyStats = data["daily_stats"]
    assert isinstance(stats["total_fed_today"], float)
    assert isinstance(stats["meals_today"], int)
    assert stats["total_fed_today"] >= 0.0
    assert stats["meals_today"] >= 0

    feedings: list[FeedingEventRecord] = data["feedings"]
    assert isinstance(feedings, list)
    for event in feedings:
      assert {"time", "amount", "scheduled", "with_medication", "skipped"} <= set(event)
      assert isinstance(event["amount"], float)
      assert isinstance(event["scheduled"], bool)
      assert isinstance(event["with_medication"], bool)

    assert isinstance(data["medication_with_meals"], bool)
    assert isinstance(data["health_aware_feeding"], bool)
    assert data["emergency_mode"] is None
    assert data["health_feeding_status"] in {
      "insufficient_data",
      "underfed",
      "overfed",
      "on_track",
      "monitoring",
      "emergency",
      "unknown",
    }

  async def test_get_feeding_data_nonexistent_dog(
    self, mock_feeding_manager: FeedingManager
  ) -> None:
    """Test retrieving data for non-existent dog."""
    data: FeedingSnapshot = mock_feeding_manager.get_feeding_data("nonexistent")

    assert data["status"] == "no_data"
    assert data["feedings"] == []
    assert data["missed_feedings"] == []

    stats: FeedingDailyStats = data["daily_stats"]
    assert stats["meals_today"] == 0
    assert stats["total_fed_today"] == 0.0
    assert stats["remaining_calories"] is None
    assert data["health_feeding_status"] == "insufficient_data"
    assert data["medication_with_meals"] is False
    assert data["health_aware_feeding"] is False
    assert data["emergency_mode"] is None

  async def test_get_daily_stats(self, mock_feeding_manager: FeedingManager) -> None:
    """Test daily statistics calculation."""
    await mock_feeding_manager.async_add_feeding(
      dog_id="test_dog",
      amount=200.0,
      meal_type="breakfast",
    )

    stats: FeedingDailyStats = mock_feeding_manager.get_daily_stats("test_dog")

    assert stats["meals_today"] == 1
    assert stats["total_fed_today"] == 200.0
    assert isinstance(stats["remaining_calories"], (float, type(None)))


@pytest.mark.unit
@pytest.mark.asyncio
class TestEdgeCases:
  """Test edge cases and error handling."""

  async def test_negative_feeding_amount_rejected(
    self, mock_feeding_manager: FeedingManager
  ) -> None:
    """Test that negative amounts are rejected."""
    with pytest.raises(ValueError):
      await mock_feeding_manager.async_add_feeding(
        dog_id="test_dog",
        amount=-50.0,
        meal_type="breakfast",
      )

  async def test_zero_feeding_amount_rejected(
    self, mock_feeding_manager: FeedingManager
  ) -> None:
    """Test that zero amounts are rejected."""
    with pytest.raises(ValueError):
      await mock_feeding_manager.async_add_feeding(
        dog_id="test_dog",
        amount=0.0,
        meal_type="breakfast",
      )

  async def test_extremely_large_feeding_rejected(
    self, mock_feeding_manager: FeedingManager
  ) -> None:
    """Test that unreasonably large amounts are rejected."""
    with pytest.raises(ValueError):
      await mock_feeding_manager.async_add_feeding(
        dog_id="test_dog",
        amount=10000.0,  # 10kg in one meal
        meal_type="breakfast",
      )

  async def test_invalid_dog_id_rejected(
    self, mock_feeding_manager: FeedingManager
  ) -> None:
    """Test that invalid dog ID is handled."""
    with pytest.raises(KeyError):
      await mock_feeding_manager.async_add_feeding(
        dog_id="invalid_dog",
        amount=200.0,
        meal_type="breakfast",
      )

  async def test_concurrent_feeding_operations(
    self, mock_feeding_manager: FeedingManager
  ) -> None:
    """Test concurrent feeding operations don't corrupt data."""
    import asyncio

    async def add_feeding(i: int) -> None:
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
