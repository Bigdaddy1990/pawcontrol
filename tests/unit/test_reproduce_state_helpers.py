"""Unit tests for reproduce state helpers."""

from typing import Any

from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Context, HomeAssistant, State
import pytest

from custom_components.pawcontrol.reproduce_state import async_reproduce_platform_states


@pytest.mark.asyncio
async def test_async_reproduce_platform_states_calls_handler_with_context(
    hass: HomeAssistant,
) -> None:
    """Invoke the handler when state and preprocess are valid."""
    entity_id = "switch.pawcontrol_test"
    desired_state = State(entity_id, STATE_ON)
    current_state = State(entity_id, STATE_OFF)
    context = Context()

    hass.states.async_set(entity_id, STATE_OFF)

    calls: list[tuple[str, str, bool, dict[str, Any]]] = []

    def preprocess(state: State) -> dict[str, Any] | None:
        return {"target": state.state}

    async def handler(
        _hass: HomeAssistant,
        wanted_state: State,
        existing_state: State,
        processed: dict[str, Any],
        call_context: Context | None,
    ) -> None:
        calls.append((
            wanted_state.entity_id,
            existing_state.state,
            call_context is context,
            processed,
        ))

    await async_reproduce_platform_states(
        hass,
        [desired_state],
        "switch",
        preprocess,
        handler,
        context=context,
    )

    assert calls == [(entity_id, current_state.state, True, {"target": STATE_ON})]


@pytest.mark.asyncio
async def test_async_reproduce_platform_states_skips_invalid_and_missing_entities(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Skip unavailable, unknown, and missing entity states."""
    existing_entity = "switch.pawcontrol_existing"
    missing_entity = "switch.pawcontrol_missing"

    hass.states.async_set(existing_entity, STATE_OFF)

    handled: list[str] = []

    def preprocess(state: State) -> str | None:
        return state.state

    async def handler(
        _hass: HomeAssistant,
        wanted_state: State,
        _existing_state: State,
        _processed: str,
        _context: Context | None,
    ) -> None:
        handled.append(wanted_state.entity_id)

    await async_reproduce_platform_states(
        hass,
        [
            State(existing_entity, STATE_UNAVAILABLE),
            State(existing_entity, STATE_UNKNOWN),
            State(missing_entity, STATE_ON),
        ],
        "switch",
        preprocess,
        handler,
    )

    assert handled == []
    assert "Cannot reproduce switch state" in caplog.text
    assert "Switch entity switch.pawcontrol_missing not found" in caplog.text


@pytest.mark.asyncio
async def test_async_reproduce_platform_states_skips_when_preprocess_returns_none(
    hass: HomeAssistant,
) -> None:
    """Do not call handler when preprocess returns None."""
    entity_id = "switch.pawcontrol_skip"
    hass.states.async_set(entity_id, STATE_OFF)

    calls = 0

    def preprocess(_state: State) -> None:
        return None

    async def handler(
        _hass: HomeAssistant,
        _wanted_state: State,
        _existing_state: State,
        _processed: None,
        _context: Context | None,
    ) -> None:
        nonlocal calls
        calls += 1

    await async_reproduce_platform_states(
        hass,
        [State(entity_id, STATE_ON)],
        "switch",
        preprocess,
        handler,
    )

    assert calls == 0
