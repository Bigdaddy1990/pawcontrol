from __future__ import annotations

import asyncio

import pytest
from custom_components.pawcontrol.person_entity_manager import PersonEntityManager
from custom_components.pawcontrol.types import (
    CacheDiagnosticsSnapshot,
    PersonEntityConfigInput,
    PersonEntityDiscoveryResult,
    PersonEntityValidationResult,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er


@pytest.mark.integration
@pytest.mark.asyncio
async def test_person_entity_manager_discovers_and_validates_targets(
    hass: HomeAssistant,
) -> None:
    """Person manager should discover registry entries and expose typed payloads."""

    entity_registry = er.async_get(hass)
    entity_registry.async_get_or_create(
        "person",
        "pawcontrol",
        "jane-unique-id",
        suggested_object_id="jane_doe",
    )
    entity_registry.async_get_or_create(
        "person",
        "pawcontrol",
        "john-unique-id",
        suggested_object_id="john_doe",
    )

    hass.states.async_set(
        "person.jane_doe",
        "home",
        {"friendly_name": "Jane Doe"},
    )
    hass.states.async_set(
        "person.john_doe",
        "not_home",
        {"friendly_name": "John Doe"},
    )
    await hass.async_block_till_done()

    manager = PersonEntityManager(hass, "person-flow-entry")
    config: PersonEntityConfigInput = {
        "enabled": True,
        "auto_discovery": False,
        "discovery_interval": 60,
        "cache_ttl": 30,
        "include_away_persons": False,
        "fallback_to_static": False,
        "notification_mapping": {
            "person.jane_doe": "notify.mobile_app_jane",
            "person.john_doe": "notify.mobile_app_john",
        },
        "priority_persons": ["person.jane_doe"],
    }

    await manager.async_initialize(config)

    persons = manager.get_all_persons()
    assert {person.entity_id for person in persons} == {
        "person.jane_doe",
        "person.john_doe",
    }
    assert [person.entity_id for person in manager.get_home_persons()] == [
        "person.jane_doe"
    ]

    home_targets = manager.get_notification_targets()
    assert home_targets == ["notify.mobile_app_jane"]

    all_targets = manager.get_notification_targets(include_away=True)
    assert sorted(all_targets) == [
        "notify.mobile_app_jane",
        "notify.mobile_app_john",
    ]

    discovery: PersonEntityDiscoveryResult = await manager.async_force_discovery()
    assert discovery["current_count"] == 2
    assert discovery["home_persons"] == 1
    assert discovery["away_persons"] == 1
    assert isinstance(discovery["discovery_time"], str)

    validation: PersonEntityValidationResult = await manager.async_validate_configuration()
    assert validation["valid"] is True
    assert validation["persons_configured"] == 2
    assert validation["notification_targets_available"] >= 1

    snapshot = manager.coordinator_snapshot()
    assert isinstance(snapshot, CacheDiagnosticsSnapshot)
    diagnostics = snapshot.diagnostics
    assert diagnostics is not None
    assert diagnostics["summary"]["persons_home"] == 1

    await manager.async_shutdown()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_person_entity_manager_update_config_rebuilds_state(
    hass: HomeAssistant,
) -> None:
    """Config updates should not deadlock and must refresh listeners/cache."""

    entity_registry = er.async_get(hass)
    entity_registry.async_get_or_create(
        "person",
        "pawcontrol",
        "jane-unique-id",
        suggested_object_id="jane_doe",
    )
    entity_registry.async_get_or_create(
        "person",
        "pawcontrol",
        "john-unique-id",
        suggested_object_id="john_doe",
    )

    hass.states.async_set(
        "person.jane_doe",
        "home",
        {"friendly_name": "Jane Doe"},
    )
    hass.states.async_set(
        "person.john_doe",
        "not_home",
        {"friendly_name": "John Doe"},
    )
    await hass.async_block_till_done()

    manager = PersonEntityManager(hass, "person-flow-entry")
    initial_config: PersonEntityConfigInput = {
        "enabled": True,
        "auto_discovery": False,
        "discovery_interval": 60,
        "cache_ttl": 30,
        "include_away_persons": False,
        "fallback_to_static": False,
        "notification_mapping": {
            "person.jane_doe": "notify.mobile_app_jane",
            "person.john_doe": "notify.mobile_app_john",
        },
    }

    await manager.async_initialize(initial_config)

    assert manager.get_notification_targets() == ["notify.mobile_app_jane"]

    hass.states.async_set(
        "person.jane_doe",
        "not_home",
        {"friendly_name": "Jane Doe"},
    )
    await hass.async_block_till_done()

    updated_config: PersonEntityConfigInput = {
        "enabled": True,
        "auto_discovery": False,
        "discovery_interval": 90,
        "cache_ttl": 15,
        "include_away_persons": False,
        "fallback_to_static": True,
        "static_notification_targets": ["notify.family_group"],
        "notification_mapping": {
            "person.jane_doe": "notify.mobile_app_jane",
            "person.john_doe": "notify.mobile_app_john",
        },
    }

    await asyncio.wait_for(manager.async_update_config(updated_config), timeout=1)

    assert len(manager.get_all_persons()) == 2
    assert manager.get_notification_targets() == ["notify.family_group"]
    assert sorted(manager.get_notification_targets(include_away=True)) == [
        "notify.mobile_app_jane",
        "notify.mobile_app_john",
    ]

    async with manager._lock:  # type: ignore[attr-defined]
        listener_count = len(manager._state_listeners)

    assert listener_count == 1

    await manager.async_shutdown()
