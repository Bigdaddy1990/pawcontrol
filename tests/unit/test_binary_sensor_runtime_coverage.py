"""Expanded runtime coverage tests for binary_sensor.py."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any, cast

import pytest

from custom_components.pawcontrol import binary_sensor as bs
from custom_components.pawcontrol.const import (
    MODULE_FEEDING,
    MODULE_GARDEN,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_WALK,
)
from custom_components.pawcontrol.coordinator import PawControlCoordinator
from custom_components.pawcontrol.types import (
    CoordinatorDogData,
    CoordinatorRuntimeManagers,
    PawControlConfigEntry,
)


class _CoordinatorStub:
    """Minimal coordinator contract required by binary sensor entities."""

    def __init__(
        self,
        dog_data: CoordinatorDogData | None = None,
        *,
        available: bool = True,
        enabled_modules: list[str] | None = None,
        runtime_managers: CoordinatorRuntimeManagers | None = None,
    ) -> None:
        self.available = available
        self.last_update_success = True
        self.last_update_success_time = datetime(2026, 1, 1, tzinfo=UTC)
        self.last_exception = None
        self._dog_data = dog_data or {}
        self._enabled_modules = enabled_modules or []
        self.runtime_managers = runtime_managers or CoordinatorRuntimeManagers()

    def get_dog_data(self, dog_id: str) -> CoordinatorDogData | None:
        return cast(CoordinatorDogData, self._dog_data)

    def get_module_data(self, dog_id: str, module: str) -> dict[str, Any]:
        payload = self._dog_data.get(module, {})
        return cast(dict[str, Any], payload if isinstance(payload, dict) else {})

    def get_enabled_modules(self, dog_id: str) -> list[str]:
        return list(self._enabled_modules)


class _GardenManagerStub:
    """Garden manager stub used to exercise manager-based fallbacks."""

    def __init__(
        self,
        *,
        snapshot: dict[str, Any] | None = None,
        in_garden: bool = False,
        pending_confirmation: bool = False,
        raise_on_snapshot: bool = False,
    ) -> None:
        self._snapshot = snapshot or {}
        self._in_garden = in_garden
        self._pending_confirmation = pending_confirmation
        self._raise_on_snapshot = raise_on_snapshot

    def build_garden_snapshot(self, dog_id: str) -> dict[str, Any]:
        if self._raise_on_snapshot:
            raise RuntimeError("snapshot failure")
        return dict(self._snapshot)

    def is_dog_in_garden(self, dog_id: str) -> bool:
        return self._in_garden

    def has_pending_confirmation(self, dog_id: str) -> bool:
        return self._pending_confirmation


def _rich_dog_data(now: datetime) -> CoordinatorDogData:
    """Return a payload with all modules populated for broad sensor coverage."""
    return cast(
        CoordinatorDogData,
        {
            "last_update": now.isoformat(),
            "status": "online",
            bs.VISITOR_MODE_ACTIVE_FIELD: True,
            "visitor_mode_started": now - timedelta(minutes=30),
            "visitor_name": "Ava",
            "visitor_mode_settings": {
                "modified_notifications": False,
                "reduced_alerts": True,
            },
            "status_snapshot": {
                "on_walk": True,
                "needs_walk": True,
                "in_safe_zone": False,
            },
            MODULE_FEEDING: {
                "is_hungry": True,
                "last_feeding": now - timedelta(hours=14),
                "last_feeding_hours": 13.5,
                "next_feeding_due": (now - timedelta(minutes=5)).isoformat(),
                "feeding_schedule_adherence": 72.0,
                "daily_target_met": True,
                "health_aware_feeding": True,
                "portion_adjustment_factor": 1.25,
                "health_conditions": ["diabetes", "sensitive_stomach"],
                "medication_with_meals": True,
                "health_emergency": 1,
                "emergency_mode": {
                    "emergency_type": "hypoglycemia",
                    "portion_adjustment": 0.8,
                    "activated_at": now - timedelta(hours=1),
                    "expires_at": now + timedelta(hours=2),
                    "status": "active",
                },
            },
            MODULE_WALK: {
                bs.WALK_IN_PROGRESS_FIELD: True,
                "current_walk": {
                    "start_time": (now - timedelta(minutes=20)).isoformat(),
                    "current_duration": 20,
                    "current_distance": 1450,
                },
                "current_walk_duration": 20,
                "current_walk_distance": 1450,
                "average_walk_duration": 35,
                "needs_walk": True,
                "last_walk": now - timedelta(hours=14),
                "last_walk_hours": 13,
                "walks_today": 1,
                "walk_goal_met": True,
                "last_long_walk": (now - timedelta(days=3)).isoformat(),
            },
            MODULE_GPS: {
                "zone": "park",
                "distance_from_home": 1.7,
                "last_seen": now,
                "accuracy": 14.5,
                "speed": 4.2,
                "geofence_alert": 1,
                "battery_level": 12,
                "geofence_status": {"in_safe_zone": False},
            },
            MODULE_HEALTH: {
                "health_alerts": ["injury"],
                "health_status": "warning",
                "weight_change_percent": 14,
                "medications_due": ["pill_a"],
                "next_checkup_due": (now - timedelta(days=1)).isoformat(),
                "grooming_due": True,
                "activity_level": "very_low",
            },
            MODULE_GARDEN: {
                "status": "active",
                "sessions_today": 2,
                "pending_confirmations": [{"id": "c1"}],
                "active_session": {
                    "start_time": (now - timedelta(minutes=15)).isoformat(),
                    "duration_minutes": 15,
                },
                "last_session": {
                    "start_time": (now - timedelta(hours=2)).isoformat(),
                    "duration_minutes": 18,
                    "end_time": (now - timedelta(hours=1, minutes=42)).isoformat(),
                },
            },
        },
    )


def _all_sensors(
    coordinator: PawControlCoordinator,
    dog_id: str = "rex",
    dog_name: str = "Rex",
) -> list[bs.PawControlBinarySensorBase]:
    """Create all sensor entities available for a fully-enabled dog profile."""
    return [
        *bs._create_base_binary_sensors(coordinator, dog_id, dog_name),
        *bs._create_feeding_binary_sensors(coordinator, dog_id, dog_name),
        *bs._create_walk_binary_sensors(coordinator, dog_id, dog_name),
        *bs._create_gps_binary_sensors(coordinator, dog_id, dog_name),
        *bs._create_health_binary_sensors(coordinator, dog_id, dog_name),
        *bs._create_garden_binary_sensors(coordinator, dog_id, dog_name),
    ]


def test_sensor_factory_helpers_create_expected_sensor_counts() -> None:
    """Factory helpers should create complete per-module sensor sets."""
    coordinator = cast(PawControlCoordinator, _CoordinatorStub({}))

    assert len(bs._create_base_binary_sensors(coordinator, "rex", "Rex")) == 3
    assert len(bs._create_feeding_binary_sensors(coordinator, "rex", "Rex")) == 4
    assert len(bs._create_walk_binary_sensors(coordinator, "rex", "Rex")) == 4
    assert len(bs._create_gps_binary_sensors(coordinator, "rex", "Rex")) == 6
    assert len(bs._create_health_binary_sensors(coordinator, "rex", "Rex")) == 9
    assert len(bs._create_garden_binary_sensors(coordinator, "rex", "Rex")) == 3
    assert len(_all_sensors(coordinator)) == 29


@pytest.mark.asyncio
async def test_async_setup_entry_handles_runtime_absence_and_full_dog_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """async_setup_entry should handle missing runtime and create entities for enabled modules."""
    added: list[bs.PawControlBinarySensorBase] = []
    entry = cast(PawControlConfigEntry, SimpleNamespace(entry_id="entry-1"))

    monkeypatch.setattr(bs, "get_runtime_data", lambda hass, cfg: None)
    await bs.async_setup_entry(object(), entry, lambda entities: added.extend(entities))
    assert added == []

    now = datetime(2026, 1, 1, tzinfo=UTC)
    coordinator = cast(PawControlCoordinator, _CoordinatorStub(_rich_dog_data(now)))
    runtime_data = SimpleNamespace(
        coordinator=coordinator,
        dogs=[
            "invalid",
            {
                bs.DOG_ID_FIELD: "rex",
                bs.DOG_NAME_FIELD: "Rex",
                "modules": {
                    MODULE_FEEDING: True,
                    MODULE_WALK: True,
                    MODULE_GPS: True,
                    MODULE_HEALTH: True,
                    MODULE_GARDEN: True,
                },
            },
        ],
    )
    monkeypatch.setattr(bs, "get_runtime_data", lambda hass, cfg: runtime_data)

    await bs.async_setup_entry(object(), entry, lambda entities: added.extend(entities))

    assert len(added) == 29


def test_binary_sensor_is_on_test_override_is_guarded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """is_on setter/deleter should enforce the pytest-only test override guard."""
    coordinator = cast(PawControlCoordinator, _CoordinatorStub({}))
    sensor = bs.PawControlOnlineBinarySensor(coordinator, "rex", "Rex")

    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    with pytest.raises(AttributeError):
        sensor.is_on = True

    monkeypatch.setenv("PYTEST_CURRENT_TEST", "test")
    sensor.is_on = True
    assert sensor.is_on is True
    del sensor.is_on
    assert isinstance(sensor.is_on, bool)


def test_local_time_and_threshold_helpers_cover_fallback_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Helper functions should handle fallback conversion and invalid comparisons."""
    monkeypatch.delattr(bs.dt_util, "as_local", raising=False)
    monkeypatch.setattr(bs.dt_util, "DEFAULT_TIME_ZONE", UTC, raising=False)
    local = bs._as_local(datetime(2026, 1, 1, 12, 0, 0))
    assert local.tzinfo is not None

    mixin = bs.BinarySensorLogicMixin()
    assert mixin._calculate_time_based_status("invalid", 1.0, True) is True
    assert mixin._evaluate_threshold(object(), 5.0, "greater", True) is True


