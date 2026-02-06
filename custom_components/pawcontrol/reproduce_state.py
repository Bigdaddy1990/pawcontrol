"""Shared helpers for reproducing platform states."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Sequence
from typing import TypeVar

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Context, HomeAssistant, State

_LOGGER = logging.getLogger(__name__)

T = TypeVar("T")

Preprocessor = Callable[[State], T | None]
Handler = Callable[[HomeAssistant, State, State, T, Context | None], Awaitable[None]]


async def async_reproduce_platform_states(
  hass: HomeAssistant,
  states: Sequence[State],
  platform_name: str,
  preprocess: Preprocessor[T],
  handler: Handler[T],
  *,
  context: Context | None = None,
) -> None:
  """Iterate over states and call a handler for each valid one."""
  for state in states:
    if state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
      _LOGGER.warning(
        "Cannot reproduce %s state for %s: %s",
        platform_name,
        state.entity_id,
        state.state,
      )
      continue

    processed = preprocess(state)
    if processed is None:
      continue

    current_state = hass.states.get(state.entity_id)
    if current_state is None:
      _LOGGER.warning(
        "%s entity %s not found for state reproduction",
        platform_name.capitalize(),
        state.entity_id,
      )
      continue

    await handler(hass, state, current_state, processed, context)
