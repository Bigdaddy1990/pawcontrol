"""Tests for PawControl reproduce state support."""

import pytest

pytest.importorskip("homeassistant")

from homeassistant.components import (
    number as number_component,
    select as select_component,
    switch as switch_component,
    text as text_component,
)
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, ServiceCall, State

from custom_components.pawcontrol import (
    number as pawcontrol_number,
    select as pawcontrol_select,
    switch as pawcontrol_switch,
    text as pawcontrol_text,
)

# Compatibility constants for different Home Assistant test harness versions.
ATTR_ENTITY_ID = "entity_id"
ATTR_VALUE = "value"
ATTR_OPTION = "option"
ATTR_OPTIONS = "options"


def _capture_service_calls(
    hass: HomeAssistant,
    domain: str,
    service: str,
) -> list[ServiceCall]:
    calls: list[ServiceCall] = []  # noqa: E111

    async def _handler(call: ServiceCall) -> None:  # noqa: E111
        calls.append(call)

    hass.services.async_register(domain, service, _handler)  # noqa: E111
    return calls  # noqa: E111


@pytest.mark.asyncio
async def test_switch_reproduce_state_calls_service(hass: HomeAssistant) -> None:
    """Reproduce switch state via turn_on service."""  # noqa: E111

    entity_id = "switch.pawcontrol_main_power"  # noqa: E111
    hass.states.async_set(entity_id, STATE_OFF)  # noqa: E111

    calls = _capture_service_calls(  # noqa: E111
        hass,
        switch_component.DOMAIN,
        switch_component.SERVICE_TURN_ON,
    )

    await pawcontrol_switch.async_reproduce_state(  # noqa: E111
        hass,
        [State(entity_id, STATE_ON)],
    )
    await hass.async_block_till_done()  # noqa: E111

    assert len(calls) == 1  # noqa: E111
    assert calls[0].data[ATTR_ENTITY_ID] == entity_id  # noqa: E111