def test_as_local_returns_input_when_no_default_timezone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without ``as_local`` and without a default timezone, conversion should be a no-op."""
    monkeypatch.delattr(bs.dt_util, "as_local", raising=False)
    monkeypatch.setattr(bs.dt_util, "DEFAULT_TIME_ZONE", None, raising=False)

    aware = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    assert bs._as_local(aware) == aware


def test_all_sensors_report_state_and_attributes_with_rich_payload() -> None:
    """Each sensor should provide a boolean state and normalized attribute mapping."""
    now = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    coordinator = cast(
        PawControlCoordinator,
        _CoordinatorStub(
            _rich_dog_data(now),
            enabled_modules=[
                MODULE_FEEDING,
                MODULE_WALK,
                MODULE_GPS,
                MODULE_HEALTH,
                MODULE_GARDEN,
            ],
        ),
    )
    sensors = _all_sensors(coordinator)

    assert sensors
    for sensor in sensors:
        assert isinstance(sensor.is_on, bool)
        attrs = sensor.extra_state_attributes
        assert isinstance(attrs, dict)
        assert attrs.get(bs.DOG_ID_FIELD) == "rex"


@pytest.mark.asyncio
async def test_async_setup_entry_skips_invalid_dog_config_mappings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invalid dog config mappings should be ignored, including empty resulting sets."""
    added: list[bs.PawControlBinarySensorBase] = []
    entry = cast(PawControlConfigEntry, SimpleNamespace(entry_id="entry-2"))
    runtime_data = SimpleNamespace(
        coordinator=cast(PawControlCoordinator, _CoordinatorStub({})),
        dogs=[
            {
                "dog_name": "Missing dog id",
                "modules": {MODULE_FEEDING: True},
            },
        ],
    )
    monkeypatch.setattr(bs, "get_runtime_data", lambda hass, cfg: runtime_data)

    await bs.async_setup_entry(object(), entry, lambda entities: added.extend(entities))

    assert added == []


