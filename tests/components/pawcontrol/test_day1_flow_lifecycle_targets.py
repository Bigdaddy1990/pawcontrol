"""Day-1 branch coverage targets for flow and lifecycle behavior."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

from homeassistant.data_entry_flow import FlowResultType
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

import custom_components.pawcontrol as pawcontrol_init
from custom_components.pawcontrol.config_flow_main import PawControlConfigFlow
from custom_components.pawcontrol.const import CONF_DOGS, CONF_NAME, DOMAIN
from custom_components.pawcontrol.options_flow_main import PawControlOptionsFlow
from custom_components.pawcontrol.types import (
    DOG_ID_FIELD,
    DOG_MODULES_FIELD,
    DOG_NAME_FIELD,
)


@pytest.mark.asyncio
async def test_day1_duplicate_user_flow_aborts_with_already_configured(hass) -> None:
    """Config flow should stop duplicate user setup attempts early."""
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, data={})
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
        data={CONF_NAME: "PawControl"},
    )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


@pytest.mark.asyncio
async def test_day1_reconfigure_validation_error_and_success_abort(
    hass,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reconfigure should cover invalid and successful abort branches."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_DOGS: [
                {
                    DOG_ID_FIELD: "buddy",
                    DOG_NAME_FIELD: "Buddy",
                    DOG_MODULES_FIELD: {"gps": True},
                }
            ],
            "entity_profile": "standard",
        },
        options={"entity_profile": "standard"},
    )
    entry.add_to_hass(hass)

    flow = PawControlConfigFlow()
    flow.hass = hass
    flow.context = {"entry_id": entry.entry_id}

    async def _placeholders(*_args, **_kwargs):
        return {"current_profile": "standard"}

    monkeypatch.setattr(flow, "_build_reconfigure_placeholders", _placeholders)
    monkeypatch.setattr(flow, "_resolve_entry_profile", lambda _entry: "standard")
    monkeypatch.setattr(
        flow,
        "_extract_entry_dogs",
        lambda _entry: (
            [
                {
                    DOG_ID_FIELD: "buddy",
                    DOG_NAME_FIELD: "Buddy",
                    DOG_MODULES_FIELD: {"gps": True},
                }
            ],
            [],
        ),
    )

    invalid = await flow.async_step_reconfigure({"entity_profile": "not-real"})
    assert invalid["type"] == FlowResultType.FORM
    assert invalid["errors"] == {"base": "invalid_profile"}

    monkeypatch.setattr(flow, "async_set_unique_id", AsyncMock())
    monkeypatch.setattr(flow, "_abort_if_unique_id_mismatch", lambda **_kwargs: None)
    monkeypatch.setattr(
        flow, "_check_profile_compatibility", lambda *_: {"warnings": []}
    )
    monkeypatch.setattr(
        flow,
        "_check_config_health_enhanced",
        AsyncMock(return_value={"healthy": True, "issues": []}),
    )
    monkeypatch.setattr(
        flow, "_estimate_entities_for_reconfigure", AsyncMock(return_value=7)
    )
    monkeypatch.setattr(
        flow,
        "async_update_reload_and_abort",
        AsyncMock(
            return_value={
                "type": FlowResultType.ABORT,
                "reason": "reconfigure_successful",
            }
        ),
        raising=False,
    )

    success = await flow.async_step_reconfigure({"entity_profile": "basic"})
    assert success["type"] == FlowResultType.ABORT
    assert success["reason"] == "reconfigure_successful"


@pytest.mark.asyncio
async def test_day1_reauth_confirm_abort_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reauth confirmation should abort with the successful reason."""
    flow = PawControlConfigFlow()
    flow.reauth_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=DOMAIN,
        data={CONF_DOGS: [{DOG_ID_FIELD: "buddy", DOG_NAME_FIELD: "Buddy"}]},
        options={"entity_profile": "standard"},
    )

    monkeypatch.setattr(flow, "async_set_unique_id", AsyncMock())
    monkeypatch.setattr(flow, "_abort_if_unique_id_mismatch", lambda **_kwargs: None)
    monkeypatch.setattr(
        flow,
        "_check_config_health_enhanced",
        AsyncMock(
            return_value={
                "healthy": True,
                "issues": [],
                "warnings": [],
                "validated_dogs": 1,
                "total_dogs": 1,
            }
        ),
    )
    monkeypatch.setattr(
        flow,
        "async_update_reload_and_abort",
        AsyncMock(
            return_value={"type": FlowResultType.ABORT, "reason": "reauth_successful"}
        ),
        raising=False,
    )

    result = await flow.async_step_reauth_confirm({"confirm": True})

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"


@pytest.mark.asyncio
async def test_day1_options_flow_success_and_validation_error() -> None:
    """Options flow should cover success and invalid profile validation."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_DOGS: [{DOG_ID_FIELD: "buddy", DOG_NAME_FIELD: "Buddy"}]},
        options={"entity_profile": "standard", "enable_analytics": True},
    )
    flow = PawControlOptionsFlow()
    flow.initialize_from_config_entry(entry)

    invalid = await flow.async_step_entity_profiles({"entity_profile": "not-real"})
    assert invalid["type"] == FlowResultType.FORM
    assert invalid["errors"] == {"base": "invalid_profile"}

    applied = await flow.async_step_profile_preview(
        {"profile": "basic", "apply_profile": True},
    )
    assert applied["type"] == FlowResultType.CREATE_ENTRY
    assert applied["data"]["entity_profile"] == "basic"


@pytest.mark.asyncio
async def test_day1_setup_entry_tolerates_non_critical_scheduler_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Setup should still succeed when daily reset scheduler registration fails."""
    runtime_data = SimpleNamespace(
        coordinator=SimpleNamespace(async_start_background_tasks=lambda: None),
        helper_manager=SimpleNamespace(get_helper_count=lambda: 0),
        door_sensor_manager=SimpleNamespace(get_configured_dogs=lambda: []),
        geofencing_manager=SimpleNamespace(is_enabled=lambda: False),
        daily_reset_unsub=None,
        background_monitor_task=None,
    )
    entry = SimpleNamespace(entry_id="entry-id", options={}, data={})
    hass = SimpleNamespace(async_create_task=lambda coro: coro)

    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "async_validate_entry_config",
        AsyncMock(return_value=([{"id": "dog-1"}], "standard", [])),
    )
    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "_should_skip_optional_setup",
        lambda _hass: False,
    )
    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "async_initialize_managers",
        AsyncMock(return_value=runtime_data),
    )
    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "store_runtime_data",
        lambda *_: None,
    )
    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "async_register_entry_webhook",
        AsyncMock(),
    )
    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "async_register_entry_mqtt",
        AsyncMock(),
    )
    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "async_setup_platforms",
        AsyncMock(),
    )
    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "async_register_cleanup",
        AsyncMock(),
    )
    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "async_setup_daily_reset_scheduler",
        AsyncMock(side_effect=RuntimeError("scheduler failed")),
    )
    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "async_check_for_issues",
        AsyncMock(),
    )
    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "_async_monitor_background_tasks",
        AsyncMock(),
    )

    assert await pawcontrol_init.async_setup_entry(hass, entry) is True
