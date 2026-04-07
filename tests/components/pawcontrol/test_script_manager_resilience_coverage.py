"""Focused resilience coverage for script manager diagnostics helpers."""

from datetime import timedelta
from types import SimpleNamespace

from homeassistant.util import dt as dt_util

from custom_components.pawcontrol import script_manager
from custom_components.pawcontrol.const import DOMAIN


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
        bus=SimpleNamespace(async_listen=lambda *_args, **_kwargs: (lambda: None)),
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
