"""Regression tests for the resilience escalation diagnostics snapshot."""

from dataclasses import dataclass
from datetime import timedelta
import json
from types import MethodType, SimpleNamespace

from homeassistant.util import dt as dt_util
import pytest

from custom_components.pawcontrol.const import DOMAIN
from custom_components.pawcontrol.script_manager import (
    PawControlScriptManager,
    _classify_timestamp,
    _coerce_threshold,
    _extract_field_int,
    _is_resilience_blueprint,
    _normalise_entry_slug,
    _parse_event_selection,
    _parse_manual_resilience_options,
    _resolve_resilience_entity_id,
    _resolve_resilience_object_id,
    _serialise_event_data,
    resolve_resilience_script_thresholds,
)


@pytest.mark.unit
def test_resilience_snapshot_requires_definition() -> None:
    """The resilience snapshot should be unavailable without a definition."""
    hass = SimpleNamespace(
        data={DOMAIN: {}},
        states={},
        config_entries=SimpleNamespace(async_entries=lambda domain: []),
        bus=SimpleNamespace(async_listen=lambda event_type, callback: None),
    )
    entry = SimpleNamespace(
        entry_id="entry",
        data={},
        options={},
        runtime_data={},
        title="PawControl Test",
    )

    manager = PawControlScriptManager(hass, entry)

    assert manager.get_resilience_escalation_snapshot() is None


