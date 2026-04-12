"""High-level config/options flow branch coverage tests for PawControl."""

from unittest.mock import AsyncMock

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pawcontrol.config_flow import PawControlConfigFlow
from custom_components.pawcontrol.const import (
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOGS,
    CONF_NAME,
    DOMAIN,
)
from custom_components.pawcontrol.exceptions import FlowValidationError
from custom_components.pawcontrol.options_flow import PawControlOptionsFlow


async def _complete_minimal_setup(flow: PawControlConfigFlow) -> dict[str, object]:
    """Run setup until the flow yields a terminal result."""
    result = await flow.async_step_user({CONF_NAME: "Paw Control"})
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "add_dog"

    result = await flow.async_step_add_dog({
        CONF_DOG_NAME: "Buddy",
        CONF_DOG_ID: "buddy_1",
    })
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "dog_modules"

    result = await flow.async_step_dog_modules({"enable_feeding": True})
    assert result["type"] == FlowResultType.FORM

    result = await flow.async_step_add_another_dog({"add_another": False})
    while result["type"] == FlowResultType.FORM:
        match result["step_id"]:
            case "configure_modules":
                result = await flow.async_step_configure_modules({})
            case "configure_dashboard":
                result = await flow.async_step_configure_dashboard({})
            case "entity_profile":
                result = await flow.async_step_entity_profile({
                    "entity_profile": "standard"
                })
            case "final_setup":
                result = await flow.async_step_final_setup({})
            case step_id:
                raise AssertionError(f"Unexpected config flow step: {step_id}")

    return result


async def test_config_flow_success_creates_entry(hass: HomeAssistant) -> None:
    flow = PawControlConfigFlow()
    flow.hass = hass

    result = await _complete_minimal_setup(flow)

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"].startswith("Paw Control")
    assert result["data"][CONF_DOGS][0][CONF_DOG_ID] == "buddy_1"


@pytest.mark.parametrize(
    ("error_key", "raised_error"),
    [
        ("invalid_auth", FlowValidationError(base_errors=["invalid_auth"])),
        ("cannot_connect", FlowValidationError(base_errors=["cannot_connect"])),
    ],
)
async def test_config_flow_known_validation_errors_return_form_error(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
    error_key: str,
    raised_error: FlowValidationError,
) -> None:
    flow = PawControlConfigFlow()
    flow.hass = hass
    await flow.async_step_user({CONF_NAME: "Paw Control"})

    async def _raise_validation(_user_input: dict[str, str]) -> dict[str, str]:
        raise raised_error

    monkeypatch.setattr(flow, "_validate_dog_input_cached", _raise_validation)

    result = await flow.async_step_add_dog({
        CONF_DOG_NAME: "Buddy",
        CONF_DOG_ID: "buddy",
    })

    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["base"] == error_key


async def test_config_flow_unknown_error_returns_unknown_error_form(
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


async def test_config_flow_duplicate_aborts_already_configured(
    hass: HomeAssistant,
) -> None:
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, data={CONF_DOGS: []})
    entry.add_to_hass(hass)

    flow = PawControlConfigFlow()
    flow.hass = hass

    try:
        result = await flow.async_step_user()
        assert result["type"] == FlowResultType.ABORT
        assert result["reason"] == "already_configured"
    except Exception as exc:
        assert "already_configured" in str(exc)


async def test_reauth_confirm_success_aborts_with_success(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
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

    monkeypatch.setattr(flow, "async_set_unique_id", AsyncMock())
    monkeypatch.setattr(flow, "_abort_if_unique_id_mismatch", lambda **_kwargs: None)
    monkeypatch.setattr(
        flow,
        "async_update_reload_and_abort",
        AsyncMock(
            return_value={"type": FlowResultType.ABORT, "reason": "reauth_successful"}
        ),
        raising=False,
    )

    await flow.async_step_reauth({})
    result = await flow.async_step_reauth_confirm({"confirm": True})

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"


async def test_reauth_confirm_failure_returns_form_error(
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

    monkeypatch.setattr(flow, "async_set_unique_id", AsyncMock())
    monkeypatch.setattr(flow, "_abort_if_unique_id_mismatch", lambda **_kwargs: None)

    async def _raise_update_failure(*_: object, **__: object) -> dict[str, str]:
        raise RuntimeError("boom")

    monkeypatch.setattr(
        flow,
        "async_update_reload_and_abort",
        _raise_update_failure,
        raising=False,
    )

    result = await flow.async_step_reauth_confirm({"confirm": True})

    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["base"] == "reauth_failed"


async def test_options_flow_updates_options_entry(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    flow = PawControlOptionsFlow()
    flow.hass = hass
    flow.initialize_from_config_entry(mock_config_entry)

    result = await flow.async_step_entity_profiles({"entity_profile": "advanced"})

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"]["entity_profile"] == "advanced"
