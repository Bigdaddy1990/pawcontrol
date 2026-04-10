from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pawcontrol.config_flow import PawControlConfigFlow
from custom_components.pawcontrol.const import (
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOGS,
    CONF_MODULES,
    CONF_NAME,
    DOMAIN,
)
from custom_components.pawcontrol.exceptions import FlowValidationError
from custom_components.pawcontrol.options_flow import PawControlOptionsFlow


async def _finish_user_flow_with_single_dog(
    flow: PawControlConfigFlow,
) -> dict[str, object]:
    """Run the minimum happy-path config flow and return the terminal result."""
    step: dict[str, object] = await flow.async_step_user({CONF_NAME: "Paw Control"})
    assert step["type"] == FlowResultType.FORM
    assert step["step_id"] == "add_dog"

    step = await flow.async_step_add_dog({
        CONF_DOG_NAME: "Buddy",
        CONF_DOG_ID: "buddy_1",
    })
    assert step["type"] == FlowResultType.FORM
    assert step["step_id"] == "dog_modules"

    step = await flow.async_step_dog_modules({"enable_feeding": True})
    assert step["type"] == FlowResultType.FORM

    step = await flow.async_step_add_another_dog({"add_another": False})
    while step["type"] == FlowResultType.FORM:
        step_id = step["step_id"]
        if step_id == "configure_modules":
            step = await flow.async_step_configure_modules({})
        elif step_id == "configure_dashboard":
            step = await flow.async_step_configure_dashboard({})
        elif step_id == "entity_profile":
            step = await flow.async_step_entity_profile({"entity_profile": "standard"})
        elif step_id == "final_setup":
            step = await flow.async_step_final_setup({})
        else:
            raise AssertionError(f"Unexpected step: {step_id}")
    return step


async def test_user_step_shows_form(hass: HomeAssistant) -> None:
    flow = PawControlConfigFlow()
    flow.hass = hass
    result = await flow.async_step_user()

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"


async def test_user_flow_success_creates_entry(hass: HomeAssistant) -> None:
    flow = PawControlConfigFlow()
    flow.hass = hass

    result = await _finish_user_flow_with_single_dog(flow)
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Paw Control"
    assert result["data"][CONF_DOGS][0][CONF_DOG_ID] == "buddy_1"
    assert result["data"][CONF_DOGS][0][CONF_DOG_NAME] == "Buddy"


