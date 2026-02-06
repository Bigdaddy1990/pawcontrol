"""Minimal Home Assistant symbol aliases.

This module intentionally avoids version compatibility shims.
"""

from __future__ import annotations

from enum import Enum

from homeassistant.const import UnitOfMass

MASS_GRAMS = UnitOfMass.GRAMS
MASS_KILOGRAMS = UnitOfMass.KILOGRAMS


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