def test_sensor_fallback_paths_without_status_snapshot_or_module_payloads() -> None:
    """Sensors should safely evaluate when status snapshot and module data are sparse."""
    dog_data: CoordinatorDogData = cast(
        CoordinatorDogData,
        {
            MODULE_FEEDING: {},
            MODULE_WALK: {
                "last_long_walk": "invalid",
            },
            MODULE_GPS: {
                "zone": "unknown",
                "geofence_status": {"in_safe_zone": False},
            },
            MODULE_HEALTH: {},
            MODULE_GARDEN: {},
        },
    )
    coordinator = cast(PawControlCoordinator, _CoordinatorStub(dog_data))

    walk_sensor = bs.PawControlWalkInProgressBinarySensor(coordinator, "rex", "Rex")
    needs_walk_sensor = bs.PawControlNeedsWalkBinarySensor(coordinator, "rex", "Rex")
    safe_zone_sensor = bs.PawControlInSafeZoneBinarySensor(coordinator, "rex", "Rex")
    attention_sensor = bs.PawControlAttentionNeededBinarySensor(coordinator, "rex", "Rex")

    assert walk_sensor.is_on is False
    assert needs_walk_sensor.is_on is False
    assert safe_zone_sensor.is_on is False
    assert isinstance(attention_sensor.is_on, bool)

    # Branches where no payload should short-circuit with safe defaults.
    assert bs.PawControlFeedingScheduleOnTrackBinarySensor(coordinator, "rex", "Rex").is_on
    assert bs.PawControlIsHomeBinarySensor(coordinator, "rex", "Rex").is_on is False
    assert bs.PawControlGPSBatteryLowBinarySensor(coordinator, "rex", "Rex").is_on is False


def test_online_sensor_property_and_attribute_branches() -> None:
    """Online sensor should expose device class and handle varied attribute payloads."""
    now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    dog_data = cast(
        CoordinatorDogData,
        {
            "last_update": now,
            "status": "ok",
        },
    )
    coordinator = cast(
        PawControlCoordinator,
        _CoordinatorStub(dog_data, enabled_modules=[]),
    )
    sensor = bs.PawControlOnlineBinarySensor(coordinator, "rex", "Rex")
    assert sensor.device_class is not None
    attrs_dt = sensor.extra_state_attributes
    assert "status" in attrs_dt

    dog_data["last_update"] = now.isoformat()
    attrs_str = sensor.extra_state_attributes
    assert isinstance(attrs_str.get("last_update"), str)

    empty_sensor = bs.PawControlOnlineBinarySensor(
        cast(PawControlCoordinator, _CoordinatorStub({})),
        "rex",
        "Rex",
    )
    assert isinstance(empty_sensor.extra_state_attributes, dict)


