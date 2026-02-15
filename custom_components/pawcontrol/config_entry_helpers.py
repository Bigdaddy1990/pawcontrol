"""Helpers for working with config entry payloads."""

from __future__ import annotations


from typing import Any

from homeassistant.config_entries import ConfigEntry

from .const import CONF_DOGS


def get_entry_dogs(entry: ConfigEntry) -> list[dict[str, Any]]:
  """Return configured dogs from options, falling back to entry data."""
  options_dogs = entry.options.get(CONF_DOGS)
  if isinstance(options_dogs, list):
    return options_dogs
  data_dogs = entry.data.get(CONF_DOGS, [])
  return data_dogs if isinstance(data_dogs, list) else []
