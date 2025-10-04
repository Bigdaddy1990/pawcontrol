"""Repairs support for Paw Control integration.

This module provides automated issue detection and user-guided repair flows
for common configuration and setup problems. It helps users resolve issues
independently and maintains system health. Designed to meet Home Assistant's
Platinum quality standards.
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.components.repairs import RepairsFlow
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.selector import selector
from homeassistant.util import dt as dt_util

from .const import (
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOGS,
    DOMAIN,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_NOTIFICATIONS,
)
from .runtime_data import get_runtime_data

_LOGGER = logging.getLogger(__name__)

# JSON serialisable payload used for issue registry metadata
type JSONPrimitive = str | int | float | bool | None
type JSONType = JSONPrimitive | list["JSONType"] | dict[str, "JSONType"]

# Issue types
ISSUE_MISSING_DOG_CONFIG = "missing_dog_configuration"
ISSUE_DUPLICATE_DOG_IDS = "duplicate_dog_ids"
ISSUE_INVALID_GPS_CONFIG = "invalid_gps_configuration"
ISSUE_MISSING_NOTIFICATIONS = "missing_notification_config"
ISSUE_OUTDATED_CONFIG = "outdated_configuration"
ISSUE_PERFORMANCE_WARNING = "performance_warning"
ISSUE_GPS_UPDATE_INTERVAL = "gps_update_interval_warning"
ISSUE_STORAGE_WARNING = "storage_warning"
ISSUE_MODULE_CONFLICT = "module_configuration_conflict"
ISSUE_INVALID_DOG_DATA = "invalid_dog_data"
ISSUE_COORDINATOR_ERROR = "coordinator_error"

# Repair flow types
REPAIR_FLOW_DOG_CONFIG = "repair_dog_configuration"
REPAIR_FLOW_GPS_SETUP = "repair_gps_setup"
REPAIR_FLOW_NOTIFICATION_SETUP = "repair_notification_setup"
REPAIR_FLOW_CONFIG_MIGRATION = "repair_config_migration"
REPAIR_FLOW_PERFORMANCE_OPTIMIZATION = "repair_performance_optimization"


def _normalise_issue_severity(
    severity: str | ir.IssueSeverity,
) -> ir.IssueSeverity:
    """Return a valid ``IssueSeverity`` for the provided ``severity`` value."""

    if isinstance(severity, ir.IssueSeverity):
        return severity

    if isinstance(severity, str):
        try:
            return ir.IssueSeverity(severity.lower())
        except ValueError:
            _LOGGER.warning(
                "Unsupported issue severity '%s'; falling back to warning.", severity
            )
            return ir.IssueSeverity.WARNING

    _LOGGER.warning(
        "Unexpected issue severity type %s; falling back to warning.",
        type(severity).__name__,
    )
    return ir.IssueSeverity.WARNING


async def async_create_issue(
    hass: HomeAssistant,
    entry: ConfigEntry,
    issue_id: str,
    issue_type: str,
    data: dict[str, Any] | None = None,
    severity: str | ir.IssueSeverity = ir.IssueSeverity.WARNING,
) -> None:
    """Create a repair issue for the integration.

    Args:
        hass: Home Assistant instance
        entry: Configuration entry
        issue_id: Unique issue identifier
        issue_type: Type of issue
        data: Additional issue data
        severity: Issue severity (``IssueSeverity`` or string such as ``"warning"``)
    """
    issue_severity = _normalise_issue_severity(severity)

    issue_data = {
        "config_entry_id": entry.entry_id,
        "issue_type": issue_type,
        "created_at": dt_util.utcnow().isoformat(),
        "severity": issue_severity.value,
    }

    if data:
        issue_data.update(data)

    def _serialise_issue_value(value: Any) -> JSONType:
        """Serialise issue metadata to JSON-compatible structures."""

        if value is None or isinstance(value, str | int | float | bool):
            return value

        if isinstance(value, list | tuple | set):
            return [_serialise_issue_value(item) for item in value]

        if isinstance(value, dict):
            return {
                str(key): _serialise_issue_value(item) for key, item in value.items()
            }

        return str(value)

    def _stringify_placeholder(value: JSONType) -> str:
        """Convert serialised metadata into user-friendly placeholder text."""

        if isinstance(value, list):
            return ", ".join(_stringify_placeholder(item) for item in value)

        if isinstance(value, dict):
            return ", ".join(
                f"{key}={_stringify_placeholder(item)}" for key, item in value.items()
            )

        return str(value)

    serialised_issue_data: dict[str, JSONType] = {
        key: _serialise_issue_value(value) for key, value in issue_data.items()
    }

    translation_placeholders = {
        key: _stringify_placeholder(value)
        for key, value in serialised_issue_data.items()
        if value is not None
    }

    await ir.async_create_issue(
        hass,
        DOMAIN,
        issue_id,
        breaks_in_ha_version=None,
        is_fixable=True,
        issue_domain=DOMAIN,
        severity=issue_severity,
        translation_key=issue_type,
        translation_placeholders=translation_placeholders,
        data=serialised_issue_data,
    )

    _LOGGER.info("Created repair issue: %s (%s)", issue_id, issue_type)


async def async_check_for_issues(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Check for common issues and create repair flows if needed.

    This function performs comprehensive health checks and identifies
    potential configuration or operational issues that require user attention.

    Args:
        hass: Home Assistant instance
        entry: Configuration entry to check
    """
    _LOGGER.debug("Checking for issues in Paw Control entry: %s", entry.entry_id)

    try:
        # Check dog configuration issues
        await _check_dog_configuration_issues(hass, entry)

        # Check GPS configuration issues
        await _check_gps_configuration_issues(hass, entry)

        # Check notification configuration issues
        await _check_notification_configuration_issues(hass, entry)

        # Check for outdated configuration
        await _check_outdated_configuration(hass, entry)

        # Check performance issues
        await _check_performance_issues(hass, entry)

        # Check storage issues
        await _check_storage_issues(hass, entry)

        # Check coordinator health
        await _check_coordinator_health(hass, entry)

        _LOGGER.debug("Issue check completed for entry: %s", entry.entry_id)

    except Exception as err:
        _LOGGER.error("Error during issue check for entry %s: %s", entry.entry_id, err)


