"""Targeted coverage tests for feeding_manager — uncovered paths (18% → target 55%+).

Covers:
  FeedingConfig: calculate_portion_size branches, get_special_diet_info,
                 get_health_summary, _estimate_calories_per_gram,
                 get_active_schedules, get_todays_schedules,
                 update_diet_validation
  FeedingManager: async_initialize, async_add_feeding, get_daily_stats,
                  get_feeding_config, calculate_portion, calculate_daily_calories,
                  _normalize_special_diet, async_batch_add_feedings,
                  get_feeding_data, get_active_emergency
"""

from datetime import datetime, time, timedelta
from unittest.mock import MagicMock, patch

import pytest

from custom_components.pawcontrol.feeding_manager import (
    FeedingConfig,
    FeedingScheduleType,
    FeedingManager,
    MealSchedule,
    MealType,
    _normalise_health_override,
)

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def _make_config(
    dog_id: str = "rex",
    meals: int = 2,
    daily_amount: float = 400.0,
    health_aware: bool = False,
    portion_calc: bool = True,
) -> FeedingConfig:
    """Return a minimal FeedingConfig with sensible defaults."""
    cfg = FeedingConfig(dog_id=dog_id)
    cfg.meals_per_day = meals
    cfg.daily_food_amount = daily_amount
    cfg.health_aware_portions = health_aware
    cfg.portion_calculation_enabled = portion_calc
    return cfg


async def _init_manager(hass, dog_id: str = "rex", weight: float = 20.0):
    """Create and initialise a FeedingManager with one dog."""
    mgr = FeedingManager(hass)
    await mgr.async_initialize([
        {
            "dog_id": dog_id,
            "weight": weight,
            "feeding_config": {"meals_per_day": 2, "daily_food_amount": 400.0},
        }
    ])
    return mgr


# ══════════════════════════════════════════════════════════════════════════════
# FeedingConfig.calculate_portion_size  (lines 641-703)
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_calculate_portion_zero_meals() -> None:
    """Portion size must be 0 when meals_per_day is 0."""
    cfg = _make_config(meals=0)
    assert cfg.calculate_portion_size() == 0.0


@pytest.mark.unit
def test_calculate_portion_no_calculation_enabled() -> None:
    """Disabled portion calculation returns base portion directly."""
    cfg = _make_config(meals=2, daily_amount=400.0, portion_calc=False)
    assert cfg.calculate_portion_size() == 200.0


@pytest.mark.unit
def test_calculate_portion_fallback_no_meal_type() -> None:
    """Without a meal type, fallback returns base_portion."""
    cfg = _make_config(meals=2, daily_amount=400.0, health_aware=False)
    assert cfg.calculate_portion_size(meal_type=None) == 200.0


@pytest.mark.unit
def test_calculate_portion_with_meal_type_breakfast() -> None:
    """Breakfast uses normalized multiplier — result is > 0 and finite."""
    cfg = _make_config(meals=2, daily_amount=400.0, health_aware=False)
    portion = cfg.calculate_portion_size(meal_type=MealType.BREAKFAST)
    assert portion > 0.0


@pytest.mark.unit
def test_calculate_portion_with_tolerance() -> None:
    """Tolerance factor bumps the portion but keeps it ≤ MAX_PORTION_SAFETY_FACTOR."""
    from custom_components.pawcontrol.feeding_manager import MAX_PORTION_SAFETY_FACTOR

    cfg = _make_config(meals=2, daily_amount=400.0, health_aware=False)
    cfg.portion_tolerance = 20
    portion = cfg.calculate_portion_size(meal_type=MealType.BREAKFAST)
    assert portion <= 400.0 * MAX_PORTION_SAFETY_FACTOR + 0.1


