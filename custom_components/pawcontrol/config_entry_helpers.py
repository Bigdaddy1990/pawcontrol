"""Helpers for working with config entry payloads."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry

from .const import CONF_DOGS


def get_entry_dogs(entry: ConfigEntry) -> list[dict[str, Any]]:
  """Return configured dogs from options, falling back to entry data."""  # noqa: E111
  options_dogs = entry.options.get(CONF_DOGS)  # noqa: E111
  if isinstance(options_dogs, list):  # noqa: E111
    return options_dogs
  data_dogs = entry.data.get(CONF_DOGS, [])  # noqa: E111
  return data_dogs if isinstance(data_dogs, list) else []  # noqa: E111
