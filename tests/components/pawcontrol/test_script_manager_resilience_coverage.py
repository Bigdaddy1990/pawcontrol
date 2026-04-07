"""Focused resilience coverage for script manager diagnostics helpers."""

from datetime import timedelta
from types import SimpleNamespace

from homeassistant.util import dt as dt_util
import pytest

from custom_components.pawcontrol import script_manager
from custom_components.pawcontrol.const import (
    CONF_DOG_ID,
    DEFAULT_MANUAL_CHECK_EVENT,
    DOMAIN,
)


def _build_entry(**overrides: object) -> SimpleNamespace:
    """Create a tiny config-entry stub for resilience helper tests."""
    entry = {
        "title": "Resilience Entry",
        "entry_id": "entry-resilience",
        "options": {},
        "data": {},
        "runtime_data": {},
    }
    entry.update(overrides)
    return SimpleNamespace(**entry)


def _build_hass() -> SimpleNamespace:
    """Create a tiny Home Assistant stub for helper tests."""
    return SimpleNamespace(
        states=SimpleNamespace(get=lambda _entity_id: None),
        data={DOMAIN: {}},
        bus=SimpleNamespace(async_listen=lambda *_args, **_kwargs: lambda: None),
    )


def test_resolve_manual_resilience_events_handles_async_entries_typeerror() -> None:
    """Resolver should fall back to empty automation lists for TypeError paths."""
    hass = _build_hass()
    hass.config_entries = SimpleNamespace(
        async_entries=lambda _domain: (_ for _ in ()).throw(TypeError("boom"))
    )
    manager = script_manager.PawControlScriptManager(hass, _build_entry())

    telemetry = manager._resolve_manual_resilience_events()

    assert telemetry["available"] is False
    assert telemetry["automations"] == []
    assert telemetry["configured_guard_events"] == []
    assert telemetry["listener_events"] == {}


def test_manual_event_source_mapping_ignores_invalid_listener_source_shapes() -> None:
    """Source mapping should ignore non-sequence listener source payloads."""
    entry = _build_entry(
        options={
            "system_settings": {
                "manual_guard_event": "paw.guard",
                "manual_breaker_event": "paw.break",
            }
        }
    )
    manager = script_manager.PawControlScriptManager(_build_hass(), entry)
    manager._resolve_manual_resilience_events = lambda: {
        "configured_guard_events": ["paw.guard"],
        "configured_breaker_events": ["paw.break"],
        "configured_check_events": [],
        "listener_metadata": {
            "paw.guard": {
                "sources": ["default", "system_settings"],
                "primary_source": "system_settings",
            }
        },
        "listener_sources": {
            "paw.guard": "invalid-string-source",
            "paw.break": ["system_options"],
        },
    }

    mapping = manager._manual_event_source_mapping()

    assert "listener_sources" not in mapping["paw.guard"]
    assert mapping["paw.guard"]["primary_source"] == "system_settings"
    assert mapping["paw.break"]["listener_sources"] == ("system_options",)


def test_serialise_manual_event_record_falls_back_to_received_timestamp() -> None:
    """Serializer should use received timestamps when recorded_at is invalid."""
    manager = script_manager.PawControlScriptManager(_build_hass(), _build_entry())
    fired_at = dt_util.utcnow() - timedelta(seconds=30)
    received_at = dt_util.utcnow() - timedelta(seconds=10)

    snapshot = manager._serialise_manual_event_record(
        {
            "event_type": "paw.guard",
            "configured_role": "invalid-role",
            "time_fired": fired_at,
            "received_at": received_at,
            "sources": "not-a-list",
        },
        recorded_at="not-a-date",
    )

    assert snapshot is not None
    assert snapshot["category"] == "unknown"
    assert snapshot["recorded_at"] == snapshot["received_at"]
    assert snapshot["recorded_age_seconds"] == snapshot["received_age_seconds"]
    assert snapshot["sources"] is None