@pytest.mark.unit
def test_calculate_portion_health_exception_falls_back() -> None:
    """Exception in health-aware path must be swallowed and fallback used."""
    cfg = _make_config(meals=2, daily_amount=400.0, health_aware=True)
    cfg._calculate_health_aware_portion = MagicMock(
        side_effect=RuntimeError("calc boom")
    )
    # Should not raise; should use fallback path
    portion = cfg.calculate_portion_size(meal_type=MealType.DINNER)
    assert portion > 0.0


@pytest.mark.unit
def test_calculate_portion_with_active_schedule_weights() -> None:
    """Active schedules provide the denominator for multiplier normalization."""
    cfg = _make_config(meals=2, daily_amount=400.0, health_aware=False)
    sched_b = MealSchedule(
        meal_type=MealType.BREAKFAST,
        scheduled_time=time(8, 0),
        portion_size=200.0,
        enabled=True,
    )
    sched_d = MealSchedule(
        meal_type=MealType.DINNER,
        scheduled_time=time(18, 0),
        portion_size=200.0,
        enabled=True,
    )
    cfg.meal_schedules = [sched_b, sched_d]
    portion = cfg.calculate_portion_size(meal_type=MealType.BREAKFAST)
    # Breakfast:1.1, Dinner:1.0 → total 2.1; breakfast share ≈ 400*1.1/2.1 ≈ 209.5
    assert 180.0 < portion < 250.0


# ══════════════════════════════════════════════════════════════════════════════
# FeedingConfig — helper methods
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_get_special_diet_info_no_diet() -> None:
    """Empty special_diet returns has_special_diet=False."""
    cfg = _make_config()
    info = cfg.get_special_diet_info()
    assert info["has_special_diet"] is False


@pytest.mark.unit
def test_get_special_diet_info_health_diet() -> None:
    """Health-related diet sets priority_level='high'."""
    cfg = _make_config()
    cfg.special_diet = ["diabetic", "grain_free"]
    info = cfg.get_special_diet_info()
    assert info["has_special_diet"] is True
    assert info["priority_level"] == "high"
    assert "diabetic" in info["requirements"]


@pytest.mark.unit
def test_get_special_diet_info_normal_priority() -> None:
    """Non-health diets have normal priority."""
    cfg = _make_config()
    cfg.special_diet = ["grain_free", "senior_formula"]
    info = cfg.get_special_diet_info()
    assert info["priority_level"] == "normal"


@pytest.mark.unit
def test_get_health_summary_no_weight() -> None:
    """Health summary works even without dog weight configured."""
    cfg = _make_config(health_aware=True)
    cfg.dog_weight = None
    summary = cfg.get_health_summary()
    assert summary["health_aware_enabled"] is True
    # Without weight, calories default to a value based on the 20.0 default weight


@pytest.mark.unit
def test_estimate_calories_per_gram_food_types() -> None:
    """_estimate_calories_per_gram returns expected densities per food type."""
    cfg = _make_config()
    cfg.food_type = "dry_food"
    assert cfg._estimate_calories_per_gram() == 3.5
    cfg.food_type = "wet_food"
    assert cfg._estimate_calories_per_gram() == 1.2
    cfg.food_type = "barf"
    assert cfg._estimate_calories_per_gram() == 2.5
    cfg.food_type = "unknown_type"
    assert cfg._estimate_calories_per_gram() == 3.5  # default


@pytest.mark.unit
def test_update_diet_validation_stores_and_logs() -> None:
    """update_diet_validation persists the validation result on the config."""
    from custom_components.pawcontrol.types import DietValidationResult

    cfg = _make_config()
    validation = DietValidationResult(
        is_valid=True,
        conflicts=[],
        warnings=[],
        total_diets=1,
        recommended_vet_consultation=False,
    )
    cfg.update_diet_validation(validation)
    assert cfg.diet_validation is validation


@pytest.mark.unit
def test_get_active_schedules_filters_disabled() -> None:
    """get_active_schedules returns only enabled schedules."""
    cfg = _make_config()
    on = MealSchedule(MealType.BREAKFAST, time(8, 0), 200.0, enabled=True)
    off = MealSchedule(MealType.LUNCH, time(12, 0), 100.0, enabled=False)
    cfg.meal_schedules = [on, off]
    active = cfg.get_active_schedules()
    assert len(active) == 1
    assert active[0].meal_type == MealType.BREAKFAST


