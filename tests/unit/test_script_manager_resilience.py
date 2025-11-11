"""Regression tests for the resilience escalation diagnostics snapshot."""

from __future__ import annotations

import json
from datetime import timedelta
from types import MethodType, SimpleNamespace

import pytest
from custom_components.pawcontrol.const import DOMAIN
from custom_components.pawcontrol.script_manager import PawControlScriptManager
from homeassistant.util import dt as dt_util


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
    assert (
        snapshot["entity_id"]
        == "script.pawcontrol_buddy_resilience_escalation"
    )
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
