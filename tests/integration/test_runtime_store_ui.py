"""Integration regressions for runtime cache recovery in UI flows."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call

import pytest
from custom_components.pawcontrol.const import (
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOGS,
    CONF_DOOR_SENSOR,
    CONF_MODULES,
    DOMAIN,
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_NOTIFICATIONS,
    MODULE_WALK,
)
from custom_components.pawcontrol.options_flow import PawControlOptionsFlow
from custom_components.pawcontrol.repairs import (
    ISSUE_RUNTIME_STORE_COMPATIBILITY,
    async_check_for_issues,
)
from custom_components.pawcontrol.runtime_data import store_runtime_data
from custom_components.pawcontrol.types import (
    CacheRepairAggregate,
    DogConfigData,
    DomainRuntimeStoreEntry,
    PawControlRuntimeData,
    ensure_dog_config_data,
)
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry
from tests.helpers import typed_deepcopy


def _build_runtime_data(
    dog: DogConfigData,
    *,
    data_manager: object,
    coordinator: object | None = None,
) -> PawControlRuntimeData:
    """Return runtime data with a cloned dog payload for integration tests."""

    return PawControlRuntimeData(
        coordinator=coordinator or MagicMock(),
        data_manager=data_manager,
        notification_manager=MagicMock(),
        feeding_manager=MagicMock(),
        walk_manager=MagicMock(),
        entity_factory=MagicMock(),
        entity_profile="standard",
        dogs=[typed_deepcopy(dog)],
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_options_flow_recovers_runtime_cache_after_manual_deletion(
    hass: HomeAssistant,
) -> None:
    """Options flow should rebuild the runtime store when hass.data was cleared."""

    dog_payload = {
        CONF_DOG_ID: "buddy",
        CONF_DOG_NAME: "Buddy",
        CONF_MODULES: {
            MODULE_FEEDING: True,
            MODULE_WALK: True,
            MODULE_GPS: False,
            MODULE_NOTIFICATIONS: True,
        },
    }
    typed_dog = ensure_dog_config_data(dog_payload)
    assert typed_dog is not None

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_DOGS: [typed_deepcopy(typed_dog)]},
        unique_id="runtime-options",
        options={"notifications": {"mobile_notifications": False}},
    )
    entry.add_to_hass(hass)

    data_manager = SimpleNamespace(
        async_update_dog_data=AsyncMock(return_value=None),
        cache_repair_summary=lambda: None,
    )
    runtime = _build_runtime_data(typed_dog, data_manager=data_manager)
    store_runtime_data(hass, entry, runtime)

    hass.data.pop(DOMAIN, None)
    assert DOMAIN not in hass.data

    hass.states.async_set(
        "binary_sensor.back_door",
        "off",
        {"device_class": "door"},
    )

    flow = PawControlOptionsFlow()
    flow.hass = hass
    flow.initialize_from_config_entry(entry)

    select_result = await flow.async_step_select_dog_for_door_sensor(
        {"dog_id": "buddy"}
    )
    assert select_result["type"] == FlowResultType.FORM
    assert select_result["step_id"] == "configure_door_sensor"

    result = await flow.async_step_configure_door_sensor(
        {CONF_DOOR_SENSOR: "binary_sensor.back_door"}
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "manage_dogs"

    data_manager.async_update_dog_data.assert_awaited_once_with(
        "buddy", {CONF_DOOR_SENSOR: "binary_sensor.back_door"}
    )

    await hass.async_block_till_done()

    store = hass.data[DOMAIN]
    assert entry.entry_id in store
    entry_cache = store[entry.entry_id]
    assert isinstance(entry_cache, DomainRuntimeStoreEntry)
    assert entry_cache.unwrap() is runtime
    assert entry_cache.version == DomainRuntimeStoreEntry.CURRENT_VERSION
    assert entry.runtime_data is runtime
    assert runtime.schema_version == DomainRuntimeStoreEntry.CURRENT_VERSION
    assert runtime.schema_created_version == DomainRuntimeStoreEntry.CURRENT_VERSION
    assert runtime.schema_version == DomainRuntimeStoreEntry.CURRENT_VERSION
    assert runtime.schema_created_version == DomainRuntimeStoreEntry.CURRENT_VERSION

    dog_snapshot = entry.data[CONF_DOGS][0]
    assert dog_snapshot[CONF_DOOR_SENSOR] == "binary_sensor.back_door"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_repair_checks_restore_runtime_cache_after_manual_deletion(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Repair evaluations should recreate the runtime cache after deletion."""

    create_issue = AsyncMock(return_value=None)
    delete_issue = AsyncMock(return_value=None)
    monkeypatch.setattr(ir, "async_create_issue", create_issue)
    monkeypatch.setattr(ir, "async_delete_issue", delete_issue)

    dog_payload = {
        CONF_DOG_ID: "buddy",
        CONF_DOG_NAME: "Buddy",
        CONF_MODULES: {
            MODULE_FEEDING: True,
            MODULE_WALK: True,
            MODULE_GPS: False,
            MODULE_NOTIFICATIONS: False,
        },
    }
    typed_dog = ensure_dog_config_data(dog_payload)
    assert typed_dog is not None

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_DOGS: [typed_deepcopy(typed_dog)]},
        unique_id="runtime-repairs",
        options={"notifications": {"mobile_notifications": False}},
    )
    entry.add_to_hass(hass)

    summary = CacheRepairAggregate(
        total_caches=1,
        anomaly_count=1,
        severity="warning",
        generated_at="2024-01-01T00:00:00+00:00",
    )

    data_manager = SimpleNamespace(
        async_update_dog_data=AsyncMock(return_value=None),
        cache_repair_summary=lambda: summary,
    )
    coordinator = SimpleNamespace(last_update_success=True)
    runtime = _build_runtime_data(
        typed_dog, data_manager=data_manager, coordinator=coordinator
    )
    store_runtime_data(hass, entry, runtime)

    hass.data.pop(DOMAIN, None)
    assert DOMAIN not in hass.data

    await async_check_for_issues(hass, entry)

    await hass.async_block_till_done()

    assert create_issue.await_count >= 1
    cache_issue_calls = [
        invocation
        for invocation in create_issue.await_args_list
        if invocation.kwargs.get("translation_key") == "cache_health_summary"
    ]
    assert cache_issue_calls

    store = hass.data[DOMAIN]
    assert entry.entry_id in store
    entry_cache = store[entry.entry_id]
    assert isinstance(entry_cache, DomainRuntimeStoreEntry)
    assert entry_cache.unwrap() is runtime
    assert entry_cache.version == DomainRuntimeStoreEntry.CURRENT_VERSION
    assert entry.runtime_data is runtime