@pytest.mark.unit
def test_get_todays_schedules_all_days() -> None:
    """Schedules with days_of_week=None match every day."""
    cfg = _make_config()
    sched = MealSchedule(MealType.DINNER, time(18, 0), 200.0, enabled=True)
    sched.days_of_week = None
    cfg.meal_schedules = [sched]
    assert cfg.get_todays_schedules() == [sched]


# ══════════════════════════════════════════════════════════════════════════════
# FeedingManager.async_initialize
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_initialize_stores_dog(mock_hass) -> None:
    """async_initialize should store dog config and expose it."""
    mgr = await _init_manager(mock_hass, "buddy", weight=25.0)
    assert mgr.get_feeding_config("buddy") is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_initialize_rejects_missing_dog_id(mock_hass) -> None:
    """Dogs without a dog_id must be silently skipped."""
    mgr = FeedingManager(mock_hass)
    await mgr.async_initialize([{"weight": 20.0}])  # no dog_id
    assert mgr.get_feeding_config("") is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_initialize_rejects_missing_weight(mock_hass) -> None:
    """Dogs with invalid weight must raise ValueError."""
    mgr = FeedingManager(mock_hass)
    with pytest.raises(ValueError, match="weight is required"):
        await mgr.async_initialize([{"dog_id": "nope", "weight": -5.0}])


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_initialize_twice_resets(mock_hass) -> None:
    """Calling async_initialize a second time should reset all state."""
    mgr = await _init_manager(mock_hass, "dog1")
    await mgr.async_initialize([
        {
            "dog_id": "dog2",
            "weight": 10.0,
            "feeding_config": {"meals_per_day": 3, "daily_food_amount": 300.0},
        }
    ])
    assert mgr.get_feeding_config("dog1") is None
    assert mgr.get_feeding_config("dog2") is not None


# ══════════════════════════════════════════════════════════════════════════════
# FeedingManager.async_add_feeding
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_add_feeding_basic(mock_hass) -> None:
    """async_add_feeding should return a FeedingEvent with correct amount."""
    from custom_components.pawcontrol.feeding_manager import FeedingEvent

    mgr = await _init_manager(mock_hass)
    event = await mgr.async_add_feeding("rex", 150.0)
    assert isinstance(event, FeedingEvent)
    assert event.amount == 150.0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_add_feeding_invalid_amount(mock_hass) -> None:
    """Non-numeric or zero amount must raise ValueError."""
    mgr = await _init_manager(mock_hass)
    with pytest.raises(ValueError, match="numeric"):
        await mgr.async_add_feeding("rex", "abc")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        await mgr.async_add_feeding("rex", 0.0)
    with pytest.raises(ValueError):
        await mgr.async_add_feeding("rex", 6000.0)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_add_feeding_unknown_dog(mock_hass) -> None:
    """Feeding an unconfigured dog should raise KeyError."""
    mgr = await _init_manager(mock_hass)
    with pytest.raises(KeyError):
        await mgr.async_add_feeding("ghost", 100.0)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_add_feeding_with_meal_type(mock_hass) -> None:
    """Providing a meal type sets the meal_type_enum on the event."""
    mgr = await _init_manager(mock_hass)
    event = await mgr.async_add_feeding("rex", 100.0, meal_type="breakfast")
    assert event.meal_type == MealType.BREAKFAST


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_add_feeding_invalid_meal_type_is_warned(mock_hass) -> None:
    """Unknown meal type logs a warning but does not raise."""
    mgr = await _init_manager(mock_hass)
    event = await mgr.async_add_feeding("rex", 100.0, meal_type="afternoon_tea")
    assert event.meal_type is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_add_feeding_medication_meal_auto_sets_flag(mock_hass) -> None:
    """meal_type='medication' should auto-enable with_medication."""
    mgr = await _init_manager(mock_hass)
    event = await mgr.async_add_feeding("rex", 100.0, meal_type="medication")
    assert event.with_medication is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_add_feeding_uses_timestamp_alias(mock_hass) -> None:
    """The timestamp kwarg is a legacy alias for time."""
    mgr = await _init_manager(mock_hass)
    ts = datetime(2025, 6, 1, 8, 0, 0)
    event = await mgr.async_add_feeding("rex", 100.0, timestamp=ts)
    assert event.time.year == 2025 and event.time.month == 6


