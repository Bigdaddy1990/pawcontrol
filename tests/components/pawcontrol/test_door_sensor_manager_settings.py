"""Coverage tests for door sensor settings normalization and diagnostics helpers."""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

from homeassistant.util import dt as dt_util
import pytest

from custom_components.pawcontrol.door_sensor_manager import (
    DoorSensorConfig,
    WalkDetectionState,
    _apply_settings_to_config,
    _classify_timestamp,
    _DoorSensorManagerCacheMonitor,
    _settings_to_payload,
    ensure_door_sensor_settings_config,
)
from custom_components.pawcontrol.types import (
    DEFAULT_DOOR_SENSOR_SETTINGS,
    DoorSensorSettingsConfig,
)


def test_ensure_door_sensor_settings_config_normalizes_aliases_and_bounds() -> None:
    """Mixed alias inputs should coerce and clamp into a safe settings object."""
    settings = ensure_door_sensor_settings_config({
        " timeout ": " 20 ",
        "min_duration": "45",
        "max_walk_duration": "999999",
        "close_timeout": -5,
        "confirmation_required": "yes",
        "auto_close": "0",
        "threshold": "1.8",
    })

    assert settings.walk_detection_timeout == 30
    assert settings.minimum_walk_duration == 60
    assert settings.maximum_walk_duration == 43200
    assert settings.door_closed_delay == 0
    assert settings.require_confirmation is True
    assert settings.auto_end_walks is False
    assert settings.confidence_threshold == 1.0


def test_ensure_door_sensor_settings_config_uses_base_and_door_sensor_config() -> None:
    """The helper should reuse base values when overrides are missing or invalid."""
    base_config = DoorSensorConfig(
        entity_id="binary_sensor.back_door",
        dog_id="dog-1",
        dog_name="Buddy",
        walk_detection_timeout=500,
        minimum_walk_duration=240,
        maximum_walk_duration=1800,
        door_closed_delay=30,
        require_confirmation=False,
        auto_end_walks=False,
        confidence_threshold=0.35,
    )

    settings = ensure_door_sensor_settings_config(
        {
            "walk_timeout": "not-a-number",
            "require_confirmation": "",
            "auto_end_walk": 3,
        },
        base=base_config,
    )

    assert settings.walk_detection_timeout == 500
    assert settings.minimum_walk_duration == 240
    assert settings.maximum_walk_duration == 1800
    assert settings.door_closed_delay == 30
    assert settings.require_confirmation is False
    assert settings.auto_end_walks is True
    assert settings.confidence_threshold == 0.35


def test_ensure_door_sensor_settings_config_rejects_non_mapping_inputs() -> None:
    """Invalid override shapes should raise a clear type error."""
    with pytest.raises(TypeError):
        ensure_door_sensor_settings_config(["bad-input"])  # type: ignore[arg-type]


def test_apply_settings_to_config_and_payload_roundtrip() -> None:
    """Applying settings should update the runtime config and payload serialization."""
    config = DoorSensorConfig(
        entity_id="binary_sensor.front_door",
        dog_id="dog-9",
        dog_name="Luna",
    )
    updated = DoorSensorSettingsConfig(
        walk_detection_timeout=720,
        minimum_walk_duration=300,
        maximum_walk_duration=1200,
        door_closed_delay=20,
        require_confirmation=False,
        auto_end_walks=True,
        confidence_threshold=0.42,
    )

    _apply_settings_to_config(config, updated)
    payload = _settings_to_payload(updated)

    assert config.walk_detection_timeout == updated.walk_detection_timeout
    assert config.minimum_walk_duration == updated.minimum_walk_duration
    assert config.maximum_walk_duration == updated.maximum_walk_duration
    assert config.door_closed_delay == updated.door_closed_delay
    assert config.require_confirmation == updated.require_confirmation
    assert config.auto_end_walks == updated.auto_end_walks
    assert config.confidence_threshold == updated.confidence_threshold
    assert payload["walk_detection_timeout"] == 720
    assert payload["confidence_threshold"] == 0.42


def test_classify_timestamp_handles_none_recent_future_and_stale() -> None:
    """Timestamp classification should emit anomaly labels only for threshold breaches."""
    assert _classify_timestamp(None) == (None, None)

    recent_value = dt_util.utcnow() - timedelta(seconds=5)
    recent_reason, recent_age = _classify_timestamp(recent_value)
    assert recent_reason is None
    assert isinstance(recent_age, int)

    future_reason, _future_age = _classify_timestamp(
        dt_util.utcnow() + timedelta(hours=2)
    )
    assert future_reason == "future"

    stale_reason, stale_age = _classify_timestamp(dt_util.utcnow() - timedelta(days=2))
    assert stale_reason == "stale"
    assert isinstance(stale_age, int)


def test_cache_monitor_build_payload_reports_anomalies_and_active_detection() -> None:
    """Cache monitor snapshot should include active states and timestamp anomalies."""
    now = dt_util.utcnow()
    config = DoorSensorConfig(
        entity_id="binary_sensor.garden_door",
        dog_id="dog-alpha",
        dog_name="Alpha",
        confidence_threshold=0.66789,
    )
    state = WalkDetectionState(
        dog_id="dog-alpha",
        current_state="active",
        door_opened_at=now - timedelta(days=2),
        confidence_score=0.12345,
        state_history=[(now - timedelta(days=2), "open")],
    )

    manager = SimpleNamespace(
        _sensor_configs={"dog-alpha": config, 101: config},
        _detection_states={"dog-alpha": state},
        _detection_stats={"detection_attempts": 4},
        _last_activity=now + timedelta(hours=3),
        _cleanup_task=object(),
    )

    monitor = _DoorSensorManagerCacheMonitor(manager)
    stats, snapshot, diagnostics = monitor._build_payload()

    assert stats["configured_sensors"] == 1
    assert stats["active_detections"] == 1
    assert snapshot["per_dog"]["dog-alpha"]["confidence_threshold"] == 0.668
    assert snapshot["per_dog"]["dog-alpha"]["state"]["confidence_score"] == 0.123
    assert diagnostics["cleanup_task_active"] is True
    assert diagnostics["timestamp_anomalies"] == {
        "dog-alpha": "stale",
        "manager": "future",
    }


def test_ensure_settings_returns_defaults_for_none() -> None:
    """No overrides should return the canonical default settings object."""
    settings = ensure_door_sensor_settings_config(None)
    assert settings == DEFAULT_DOOR_SENSOR_SETTINGS