def test_attention_sensor_covers_secondary_reason_branches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Attention sensor should include non-critical reason paths and GPS fallback checks."""
    dog_data = cast(
        CoordinatorDogData,
        {
            MODULE_FEEDING: {"is_hungry": True, "last_feeding_hours": 5},
            MODULE_WALK: {"needs_walk": True, "last_walk_hours": 6},
            MODULE_GPS: {"geofence_status": {"in_safe_zone": False}},
            MODULE_HEALTH: {"health_alerts": []},
        },
    )
    sensor = bs.PawControlAttentionNeededBinarySensor(
        cast(PawControlCoordinator, _CoordinatorStub(dog_data)),
        "rex",
        "Rex",
    )
    monkeypatch.setattr(sensor, "_get_status_snapshot", lambda: None)

    attrs_before = sensor.extra_state_attributes
    assert "attention_reasons" not in attrs_before

    assert sensor.is_on is True
    attrs_after = sensor.extra_state_attributes
    reasons = attrs_after.get("attention_reasons", [])
    assert "hungry" in reasons
    assert "needs_walk" in reasons
    assert "outside_safe_zone" in reasons

    sensor._attention_reasons = []
    assert sensor._calculate_urgency_level() == "none"
    del sensor._attention_reasons
    assert sensor._get_recommended_actions() == []
    sensor._attention_reasons = ["hungry"]
    assert sensor._get_recommended_actions() == ["Consider feeding"]


def test_attention_and_urgency_helper_paths_cover_all_levels() -> None:
    """Internal helper methods should classify urgency and recommendations consistently."""
    coordinator = cast(PawControlCoordinator, _CoordinatorStub({}))
    attention = bs.PawControlAttentionNeededBinarySensor(coordinator, "rex", "Rex")

    assert attention._calculate_urgency_level() == "none"
    attention._attention_reasons = ["hungry"]
    assert attention._calculate_urgency_level() == "low"
    attention._attention_reasons = ["hungry", "needs_walk", "outside_safe_zone"]
    assert attention._calculate_urgency_level() == "medium"
    attention._attention_reasons = ["health_alert"]
    assert attention._calculate_urgency_level() == "high"

    attention._attention_reasons = [
        "critically_hungry",
        "urgent_walk_needed",
        "health_alert",
        "outside_safe_zone",
    ]
    actions = attention._get_recommended_actions()
    assert "Feed immediately" in actions
    assert "Take for walk immediately" in actions
    assert "Check health status" in actions
    assert "Check location and safety" in actions


def test_domain_specific_helper_methods_cover_threshold_classifications() -> None:
    """Sensor helper methods should classify feeding/walk/activity values deterministically."""
    coordinator = cast(PawControlCoordinator, _CoordinatorStub({}))
    hungry = bs.PawControlIsHungryBinarySensor(coordinator, "rex", "Rex")
    walk = bs.PawControlWalkInProgressBinarySensor(coordinator, "rex", "Rex")
    needs_walk = bs.PawControlNeedsWalkBinarySensor(coordinator, "rex", "Rex")
    activity = bs.PawControlActivityLevelConcernBinarySensor(coordinator, "rex", "Rex")

    assert hungry._calculate_hunger_level({"last_feeding_hours": "bad"}) == bs.STATE_UNKNOWN
    assert hungry._calculate_hunger_level({"last_feeding_hours": 13}) == "very_hungry"
    assert hungry._calculate_hunger_level({"last_feeding_hours": 8}) == "hungry"
    assert hungry._calculate_hunger_level({"last_feeding_hours": 6}) == "somewhat_hungry"
    assert hungry._calculate_hunger_level({"last_feeding_hours": 2}) == "satisfied"

    assert walk._estimate_remaining_time(
        {"current_walk_duration": 10, "average_walk_duration": 25},
    ) == 15
    assert walk._estimate_remaining_time(
        {"current_walk_duration": 30, "average_walk_duration": 25},
    ) is None

    assert needs_walk._calculate_walk_urgency({"last_walk_hours": "bad"}) == bs.STATE_UNKNOWN
    assert needs_walk._calculate_walk_urgency({"last_walk_hours": 13}) == "urgent"
    assert needs_walk._calculate_walk_urgency({"last_walk_hours": 9}) == "high"
    assert needs_walk._calculate_walk_urgency({"last_walk_hours": 7}) == "medium"
    assert needs_walk._calculate_walk_urgency({"last_walk_hours": 2}) == "low"

    assert activity._get_concern_reason("very_low") == "Activity level is unusually low"
    assert activity._get_concern_reason("very_high") == "Activity level is unusually high"
    assert activity._get_concern_reason("normal") == "No concern"
    assert (
        activity._get_recommended_action("very_low")
        == "Consider vet consultation or encouraging more activity"
    )
    assert (
        activity._get_recommended_action("very_high")
        == "Monitor for signs of distress or illness"
    )
    assert activity._get_recommended_action("normal") == "Continue normal monitoring"


def test_core_sensor_no_data_and_invalid_data_fallbacks() -> None:
    """Sensors should return deterministic defaults for missing/invalid module payloads."""
    empty = cast(PawControlCoordinator, _CoordinatorStub({}))

    assert bs.PawControlVisitorModeBinarySensor(empty, "rex", "Rex").is_on is False
    assert bs.PawControlIsHungryBinarySensor(empty, "rex", "Rex").is_on is False
    assert bs.PawControlDailyFeedingGoalMetBinarySensor(empty, "rex", "Rex").is_on is False
    assert bs.PawControlWalkGoalMetBinarySensor(empty, "rex", "Rex").is_on is False
    assert bs.PawControlLongWalkOverdueBinarySensor(empty, "rex", "Rex").is_on is False
    assert bs.PawControlIsHomeBinarySensor(empty, "rex", "Rex").is_on is True
    assert bs.PawControlGPSAccuratelyTrackedBinarySensor(empty, "rex", "Rex").is_on is False
    assert bs.PawControlMovingBinarySensor(empty, "rex", "Rex").is_on is False
    assert bs.PawControlGeofenceAlertBinarySensor(empty, "rex", "Rex").is_on is False
    assert bs.PawControlGPSBatteryLowBinarySensor(empty, "rex", "Rex").is_on is False
    assert bs.PawControlHealthAlertBinarySensor(empty, "rex", "Rex").is_on is False
    assert bs.PawControlWeightAlertBinarySensor(empty, "rex", "Rex").is_on is False
    assert bs.PawControlMedicationDueBinarySensor(empty, "rex", "Rex").is_on is False
    assert bs.PawControlVetCheckupDueBinarySensor(empty, "rex", "Rex").is_on is False
    assert bs.PawControlGroomingDueBinarySensor(empty, "rex", "Rex").is_on is False
    assert bs.PawControlHealthAwareFeedingBinarySensor(empty, "rex", "Rex").is_on is False
    assert bs.PawControlMedicationWithMealsBinarySensor(empty, "rex", "Rex").is_on is False
    assert bs.PawControlHealthEmergencyBinarySensor(empty, "rex", "Rex").is_on is False
    assert bs.PawControlGardenSessionActiveBinarySensor(empty, "rex", "Rex").is_on is False

    visitor_data = cast(
        CoordinatorDogData,
        {
            bs.VISITOR_MODE_ACTIVE_FIELD: True,
            "visitor_mode_started": "2026-01-01T12:00:00+00:00",
            "visitor_mode_settings": {},
        },
    )
    visitor_sensor = bs.PawControlVisitorModeBinarySensor(
        cast(PawControlCoordinator, _CoordinatorStub(visitor_data)),
        "rex",
        "Rex",
    )
    visitor_attrs = visitor_sensor.extra_state_attributes
    assert visitor_attrs["visitor_mode_started"] == "2026-01-01T12:00:00+00:00"

    feeding_sensor = bs.PawControlIsHungryBinarySensor(
        cast(
            PawControlCoordinator,
            _CoordinatorStub(
                cast(
                    CoordinatorDogData,
                    {
                        MODULE_FEEDING: {
                            "last_feeding": "2026-01-01T07:00:00+00:00",
                            "last_feeding_hours": None,
                            "next_feeding_due": datetime(2026, 1, 1, 13, tzinfo=UTC),
                        }
                    },
                ),
            ),
        ),
        "rex",
        "Rex",
    )
    feeding_attrs = feeding_sensor.extra_state_attributes
    assert feeding_attrs["last_feeding"] == "2026-01-01T07:00:00+00:00"
    assert feeding_attrs["last_feeding_hours"] is None
    assert isinstance(feeding_attrs.get("next_feeding_due"), str)

    feeding_due_non_str = bs.PawControlFeedingDueBinarySensor(
        cast(
            PawControlCoordinator,
            _CoordinatorStub(cast(CoordinatorDogData, {MODULE_FEEDING: {"next_feeding_due": 1}})),
        ),
        "rex",
        "Rex",
    )
    assert feeding_due_non_str.is_on is False

    feeding_due_invalid = bs.PawControlFeedingDueBinarySensor(
        cast(
            PawControlCoordinator,
            _CoordinatorStub(
                cast(
                    CoordinatorDogData,
                    {MODULE_FEEDING: {"next_feeding_due": "not-a-timestamp"}},
                ),
            ),
        ),
        "rex",
        "Rex",
    )
    assert feeding_due_invalid.is_on is False

    schedule_sensor = bs.PawControlFeedingScheduleOnTrackBinarySensor(
        cast(
            PawControlCoordinator,
            _CoordinatorStub(
                cast(
                    CoordinatorDogData,
                    {MODULE_FEEDING: {"feeding_schedule_adherence": "bad"}},
                ),
            ),
        ),
        "rex",
        "Rex",
    )
    assert schedule_sensor.is_on is True


def test_walk_and_location_sensors_cover_status_snapshot_fallback_branches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Walk/location sensors should evaluate module payloads when status snapshots are absent."""
    walk_data = cast(
        CoordinatorDogData,
        {
            MODULE_WALK: {bs.WALK_IN_PROGRESS_FIELD: True, "needs_walk": True},
            MODULE_GPS: {
                "zone": "friend_house",
                "last_seen": "2026-01-01T12:00:00+00:00",
                "accuracy": 25,
                "geofence_alert": "invalid",
            },
        },
    )
    coordinator = cast(PawControlCoordinator, _CoordinatorStub(walk_data))

    walk_sensor = bs.PawControlWalkInProgressBinarySensor(coordinator, "rex", "Rex")
    needs_walk_sensor = bs.PawControlNeedsWalkBinarySensor(coordinator, "rex", "Rex")
    safe_zone_sensor = bs.PawControlInSafeZoneBinarySensor(coordinator, "rex", "Rex")
    geofence_sensor = bs.PawControlGeofenceAlertBinarySensor(coordinator, "rex", "Rex")
    home_sensor = bs.PawControlIsHomeBinarySensor(coordinator, "rex", "Rex")

    monkeypatch.setattr(walk_sensor, "_get_status_snapshot", lambda: None)
    monkeypatch.setattr(needs_walk_sensor, "_get_status_snapshot", lambda: None)
    monkeypatch.setattr(safe_zone_sensor, "_get_status_snapshot", lambda: None)

    assert walk_sensor.is_on is True
    assert needs_walk_sensor.is_on is True
    assert safe_zone_sensor.is_on is True
    assert geofence_sensor.is_on is False

    attrs = home_sensor.extra_state_attributes
    assert attrs["last_seen"] == "2026-01-01T12:00:00+00:00"

    no_walk = bs.PawControlWalkInProgressBinarySensor(
        cast(PawControlCoordinator, _CoordinatorStub(cast(CoordinatorDogData, {MODULE_WALK: {}}))),
        "rex",
        "Rex",
    )
    monkeypatch.setattr(no_walk, "_get_status_snapshot", lambda: None)
    assert no_walk.is_on is False

    no_needs_walk = bs.PawControlNeedsWalkBinarySensor(
        cast(PawControlCoordinator, _CoordinatorStub(cast(CoordinatorDogData, {MODULE_WALK: {}}))),
        "rex",
        "Rex",
    )
    monkeypatch.setattr(no_needs_walk, "_get_status_snapshot", lambda: None)
    assert no_needs_walk.is_on is False

    overdue_invalid = bs.PawControlLongWalkOverdueBinarySensor(
        cast(
            PawControlCoordinator,
            _CoordinatorStub(cast(CoordinatorDogData, {MODULE_WALK: {"last_long_walk": object()}})),
        ),
        "rex",
        "Rex",
    )
    assert overdue_invalid.is_on is True