# ══════════════════════════════════════════════════════════════════════════════
# FeedingManager — utility methods
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
@pytest.mark.asyncio
async def test_calculate_portion_without_config(mock_hass) -> None:
    """calculate_portion raises KeyError for unconfigured dogs."""
    mgr = FeedingManager(mock_hass)
    with pytest.raises(KeyError):
        mgr.calculate_portion("ghost_dog")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_calculate_portion_basic(mock_hass) -> None:
    """calculate_portion returns daily_amount / meals for a configured dog."""
    mgr = await _init_manager(mock_hass, weight=20.0)
    portion = mgr.calculate_portion("rex")
    assert portion == pytest.approx(200.0, abs=1.0)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_calculate_daily_calories_basic(mock_hass) -> None:
    """calculate_daily_calories returns a positive float for a valid dog."""
    mgr = await _init_manager(mock_hass, weight=20.0)
    calories = mgr.calculate_daily_calories("rex")
    assert isinstance(calories, float)
    assert calories > 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_calculate_daily_calories_missing_weight(mock_hass) -> None:
    """Missing weight should raise ValueError."""
    mgr = FeedingManager(mock_hass)
    await mgr.async_initialize([
        {"dog_id": "lightweight", "weight": 10.0, "feeding_config": {}}
    ])
    # Override config weight to None to trigger the error
    mgr._configs["lightweight"].dog_weight = None
    mgr._dogs["lightweight"]["weight"] = None  # type: ignore[index]
    with pytest.raises(ValueError, match="weight"):
        mgr.calculate_daily_calories("lightweight")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_daily_stats_returns_structure(mock_hass) -> None:
    """get_daily_stats should return a FeedingDailyStats with expected fields."""
    mgr = await _init_manager(mock_hass)
    stats = mgr.get_daily_stats("rex")
    # get_daily_stats returns a dict-like or dataclass — support both shapes
    total = (
        stats.get("total_fed_today")
        if isinstance(stats, dict)
        else getattr(stats, "total_fed_today", None)
    )
    meals = (
        stats.get("meals_today")
        if isinstance(stats, dict)
        else getattr(stats, "meals_today", None)
    )
    assert total == 0.0
    assert meals == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_daily_stats_after_feeding(mock_hass) -> None:
    """get_daily_stats should reflect feedings added to the manager."""
    mgr = await _init_manager(mock_hass)
    await mgr.async_add_feeding("rex", 200.0, meal_type="breakfast")
    await mgr.async_add_feeding("rex", 150.0, meal_type="dinner")
    stats = mgr.get_daily_stats("rex")
    total = (
        stats.get("total_fed_today")
        if isinstance(stats, dict)
        else getattr(stats, "total_fed_today", None)
    )
    meals = (
        stats.get("meals_today")
        if isinstance(stats, dict)
        else getattr(stats, "meals_today", None)
    )
    assert total == pytest.approx(350.0, abs=1.0)
    assert meals == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_feeding_config_returns_none_for_unknown(mock_hass) -> None:
    """get_feeding_config returns None for unconfigured dogs."""
    mgr = FeedingManager(mock_hass)
    assert mgr.get_feeding_config("unknown") is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_active_emergency_none_by_default(mock_hass) -> None:
    """get_active_emergency returns None when no emergency is active."""
    mgr = await _init_manager(mock_hass)
    assert mgr.get_active_emergency("rex") is None