@pytest.mark.integration
@pytest.mark.asyncio
async def test_repair_checks_upgrade_legacy_store_entry(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Legacy mapping store entries should upgrade to current versions."""

    create_issue = AsyncMock(return_value=None)
    delete_issue = AsyncMock(return_value=None)
    monkeypatch.setattr(ir, "async_create_issue", create_issue)
    monkeypatch.setattr(ir, "async_delete_issue", delete_issue)

    dog_payload = {
        CONF_DOG_ID: "buddy",
        CONF_DOG_NAME: "Buddy",
        CONF_MODULES: {
            MODULE_FEEDING: True,
            MODULE_WALK: True,
            MODULE_GPS: False,
            MODULE_NOTIFICATIONS: True,
        },
    }
    typed_dog = ensure_dog_config_data(dog_payload)
    assert typed_dog is not None

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_DOGS: [typed_deepcopy(typed_dog)]},
        unique_id="runtime-legacy",
        options={"notifications": {"mobile_notifications": False}},
    )
    entry.add_to_hass(hass)

    summary = CacheRepairAggregate(
        total_caches=1,
        anomaly_count=1,
        severity="warning",
        generated_at="2024-01-01T00:00:00+00:00",
    )

    data_manager = SimpleNamespace(
        async_update_dog_data=AsyncMock(return_value=None),
        cache_repair_summary=lambda: summary,
    )
    coordinator = SimpleNamespace(last_update_success=True)
    runtime = _build_runtime_data(
        typed_dog, data_manager=data_manager, coordinator=coordinator
    )

    hass.data[DOMAIN] = {
        entry.entry_id: {
            "runtime_data": runtime,
            "version": DomainRuntimeStoreEntry.CURRENT_VERSION - 2,
        }
    }
    entry.runtime_data = None

    await async_check_for_issues(hass, entry)
    await hass.async_block_till_done()

    assert create_issue.await_count >= 1

    store = hass.data[DOMAIN]
    entry_cache = store[entry.entry_id]
    assert isinstance(entry_cache, DomainRuntimeStoreEntry)
    assert entry_cache.version == DomainRuntimeStoreEntry.CURRENT_VERSION
    assert entry_cache.unwrap() is runtime
    assert entry.runtime_data is runtime
    assert runtime.schema_version == DomainRuntimeStoreEntry.CURRENT_VERSION
    assert runtime.schema_created_version == DomainRuntimeStoreEntry.CURRENT_VERSION


@pytest.mark.integration
@pytest.mark.asyncio
async def test_repair_checks_surface_runtime_store_incompatibility(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Runtime store incompatibilities should raise repair issues."""

    create_issue = AsyncMock(return_value=None)
    delete_issue = AsyncMock(return_value=None)
    monkeypatch.setattr(ir, "async_create_issue", create_issue)
    monkeypatch.setattr(ir, "async_delete_issue", delete_issue)

    dog_payload = {
        CONF_DOG_ID: "buddy",
        CONF_DOG_NAME: "Buddy",
        CONF_MODULES: {MODULE_WALK: True},
    }
    typed_dog = ensure_dog_config_data(dog_payload)
    assert typed_dog is not None

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_DOGS: [typed_deepcopy(typed_dog)]},
        unique_id="runtime-store-incompatible",
        options={"notifications": {"mobile_notifications": False}},
    )
    entry.add_to_hass(hass)
    entry.version = 1

    data_manager = SimpleNamespace(
        async_update_dog_data=AsyncMock(return_value=None),
        cache_repair_summary=lambda: None,
    )
    coordinator = SimpleNamespace(last_update_success=True)
    runtime = _build_runtime_data(
        typed_dog, data_manager=data_manager, coordinator=coordinator
    )
    store_runtime_data(hass, entry, runtime)

    store = hass.data[DOMAIN]
    store_entry = store[entry.entry_id]
    assert isinstance(store_entry, DomainRuntimeStoreEntry)
    future_version = DomainRuntimeStoreEntry.CURRENT_VERSION + 2
    store_entry.version = future_version
    store_entry.created_version = future_version
    entry._pawcontrol_runtime_store_version = future_version
    entry._pawcontrol_runtime_store_created_version = future_version

    await async_check_for_issues(hass, entry)
    await hass.async_block_till_done()

    compatibility_calls = [
        invocation
        for invocation in create_issue.await_args_list
        if invocation.kwargs.get("translation_key") == ISSUE_RUNTIME_STORE_COMPATIBILITY
    ]
    assert compatibility_calls
    compatibility_kwargs = compatibility_calls[-1].kwargs
    assert compatibility_kwargs["data"]["status"] == "future_incompatible"
    assert compatibility_kwargs["severity"] == ir.IssueSeverity.ERROR


