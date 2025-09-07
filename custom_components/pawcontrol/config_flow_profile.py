"""Profile configuration integration for PawControl config flow.

Updates config_flow.py to include entity profile selection.
Reduces entity count from 54+ to 8-18 per dog based on user needs.
"""

# Add to config_flow.py - Profile selection step

ENTITY_PROFILES = {
    "basic": "Essential monitoring only (8 entities)",
    "standard": "Balanced monitoring with GPS (12 entities)", 
    "advanced": "Comprehensive monitoring (18 entities)",
    "gps_focus": "GPS tracking focused (10 entities)",
    "health_focus": "Health monitoring focused (10 entities)",
}

async def async_step_entity_profile(self, user_input=None):
    """Handle entity profile selection."""
    if user_input is not None:
        self._config_data["entity_profile"] = user_input["entity_profile"]
        return await self.async_step_final()

    return self.async_show_form(
        step_id="entity_profile",
        data_schema=vol.Schema({
            vol.Required("entity_profile", default="standard"): vol.In(ENTITY_PROFILES)
        }),
        description_placeholders={
            "profile_info": "Choose entity profile to optimize performance",
        }
    )
