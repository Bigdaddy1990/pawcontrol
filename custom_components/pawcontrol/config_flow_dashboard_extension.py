"""Dashboard Configuration Extension for Paw Control Config Flow.

This module extends the config flow with dashboard-specific configuration steps.
To be integrated into config_flow.py.

Quality Scale: Platinum
Home Assistant: 2025.8.2+
Python: 3.13+
"""

# Add this method to PawControlConfigFlow class:

async def async_step_configure_dashboard(
    self, user_input: dict[str, Any] | None = None
) -> ConfigFlowResult:
    """Configure dashboard settings.
    
    This step allows users to configure how the dashboard should be created
    and displayed, including per-dog dashboards and theme selection.
    
    Args:
        user_input: Dashboard configuration choices
        
    Returns:
        Configuration flow result for next step
    """
    if user_input is not None:
        # Store dashboard configuration
        self._dashboard_config = {
            CONF_DASHBOARD_ENABLED: True,
            CONF_DASHBOARD_AUTO_CREATE: user_input.get("auto_create_dashboard", True),
            CONF_DASHBOARD_PER_DOG: user_input.get("create_per_dog_dashboards", False),
            CONF_DASHBOARD_THEME: user_input.get("dashboard_theme", "default"),
            CONF_DASHBOARD_MODE: user_input.get("dashboard_mode", "full"),
            "show_statistics": user_input.get("show_statistics", True),
            "show_maps": user_input.get("show_maps", True),
        }
        
        # Continue to GPS configuration if enabled
        if self._enabled_modules.get("gps", False):
            return await self.async_step_configure_external_entities()
        else:
            return await self.async_step_final_setup()
    
    # Determine default values based on dog count
    has_multiple_dogs = len(self._dogs) > 1
    has_gps = self._enabled_modules.get("gps", False)
    
    schema = vol.Schema({
        vol.Optional(
            "auto_create_dashboard", default=True
        ): selector.BooleanSelector(),
        vol.Optional(
            "create_per_dog_dashboards", default=has_multiple_dogs
        ): selector.BooleanSelector(),
        vol.Optional(
            "dashboard_theme", default="default"
        ): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[
                    {"value": "default", "label": "Default - Clean and modern"},
                    {"value": "dark", "label": "Dark - Night-friendly theme"},
                    {"value": "playful", "label": "Playful - Colorful and fun"},
                ],
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        ),
        vol.Optional(
            "dashboard_mode", default="full" if has_multiple_dogs else "cards"
        ): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[
                    {"value": "full", "label": "Full - Complete dashboard with all features"},
                    {"value": "cards", "label": "Cards - Organized card-based layout"},
                    {"value": "minimal", "label": "Minimal - Essential information only"},
                ],
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        ),
        vol.Optional(
            "show_statistics", default=True
        ): selector.BooleanSelector(),
        vol.Optional(
            "show_maps", default=has_gps
        ): selector.BooleanSelector(),
    })
    
    return self.async_show_form(
        step_id="configure_dashboard",
        data_schema=schema,
        description_placeholders={
            "dog_count": len(self._dogs),
            "dashboard_info": self._get_dashboard_info(),
        },
    )

def _get_dashboard_info(self) -> str:
    """Get dashboard information for display.
    
    Returns:
        Formatted dashboard information string
    """
    info = [
        "🎨 The dashboard will be automatically created after setup",
        "📊 It will include cards for each dog and their activities",
        "🗺️ GPS maps will be shown if GPS module is enabled",
        "📱 Dashboards are mobile-friendly and responsive",
    ]
    
    if len(self._dogs) > 1:
        info.append(f"🐕 Individual dashboards for {len(self._dogs)} dogs recommended")
    
    return "\n".join(info)

# Update the async_step_configure_modules to include dashboard configuration:
# Add this after line where dashboard_enabled is set:
dashboard_enabled = user_input.get("enable_dashboard", True)

# Update the module configuration loop to include dashboard:
dog[CONF_MODULES][MODULE_DASHBOARD] = dashboard_enabled

# Add dashboard option to the schema in async_step_configure_modules:
vol.Optional(
    "enable_dashboard", default=True
): selector.BooleanSelector(),

# Update the async_step_final_setup to include dashboard config:
# Add dashboard configuration to options_data:
if hasattr(self, "_dashboard_config"):
    options_data.update(self._dashboard_config)

# Add these imports to config_flow.py if not already present:
from .const import (
    CONF_DASHBOARD_AUTO_CREATE,
    CONF_DASHBOARD_ENABLED,
    CONF_DASHBOARD_MODE,
    CONF_DASHBOARD_PER_DOG,
    CONF_DASHBOARD_THEME,
    DEFAULT_DASHBOARD_AUTO_CREATE,
    DEFAULT_DASHBOARD_ENABLED,
    DEFAULT_DASHBOARD_MODE,
    DEFAULT_DASHBOARD_THEME,
)