@pytest.mark.integration
@pytest.mark.asyncio
async def test_repair_checks_clear_runtime_store_issue_when_healthy(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Healthy runtime stores should clear previously raised issues."""

    create_issue = AsyncMock(return_value=None)
    delete_issue = AsyncMock(return_value=None)
    monkeypatch.setattr(ir, "async_create_issue", create_issue)
    monkeypatch.setattr(ir, "async_delete_issue", delete_issue)

    dog_payload = {
        CONF_DOG_ID: "buddy",
        CONF_DOG_NAME: "Buddy",
        CONF_MODULES: {MODULE_WALK: True},
    }
    typed_dog = ensure_dog_config_data(dog_payload)
    assert typed_dog is not None

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_DOGS: [typed_deepcopy(typed_dog)]},
        unique_id="runtime-store-healthy",
        options={"notifications": {"mobile_notifications": False}},
    )
    entry.add_to_hass(hass)
    entry.version = 1

    data_manager = SimpleNamespace(
        async_update_dog_data=AsyncMock(return_value=None),
        cache_repair_summary=lambda: None,
    )
    coordinator = SimpleNamespace(last_update_success=True)
    runtime = _build_runtime_data(
        typed_dog, data_manager=data_manager, coordinator=coordinator
    )
    store_runtime_data(hass, entry, runtime)

    await async_check_for_issues(hass, entry)
    await hass.async_block_till_done()

    runtime_issue_id = f"{entry.entry_id}_runtime_store"
    deletion_calls = [
        invocation
        for invocation in delete_issue.await_args_list
        if invocation.args[2] == runtime_issue_id
    ]
    assert deletion_calls
    assert not [
        invocation
        for invocation in create_issue.await_args_list
        if invocation.kwargs.get("translation_key") == ISSUE_RUNTIME_STORE_COMPATIBILITY
    ]
