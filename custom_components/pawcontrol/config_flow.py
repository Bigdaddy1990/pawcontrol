"""Config flow for the PawControl integration."""

from __future__ import annotations

__all__ = ["ConfigFlow", "PawControlConfigFlow"]

import asyncio
import copy
import logging
import re
import time
from collections.abc import AsyncIterator, Awaitable, Mapping, Sequence
from contextlib import asynccontextmanager, suppress
from datetime import datetime
from typing import TYPE_CHECKING, Any, Final, cast

import voluptuous as vol
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
from homeassistant.helpers.service_info.usb import UsbServiceInfo
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
from homeassistant.util import dt as dt_util

from . import compat as compat_module
from .compat import (
    ConfigEntry,
    ConfigEntryAuthFailed,
    bind_exception_alias,
    ensure_homeassistant_exception_symbols,
)
from .config_flow_base import PawControlBaseConfigFlow
from .config_flow_dashboard_extension import DashboardFlowMixin
from .config_flow_dogs import DogManagementMixin
from .config_flow_external import ExternalEntityConfigurationMixin
from .config_flow_modules import ModuleConfigurationMixin
from .config_flow_profile import (
    DEFAULT_PROFILE,
    PROFILE_SCHEMA,
    build_profile_summary_text,
    validate_profile_selection,
)
from .const import (
    CONF_API_ENDPOINT,
    CONF_API_TOKEN,
    CONF_DATA_RETENTION_DAYS,
    CONF_DOG_AGE,
    CONF_DOG_BREED,
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOG_OPTIONS,
    CONF_DOG_SIZE,
    CONF_DOG_WEIGHT,
    CONF_DOGS,
    CONF_MODULES,
    DEFAULT_DATA_RETENTION_DAYS,
    DEFAULT_PERFORMANCE_MODE,
    DOG_SIZES,
    DOMAIN,
    MAX_DOG_AGE,
    MAX_DOG_NAME_LENGTH,
    MAX_DOG_WEIGHT,
    MIN_DOG_AGE,
    MIN_DOG_NAME_LENGTH,
    MIN_DOG_WEIGHT,
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_NOTIFICATIONS,
    MODULE_WALK,
)
from .entity_factory import ENTITY_PROFILES, EntityFactory, EntityProfileDefinition
from .exceptions import ConfigurationError, PawControlSetupError, ValidationError
from .options_flow import PawControlOptionsFlow
from .types import (
    ADD_ANOTHER_DOG_PLACEHOLDERS_TEMPLATE,
    ADD_DOG_SUMMARY_PLACEHOLDERS_TEMPLATE,
    DOG_ID_FIELD,
    DOG_MODULES_FIELD,
    DOG_MODULES_SMART_DEFAULTS_TEMPLATE,
    DOG_NAME_FIELD,
    MODULE_TOGGLE_FLAG_BY_KEY,
    MODULE_TOGGLE_KEYS,
    REAUTH_PLACEHOLDERS_TEMPLATE,
    RECONFIGURE_FORM_PLACEHOLDERS_TEMPLATE,
    ConfigEntryDataPayload,
    ConfigEntryOptionsPayload,
    ConfigFlowDiscoveryData,
    ConfigFlowDiscoveryProperties,
    ConfigFlowDiscoverySource,
    ConfigFlowGlobalSettings,
    ConfigFlowImportResult,
    ConfigFlowOperationMetricsMap,
    ConfigFlowPerformanceStats,
    ConfigFlowPlaceholders,
    ConfigFlowUserInput,
    DashboardConfigurationStepInput,
    DiscoveryUpdatePayload,
    DogConfigData,
    DogModulesConfig,
    DogSetupStepInput,
    DogValidationCacheEntry,
    ExternalEntityConfig,
    FinalSetupValidationResult,
    JSONMutableMapping,
    JSONValue,
    ModuleConfigurationStepInput,
    ModuleToggleKey,
    PerformanceMode,
    ReauthDataUpdates,
    ReauthHealthSummary,
    ReauthOptionsUpdates,
    ReauthPlaceholders,
    ReconfigureCompatibilityResult,
    ReconfigureDataUpdates,
    ReconfigureFormPlaceholders,
    ReconfigureOptionsUpdates,
    ReconfigureProfileInput,
    ReconfigureTelemetry,
    clone_placeholders,
    coerce_dog_modules_config,
    dog_modules_from_flow_input,
    ensure_dog_modules_mapping,
    freeze_placeholders,
    is_dog_config_valid,
    normalize_performance_mode,
)

ensure_homeassistant_exception_symbols()


ConfigEntryNotReady: type[Exception] = cast(
    type[Exception], compat_module.ConfigEntryNotReady
)
bind_exception_alias("ConfigEntryNotReady")

if TYPE_CHECKING:
    from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
else:  # pragma: no cover - only used for typing
    BluetoothServiceInfoBleak = Any

_LOGGER = logging.getLogger(__name__)

# Validation constants with performance optimization
DOG_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
MAX_DOGS_PER_INTEGRATION = 10

# Pre-compiled validation sets for O(1) lookups
VALID_DOG_SIZES: frozenset[str] = frozenset(DOG_SIZES)
VALID_PROFILES: frozenset[str] = frozenset(ENTITY_PROFILES.keys())

DISCOVERY_SOURCE_SET: frozenset[str] = frozenset(
    {"zeroconf", "dhcp", "usb", "bluetooth", "import", "reauth"}
)
UNKNOWN_DISCOVERY_SOURCE: ConfigFlowDiscoverySource = "unknown"

_LIST_REMOVE_DIRECTIVE = "__pc_merge_remove__"

# PLATINUM: Enhanced timeouts for robust operations
REAUTH_TIMEOUT_SECONDS = 30.0
CONFIG_HEALTH_CHECK_TIMEOUT = 15.0
NETWORK_OPERATION_TIMEOUT = 10.0


def _build_add_dog_summary_placeholders(
    *, dogs_configured: int, max_dogs: int, discovery_hint: str
) -> ConfigFlowPlaceholders:
    """Return placeholders for the main add-dog form."""

    placeholders = clone_placeholders(ADD_DOG_SUMMARY_PLACEHOLDERS_TEMPLATE)
    placeholders["dogs_configured"] = str(dogs_configured)
    placeholders["max_dogs"] = str(max_dogs)
    placeholders["discovery_hint"] = discovery_hint
    return freeze_placeholders(placeholders)


def _build_dog_modules_form_placeholders(
    *, dog_name: str, dogs_configured: int, smart_defaults: str
) -> ConfigFlowPlaceholders:
    """Return placeholders for the module selection form."""

    placeholders = clone_placeholders(DOG_MODULES_SMART_DEFAULTS_TEMPLATE)
    placeholders["dog_name"] = dog_name
    placeholders["dogs_configured"] = str(dogs_configured)
    placeholders["smart_defaults"] = smart_defaults
    return freeze_placeholders(placeholders)


def _build_add_another_placeholders(
    *,
    dogs_configured: int,
    dogs_list: str,
    can_add_more: bool,
    max_dogs: int,
    performance_note: str,
) -> ConfigFlowPlaceholders:
    """Return placeholders used when prompting to add another dog."""

    placeholders = clone_placeholders(ADD_ANOTHER_DOG_PLACEHOLDERS_TEMPLATE)
    placeholders["dogs_configured"] = str(dogs_configured)
    placeholders["dogs_list"] = dogs_list
    placeholders["can_add_more"] = "yes" if can_add_more else "no"
    placeholders["max_dogs"] = str(max_dogs)
    placeholders["performance_note"] = performance_note
    return freeze_placeholders(placeholders)


# Optimized schema definitions using constants from const.py
DOG_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_DOG_ID): cv.string,
        vol.Required(CONF_DOG_NAME): cv.string,
        vol.Optional(CONF_DOG_BREED, default=""): cv.string,
        vol.Optional(CONF_DOG_AGE, default=3): vol.All(
            vol.Coerce(int), vol.Range(min=MIN_DOG_AGE, max=MAX_DOG_AGE)
        ),
        vol.Optional(CONF_DOG_WEIGHT, default=20.0): vol.All(
            vol.Coerce(float), vol.Range(min=MIN_DOG_WEIGHT, max=MAX_DOG_WEIGHT)
        ),
        vol.Optional(CONF_DOG_SIZE, default="medium"): vol.In(VALID_DOG_SIZES),
        vol.Optional(CONF_MODULES, default={}): dict,
    }
)


class ConfigFlowPerformanceMonitor:
    """Monitor performance of config flow operations."""

    def __init__(self) -> None:
        """Initialise empty metric buckets for tracking config flow performance."""
        self.operation_times: dict[str, list[float]] = {}
        self.validation_counts: dict[str, int] = {}

    def record_operation(self, operation: str, duration: float) -> None:
        """Record timing information for an operation."""

        times = self.operation_times.setdefault(operation, [])
        times.append(duration)

        # Keep cache size bounded to avoid memory bloat
        if len(times) > 100:
            self.operation_times[operation] = times[-50:]

    def record_validation(self, validation_type: str) -> None:
        """Record a validation invocation."""

        self.validation_counts[validation_type] = (
            self.validation_counts.get(validation_type, 0) + 1
        )

    def get_stats(self) -> ConfigFlowPerformanceStats:
        """Return aggregated statistics for diagnostics."""

        operations: ConfigFlowOperationMetricsMap = {}
        for operation, times in self.operation_times.items():
            if not times:
                continue
            operations[operation] = {
                "avg_time": sum(times) / len(times),
                "max_time": max(times),
                "count": len(times),
            }

        return ConfigFlowPerformanceStats(
            operations=operations,
            validations=self.validation_counts.copy(),
        )


config_flow_monitor = ConfigFlowPerformanceMonitor()


@asynccontextmanager
async def timed_operation(operation_name: str) -> AsyncIterator[None]:
    """Async context manager that records operation duration."""

    start_time = time.monotonic()
    try:
        yield
    finally:
        duration = time.monotonic() - start_time
        config_flow_monitor.record_operation(operation_name, duration)
        if duration > 2.0:
            _LOGGER.warning(
                "Slow config flow operation: %s took %.2fs",
                operation_name,
                duration,
            )


MODULE_SELECTION_KEYS: Final[tuple[str, ...]] = (
    MODULE_FEEDING,
    MODULE_WALK,
    MODULE_HEALTH,
    MODULE_GPS,
    MODULE_NOTIFICATIONS,
)

MODULES_SCHEMA = vol.Schema(
    {
        vol.Optional(MODULE_FEEDING, default=True): cv.boolean,
        vol.Optional(MODULE_WALK, default=True): cv.boolean,
        vol.Optional(MODULE_HEALTH, default=True): cv.boolean,
        vol.Optional(MODULE_GPS, default=False): cv.boolean,
        vol.Optional(MODULE_NOTIFICATIONS, default=True): cv.boolean,
    }
)


class DogValidationError(Exception):
    """Raised when validating a dog configuration fails."""

    def __init__(
        self,
        *,
        field_errors: dict[str, str] | None = None,
        base_errors: list[str] | None = None,
    ) -> None:
        """Store validation errors for later conversion to form errors."""

        self.field_errors = field_errors or {}
        self.base_errors = base_errors or []

        message_parts: list[str] = []
        message_parts.extend(self.field_errors.values())
        message_parts.extend(self.base_errors)
        super().__init__("; ".join(message_parts) or "Invalid dog configuration")

    def as_form_errors(self) -> dict[str, str]:
        """Return errors in the format expected by Home Assistant forms."""

        if self.field_errors:
            return dict(self.field_errors)

        if self.base_errors:
            return {"base": self.base_errors[0]}

        return {"base": "invalid_dog_data"}