@pytest.mark.asyncio
async def test_switch_reproduce_state_invalid_state(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Ignore invalid switch states."""  # noqa: E111

    entity_id = "switch.pawcontrol_main_power"  # noqa: E111
    hass.states.async_set(entity_id, STATE_OFF)  # noqa: E111

    calls = _capture_service_calls(  # noqa: E111
        hass,
        switch_component.DOMAIN,
        switch_component.SERVICE_TURN_ON,
    )

    await pawcontrol_switch.async_reproduce_state(  # noqa: E111
        hass,
        [State(entity_id, "invalid")],
    )
    await hass.async_block_till_done()  # noqa: E111

    assert len(calls) == 0  # noqa: E111
    assert "Invalid switch state" in caplog.text  # noqa: E111


@pytest.mark.asyncio
async def test_select_reproduce_state_calls_service(hass: HomeAssistant) -> None:
    """Reproduce select state via select_option service."""  # noqa: E111

    entity_id = "select.pawcontrol_notification_priority"  # noqa: E111
    hass.states.async_set(entity_id, "low", {ATTR_OPTIONS: ["low", "high"]})  # noqa: E111

    calls = _capture_service_calls(  # noqa: E111
        hass,
        select_component.DOMAIN,
        select_component.SERVICE_SELECT_OPTION,
    )

    await pawcontrol_select.async_reproduce_state(  # noqa: E111
        hass,
        [State(entity_id, "high")],
    )
    await hass.async_block_till_done()  # noqa: E111

    assert len(calls) == 1  # noqa: E111
    assert calls[0].data[ATTR_ENTITY_ID] == entity_id  # noqa: E111
    assert calls[0].data[ATTR_OPTION] == "high"  # noqa: E111


@pytest.mark.asyncio
async def test_select_reproduce_state_invalid_state(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Ignore invalid select options."""  # noqa: E111

    entity_id = "select.pawcontrol_notification_priority"  # noqa: E111
    hass.states.async_set(entity_id, "low", {ATTR_OPTIONS: ["low", "high"]})  # noqa: E111

    calls = _capture_service_calls(  # noqa: E111
        hass,
        select_component.DOMAIN,
        select_component.SERVICE_SELECT_OPTION,
    )

    await pawcontrol_select.async_reproduce_state(  # noqa: E111
        hass,
        [State(entity_id, "invalid")],
    )
    await hass.async_block_till_done()  # noqa: E111

    assert len(calls) == 0  # noqa: E111
    assert "Invalid select option" in caplog.text  # noqa: E111


@pytest.mark.asyncio
async def test_number_reproduce_state_calls_service(hass: HomeAssistant) -> None:
    """Reproduce number state via set_value service."""  # noqa: E111

    entity_id = "number.pawcontrol_daily_walk_target"  # noqa: E111
    hass.states.async_set(entity_id, "5")  # noqa: E111

    calls = _capture_service_calls(  # noqa: E111
        hass,
        number_component.DOMAIN,
        number_component.SERVICE_SET_VALUE,
    )

    await pawcontrol_number.async_reproduce_state(  # noqa: E111
        hass,
        [State(entity_id, "7.5")],
    )
    await hass.async_block_till_done()  # noqa: E111

    assert len(calls) == 1  # noqa: E111
    assert calls[0].data[ATTR_ENTITY_ID] == entity_id  # noqa: E111
    assert calls[0].data[ATTR_VALUE] == 7.5  # noqa: E111


@pytest.mark.asyncio
async def test_number_reproduce_state_invalid_state(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Ignore invalid number states."""  # noqa: E111

    entity_id = "number.pawcontrol_daily_walk_target"  # noqa: E111
    hass.states.async_set(entity_id, "5")  # noqa: E111

    calls = _capture_service_calls(  # noqa: E111
        hass,
        number_component.DOMAIN,
        number_component.SERVICE_SET_VALUE,
    )

    await pawcontrol_number.async_reproduce_state(  # noqa: E111
        hass,
        [State(entity_id, "bad")],
    )
    await hass.async_block_till_done()  # noqa: E111

    assert len(calls) == 0  # noqa: E111
    assert "Invalid number state" in caplog.text  # noqa: E111


@pytest.mark.asyncio
async def test_text_reproduce_state_calls_service(hass: HomeAssistant) -> None:
    """Reproduce text state via set_value service."""  # noqa: E111

    entity_id = "text.pawcontrol_dog_notes"  # noqa: E111
    hass.states.async_set(entity_id, "hello")  # noqa: E111

    calls = _capture_service_calls(  # noqa: E111
        hass,
        text_component.DOMAIN,
        text_component.SERVICE_SET_VALUE,
    )

    await pawcontrol_text.async_reproduce_state(  # noqa: E111
        hass,
        [State(entity_id, "world")],
    )
    await hass.async_block_till_done()  # noqa: E111

    assert len(calls) == 1  # noqa: E111
    assert calls[0].data[ATTR_ENTITY_ID] == entity_id  # noqa: E111
    assert calls[0].data[ATTR_VALUE] == "world"  # noqa: E111


@pytest.mark.asyncio
async def test_text_reproduce_state_invalid_state(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Ignore invalid text states."""  # noqa: E111

    entity_id = "text.pawcontrol_dog_notes"  # noqa: E111
    hass.states.async_set(entity_id, "hello")  # noqa: E111

    calls = _capture_service_calls(  # noqa: E111
        hass,
        text_component.DOMAIN,
        text_component.SERVICE_SET_VALUE,
    )

    await pawcontrol_text.async_reproduce_state(  # noqa: E111
        hass,
        [State(entity_id, STATE_UNKNOWN)],
    )
    await hass.async_block_till_done()  # noqa: E111

    assert len(calls) == 0  # noqa: E111
    assert "Cannot reproduce text state" in caplog.text  # noqa: E111
