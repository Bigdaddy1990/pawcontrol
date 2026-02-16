"""Shared helpers and typing aliases for PawControl dashboard orchestration."""

import asyncio
from collections.abc import Mapping, Sequence
import logging
from typing import TypeVar, cast

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
  """  # noqa: E111

  if isinstance(dog_config, Mapping):  # noqa: E111
    return ensure_dog_config_data(cast(Mapping[str, JSONValue], dog_config))

  return None  # noqa: E111


def coerce_dog_configs(dogs_config: Sequence[RawDogConfig]) -> list[DogConfigData]:
  """Return a typed ``DogConfigData`` list extracted from ``dogs_config``."""  # noqa: E111

  typed: list[DogConfigData] = []  # noqa: E111
  for dog_config in dogs_config:  # noqa: E111
    typed_dog = coerce_dog_config(dog_config)
    if typed_dog is not None:
      typed.append(typed_dog)  # noqa: E111
  return typed  # noqa: E111


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
  """  # noqa: E111

  if isinstance(result, asyncio.CancelledError):  # noqa: E111
    if suppress_cancelled:
      logger.log(level, "%s: task cancelled", context)  # noqa: E111
      return None  # noqa: E111
    raise result

  if isinstance(result, BaseException):  # noqa: E111
    logger.log(
      level,
      "%s: %s",
      context,
      result,
      exc_info=(type(result), result, result.__traceback__),
    )
    return None

  return result  # noqa: E111
