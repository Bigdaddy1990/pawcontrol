"""Resilience helpers for PawControl.

Simplified to standard retry logic without heavy circuit breakers.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, TypeVar

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

T = TypeVar("T")
AsyncCallable = Callable[..., Awaitable[T]]


@dataclass(slots=True)
class RetryConfig:
  """Retry configuration for compatibility with existing callers."""

  max_attempts: int = 3
  base_delay: float = 1.0


@dataclass(slots=True)
class CircuitBreakerConfig:
  """Compatibility stub retained for existing imports."""

  failure_threshold: int = 5
  success_threshold: int = 2
  timeout_seconds: float = 60.0
  half_open_max_calls: int = 3


async def async_retry[T](
  func: AsyncCallable[T],
  *args: Any,
  attempts: int = 3,
  delay: float = 1.0,
  **kwargs: Any,
) -> T:
  """Simple retry helper with exponential backoff."""

  last_error: Exception | None = None
  for attempt in range(1, attempts + 1):
    try:
      return await func(*args, **kwargs)
    except Exception as err:  # pragma: no cover - exercised by call-sites
      last_error = err
      if attempt == attempts:
        break
      wait_time = delay * (2 ** (attempt - 1))
      _LOGGER.debug(
        "Attempt %d/%d failed for %s, retrying in %.1fs: %s",
        attempt,
        attempts,
        getattr(func, "__name__", repr(func)),
        wait_time,
        err,
      )
      await asyncio.sleep(wait_time)

  if last_error is not None:
    raise last_error
  raise RuntimeError("Retry failed without exception")


async def retry_with_backoff[T](
  func: AsyncCallable[T],
  *args: Any,
  config: RetryConfig | None = None,
  **kwargs: Any,
) -> T:
  """Compatibility wrapper around :func:`async_retry`."""

  retry_config = config or RetryConfig()
  return await async_retry(
    func,
    *args,
    attempts=max(1, retry_config.max_attempts),
    delay=max(0.0, retry_config.base_delay),
    **kwargs,
  )


class ResilienceManager:
  """Minimal resilience manager retained for compatibility."""

  def __init__(self, hass: HomeAssistant) -> None:
    self.hass = hass

  async def execute_with_resilience(
    self,
    func: AsyncCallable[T],
    *args: Any,
    circuit_breaker_name: str | None = None,
    retry_config: RetryConfig | None = None,
    **kwargs: Any,
  ) -> T:
    """Execute with simple retry logic."""

    del circuit_breaker_name
    return await retry_with_backoff(func, *args, config=retry_config, **kwargs)

  def get_all_circuit_breakers(self) -> dict[str, Any]:
    """Return empty circuit breaker stats in simplified mode."""

    return {}

  async def reset_circuit_breaker(self, name: str) -> bool:
    """Compatibility no-op."""

    del name
    return False

  async def reset_all_circuit_breakers(self) -> int:
    """Compatibility no-op."""

    return 0