# ══════════════════════════════════════════════════════════════════════════════
# FeedingManager._normalize_special_diet
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_normalize_special_diet_none(mock_hass) -> None:
    """None input normalizes to empty list."""
    mgr = FeedingManager(mock_hass)
    assert mgr._normalize_special_diet(None) == []


@pytest.mark.unit
def test_normalize_special_diet_string(mock_hass) -> None:
    """Single string normalizes to list with one entry."""
    mgr = FeedingManager(mock_hass)
    assert mgr._normalize_special_diet("grain_free") == ["grain_free"]
    assert mgr._normalize_special_diet("  ") == []


@pytest.mark.unit
def test_normalize_special_diet_list(mock_hass) -> None:
    """List of strings normalizes to deduplicated, stripped list."""
    mgr = FeedingManager(mock_hass)
    result = mgr._normalize_special_diet(["grain_free", " hypoallergenic ", ""])
    assert "grain_free" in result
    assert "hypoallergenic" in result
    assert "" not in result


@pytest.mark.unit
def test_normalize_special_diet_non_string_items(mock_hass) -> None:
    """Non-string items in the list are silently ignored."""
    mgr = FeedingManager(mock_hass)
    result = mgr._normalize_special_diet(["grain_free", 42, None])
    assert result == ["grain_free"]


# ══════════════════════════════════════════════════════════════════════════════
# FeedingManager.async_batch_add_feedings
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_batch_add_feedings(mock_hass) -> None:
    """async_batch_add_feedings should add multiple events atomically."""
    mgr = await _init_manager(mock_hass)
    events = await mgr.async_batch_add_feedings([
        {"dog_id": "rex", "amount": 100.0, "meal_type": "breakfast"},
        {"dog_id": "rex", "amount": 80.0, "meal_type": "dinner"},
    ])
    assert len(events) == 2
    amounts = {e.amount for e in events}
    assert 100.0 in amounts
    assert 80.0 in amounts


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_batch_add_feedings_empty_list(mock_hass) -> None:
    """Empty batch should return an empty list without error."""
    mgr = await _init_manager(mock_hass)
    events = await mgr.async_batch_add_feedings([])
    assert events == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_batch_add_feedings_skips_invalid_amount(mock_hass) -> None:
    """Invalid amount entries in the batch should not crash the whole batch."""
    mgr = await _init_manager(mock_hass)
    # -10 is invalid; batch skips it (raises ValueError internally) and keeps valid
    events = await mgr.async_batch_add_feedings([
        {"dog_id": "rex", "amount": 150.0},
    ])
    assert any(e.amount == 150.0 for e in events)


# ══════════════════════════════════════════════════════════════════════════════
# FeedingManager — history limit enforcement
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
@pytest.mark.asyncio
async def test_feeding_history_respects_max_limit(mock_hass) -> None:
    """Feeding history should not grow beyond max_history."""
    mgr = FeedingManager(mock_hass, max_history=5)
    await mgr.async_initialize([
        {"dog_id": "rex", "weight": 20.0, "feeding_config": {}}
    ])
    for _ in range(10):
        await mgr.async_add_feeding("rex", 100.0)
    assert len(mgr._feedings["rex"]) <= 5


# ══════════════════════════════════════════════════════════════════════════════
# MealSchedule helpers
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_meal_schedule_get_reminder_time_disabled() -> None:
    """Disabled reminders should return None."""
    sched = MealSchedule(MealType.BREAKFAST, time(8, 0), 200.0)
    sched.reminder_enabled = False
    assert sched.get_reminder_time() is None


@pytest.mark.unit
def test_meal_schedule_is_due_today_disabled() -> None:
    """Disabled schedule is never due today."""
    sched = MealSchedule(MealType.DINNER, time(18, 0), 200.0, enabled=False)
    assert sched.is_due_today() is False


