"""Shared helper functions for config and options flows."""

from __future__ import annotations

from typing import Any


def coerce_bool(value: Any, *, default: bool = False) -> bool:
  """Coerce an arbitrary value into a boolean flag."""

  if isinstance(value, bool):
    return value
  if isinstance(value, str):
    lowered = value.strip().lower()
    if lowered in {"1", "true", "yes", "on", "enabled"}:
      return True
    if lowered in {"0", "false", "no", "off", "disabled"}:
      return False
  if isinstance(value, int | float):
    return bool(value)
  return default


def coerce_str(value: Any, *, default: str = "") -> str:
  """Coerce arbitrary user input into a trimmed string."""

  if isinstance(value, str):
    trimmed = value.strip()
    return trimmed or default
  return default


def coerce_optional_str(value: Any) -> str | None:
  """Return a trimmed string when available, otherwise ``None``."""

  if isinstance(value, str):
    trimmed = value.strip()
    return trimmed or None
  return None


def coerce_optional_float(value: Any) -> float | None:
  """Coerce arbitrary user input into a float when possible."""

  if isinstance(value, float | int):
    return float(value)
  if isinstance(value, str):
    try:
      return float(value.strip())
    except ValueError:
      return None
  return None


def coerce_optional_int(value: Any) -> int | None:
  """Coerce arbitrary user input into an integer when possible."""

  if isinstance(value, int):
    return value
  if isinstance(value, float):
    return int(value)
  if isinstance(value, str):
    try:
      return int(value.strip())
    except ValueError:
      return None
  return None
