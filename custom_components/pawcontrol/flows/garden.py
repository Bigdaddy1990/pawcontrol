"""Garden flow helpers for Paw Control configuration and options."""

import voluptuous as vol

from ..selector_shim import selector


class GardenModuleSelectorMixin:
  """Provide helpers for garden module selection fields."""  # noqa: E111

  @staticmethod  # noqa: E111
  def _build_garden_module_selector(  # noqa: E111
    *,
    field: str,
    default: bool,
  ) -> dict[vol.Marker, object]:
    """Return a selector mapping for a garden module toggle."""

    return {
      vol.Optional(
        field,
        default=default,
      ): selector.BooleanSelector(),
    }