def test_health_and_feeding_diagnostic_sensor_fallback_attributes() -> None:
    """Health/feed diagnostic sensors should normalize malformed payloads safely."""
    health_data = cast(
        CoordinatorDogData,
        {
            MODULE_HEALTH: {
                "health_alerts": 123,
                "health_status": None,
                "weight_change_percent": "bad",
                "medications_due": 123,
                "next_checkup_due": "bad-date",
            },
            MODULE_FEEDING: {
                "portion_adjustment_factor": None,
                "health_conditions": "bad",
                "medication_with_meals": True,
                "health_emergency": "bad",
                "emergency_mode": {
                    "activated_at": "2026-01-01T12:00:00+00:00",
                    "expires_at": None,
                    "status": 123,
                },
            },
        },
    )
    coordinator = cast(PawControlCoordinator, _CoordinatorStub(health_data))

    health_alert = bs.PawControlHealthAlertBinarySensor(coordinator, "rex", "Rex")
    assert health_alert.is_on is False
    health_attrs = health_alert.extra_state_attributes
    assert health_attrs["alert_count"] == 0

    assert bs.PawControlWeightAlertBinarySensor(coordinator, "rex", "Rex").is_on is False
    assert bs.PawControlMedicationDueBinarySensor(coordinator, "rex", "Rex").is_on is False
    assert bs.PawControlVetCheckupDueBinarySensor(coordinator, "rex", "Rex").is_on is False

    aware = bs.PawControlHealthAwareFeedingBinarySensor(coordinator, "rex", "Rex")
    aware_attrs = aware.extra_state_attributes
    assert aware_attrs["portion_adjustment_factor"] is None
    assert aware_attrs["health_conditions"] == []

    med_meals = bs.PawControlMedicationWithMealsBinarySensor(coordinator, "rex", "Rex")
    med_meals_attrs = med_meals.extra_state_attributes
    assert med_meals_attrs["health_conditions"] == []

    emergency = bs.PawControlHealthEmergencyBinarySensor(coordinator, "rex", "Rex")
    assert emergency.is_on is False
    emergency_attrs = emergency.extra_state_attributes
    assert emergency_attrs["activated_at"] == "2026-01-01T12:00:00+00:00"
    assert emergency_attrs["expires_at"] is None
    assert "status" not in emergency_attrs


