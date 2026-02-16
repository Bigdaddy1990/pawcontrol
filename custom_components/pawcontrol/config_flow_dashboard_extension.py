"""Dashboard configuration extension for the config flow.

This module provides a mixin with additional steps for configuring the
dashboard during the integration setup. It can be mixed into the main
``PawControlConfigFlow`` class to keep the core config flow file concise.

Quality Scale: Platinum target
Home Assistant: 2025.9.0+
Python: 3.13+
"""

from collections.abc import Mapping
from typing import TYPE_CHECKING, Final, cast

from homeassistant.config_entries import ConfigFlowResult
import voluptuous as vol

from .config_flow_modules import (
  normalize_dashboard_language,
  translated_dashboard_feature,
)
from .const import (
  CONF_MODULES,
  DASHBOARD_MODE_SELECTOR_OPTIONS,
  DEFAULT_DASHBOARD_AUTO_CREATE,
  DEFAULT_DASHBOARD_MODE,
  DEFAULT_DASHBOARD_THEME,
  MODULE_GPS,
)
from .selector_shim import selector
from .types import (
  DASHBOARD_AUTO_CREATE_FIELD,
  DASHBOARD_CONFIGURATION_PLACEHOLDERS_TEMPLATE,
  DASHBOARD_ENABLED_FIELD,
  DASHBOARD_MODE_FIELD,
  DASHBOARD_PER_DOG_FIELD,
  DASHBOARD_THEME_FIELD,
  SHOW_MAPS_FIELD,
  SHOW_STATISTICS_FIELD,
  ConfigFlowPlaceholders,
  ConfigFlowUserInput,
  DashboardConfigurationStepInput,
  DashboardMode,
  DashboardSetupConfig,
  DogConfigData,
  DogModulesConfig,
  ExternalEntityConfig,
  clone_placeholders,
  freeze_placeholders,
)

_DASHBOARD_INFO_TRANSLATIONS: Final[Mapping[str, Mapping[str, str]]] = {
  "auto_create": {
    "en": "🎨 The dashboard will be automatically created after setup",
    "de": "🎨 Das Dashboard wird nach der Einrichtung automatisch erstellt",
  },
  "cards": {
    "en": "📊 It will include cards for each dog and their activities",
    "de": "📊 Enthält Karten für jeden Hund und seine Aktivitäten",
  },
  "maps": {
    "en": "🗺️ GPS maps will be shown if GPS module is enabled",
    "de": "🗺️ GPS-Karten werden angezeigt, wenn das GPS-Modul aktiviert ist",
  },
  "responsive": {
    "en": "📱 Dashboards are mobile-friendly and responsive",
    "de": "📱 Dashboards sind mobilfreundlich und responsiv",
  },
  "multi_dog": {
    "en": "🐕 Individual dashboards for {count} dogs recommended",
    "de": "🐕 Individuelle Dashboards für {count} Hunde empfohlen",
  },
}


def _build_dashboard_configure_placeholders(
  *,
  dog_count: int,
  dashboard_info: str,
  features: str,
) -> ConfigFlowPlaceholders:
  """Return immutable placeholders for the dashboard configuration form."""  # noqa: E111

  placeholders = clone_placeholders(  # noqa: E111
    DASHBOARD_CONFIGURATION_PLACEHOLDERS_TEMPLATE,
  )
  placeholders["dog_count"] = dog_count  # noqa: E111
  placeholders["dashboard_info"] = dashboard_info  # noqa: E111
  placeholders["features"] = features  # noqa: E111
  return freeze_placeholders(placeholders)  # noqa: E111


def _translated_dashboard_info_line(
  language: str | None,
  key: str,
  *,
  count: int | None = None,
) -> str:
  """Return a localized dashboard info line."""  # noqa: E111

  translations = _DASHBOARD_INFO_TRANSLATIONS.get(key)  # noqa: E111
  if translations is None:  # noqa: E111
    template = key
  else:  # noqa: E111
    template = (
      translations.get(normalize_dashboard_language(language))
      or translations.get("en")
      or key
    )

  if count is not None:  # noqa: E111
    return template.format(count=count)

  return template  # noqa: E111


