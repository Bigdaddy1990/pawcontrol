"""Shared helpers and typing aliases for PawControl dashboard orchestration."""

from __future__ import annotations

from typing import TypeVar
import asyncio
import logging
from collections.abc import Mapping, Sequence
from typing import cast

from .types import (
  DogConfigData,
  JSONValue,
  LovelaceCardConfig,
  RawDogConfig,
  ensure_dog_config_data,
)

type CardConfig = LovelaceCardConfig
type CardCollection = list[LovelaceCardConfig]

__all__ = [
  "CardCollection",
  "CardConfig",
  "coerce_dog_config",
  "coerce_dog_configs",
  "unwrap_async_result",
]


def coerce_dog_config(dog_config: RawDogConfig) -> DogConfigData | None:
  """Return a typed dog configuration for dashboard rendering.

  Card gatherers receive a mix of raw dictionaries (from legacy storage) and
  ``DogConfigData`` typed dictionaries. Normalising the payload here keeps the
  helpers focused on rendering logic and guarantees downstream consumers work
  with typed metadata only.
  """

  if isinstance(dog_config, Mapping):
    return ensure_dog_config_data(cast(Mapping[str, JSONValue], dog_config))

  return None


def coerce_dog_configs(dogs_config: Sequence[RawDogConfig]) -> list[DogConfigData]:
  """Return a typed ``DogConfigData`` list extracted from ``dogs_config``."""

  typed: list[DogConfigData] = []
  for dog_config in dogs_config:
    typed_dog = coerce_dog_config(dog_config)
    if typed_dog is not None:
      typed.append(typed_dog)
  return typed


T = TypeVar("T")


def unwrap_async_result[T](
  result: T | BaseException,
  *,
  context: str,
  logger: logging.Logger,
  level: int = logging.WARNING,
  suppress_cancelled: bool = False,
) -> T | None:
  """Return ``result`` when successful, logging and returning ``None`` otherwise.

  Args:
      result: Payload produced by an ``asyncio.gather`` call.
      context: Human-readable context explaining the gather operation.
      logger: Logger used to emit cancellation and error details.
      level: Logging level for non-fatal failures.
      suppress_cancelled: When ``True`` cancelled tasks are logged instead of
          re-raised.

  Returns:
      The successful payload when ``result`` is not an exception, otherwise
      ``None``.

  Raises:
      asyncio.CancelledError: Raised when a gather task is cancelled and
          ``suppress_cancelled`` is ``False``.
  """

  if isinstance(result, asyncio.CancelledError):
    if suppress_cancelled:
      logger.log(level, "%s: task cancelled", context)
      return None
    raise result

  if isinstance(result, BaseException):
    logger.log(
      level,
      "%s: %s",
      context,
      result,
      exc_info=(type(result), result, result.__traceback__),
    )
    return None

  return result