def test_garden_sensor_manager_fallbacks_and_attribute_shapes() -> None:
    """Garden sensors should use manager snapshots and fallback checks when payload is absent."""
    snapshot = {
        "status": "active",
        "sessions_today": 1,
        "pending_confirmations": [{"id": "p1"}, {"id": "p2"}],
        "last_session": {
            "start_time": "2026-01-01T09:00:00+00:00",
            "duration_minutes": 10,
            "end_time": "2026-01-01T09:10:00+00:00",
        },
    }
    manager = _GardenManagerStub(
        snapshot=snapshot,
        in_garden=True,
        pending_confirmation=True,
    )
    coordinator = cast(
        PawControlCoordinator,
        _CoordinatorStub(
            {},
            runtime_managers=CoordinatorRuntimeManagers(garden_manager=manager),
        ),
    )

    session_sensor = bs.PawControlGardenSessionActiveBinarySensor(coordinator, "rex", "Rex")
    in_garden_sensor = bs.PawControlInGardenBinarySensor(coordinator, "rex", "Rex")
    pending_sensor = bs.PawControlGardenPoopPendingBinarySensor(coordinator, "rex", "Rex")

    assert session_sensor.is_on is True
    assert in_garden_sensor.is_on is True
    assert pending_sensor.is_on is True

    attrs = pending_sensor.extra_state_attributes
    assert attrs["pending_confirmation_count"] == 2

    failing_manager = _GardenManagerStub(raise_on_snapshot=True)
    failing_coordinator = cast(
        PawControlCoordinator,
        _CoordinatorStub(
            {},
            runtime_managers=CoordinatorRuntimeManagers(garden_manager=failing_manager),
        ),
    )
    fallback_sensor = bs.PawControlGardenSessionActiveBinarySensor(
        failing_coordinator,
        "rex",
        "Rex",
    )
    assert fallback_sensor.is_on is False

    empty_pending_sensor = bs.PawControlGardenPoopPendingBinarySensor(
        cast(
            PawControlCoordinator,
            _CoordinatorStub(cast(CoordinatorDogData, {MODULE_GARDEN: {"pending_confirmations": "bad"}})),
        ),
        "rex",
        "Rex",
    )
    empty_attrs = empty_pending_sensor.extra_state_attributes
    assert empty_attrs["pending_confirmation_count"] == 0