class PawControlConfigFlow(
    ModuleConfigurationMixin,
    DashboardFlowMixin,
    ExternalEntityConfigurationMixin,
    DogManagementMixin,
    PawControlBaseConfigFlow,
):
    """Enhanced configuration flow for Paw Control integration.

    Features:
    - Device discovery support (Zeroconf, DHCP)
    - Import from configuration.yaml
    - Optimized validation with set operations
    - Comprehensive error handling
    - Performance monitoring
    """

    VERSION = 1
    MINOR_VERSION = 3

    def __init__(self) -> None:
        """Initialize configuration flow with enhanced state management."""
        super().__init__()
        self._integration_name = "Paw Control"
        self._entity_profile = "standard"
        self.reauth_entry: ConfigEntry | None = None
        self._discovery_info: ConfigFlowDiscoveryData = {}
        self._existing_dog_ids: set[str] = set()  # Performance: O(1) lookups
        self._entity_factory = EntityFactory(None)

        # Validation and estimation caches for improved responsiveness
        self._profile_estimates_cache: dict[str, int] = {}
        self._enabled_modules: DogModulesConfig = {}
        self._external_entities: ExternalEntityConfig = {}

    async def async_step_user(
        self, user_input: ConfigFlowUserInput | None = None
    ) -> ConfigFlowResult:
        """Handle initial step with enhanced uniqueness validation.

        Args:
            user_input: User provided data

        Returns:
            Config flow result
        """
        async with timed_operation("user_step"):
            # Ensure single instance with improved messaging
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured(
                updates={},
                reload_on_update=False,
            )

            return await self.async_step_add_dog()

    async def async_step_zeroconf(
        self, discovery_info: ZeroconfServiceInfo
    ) -> ConfigFlowResult:
        """Handle Zeroconf discovery.

        Args:
            discovery_info: Zeroconf discovery information

        Returns:
            Config flow result
        """
        _LOGGER.debug("Zeroconf discovery: %s", discovery_info)

        # Extract device information from Zeroconf
        hostname = discovery_info.hostname or ""
        properties_raw = discovery_info.properties or {}
        properties: ConfigFlowDiscoveryProperties = dict(properties_raw)

        # Check if this is a supported device
        if not self._is_supported_device(hostname, properties):
            return self.async_abort(reason="not_supported")

        # Store discovery info for later use
        discovery_payload: ConfigFlowDiscoveryData = {
            "source": "zeroconf",
            "hostname": hostname,
            "host": discovery_info.host or "",
            "properties": properties,
        }

        if discovery_info.port is not None:
            discovery_payload["port"] = int(discovery_info.port)
        if discovery_info.type:
            discovery_payload["type"] = discovery_info.type
        if discovery_info.name:
            discovery_payload["name"] = discovery_info.name

        updates, comparison = self._prepare_discovery_updates(
            discovery_payload, source="zeroconf"
        )

        # Set unique ID based on discovered device
        device_id = self._extract_device_id(properties)
        if device_id:
            await self.async_set_unique_id(device_id)
            result = await self._handle_existing_discovery_entry(
                updates=updates,
                comparison=comparison,
                reload_on_update=True,
            )
            if result is not None:
                return result

        return await self.async_step_discovery_confirm()

    async def async_step_dhcp(
        self, discovery_info: DhcpServiceInfo
    ) -> ConfigFlowResult:
        """Handle DHCP discovery.

        Args:
            discovery_info: DHCP discovery information

        Returns:
            Config flow result
        """
        _LOGGER.debug("DHCP discovery: %s", discovery_info)

        hostname = discovery_info.hostname or ""
        macaddress = discovery_info.macaddress or ""

        # Check if this is a supported device
        if not self._is_supported_device(hostname, {"mac": macaddress}):
            return self.async_abort(reason="not_supported")

        dhcp_payload: ConfigFlowDiscoveryData = {
            "source": "dhcp",
            "hostname": hostname,
            "macaddress": macaddress,
        }
        if discovery_info.ip:
            dhcp_payload["ip"] = discovery_info.ip

        updates, comparison = self._prepare_discovery_updates(
            dhcp_payload, source="dhcp"
        )

        # Use MAC address as unique ID
        await self.async_set_unique_id(macaddress)
        result = await self._handle_existing_discovery_entry(
            updates=updates,
            comparison=comparison,
            reload_on_update=True,
        )
        if result is not None:
            return result

        return await self.async_step_discovery_confirm()

    async def async_step_usb(self, discovery_info: UsbServiceInfo) -> ConfigFlowResult:
        """Handle USB discovery for supported trackers."""

        _LOGGER.debug("USB discovery: %s", discovery_info)

        description = discovery_info.description or ""
        serial_number = discovery_info.serial_number or ""
        hostname_hint = description or serial_number
        properties: ConfigFlowDiscoveryProperties = {
            "serial": serial_number,
            "vid": discovery_info.vid,
            "pid": discovery_info.pid,
            "manufacturer": discovery_info.manufacturer,
            "description": description,
        }

        if not self._is_supported_device(hostname_hint, properties):
            return self.async_abort(reason="not_supported")

        usb_payload: ConfigFlowDiscoveryData = {
            "source": "usb",
            "description": description,
            "manufacturer": discovery_info.manufacturer or "",
            "vid": str(discovery_info.vid) if discovery_info.vid is not None else "",
            "pid": str(discovery_info.pid) if discovery_info.pid is not None else "",
            "serial_number": serial_number,
        }
        if discovery_info.device:
            usb_payload["device"] = discovery_info.device

        updates, comparison = self._prepare_discovery_updates(usb_payload, source="usb")

        unique_id = serial_number or f"{discovery_info.vid}:{discovery_info.pid}"
        if unique_id:
            await self.async_set_unique_id(unique_id)
            result = await self._handle_existing_discovery_entry(
                updates=updates,
                comparison=comparison,
                reload_on_update=True,
            )
            if result is not None:
                return result

        return await self.async_step_discovery_confirm()

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle Bluetooth discovery for supported trackers."""

        _LOGGER.debug("Bluetooth discovery: %s", discovery_info)

        name = getattr(discovery_info, "name", "") or ""
        address = getattr(discovery_info, "address", "") or ""
        service_uuids = list(getattr(discovery_info, "service_uuids", []) or [])

        hostname_hint = name or address
        properties: ConfigFlowDiscoveryProperties = {
            "address": address,
            "service_uuids": service_uuids,
            "name": name,
        }

        if not self._is_supported_device(hostname_hint, properties):
            return self.async_abort(reason="not_supported")

        bluetooth_payload: ConfigFlowDiscoveryData = {
            "source": "bluetooth",
            "name": name,
            "address": address,
            "service_uuids": service_uuids,
        }

        updates, comparison = self._prepare_discovery_updates(
            bluetooth_payload, source="bluetooth"
        )

        if address:
            await self.async_set_unique_id(address)
            result = await self._handle_existing_discovery_entry(
                updates=updates,
                comparison=comparison,
                reload_on_update=True,
            )
            if result is not None:
                return result

        return await self.async_step_discovery_confirm()

    async def async_step_discovery_confirm(
        self, user_input: ConfigFlowUserInput | None = None
    ) -> ConfigFlowResult:
        """Confirm discovered device setup.

        Args:
            user_input: User provided data

        Returns:
            Config flow result
        """
        if user_input is not None:
            if user_input.get("confirm", False):
                # Pre-populate with discovered device info
                return await self.async_step_add_dog()
            return self.async_abort(reason="discovery_rejected")

        discovery_source = self._discovery_info.get("source", "unknown")
        device_info = self._format_discovery_info()

        return self.async_show_form(
            step_id="discovery_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required("confirm", default=True): cv.boolean,
                }
            ),
            description_placeholders={
                "discovery_source": discovery_source,
                "device_info": device_info,
            },
        )

    async def async_step_import(
        self, import_config: ConfigFlowUserInput
    ) -> ConfigFlowResult:
        """Handle import from configuration.yaml.

        Args:
            import_config: Configuration from YAML

        Returns:
            Config flow result

        Raises:
            ConfigEntryNotReady: If import validation fails
        """
        _LOGGER.debug("Import configuration: %s", import_config)

        async with timed_operation("import_step"):
            # Ensure single instance
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()

            try:
                validated_config = await self._validate_import_config_enhanced(
                    import_config
                )

                return self.async_create_entry(
                    title="PawControl (Imported)",
                    data=validated_config["data"],
                    options=validated_config["options"],
                )

            except vol.Invalid as err:
                _LOGGER.error("Invalid import configuration: %s", err)
                raise ConfigEntryNotReady(
                    "Invalid import configuration format"
                ) from err
            except ValidationError as err:
                _LOGGER.error("Import validation failed: %s", err)
                raise ConfigEntryNotReady(f"Import validation failed: {err}") from err

    async def _validate_import_config(
        self, import_config: ConfigFlowUserInput
    ) -> ConfigFlowImportResult:
        """Backward-compatible wrapper for enhanced import validation."""

        return await self._validate_import_config_enhanced(import_config)

    async def _validate_import_config_enhanced(
        self, import_config: ConfigFlowUserInput
    ) -> ConfigFlowImportResult:
        """Enhanced validation for imported configuration with better error reporting.

        Args:
            import_config: Configuration to validate

        Returns:
            Validated configuration data

        Raises:
            ValidationError: If validation fails
            ConfigurationError: If configuration is invalid
        """
        config_flow_monitor.record_validation("import_attempt")

        async with timed_operation("import_validation"):
            validation_errors: list[str] = []

            try:
                dogs_config = import_config.get(CONF_DOGS, [])
                if not isinstance(dogs_config, list):
                    raise ConfigurationError(
                        "dogs",
                        dogs_config,
                        "Dogs configuration must be a list",
                    )

                validated_dogs = []
                seen_ids: set[str] = set()
                seen_names: set[str] = set()

                for index, dog_config in enumerate(dogs_config):
                    try:
                        validated_dog = DOG_SCHEMA(dog_config)

                        dog_id = validated_dog.get(DOG_ID_FIELD)
                        dog_name = validated_dog.get(DOG_NAME_FIELD)

                        if dog_id in seen_ids:
                            validation_errors.append(
                                f"Duplicate dog ID '{dog_id}' at position {index + 1}"
                            )
                            continue

                        if dog_name in seen_names:
                            validation_errors.append(
                                f"Duplicate dog name '{dog_name}' at position {index + 1}"
                            )
                            continue

                        if not is_dog_config_valid(validated_dog):
                            validation_errors.append(
                                f"Invalid dog configuration at position {index + 1}: {dog_config}"
                            )
                            continue

                        seen_ids.add(dog_id)
                        seen_names.add(dog_name)
                        validated_dogs.append(validated_dog)
                        config_flow_monitor.record_validation("import_dog_valid")

                    except vol.Invalid as err:
                        validation_errors.append(
                            f"Dog validation failed at position {index + 1}: {err}"
                        )
                        config_flow_monitor.record_validation("import_dog_invalid")

                if not validated_dogs:
                    if validation_errors:
                        raise ValidationError(
                            "import_dogs",
                            constraint="No valid dogs found. Errors: "
                            + "; ".join(validation_errors),
                        )
                    raise ValidationError(
                        "import_dogs",
                        constraint="No valid dogs found in import configuration",
                    )

                profile = import_config.get("entity_profile", "standard")
                if profile not in VALID_PROFILES:
                    validation_errors.append(
                        f"Invalid profile '{profile}', using 'standard'"
                    )
                    profile = "standard"

                for dog in validated_dogs:
                    modules = ensure_dog_modules_mapping(dog)
                    if not self._entity_factory.validate_profile_for_modules(
                        profile, modules
                    ):
                        validation_errors.append(
                            f"Profile '{profile}' may not be optimal for dog '{dog.get(DOG_NAME_FIELD)}'"
                        )

                if validation_errors:
                    _LOGGER.warning(
                        "Import validation warnings: %s",
                        "; ".join(validation_errors),
                    )

                config_flow_monitor.record_validation("import_validated")

                data_payload: ConfigEntryDataPayload = {
                    "name": import_config.get("name", "PawControl (Imported)"),
                    CONF_DOGS: validated_dogs,
                    "entity_profile": profile,
                    "import_warnings": validation_errors,
                    "import_timestamp": dt_util.utcnow().isoformat(),
                }
                options_payload: ConfigEntryOptionsPayload = {
                    "entity_profile": profile,
                    "dashboard_enabled": bool(
                        import_config.get("dashboard_enabled", True)
                    ),
                    "dashboard_auto_create": bool(
                        import_config.get("dashboard_auto_create", True)
                    ),
                    "import_source": "configuration_yaml",
                }

                result: ConfigFlowImportResult = {
                    "data": data_payload,
                    "options": options_payload,
                }
                return result

            except Exception as err:
                raise ValidationError(
                    "import_configuration",
                    constraint=f"Import configuration validation failed: {err}",
                ) from err

    def _is_supported_device(
        self, hostname: str, properties: ConfigFlowDiscoveryProperties
    ) -> bool:
        """Check if discovered device is supported.

        Args:
            hostname: Device hostname
            properties: Device properties

        Returns:
            True if device is supported
        """
        # Check for known device patterns
        supported_patterns = [
            r"tractive-.*",
            r"petnet-.*",
            r"whistle-.*",
            r"paw-control-.*",
        ]

        return any(
            re.match(pattern, hostname, re.IGNORECASE) for pattern in supported_patterns
        )

    def _extract_device_id(
        self, properties: ConfigFlowDiscoveryProperties
    ) -> str | None:
        """Extract device ID from discovery properties.

        Args:
            properties: Device properties

        Returns:
            Device ID if found
        """
        # Look for common device ID fields
        for field in ["serial", "device_id", "mac", "uuid"]:
            if field in properties:
                return str(properties[field])
        return None

    def _normalise_discovery_metadata(
        self,
        payload: Mapping[str, object] | None,
        *,
        source: ConfigFlowDiscoverySource | None = None,
        include_last_seen: bool = True,
    ) -> ConfigFlowDiscoveryData:
        """Return a normalised discovery metadata payload."""

        data = payload if isinstance(payload, Mapping) else {}

        candidate_source = source or data.get("source") or UNKNOWN_DISCOVERY_SOURCE
        candidate_source_str = str(candidate_source).lower()
        resolved_source = (
            candidate_source_str
            if candidate_source_str in DISCOVERY_SOURCE_SET
            else UNKNOWN_DISCOVERY_SOURCE
        )

        normalised: ConfigFlowDiscoveryData = {
            "source": cast(ConfigFlowDiscoverySource, resolved_source)
        }

        if include_last_seen:
            normalised["last_seen"] = dt_util.utcnow().isoformat()

        str_fields = (
            "hostname",
            "host",
            "ip",
            "macaddress",
            "type",
            "name",
            "description",
            "manufacturer",
            "vid",
            "pid",
            "serial_number",
            "device",
            "address",
        )

        for field in str_fields:
            value = data.get(field)
            if isinstance(value, str):
                trimmed = value.strip()
                if trimmed:
                    normalised[field] = trimmed
            elif value not in (None, ""):
                normalised[field] = str(value)

        port_value = data.get("port")
        if isinstance(port_value, int):
            normalised["port"] = port_value
        elif isinstance(port_value, str):
            with suppress(ValueError):
                normalised["port"] = int(port_value.strip())

        properties_value = data.get("properties")
        if isinstance(properties_value, Mapping):
            properties: ConfigFlowDiscoveryProperties = {}
            for key, value in properties_value.items():
                key_str = str(key)
                if isinstance(value, str | int | float | bool):
                    properties[key_str] = value
                elif isinstance(value, bytes):
                    try:
                        properties[key_str] = value.decode()
                    except Exception:
                        properties[key_str] = value.decode(errors="ignore")
                elif value is None:
                    continue
                else:
                    properties[key_str] = str(value)
            if properties:
                normalised["properties"] = properties

        service_uuids_value = data.get("service_uuids")
        if isinstance(service_uuids_value, Sequence) and not isinstance(
            service_uuids_value, str | bytes
        ):
            service_uuids: list[str] = []
            for item in service_uuids_value:
                if isinstance(item, str):
                    trimmed = item.strip()
                    if trimmed:
                        service_uuids.append(trimmed)
                elif isinstance(item, bytes):
                    try:
                        decoded = item.decode()
                    except Exception:
                        decoded = item.decode(errors="ignore")
                    if decoded:
                        service_uuids.append(decoded)
                elif item is not None:
                    service_uuids.append(str(item))
            if service_uuids:
                normalised["service_uuids"] = service_uuids

        return cast(ConfigFlowDiscoveryData, normalised)

    def _strip_dynamic_discovery_fields(
        self, info: Mapping[str, object]
    ) -> ConfigFlowDiscoveryData:
        """Remove dynamic fields (like timestamps) for comparison."""

        cleaned = {key: value for key, value in info.items() if key != "last_seen"}
        return cast(ConfigFlowDiscoveryData, cleaned)

    async def _async_get_entry_for_unique_id(self) -> ConfigEntry | None:
        """Return the current entry matching the configured unique ID."""

        unique_id = getattr(self, "_unique_id", None)
        if not unique_id:
            return None

        entries = self._async_current_entries()
        if isinstance(entries, Awaitable):
            entries_list = await entries
        else:
            entries_list = entries

        for entry in entries_list:
            if entry.unique_id == unique_id:
                return entry

        if isinstance(unique_id, str):
            normalised_unique_id = unique_id.casefold()
            for entry in entries_list:
                entry_id = entry.unique_id
                if (
                    isinstance(entry_id, str)
                    and entry_id.casefold() == normalised_unique_id
                ):
                    return entry
        return None

    def _discovery_update_required(
        self,
        entry: ConfigEntry,
        *,
        updates: Mapping[str, object],
        comparison: Mapping[str, object],
    ) -> bool:
        """Return whether discovery updates require entry persistence."""

        existing_data = entry.data

        if "discovery_info" in updates:
            existing_info_raw = existing_data.get("discovery_info")
            if isinstance(existing_info_raw, Mapping):
                normalised_existing = self._normalise_discovery_metadata(
                    existing_info_raw,
                    source=cast(
                        ConfigFlowDiscoverySource | None,
                        existing_info_raw.get("source"),
                    ),
                    include_last_seen=False,
                )
            else:
                normalised_existing = self._normalise_discovery_metadata(
                    None,
                    source=None,
                    include_last_seen=False,
                )

            if self._strip_dynamic_discovery_fields(normalised_existing) != comparison:
                return True

        for key, value in updates.items():
            if key == "discovery_info":
                continue
            if existing_data.get(key) != value:
                return True

        return False

    async def _handle_existing_discovery_entry(
        self,
        *,
        updates: Mapping[str, object],
        comparison: Mapping[str, object],
        reload_on_update: bool,
    ) -> ConfigFlowResult | None:
        """Abort or update when discovery encounters an existing entry."""

        entry = await self._async_get_entry_for_unique_id()
        if entry is None:
            return self._abort_if_unique_id_configured(
                updates=dict(updates),
                reload_on_update=reload_on_update,
            )

        if not self._discovery_update_required(
            entry, updates=updates, comparison=comparison
        ):
            return self.async_abort(reason="already_configured")

        if not reload_on_update:
            return self.async_abort(reason="already_configured")

        return await self.async_update_reload_and_abort(
            entry,
            data_updates=dict(updates),
            reason="already_configured",
        )

    def _prepare_discovery_updates(
        self,
        payload: Mapping[str, object],
        *,
        source: ConfigFlowDiscoverySource,
    ) -> tuple[DiscoveryUpdatePayload, ConfigFlowDiscoveryData]:
        """Normalise discovery metadata and build update payloads."""

        normalised = self._normalise_discovery_metadata(payload, source=source)
        comparison = self._strip_dynamic_discovery_fields(normalised)

        discovery_info: ConfigFlowDiscoveryData = cast(
            ConfigFlowDiscoveryData, copy.deepcopy(normalised)
        )
        self._discovery_info = cast(ConfigFlowDiscoveryData, copy.deepcopy(normalised))

        updates: DiscoveryUpdatePayload = {
            "discovery_info": cast(ConfigFlowDiscoveryData, copy.deepcopy(normalised))
        }

        host = discovery_info.get("host") or discovery_info.get("ip")
        if host:
            updates["host"] = host

        device = discovery_info.get("device")
        if device:
            updates["device"] = device

        address = discovery_info.get("address")
        if address:
            updates["address"] = address

        return updates, comparison

    def _format_discovery_info(self) -> str:
        """Format discovery info for display.

        Returns:
            Formatted discovery information
        """
        info = self._discovery_info
        if info.get("source") == "zeroconf":
            return f"Device: {info.get('hostname', 'Unknown')}\nHost: {info.get('host', 'Unknown')}"
        if info.get("source") == "dhcp":
            return f"Device: {info.get('hostname', 'Unknown')}\nIP: {info.get('ip', 'Unknown')}"
        return "Unknown device"

    async def async_step_add_dog(
        self, user_input: ConfigFlowUserInput | None = None
    ) -> ConfigFlowResult:
        """Add a dog configuration with optimized validation.

        Args:
            user_input: User provided data

        Returns:
            Config flow result
        """
        async with timed_operation("add_dog_step"):
            errors: dict[str, str] = {}

            if user_input is not None:
                user_input_dict = dict(user_input)
                try:
                    validated_input = await self._validate_dog_input_cached(
                        user_input_dict
                    )
                    if validated_input:
                        dog_config = await self._create_dog_config(validated_input)
                        self._dogs.append(dog_config)
                        self._existing_dog_ids.add(dog_config[DOG_ID_FIELD])
                        self._invalidate_profile_caches()
                        return await self.async_step_dog_modules()

                except DogValidationError as err:
                    errors.update(err.as_form_errors())
                    if "base" not in errors:
                        _LOGGER.warning("Dog validation failed: %s", err)
                    else:
                        _LOGGER.warning("Dog validation failed: %s", errors["base"])
                except Exception as err:
                    _LOGGER.error("Unexpected error during dog validation: %s", err)
                    errors["base"] = "unknown_error"

            return self.async_show_form(
                step_id="add_dog",
                data_schema=DOG_SCHEMA,
                errors=errors,
                description_placeholders=_build_add_dog_summary_placeholders(
                    dogs_configured=len(self._dogs),
                    max_dogs=MAX_DOGS_PER_INTEGRATION,
                    discovery_hint=self._get_discovery_hint(),
                ),
            )

    def _get_validation_state_signature(self) -> str:
        """Get a signature representing current validation state."""

        existing_ids = "|".join(sorted(self._existing_dog_ids))
        return f"{len(self._dogs)}::{existing_ids}"

    async def _validate_dog_input_cached(
        self, user_input: ConfigFlowUserInput
    ) -> DogSetupStepInput | None:
        """Validate dog input with caching for repeated validations."""

        config_flow_monitor.record_validation("dog_input_attempt")

        cache_key = "_".join(
            [
                user_input.get("dog_id", ""),
                user_input.get("dog_name", ""),
                str(user_input.get("dog_weight", 0)),
            ]
        )
        state_signature = self._get_validation_state_signature()
        cached_entry = self._validation_cache.get(cache_key)
        now_ts = dt_util.utcnow().timestamp()

        if cached_entry is not None:
            cached_result = cast(DogSetupStepInput | None, cached_entry["result"])
            cached_state = cached_entry.get("state_signature")
            cached_at = cached_entry["cached_at"]
            if (
                cached_state == state_signature
                and cached_result is not None
                and now_ts - cached_at < 60
            ):
                config_flow_monitor.record_validation("dog_input_cache_hit")
                return cast(DogSetupStepInput, dict(cached_result))

        try:
            result = await self._validate_dog_input_optimized(user_input)
        except DogValidationError:
            config_flow_monitor.record_validation("dog_input_error")
            raise

        cloned_result: DogSetupStepInput | None
        if result is None:
            cloned_result = None
        else:
            cloned_result = cast(DogSetupStepInput, dict(result))

        cache_payload: DogValidationCacheEntry = {
            "result": cloned_result,
            "cached_at": now_ts,
            "state_signature": state_signature,
        }
        self._validation_cache[cache_key] = cache_payload
        config_flow_monitor.record_validation("dog_input_validated")
        return cloned_result

    def _invalidate_profile_caches(self) -> None:
        """Invalidate cached profile estimates when configuration changes."""

        self._profile_estimates_cache.clear()

    def _estimate_total_entities_cached(self) -> int:
        """Estimate total entities with improved caching."""

        dogs_signature = hash(
            str(
                [
                    (
                        dog.get(DOG_ID_FIELD),
                        tuple(sorted(ensure_dog_modules_mapping(dog).items())),
                    )
                    for dog in self._dogs
                ]
            )
        )
        cache_key = f"{self._entity_profile}_{len(self._dogs)}_{dogs_signature}"

        cached = self._profile_estimates_cache.get(cache_key)
        if cached is not None:
            return cached

        total = 0
        for dog in self._dogs:
            module_flags_mapping = ensure_dog_modules_mapping(dog)
            module_flags = {
                key: bool(value) for key, value in module_flags_mapping.items()
            }
            total += self._entity_factory.estimate_entity_count(
                self._entity_profile, module_flags
            )

        self._profile_estimates_cache[cache_key] = total
        return total

    def _get_discovery_hint(self) -> str:
        """Get hint text based on discovery info.

        Returns:
            Discovery hint text
        """
        if self._discovery_info:
            return (
                f"Discovered device: {self._discovery_info.get('hostname', 'Unknown')}"
            )
        return ""

    async def _validate_dog_input_optimized(
        self, user_input: ConfigFlowUserInput
    ) -> DogSetupStepInput | None:
        """Validate dog input data with optimized performance.

        Uses set operations and pre-compiled regex for better performance.

        Args:
            user_input: Raw user input

        Returns:
            Validated input or None if validation fails

        Raises:
            DogValidationError: If validation fails
        """
        # Sanitize inputs with optimized string operations
        raw_dog_id = str(user_input[CONF_DOG_ID])
        dog_id = raw_dog_id.lower().strip()
        dog_name = str(user_input[CONF_DOG_NAME]).strip()

        # Batch validation for better performance
        field_errors: dict[str, str] = {}
        base_errors: list[str] = []

        # Validate dog ID format (pre-compiled regex)
        if not DOG_ID_PATTERN.match(dog_id):
            field_errors[CONF_DOG_ID] = "Invalid ID format"

        # Check for duplicate dog ID (O(1) set lookup)
        if dog_id in self._existing_dog_ids:
            field_errors.setdefault(CONF_DOG_ID, "ID already exists")

        # Validate dog name length
        name_len = len(dog_name)
        if name_len < MIN_DOG_NAME_LENGTH:
            field_errors[CONF_DOG_NAME] = (
                f"Dog name must be at least {MIN_DOG_NAME_LENGTH} characters"
            )
        elif name_len > MAX_DOG_NAME_LENGTH:
            field_errors[CONF_DOG_NAME] = (
                f"Dog name cannot exceed {MAX_DOG_NAME_LENGTH} characters"
            )

        # Check maximum dogs limit
        if len(self._dogs) >= MAX_DOGS_PER_INTEGRATION:
            base_errors.append(
                f"Maximum {MAX_DOGS_PER_INTEGRATION} dogs allowed per integration"
            )

        # Validate dog size (O(1) frozenset lookup)
        dog_size = str(user_input.get(CONF_DOG_SIZE, "medium"))
        if dog_size not in VALID_DOG_SIZES:
            field_errors[CONF_DOG_SIZE] = f"Invalid dog size: {dog_size}"

        # Normalise and validate weight using schema bounds
        raw_weight = (
            user_input.get(CONF_DOG_WEIGHT)
            if CONF_DOG_WEIGHT in user_input
            else user_input.get("weight")
        )
        dog_weight: float
        if raw_weight is None:
            dog_weight = 20.0
        else:
            try:
                dog_weight = float(raw_weight)
            except (TypeError, ValueError):
                field_errors[CONF_DOG_WEIGHT] = "Invalid weight"
            else:
                if not (MIN_DOG_WEIGHT <= dog_weight <= MAX_DOG_WEIGHT):
                    field_errors[CONF_DOG_WEIGHT] = (
                        f"Weight must be between {MIN_DOG_WEIGHT} and {MAX_DOG_WEIGHT}"
                    )

        # Raise single error with all issues
        if field_errors or base_errors:
            raise DogValidationError(
                field_errors=field_errors,
                base_errors=base_errors,
            )

        # Return validated data
        raw_breed = user_input.get(CONF_DOG_BREED, "")
        dog_breed = raw_breed.strip() if isinstance(raw_breed, str) else ""
        breed_value: str | None = dog_breed or None

        age_value = user_input.get(CONF_DOG_AGE, 3)
        if isinstance(age_value, int | float):
            dog_age: int | None = int(age_value)
        else:
            dog_age = None

        validated: DogSetupStepInput = {
            "dog_id": dog_id,
            "dog_name": dog_name,
        }
        if breed_value is not None:
            validated["dog_breed"] = breed_value
        if dog_age is not None:
            validated["dog_age"] = dog_age
        validated["dog_weight"] = dog_weight
        validated["dog_size"] = dog_size

        return validated

    async def _create_dog_config(
        self, validated_input: DogSetupStepInput
    ) -> DogConfigData:
        """Create dog configuration from validated input."""

        dog_id = cast(str, validated_input.get("dog_id", "")).strip()
        dog_name = cast(str, validated_input.get("dog_name", "")).strip()

        breed_raw = validated_input.get("dog_breed")
        dog_breed: str | None
        if isinstance(breed_raw, str):
            stripped = breed_raw.strip()
            dog_breed = stripped or None
        else:
            dog_breed = None

        age_raw = validated_input.get("dog_age")
        dog_age: int | None = int(age_raw) if isinstance(age_raw, int | float) else None

        weight_raw = validated_input.get("dog_weight")
        dog_weight: float | None = (
            float(weight_raw) if isinstance(weight_raw, int | float) else None
        )

        size_raw = validated_input.get("dog_size")
        dog_size: str | None = size_raw if isinstance(size_raw, str) else None

        modules: DogModulesConfig = cast(DogModulesConfig, {})

        config: DogConfigData = {
            "dog_id": dog_id,
            "dog_name": dog_name,
            "modules": modules,
        }

        if dog_breed is not None:
            config["dog_breed"] = dog_breed
        if dog_age is not None:
            config["dog_age"] = dog_age
        if dog_weight is not None:
            config["dog_weight"] = dog_weight
        if dog_size is not None:
            config["dog_size"] = dog_size

        if self._discovery_info:
            config["discovery_info"] = cast(
                ConfigFlowDiscoveryData, dict(self._discovery_info)
            )

        return config

    async def async_step_dog_modules(
        self, user_input: ConfigFlowUserInput | None = None
    ) -> ConfigFlowResult:
        """Configure optional modules for the newly added dog.

        Args:
            user_input: User provided data

        Returns:
            Config flow result
        """
        if not self._dogs:
            return await self.async_step_add_dog()

        current_dog = self._dogs[-1]

        if user_input is not None:
            existing_modules = cast(
                DogModulesConfig | None, current_dog.get(DOG_MODULES_FIELD)
            )
            mapping_candidate: DogModulesConfig
            raw_mapping: ConfigFlowUserInput = {}

            if isinstance(user_input, Mapping):
                raw_mapping = cast(ConfigFlowUserInput, dict(user_input))

            if raw_mapping and any(
                flag in raw_mapping for flag in MODULE_TOGGLE_FLAG_BY_KEY.values()
            ):
                mapping_candidate = dog_modules_from_flow_input(
                    raw_mapping,
                    existing=existing_modules,
                )
            elif raw_mapping:
                mapping_candidate = cast(DogModulesConfig, dict(raw_mapping))
            else:
                mapping_candidate = coerce_dog_modules_config(user_input)

            filtered_candidate = {
                key: mapping_candidate.get(key)
                for key in MODULE_SELECTION_KEYS
                if key in mapping_candidate
            }

            try:
                # Validate modules configuration
                modules = MODULES_SCHEMA(filtered_candidate)
                typed_modules = cast(DogModulesConfig, dict(modules))
                current_dog[DOG_MODULES_FIELD] = typed_modules
                self._invalidate_profile_caches()
                return await self.async_step_add_another()

            except vol.Invalid as err:
                _LOGGER.warning("Module validation failed: %s", err)
                return self.async_show_form(
                    step_id="dog_modules",
                    data_schema=MODULES_SCHEMA,
                    errors={"base": "invalid_modules"},
                    description_placeholders=_build_dog_modules_form_placeholders(
                        dog_name=current_dog[DOG_NAME_FIELD],
                        dogs_configured=len(self._dogs),
                        smart_defaults=self._get_smart_module_defaults(current_dog),
                    ),
                )

        # Enhanced schema with smart defaults based on discovery
        enhanced_schema = self._get_enhanced_modules_schema(current_dog)

        return self.async_show_form(
            step_id="dog_modules",
            data_schema=enhanced_schema,
            description_placeholders=_build_dog_modules_form_placeholders(
                dog_name=current_dog[DOG_NAME_FIELD],
                dogs_configured=len(self._dogs),
                smart_defaults=self._get_smart_module_defaults(current_dog),
            ),
        )

    def _get_enhanced_modules_schema(self, dog_config: DogConfigData) -> vol.Schema:
        """Get enhanced modules schema with smart defaults.

        Args:
            dog_config: Dog configuration

        Returns:
            Enhanced modules schema
        """
        # Smart defaults based on discovery info or dog characteristics
        defaults = {
            MODULE_FEEDING: True,
            MODULE_WALK: True,
            MODULE_HEALTH: True,
            MODULE_GPS: self._should_enable_gps(dog_config),
            MODULE_NOTIFICATIONS: True,
        }

        return vol.Schema(
            {
                vol.Optional(
                    MODULE_FEEDING, default=defaults[MODULE_FEEDING]
                ): cv.boolean,
                vol.Optional(MODULE_WALK, default=defaults[MODULE_WALK]): cv.boolean,
                vol.Optional(
                    MODULE_HEALTH, default=defaults[MODULE_HEALTH]
                ): cv.boolean,
                vol.Optional(MODULE_GPS, default=defaults[MODULE_GPS]): cv.boolean,
                vol.Optional(
                    MODULE_NOTIFICATIONS, default=defaults[MODULE_NOTIFICATIONS]
                ): cv.boolean,
            }
        )

    def _should_enable_gps(self, dog_config: DogConfigData) -> bool:
        """Determine if GPS should be enabled by default.

        Args:
            dog_config: Dog configuration

        Returns:
            True if GPS should be enabled by default
        """
        # Enable GPS for discovered devices or large dogs
        if self._discovery_info:
            return True

        dog_size = dog_config.get("dog_size", "medium")
        return dog_size in {"large", "giant"}

    def _get_smart_module_defaults(self, dog_config: DogConfigData) -> str:
        """Get explanation for smart module defaults.

        Args:
            dog_config: Dog configuration

        Returns:
            Explanation text
        """
        reasons = []

        if self._discovery_info:
            reasons.append("GPS enabled due to discovered tracking device")

        dog_size = dog_config.get("dog_size", "medium")
        if dog_size in {"large", "giant"}:
            reasons.append("GPS recommended for larger dogs")

        return "; ".join(reasons) if reasons else "Standard defaults applied"

    async def async_step_add_another(
        self, user_input: ConfigFlowUserInput | None = None
    ) -> ConfigFlowResult:
        """Ask if user wants to add another dog with enhanced logic.

        Args:
            user_input: User provided data

        Returns:
            Config flow result
        """
        if user_input is not None:
            add_another = user_input.get("add_another", False)
            at_limit = len(self._dogs) >= MAX_DOGS_PER_INTEGRATION

            if add_another and not at_limit:
                return await self.async_step_add_dog()
            return await self.async_step_entity_profile()

        # Enhanced logic for smart recommendations
        can_add_more = len(self._dogs) < MAX_DOGS_PER_INTEGRATION

        schema = (
            vol.Schema(
                {
                    vol.Optional("add_another", default=False): cv.boolean,
                }
            )
            if can_add_more
            else vol.Schema({})
        )

        return self.async_show_form(
            step_id="add_another",
            data_schema=schema,
            description_placeholders=_build_add_another_placeholders(
                dogs_configured=len(self._dogs),
                dogs_list=self._format_dogs_list_enhanced(),
                can_add_more=can_add_more,
                max_dogs=MAX_DOGS_PER_INTEGRATION,
                performance_note=self._get_performance_note(),
            ),
        )

    def _get_performance_note(self) -> str:
        """Get performance note based on current configuration.

        Returns:
            Performance guidance text
        """
        dog_count = len(self._dogs)
        if dog_count >= 5:
            return "Consider 'basic' profile for better performance with many dogs"
        if dog_count >= 3:
            return "Multiple dogs configured - 'standard' profile recommended"
        return "Single/few dogs - 'advanced' profile available for full features"

    async def async_step_entity_profile(
        self, user_input: ConfigFlowUserInput | None = None
    ) -> ConfigFlowResult:
        """Select entity profile with performance guidance.

        Args:
            user_input: User provided data

        Returns:
            Config flow result
        """
        if user_input is not None:
            try:
                self._entity_profile = validate_profile_selection(user_input)
                modules = self._aggregate_enabled_modules()
                if modules.get(MODULE_GPS, False):
                    self._enabled_modules = modules
                    return await self.async_step_configure_modules()
                return await self.async_step_final_setup()

            except vol.Invalid as err:
                _LOGGER.warning("Profile validation failed: %s", err)
                return self.async_show_form(
                    step_id="entity_profile",
                    data_schema=PROFILE_SCHEMA,
                    errors={"base": "invalid_profile"},
                    description_placeholders={
                        "dogs_count": str(len(self._dogs)),
                        "profiles_info": self._get_profiles_info_enhanced(),
                        "profiles_summary": build_profile_summary_text(),
                        "recommendation": self._get_profile_recommendation(),
                    },
                )

        return self.async_show_form(
            step_id="entity_profile",
            data_schema=PROFILE_SCHEMA,
            description_placeholders={
                "dogs_count": str(len(self._dogs)),
                "profiles_info": self._get_profiles_info_enhanced(),
                "estimated_entities": str(self._estimate_total_entities()),
                "profiles_summary": build_profile_summary_text(),
                "recommendation": self._get_profile_recommendation(),
            },
        )

    def _get_profile_recommendation(self) -> str:
        """Get smart profile recommendation.

        Returns:
            Profile recommendation text
        """
        dog_count = len(self._dogs)
        total_modules = sum(
            sum(1 for enabled in ensure_dog_modules_mapping(dog).values() if enabled)
            for dog in self._dogs
        )

        if dog_count >= 5 or total_modules >= 20:
            return "Recommended: 'basic' profile for optimal performance"
        if dog_count >= 3 or total_modules >= 12:
            return "Recommended: 'standard' profile for balanced functionality"
        return "Recommended: 'standard' or 'advanced' profile for full features"

    async def async_step_final_setup(
        self, user_input: ConfigFlowUserInput | None = None
    ) -> ConfigFlowResult:
        """Complete setup and create config entry with enhanced validation.

        Args:
            user_input: User provided data

        Returns:
            Config flow result

        Raises:
            PawControlSetupError: If setup validation fails
        """
        async with timed_operation("final_setup"):
            if not self._dogs:
                raise PawControlSetupError("No dogs configured for setup")

            validation_results = await self._perform_comprehensive_validation()
            if not validation_results["valid"]:
                _LOGGER.error(
                    "Final validation failed: %s", validation_results["errors"]
                )
                raise PawControlSetupError(
                    f"Setup validation failed: {'; '.join(validation_results['errors'])}"
                )

            if not self._validate_profile_compatibility():
                _LOGGER.warning("Profile compatibility issues detected")

            try:
                config_data, options_data = self._build_config_entry_data()

                profile_info = ENTITY_PROFILES[self._entity_profile]
                title = self._generate_entry_title(profile_info)

                return self.async_create_entry(
                    title=title,
                    data=config_data,
                    options=options_data,
                )

            except Exception as err:
                _LOGGER.error("Final setup failed: %s", err)
                raise PawControlSetupError(f"Setup failed: {err}") from err

    async def _perform_comprehensive_validation(self) -> FinalSetupValidationResult:
        """Perform comprehensive final validation."""

        async with timed_operation("final_validation"):
            errors: list[str] = [
                f"Invalid dog configuration: {dog.get(DOG_ID_FIELD, 'unknown')}"
                for dog in self._dogs
                if not is_dog_config_valid(dog)
            ]

            estimated_entities = self._estimate_total_entities_cached()
            if estimated_entities > 200:
                errors.append(f"Too many estimated entities: {estimated_entities}")

            if self._entity_profile not in VALID_PROFILES:
                errors.append(f"Invalid profile: {self._entity_profile}")

            result: FinalSetupValidationResult = {
                "valid": len(errors) == 0,
                "errors": errors,
                "estimated_entities": estimated_entities,
            }

        config_flow_monitor.record_validation("final_validation")
        return result

    def _validate_profile_compatibility(self) -> bool:
        """Validate profile compatibility with configuration.

        Returns:
            True if profile is compatible
        """
        for dog in self._dogs:
            modules = ensure_dog_modules_mapping(dog)
            if not self._entity_factory.validate_profile_for_modules(
                self._entity_profile, modules
            ):
                return False

        return True

    def _build_config_entry_data(
        self,
    ) -> tuple[ConfigEntryDataPayload, ConfigEntryOptionsPayload]:
        """Build optimized config entry data.

        Returns:
            Tuple of (config_data, options_data)
        """
        config_data: ConfigEntryDataPayload = {
            "name": self._integration_name,
            CONF_DOGS: self._dogs,
            "entity_profile": self._entity_profile,
            "setup_timestamp": dt_util.utcnow().isoformat(),
        }

        if self._external_entities:
            config_data["external_entities"] = dict(self._external_entities)

        # Add discovery info if available
        if self._discovery_info:
            config_data["discovery_info"] = self._discovery_info

        options_data: ConfigEntryOptionsPayload = {
            "entity_profile": self._entity_profile,
            "dashboard_enabled": True,
            "dashboard_auto_create": True,
            "performance_monitoring": True,
        }

        settings = cast(ConfigFlowGlobalSettings, self._global_settings)
        performance_mode = normalize_performance_mode(
            settings.get("performance_mode"),
            fallback=cast(PerformanceMode, DEFAULT_PERFORMANCE_MODE),
        )
        options_data["performance_mode"] = performance_mode

        options_data["enable_analytics"] = bool(settings.get("enable_analytics", False))
        options_data["enable_cloud_backup"] = bool(
            settings.get("enable_cloud_backup", False)
        )
        options_data["debug_logging"] = bool(settings.get("debug_logging", False))

        options_data[CONF_DATA_RETENTION_DAYS] = cast(
            int,
            settings.get("data_retention_days", DEFAULT_DATA_RETENTION_DAYS),
        )

        # Derive default API endpoint/token from discovery results when available
        discovery_info = self._discovery_info or {}
        if discovery_info:
            host = discovery_info.get("host") or discovery_info.get("ip")
            port = discovery_info.get("port")
            properties = discovery_info.get("properties", {})

            if host and CONF_API_ENDPOINT not in options_data:
                raw_https: object = properties.get("https")
                if isinstance(raw_https, str):
                    normalized = raw_https.strip().lower()
                    https_enabled = normalized in {"true", "1", "on", "yes"}
                elif isinstance(raw_https, (bool, int, float)):
                    https_enabled = bool(raw_https)
                else:
                    https_enabled = False

                scheme = "https" if https_enabled else "http"
                if port:
                    options_data[CONF_API_ENDPOINT] = f"{scheme}://{host}:{port}"
                else:
                    options_data[CONF_API_ENDPOINT] = f"{scheme}://{host}"

            api_token = properties.get("api_key") or discovery_info.get("api_key")
            if api_token and CONF_API_TOKEN not in options_data:
                options_data[CONF_API_TOKEN] = api_token

        return config_data, options_data

    def _generate_entry_title(self, profile_info: EntityProfileDefinition) -> str:
        """Generate descriptive entry title.

        Args:
            profile_info: Profile information

        Returns:
            Entry title
        """
        return f"Paw Control ({profile_info['name']})"

    def _estimate_total_entities(self) -> int:
        """Estimate total entities with caching.

        Returns:
            Estimated total entity count
        """
        return self._estimate_total_entities_cached()

    def _format_dogs_list_enhanced(self) -> str:
        """Format enhanced list of configured dogs.

        Returns:
            Formatted dogs list with module info
        """
        if not self._dogs:
            return "No dogs configured yet."

        dogs_list = []
        for i, dog in enumerate(self._dogs, 1):
            modules = ensure_dog_modules_mapping(dog)
            enabled_modules = [name for name, enabled in modules.items() if enabled]
            module_summary = ", ".join(enabled_modules) if enabled_modules else "none"

            dogs_list.append(
                f"{i}. {dog[DOG_NAME_FIELD]} ({dog[DOG_ID_FIELD]})\n"
                f"   Size: {dog.get(CONF_DOG_SIZE, 'unknown')}, "
                f"Weight: {dog.get(CONF_DOG_WEIGHT, 0)}kg\n"
                f"   Modules: {module_summary}"
            )

        return "\n\n".join(dogs_list)

    def _get_profiles_info_enhanced(self) -> str:
        """Get enhanced entity profiles information.

        Returns:
            Formatted profiles information with performance guidance
        """
        profiles_info = []
        for config in ENTITY_PROFILES.values():
            estimated_for_profile = 0
            for dog in self._dogs:
                modules = ensure_dog_modules_mapping(dog)
                # Rough estimation without full factory
                estimated_for_profile += sum(
                    3 if enabled else 0 for enabled in modules.values()
                )

            profiles_info.append(
                f"• {config['name']}: {config['description']}\n"
                f"  Performance: {config['performance_impact']}\n"
                f"  Estimated entities: ~{estimated_for_profile} per dog\n"
                f"  Best for: {config['recommended_for']}"
            )
        return "\n\n".join(profiles_info)

    @staticmethod
    def _normalise_string_list(values: Any) -> list[str]:
        """Normalise arbitrary iterables to a list of non-empty strings."""

        if not values:
            return []

        normalised: list[str] = []
        for value in values:
            if value is None:
                continue
            if isinstance(value, str):
                candidate = value.strip()
                if candidate:
                    normalised.append(candidate)
                continue
            normalised.append(str(value))
        return normalised

    def _render_reauth_health_status(self, summary: ReauthHealthSummary) -> str:
        """Render a concise description of the reauth health snapshot."""

        healthy = summary.get("healthy", True)
        validated = summary.get("validated_dogs", 0)
        total = summary.get("total_dogs", 0)
        parts = [
            "Status: " + ("healthy" if healthy else "attention required"),
            f"Validated dogs: {validated}/{total}",
        ]

        issues = self._normalise_string_list(summary.get("issues", []))
        if issues:
            parts.append("Issues: " + ", ".join(issues))

        warnings = self._normalise_string_list(summary.get("warnings", []))
        if warnings:
            parts.append("Warnings: " + ", ".join(warnings))

        invalid_modules = summary.get("invalid_modules")
        if isinstance(invalid_modules, int) and invalid_modules > 0:
            parts.append(f"Modules needing review: {invalid_modules}")

        return "; ".join(parts)

    def _build_reauth_updates(
        self, summary: ReauthHealthSummary
    ) -> tuple[ReauthDataUpdates, ReauthOptionsUpdates]:
        """Build typed update payloads for a successful reauth."""

        timestamp = dt_util.utcnow().isoformat()

        data_updates: ReauthDataUpdates = {
            "reauth_timestamp": timestamp,
            "reauth_version": self.VERSION,
            "health_status": summary.get("healthy", True),
            "health_validated_dogs": summary.get("validated_dogs", 0),
            "health_total_dogs": summary.get("total_dogs", 0),
        }

        options_updates: ReauthOptionsUpdates = {
            "last_reauth": timestamp,
            "reauth_health_issues": self._normalise_string_list(
                summary.get("issues", [])
            ),
            "reauth_health_warnings": self._normalise_string_list(
                summary.get("warnings", [])
            ),
            "last_reauth_summary": self._render_reauth_health_status(summary),
        }

        return data_updates, options_updates

    def _build_reauth_placeholders(
        self, summary: ReauthHealthSummary
    ) -> ReauthPlaceholders:
        """Generate description placeholders for the reauth confirmation form."""

        if not self.reauth_entry:
            raise ConfigEntryAuthFailed("No entry available for reauthentication")

        total_dogs = summary.get("total_dogs")
        if total_dogs is None:
            total_dogs = len(self.reauth_entry.data.get(CONF_DOGS, []))

        profile_raw = self.reauth_entry.options.get("entity_profile", "unknown")
        profile = profile_raw if isinstance(profile_raw, str) else str(profile_raw)

        placeholders = clone_placeholders(REAUTH_PLACEHOLDERS_TEMPLATE)
        placeholders["integration_name"] = self.reauth_entry.title
        placeholders["dogs_count"] = str(total_dogs)
        placeholders["current_profile"] = profile
        placeholders["health_status"] = self._render_reauth_health_status(summary)
        return cast(ReauthPlaceholders, freeze_placeholders(placeholders))

    async def async_step_reauth(
        self, entry_data: ConfigEntryDataPayload
    ) -> ConfigFlowResult:
        """PLATINUM: Handle reauthentication flow with enhanced error handling.

        Args:
            entry_data: Existing config entry data

        Returns:
            Config flow result

        Raises:
            ConfigEntryAuthFailed: If entry cannot be found or is invalid
        """
        _LOGGER.debug("Starting reauthentication flow for entry data: %s", entry_data)

        try:
            # PLATINUM: Enhanced entry validation with timeout
            async with asyncio.timeout(REAUTH_TIMEOUT_SECONDS):
                self.reauth_entry = self.hass.config_entries.async_get_entry(
                    self.context["entry_id"]
                )

            if not self.reauth_entry:
                _LOGGER.error("Reauthentication failed: entry not found")
                raise ConfigEntryAuthFailed(
                    "Config entry not found for reauthentication"
                )

            # PLATINUM: Validate the entry is in a reauth-able state with timeout
            try:
                async with asyncio.timeout(CONFIG_HEALTH_CHECK_TIMEOUT):
                    await self._validate_reauth_entry_enhanced(self.reauth_entry)
            except TimeoutError as err:
                _LOGGER.error("Entry validation timeout during reauth: %s", err)
                raise ConfigEntryAuthFailed("Entry validation timeout") from err
            except ValidationError as err:
                _LOGGER.error("Reauthentication validation failed: %s", err)
                raise ConfigEntryAuthFailed(f"Entry validation failed: {err}") from err

            return await self.async_step_reauth_confirm()

        except TimeoutError as err:
            _LOGGER.error("Reauth step timeout: %s", err)
            raise ConfigEntryAuthFailed("Reauthentication timeout") from err
        except Exception as err:
            _LOGGER.error("Unexpected reauth error: %s", err)
            raise ConfigEntryAuthFailed(f"Reauthentication failed: {err}") from err

    async def _validate_reauth_entry_enhanced(self, entry: ConfigEntry) -> None:
        """PLATINUM: Enhanced config entry validation for reauthentication with graceful degradation.

        Args:
            entry: Config entry to validate

        Raises:
            ValidationError: If entry is invalid
        """
        # Check basic entry structure
        dogs = entry.data.get(CONF_DOGS, [])
        if not dogs:
            _LOGGER.debug(
                "Reauthentication proceeding without stored dog data for entry %s",
                entry.entry_id,
            )
            return

        # Validate dogs configuration with graceful error handling
        invalid_dogs = []

        for dog in dogs:
            try:
                if not is_dog_config_valid(dog):
                    dog_id = dog.get(DOG_ID_FIELD, "unknown")
                    invalid_dogs.append(dog_id)
            except Exception as err:
                # PLATINUM: Graceful degradation for corrupted dog data
                _LOGGER.warning(
                    "Dog validation error during reauth (non-critical): %s", err
                )
                dog_id = dog.get(DOG_ID_FIELD, "corrupted")
                invalid_dogs.append(dog_id)

        if invalid_dogs:
            _LOGGER.warning(
                "Invalid dog configurations found during reauth: %s",
                ", ".join(invalid_dogs),
            )
            # Only fail if ALL dogs are invalid
            if len(invalid_dogs) == len(dogs):
                raise ValidationError(
                    "entry_dogs",
                    constraint=f"All dog configurations are invalid: {', '.join(invalid_dogs)}",
                )

        # Check profile validity with fallback
        profile = entry.options.get("entity_profile", "standard")
        if profile not in VALID_PROFILES:
            _LOGGER.warning(
                "Invalid entity profile '%s' during reauth, will use 'standard'",
                profile,
            )
            # Don't fail reauth for invalid profile, will be corrected

    def _aggregate_enabled_modules(self) -> DogModulesConfig:
        """Aggregate enabled modules across all configured dogs."""

        aggregated: DogModulesConfig = {}
        for dog in self._dogs:
            modules = ensure_dog_modules_mapping(dog)
            for module, enabled in modules.items():
                if module not in MODULE_TOGGLE_KEYS:
                    continue

                module_key = cast(ModuleToggleKey, module)
                if enabled:
                    aggregated[module_key] = True
                else:
                    aggregated.setdefault(module_key, False)

        return aggregated

    async def async_step_configure_modules(
        self, user_input: ModuleConfigurationStepInput | None = None
    ) -> ConfigFlowResult:
        """Update cached module summary before delegating to mixin."""

        self._enabled_modules = self._aggregate_enabled_modules()
        return await super().async_step_configure_modules(user_input)

    async def async_step_configure_dashboard(
        self, user_input: DashboardConfigurationStepInput | None = None
    ) -> ConfigFlowResult:
        """Delegate dashboard configuration to the dashboard mixin implementation."""

        return await DashboardFlowMixin.async_step_configure_dashboard(self, user_input)

    async def async_step_reauth_confirm(
        self, user_input: ConfigFlowUserInput | None = None
    ) -> ConfigFlowResult:
        """PLATINUM: Confirm reauthentication with enhanced validation and error handling.

        Args:
            user_input: User provided data

        Returns:
            Config flow result

        Raises:
            ConfigEntryAuthFailed: If reauthentication fails
        """
        if not self.reauth_entry:
            raise ConfigEntryAuthFailed("No entry available for reauthentication")

        errors: dict[str, str] = {}
        summary: ReauthHealthSummary | None = None

        if user_input is not None:
            if user_input.get("confirm", False):
                try:
                    # PLATINUM: Enhanced validation for reauthentication with timeout
                    async with asyncio.timeout(REAUTH_TIMEOUT_SECONDS):
                        await self.async_set_unique_id(self.reauth_entry.unique_id)
                        self._abort_if_unique_id_mismatch(reason="wrong_account")

                        # PLATINUM: Perform configuration health check with graceful degradation
                        try:
                            async with asyncio.timeout(CONFIG_HEALTH_CHECK_TIMEOUT):
                                summary = cast(
                                    ReauthHealthSummary,
                                    await self._check_config_health_enhanced(
                                        self.reauth_entry
                                    ),
                                )
                        except TimeoutError:
                            _LOGGER.warning(
                                "Config health check timeout - proceeding with reauth"
                            )
                            summary = {
                                "healthy": True,
                                "issues": ["Health check timeout"],
                                "warnings": [],
                                "validated_dogs": 0,
                                "total_dogs": len(
                                    self.reauth_entry.data.get(CONF_DOGS, [])
                                ),
                            }
                        except Exception as err:
                            _LOGGER.warning(
                                "Config health check failed: %s - proceeding with reauth",
                                err,
                            )
                            summary = {
                                "healthy": True,
                                "issues": [f"Health check error: {err}"],
                                "warnings": [],
                                "validated_dogs": 0,
                                "total_dogs": len(
                                    self.reauth_entry.data.get(CONF_DOGS, [])
                                ),
                            }

                        if summary is None:
                            summary = {
                                "healthy": True,
                                "issues": [],
                                "warnings": [],
                                "validated_dogs": 0,
                                "total_dogs": len(
                                    self.reauth_entry.data.get(CONF_DOGS, [])
                                ),
                            }

                        if not summary.get("healthy", True):
                            _LOGGER.warning(
                                "Configuration health issues detected: %s",
                                summary.get("issues", []),
                            )
                            # Don't fail reauth for health issues, just warn

                        # PLATINUM: Update entry with reauth timestamp and health info
                        data_updates, options_updates = self._build_reauth_updates(
                            summary
                        )

                        return await self.async_update_reload_and_abort(
                            self.reauth_entry,
                            data_updates=data_updates,
                            options_updates=options_updates,
                            reason="reauth_successful",
                        )

                except TimeoutError as err:
                    _LOGGER.error("Reauth confirmation timeout: %s", err)
                    errors["base"] = "reauth_timeout"
                except ConfigEntryAuthFailed:
                    raise
                except Exception as err:
                    _LOGGER.error("Reauthentication failed: %s", err)
                    errors["base"] = "reauth_failed"
            else:
                errors["base"] = "reauth_unsuccessful"

        # Show enhanced confirmation form with graceful error handling
        if summary is None:
            try:
                async with asyncio.timeout(CONFIG_HEALTH_CHECK_TIMEOUT):
                    summary = cast(
                        ReauthHealthSummary,
                        await self._check_config_health_enhanced(self.reauth_entry),
                    )
            except Exception as err:
                _LOGGER.warning("Error getting reauth display info: %s", err)
                summary = {
                    "healthy": True,
                    "issues": [],
                    "warnings": [f"Status check failed: {err}"],
                    "validated_dogs": 0,
                    "total_dogs": len(self.reauth_entry.data.get(CONF_DOGS, [])),
                }

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required("confirm", default=True): cv.boolean,
                }
            ),
            errors=errors,
            description_placeholders=dict(self._build_reauth_placeholders(summary)),
        )

    async def _check_config_health_enhanced(
        self, entry: ConfigEntry
    ) -> ReauthHealthSummary:
        """PLATINUM: Enhanced configuration health check with graceful degradation."""

        dogs = [dict(dog) for dog in self._normalise_entry_dogs(entry)]
        issues: list[str] = []
        warnings: list[str] = []
        valid_dogs = 0
        invalid_modules = 0

        for index, dog in enumerate(dogs):
            dog_id_value = dog.get(DOG_ID_FIELD)
            dog_id = (
                dog_id_value
                if isinstance(dog_id_value, str) and dog_id_value
                else f"dog_{index}"
            )
            try:
                if is_dog_config_valid(dog):
                    valid_dogs += 1
                else:
                    issues.append(f"Invalid dog config: {dog_id}")
            except Exception as err:
                warnings.append(f"Dog config validation error for {dog_id}: {err}")

            modules = dog.get(CONF_MODULES)
            if isinstance(modules, Mapping):
                for module, enabled in modules.items():
                    if not isinstance(enabled, bool):
                        invalid_modules += 1
                        warnings.append(
                            f"Module '{module}' has invalid flag for {dog_id}"
                        )
            elif modules not in (None, {}):
                invalid_modules += 1
                warnings.append(f"Modules payload invalid for {dog_id}")

        if valid_dogs == 0 and dogs:
            issues.append("No valid dog configurations found")

        profile_raw = entry.options.get("entity_profile", "standard")
        profile = profile_raw if isinstance(profile_raw, str) else str(profile_raw)
        if profile not in VALID_PROFILES:
            warnings.append(f"Invalid profile '{profile}' - will use 'standard'")

        try:
            dog_ids = [
                dog_id
                for dog_id in (
                    dog.get(DOG_ID_FIELD) for dog in dogs if dog.get(DOG_ID_FIELD)
                )
                if isinstance(dog_id, str)
            ]
            if len(dog_ids) != len(set(dog_ids)):
                issues.append("Duplicate dog IDs detected")
        except Exception as err:
            warnings.append(f"Dog ID validation error: {err}")

        estimated_entities = 0
        try:
            factory = EntityFactory(None)
            estimated_entities = 0
            for dog in dogs:
                if not is_dog_config_valid(dog):
                    continue
                modules_payload = dog.get(CONF_MODULES, {})
                modules_mapping = (
                    modules_payload if isinstance(modules_payload, Mapping) else {}
                )
                estimated_entities += factory.estimate_entity_count(
                    profile, cast(DogModulesConfig, dict(modules_mapping))
                )
            if estimated_entities > 200:
                warnings.append(
                    f"High entity count ({estimated_entities}) may impact performance"
                )
        except Exception as err:
            warnings.append(f"Entity estimation failed: {err}")

        summary: ReauthHealthSummary = {
            "healthy": len(issues) == 0,
            "issues": self._normalise_string_list(issues),
            "warnings": self._normalise_string_list(warnings),
            "validated_dogs": valid_dogs,
            "total_dogs": len(dogs),
            "dogs_count": len(dogs),
            "valid_dogs": valid_dogs,
            "profile": profile,
            "estimated_entities": estimated_entities,
        }
        if invalid_modules:
            summary["invalid_modules"] = invalid_modules
        return summary

    async def _get_health_status_summary_safe(self, entry: ConfigEntry) -> str:
        """PLATINUM: Get health status summary with graceful error handling."""

        try:
            async with asyncio.timeout(CONFIG_HEALTH_CHECK_TIMEOUT):
                summary = cast(
                    ReauthHealthSummary,
                    await self._check_config_health_enhanced(entry),
                )
            return self._render_reauth_health_status(summary)
        except TimeoutError:
            return "Health check timeout"
        except Exception as err:
            _LOGGER.debug("Health status summary error: %s", err)
            return f"Health check failed: {err}"

    async def async_step_reconfigure(
        self, user_input: ConfigFlowUserInput | None = None
    ) -> ConfigFlowResult:
        """Handle reconfiguration with typed telemetry and validation."""

        entry_id = self.context.get("entry_id")
        entry = (
            self.hass.config_entries.async_get_entry(entry_id)
            if entry_id is not None
            else None
        )
        if entry is None:
            raise ConfigEntryNotReady("Config entry not found for reconfiguration")

        dogs, merge_notes = self._extract_entry_dogs(entry)
        current_profile = self._resolve_entry_profile(entry)
        form_schema = vol.Schema(
            {
                vol.Required("entity_profile", default=current_profile): vol.In(
                    VALID_PROFILES
                ),
            }
        )
        base_placeholders = await self._build_reconfigure_placeholders(
            entry, dogs, current_profile, merge_notes
        )

        if user_input is not None:
            try:
                profile_data = cast(
                    ReconfigureProfileInput, PROFILE_SCHEMA(dict(user_input))
                )
                new_profile = profile_data["entity_profile"]
            except vol.Invalid as err:
                error_placeholders = dict(base_placeholders)
                error_placeholders["error_details"] = str(err)
                return self.async_show_form(
                    step_id="reconfigure",
                    data_schema=form_schema,
                    errors={"base": "invalid_profile"},
                    description_placeholders=error_placeholders,
                )

            if new_profile == current_profile:
                error_placeholders = dict(base_placeholders)
                error_placeholders["requested_profile"] = new_profile
                return self.async_show_form(
                    step_id="reconfigure",
                    data_schema=form_schema,
                    errors={"base": "profile_unchanged"},
                    description_placeholders=error_placeholders,
                )

            unique_id = entry.unique_id
            if unique_id:
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_mismatch(reason="wrong_account")
            else:
                _LOGGER.debug(
                    "Skipping unique_id guard for reconfigure entry %s", entry.entry_id
                )

            compatibility = self._check_profile_compatibility(new_profile, dogs)
            if compatibility["warnings"]:
                _LOGGER.warning(
                    "Profile %s compatibility warnings: %s",
                    new_profile,
                    "; ".join(compatibility["warnings"]),
                )

            health_check = await self._check_config_health_enhanced(entry)
            if not health_check.get("healthy", True):
                issues = self._normalise_string_list(health_check.get("issues", []))
                if issues:
                    _LOGGER.warning(
                        "Configuration health issues before reconfigure: %s",
                        "; ".join(issues),
                    )

            timestamp = dt_util.utcnow().isoformat()
            estimated_entities = await self._estimate_entities_for_reconfigure(
                dogs, new_profile
            )
            previous_profile = current_profile
            valid_dogs = sum(1 for dog in dogs if is_dog_config_valid(dog))

            telemetry: ReconfigureTelemetry = {
                "requested_profile": new_profile,
                "previous_profile": previous_profile,
                "dogs_count": len(dogs),
                "estimated_entities": estimated_entities,
                "timestamp": timestamp,
                "version": self.VERSION,
            }
            if compatibility["warnings"]:
                telemetry["compatibility_warnings"] = compatibility["warnings"]
            telemetry["health_summary"] = health_check
            telemetry["valid_dogs"] = valid_dogs
            merge_notes_normalised = self._normalise_string_list(merge_notes)
            if merge_notes_normalised:
                telemetry["merge_notes"] = merge_notes_normalised

            data_updates: ReconfigureDataUpdates = {
                "entity_profile": new_profile,
                "reconfigure_timestamp": timestamp,
                "reconfigure_version": self.VERSION,
            }
            options_updates: ReconfigureOptionsUpdates = {
                "entity_profile": new_profile,
                "last_reconfigure": timestamp,
                "previous_profile": previous_profile,
                "reconfigure_telemetry": telemetry,
            }

            return await self.async_update_reload_and_abort(
                entry,
                data_updates=data_updates,
                options_updates=options_updates,
            )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=form_schema,
            description_placeholders=dict(base_placeholders),
        )

    def _extract_entry_dogs(
        self, entry: ConfigEntry
    ) -> tuple[list[DogConfigData], list[str]]:
        """Return the typed dog configuration list for the given entry."""

        merged: dict[str, DogConfigData] = {}
        merge_notes: list[str] = []

        for dog in self._normalise_entry_dogs(entry):
            self._merge_dog_entry(
                merged,
                dog,
                merge_notes,
                source="config_entry_data",
            )

        if isinstance(entry.options, Mapping):
            for dog in self._normalise_dogs_payload(entry.options.get(CONF_DOGS)):
                self._merge_dog_entry(
                    merged,
                    dog,
                    merge_notes,
                    source="config_entry_options",
                )

            for dog in self._normalise_dogs_payload(
                entry.options.get(CONF_DOG_OPTIONS)
            ):
                self._merge_dog_entry(
                    merged,
                    dog,
                    merge_notes,
                    source="options_dog_options",
                )

        for dog in self._normalise_dogs_payload(entry.data.get(CONF_DOG_OPTIONS)):
            self._merge_dog_entry(
                merged,
                dog,
                merge_notes,
                source="data_dog_options",
            )

        return list(merged.values()), merge_notes

    def _resolve_entry_profile(self, entry: ConfigEntry) -> str:
        """Resolve the current profile from entry options or data."""

        profile_candidate = entry.options.get("entity_profile")
        if isinstance(profile_candidate, str) and profile_candidate in VALID_PROFILES:
            return profile_candidate

        data_profile = entry.data.get("entity_profile")
        if isinstance(data_profile, str) and data_profile in VALID_PROFILES:
            return data_profile

        return DEFAULT_PROFILE

    async def _build_reconfigure_placeholders(
        self,
        entry: ConfigEntry,
        dogs: list[DogConfigData],
        profile: str,
        merge_notes: Sequence[str],
    ) -> ReconfigureFormPlaceholders:
        """Build description placeholders for the reconfigure form."""

        estimated_entities = await self._estimate_entities_for_reconfigure(
            dogs, profile
        )
        valid_dogs = sum(1 for dog in dogs if is_dog_config_valid(dog))
        invalid_dogs = max(len(dogs) - valid_dogs, 0)
        merge_lines = self._normalise_string_list(list(merge_notes))
        placeholders: ReconfigureFormPlaceholders = cast(
            ReconfigureFormPlaceholders,
            clone_placeholders(RECONFIGURE_FORM_PLACEHOLDERS_TEMPLATE),
        )
        placeholders.update(
            {
                "current_profile": profile,
                "profiles_info": self._get_profiles_info_enhanced(),
                "dogs_count": str(len(dogs)),
                "compatibility_info": self._get_compatibility_info(profile, dogs),
                "estimated_entities": str(estimated_entities),
                "reconfigure_valid_dogs": str(valid_dogs),
                "reconfigure_invalid_dogs": str(invalid_dogs),
                "reconfigure_merge_notes": (
                    "\n".join(merge_lines)
                    if merge_lines
                    else "No merge adjustments detected"
                ),
            }
        )
        placeholders.update(
            self._reconfigure_history_placeholders(
                cast(Mapping[str, JSONValue], entry.options)
            )
        )
        return placeholders

    def _reconfigure_history_placeholders(
        self, options: Mapping[str, JSONValue]
    ) -> ReconfigureFormPlaceholders:
        """Return placeholders describing the latest reconfigure telemetry."""

        telemetry_raw = options.get("reconfigure_telemetry")
        telemetry = telemetry_raw if isinstance(telemetry_raw, Mapping) else None
        timestamp_raw = options.get("last_reconfigure")

        history: ReconfigureFormPlaceholders = cast(
            ReconfigureFormPlaceholders,
            clone_placeholders(RECONFIGURE_FORM_PLACEHOLDERS_TEMPLATE),
        )

        if telemetry is None:
            history["last_reconfigure"] = self._format_local_timestamp(timestamp_raw)
            history["reconfigure_requested_profile"] = "Not recorded"
            history["reconfigure_previous_profile"] = "Not recorded"
            history["reconfigure_dogs"] = "0"
            history["reconfigure_entities"] = "0"
            history["reconfigure_health"] = "No recent health summary"
            history["reconfigure_warnings"] = "None"
            return history

        requested_profile = str(telemetry.get("requested_profile", "")) or "Unknown"
        previous_profile = str(telemetry.get("previous_profile", "")) or "Unknown"
        dogs_count = telemetry.get("dogs_count")
        estimated_entities = telemetry.get("estimated_entities")
        warnings_raw = telemetry.get("compatibility_warnings")
        warnings = (
            [str(item) for item in warnings_raw]
            if isinstance(warnings_raw, Sequence)
            and not isinstance(warnings_raw, str | bytes)
            else []
        )
        health_summary = telemetry.get("health_summary")
        merge_notes = self._normalise_string_list(telemetry.get("merge_notes"))
        last_recorded = telemetry.get("timestamp") or timestamp_raw

        history["last_reconfigure"] = self._format_local_timestamp(last_recorded)
        history["reconfigure_requested_profile"] = requested_profile
        history["reconfigure_previous_profile"] = previous_profile
        history["reconfigure_dogs"] = (
            str(int(dogs_count)) if isinstance(dogs_count, int | float) else "0"
        )
        history["reconfigure_entities"] = (
            str(int(estimated_entities))
            if isinstance(estimated_entities, int | float)
            else "0"
        )
        history["reconfigure_health"] = self._summarise_health_summary(health_summary)
        history["reconfigure_warnings"] = ", ".join(warnings) if warnings else "None"
        if merge_notes:
            history["reconfigure_merge_notes"] = "\n".join(merge_notes)
        return history

    def _format_local_timestamp(self, timestamp: Any) -> str:
        """Return a human-friendly representation for an ISO timestamp."""

        if not isinstance(timestamp, str) or not timestamp:
            return "Never reconfigured"

        parse_datetime = getattr(dt_util, "parse_datetime", None)
        parsed = parse_datetime(timestamp) if callable(parse_datetime) else None
        if parsed is None:
            candidate = timestamp.replace("Z", "+00:00")
            try:
                parsed = datetime.fromisoformat(candidate)
            except ValueError:
                return timestamp

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt_util.UTC)

        as_local = getattr(dt_util, "as_local", None)
        local_dt = as_local(parsed) if callable(as_local) else parsed.astimezone()
        return local_dt.strftime("%Y-%m-%d %H:%M:%S %Z")

    def _summarise_health_summary(self, summary: Any) -> str:
        """Convert a health summary mapping into a user-facing string."""

        if not isinstance(summary, Mapping):
            return "No recent health summary"

        healthy = bool(summary.get("healthy", True))
        issues = self._normalise_string_list(summary.get("issues"))
        warnings = self._normalise_string_list(summary.get("warnings"))

        if healthy and not issues and not warnings:
            return "Healthy"

        segments: list[str] = []
        if not healthy:
            segments.append("Issues detected")
        if issues:
            segments.append(f"Issues: {', '.join(issues)}")
        if warnings:
            segments.append(f"Warnings: {', '.join(warnings)}")

        return " | ".join(segments)

    def _normalise_entry_dogs(self, entry: ConfigEntry) -> list[DogConfigData]:
        """Normalise raw dog payloads from a config entry to typed dictionaries."""

        return self._normalise_dogs_payload(
            entry.data.get(CONF_DOGS), preserve_empty_name=True
        )

    def _clone_merge_value(self, value: Any) -> Any:
        """Return a defensive copy of ``value`` for nested migration merges."""

        if isinstance(value, Mapping):
            return self._merge_nested_mapping(value, {})
        if isinstance(value, Sequence) and not isinstance(
            value, str | bytes | bytearray
        ):
            return [self._clone_merge_value(item) for item in value]
        return value

    def _sequence_requests_removal(self, value: Sequence[Any]) -> bool:
        """Return ``True`` when ``value`` signals that the list should clear."""

        for item in value:
            if isinstance(item, Mapping) and item.get(_LIST_REMOVE_DIRECTIVE):
                return True
            if item == _LIST_REMOVE_DIRECTIVE:
                return True
        return False

    def _sequence_contains(self, items: Sequence[Any], candidate: Any) -> bool:
        """Return ``True`` when ``candidate`` already exists in ``items``."""

        return any(existing == candidate for existing in items)

    def _merge_sequence_values(
        self,
        existing: Any,
        override: Sequence[Any],
    ) -> list[Any]:
        """Merge sequence values without mutating the originals."""

        if self._sequence_requests_removal(override):
            return []

        existing_sequence: Sequence[Any] | None
        if isinstance(existing, Sequence) and not isinstance(
            existing, str | bytes | bytearray
        ):
            existing_sequence = existing
        else:
            existing_sequence = None

        override_items = [self._clone_merge_value(item) for item in override]

        if override_items:
            merged_items = list(override_items)
            if existing_sequence is not None:
                for item in existing_sequence:
                    cloned_item = self._clone_merge_value(item)
                    if not self._sequence_contains(merged_items, cloned_item):
                        merged_items.append(cloned_item)
            return merged_items

        if existing_sequence is None:
            return []

        return [self._clone_merge_value(item) for item in existing_sequence]

    def _merge_nested_mapping(
        self,
        base: Mapping[str, object] | None,
        override: Mapping[str, object],
    ) -> JSONMutableMapping:
        """Merge nested mappings without mutating the original payloads."""

        merged: JSONMutableMapping = {}

        if isinstance(base, Mapping):
            for key, value in base.items():
                merged[key] = self._clone_merge_value(value)

        for key, value in override.items():
            if value is None:
                continue
            if isinstance(value, Mapping):
                existing = merged.get(key)
                existing_mapping = existing if isinstance(existing, Mapping) else None
                merged[key] = self._merge_nested_mapping(existing_mapping, value)
                continue
            if isinstance(value, Sequence) and not isinstance(
                value, str | bytes | bytearray
            ):
                merged[key] = self._merge_sequence_values(merged.get(key), value)
                continue
            merged[key] = value

        return merged

    def _merge_dog_entry(
        self,
        merged: dict[str, DogConfigData],
        candidate: DogConfigData,
        merge_notes: list[str],
        *,
        source: str,
    ) -> None:
        """Merge ``candidate`` into ``merged`` keyed by dog identifier."""

        dog_id = candidate.get(DOG_ID_FIELD)
        if not isinstance(dog_id, str) or not dog_id:
            return

        source_labels = {
            "config_entry_data": "config entry data",
            "config_entry_options": "config entry options",
            "options_dog_options": "dog options",
            "data_dog_options": "legacy dog options data",
        }
        source_label = source_labels.get(source, source.replace("_", " "))
        baseline_source = source == "config_entry_data"

        display_name = candidate.get(DOG_NAME_FIELD)
        candidate_name = (
            display_name.strip()
            if isinstance(display_name, str) and display_name.strip()
            else dog_id
        )

        existing = merged.get(dog_id)
        if existing is None:
            merged[dog_id] = candidate
            if not baseline_source:
                merge_notes.append(
                    f"{candidate_name}: your {source_label} added a dog configuration."
                )
            return

        combined: JSONMutableMapping = dict(existing)

        existing_name_value = existing.get(DOG_NAME_FIELD)
        existing_name = (
            existing_name_value.strip()
            if isinstance(existing_name_value, str) and existing_name_value.strip()
            else ""
        )

        module_changes: list[str] = []
        modules_override = candidate.get(DOG_MODULES_FIELD)
        if isinstance(modules_override, Mapping):
            current_modules = coerce_dog_modules_config(
                cast(Mapping[str, object] | None, combined.get(DOG_MODULES_FIELD))
            )
            override_modules = coerce_dog_modules_config(modules_override)
            merged_modules: DogModulesConfig = cast(
                DogModulesConfig, dict(current_modules)
            )
            for module, enabled in override_modules.items():
                toggle = cast(ModuleToggleKey, module)
                enabled_flag = cast(bool, enabled)
                if current_modules.get(toggle) != enabled_flag:
                    action = "enabled" if enabled_flag else "disabled"
                    module_changes.append(f"{action} {module}")
                merged_modules[toggle] = enabled_flag
            combined[DOG_MODULES_FIELD] = merged_modules

        for key, value in candidate.items():
            if key in (DOG_ID_FIELD, DOG_MODULES_FIELD):
                continue
            if key == DOG_NAME_FIELD:
                if isinstance(value, str):
                    trimmed_name = value.strip()
                    if not trimmed_name:
                        continue
                    if trimmed_name == dog_id:
                        existing_name_value = combined.get(DOG_NAME_FIELD)
                        if (
                            not isinstance(existing_name_value, str)
                            or not existing_name_value.strip()
                        ):
                            combined[DOG_NAME_FIELD] = trimmed_name
                    else:
                        combined[DOG_NAME_FIELD] = trimmed_name
                continue
            if value is None:
                continue
            if isinstance(value, Mapping):
                existing_value = combined.get(key)
                existing_mapping = (
                    existing_value if isinstance(existing_value, Mapping) else None
                )
                combined[key] = self._merge_nested_mapping(existing_mapping, value)
                continue
            if isinstance(value, Sequence) and not isinstance(
                value, str | bytes | bytearray
            ):
                combined[key] = self._merge_sequence_values(combined.get(key), value)
                continue
            combined[key] = value

        merged[dog_id] = cast(DogConfigData, combined)

        updated_name_value = combined.get(DOG_NAME_FIELD)
        updated_name = (
            updated_name_value.strip()
            if isinstance(updated_name_value, str) and updated_name_value.strip()
            else ""
        )
        display_target = updated_name or dog_id

        if baseline_source:
            return

        if module_changes:
            formatted_changes = ", ".join(sorted(module_changes))
            merge_notes.append(
                f"{display_target}: your {source_label} {formatted_changes}."
            )

        if updated_name and updated_name != existing_name:
            if existing_name:
                merge_notes.append(
                    f"{dog_id}: your {source_label} renamed this dog from '{existing_name}' to '{updated_name}'."
                )
            else:
                merge_notes.append(
                    f"{dog_id}: your {source_label} set the name to '{updated_name}'."
                )

    def _normalise_dogs_payload(
        self, payload: Any, *, preserve_empty_name: bool = False
    ) -> list[DogConfigData]:
        """Return a list of dog mappings extracted from ``payload``."""

        dogs: list[DogConfigData] = []

        if isinstance(payload, Sequence) and not isinstance(
            payload, str | bytes | bytearray
        ):
            for raw in payload:
                candidate = self._build_dog_candidate(
                    raw, preserve_empty_name=preserve_empty_name
                )
                if candidate is not None:
                    dogs.append(candidate)
            return dogs

        if isinstance(payload, Mapping):
            for key, raw in payload.items():
                fallback_id = key if isinstance(key, str) and key else None
                candidate = self._build_dog_candidate(
                    raw,
                    fallback_id=fallback_id,
                    preserve_empty_name=preserve_empty_name,
                )
                if candidate is not None:
                    dogs.append(candidate)

        return dogs

    def _build_dog_candidate(
        self,
        raw: Any,
        *,
        fallback_id: str | None = None,
        preserve_empty_name: bool = False,
    ) -> DogConfigData | None:
        """Normalise ``raw`` dog payloads into ``DogConfigData`` mappings."""

        if not isinstance(raw, Mapping):
            return None

        candidate: JSONMutableMapping = {
            str(key): value for key, value in raw.items() if isinstance(key, str)
        }

        dog_id = self._resolve_dog_identifier(candidate, fallback_id)
        if dog_id is None:
            return None
        candidate[DOG_ID_FIELD] = dog_id

        legacy_name = candidate.get("name")
        dog_name = candidate.get(DOG_NAME_FIELD)
        if not isinstance(dog_name, str):
            if isinstance(legacy_name, str) and legacy_name.strip():
                candidate[DOG_NAME_FIELD] = legacy_name.strip()
            else:
                candidate[DOG_NAME_FIELD] = dog_id
        elif not dog_name.strip():
            if preserve_empty_name:
                candidate[DOG_NAME_FIELD] = dog_name
            elif isinstance(legacy_name, str) and legacy_name.strip():
                candidate[DOG_NAME_FIELD] = legacy_name.strip()
            else:
                candidate[DOG_NAME_FIELD] = dog_id
        else:
            candidate[DOG_NAME_FIELD] = dog_name.strip()

        modules = candidate.get(DOG_MODULES_FIELD)
        if isinstance(modules, Mapping):
            candidate[DOG_MODULES_FIELD] = dict(ensure_dog_modules_mapping(candidate))
        elif isinstance(modules, Sequence) and not isinstance(
            modules, str | bytes | bytearray
        ):
            toggles: dict[str, bool] = {}
            for module in modules:
                if isinstance(module, str):
                    key = module.strip()
                    if key in MODULE_TOGGLE_KEYS:
                        toggles[key] = True
                    continue

                if not isinstance(module, Mapping):
                    continue

                legacy_key = None
                for key_name in ("module", "key", "name"):
                    raw_key = module.get(key_name)
                    if isinstance(raw_key, str) and raw_key.strip():
                        legacy_key = raw_key.strip()
                        break

                if legacy_key is None or legacy_key not in MODULE_TOGGLE_KEYS:
                    continue

                enabled_value = module.get("enabled")
                if "value" in module:
                    enabled_value = module["value"]
                toggles[legacy_key] = self._coerce_legacy_toggle(enabled_value)

            if toggles:
                candidate[DOG_MODULES_FIELD] = toggles
            else:
                candidate.pop(DOG_MODULES_FIELD, None)
        elif modules is not None:
            candidate.pop(DOG_MODULES_FIELD, None)

        return cast(DogConfigData, candidate)

    @staticmethod
    def _resolve_dog_identifier(
        candidate: Mapping[str, object], fallback_id: str | None
    ) -> str | None:
        """Return a trimmed dog identifier from legacy payloads when available."""

        potential_keys = (
            DOG_ID_FIELD,
            "id",
            "dogId",
            "dog_identifier",
            "identifier",
            "unique_id",
            "uniqueId",
        )

        for key in potential_keys:
            value = candidate.get(key)
            if isinstance(value, str):
                trimmed = value.strip()
                if trimmed:
                    return trimmed

        if isinstance(fallback_id, str) and fallback_id.strip():
            return fallback_id.strip()

        return None

    @staticmethod
    def _coerce_legacy_toggle(value: Any) -> bool:
        """Best-effort coercion for legacy module toggle payloads."""

        if value is None:
            return True
        if isinstance(value, bool):
            return value
        if isinstance(value, (int | float)):
            return value != 0
        if isinstance(value, str):
            text = value.strip().lower()
            if not text:
                return True
            if text in {"0", "false", "no", "n", "off", "disabled"}:
                return False
            return text in {"1", "true", "yes", "y", "on", "enabled"}
        return bool(value)

    def _normalise_dog_modules(self, dog: DogConfigData) -> dict[str, bool]:
        """Return a normalised modules mapping for a dog configuration."""

        modules_raw = dog.get(CONF_MODULES)
        if isinstance(modules_raw, Mapping):
            return {
                module: enabled
                for module, enabled in modules_raw.items()
                if isinstance(module, str) and isinstance(enabled, bool)
            }
        return {}

    async def _estimate_entities_for_reconfigure(
        self, dogs: list[DogConfigData], profile: str
    ) -> int:
        """Estimate entities for reconfiguration display."""

        try:
            return sum(
                self._entity_factory.estimate_entity_count(
                    profile, self._normalise_dog_modules(dog)
                )
                for dog in dogs
                if is_dog_config_valid(dog)
            )
        except Exception as err:  # pragma: no cover - defensive guard
            _LOGGER.debug("Entity estimation failed: %s", err)
            return 0

    def _check_profile_compatibility(
        self, profile: str, dogs: list[DogConfigData]
    ) -> ReconfigureCompatibilityResult:
        """Check profile compatibility with existing dogs."""

        warnings: list[str] = []

        try:
            for dog in dogs:
                modules = self._normalise_dog_modules(dog)
                if modules and not self._entity_factory.validate_profile_for_modules(
                    profile, modules
                ):
                    dog_name = dog.get(DOG_NAME_FIELD) or dog.get(
                        DOG_ID_FIELD, "unknown"
                    )
                    warnings.append(
                        f"Profile '{profile}' may not be optimal for {dog_name}"
                    )
        except Exception as err:  # pragma: no cover - defensive guard
            warnings.append(f"Profile validation error: {err}")

        return {
            "compatible": not warnings,
            "warnings": self._normalise_string_list(warnings),
        }

    def _get_compatibility_info(
        self, current_profile: str, dogs: list[DogConfigData]
    ) -> str:
        """Get compatibility information for profile change."""

        dog_count = len(dogs)
        total_modules = sum(
            sum(1 for enabled in modules.values() if enabled)
            for modules in (self._normalise_dog_modules(dog) for dog in dogs)
        )

        if dog_count >= 5:
            return "High dog count - 'basic' profile recommended for performance"
        if total_modules >= 20:
            return "Many modules enabled - consider 'standard' or 'basic' profile"
        return "Current configuration supports all profiles"

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> PawControlOptionsFlow:
        """Create options flow.

        Args:
            config_entry: Configuration entry

        Returns:
            Options flow instance
        """
        flow = PawControlOptionsFlow()
        flow.initialize_from_config_entry(config_entry)
        return flow


ConfigFlow = PawControlConfigFlow
ConfigFlow.__doc__ = "Compatibility alias for Home Assistant's config flow loader."
