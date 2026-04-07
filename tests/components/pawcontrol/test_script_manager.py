"""Coverage tests for script manager helpers and option migration paths."""

from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import AsyncMock

from homeassistant.components.script import DOMAIN as SCRIPT_DOMAIN
import pytest

from custom_components.pawcontrol import script_manager
from custom_components.pawcontrol.const import (
    CONF_DOG_ID,
    CONF_DOG_NAME,
    DEFAULT_RESILIENCE_BREAKER_THRESHOLD,
    DEFAULT_RESILIENCE_SKIP_THRESHOLD,
    DOMAIN,
    MODULE_NOTIFICATIONS,
    RESILIENCE_BREAKER_THRESHOLD_MAX,
)


@dataclass(slots=True)
class _FieldDefault:
    """Minimal script field object exposing ``default`` for extraction."""

    default: object


def _build_entry(**overrides: object) -> SimpleNamespace:
    """Return a light-weight config-entry stub for helper tests."""
    entry = {
        "title": "My Fancy Entry",
        "entry_id": "entry-123",
        "options": {},
        "data": {},
        "runtime_data": {},
    }
    entry.update(overrides)
    return SimpleNamespace(**entry)


def _build_hass(state: object | None = None) -> SimpleNamespace:
    """Return a light-weight Home Assistant stub."""
    states = SimpleNamespace(get=lambda entity_id: state)
    return SimpleNamespace(
        states=states,
        data={DOMAIN: {}},
        bus=SimpleNamespace(async_listen=lambda *_args, **_kwargs: (lambda: None)),
    )


def test_helper_slug_and_event_normalisation_paths() -> None:
    """Helpers should normalise slugs and strip event values predictably."""
    titled = _build_entry(title="Front Door Dog", entry_id="entry-1")
    blank_title = _build_entry(title="   ", entry_id="entry-2")
    no_identity = _build_entry(title="", entry_id="")

    assert script_manager._normalise_entry_slug(titled) == "front-door-dog"
    assert script_manager._normalise_entry_slug(blank_title) == DOMAIN
    assert script_manager._normalise_entry_slug(no_identity) == DOMAIN

    assert script_manager._normalise_manual_event("  paw_event  ") == "paw_event"
    assert script_manager._normalise_manual_event("   ") is None
    assert script_manager._normalise_manual_event(42) is None


def test_parse_manual_resilience_options_and_selection() -> None:
    """Parser helpers should keep valid values and drop invalid payloads."""
    payload = {
        "manual_guard_event": " guard_event ",
        "manual_breaker_event": "breaker_event",
        "resilience_skip_threshold": "6",
        "resilience_breaker_threshold": 9.0,
        "manual_event_history_size": "4",
        "system_settings": {
            "manual_check_event": " check_event ",
            "resilience_skip_threshold": "8",
            "resilience_breaker_threshold": 12,
        },
    }

    options = script_manager._parse_manual_resilience_options(payload)
    assert options == {
        "manual_guard_event": "guard_event",
        "manual_breaker_event": "breaker_event",
        "resilience_skip_threshold": 6,
        "resilience_breaker_threshold": 9,
        "manual_event_history_size": 4,
        "system_settings": {
            "manual_check_event": "check_event",
            "resilience_skip_threshold": 8,
            "resilience_breaker_threshold": 12,
        },
    }

    selection = script_manager._parse_event_selection({
        "manual_guard_event": "",
        "manual_breaker_event": " breaker ",
    })
    assert selection == {
        "manual_guard_event": None,
        "manual_breaker_event": "breaker",
    }


def test_resolve_resilience_script_thresholds_reads_field_defaults() -> None:
    """Script threshold resolution should support mapping and object field types."""
    state = SimpleNamespace(
        attributes={
            "fields": {
                "skip_threshold": {"default": "7"},
                "breaker_threshold": _FieldDefault("11"),
            }
        }
    )
    hass = _build_hass(state)
    entry = _build_entry(title="My Entry", entry_id="entry-script")

    skip, breaker = script_manager.resolve_resilience_script_thresholds(hass, entry)

    assert skip == 7
    assert breaker == 11


def test_ensure_resilience_threshold_options_migrates_legacy_script_defaults() -> None:
    """Migration helper should inject script defaults into system settings."""
    hass = _build_hass(
        SimpleNamespace(
            attributes={
                "fields": {
                    "skip_threshold": {"default": "8"},
                    "breaker_threshold": {"default": "16"},
                }
            }
        )
    )
    entry = _build_entry(
        options={"system_settings": {"manual_guard_event": "guard.custom"}},
    )

    manager = script_manager.PawControlScriptManager(hass, entry)
    migrated = manager.ensure_resilience_threshold_options()

    assert migrated is not None
    assert migrated["system_settings"] == {
        "manual_guard_event": "guard.custom",
        "resilience_skip_threshold": 8,
        "resilience_breaker_threshold": RESILIENCE_BREAKER_THRESHOLD_MAX,
    }
    assert migrated["resilience_skip_threshold"] == 8
    assert migrated["resilience_breaker_threshold"] == RESILIENCE_BREAKER_THRESHOLD_MAX