@pytest.mark.unit
def test_resilience_snapshot_serialises_manual_payload() -> None:
    """The resilience snapshot should expose JSON-safe manual event payloads."""
    now = dt_util.utcnow()
    hass = SimpleNamespace(
        data={DOMAIN: {}},
        states={},
        config_entries=SimpleNamespace(async_entries=lambda domain: []),
        bus=SimpleNamespace(async_listen=lambda event_type, callback: None),
    )
    entry = SimpleNamespace(
        entry_id="entry",
        data={},
        options={},
        runtime_data={},
        title="Buddy",
    )

    manager = PawControlScriptManager(hass, entry)
    manager._resilience_escalation_definition = {  # type: ignore[attr-defined]
        "object_id": "pawcontrol_buddy_resilience_escalation",
        "alias": "Buddy resilience escalation",
        "description": "Escalates guard and breaker events",
        "field_defaults": {
            "skip_threshold": 3,
            "breaker_threshold": 2,
            "followup_script": "script.followup",
            "statistics_entity_id": "sensor.pawcontrol_statistics",
            "escalation_service": "persistent_notification.create",
        },
    }
    manager._entry_scripts = [  # type: ignore[attr-defined]
        "script.pawcontrol_buddy_resilience_escalation"
    ]
    manager._last_generation = now - timedelta(minutes=5)  # type: ignore[attr-defined]

    manual_record = {
        "event_type": "manual.guard",
        "preference_key": "manual_guard_event",
        "configured_role": "guard",
        "time_fired": now - timedelta(minutes=2, seconds=30),
        "received_at": now - timedelta(minutes=2),
        "recorded_at": now - timedelta(minutes=2),
        "data": {"skip_count": 4},
        "sources": ("automation.resilience",),
        "reasons": ["guard"],
    }
    manager._manual_event_history.clear()  # type: ignore[attr-defined]
    manager._manual_event_history.append(manual_record)  # type: ignore[attr-defined]
    manager._manual_event_counters = {  # type: ignore[attr-defined]
        "manual.guard": 2,
        "manual.breaker": 1,
    }
    manager._manual_event_sources = {  # type: ignore[attr-defined]
        "manual.guard": {
            "preference_key": "manual_guard_event",
            "configured_role": "guard",
        }
    }

    manual_events_payload = {
        "available": True,
        "automations": [
            {
                "config_entry_id": "automation-entry",
                "title": "Resilience automation",
                "manual_guard_event": "manual.guard",
                "manual_breaker_event": "manual.breaker",
            }
        ],
        "configured_guard_events": ["manual.guard"],
        "configured_breaker_events": ["manual.breaker"],
        "configured_check_events": [],
        "system_guard_event": "manual.guard",
        "system_breaker_event": "manual.breaker",
        "listener_events": {
            "manual.guard": ["guard"],
            "manual.breaker": ["breaker"],
        },
        "listener_sources": {
            "manual.guard": ["automation.resilience"],
        },
        "listener_metadata": {
            "manual.guard": {
                "sources": ["automation.resilience"],
                "primary_source": "automation.resilience",
            }
        },
        "event_history": [],
        "last_event": None,
        "last_trigger": None,
        "event_counters": {"total": 0, "by_event": {}, "by_reason": {}},
        "active_listeners": [],
    }
    manual_preferences = {
        "manual_guard_event": "manual.guard",
        "manual_breaker_event": "manual.breaker",
        "manual_check_event": None,
    }

    manager._resolve_manual_resilience_events = MethodType(  # type: ignore[attr-defined]
        lambda self: manual_events_payload,
        manager,
    )
    manager._manual_event_preferences = MethodType(  # type: ignore[attr-defined]
        lambda self: manual_preferences,
        manager,
    )
    manager._manual_event_source_mapping = MethodType(  # type: ignore[attr-defined]
        lambda self: {
            "manual.guard": {
                "preference_key": "manual_guard_event",
                "listener_sources": ("automation.resilience",),
            },
            "manual.breaker": {"preference_key": "manual_breaker_event"},
        },
        manager,
    )

    hass.states = {  # type: ignore[assignment]
        "script.pawcontrol_buddy_resilience_escalation": SimpleNamespace(
            attributes={
                "last_triggered": now - timedelta(minutes=1),
                "fields": {
                    "skip_threshold": {"default": 5},
                    "breaker_threshold": {"default": 4},
                    "followup_script": {"default": "script.alternate"},
                    "statistics_entity_id": {"default": "sensor.alt_statistics"},
                    "escalation_service": {"default": "persistent_notification.create"},
                },
            }
        )
    }

    snapshot = manager.get_resilience_escalation_snapshot()
    assert snapshot is not None
    assert snapshot["available"] is True
    assert snapshot["entity_id"] == "script.pawcontrol_buddy_resilience_escalation"
    assert snapshot["manual_events"]["available"] is True
    assert snapshot["manual_events"]["preferred_guard_event"] == "manual.guard"
    assert snapshot["manual_events"]["preferred_breaker_event"] == "manual.breaker"
    assert snapshot["manual_events"]["preferred_check_event"] is None
    assert snapshot["manual_events"]["event_counters"]["total"] == 3
    assert snapshot["manual_events"]["event_counters"]["by_event"] == {
        "manual.breaker": 1,
        "manual.guard": 2,
    }
    assert snapshot["manual_events"]["event_counters"]["by_reason"]["guard"] == 2
    assert snapshot["manual_events"]["active_listeners"] == [
        "manual.breaker",
        "manual.guard",
    ]

    history = snapshot["manual_events"]["event_history"]
    assert isinstance(history, list) and history
    assert history[0]["event_type"] == "manual.guard"
    assert isinstance(history[0]["time_fired"], str)

    # The manual payload must be JSON serialisable so diagnostics remain stable.
    json.dumps(snapshot["manual_events"])

    thresholds = snapshot["thresholds"]
    assert thresholds["skip_threshold"]["active"] == 5
    assert thresholds["breaker_threshold"]["active"] == 4
    assert snapshot["followup_script"]["configured"] is True