def test_get_resilience_escalation_snapshot_returns_none_without_definition() -> None:
    """Diagnostics snapshot should return ``None`` when no script was generated."""
    manager = script_manager.PawControlScriptManager(_build_hass(), _build_entry())

    assert manager.get_resilience_escalation_snapshot() is None


def test_resolve_manual_resilience_events_handles_keyerror_and_invalid_forms() -> None:
    """Resolver should swallow key errors and invalid option/event structures."""
    hass = _build_hass()
    hass.config_entries = SimpleNamespace(
        async_entries=lambda _domain: (_ for _ in ()).throw(KeyError("boom"))
    )
    entry = _build_entry(
        options={
            "manual_guard_event": "   ",
            "system_settings": {"manual_breaker_event": 123},
        },
        data={"manual_check_event": ["invalid"]},
    )
    manager = script_manager.PawControlScriptManager(hass, entry)

    telemetry = manager._resolve_manual_resilience_events()

    assert telemetry["available"] is False
    assert telemetry["automations"] == []
    assert telemetry["configured_breaker_events"] == []
    assert telemetry["listener_metadata"][DEFAULT_MANUAL_CHECK_EVENT]["sources"] == [
        "default"
    ]


def test_serialise_manual_event_record_rejects_non_mapping_records() -> None:
    """Serializer should reject unknown record shapes without raising."""
    manager = script_manager.PawControlScriptManager(_build_hass(), _build_entry())

    assert manager._serialise_manual_event_record(None) is None
    assert manager._serialise_manual_event_record("invalid") is None


def test_get_resilience_escalation_snapshot_handles_invalid_listener_reasons() -> None:
    """Snapshot generation should ignore invalid reason/event payload forms."""
    manager = script_manager.PawControlScriptManager(_build_hass(), _build_entry())
    manager._resilience_escalation_definition = {
        "object_id": "pawcontrol_resilience_escalation",
        "alias": "Resilience",
        "description": "Test",
        "field_defaults": {"skip_threshold": 1, "breaker_threshold": 2},
    }
    manager._entry_scripts = ["script.pawcontrol_resilience_escalation"]
    manager._manual_event_counters = {"paw.guard": 2}

    manager._resolve_manual_resilience_events = lambda: {
        "available": True,
        "automations": [],
        "configured_guard_events": ["paw.guard"],
        "configured_breaker_events": [],
        "configured_check_events": [123],
        "system_guard_event": None,
        "system_breaker_event": None,
        "listener_events": {"paw.guard": 999, "paw.other": "guard"},
        "listener_sources": {},
        "listener_metadata": {},
        "event_history": [],
        "last_event": None,
        "last_trigger": None,
        "event_counters": {"total": 0, "by_event": {}, "by_reason": {}},
        "active_listeners": [],
    }
    manager._manual_event_preferences = lambda: {
        "manual_guard_event": "paw.guard",
        "manual_breaker_event": None,
        "manual_check_event": None,
    }
    manager._manual_event_source_mapping = lambda: {"paw.guard": {}}

    snapshot = manager.get_resilience_escalation_snapshot()

    assert snapshot is not None
    counters = snapshot["manual_events"]["event_counters"]
    assert counters["by_event"] == {"paw.guard": 2, "paw.other": 0}
    assert counters["by_reason"] == {}


@pytest.mark.asyncio
async def test_async_generate_scripts_for_dogs_returns_falsey_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Generation should return empty payloads for early-return branches."""
    manager = script_manager.PawControlScriptManager(_build_hass(), _build_entry())

    created_empty = await manager.async_generate_scripts_for_dogs([], set())
    assert created_empty == {}

    monkeypatch.setattr(manager, "_get_component", lambda: None)
    created_no_component = await manager.async_generate_scripts_for_dogs(
        [{CONF_DOG_ID: "dog-1"}],
        set(),
    )

    assert created_no_component == {}