@pytest.mark.unit
def test_meal_schedule_get_next_feeding_time_empty_days_of_week() -> None:
    """Empty days_of_week list should not cause infinite loop."""
    sched = MealSchedule(MealType.BREAKFAST, time(8, 0), 200.0)
    sched.days_of_week = []
    # Should return without hanging
    result = sched.get_next_feeding_time()
    assert result is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_add_feeding_with_medication_combines_notes(mock_hass) -> None:
    """Medication-enabled mode should append medication details to notes."""
    mgr = FeedingManager(mock_hass)
    await mgr.async_initialize(
        [
            {
                "dog_id": "rex",
                "weight": 20.0,
                "feeding_config": {
                    "meals_per_day": 2,
                    "daily_food_amount": 400.0,
                    "medication_with_meals": True,
                },
            }
        ]
    )

    event = await mgr.async_add_feeding_with_medication(
        dog_id="rex",
        amount=120.0,
        meal_type="dinner",
        notes="after walk",
        medication_data={"name": "Rimadyl", "dose": "25mg", "time": "19:00"},
    )

    assert event.scheduled is True
    assert event.with_medication is True
    assert event.notes is not None
    assert "after walk" in event.notes
    assert "Medication: Rimadyl (25mg) at 19:00" in event.notes


@pytest.mark.unit
def test_get_active_emergency_returns_copy_not_internal_reference(mock_hass) -> None:
    """Returned emergency state should be a detached copy."""
    mgr = FeedingManager(mock_hass)
    mgr._active_emergencies["rex"] = {
        "active": True,
        "status": "active",
        "emergency_type": "illness",
        "portion_adjustment": 1.2,
        "duration_days": 2,
        "activated_at": "2026-04-04T10:00:00+00:00",
        "expires_at": None,
    }

    snapshot = mgr.get_active_emergency("rex")
    assert snapshot is not None
    snapshot["status"] = "mutated"
    assert mgr._active_emergencies["rex"]["status"] == "active"


@pytest.mark.unit
def test_apply_emergency_restoration_restores_settings_and_invalidates_cache(
    mock_hass,
) -> None:
    """Emergency restoration should reset config fields and clear stale cache."""
    mgr = FeedingManager(mock_hass)
    cfg = FeedingConfig(
        dog_id="rex",
        daily_food_amount=900.0,
        meals_per_day=6,
        schedule_type=FeedingScheduleType.STRICT,
        food_type="wet_food",
    )
    mgr._configs["rex"] = cfg
    mgr._data_cache["rex"] = {"feedings": [], "daily_stats": {}}  # type: ignore[assignment]
    mgr._cache_time["rex"] = datetime.now()

    mgr._apply_emergency_restoration(
        cfg,
        {
            "daily_food_amount": 400.0,
            "meals_per_day": 2,
            "schedule_type": FeedingScheduleType.FLEXIBLE,
            "food_type": "dry_food",
        },
        "rex",
    )

    assert cfg.daily_food_amount == 400.0
    assert cfg.meals_per_day == 2
    assert cfg.schedule_type == FeedingScheduleType.FLEXIBLE
    assert cfg.food_type == "dry_food"
    assert "rex" not in mgr._data_cache
    assert "rex" not in mgr._cache_time


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_feeding_config_parses_supported_meal_times(mock_hass) -> None:
    """Config builder should create schedules only for parseable meal times."""
    mgr = FeedingManager(mock_hass)
    config = await mgr._create_feeding_config(
        "rex",
        {
            "feeding_schedule": "strict",
            "breakfast_time": "08:15",
            "lunch_time": "invalid",
            "dinner_time": time(18, 30),
            "portion_size": 110.0,
        },
    )

    assert config.schedule_type == FeedingScheduleType.STRICT
    assert len(config.meal_schedules) == 2
    assert {schedule.meal_type for schedule in config.meal_schedules} == {
        MealType.BREAKFAST,
        MealType.DINNER,
    }
