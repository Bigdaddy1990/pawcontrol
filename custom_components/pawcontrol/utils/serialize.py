"""JSON serialization utilities for entity attributes.

Ensures all entity extra_state_attributes are JSON-serializable for
Home Assistant's state machine and diagnostics export.

Quality Scale: Platinum
Python: 3.14+
"""

from __future__ import annotations


from dataclasses import asdict, is_dataclass
from datetime import datetime, timedelta
from typing import Any
from collections.abc import Mapping

__all__ = [
  "serialize_datetime",
  "serialize_timedelta",
  "serialize_dataclass",
  "serialize_entity_attributes",
]


def serialize_datetime(dt: datetime) -> str:
  """Convert datetime to ISO 8601 string.

  Args:
      dt: Datetime object to serialize

  Returns:
      ISO 8601 formatted string

  Example:
      >>> from datetime import datetime, UTC
      >>> dt = datetime(2026, 2, 15, 10, 30, 0, tzinfo=UTC)
      >>> serialize_datetime(dt)
      '2026-02-15T10:30:00+00:00'
  """
  return dt.isoformat()


def serialize_timedelta(td: timedelta) -> int:
  """Convert timedelta to total seconds.

  Args:
      td: Timedelta object to serialize

  Returns:
      Total seconds as integer

  Example:
      >>> from datetime import timedelta
      >>> td = timedelta(minutes=30)
      >>> serialize_timedelta(td)
      1800
  """
  return int(td.total_seconds())


def serialize_dataclass(obj: Any) -> dict[str, Any]:
  """Convert dataclass instance to dictionary.

  Args:
      obj: Dataclass instance to serialize

  Returns:
      Dictionary representation

  Raises:
      TypeError: If obj is not a dataclass

  Example:
      >>> from dataclasses import dataclass
      >>> @dataclass
      ... class Dog:
      ...   name: str
      ...   age: int
      >>> dog = Dog("Buddy", 5)
      >>> serialize_dataclass(dog)
      {'name': 'Buddy', 'age': 5}
  """
  if not is_dataclass(obj):
    raise TypeError(f"Expected dataclass, got {type(obj).__name__}")
  return asdict(obj)


def serialize_entity_attributes(attrs: Mapping[str, Any]) -> dict[str, Any]:
  """Ensure all entity attributes are JSON-serializable.

  Converts datetime, timedelta, and dataclass instances to JSON-safe formats.
  Recursively processes nested dictionaries and lists.

  Args:
      attrs: Dictionary of entity attributes

  Returns:
      JSON-serializable dictionary

  Example:
      >>> from datetime import datetime, timedelta, UTC
      >>> attrs = {
      ...   "last_update": datetime(2026, 2, 15, 10, 30, tzinfo=UTC),
      ...   "duration": timedelta(minutes=30),
      ...   "count": 42,
      ...   "name": "Buddy",
      ... }
      >>> result = serialize_entity_attributes(attrs)
      >>> result["last_update"]
      '2026-02-15T10:30:00+00:00'
      >>> result["duration"]
      1800
      >>> result["count"]
      42
  """
  result: dict[str, Any] = {}

  for key, value in attrs.items():
    result[key] = _serialize_value(value)

  return result


def _serialize_value(value: Any) -> Any:
  """Recursively serialize a value to JSON-safe format.

  Args:
      value: Value to serialize

  Returns:
      JSON-serializable value
  """
  # Handle None
  if value is None:
    return None

  # Handle datetime
  if isinstance(value, datetime):
    return serialize_datetime(value)

  # Handle timedelta
  if isinstance(value, timedelta):
    return serialize_timedelta(value)

  # Handle dataclass
  if is_dataclass(value):
    # Recursively serialize dataclass fields
    return {k: _serialize_value(v) for k, v in asdict(value).items()}

  # Handle dict (recursively)
  if isinstance(value, dict):
    return {k: _serialize_value(v) for k, v in value.items()}

  # Handle list/tuple (recursively)
  if isinstance(value, list | tuple):
    return [_serialize_value(item) for item in value]

  # Handle primitives (str, int, float, bool)
  if isinstance(value, str | int | float | bool):
    return value

  # Fallback: convert to string
  return str(value)