def test_ensure_resilience_threshold_options_skips_when_already_configured() -> None:
    """Migration should no-op when options already include both thresholds."""
    hass = _build_hass(
        SimpleNamespace(
            attributes={
                "fields": {
                    "skip_threshold": {"default": "99"},
                    "breaker_threshold": {"default": "99"},
                }
            }
        )
    )
    entry = _build_entry(
        options={
            "system_settings": {
                "resilience_skip_threshold": DEFAULT_RESILIENCE_SKIP_THRESHOLD,
                "resilience_breaker_threshold": DEFAULT_RESILIENCE_BREAKER_THRESHOLD,
            }
        }
    )

    manager = script_manager.PawControlScriptManager(hass, entry)

    assert manager.ensure_resilience_threshold_options() is None


def test_resolve_manual_resilience_events_returns_robust_defaults_without_manager() -> (
    None
):
    """Missing config-entry manager should emit stable telemetry defaults."""
    entry = _build_entry()
    hass = _build_hass()
    manager = script_manager.PawControlScriptManager(hass, entry)

    telemetry = manager._resolve_manual_resilience_events()

    assert telemetry["available"] is False
    assert telemetry["automations"] == []
    assert telemetry["listener_events"] == {}
    assert telemetry["listener_sources"] == {}
    assert telemetry["listener_metadata"] == {}
    assert telemetry["event_counters"] == {"total": 0, "by_event": {}, "by_reason": {}}
    assert telemetry["active_listeners"] == []


def test_manual_event_source_mapping_includes_roles_and_sources() -> None:
    """Source mapping should retain configured roles and canonical source metadata."""
    entry = _build_entry(
        options={
            "system_settings": {
                "manual_guard_event": "paw.guard",
                "manual_check_event": "paw.check",
                "manual_breaker_event": "paw.breaker",
            }
        }
    )
    manager = script_manager.PawControlScriptManager(_build_hass(), entry)
    manager._resolve_manual_resilience_events = lambda: {
        "configured_guard_events": ["paw.guard"],
        "configured_breaker_events": ["paw.breaker"],
        "configured_check_events": ["paw.check"],
        "listener_sources": {"paw.guard": ["system_options", "blueprint"]},
        "listener_metadata": {
            "paw.guard": {
                "sources": ["system_settings", "default"],
                "primary_source": "system_settings",
            }
        },
    }

    mapping = manager._manual_event_source_mapping()

    assert mapping["paw.guard"]["configured_role"] == "guard"
    assert mapping["paw.guard"]["preference_key"] == "manual_guard_event"
    assert mapping["paw.guard"]["primary_source"] == "system_settings"
    assert mapping["paw.guard"]["source_tags"] == ["system_settings", "default"]
    assert mapping["paw.guard"]["listener_sources"] == ("system_options", "blueprint")
    assert mapping["paw.breaker"]["configured_role"] == "breaker"
    assert mapping["paw.check"]["configured_role"] == "check"


