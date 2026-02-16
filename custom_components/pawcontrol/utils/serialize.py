"""JSON serialization utilities for entity attributes.

Ensures all entity extra_state_attributes are JSON-serializable for
Home Assistant's state machine and diagnostics export.

Quality Scale: Platinum
Python: 3.14+
"""

# ruff: noqa: E111

from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from datetime import datetime, timedelta
from typing import Any

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
  """  # noqa: E111
  return dt.isoformat()  # noqa: E111


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
  """  # noqa: E111
  return int(td.total_seconds())  # noqa: E111


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
  """  # noqa: E111
  if not is_dataclass(obj):
    raise TypeError(f"Expected dataclass instance, got {type(obj).__name__}")
  if isinstance(obj, type):
    raise TypeError(
      "Expected dataclass instance, but received a class. "
      "Did you mean to instantiate it?",
    )
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
  """  # noqa: E111
  result: dict[str, Any] = {}  # noqa: E111

  for key, value in attrs.items():  # noqa: E111
    result[key] = _serialize_value(value)

  return result  # noqa: E111


def _serialize_value(value: Any) -> Any:
  """Recursively serialize a value to JSON-safe format.

  Args:
      value: Value to serialize

  Returns:
      JSON-serializable value
  """  # noqa: E111
  # Handle None  # noqa: E114
  if value is None:  # noqa: E111
    return None

  # Handle datetime  # noqa: E114
  if isinstance(value, datetime):  # noqa: E111
    return serialize_datetime(value)

  # Handle timedelta  # noqa: E114
  if isinstance(value, timedelta):  # noqa: E111
    return serialize_timedelta(value)

  # Handle dataclass  # noqa: E114
  if is_dataclass(value) and not isinstance(value, type):  # noqa: E111
    # Recursively serialize dataclass fields
    return {k: _serialize_value(v) for k, v in asdict(value).items()}

  # Handle dict (recursively)  # noqa: E114
  if isinstance(value, dict):  # noqa: E111
    return {k: _serialize_value(v) for k, v in value.items()}

  # Handle list/tuple (recursively)  # noqa: E114
  if isinstance(value, list | tuple):  # noqa: E111
    return [_serialize_value(item) for item in value]

  # Handle primitives (str, int, float, bool)  # noqa: E114
  if isinstance(value, str | int | float | bool):  # noqa: E111
    return value

  # Fallback: convert to string  # noqa: E114
  return str(value)  # noqa: E111