@pytest.mark.asyncio
async def test_user_flow_invalid_auth_shows_form_error(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    flow = PawControlConfigFlow()
    flow.hass = hass
    await flow.async_step_user({CONF_NAME: "Paw Control"})

    async def _raise_invalid_auth(_user_input: dict[str, str]) -> dict[str, str]:
        raise FlowValidationError(base_errors=["invalid_auth"])

    monkeypatch.setattr(flow, "_validate_dog_input_cached", _raise_invalid_auth)

    result = await flow.async_step_add_dog({
        CONF_DOG_NAME: "Buddy",
        CONF_DOG_ID: "buddy",
    })
    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["base"] == "invalid_auth"


@pytest.mark.asyncio
async def test_user_flow_cannot_connect_shows_form_error(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    flow = PawControlConfigFlow()
    flow.hass = hass
    await flow.async_step_user({CONF_NAME: "Paw Control"})

    async def _raise_connect_error(_user_input: dict[str, str]) -> dict[str, str]:
        raise FlowValidationError(base_errors=["cannot_connect"])

    monkeypatch.setattr(flow, "_validate_dog_input_cached", _raise_connect_error)

    result = await flow.async_step_add_dog({
        CONF_DOG_NAME: "Buddy",
        CONF_DOG_ID: "buddy",
    })
    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["base"] == "cannot_connect"


@pytest.mark.asyncio
async def test_user_flow_unknown_exception_shows_unknown(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    flow = PawControlConfigFlow()
    flow.hass = hass
    await flow.async_step_user({CONF_NAME: "Paw Control"})

    async def _raise_unknown(_user_input: dict[str, str]) -> dict[str, str]:
        raise RuntimeError("unexpected")

    monkeypatch.setattr(flow, "_validate_dog_input_cached", _raise_unknown)

    result = await flow.async_step_add_dog({
        CONF_DOG_NAME: "Buddy",
        CONF_DOG_ID: "buddy",
    })
    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["base"] == "unknown_error"


async def test_duplicate_entry_aborts_already_configured(hass: HomeAssistant) -> None:
    existing = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, data={CONF_DOGS: []})
    existing.add_to_hass(hass)

    flow = PawControlConfigFlow()
    flow.hass = hass
    result = await flow.async_step_user()
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_flow_success_updates_entry(
    hass: HomeAssistant,
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=DOMAIN,
        data={
            CONF_DOGS: [
                {
                    CONF_DOG_ID: "buddy",
                    CONF_DOG_NAME: "Buddy",
                }
            ]
        },
        options={},
    )
    entry.add_to_hass(hass)

    flow = PawControlConfigFlow()
    flow.hass = hass
    flow.context = {"entry_id": entry.entry_id}

    await flow.async_step_reauth({})
    result = await flow.async_step_reauth_confirm({"confirm": True})

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert isinstance(entry.data["reauth_timestamp"], str)
    assert isinstance(entry.options["last_reauth"], str)


async def test_reauth_flow_failure_keeps_entry(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=DOMAIN,
        data={CONF_DOGS: [{CONF_DOG_ID: "buddy", CONF_DOG_NAME: "Buddy"}]},
        options={},
    )
    entry.add_to_hass(hass)
    flow = PawControlConfigFlow()
    flow.hass = hass
    flow.context = {"entry_id": entry.entry_id}
    await flow.async_step_reauth({})

    async def _raise_on_update(*args: object, **kwargs: object) -> dict[str, str]:
        raise RuntimeError("update failed")

    monkeypatch.setattr(flow, "async_update_reload_and_abort", _raise_on_update)

    result = await flow.async_step_reauth_confirm({"confirm": True})
    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["base"] == "reauth_failed"
    assert "reauth_timestamp" not in entry.data
    assert "last_reauth" not in entry.options


async def test_reconfigure_step_shows_form(
    hass: HomeAssistant,
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_DOGS: [
                {
                    CONF_DOG_ID: "buddy",
                    CONF_DOG_NAME: "Buddy",
                }
            ]
        },
        options={"entity_profile": "standard"},
    )
    entry.add_to_hass(hass)

    flow = PawControlConfigFlow()
    flow.hass = hass
    flow.context = {"entry_id": entry.entry_id}

    result = await flow.async_step_reconfigure()

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reconfigure"


@pytest.mark.asyncio
async def test_options_flow_updates_options(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Options updates are returned as persisted payloads for Home Assistant."""
    flow = PawControlOptionsFlow()
    flow.hass = hass
    flow.initialize_from_config_entry(mock_config_entry)

    result = await flow.async_step_entity_profiles({"entity_profile": "advanced"})

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"]["entity_profile"] == "advanced"


async def test_reauth_health_check_reports_config_issues(
    hass: HomeAssistant,
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_DOGS: [
                {
                    CONF_DOG_ID: "buddy",
                    CONF_DOG_NAME: "Buddy",
                    CONF_MODULES: {"feeding": "yes"},
                },
                {
                    CONF_DOG_ID: "buddy",
                    CONF_DOG_NAME: "Buddy 2",
                    CONF_MODULES: {"walking": True},
                },
            ]
        },
        options={"entity_profile": "broken_profile"},
    )
    entry.add_to_hass(hass)

    flow = PawControlConfigFlow()
    flow.hass = hass

    summary = await flow._check_config_health_enhanced(entry)

    assert summary["healthy"] is False
    assert summary["total_dogs"] == 2
    assert summary["validated_dogs"] == 2
    assert "Duplicate dog IDs detected" in summary["issues"]
    assert (
        "Invalid profile 'broken_profile' - will use 'standard'" in summary["warnings"]
    )


async def test_reauth_health_summary_safe_handles_timeout(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_DOGS: []},
        options={},
    )
    flow = PawControlConfigFlow()
    flow.hass = hass

    async def _raise_timeout(_entry: MockConfigEntry) -> object:
        raise TimeoutError

    monkeypatch.setattr(flow, "_check_config_health_enhanced", _raise_timeout)

    summary = await flow._get_health_status_summary_safe(entry)

    assert summary == "Health check timeout"
