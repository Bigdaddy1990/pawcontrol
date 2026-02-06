"""Minimal Home Assistant symbol aliases.

This module intentionally avoids version compatibility shims.
"""

from __future__ import annotations

from enum import Enum

from homeassistant import const as ha_const

UnitOfMass = getattr(ha_const, "UnitOfMass", None)
MASS_GRAMS = getattr(UnitOfMass, "GRAMS", "g")
MASS_KILOGRAMS = getattr(UnitOfMass, "KILOGRAMS", "kg")


class ConfigEntryState(Enum):
  """Config entry state aliases used by integration helpers."""

  LOADED = "loaded"


class ConfigEntryChange(Enum):
  """Config entry change aliases used by integration helpers."""

  ADDED = "added"
  REMOVED = "removed"
  UPDATED = "updated"


def ensure_homeassistant_exception_symbols() -> None:
  """No-op retained for legacy call sites."""


def bind_exception_alias(*_args: object, **_kwargs: object) -> None:
  """No-op retained for legacy call sites."""


def ensure_homeassistant_config_entry_symbols() -> None:
  """No-op retained for legacy call sites."""