@pytest.mark.asyncio
async def test_async_generate_scripts_for_dogs_tracks_outputs_and_removes_obsolete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Script generation should return per-dog/entry outputs and clean stale scripts."""

    class _FakeScriptEntity:
        def __init__(self, _hass, object_id, *_args):
            self.object_id = object_id
            self.entity_id = f"{SCRIPT_DOMAIN}.{object_id}"
            self.removed = False

        async def async_remove(self) -> None:
            self.removed = True

    class _FakeComponent:
        def __init__(self) -> None:
            self._entities: dict[str, _FakeScriptEntity] = {}

        def get_entity(self, entity_id: str):
            return self._entities.get(entity_id)

        async def async_add_entities(self, entities: list[_FakeScriptEntity]) -> None:
            for entity in entities:
                self._entities[entity.entity_id] = entity

    class _FakeRegistry:
        def __init__(self) -> None:
            self._entries = {
                "script.paw_dog_1_setup": SimpleNamespace(config_entry_id="another"),
                "script.paw_entry_resilience": SimpleNamespace(config_entry_id="old"),
            }
            self.updated: list[tuple[str, str]] = []

        def async_get(self, entity_id: str):
            return self._entries.get(entity_id)

        def async_update_entity(self, entity_id: str, *, config_entry_id: str) -> None:
            self.updated.append((entity_id, config_entry_id))
            self._entries[entity_id] = SimpleNamespace(config_entry_id=config_entry_id)

        async def async_remove(self, entity_id: str) -> None:
            self._entries.pop(entity_id, None)

    component = _FakeComponent()
    registry = _FakeRegistry()
    entry = _build_entry()
    hass = _build_hass()
    hass.data[SCRIPT_DOMAIN] = component
    hass.config_entries = SimpleNamespace(async_entries=lambda _domain: [])
    manager = script_manager.PawControlScriptManager(hass, entry)
    manager._dog_scripts = {"old-dog": ["script.paw_old_cleanup"]}
    manager._entry_scripts = ["script.paw_old_entry"]

    monkeypatch.setattr(script_manager, "SCRIPT_ENTITY_SCHEMA", lambda payload: payload)
    monkeypatch.setattr(script_manager, "ScriptEntity", _FakeScriptEntity)
    monkeypatch.setattr(script_manager.er, "async_get", lambda _hass: registry)
    monkeypatch.setattr(
        manager,
        "_build_scripts_for_dog",
        lambda *_args, **_kwargs: [("paw_dog_1_setup", {"sequence": []})],
    )
    monkeypatch.setattr(
        manager,
        "_build_entry_scripts",
        lambda: [("paw_entry_resilience", {"sequence": []})],
    )
    remove_entity = AsyncMock()
    monkeypatch.setattr(manager, "_async_remove_script_entity", remove_entity)

    created = await manager.async_generate_scripts_for_dogs(
        [{CONF_DOG_ID: "dog-1", CONF_DOG_NAME: "Bolt"}],
        {MODULE_NOTIFICATIONS},
    )

    assert created == {
        "dog-1": ["script.paw_dog_1_setup"],
        "__entry__": ["script.paw_entry_resilience"],
    }
    remove_entity.assert_any_await("script.paw_old_cleanup")
    remove_entity.assert_any_await("script.paw_old_entry")
    assert ("script.paw_dog_1_setup", entry.entry_id) in registry.updated
    assert ("script.paw_entry_resilience", entry.entry_id) in registry.updated


@pytest.mark.asyncio
async def test_async_generate_scripts_for_dogs_skips_invalid_ids_and_uses_name_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Generation should ignore invalid dogs and fall back to the dog id as name."""

    class _FakeScriptEntity:
        def __init__(self, _hass, object_id, *_args):
            self.entity_id = f"{SCRIPT_DOMAIN}.{object_id}"

        async def async_remove(self) -> None:
            return None

    class _FakeComponent:
        def __init__(self) -> None:
            self._entities: dict[str, _FakeScriptEntity] = {}

        def get_entity(self, entity_id: str):
            return self._entities.get(entity_id)

        async def async_add_entities(self, entities: list[_FakeScriptEntity]) -> None:
            for entity in entities:
                self._entities[entity.entity_id] = entity

    class _FakeRegistry:
        def async_get(self, _entity_id: str):
            return None

        def async_update_entity(self, _entity_id: str, *, config_entry_id: str) -> None:
            return None

        async def async_remove(self, _entity_id: str) -> None:
            return None

    captured: list[tuple[str, str, str, bool]] = []
    component = _FakeComponent()
    hass = _build_hass()
    hass.data[SCRIPT_DOMAIN] = component
    hass.config_entries = SimpleNamespace(async_entries=lambda _domain: [])
    manager = script_manager.PawControlScriptManager(hass, _build_entry())

    monkeypatch.setattr(script_manager, "SCRIPT_ENTITY_SCHEMA", lambda payload: payload)
    monkeypatch.setattr(script_manager, "ScriptEntity", _FakeScriptEntity)
    monkeypatch.setattr(script_manager.er, "async_get", lambda _hass: _FakeRegistry())
    monkeypatch.setattr(
        manager,
        "_build_scripts_for_dog",
        lambda slug, dog_id, dog_name, notifications_enabled: (
            captured.append((slug, dog_id, dog_name, notifications_enabled))
            or [("paw_generated", {"sequence": []})]
        ),
    )
    monkeypatch.setattr(manager, "_build_entry_scripts", lambda: [])

    created = await manager.async_generate_scripts_for_dogs(
        [
            {CONF_DOG_ID: "", CONF_DOG_NAME: "invalid-empty-id"},
            {CONF_DOG_ID: "dog-2", CONF_DOG_NAME: "   "},
        ],
        set(),
    )

    assert created == {"dog-2": ["script.paw_generated"]}
    assert captured == [("dog-2", "dog-2", "dog-2", False)]
