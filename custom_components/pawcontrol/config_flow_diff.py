"""
Minimal erforderliche Änderungen an der bestehenden config_flow.py

Diese Datei zeigt, wie Sie die bestehende OptionsFlowHandler minimal erweitern können,
ohne die gesamte Struktur zu ändern. Fügen Sie diese Methoden zur bestehenden 
OptionsFlowHandler-Klasse hinzu.
"""

# === HINZUFÜGUNGEN FÜR DIE BESTEHENDE OptionsFlowHandler KLASSE ===

# 1. Erweitern Sie das __init__ um neue Variablen:
def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
    """Initialize options flow."""
    self._entry = config_entry
    self._dogs_data: dict[str, Any] = {}
    self._current_dog_index = 0
    self._total_dogs = 0
    self._editing_dog_id: str | None = None
    self._temp_options: dict[str, Any] = {}

# 2. Erweitern Sie das init-Menü:
async def async_step_init(
    self, user_input: dict[str, Any] | None = None
) -> FlowResult:
    """Manage the options with a comprehensive menu."""
    if user_input is not None:
        # Handle direct option updates for backward compatibility
        if "geofencing_enabled" in user_input or "modules" in user_input:
            return self.async_create_entry(title="", data=user_input)

    # ERWEITERTE MENU-OPTIONEN - ersetzen Sie das bestehende menu_options:
    menu_options = {
        "dogs": "Dog Management",  # NEU
        "gps": "GPS & Tracking",   # NEU
        "geofence": "Geofence Settings",
        "notifications": "Notifications", 
        "data_sources": "Data Sources",  # NEU
        "modules": "Feature Modules",
        "system": "System Settings",
        "maintenance": "Maintenance & Backup",  # NEU
    }
    
    return self.async_show_menu(
        step_id="init",
        menu_options=menu_options,
    )

# 3. Neue GPS-Einstellungen Methode hinzufügen:
async def async_step_gps(
    self, user_input: dict[str, Any] | None = None
) -> FlowResult:
    """Configure GPS and tracking settings."""
    if user_input is not None:
        new_options = dict(self._options)
        new_options["gps"] = user_input
        return self.async_create_entry(title="", data=new_options)

    current_gps = self._options.get("gps", {})
    
    schema = vol.Schema({
        vol.Optional(
            "gps_enabled",
            default=current_gps.get("enabled", True),
        ): bool,
        vol.Optional(
            "gps_accuracy_filter",
            default=current_gps.get("accuracy_filter", 100),
        ): vol.All(vol.Coerce(int), vol.Range(min=1, max=1000)),
        vol.Optional(
            "gps_distance_filter",
            default=current_gps.get("distance_filter", 5),
        ): vol.All(vol.Coerce(int), vol.Range(min=1, max=100)),
        vol.Optional(
            "auto_start_walk",
            default=current_gps.get("auto_start_walk", False),
        ): bool,
        vol.Optional(
            "auto_end_walk",
            default=current_gps.get("auto_end_walk", True),
        ): bool,
        vol.Optional(
            "route_recording",
            default=current_gps.get("route_recording", True),
        ): bool,
    })
    
    return self.async_show_form(step_id="gps", data_schema=schema)

# 4. Neue Datenquellen-Methode hinzufügen:
async def async_step_data_sources(
    self, user_input: dict[str, Any] | None = None
) -> FlowResult:
    """Configure data source connections."""
    if user_input is not None:
        new_options = dict(self._options)
        new_options["data_sources"] = user_input
        return self.async_create_entry(title="", data=new_options)

    current_sources = self._options.get("data_sources", {})
    
    # Get available entities for selection
    ent_reg = er.async_get(self.hass)
    
    # Get person entities
    person_entities = [
        entity.entity_id for entity in ent_reg.entities.values()
        if entity.domain == "person"
    ]
    
    # Get device tracker entities
    device_tracker_entities = [
        entity.entity_id for entity in ent_reg.entities.values()
        if entity.domain == "device_tracker"
    ]

    schema = vol.Schema({
        vol.Optional(
            "person_entities",
            default=current_sources.get("person_entities", []),
        ): cv.multi_select(person_entities) if person_entities else cv.multi_select([]),
        vol.Optional(
            "device_trackers",
            default=current_sources.get("device_trackers", []),
        ): cv.multi_select(device_tracker_entities) if device_tracker_entities else cv.multi_select([]),
        vol.Optional(
            "auto_discovery",
            default=current_sources.get("auto_discovery", True),
        ): bool,
    })
    
    return self.async_show_form(step_id="data_sources", data_schema=schema)

