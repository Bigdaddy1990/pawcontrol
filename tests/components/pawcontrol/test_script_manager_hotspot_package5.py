"""Hotspot package 5: script manager dispatch and argument normalisation tests."""

from types import SimpleNamespace

import pytest

from custom_components.pawcontrol import script_manager
from custom_components.pawcontrol.const import DOMAIN


class _Entry(SimpleNamespace):
    """Minimal config-entry stub used for script-manager tests."""


class _AutomationEntry(SimpleNamespace):
    """Minimal automation config-entry stub."""


def _build_hass() -> SimpleNamespace:
    return SimpleNamespace(
        states=SimpleNamespace(get=lambda _entity_id: None),
        data={DOMAIN: {}},
        bus=SimpleNamespace(async_listen=lambda *_args, **_kwargs: lambda: None),
    )


def _build_entry(**overrides: object) -> _Entry:
    payload = {
        "title": "Script Entry",
        "entry_id": "entry-script",
        "options": {},
        "data": {},
        "runtime_data": {},
    }
    payload.update(overrides)
    return _Entry(**payload)


def test_parse_manual_resilience_options_normalises_threshold_arguments() -> None:
    """Option parsing should coerce integer-like strings and ignore invalid values."""
    options = script_manager._parse_manual_resilience_options({
        "manual_guard_event": "  paw.guard ",
        "manual_breaker_event": "",
        "resilience_skip_threshold": " 7 ",
        "resilience_breaker_threshold": True,
        "manual_event_history_size": "999",
        "system_settings": {
            "manual_check_event": "paw.check",
            "resilience_skip_threshold": "-1",
            "resilience_breaker_threshold": "21",
        },
    })

    assert options["manual_guard_event"] == "paw.guard"
    assert "manual_breaker_event" not in options
    assert options["resilience_skip_threshold"] == 7
    assert options["resilience_breaker_threshold"] == 1
    assert "manual_event_history_size" not in options
    assert options["system_settings"]["resilience_breaker_threshold"] == 21


@pytest.mark.asyncio
async def test_async_sync_manual_resilience_events_updates_blueprint_inputs() -> None:
    """Dispatch should update blueprint-backed automations when inputs changed."""
    hass = _build_hass()
    updated: list[dict[str, object]] = []
    automation = _AutomationEntry(
        entry_id="automation-1",
        data={
            "use_blueprint": {
                "path": "pawcontrol/resilience_escalation_followup.yaml",
                "input": {
                    "manual_guard_event": "legacy.guard",
                    "manual_breaker_event": "legacy.breaker",
                },
            }
        },
    )

    hass.config_entries = SimpleNamespace(
        async_entries=lambda domain: [automation] if domain == "automation" else [],
        async_update_entry=lambda _entry, data: updated.append(data),
    )
    manager = script_manager.PawControlScriptManager(hass, _build_entry())

    await manager.async_sync_manual_resilience_events({
        "manual_guard_event": "paw.guard",
        "manual_breaker_event": None,
    })

    assert len(updated) == 1
    blueprint = updated[0]["use_blueprint"]
    assert blueprint["input"]["manual_guard_event"] == "paw.guard"
    assert blueprint["input"]["manual_breaker_event"] == ""


@pytest.mark.asyncio
async def test_async_sync_manual_resilience_events_handles_update_errors() -> None:
    """Update errors should be swallowed so refresh logic still executes."""
    hass = _build_hass()
    automation = _AutomationEntry(
        entry_id="automation-err",
        data={
            "use_blueprint": {
                "path": "pawcontrol/resilience_escalation_followup.yaml",
                "inputs": {"manual_guard_event": "legacy.guard"},
            }
        },
    )
    hass.config_entries = SimpleNamespace(
        async_entries=lambda _domain: [automation],
        async_update_entry=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("boom")
        ),
    )
    manager = script_manager.PawControlScriptManager(hass, _build_entry())

    await manager.async_sync_manual_resilience_events({
        "manual_guard_event": "paw.guard"
    })


@pytest.mark.asyncio
async def test_async_generate_scripts_for_dogs_skips_invalid_dog_identifiers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Generation should ignore malformed dog records without crashing dispatch."""
    hass = _build_hass()
    component = SimpleNamespace(
        get_entity=lambda _entity_id: None, async_add_entities=lambda _entities: None
    )
    monkeypatch.setattr(
        script_manager.er,
        "async_get",
        lambda _hass: SimpleNamespace(async_get=lambda _eid: None),
    )

    manager = script_manager.PawControlScriptManager(hass, _build_entry())
    monkeypatch.setattr(manager, "_get_component", lambda: component)
    monkeypatch.setattr(manager, "_build_scripts_for_dog", lambda *_args: [])
    monkeypatch.setattr(manager, "_build_entry_scripts", lambda: [])

    created = await manager.async_generate_scripts_for_dogs(
        [{"dog_id": ""}, {"dog_name": "No ID"}, {"dog_id": 123}],
        set(),
    )

    assert created == {}