@pytest.mark.asyncio
async def test_async_setup_entry_module_gate_false_paths_and_empty_entities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Module gate checks should short-circuit correctly, including empty-entity fallback."""
    added: list[bs.PawControlBinarySensorBase] = []
    entry = cast(PawControlConfigEntry, SimpleNamespace(entry_id="entry-3"))
    runtime_data = SimpleNamespace(
        coordinator=cast(PawControlCoordinator, _CoordinatorStub({})),
        dogs=[
            {
                bs.DOG_ID_FIELD: "rex",
                bs.DOG_NAME_FIELD: "Rex",
                "modules": {
                    MODULE_FEEDING: False,
                    MODULE_WALK: False,
                    MODULE_GPS: False,
                    MODULE_HEALTH: False,
                    MODULE_GARDEN: False,
                },
            },
        ],
    )
    monkeypatch.setattr(bs, "get_runtime_data", lambda hass, cfg: runtime_data)
    await bs.async_setup_entry(object(), entry, lambda entities: added.extend(entities))
    assert len(added) == 3

    # Force the "if entities" false branch.
    monkeypatch.setattr(bs, "_create_base_binary_sensors", lambda *args, **kwargs: [])
    added.clear()
    await bs.async_setup_entry(object(), entry, lambda entities: added.extend(entities))
    assert added == []


def test_is_on_deleter_without_override_is_a_noop() -> None:
    """Deleting is_on without a test override should not raise."""
    sensor = bs.PawControlOnlineBinarySensor(
        cast(PawControlCoordinator, _CoordinatorStub({})),
        "rex",
        "Rex",
    )
    del sensor.is_on
    assert isinstance(sensor.is_on, bool)


def test_online_and_visitor_attribute_edge_branches() -> None:
    """Online/visitor attribute builders should handle unexpected payload types."""
    online_sensor = bs.PawControlOnlineBinarySensor(
        cast(
            PawControlCoordinator,
            _CoordinatorStub(cast(CoordinatorDogData, {"last_update": 123, "status": "ok"})),
        ),
        "rex",
        "Rex",
    )
    online_attrs = online_sensor.extra_state_attributes
    assert online_attrs["status"] == "ok"

    visitor_false = bs.PawControlVisitorModeBinarySensor(
        cast(PawControlCoordinator, _CoordinatorStub({}, available=False)),
        "rex",
        "Rex",
    )
    assert isinstance(visitor_false.extra_state_attributes, dict)

    visitor_sensor = bs.PawControlVisitorModeBinarySensor(
        cast(
            PawControlCoordinator,
            _CoordinatorStub(
                cast(
                    CoordinatorDogData,
                    {
                        bs.VISITOR_MODE_ACTIVE_FIELD: True,
                        "visitor_mode_started": 123,
                        "visitor_mode_settings": {},
                    },
                ),
            ),
        ),
        "rex",
        "Rex",
    )
    attrs = visitor_sensor.extra_state_attributes
    assert "visitor_mode_started" not in attrs


def test_attention_recommendation_and_geofence_branch_matrix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Attention sensor should cover snapshot/geofence recommendation branch variants."""
    # Snapshot present and safe -> no outside-safe-zone reason.
    snapshot_sensor = bs.PawControlAttentionNeededBinarySensor(
        cast(
            PawControlCoordinator,
            _CoordinatorStub(
                cast(
                    CoordinatorDogData,
                    {"status_snapshot": {"in_safe_zone": True}, MODULE_FEEDING: {}},
                ),
            ),
        ),
        "rex",
        "Rex",
    )
    assert snapshot_sensor.is_on is False

    # No snapshot and no GPS data -> fallback branch.
    no_gps_sensor = bs.PawControlAttentionNeededBinarySensor(
        cast(PawControlCoordinator, _CoordinatorStub(cast(CoordinatorDogData, {MODULE_FEEDING: {}}))),
        "rex",
        "Rex",
    )
    monkeypatch.setattr(no_gps_sensor, "_get_status_snapshot", lambda: None)
    assert no_gps_sensor.is_on is False

    # No snapshot, non-mapping geofence payload -> keep safe-zone default.
    geofence_sensor = bs.PawControlAttentionNeededBinarySensor(
        cast(
            PawControlCoordinator,
            _CoordinatorStub(cast(CoordinatorDogData, {MODULE_GPS: {"geofence_status": "bad"}})),
        ),
        "rex",
        "Rex",
    )
    monkeypatch.setattr(geofence_sensor, "_get_status_snapshot", lambda: None)
    assert geofence_sensor.is_on is False
    geofence_sensor._attention_reasons = ["needs_walk"]
    assert geofence_sensor._get_recommended_actions() == []


