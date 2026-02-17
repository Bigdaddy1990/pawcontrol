"""Shared helpers for reproducing platform states."""

from collections.abc import Awaitable, Callable, Sequence
import logging
from typing import TypeVar

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Context, HomeAssistant, State

_LOGGER = logging.getLogger(__name__)

T = TypeVar("T")

Preprocessor = Callable[[State], T | None]
Handler = Callable[[HomeAssistant, State, State, T, Context | None], Awaitable[None]]


async def async_reproduce_platform_states[T](
    hass: HomeAssistant,
    states: Sequence[State],
    platform_name: str,
    preprocess: Preprocessor[T],
    handler: Handler[T],
    *,
    context: Context | None = None,
) -> None:
    """Iterate over states and call a handler for each valid one."""  # noqa: E111
    for state in states:  # noqa: E111
        if state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            _LOGGER.warning(  # noqa: E111
                "Cannot reproduce %s state for %s: %s",
                platform_name,
                state.entity_id,
                state.state,
            )
            continue  # noqa: E111

        processed = preprocess(state)
        if processed is None:
            continue  # noqa: E111

        current_state = hass.states.get(state.entity_id)
        if current_state is None:
            _LOGGER.warning(  # noqa: E111
                "%s entity %s not found for state reproduction",
                platform_name.capitalize(),
                state.entity_id,
            )
            continue  # noqa: E111

        await handler(hass, state, current_state, processed, context)