async def _check_dog_configuration_issues(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Check for dog configuration issues.

    Args:
        hass: Home Assistant instance
        entry: Configuration entry
    """
    dogs = entry.data.get(CONF_DOGS, [])

    # Check for empty dog configuration
    if not dogs:
        await async_create_issue(
            hass,
            entry,
            f"{entry.entry_id}_no_dogs",
            ISSUE_MISSING_DOG_CONFIG,
            {"dogs_count": 0},
            severity="error",
        )
        return

    # Check for duplicate dog IDs
    dog_ids = [dog.get(CONF_DOG_ID) for dog in dogs]
    duplicate_ids = [dog_id for dog_id in set(dog_ids) if dog_ids.count(dog_id) > 1]

    if duplicate_ids:
        await async_create_issue(
            hass,
            entry,
            f"{entry.entry_id}_duplicate_dogs",
            ISSUE_DUPLICATE_DOG_IDS,
            {
                "duplicate_ids": duplicate_ids,
                "total_dogs": len(dogs),
            },
            severity="error",
        )

    # Check for invalid dog data
    invalid_dogs = []
    for dog in dogs:
        if not dog.get(CONF_DOG_ID) or not dog.get(CONF_DOG_NAME):
            invalid_dogs.append(dog.get(CONF_DOG_ID, "unknown"))  # noqa: PERF401

    if invalid_dogs:
        await async_create_issue(
            hass,
            entry,
            f"{entry.entry_id}_invalid_dogs",
            ISSUE_INVALID_DOG_DATA,
            {
                "invalid_dogs": invalid_dogs,
                "total_dogs": len(dogs),
            },
            severity="error",
        )


async def _check_gps_configuration_issues(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Check for GPS configuration issues.

    Args:
        hass: Home Assistant instance
        entry: Configuration entry
    """
    dogs = entry.data.get(CONF_DOGS, [])
    gps_enabled_dogs = [
        dog for dog in dogs if dog.get("modules", {}).get(MODULE_GPS, False)
    ]

    if not gps_enabled_dogs:
        return  # No GPS configuration to check

    # Check if GPS sources are properly configured
    gps_config = entry.options.get("gps", {})

    # Check for missing GPS source configuration
    if not gps_config.get("gps_source"):
        await async_create_issue(
            hass,
            entry,
            f"{entry.entry_id}_missing_gps_source",
            ISSUE_INVALID_GPS_CONFIG,
            {
                "issue": "missing_gps_source",
                "gps_enabled_dogs": len(gps_enabled_dogs),
            },
            severity="warning",
        )

    # Check for unrealistic GPS update intervals
    update_interval = gps_config.get("gps_update_interval", 60)
    if update_interval < 10:  # Less than 10 seconds
        await async_create_issue(
            hass,
            entry,
            f"{entry.entry_id}_gps_update_too_frequent",
            ISSUE_GPS_UPDATE_INTERVAL,
            {
                "current_interval": update_interval,
                "recommended_interval": 30,
            },
            severity="info",
        )


async def _check_notification_configuration_issues(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Check for notification configuration issues.

    Args:
        hass: Home Assistant instance
        entry: Configuration entry
    """
    dogs = entry.data.get(CONF_DOGS, [])
    notification_enabled_dogs = [
        dog for dog in dogs if dog.get("modules", {}).get(MODULE_NOTIFICATIONS, False)
    ]

    if not notification_enabled_dogs:
        return  # No notification configuration to check

    # Check if notification services are available
    notification_config = entry.options.get("notifications", {})

    # Check for mobile app availability
    mobile_enabled = notification_config.get("mobile_notifications", True)
    if mobile_enabled and not hass.services.has_service("notify", "mobile_app"):
        await async_create_issue(
            hass,
            entry,
            f"{entry.entry_id}_mobile_app_missing",
            ISSUE_MISSING_NOTIFICATIONS,
            {
                "missing_service": "mobile_app",
                "notification_enabled_dogs": len(notification_enabled_dogs),
            },
            severity="warning",
        )


async def _check_outdated_configuration(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Check for outdated configuration that needs migration.

    Args:
        hass: Home Assistant instance
        entry: Configuration entry
    """
    # Check config entry version
    if entry.version < 1:  # Current version is 1
        await async_create_issue(
            hass,
            entry,
            f"{entry.entry_id}_outdated_config",
            ISSUE_OUTDATED_CONFIG,
            {
                "current_version": entry.version,
                "required_version": 1,
            },
            severity="info",
        )


async def _check_performance_issues(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Check for performance-related issues.

    Args:
        hass: Home Assistant instance
        entry: Configuration entry
    """
    dogs = entry.data.get(CONF_DOGS, [])

    # Check for too many dogs (performance warning)
    if len(dogs) > 10:
        await async_create_issue(
            hass,
            entry,
            f"{entry.entry_id}_too_many_dogs",
            ISSUE_PERFORMANCE_WARNING,
            {
                "dog_count": len(dogs),
                "recommended_max": 10,
                "suggestion": "Consider performance mode optimization",
            },
            severity="info",
        )

    # Check for conflicting module configurations
    high_resource_modules = [MODULE_GPS, MODULE_HEALTH]
    dogs_with_all_modules = [
        dog
        for dog in dogs
        if all(
            dog.get("modules", {}).get(module, False)
            for module in high_resource_modules
        )
    ]

    if len(dogs_with_all_modules) > 5:
        await async_create_issue(
            hass,
            entry,
            f"{entry.entry_id}_resource_intensive_config",
            ISSUE_MODULE_CONFLICT,
            {
                "intensive_dogs": len(dogs_with_all_modules),
                "total_dogs": len(dogs),
                "suggestion": "Consider selective module enabling",
            },
            severity="info",
        )


async def _check_storage_issues(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Check for storage-related issues.

    Args:
        hass: Home Assistant instance
        entry: Configuration entry
    """
    # Check data retention settings
    retention_days = entry.options.get("data_retention_days", 90)

    if retention_days > 365:  # More than 1 year
        await async_create_issue(
            hass,
            entry,
            f"{entry.entry_id}_high_storage_retention",
            ISSUE_STORAGE_WARNING,
            {
                "current_retention": retention_days,
                "recommended_max": 365,
                "suggestion": "Consider reducing data retention period",
            },
            severity="info",
        )


async def _check_coordinator_health(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Check coordinator health and functionality.

    Args:
        hass: Home Assistant instance
        entry: Configuration entry
    """
    try:
        runtime_data = get_runtime_data(hass, entry)
        if runtime_data is None:
            await async_create_issue(
                hass,
                entry,
                f"{entry.entry_id}_coordinator_missing",
                ISSUE_COORDINATOR_ERROR,
                {
                    "error": "coordinator_not_initialized",
                    "suggestion": "Try reloading the integration",
                },
                severity="error",
            )
            return

        coordinator = runtime_data.coordinator

        if not getattr(coordinator, "last_update_success", True):
            last_update_time = getattr(coordinator, "last_update_time", None)
            await async_create_issue(
                hass,
                entry,
                f"{entry.entry_id}_coordinator_failed",
                ISSUE_COORDINATOR_ERROR,
                {
                    "error": "last_update_failed",
                    "last_update": last_update_time.isoformat()
                    if last_update_time
                    else None,
                    "suggestion": "Check logs for detailed error information",
                },
                severity="warning",
            )

    except Exception as err:
        _LOGGER.error("Error checking coordinator health: %s", err)


class PawControlRepairsFlow(RepairsFlow):
    """Handle repair flows for Paw Control integration."""

    def __init__(self) -> None:
        """Initialize the repair flow."""
        super().__init__()
        self._issue_data: dict[str, Any] = {}
        self._repair_type: str = ""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step of a repair flow.

        Args:
            user_input: User provided data

        Returns:
            Flow result for next step or completion
        """
        self._issue_data = self.hass.data[ir.DOMAIN][self.issue_id].data
        self._repair_type = self._issue_data.get("issue_type", "")

        # Route to appropriate repair flow based on issue type
        if self._repair_type == ISSUE_MISSING_DOG_CONFIG:
            return await self.async_step_missing_dog_config()
        elif self._repair_type == ISSUE_DUPLICATE_DOG_IDS:
            return await self.async_step_duplicate_dog_ids()
        elif self._repair_type == ISSUE_INVALID_GPS_CONFIG:
            return await self.async_step_invalid_gps_config()
        elif self._repair_type == ISSUE_MISSING_NOTIFICATIONS:
            return await self.async_step_missing_notifications()
        elif self._repair_type == ISSUE_OUTDATED_CONFIG:
            return await self.async_step_outdated_config()
        elif self._repair_type in {
            ISSUE_PERFORMANCE_WARNING,
            ISSUE_GPS_UPDATE_INTERVAL,
        }:
            return await self.async_step_performance_warning()
        elif self._repair_type == ISSUE_STORAGE_WARNING:
            return await self.async_step_storage_warning()
        elif self._repair_type == ISSUE_MODULE_CONFLICT:
            return await self.async_step_module_conflict()
        elif self._repair_type == ISSUE_INVALID_DOG_DATA:
            return await self.async_step_invalid_dog_data()
        elif self._repair_type == ISSUE_COORDINATOR_ERROR:
            return await self.async_step_coordinator_error()
        else:
            return await self.async_step_unknown_issue()

    async def async_step_missing_dog_config(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle repair flow for missing dog configuration.

        Args:
            user_input: User provided data

        Returns:
            Flow result for next step or completion
        """
        if user_input is not None:
            action = user_input.get("action")

            if action == "add_dog":
                return await self.async_step_add_first_dog()
            elif action == "reconfigure":
                # Redirect to reconfigure flow
                return self.async_external_step(
                    step_id="reconfigure", url="/config/integrations"
                )
            else:
                return await self.async_step_complete_repair()

        return self.async_show_form(
            step_id="missing_dog_config",
            data_schema=vol.Schema(
                {
                    vol.Required("action"): selector(
                        {
                            "select": {
                                "options": [
                                    {"value": "add_dog", "label": "Add a dog now"},
                                    {
                                        "value": "reconfigure",
                                        "label": "Go to integration settings",
                                    },
                                    {"value": "ignore", "label": "Ignore for now"},
                                ]
                            }
                        }
                    )
                }
            ),
            description_placeholders={
                "dogs_count": self._issue_data.get("dogs_count", 0),
            },
        )

    async def async_step_add_first_dog(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle adding the first dog.

        Args:
            user_input: User provided data

        Returns:
            Flow result for next step or completion
        """
        errors = {}

        if user_input is not None:
            try:
                # Validate dog data
                dog_id = user_input["dog_id"].lower().strip()
                dog_name = user_input["dog_name"].strip()

                if not dog_id or not dog_name:
                    errors["base"] = "incomplete_data"
                else:
                    # Get the config entry and update it
                    config_entry_id = self._issue_data["config_entry_id"]
                    entry = self.hass.config_entries.async_get_entry(config_entry_id)

                    if entry:
                        # Create new dog configuration
                        new_dog = {
                            CONF_DOG_ID: dog_id,
                            CONF_DOG_NAME: dog_name,
                            "dog_breed": user_input.get("dog_breed", ""),
                            "dog_age": user_input.get("dog_age", 3),
                            "dog_weight": user_input.get("dog_weight", 20.0),
                            "dog_size": user_input.get("dog_size", "medium"),
                            "modules": {
                                "feeding": True,
                                "walk": True,
                                "gps": False,
                                "health": True,
                                "notifications": True,
                            },
                        }

                        # Update the config entry
                        new_data = entry.data.copy()
                        new_data[CONF_DOGS] = [new_dog]

                        self.hass.config_entries.async_update_entry(
                            entry, data=new_data
                        )

                        return await self.async_step_complete_repair()
                    else:
                        errors["base"] = "config_entry_not_found"

            except Exception as err:
                _LOGGER.error("Error adding first dog: %s", err)
                errors["base"] = "unexpected_error"

        return self.async_show_form(
            step_id="add_first_dog",
            data_schema=vol.Schema(
                {
                    vol.Required("dog_id"): str,
                    vol.Required("dog_name"): str,
                    vol.Optional("dog_breed", default=""): str,
                    vol.Optional("dog_age", default=3): int,
                    vol.Optional("dog_weight", default=20.0): float,
                    vol.Optional("dog_size", default="medium"): selector(
                        {
                            "select": {
                                "options": ["toy", "small", "medium", "large", "giant"]
                            }
                        }
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_duplicate_dog_ids(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle repair flow for duplicate dog IDs.

        Args:
            user_input: User provided data

        Returns:
            Flow result for next step or completion
        """
        if user_input is not None:
            action = user_input.get("action")

            if action == "auto_fix":
                # Automatically fix duplicate IDs
                await self._fix_duplicate_dog_ids()
                return await self.async_step_complete_repair()
            elif action == "manual_fix":
                return self.async_external_step(
                    step_id="reconfigure", url="/config/integrations"
                )
            else:
                return await self.async_step_complete_repair()

        return self.async_show_form(
            step_id="duplicate_dog_ids",
            data_schema=vol.Schema(
                {
                    vol.Required("action"): selector(
                        {
                            "select": {
                                "options": [
                                    {
                                        "value": "auto_fix",
                                        "label": "Automatically fix duplicate IDs",
                                    },
                                    {
                                        "value": "manual_fix",
                                        "label": "Manually fix in integration settings",
                                    },
                                    {"value": "ignore", "label": "Ignore for now"},
                                ]
                            }
                        }
                    )
                }
            ),
            description_placeholders={
                "duplicate_ids": ", ".join(self._issue_data.get("duplicate_ids", [])),
                "total_dogs": self._issue_data.get("total_dogs", 0),
            },
        )

    async def async_step_invalid_gps_config(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle repair flow for invalid GPS configuration.

        Args:
            user_input: User provided data

        Returns:
            Flow result for next step or completion
        """
        if user_input is not None:
            action = user_input.get("action")

            if action == "configure_gps":
                return await self.async_step_configure_gps()
            elif action == "disable_gps":
                await self._disable_gps_for_all_dogs()
                return await self.async_step_complete_repair()
            else:
                return await self.async_step_complete_repair()

        return self.async_show_form(
            step_id="invalid_gps_config",
            data_schema=vol.Schema(
                {
                    vol.Required("action"): selector(
                        {
                            "select": {
                                "options": [
                                    {
                                        "value": "configure_gps",
                                        "label": "Configure GPS settings",
                                    },
                                    {
                                        "value": "disable_gps",
                                        "label": "Disable GPS for all dogs",
                                    },
                                    {"value": "ignore", "label": "Ignore for now"},
                                ]
                            }
                        }
                    )
                }
            ),
            description_placeholders={
                "issue": self._issue_data.get("issue", "unknown"),
                "gps_enabled_dogs": self._issue_data.get("gps_enabled_dogs", 0),
            },
        )

    async def async_step_configure_gps(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle GPS configuration step.

        Args:
            user_input: User provided data

        Returns:
            Flow result for next step or completion
        """
        if user_input is not None:
            try:
                # Update GPS configuration
                config_entry_id = self._issue_data["config_entry_id"]
                entry = self.hass.config_entries.async_get_entry(config_entry_id)

                if entry:
                    new_options = entry.options.copy()
                    new_options.setdefault("gps", {}).update(
                        {
                            "gps_source": user_input["gps_source"],
                            "gps_update_interval": user_input["update_interval"],
                            "gps_accuracy_filter": user_input["accuracy_filter"],
                        }
                    )

                    self.hass.config_entries.async_update_entry(
                        entry, options=new_options
                    )

                    return await self.async_step_complete_repair()
                else:
                    return self.async_abort(reason="config_entry_not_found")

            except Exception as err:
                _LOGGER.error("Error configuring GPS: %s", err)
                return self.async_abort(reason="unexpected_error")

        return self.async_show_form(
            step_id="configure_gps",
            data_schema=vol.Schema(
                {
                    vol.Required("gps_source", default="device_tracker"): selector(
                        {
                            "select": {
                                "options": [
                                    "device_tracker",
                                    "person_entity",
                                    "manual",
                                    "smartphone",
                                ]
                            }
                        }
                    ),
                    vol.Required("update_interval", default=60): vol.All(
                        int, vol.Range(min=30, max=600)
                    ),
                    vol.Required("accuracy_filter", default=100): vol.All(
                        int, vol.Range(min=5, max=500)
                    ),
                }
            ),
        )

    async def async_step_missing_notifications(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle repair flow for missing notification services.

        Args:
            user_input: User provided data

        Returns:
            Flow result for next step or completion
        """
        if user_input is not None:
            action = user_input.get("action")

            if action == "setup_mobile_app":
                return self.async_external_step(
                    step_id="setup_mobile", url="/config/mobile_app"
                )
            elif action == "disable_mobile":
                await self._disable_mobile_notifications()
                return await self.async_step_complete_repair()
            else:
                return await self.async_step_complete_repair()

        return self.async_show_form(
            step_id="missing_notifications",
            data_schema=vol.Schema(
                {
                    vol.Required("action"): selector(
                        {
                            "select": {
                                "options": [
                                    {
                                        "value": "setup_mobile_app",
                                        "label": "Set up Mobile App integration",
                                    },
                                    {
                                        "value": "disable_mobile",
                                        "label": "Disable mobile notifications",
                                    },
                                    {"value": "ignore", "label": "Ignore for now"},
                                ]
                            }
                        }
                    )
                }
            ),
            description_placeholders={
                "missing_service": self._issue_data.get("missing_service", "unknown"),
                "notification_enabled_dogs": self._issue_data.get(
                    "notification_enabled_dogs", 0
                ),
            },
        )

    async def async_step_performance_warning(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle performance warning repair flow.

        Args:
            user_input: User provided data

        Returns:
            Flow result for next step or completion
        """
        if user_input is not None:
            action = user_input.get("action")

            if action == "optimize":
                await self._apply_performance_optimizations()
                return await self.async_step_complete_repair()
            elif action == "configure":
                return self.async_external_step(
                    step_id="configure", url="/config/integrations"
                )
            else:
                return await self.async_step_complete_repair()

        return self.async_show_form(
            step_id="performance_warning",
            data_schema=vol.Schema(
                {
                    vol.Required("action"): selector(
                        {
                            "select": {
                                "options": [
                                    {
                                        "value": "optimize",
                                        "label": "Apply automatic optimizations",
                                    },
                                    {
                                        "value": "configure",
                                        "label": "Configure settings manually",
                                    },
                                    {"value": "ignore", "label": "Ignore warning"},
                                ]
                            }
                        }
                    )
                }
            ),
            description_placeholders=self._issue_data,
        )

    async def async_step_storage_warning(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle repair flow for storage warnings."""

        if user_input is not None:
            action = user_input.get("action")

            if action == "reduce_retention":
                await self._reduce_data_retention()
                return await self.async_step_complete_repair()
            if action == "configure":
                return self.async_external_step(
                    step_id="configure_storage", url="/config/integrations"
                )
            return await self.async_step_complete_repair()

        return self.async_show_form(
            step_id="storage_warning",
            data_schema=vol.Schema(
                {
                    vol.Required("action"): selector(
                        {
                            "select": {
                                "options": [
                                    {
                                        "value": "reduce_retention",
                                        "label": "Reduce data retention to recommended value",
                                    },
                                    {
                                        "value": "configure",
                                        "label": "Review storage settings manually",
                                    },
                                    {"value": "ignore", "label": "Ignore warning"},
                                ]
                            }
                        }
                    )
                }
            ),
            description_placeholders={
                "current_retention": self._issue_data.get("current_retention"),
                "recommended_max": self._issue_data.get("recommended_max"),
                "suggestion": self._issue_data.get("suggestion"),
            },
        )

    async def async_step_module_conflict(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle repair flow for high resource module conflicts."""

        if user_input is not None:
            action = user_input.get("action")

            if action == "reduce_load":
                await self._limit_high_resource_modules()
                return await self.async_step_complete_repair()
            if action == "optimize":
                await self._apply_performance_optimizations()
                return await self.async_step_complete_repair()
            if action == "configure":
                return self.async_external_step(
                    step_id="configure_modules", url="/config/integrations"
                )
            return await self.async_step_complete_repair()

        return self.async_show_form(
            step_id="module_conflict",
            data_schema=vol.Schema(
                {
                    vol.Required("action"): selector(
                        {
                            "select": {
                                "options": [
                                    {
                                        "value": "reduce_load",
                                        "label": "Disable intensive modules for extra dogs",
                                    },
                                    {
                                        "value": "optimize",
                                        "label": "Apply automatic optimizations",
                                    },
                                    {
                                        "value": "configure",
                                        "label": "Adjust modules manually",
                                    },
                                    {"value": "ignore", "label": "Ignore warning"},
                                ]
                            }
                        }
                    )
                }
            ),
            description_placeholders={
                "intensive_dogs": self._issue_data.get("intensive_dogs"),
                "total_dogs": self._issue_data.get("total_dogs"),
                "suggestion": self._issue_data.get("suggestion"),
            },
        )

    async def async_step_invalid_dog_data(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle repair flow for invalid dog configuration data."""

        if user_input is not None:
            action = user_input.get("action")

            if action == "clean_up":
                await self._remove_invalid_dogs()
                return await self.async_step_complete_repair()
            if action == "reconfigure":
                return self.async_external_step(
                    step_id="reconfigure", url="/config/integrations"
                )
            return await self.async_step_complete_repair()

        return self.async_show_form(
            step_id="invalid_dog_data",
            data_schema=vol.Schema(
                {
                    vol.Required("action"): selector(
                        {
                            "select": {
                                "options": [
                                    {
                                        "value": "clean_up",
                                        "label": "Remove invalid dog entries",
                                    },
                                    {
                                        "value": "reconfigure",
                                        "label": "Fix dog data manually",
                                    },
                                    {"value": "ignore", "label": "Ignore for now"},
                                ]
                            }
                        }
                    )
                }
            ),
            description_placeholders={
                "invalid_dogs": ", ".join(self._issue_data.get("invalid_dogs", [])),
                "total_dogs": self._issue_data.get("total_dogs"),
            },
        )

    async def async_step_coordinator_error(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle repair flow for coordinator errors."""

        if user_input is not None:
            action = user_input.get("action")

            if action == "reload":
                await self._reload_config_entry()
                return await self.async_step_complete_repair()
            if action == "view_logs":
                return self.async_external_step(step_id="view_logs", url="/config/logs")
            return await self.async_step_complete_repair()

        return self.async_show_form(
            step_id="coordinator_error",
            data_schema=vol.Schema(
                {
                    vol.Required("action"): selector(
                        {
                            "select": {
                                "options": [
                                    {
                                        "value": "reload",
                                        "label": "Reload Paw Control",
                                    },
                                    {
                                        "value": "view_logs",
                                        "label": "Open system logs",
                                    },
                                    {"value": "ignore", "label": "Ignore for now"},
                                ]
                            }
                        }
                    )
                }
            ),
            description_placeholders={
                "error": self._issue_data.get("error", "unknown"),
                "last_update": self._issue_data.get("last_update"),
                "suggestion": self._issue_data.get("suggestion"),
            },
        )

    async def async_step_complete_repair(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Complete the repair flow.

        Args:
            user_input: User provided data

        Returns:
            Flow result indicating completion
        """
        # Remove the issue from the issue registry
        await ir.async_delete_issue(self.hass, DOMAIN, self.issue_id)

        return self.async_create_entry(
            title="Repair completed",
            data={"repaired_issue": self._repair_type},
        )

    async def async_step_unknown_issue(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle unknown issue types.

        Args:
            user_input: User provided data

        Returns:
            Flow result for completion
        """
        return self.async_abort(reason="unknown_issue_type")

    # Helper methods for repair actions

    async def _fix_duplicate_dog_ids(self) -> None:
        """Automatically fix duplicate dog IDs."""
        config_entry_id = self._issue_data["config_entry_id"]
        entry = self.hass.config_entries.async_get_entry(config_entry_id)

        if not entry:
            return

        dogs = entry.data.get(CONF_DOGS, [])
        seen_ids = set()
        fixed_dogs = []

        for dog in dogs:
            original_id = dog.get(CONF_DOG_ID, "")
            dog_id = original_id
            counter = 1

            # Generate unique ID
            while dog_id in seen_ids:
                dog_id = f"{original_id}_{counter}"
                counter += 1

            seen_ids.add(dog_id)

            # Update dog configuration
            fixed_dog = dog.copy()
            fixed_dog[CONF_DOG_ID] = dog_id
            fixed_dogs.append(fixed_dog)

        # Update config entry
        new_data = entry.data.copy()
        new_data[CONF_DOGS] = fixed_dogs

        self.hass.config_entries.async_update_entry(entry, data=new_data)

    async def _disable_gps_for_all_dogs(self) -> None:
        """Disable GPS module for all dogs."""
        config_entry_id = self._issue_data["config_entry_id"]
        entry = self.hass.config_entries.async_get_entry(config_entry_id)

        if not entry:
            return

        dogs = entry.data.get(CONF_DOGS, [])
        updated_dogs = []

        for dog in dogs:
            updated_dog = dog.copy()
            modules = updated_dog.setdefault("modules", {})
            modules[MODULE_GPS] = False
            updated_dogs.append(updated_dog)

        new_data = entry.data.copy()
        new_data[CONF_DOGS] = updated_dogs

        self.hass.config_entries.async_update_entry(entry, data=new_data)

    async def _disable_mobile_notifications(self) -> None:
        """Disable mobile app notifications."""
        config_entry_id = self._issue_data["config_entry_id"]
        entry = self.hass.config_entries.async_get_entry(config_entry_id)

        if not entry:
            return

        new_options = entry.options.copy()
        notifications = new_options.setdefault("notifications", {})
        notifications["mobile_notifications"] = False

        self.hass.config_entries.async_update_entry(entry, options=new_options)

    async def _apply_performance_optimizations(self) -> None:
        """Apply automatic performance optimizations."""
        config_entry_id = self._issue_data["config_entry_id"]
        entry = self.hass.config_entries.async_get_entry(config_entry_id)

        if not entry:
            return

        new_options = entry.options.copy()

        # Set performance mode to minimal
        new_options["performance_mode"] = "minimal"

        # Optimize GPS settings if present
        if "gps" in new_options:
            gps_settings = new_options["gps"]
            gps_settings["gps_update_interval"] = max(
                gps_settings.get("gps_update_interval", 60), 120
            )

        # Reduce data retention
        new_options["data_retention_days"] = min(
            new_options.get("data_retention_days", 90), 30
        )

        self.hass.config_entries.async_update_entry(entry, options=new_options)

    async def _reduce_data_retention(self) -> None:
        """Reduce stored history to the recommended value."""

        config_entry_id = self._issue_data.get("config_entry_id")
        if not config_entry_id:
            return

        entry = self.hass.config_entries.async_get_entry(config_entry_id)
        if not entry:
            return

        recommended_max = self._issue_data.get("recommended_max")
        if not isinstance(recommended_max, int):
            recommended_max = 365

        new_options = entry.options.copy()
        if new_options.get("data_retention_days") == recommended_max:
            return

        new_options["data_retention_days"] = recommended_max
        self.hass.config_entries.async_update_entry(entry, options=new_options)

    async def _limit_high_resource_modules(self) -> None:
        """Disable heavy modules for dogs beyond the recommended threshold."""

        config_entry_id = self._issue_data.get("config_entry_id")
        if not config_entry_id:
            return

        entry = self.hass.config_entries.async_get_entry(config_entry_id)
        if not entry:
            return

        dogs = entry.data.get(CONF_DOGS, [])
        updated_dogs: list[dict[str, Any]] = []
        high_resource_limit = 5
        high_resource_count = 0

        for dog in dogs:
            updated_dog = dog.copy()
            modules = dict(updated_dog.get("modules", {}))

            if modules.get(MODULE_GPS) and modules.get(MODULE_HEALTH):
                high_resource_count += 1
                if high_resource_count > high_resource_limit:
                    modules[MODULE_GPS] = False

            updated_dog["modules"] = modules
            updated_dogs.append(updated_dog)

        if updated_dogs == dogs:
            return

        new_data = entry.data.copy()
        new_data[CONF_DOGS] = updated_dogs
        self.hass.config_entries.async_update_entry(entry, data=new_data)

    async def _remove_invalid_dogs(self) -> None:
        """Remove dogs that are missing required identifiers."""

        config_entry_id = self._issue_data.get("config_entry_id")
        if not config_entry_id:
            return

        entry = self.hass.config_entries.async_get_entry(config_entry_id)
        if not entry:
            return

        dogs = entry.data.get(CONF_DOGS, [])
        valid_dogs = [
            dog for dog in dogs if dog.get(CONF_DOG_ID) and dog.get(CONF_DOG_NAME)
        ]

        if len(valid_dogs) == len(dogs):
            return

        new_data = entry.data.copy()
        new_data[CONF_DOGS] = valid_dogs
        self.hass.config_entries.async_update_entry(entry, data=new_data)

    async def _reload_config_entry(self) -> None:
        """Reload the integration config entry to recover from coordinator errors."""

        config_entry_id = self._issue_data.get("config_entry_id")
        if not config_entry_id:
            return

        try:
            await self.hass.config_entries.async_reload(config_entry_id)
        except Exception as err:  # pragma: no cover - defensive logging
            _LOGGER.error(
                "Error reloading config entry %s during repair flow: %s",
                config_entry_id,
                err,
            )


async def async_create_fix_flow(
    hass: HomeAssistant,
    issue_id: str,
    data: dict[str, Any] | None,
) -> PawControlRepairsFlow:
    """Create a repair flow compatible with the Repairs integration.

    Home Assistant loads `repairs.py` integration platforms via
    :func:`homeassistant.helpers.integration_platform.async_process_integration_platforms`
    and expects them to expose an ``async_create_fix_flow`` coroutine that
    returns a :class:`~homeassistant.components.repairs.RepairsFlow` instance.

    Args:
        hass: Home Assistant instance
        issue_id: Identifier of the repair issue
        data: Issue metadata provided by the registry

    Returns:
        Repair flow instance bound to the Paw Control handler
    """
    return PawControlRepairsFlow()


async def async_register_repairs(hass: HomeAssistant) -> None:
    """Register initial repair checks for Paw Control integration."""
    _LOGGER.debug("Registering Paw Control repair checks")

    # Iterate over all loaded entries and run checks for those with runtime data
    for entry in hass.config_entries.async_entries(DOMAIN):
        if get_runtime_data(hass, entry) is None:
            continue
        await async_check_for_issues(hass, entry)
