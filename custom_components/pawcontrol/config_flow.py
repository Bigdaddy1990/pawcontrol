"""Extended config flow with options flow for PawControl integration."""
from __future__ import annotations

import logging
from typing import Any, Dict
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
import homeassistant.helpers.config_validation as cv

from .const import (
    DOMAIN,
    CONF_DOG_NAME,
    CONF_DOG_BREED,
    CONF_DOG_AGE,
    CONF_DOG_WEIGHT,
    CONF_DOG_SIZE,
    CONF_DOGS,
    CONF_MODULES,
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_NOTIFICATIONS,
    MODULE_AUTOMATION,
    MODULE_DASHBOARD,
    MODULE_WALK,
    MODULE_TRAINING,
    MODULE_GROOMING,
    MODULE_VISITOR,
    MODULE_NAMES,
    SIZE_OPTIONS,
    HEALTH_STATUS_OPTIONS,
    MOOD_OPTIONS,
    ACTIVITY_LEVELS,
    MIN_DOG_NAME_LENGTH,
    MAX_DOG_NAME_LENGTH,
    MIN_DOG_AGE,
    MAX_DOG_AGE,
    MIN_DOG_WEIGHT,
    MAX_DOG_WEIGHT,
)

_LOGGER = logging.getLogger(__name__)


class PawControlConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for PawControl."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._dogs: list[dict[str, Any]] = []
        self._current_dog: dict[str, Any] = {}
        self._current_modules: dict[str, Any] = {}
        
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        
        if user_input is not None:
            # Start with first dog configuration
            return await self.async_step_dog_basic()
        
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({}),
            description_placeholders={
                "info": "Willkommen bei PawControl! Lassen Sie uns Ihren Hund einrichten."
            },
        )

    async def async_step_dog_basic(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure basic dog information."""
        errors: dict[str, str] = {}
        
        if user_input is not None:
            # Validate dog name
            dog_name = user_input.get(CONF_DOG_NAME, "").strip()
            if len(dog_name) < MIN_DOG_NAME_LENGTH or len(dog_name) > MAX_DOG_NAME_LENGTH:
                errors[CONF_DOG_NAME] = "invalid_name"
            elif self._dog_name_exists(dog_name):
                errors[CONF_DOG_NAME] = "name_exists"
            
            if not errors:
                self._current_dog = user_input
                # Automatically suggest size based on weight if provided
                if CONF_DOG_WEIGHT in user_input and CONF_DOG_SIZE not in user_input:
                    weight = user_input[CONF_DOG_WEIGHT]
                    self._current_dog[CONF_DOG_SIZE] = self._suggest_size_by_weight(weight)
                
                return await self.async_step_modules()
        
        schema = vol.Schema(
            {
                vol.Required(CONF_DOG_NAME): selector.TextSelector(
                    selector.TextSelectorConfig(
                        multiline=False,
                        type=selector.TextSelectorType.TEXT,
                    )
                ),
                vol.Optional(CONF_DOG_BREED): selector.TextSelector(
                    selector.TextSelectorConfig(
                        multiline=False,
                        type=selector.TextSelectorType.TEXT,
                    )
                ),
                vol.Optional(CONF_DOG_AGE, default=2.0): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=MIN_DOG_AGE,
                        max=MAX_DOG_AGE,
                        step=0.1,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="Jahre",
                    )
                ),
                vol.Optional(CONF_DOG_WEIGHT, default=15.0): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=MIN_DOG_WEIGHT,
                        max=MAX_DOG_WEIGHT,
                        step=0.1,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="kg",
                    )
                ),
                vol.Optional(CONF_DOG_SIZE, default=SIZE_OPTIONS[2]): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=SIZE_OPTIONS,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional("health_status", default=HEALTH_STATUS_OPTIONS[2]): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=HEALTH_STATUS_OPTIONS,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional("mood", default=MOOD_OPTIONS[0]): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=MOOD_OPTIONS,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional("activity_level", default=ACTIVITY_LEVELS[2]): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=ACTIVITY_LEVELS,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )
        
        return self.async_show_form(
            step_id="dog_basic",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "title": "Grundlegende Hundedaten",
                "info": "Bitte geben Sie die Grunddaten Ihres Hundes ein.",
            },
        )

    async def async_step_modules(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Select which modules to enable."""
        errors: dict[str, str] = {}
        
        if user_input is not None:
            # Store selected modules
            self._current_modules = {}
            for module_id, enabled in user_input.items():
                if enabled:
                    self._current_modules[module_id] = {"enabled": True}
            
            # Continue with module-specific configuration
            return await self.async_step_module_config()
        
        # Create schema for module selection
        schema_dict = {}
        for module_id in [MODULE_FEEDING, MODULE_WALK, MODULE_HEALTH, MODULE_GPS, 
                         MODULE_NOTIFICATIONS, MODULE_DASHBOARD]:
            default = module_id in [MODULE_FEEDING, MODULE_WALK, MODULE_DASHBOARD]
            schema_dict[vol.Optional(module_id, default=default)] = selector.BooleanSelector()
        
        return self.async_show_form(
            step_id="modules",
            data_schema=vol.Schema(schema_dict),
            errors=errors,
            description_placeholders={
                "dog_name": self._current_dog.get(CONF_DOG_NAME, "")
            },
        )

    async def async_step_module_config(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure specific module settings."""
        # For now, skip detailed module configuration
        # This can be expanded later for each module
        
        # Add dog to list
        self._current_dog[CONF_MODULES] = self._current_modules
        self._dogs.append(self._current_dog)
        
        return await self.async_step_add_another()

    async def async_step_add_another(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Ask if user wants to add another dog."""
        if user_input is not None:
            if user_input.get("add_another"):
                # Reset current dog and modules
                self._current_dog = {}
                self._current_modules = {}
                return await self.async_step_dog_basic()
            else:
                # Finish configuration
                return self._create_entry()
        
        return self.async_show_form(
            step_id="add_another",
            data_schema=vol.Schema(
                {
                    vol.Required("add_another", default=False): selector.BooleanSelector(),
                }
            ),
            description_placeholders={
                "dog_name": self._current_dog.get(CONF_DOG_NAME, "")
            },
        )

    @callback
    def _create_entry(self) -> FlowResult:
        """Create the config entry."""
        title = "PawControl"
        if len(self._dogs) == 1:
            title = f"PawControl - {self._dogs[0].get(CONF_DOG_NAME)}"
        elif len(self._dogs) > 1:
            names = [dog.get(CONF_DOG_NAME) for dog in self._dogs]
            title = f"PawControl - {', '.join(names)}"
        
        return self.async_create_entry(
            title=title,
            data={
                CONF_DOGS: self._dogs,
            },
        )

    def _dog_name_exists(self, name: str) -> bool:
        """Check if a dog name already exists."""
        for dog in self._dogs:
            if dog.get(CONF_DOG_NAME) == name:
                return True
        return False

    def _suggest_size_by_weight(self, weight: float) -> str:
        """Suggest size category based on weight."""
        if weight < 5:
            return SIZE_OPTIONS[0]  # Toy
        elif weight < 10:
            return SIZE_OPTIONS[1]  # Klein
        elif weight < 25:
            return SIZE_OPTIONS[2]  # Mittel
        elif weight < 45:
            return SIZE_OPTIONS[3]  # Groß
        else:
            return SIZE_OPTIONS[4]  # Riesig

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return PawControlOptionsFlow(config_entry)


class PawControlOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for PawControl."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        super().__init__(config_entry)
        self._dogs = config_entry.data.get(CONF_DOGS, [])
        self._selected_dog: Dict[str, Any] = {}
        self._selected_dog_index: int = -1
        self._action: str = ""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            self._action = user_input.get("action", "")
            
            if self._action == "edit_dog":
                return await self.async_step_select_dog()
            elif self._action == "add_dog":
                return await self.async_step_add_dog()
            elif self._action == "remove_dog":
                return await self.async_step_select_dog_remove()
            elif self._action == "manage_modules":
                return await self.async_step_select_dog_modules()
            else:
                return self.async_create_entry(title="", data={})
        
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required("action", default="edit_dog"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {"value": "edit_dog", "label": "Hund bearbeiten"},
                            {"value": "add_dog", "label": "Hund hinzufügen"},
                            {"value": "remove_dog", "label": "Hund entfernen"},
                            {"value": "manage_modules", "label": "Module verwalten"},
                        ],
                        mode=selector.SelectSelectorMode.LIST,
                    )
                ),
            }),
            description_placeholders={
                "info": f"Sie haben {len(self._dogs)} Hund(e) konfiguriert. Was möchten Sie tun?",
            },
        )

    async def async_step_select_dog(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Select a dog to edit."""
        if user_input is not None:
            dog_name = user_input.get("dog_name")
            for i, dog in enumerate(self._dogs):
                if dog.get(CONF_DOG_NAME) == dog_name:
                    self._selected_dog = dog
                    self._selected_dog_index = i
                    return await self.async_step_edit_dog()
        
        dog_names = [dog.get(CONF_DOG_NAME) for dog in self._dogs]
        
        return self.async_show_form(
            step_id="select_dog",
            data_schema=vol.Schema({
                vol.Required("dog_name"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=dog_names,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }),
            description_placeholders={
                "info": "Wählen Sie den Hund aus, den Sie bearbeiten möchten.",
            },
        )

    async def async_step_edit_dog(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Edit selected dog."""
        if user_input is not None:
            # Update dog configuration
            self._selected_dog.update(user_input)
            self._dogs[self._selected_dog_index] = self._selected_dog
            
            # Update config entry
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data={CONF_DOGS: self._dogs}
            )
            
            return self.async_create_entry(title="", data={})
        
        # Pre-fill with current values
        schema = vol.Schema({
            vol.Required(CONF_DOG_NAME, default=self._selected_dog.get(CONF_DOG_NAME, "")): str,
            vol.Optional(CONF_DOG_BREED, default=self._selected_dog.get(CONF_DOG_BREED, "")): str,
            vol.Optional(CONF_DOG_AGE, default=self._selected_dog.get(CONF_DOG_AGE, 0)): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=MIN_DOG_AGE,
                    max=MAX_DOG_AGE,
                    step=0.1,
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Optional(CONF_DOG_WEIGHT, default=self._selected_dog.get(CONF_DOG_WEIGHT, 0)): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=MIN_DOG_WEIGHT,
                    max=MAX_DOG_WEIGHT,
                    step=0.1,
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Optional(CONF_DOG_SIZE, default=self._selected_dog.get(CONF_DOG_SIZE, SIZE_OPTIONS[2])): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=SIZE_OPTIONS,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
        })
        
        return self.async_show_form(
            step_id="edit_dog",
            data_schema=schema,
            description_placeholders={
                "info": f"Bearbeiten Sie die Daten von {self._selected_dog.get(CONF_DOG_NAME)}",
            },
        )

    async def async_step_select_dog_remove(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Select a dog to remove."""
        if user_input is not None:
            dog_name = user_input.get("dog_name")
            
            # Remove the dog
            self._dogs = [dog for dog in self._dogs if dog.get(CONF_DOG_NAME) != dog_name]
            
            # Update config entry
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data={CONF_DOGS: self._dogs}
            )
            
            # Trigger cleanup in the integration
            await self.hass.config_entries.async_reload(self.config_entry.entry_id)
            
            return self.async_create_entry(title="", data={})
        
        dog_names = [dog.get(CONF_DOG_NAME) for dog in self._dogs]
        
        return self.async_show_form(
            step_id="select_dog_remove",
            data_schema=vol.Schema({
                vol.Required("dog_name"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=dog_names,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }),
            description_placeholders={
                "info": "⚠️ Wählen Sie den Hund aus, den Sie entfernen möchten. Alle Daten werden gelöscht!",
            },
        )

    async def async_step_select_dog_modules(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Select a dog to manage modules."""
        if user_input is not None:
            dog_name = user_input.get("dog_name")
            for i, dog in enumerate(self._dogs):
                if dog.get(CONF_DOG_NAME) == dog_name:
                    self._selected_dog = dog
                    self._selected_dog_index = i
                    return await self.async_step_manage_modules()
        
        dog_names = [dog.get(CONF_DOG_NAME) for dog in self._dogs]
        
        return self.async_show_form(
            step_id="select_dog_modules",
            data_schema=vol.Schema({
                vol.Required("dog_name"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=dog_names,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }),
            description_placeholders={
                "info": "Wählen Sie den Hund aus, dessen Module Sie verwalten möchten.",
            },
        )

    async def async_step_manage_modules(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage modules for selected dog."""
        if user_input is not None:
            # Update module configuration
            modules = {}
            for module_id, enabled in user_input.items():
                modules[module_id] = {"enabled": enabled}
            
            self._selected_dog[CONF_MODULES] = modules
            self._dogs[self._selected_dog_index] = self._selected_dog
            
            # Update config entry
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data={CONF_DOGS: self._dogs}
            )
            
            # Reload to apply changes
            await self.hass.config_entries.async_reload(self.config_entry.entry_id)
            
            return self.async_create_entry(title="", data={})
        
        # Get current module status
        current_modules = self._selected_dog.get(CONF_MODULES, {})
        
        # Create schema with current values
        schema_dict = {}
        for module_id in [
            MODULE_FEEDING, MODULE_WALK, MODULE_HEALTH, MODULE_GPS,
            MODULE_TRAINING, MODULE_GROOMING, MODULE_VISITOR,
            MODULE_NOTIFICATIONS, MODULE_AUTOMATION, MODULE_DASHBOARD
        ]:
            current = current_modules.get(module_id, {}).get("enabled", False)
            schema_dict[vol.Optional(module_id, default=current)] = selector.BooleanSelector()
        
        return self.async_show_form(
            step_id="manage_modules",
            data_schema=vol.Schema(schema_dict),
            description_placeholders={
                "info": f"Module für {self._selected_dog.get(CONF_DOG_NAME)} verwalten",
                MODULE_FEEDING: MODULE_NAMES[MODULE_FEEDING],
                MODULE_WALK: MODULE_NAMES[MODULE_WALK],
                MODULE_HEALTH: MODULE_NAMES[MODULE_HEALTH],
                MODULE_GPS: MODULE_NAMES[MODULE_GPS],
                MODULE_TRAINING: MODULE_NAMES[MODULE_TRAINING],
                MODULE_GROOMING: MODULE_NAMES[MODULE_GROOMING],
                MODULE_VISITOR: MODULE_NAMES[MODULE_VISITOR],
                MODULE_NOTIFICATIONS: MODULE_NAMES[MODULE_NOTIFICATIONS],
                MODULE_AUTOMATION: MODULE_NAMES[MODULE_AUTOMATION],
                MODULE_DASHBOARD: MODULE_NAMES[MODULE_DASHBOARD],
            },
        )

    async def async_step_add_dog(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Add a new dog."""
        if user_input is not None:
            # Add new dog to list
            new_dog = user_input
            new_dog[CONF_MODULES] = {
                MODULE_FEEDING: {"enabled": True},
                MODULE_WALK: {"enabled": True},
                MODULE_DASHBOARD: {"enabled": True},
            }
            
            self._dogs.append(new_dog)
            
            # Update config entry
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data={CONF_DOGS: self._dogs}
            )
            
            # Reload to apply changes
            await self.hass.config_entries.async_reload(self.config_entry.entry_id)
            
            return self.async_create_entry(title="", data={})
        
        schema = vol.Schema({
            vol.Required(CONF_DOG_NAME): str,
            vol.Optional(CONF_DOG_BREED): str,
            vol.Optional(CONF_DOG_AGE, default=2.0): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=MIN_DOG_AGE,
                    max=MAX_DOG_AGE,
                    step=0.1,
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Optional(CONF_DOG_WEIGHT, default=15.0): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=MIN_DOG_WEIGHT,
                    max=MAX_DOG_WEIGHT,
                    step=0.1,
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Optional(CONF_DOG_SIZE, default=SIZE_OPTIONS[2]): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=SIZE_OPTIONS,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
        })
        
        return self.async_show_form(
            step_id="add_dog",
            data_schema=schema,
            description_placeholders={
                "info": "Fügen Sie einen neuen Hund hinzu",
            },
        )
