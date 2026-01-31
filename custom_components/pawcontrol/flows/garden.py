"""Garden flow helpers for Paw Control configuration and options."""

from __future__ import annotations

import voluptuous as vol

from ..selector_shim import selector


class GardenModuleSelectorMixin:
  """Provide helpers for garden module selection fields."""

  @staticmethod
  def _build_garden_module_selector(
    *,
    field: str,
    default: bool,
  ) -> dict[vol.Optional, selector.BooleanSelector]:
    """Return a selector mapping for a garden module toggle."""

    return {
      vol.Optional(
        field,
        default=default,
      ): selector.BooleanSelector(),
    }