# 5. Wartungs-Methode hinzufügen:
async def async_step_maintenance(
    self, user_input: dict[str, Any] | None = None
) -> FlowResult:
    """Configure maintenance and backup options."""
    if user_input is not None:
        if user_input.get("action") == "backup_config":
            return await self._async_backup_configuration()
        elif user_input.get("action") == "cleanup":
            return await self._async_cleanup_data()
        else:
            new_options = dict(self._options)
            new_options["maintenance"] = {
                k: v for k, v in user_input.items() 
                if k != "action"
            }
            return self.async_create_entry(title="", data=new_options)

    current_maintenance = self._options.get("maintenance", {})

    schema = vol.Schema({
        vol.Optional(
            "auto_backup_enabled",
            default=current_maintenance.get("auto_backup_enabled", True),
        ): bool,
        vol.Optional(
            "auto_cleanup_enabled",
            default=current_maintenance.get("auto_cleanup_enabled", True),
        ): bool,
        vol.Optional(
            "action",
            default="save_settings",
        ): vol.In({
            "save_settings": "Save Settings",
            "backup_config": "Backup Configuration Now",
            "cleanup": "Cleanup Old Data",
        }),
    })

    return self.async_show_form(step_id="maintenance", data_schema=schema)

# 6. Backup-Hilfsmethoden hinzufügen:
async def _async_backup_configuration(self) -> FlowResult:
    """Backup current configuration."""
    try:
        import json
        from datetime import datetime
        
        backup_data = {
            "timestamp": datetime.now().isoformat(),
            "version": "1.0",
            "data": self._data,
            "options": self._options,
        }
        
        # Store backup in Home Assistant config directory
        backup_path = self.hass.config.path(
            f"pawcontrol_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        
        with open(backup_path, "w") as f:
            json.dump(backup_data, f, indent=2)
        
        return self.async_show_form(
            step_id="backup_success",
            data_schema=vol.Schema({}),
            description_placeholders={"backup_path": backup_path},
        )
        
    except Exception as err:
        _LOGGER.error("Failed to backup configuration: %s", err)
        return self.async_show_form(
            step_id="backup_error",
            data_schema=vol.Schema({}),
            errors={"base": "backup_failed"},
        )

async def _async_cleanup_data(self) -> FlowResult:
    """Cleanup old data and optimize storage."""
    try:
        # Call cleanup services
        await self.hass.services.async_call(
            DOMAIN,
            "purge_all_storage",
            {"config_entry_id": self._entry.entry_id},
        )
        
        return self.async_show_form(
            step_id="cleanup_success",
            data_schema=vol.Schema({}),
        )
        
    except Exception as err:
        _LOGGER.error("Failed to cleanup data: %s", err)
        return self.async_show_form(
            step_id="cleanup_error", 
            data_schema=vol.Schema({}),
            errors={"base": "cleanup_failed"},
        )

# 7. Erweitern Sie die bestehende notifications-Methode:
async def async_step_notifications(
    self, user_input: dict[str, Any] | None = None
) -> FlowResult:
    """Configure comprehensive notification settings."""
    if user_input is not None:
        new_options = dict(self._options)
        new_options["notifications"] = user_input
        return self.async_create_entry(title="", data=new_options)

    current_notifications = self._options.get("notifications", {})
    
    # ERWEITERTE SCHEMA - bestehende Schema erweitern:
    schema = vol.Schema({
        vol.Optional(
            "notifications_enabled",
            default=current_notifications.get("enabled", True),
        ): bool,
        vol.Optional(
            "quiet_hours_enabled",
            default=current_notifications.get("quiet_hours_enabled", False),
        ): bool,
        vol.Optional(
            "quiet_start",
            default=current_notifications.get("quiet_start", "22:00"),
        ): str,
        vol.Optional(
            "quiet_end",
            default=current_notifications.get("quiet_end", "07:00"),
        ): str,
        vol.Optional(
            "reminder_repeat_min",
            default=current_notifications.get("reminder_repeat_min", 30),
        ): vol.All(vol.Coerce(int), vol.Range(min=5, max=120)),
        # NEUE FELDER:
        vol.Optional(
            "priority_notifications",
            default=current_notifications.get("priority_notifications", True),
        ): bool,
        vol.Optional(
            "summary_notifications",
            default=current_notifications.get("summary_notifications", True),
        ): bool,
        vol.Optional(
            "notification_channels",
            default=current_notifications.get("notification_channels", ["mobile", "persistent"]),
        ): cv.multi_select({
            "mobile": "Mobile App",
            "persistent": "Persistent Notification",
            "email": "Email",
            "slack": "Slack",
        }),
    })
    
    return self.async_show_form(step_id="notifications", data_schema=schema)

# 8. Erweitern Sie die bestehende system-Methode:
async def async_step_system(
    self, user_input: dict[str, Any] | None = None
) -> FlowResult:
    """Configure system settings."""
    if user_input is not None:
        new_options = dict(self._options)
        new_options.update(user_input)
        return self.async_create_entry(title="", data=new_options)

    # ERWEITERTE SCHEMA - bestehende Schema erweitern:
    schema = vol.Schema({
        vol.Optional(
            "reset_time",
            default=self._options.get("reset_time", "23:59:00"),
        ): str,
        vol.Optional(
            "visitor_mode",
            default=self._options.get("visitor_mode", False),
        ): bool,
        vol.Optional(
            "export_format",
            default=self._options.get("export_format", "csv"),
        ): vol.In(["csv", "json", "pdf"]),
        vol.Optional(
            "auto_prune_devices",
            default=self._options.get("auto_prune_devices", True),
        ): bool,
        # NEUE FELDER:
        vol.Optional(
            "performance_mode",
            default=self._options.get("performance_mode", "balanced"),
        ): vol.In(["minimal", "balanced", "full"]),
        vol.Optional(
            "log_level",
            default=self._options.get("log_level", "info"),
        ): vol.In(["debug", "info", "warning", "error"]),
        vol.Optional(
            "data_retention_days",
            default=self._options.get("data_retention_days", 365),
        ): vol.All(vol.Coerce(int), vol.Range(min=30, max=1095)),
    })
    
    return self.async_show_form(step_id="system", data_schema=schema)

# === IMPORTS AM ANFANG DER DATEI HINZUFÜGEN ===

# Fügen Sie diese Imports am Anfang der config_flow.py hinzu:
from homeassistant.helpers import entity_registry as er, device_registry as dr

# === VERWENDUNG ===
"""
Um diese Erweiterungen zu implementieren:

1. Kopieren Sie die bestehende config_flow.py als Backup
2. Fügen Sie die neuen Imports am Anfang hinzu
3. Erweitern Sie das __init__ der OptionsFlowHandler
4. Ersetzen Sie async_step_init mit der erweiterten Version
5. Fügen Sie die neuen Methoden (gps, data_sources, maintenance) hinzu
6. Erweitern Sie die bestehenden Methoden (notifications, system)
7. Fügen Sie die Hilfsmethoden (_async_backup_configuration, etc.) hinzu
8. Aktualisieren Sie die Übersetzungsdateien

Diese minimale Erweiterung bewahrt die bestehende Funktionalität und fügt
schrittweise neue Features hinzu, ohne alles neu zu schreiben.
"""