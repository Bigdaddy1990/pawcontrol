from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pawcontrol.config_flow import PawControlConfigFlow
from custom_components.pawcontrol.config_flow_base import INTEGRATION_SCHEMA
from custom_components.pawcontrol.const import (
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOGS,
    CONF_NAME,
    DOMAIN,
)
from custom_components.pawcontrol.exceptions import ConfigEntryAuthFailed


async def test_user_step_shows_form(hass: HomeAssistant) -> None:
    flow = PawControlConfigFlow()
    flow.hass = hass
    result = await flow.async_step_user()

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"


async def test_add_dog_then_finish_creates_entry(hass: HomeAssistant) -> None:
    flow = PawControlConfigFlow()
    flow.hass = hass

    user = await flow.async_step_user({CONF_NAME: "Paw Control"})
    assert user["type"] == FlowResultType.FORM
    assert user["step_id"] == "add_dog"
    assert flow._integration_name == "Paw Control"

    dog_step = await flow.async_step_add_dog({
        CONF_DOG_NAME: "Buddy",
        CONF_DOG_ID: "buddy_1",
    })
    assert dog_step["type"] == FlowResultType.FORM
    assert dog_step["step_id"] == "dog_modules"

    step: dict[str, object] = await flow.async_step_dog_modules({
        "enable_feeding": True
    })
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

    result = step
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_DOGS][0][CONF_DOG_ID] == "buddy_1"


async def test_duplicate_dog_id_is_rejected(hass: HomeAssistant) -> None:
    flow = PawControlConfigFlow()
    flow.hass = hass
    await flow.async_step_user({CONF_NAME: "Paw Control"})
    await flow.async_step_add_dog({CONF_DOG_NAME: "Buddy", CONF_DOG_ID: "buddy"})
    await flow.async_step_dog_modules({"enable_feeding": True})

    duplicate = await flow.async_step_add_dog({
        CONF_DOG_NAME: "Buddy 2",
        CONF_DOG_ID: "buddy",
    })
    assert duplicate["type"] == FlowResultType.FORM
    assert duplicate["errors"] == {CONF_DOG_ID: "dog_id_already_exists"}


async def test_reauth_step_shows_confirmation_form(
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
        options={},
    )
    entry.add_to_hass(hass)

    flow = PawControlConfigFlow()
    flow.hass = hass
    flow.context = {"entry_id": entry.entry_id}

    result = await flow.async_step_reauth({})

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"


async def test_reauth_rejects_invalid_dog_payload(
    hass: HomeAssistant,
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_DOGS: [
                {
                    CONF_DOG_ID: "",
                    CONF_DOG_NAME: "",
                }
            ]
        },
        options={},
    )
    entry.add_to_hass(hass)

    flow = PawControlConfigFlow()
    flow.hass = hass
    flow.context = {"entry_id": entry.entry_id}

    with pytest.raises(ConfigEntryAuthFailed):
        await flow.async_step_reauth({})


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
