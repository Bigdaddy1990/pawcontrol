"""Utility functions for JSON normalization."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from collections.abc import Set as ABCSet
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, time, timedelta

# Type alias for JSON-serializable values.
JSONValue = str | int | float | bool | None | list["JSONValue"] | dict[str, "JSONValue"]


def normalize_value(value: object) -> JSONValue:
  """Recursively normalise values to JSON-serializable primitives.

  Converts datetimes to ISO strings, timedeltas to seconds, dataclasses to dicts,
  mappings, sets, and iterables to recursively normalised forms. Falls back to repr().
  """
  if value is None or isinstance(value, int | float | str | bool):
    return value  # type: ignore[return-value]
  if isinstance(value, datetime):
    return value.isoformat()
  if isinstance(value, date | time):
    return value.isoformat()
  if isinstance(value, timedelta):
    return value.total_seconds()  # type: ignore[return-value]
  if is_dataclass(value) and not isinstance(value, type):
    return {k: normalize_value(v) for k, v in asdict(value).items()}
  if isinstance(value, Mapping):
    return {str(k): normalize_value(v) for k, v in value.items()}
  if isinstance(value, ABCSet):
    return [normalize_value(v) for v in value]
  if isinstance(value, Iterable) and not isinstance(value, str | bytes):
    return [normalize_value(v) for v in value]
  return repr(value)