def test_hungry_walk_needs_and_home_attribute_branch_fallbacks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Feeding/walk/location attribute builders should cover edge payload branches."""
    hungry_sensor = bs.PawControlIsHungryBinarySensor(
        cast(PawControlCoordinator, _CoordinatorStub({})),
        "rex",
        "Rex",
    )
    assert isinstance(hungry_sensor.extra_state_attributes, dict)

    weird_feeding_sensor = bs.PawControlIsHungryBinarySensor(
        cast(
            PawControlCoordinator,
            _CoordinatorStub(
                cast(
                    CoordinatorDogData,
                    {
                        MODULE_FEEDING: {
                            "last_feeding": 123,
                            "last_feeding_hours": "bad",
                            "next_feeding_due": 123,
                        }
                    },
                ),
            ),
        ),
        "rex",
        "Rex",
    )
    weird_feeding_attrs = weird_feeding_sensor.extra_state_attributes
    assert "last_feeding" not in weird_feeding_attrs
    assert "last_feeding_hours" not in weird_feeding_attrs
    assert "next_feeding_due" not in weird_feeding_attrs

    walk_sensor = bs.PawControlWalkInProgressBinarySensor(
        cast(
            PawControlCoordinator,
            _CoordinatorStub(
                cast(
                    CoordinatorDogData,
                    {MODULE_WALK: {bs.WALK_IN_PROGRESS_FIELD: True, "current_walk": "bad"}},
                ),
            ),
        ),
        "rex",
        "Rex",
    )
    monkeypatch.setattr(walk_sensor, "_get_status_snapshot", lambda: None)
    walk_attrs = walk_sensor.extra_state_attributes
    assert "distance_meters" not in walk_attrs
    assert "estimated_remaining" not in walk_attrs

    needs_walk_sensor = bs.PawControlNeedsWalkBinarySensor(
        cast(
            PawControlCoordinator,
            _CoordinatorStub(
                cast(
                    CoordinatorDogData,
                    {MODULE_WALK: {"last_walk": "2026-01-01T10:00:00+00:00", "walks_today": "bad"}},
                ),
            ),
        ),
        "rex",
        "Rex",
    )
    needs_walk_attrs = needs_walk_sensor.extra_state_attributes
    assert needs_walk_attrs["last_walk"] == "2026-01-01T10:00:00+00:00"
    assert "walks_today" not in needs_walk_attrs

    home_sensor_no_gps = bs.PawControlIsHomeBinarySensor(
        cast(PawControlCoordinator, _CoordinatorStub({})),
        "rex",
        "Rex",
    )
    assert isinstance(home_sensor_no_gps.extra_state_attributes, dict)

    home_sensor_odd = bs.PawControlIsHomeBinarySensor(
        cast(
            PawControlCoordinator,
            _CoordinatorStub(
                cast(CoordinatorDogData, {MODULE_GPS: {"last_seen": 1, "accuracy": "bad"}}),
            ),
        ),
        "rex",
        "Rex",
    )
    odd_attrs = home_sensor_odd.extra_state_attributes
    assert "last_seen" not in odd_attrs
    assert "accuracy" not in odd_attrs

    safe_zone_sensor = bs.PawControlInSafeZoneBinarySensor(
        cast(PawControlCoordinator, _CoordinatorStub({})),
        "rex",
        "Rex",
    )
    monkeypatch.setattr(safe_zone_sensor, "_get_status_snapshot", lambda: None)
    assert safe_zone_sensor.is_on is True
    safe_zone_attrs = safe_zone_sensor.extra_state_attributes
    assert safe_zone_attrs["last_seen"] is None


def test_health_activity_and_emergency_attribute_branch_fallbacks() -> None:
    """Health-family sensors should cover remaining malformed and empty branch paths."""
    health_empty = cast(PawControlCoordinator, _CoordinatorStub({}))
    alert_sensor = bs.PawControlHealthAlertBinarySensor(health_empty, "rex", "Rex")
    assert isinstance(alert_sensor.extra_state_attributes, dict)

    checkup_sensor = bs.PawControlVetCheckupDueBinarySensor(
        cast(
            PawControlCoordinator,
            _CoordinatorStub(cast(CoordinatorDogData, {MODULE_HEALTH: {"next_checkup_due": 123}})),
        ),
        "rex",
        "Rex",
    )
    assert checkup_sensor.is_on is False

    activity_sensor = bs.PawControlActivityLevelConcernBinarySensor(health_empty, "rex", "Rex")
    assert isinstance(activity_sensor.extra_state_attributes, dict)

    aware_sensor = bs.PawControlHealthAwareFeedingBinarySensor(health_empty, "rex", "Rex")
    aware_attrs = aware_sensor.extra_state_attributes
    assert aware_attrs["health_conditions"] == []

    aware_sensor_weird = bs.PawControlHealthAwareFeedingBinarySensor(
        cast(
            PawControlCoordinator,
            _CoordinatorStub(
                cast(
                    CoordinatorDogData,
                    {MODULE_FEEDING: {"portion_adjustment_factor": "bad", "health_conditions": []}},
                ),
            ),
        ),
        "rex",
        "Rex",
    )
    aware_weird_attrs = aware_sensor_weird.extra_state_attributes
    assert "portion_adjustment_factor" not in aware_weird_attrs

    med_meals_sensor = bs.PawControlMedicationWithMealsBinarySensor(
        cast(
            PawControlCoordinator,
            _CoordinatorStub(
                cast(
                    CoordinatorDogData,
                    {MODULE_FEEDING: {"health_conditions": "bad"}},
                ),
            ),
        ),
        "rex",
        "Rex",
    )
    assert med_meals_sensor.extra_state_attributes["health_conditions"] == []

    emergency_no_mapping = bs.PawControlHealthEmergencyBinarySensor(
        cast(
            PawControlCoordinator,
            _CoordinatorStub(cast(CoordinatorDogData, {MODULE_FEEDING: {"emergency_mode": "bad"}})),
        ),
        "rex",
        "Rex",
    )
    assert isinstance(emergency_no_mapping.extra_state_attributes, dict)

    emergency_odd_types = bs.PawControlHealthEmergencyBinarySensor(
        cast(
            PawControlCoordinator,
            _CoordinatorStub(
                cast(
                    CoordinatorDogData,
                    {
                        MODULE_FEEDING: {
                            "emergency_mode": {
                                "activated_at": 1,
                                "expires_at": 1,
                            }
                        }
                    },
                ),
            ),
        ),
        "rex",
        "Rex",
    )
    emergency_attrs = emergency_odd_types.extra_state_attributes
    assert "activated_at" not in emergency_attrs
    assert "expires_at" not in emergency_attrs


def test_remaining_branch_paths_for_garden_walk_health_and_medication_attrs() -> None:
    """Cover remaining attribute branches with absent/odd module payload fields."""
    garden_sensor = bs.PawControlInGardenBinarySensor(
        cast(
            PawControlCoordinator,
            _CoordinatorStub(cast(CoordinatorDogData, {MODULE_GARDEN: {"status": "idle"}})),
        ),
        "rex",
        "Rex",
    )
    garden_attrs = garden_sensor.extra_state_attributes
    assert "pending_confirmations" not in garden_attrs

    needs_walk_empty = bs.PawControlNeedsWalkBinarySensor(
        cast(PawControlCoordinator, _CoordinatorStub(cast(CoordinatorDogData, {MODULE_WALK: {}}))),
        "rex",
        "Rex",
    )
    assert isinstance(needs_walk_empty.extra_state_attributes, dict)

    needs_walk_weird = bs.PawControlNeedsWalkBinarySensor(
        cast(
            PawControlCoordinator,
            _CoordinatorStub(cast(CoordinatorDogData, {MODULE_WALK: {"last_walk": 123}})),
        ),
        "rex",
        "Rex",
    )
    weird_attrs = needs_walk_weird.extra_state_attributes
    assert "last_walk" not in weird_attrs

    health_sensor = bs.PawControlHealthAlertBinarySensor(
        cast(
            PawControlCoordinator,
            _CoordinatorStub(
                cast(
                    CoordinatorDogData,
                    {MODULE_HEALTH: {"health_alerts": [], "health_status": 123}},
                ),
            ),
        ),
        "rex",
        "Rex",
    )
    health_attrs = health_sensor.extra_state_attributes
    assert "health_status" not in health_attrs

    med_with_meals_empty = bs.PawControlMedicationWithMealsBinarySensor(
        cast(PawControlCoordinator, _CoordinatorStub({})),
        "rex",
        "Rex",
    )
    assert med_with_meals_empty.extra_state_attributes["health_conditions"] == []