@pytest.mark.unit
def test_parse_manual_resilience_options_filters_invalid_values() -> None:
    """Parser should normalise accepted values and drop malformed options."""
    payload = {
        "manual_check_event": "  manual.check  ",
        "manual_guard_event": "",
        "manual_breaker_event": "manual.breaker",
        "resilience_skip_threshold": "4",
        "resilience_breaker_threshold": 3.0,
        "manual_event_history_size": 1000,
        "system_settings": {
            "manual_check_event": "system.check",
            "manual_guard_event": None,
            "manual_breaker_event": "  system.breaker  ",
            "resilience_skip_threshold": True,
            "resilience_breaker_threshold": "6",
        },
    }

    parsed = _parse_manual_resilience_options(payload)
    assert parsed == {
        "manual_check_event": "manual.check",
        "manual_breaker_event": "manual.breaker",
        "resilience_skip_threshold": 4,
        "resilience_breaker_threshold": 3,
        "system_settings": {
            "manual_check_event": "system.check",
            "manual_breaker_event": "system.breaker",
            "resilience_skip_threshold": 1,
            "resilience_breaker_threshold": 6,
        },
    }


@pytest.mark.unit
def test_parse_event_selection_preserves_explicit_none() -> None:
    """Selection parser should retain provided keys even when invalid."""
    parsed = _parse_event_selection({
        "manual_check_event": "  ",
        "manual_guard_event": "manual.guard",
    })

    assert parsed == {
        "manual_check_event": None,
        "manual_guard_event": "manual.guard",
    }


@pytest.mark.unit
def test_resolve_resilience_script_thresholds_reads_entity_fields() -> None:
    """Threshold resolver should handle mapping and object defaults."""

    class _States:
        def get(self, entity_id: str) -> SimpleNamespace | None:
            if entity_id != "script.pawcontrol_buddy_resilience_escalation":
                return None
            return SimpleNamespace(
                attributes={
                    "fields": {
                        "skip_threshold": {"default": "7"},
                        "breaker_threshold": SimpleNamespace(default=8.0),
                    }
                }
            )

    entry = SimpleNamespace(title="Buddy", entry_id="entry")
    hass = SimpleNamespace(states=_States())

    skip, breaker = resolve_resilience_script_thresholds(hass, entry)

    assert (skip, breaker) == (7, 8)


@pytest.mark.unit
def test_extract_field_int_handles_mapping_and_object_defaults() -> None:
    """Field extraction should support mapping defaults and object attributes."""
    field_object = SimpleNamespace(default="9")
    fields = {
        "skip_threshold": {"default": "7"},
        "breaker_threshold": field_object,
        "missing_default": {"name": "ignored"},
    }

    assert _extract_field_int(fields, "skip_threshold") == 7
    assert _extract_field_int(fields, "breaker_threshold") == 9
    assert _extract_field_int(fields, "missing_default") is None
    assert _extract_field_int(fields, "unknown") is None
    assert _extract_field_int(None, "skip_threshold") is None


@pytest.mark.unit
def test_coerce_threshold_clamps_and_falls_back_to_default() -> None:
    """Threshold coercion should clamp to limits and honour the default."""
    assert _coerce_threshold(None, default=5, minimum=1, maximum=9) == 5
    assert _coerce_threshold("0", default=5, minimum=1, maximum=9) == 1
    assert _coerce_threshold("42", default=5, minimum=1, maximum=9) == 9
    assert _coerce_threshold("4", default=5, minimum=1, maximum=9) == 4


@pytest.mark.unit
def test_resilience_blueprint_detection_matches_suffix() -> None:
    """Blueprint matcher should accept known key names and slash variants."""
    assert (
        _is_resilience_blueprint({
            "path": (
                "BluePrints\\Automation\\pawcontrol\\"
                "resilience_escalation_followup.yaml"
            )
        })
        is True
    )
    assert _is_resilience_blueprint({"id": "pawcontrol/other.yaml"}) is False
    assert _is_resilience_blueprint(None) is False


@pytest.mark.unit
def test_serialise_event_data_normalises_nested_values() -> None:
    """Event serialiser should convert nested non-JSON values into strings."""
    payload = {
        1: "ok",
        "nested": {"enabled": True, "raw": object()},
        "sequence": ["value", 3, object()],
    }

    serialised = _serialise_event_data(payload)

    assert serialised["1"] == "ok"
    assert serialised["nested"]["enabled"] is True
    assert isinstance(serialised["nested"]["raw"], str)
    assert serialised["sequence"][0:2] == ["value", 3]
    assert isinstance(serialised["sequence"][2], str)