class DashboardFlowMixin:
  """Mixin adding dashboard configuration steps to the config flow."""  # noqa: E111

  if TYPE_CHECKING:  # noqa: E111
    _dogs: list[DogConfigData]
    _enabled_modules: DogModulesConfig
    _dashboard_config: DashboardSetupConfig

    async def async_step_configure_external_entities(
      self,
      user_input: ExternalEntityConfig | None = None,
    ) -> ConfigFlowResult:
      """Type-checking stub for the GPS entity configuration step."""  # noqa: E111
      ...  # noqa: E111

    async def async_step_final_setup(
      self,
      user_input: ConfigFlowUserInput | None = None,
    ) -> ConfigFlowResult:
      """Type-checking stub for the concluding config flow step."""  # noqa: E111
      ...  # noqa: E111

    def async_show_form(
      self,
      *,
      step_id: str,
      data_schema: vol.Schema,
      description_placeholders: ConfigFlowPlaceholders | None = None,
      errors: dict[str, str] | None = None,
    ) -> ConfigFlowResult:
      """Type-checking stub for Home Assistant form rendering."""  # noqa: E111
      ...  # noqa: E111

  async def async_step_configure_dashboard(  # noqa: E111
    self,
    user_input: DashboardConfigurationStepInput | None = None,
  ) -> ConfigFlowResult:
    """Configure dashboard settings.

    This step allows users to configure how the dashboard should be created
    and displayed, including per-dog dashboards and theme selection.
    """

    has_multiple_dogs = len(self._dogs) > 1

    if user_input is not None:
      has_gps_enabled = self._enabled_modules.get(MODULE_GPS, False) or any(  # noqa: E111
        cast(DogModulesConfig, dog.get(CONF_MODULES, {})).get(
          MODULE_GPS,
          False,
        )
        for dog in self._dogs
      )
      str(  # noqa: E111
        user_input.get(
          "dashboard_mode",
          DEFAULT_DASHBOARD_MODE if has_multiple_dogs else "cards",
        ),
      )
      dashboard_config: DashboardSetupConfig = {  # noqa: E111
        DASHBOARD_ENABLED_FIELD: True,
        DASHBOARD_AUTO_CREATE_FIELD: bool(
          user_input.get(
            "auto_create_dashboard",
            DEFAULT_DASHBOARD_AUTO_CREATE,
          ),
        ),
        DASHBOARD_PER_DOG_FIELD: bool(
          user_input.get("create_per_dog_dashboards", False),
        ),
        DASHBOARD_THEME_FIELD: str(
          user_input.get("dashboard_theme", DEFAULT_DASHBOARD_THEME),
        ),
        DASHBOARD_MODE_FIELD: cast(
          DashboardMode,
          user_input.get(
            "dashboard_mode",
            DEFAULT_DASHBOARD_MODE if has_multiple_dogs else "cards",
          ),
        ),
        SHOW_STATISTICS_FIELD: bool(user_input.get("show_statistics", True)),
        SHOW_MAPS_FIELD: bool(user_input.get("show_maps", True)),
      }
      self._dashboard_config = dashboard_config  # noqa: E111

      if bool(has_gps_enabled):  # noqa: E111
        return await self.async_step_configure_external_entities()
      return await self.async_step_final_setup()  # noqa: E111

    has_gps_enabled = bool(
      self._enabled_modules.get(MODULE_GPS, False)
      or any(
        cast(DogModulesConfig, dog.get(CONF_MODULES, {})).get(
          MODULE_GPS,
          False,
        )
        for dog in self._dogs
      ),
    )

    hass_language: str | None = None
    hass = getattr(self, "hass", None)
    if hass is not None:
      hass_language = getattr(  # noqa: E111
        getattr(hass, "config", None),
        "language",
        None,
      )

    schema = vol.Schema(
      {
        vol.Optional(
          "auto_create_dashboard",
          default=DEFAULT_DASHBOARD_AUTO_CREATE,
        ): selector.BooleanSelector(),
        vol.Optional(
          "create_per_dog_dashboards",
          default=has_multiple_dogs,
        ): selector.BooleanSelector(),
        vol.Optional(
          "dashboard_theme",
          default=DEFAULT_DASHBOARD_THEME,
        ): selector.SelectSelector(
          selector.SelectSelectorConfig(
            options=[
              {
                "value": "default",
                "label": "Default - Clean and modern",
              },
              {
                "value": "dark",
                "label": "Dark - Night-friendly theme",
              },
              {
                "value": "playful",
                "label": "Playful - Colorful and fun",
              },
            ],
            mode=selector.SelectSelectorMode.DROPDOWN,
          ),
        ),
        vol.Optional(
          "dashboard_mode",
          default=DEFAULT_DASHBOARD_MODE if has_multiple_dogs else "cards",
        ): selector.SelectSelector(
          selector.SelectSelectorConfig(
            options=DASHBOARD_MODE_SELECTOR_OPTIONS,
            mode=selector.SelectSelectorMode.DROPDOWN,
          ),
        ),
        vol.Optional(
          "show_statistics",
          default=True,
        ): selector.BooleanSelector(),
        vol.Optional(
          "show_maps",
          default=has_gps_enabled,
        ): selector.BooleanSelector(),
      },
    )

    placeholders = _build_dashboard_configure_placeholders(
      dog_count=len(self._dogs),
      dashboard_info=self._get_dashboard_info(hass_language),
      features=self._build_dashboard_features_string(
        hass_language,
        has_gps_enabled,
      ),
    )

    return self.async_show_form(
      step_id="configure_dashboard",
      data_schema=schema,
      description_placeholders=dict(placeholders),
    )

  def _get_dashboard_info(self, language: str | None) -> str:  # noqa: E111
    """Get dashboard information for display."""

    info = [
      _translated_dashboard_info_line(language, "auto_create"),
      _translated_dashboard_info_line(language, "cards"),
      _translated_dashboard_info_line(language, "maps"),
      _translated_dashboard_info_line(language, "responsive"),
    ]

    if len(self._dogs) > 1:
      info.append(  # noqa: E111
        _translated_dashboard_info_line(
          language,
          "multi_dog",
          count=len(self._dogs),
        ),
      )

    return "\n".join(info)

  def _build_dashboard_features_string(  # noqa: E111
    self,
    language: str | None,
    has_gps_enabled: bool,
  ) -> str:
    """Return localized feature highlights for the dashboard wizard."""

    feature_keys = ["status_cards", "activity_tracking", "quick_actions"]

    if has_gps_enabled:
      feature_keys.append("location_maps")  # noqa: E111

    if len(self._dogs) > 1:
      feature_keys.append("multi_dog_overview")  # noqa: E111

    return ", ".join(
      translated_dashboard_feature(language, key) for key in feature_keys
    )


__all__ = ["DashboardFlowMixin"]
