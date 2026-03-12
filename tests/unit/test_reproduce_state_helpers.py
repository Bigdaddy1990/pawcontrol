"""Unit tests for shared reproduce-state helper coverage."""

from types import SimpleNamespace

import pytest
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Context, State

from custom_components.pawcontrol.reproduce_state import async_reproduce_platform_states


@pytest.mark.asyncio
async def test_async_reproduce_platform_states_calls_handler_for_valid_state() -> None:
    """Valid states should be preprocessed and forwarded to the handler."""
    current_state = State("switch.pawcontrol_main", STATE_OFF)
    hass = SimpleNamespace(states=SimpleNamespace(get=lambda _entity_id: current_state))
    context = Context()
    calls: list[tuple[str, str, str, Context | None]] = []

    async def _handler(_hass: object, target: State, current: State, value: str, ctx: Context | None) -> None:
        calls.append((target.entity_id, current.state, value, ctx))

    await async_reproduce_platform_states(
        hass,
        [State("switch.pawcontrol_main", STATE_ON)],
        "switch",
        lambda state: state.state,
        _handler,
        context=context,
    )

    assert calls == [("switch.pawcontrol_main", STATE_OFF, STATE_ON, context)]


@pytest.mark.asyncio
async def test_async_reproduce_platform_states_skips_unavailable_and_unknown_states(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Unavailable/unknown target states should only log and skip handling."""
    hass = SimpleNamespace(states=SimpleNamespace(get=lambda _entity_id: State("switch.any", STATE_OFF)))
    called = False

    async def _handler(
        _hass: object,
        _target: State,
        _current: State,
        _value: str,
        _context: Context | None,
    ) -> None:
        nonlocal called
        called = True

    await async_reproduce_platform_states(
        hass,
        [
            State("switch.pawcontrol_main", STATE_UNAVAILABLE),
            State("switch.pawcontrol_main", STATE_UNKNOWN),
        ],
        "switch",
        lambda state: state.state,
        _handler,
    )

    assert called is False
    assert "Cannot reproduce switch state for switch.pawcontrol_main" in caplog.text


@pytest.mark.asyncio
async def test_async_reproduce_platform_states_skips_when_preprocess_returns_none() -> None:
    """States should be skipped when preprocess indicates invalid target."""
    hass = SimpleNamespace(states=SimpleNamespace(get=lambda _entity_id: State("switch.any", STATE_OFF)))
    called = False

    async def _handler(
        _hass: object,
        _target: State,
        _current: State,
        _value: str,
        _context: Context | None,
    ) -> None:
        nonlocal called
        called = True

    await async_reproduce_platform_states(
        hass,
        [State("switch.pawcontrol_main", STATE_ON)],
        "switch",
        lambda _state: None,
        _handler,
    )

    assert called is False


@pytest.mark.asyncio
async def test_async_reproduce_platform_states_logs_when_entity_is_missing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Missing entities should log and avoid calling the handler."""
    hass = SimpleNamespace(states=SimpleNamespace(get=lambda _entity_id: None))
    called = False

    async def _handler(
        _hass: object,
        _target: State,
        _current: State,
        _value: str,
        _context: Context | None,
    ) -> None:
        nonlocal called
        called = True

    await async_reproduce_platform_states(
        hass,
        [State("switch.pawcontrol_missing", STATE_ON)],
        "switch",
        lambda state: state.state,
        _handler,
    )

    assert called is False
    assert "Switch entity switch.pawcontrol_missing not found" in caplog.text