@pytest.mark.unit
def test_blueprint_detection_and_event_data_serialisation() -> None:
    """Helpers should detect blueprint paths and serialise nested payloads."""
    assert _is_resilience_blueprint({
        "path": "PawControl\\resilience_escalation_followup.yaml"
    })
    assert not _is_resilience_blueprint({"path": "pawcontrol/other.yaml"})

    class _Opaque:
        pass

    payload = _serialise_event_data({
        "count": 3,
        "nested": {"flag": True, "opaque": _Opaque()},
        "sequence": [1, {"x": "y"}, _Opaque()],
    })

    assert payload["count"] == 3
    assert payload["nested"]["flag"] is True  # type: ignore[index]
    assert "opaque" in payload["nested"]  # type: ignore[index]
    assert payload["sequence"][0] == 1  # type: ignore[index]
    assert isinstance(payload["sequence"][1], str)  # type: ignore[index]


@pytest.mark.unit
def test_slug_and_resilience_entity_resolution_fall_back_to_entry_id() -> None:
    """Slug and entity/object IDs should remain deterministic for empty titles."""
    entry = SimpleNamespace(title="", entry_id="Entry-ID")

    assert _normalise_entry_slug(entry) == "entry-id"
    assert (
        _resolve_resilience_object_id(entry)
        == "pawcontrol_entry-id_resilience_escalation"
    )
    assert (
        _resolve_resilience_entity_id(entry)
        == "script.pawcontrol_entry-id_resilience_escalation"
    )


@pytest.mark.unit
def test_coerce_threshold_clamps_and_defaults() -> None:
    """Threshold coercion should clamp out-of-range values and use defaults."""
    assert _coerce_threshold(None, default=3, minimum=1, maximum=5) == 3
    assert _coerce_threshold("0", default=3, minimum=1, maximum=5) == 1
    assert _coerce_threshold("8", default=3, minimum=1, maximum=5) == 5
    assert _coerce_threshold(4, default=3, minimum=1, maximum=5) == 4


@pytest.mark.unit
def test_extract_field_int_supports_mapping_and_objects() -> None:
    """Field extraction should read mapping/object defaults and ignore invalid data."""

    @dataclass
    class _FieldObject:
        default: object

    assert _extract_field_int(None, "skip_threshold") is None
    assert (
        _extract_field_int({"skip_threshold": {"default": "6"}}, "skip_threshold") == 6
    )
    assert (
        _extract_field_int({"skip_threshold": _FieldObject(7.0)}, "skip_threshold") == 7
    )
    assert (
        _extract_field_int({"skip_threshold": {"default": "bad"}}, "skip_threshold")
        is None
    )


@pytest.mark.unit
def test_resolve_resilience_script_thresholds_handles_missing_state_shape() -> None:
    """Threshold resolver should gracefully handle missing state accessors."""
    entry = SimpleNamespace(title="Buddy", entry_id="entry")

    assert resolve_resilience_script_thresholds(
        SimpleNamespace(states=None), entry
    ) == (
        None,
        None,
    )
    assert resolve_resilience_script_thresholds(SimpleNamespace(states={}), entry) == (
        None,
        None,
    )


@pytest.mark.unit
def test_classify_timestamp_covers_recent_stale_and_future_values() -> None:
    """Timestamp classification should expose reason labels and ages."""
    now = dt_util.utcnow()

    reason, age = _classify_timestamp(now)
    assert reason is None
    assert isinstance(age, int)

    stale_reason, stale_age = _classify_timestamp(now - timedelta(days=3))
    assert stale_reason == "stale"
    assert isinstance(stale_age, int) and stale_age > 0

    future_reason, future_age = _classify_timestamp(now + timedelta(days=3))
    assert future_reason == "future"
    assert isinstance(future_age, int) and future_age < 0
