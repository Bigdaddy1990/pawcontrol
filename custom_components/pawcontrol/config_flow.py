"""Config flow for PawControl integration.

Enhanced configuration flow with discovery support, optimized validation,
and comprehensive error handling for Platinum quality compliance.
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
)
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv
from homeassistant.util import dt as dt_util

from .config_flow_profile import (
    PROFILE_SCHEMA,
    build_profile_summary_text,
    validate_profile_selection,
)
from .const import (
    CONF_DOG_AGE,
    CONF_DOG_BREED,
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOG_SIZE,
    CONF_DOG_WEIGHT,
    CONF_DOGS,
    CONF_MODULES,
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
from .entity_factory import ENTITY_PROFILES, EntityFactory
from .options_flow import PawControlOptionsFlow
from .types import DogConfigData, is_dog_config_valid

_LOGGER = logging.getLogger(__name__)

# Validation constants with performance optimization
DOG_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
MAX_DOGS_PER_INTEGRATION = 10

# Pre-compiled validation sets for O(1) lookups
VALID_DOG_SIZES: frozenset[str] = frozenset(DOG_SIZES)
VALID_PROFILES: frozenset[str] = frozenset(ENTITY_PROFILES.keys())

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
    }
)


class ConfigFlowPerformanceMonitor:
    """Monitor performance of config flow operations."""

    def __init__(self) -> None:
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

    def get_stats(self) -> dict[str, Any]:
        """Return aggregated statistics for diagnostics."""

        stats: dict[str, Any] = {}
        for operation, times in self.operation_times.items():
            if not times:
                continue
            stats[operation] = {
                "avg_time": sum(times) / len(times),
                "max_time": max(times),
                "count": len(times),
            }

        stats["validations"] = self.validation_counts.copy()
        return stats


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


class PawControlConfigFlow(ConfigFlow, domain=DOMAIN):
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
        self._dogs: list[DogConfigData] = []
        self._integration_name = "Paw Control"
        self._entity_profile = "standard"
        self.reauth_entry: ConfigEntry | None = None
        self._discovery_info: dict[str, Any] = {}
        self._existing_dog_ids: set[str] = set()  # Performance: O(1) lookups
        self._entity_factory = EntityFactory(None)

        # Validation and estimation caches for improved responsiveness
        self._validation_cache: dict[str, tuple[dict[str, Any], Any, str]] = {}
        self._profile_estimates_cache: dict[str, int] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
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
        self, discovery_info: dict[str, Any]
    ) -> ConfigFlowResult:
        """Handle Zeroconf discovery.

        Args:
            discovery_info: Zeroconf discovery information

        Returns:
            Config flow result
        """
        _LOGGER.debug("Zeroconf discovery: %s", discovery_info)

        # Extract device information from Zeroconf
        hostname = discovery_info.get("hostname", "")
        properties = discovery_info.get("properties", {})

        # Check if this is a supported device
        if not self._is_supported_device(hostname, properties):
            return self.async_abort(reason="not_supported")

        # Store discovery info for later use
        self._discovery_info = {
            "source": "zeroconf",
            "hostname": hostname,
            "host": discovery_info.get("host"),
            "port": discovery_info.get("port"),
            "properties": properties,
        }

        # Set unique ID based on discovered device
        device_id = self._extract_device_id(properties)
        if device_id:
            await self.async_set_unique_id(device_id)
            self._abort_if_unique_id_configured(
                updates={"host": discovery_info.get("host")},
                reload_on_update=True,
            )

        return await self.async_step_discovery_confirm()

    async def async_step_dhcp(self, discovery_info: dict[str, Any]) -> ConfigFlowResult:
        """Handle DHCP discovery.

        Args:
            discovery_info: DHCP discovery information

        Returns:
            Config flow result
        """
        _LOGGER.debug("DHCP discovery: %s", discovery_info)

        hostname = discovery_info.get("hostname", "")
        macaddress = discovery_info.get("macaddress", "")

        # Check if this is a supported device
        if not self._is_supported_device(hostname, {"mac": macaddress}):
            return self.async_abort(reason="not_supported")

        self._discovery_info = {
            "source": "dhcp",
            "hostname": hostname,
            "ip": discovery_info.get("ip"),
            "macaddress": macaddress,
        }

        # Use MAC address as unique ID
        await self.async_set_unique_id(macaddress)
        self._abort_if_unique_id_configured(
            updates={"host": discovery_info.get("ip")},
            reload_on_update=True,
        )

        return await self.async_step_discovery_confirm()

    async def async_step_discovery_confirm(
        self, user_input: dict[str, Any] | None = None
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
            else:
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
        self, import_config: dict[str, Any]
    ) -> ConfigFlowResult:
        """Handle import from configuration.yaml.

        Args:
            import_config: Configuration from YAML

        Returns:
            Config flow result
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
                return self.async_abort(reason="invalid_import_config")

    async def _validate_import_config(
        self, import_config: dict[str, Any]
    ) -> dict[str, Any]:
        """Backward-compatible wrapper for enhanced import validation."""

        return await self._validate_import_config_enhanced(import_config)

    async def _validate_import_config_enhanced(
        self, import_config: dict[str, Any]
    ) -> dict[str, Any]:
        """Enhanced validation for imported configuration with better error reporting."""

        config_flow_monitor.record_validation("import_attempt")

        async with timed_operation("import_validation"):
            validation_errors: list[str] = []

            try:
                dogs_config = import_config.get(CONF_DOGS, [])
                if not isinstance(dogs_config, list):
                    raise vol.Invalid("Dogs configuration must be a list")

                validated_dogs = []
                seen_ids: set[str] = set()
                seen_names: set[str] = set()

                for index, dog_config in enumerate(dogs_config):
                    try:
                        validated_dog = DOG_SCHEMA(dog_config)

                        dog_id = validated_dog.get(CONF_DOG_ID)
                        dog_name = validated_dog.get(CONF_DOG_NAME)

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
                        raise vol.Invalid(
                            "No valid dogs found. Errors: "
                            + "; ".join(validation_errors)
                        )
                    raise vol.Invalid("No valid dogs found in import configuration")

                profile = import_config.get("entity_profile", "standard")
                if profile not in VALID_PROFILES:
                    validation_errors.append(
                        f"Invalid profile '{profile}', using 'standard'"
                    )
                    profile = "standard"

                for dog in validated_dogs:
                    modules = dog.get("modules", {})
                    if not self._entity_factory.validate_profile_for_modules(
                        profile, modules
                    ):
                        validation_errors.append(
                            f"Profile '{profile}' may not be optimal for dog '{dog.get(CONF_DOG_NAME)}'"
                        )

                if validation_errors:
                    _LOGGER.warning(
                        "Import validation warnings: %s",
                        "; ".join(validation_errors),
                    )

                config_flow_monitor.record_validation("import_validated")

                return {
                    "data": {
                        "name": import_config.get("name", "PawControl (Imported)"),
                        CONF_DOGS: validated_dogs,
                        "entity_profile": profile,
                        "import_warnings": validation_errors,
                        "import_timestamp": dt_util.utcnow().isoformat(),
                    },
                    "options": {
                        "entity_profile": profile,
                        "dashboard_enabled": import_config.get(
                            "dashboard_enabled", True
                        ),
                        "dashboard_auto_create": import_config.get(
                            "dashboard_auto_create", True
                        ),
                        "import_source": "configuration_yaml",
                    },
                }

            except Exception as err:
                raise vol.Invalid(
                    f"Import configuration validation failed: {err}"
                ) from err

    def _is_supported_device(self, hostname: str, properties: dict[str, Any]) -> bool:
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

    def _extract_device_id(self, properties: dict[str, Any]) -> str | None:
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

    def _format_discovery_info(self) -> str:
        """Format discovery info for display.

        Returns:
            Formatted discovery information
        """
        info = self._discovery_info
        if info.get("source") == "zeroconf":
            return f"Device: {info.get('hostname', 'Unknown')}\nHost: {info.get('host', 'Unknown')}"
        elif info.get("source") == "dhcp":
            return f"Device: {info.get('hostname', 'Unknown')}\nIP: {info.get('ip', 'Unknown')}"
        return "Unknown device"

    async def async_step_add_dog(
        self, user_input: dict[str, Any] | None = None
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
                try:
                    validated_input = await self._validate_dog_input_cached(user_input)
                    if validated_input:
                        dog_config = self._create_dog_config(validated_input)
                        self._dogs.append(dog_config)
                        self._existing_dog_ids.add(dog_config[CONF_DOG_ID])
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
                description_placeholders={
                    "dogs_configured": str(len(self._dogs)),
                    "max_dogs": str(MAX_DOGS_PER_INTEGRATION),
                    "discovery_hint": self._get_discovery_hint(),
                },
            )

    def _get_validation_state_signature(self) -> str:
        """Get a signature representing current validation state."""

        existing_ids = "|".join(sorted(self._existing_dog_ids))
        return f"{len(self._dogs)}::{existing_ids}"

    async def _validate_dog_input_cached(
        self, user_input: dict[str, Any]
    ) -> dict[str, Any] | None:
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
        now = dt_util.utcnow()

        if cached_entry:
            cached_result, cache_time, cached_state = cached_entry
            if (
                cached_state == state_signature
                and (now - cache_time).total_seconds() < 60
            ):
                config_flow_monitor.record_validation("dog_input_cache_hit")
                return dict(cached_result)

        try:
            result = await self._validate_dog_input_optimized(user_input)
        except DogValidationError:
            config_flow_monitor.record_validation("dog_input_error")
            raise

        cache_payload = (dict(result), now, state_signature)
        self._validation_cache[cache_key] = cache_payload
        config_flow_monitor.record_validation("dog_input_validated")
        return result

    def _invalidate_profile_caches(self) -> None:
        """Invalidate cached profile estimates when configuration changes."""

        self._profile_estimates_cache.clear()

    def _estimate_total_entities_cached(self) -> int:
        """Estimate total entities with improved caching."""

        dogs_signature = hash(
            str(
                [
                    (
                        dog.get("dog_id"),
                        tuple(sorted(dog.get("modules", {}).items())),
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
            modules = dog.get("modules", {})
            total += self._entity_factory.estimate_entity_count(
                self._entity_profile, modules
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
        self, user_input: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Validate dog input data with optimized performance.

        Uses set operations and pre-compiled regex for better performance.

        Args:
            user_input: Raw user input

        Returns:
            Validated input or None if validation fails

        Raises:
            ValueError: If validation fails
        """
        # Sanitize inputs with optimized string operations
        dog_id = user_input[CONF_DOG_ID].lower().strip()
        dog_name = user_input[CONF_DOG_NAME].strip()

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
        dog_size = user_input.get(CONF_DOG_SIZE, "medium")
        if dog_size not in VALID_DOG_SIZES:
            field_errors[CONF_DOG_SIZE] = f"Invalid dog size: {dog_size}"

        # Raise single error with all issues
        if field_errors or base_errors:
            raise DogValidationError(
                field_errors=field_errors,
                base_errors=base_errors,
            )

        # Return validated data
        return {
            CONF_DOG_ID: dog_id,
            CONF_DOG_NAME: dog_name,
            CONF_DOG_BREED: user_input.get(CONF_DOG_BREED, "").strip(),
            CONF_DOG_AGE: user_input.get(CONF_DOG_AGE, 3),
            CONF_DOG_WEIGHT: user_input.get(CONF_DOG_WEIGHT, 20.0),
            CONF_DOG_SIZE: dog_size,
        }

    def _create_dog_config(self, validated_input: dict[str, Any]) -> DogConfigData:
        """Create dog configuration from validated input.

        Args:
            validated_input: Validated user input

        Returns:
            Dog configuration data
        """
        config: DogConfigData = {
            "dog_id": validated_input[CONF_DOG_ID],
            "dog_name": validated_input[CONF_DOG_NAME],
            "dog_breed": validated_input[CONF_DOG_BREED] or None,
            "dog_age": validated_input[CONF_DOG_AGE],
            "dog_weight": validated_input[CONF_DOG_WEIGHT],
            "dog_size": validated_input[CONF_DOG_SIZE],
            "modules": {},  # Will be set in next step
        }

        # Add discovery info if available
        if self._discovery_info:
            config["discovery_info"] = self._discovery_info.copy()

        return config

    async def async_step_dog_modules(
        self, user_input: dict[str, Any] | None = None
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
            try:
                # Validate modules configuration
                modules = MODULES_SCHEMA(user_input or {})
                current_dog[CONF_MODULES] = modules
                self._invalidate_profile_caches()
                return await self.async_step_add_another()

            except vol.Invalid as err:
                _LOGGER.warning("Module validation failed: %s", err)
                return self.async_show_form(
                    step_id="dog_modules",
                    data_schema=MODULES_SCHEMA,
                    errors={"base": "invalid_modules"},
                    description_placeholders={
                        "dog_name": current_dog[CONF_DOG_NAME],
                        "dogs_configured": str(len(self._dogs)),
                        "smart_defaults": self._get_smart_module_defaults(current_dog),
                    },
                )

        # Enhanced schema with smart defaults based on discovery
        enhanced_schema = self._get_enhanced_modules_schema(current_dog)

        return self.async_show_form(
            step_id="dog_modules",
            data_schema=enhanced_schema,
            description_placeholders={
                "dog_name": current_dog[CONF_DOG_NAME],
                "dogs_configured": str(len(self._dogs)),
                "smart_defaults": self._get_smart_module_defaults(current_dog),
            },
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
        self, user_input: dict[str, Any] | None = None
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
            else:
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
            description_placeholders={
                "dogs_configured": str(len(self._dogs)),
                "dogs_list": self._format_dogs_list_enhanced(),
                "can_add_more": "yes" if can_add_more else "no",
                "max_dogs": str(MAX_DOGS_PER_INTEGRATION),
                "performance_note": self._get_performance_note(),
            },
        )

    def _get_performance_note(self) -> str:
        """Get performance note based on current configuration.

        Returns:
            Performance guidance text
        """
        dog_count = len(self._dogs)
        if dog_count >= 5:
            return "Consider 'basic' profile for better performance with many dogs"
        elif dog_count >= 3:
            return "Multiple dogs configured - 'standard' profile recommended"
        return "Single/few dogs - 'advanced' profile available for full features"

    async def async_step_entity_profile(
        self, user_input: dict[str, Any] | None = None
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
            len([m for m, e in dog.get("modules", {}).items() if e])
            for dog in self._dogs
        )

        if dog_count >= 5 or total_modules >= 20:
            return "Recommended: 'basic' profile for optimal performance"
        elif dog_count >= 3 or total_modules >= 12:
            return "Recommended: 'standard' profile for balanced functionality"
        else:
            return "Recommended: 'standard' or 'advanced' profile for full features"

    async def async_step_final_setup(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Complete setup and create config entry with enhanced validation.

        Args:
            user_input: User provided data

        Returns:
            Config flow result
        """
        async with timed_operation("final_setup"):
            if not self._dogs:
                return self.async_abort(reason="no_dogs_configured")

            validation_results = await self._perform_comprehensive_validation()
            if not validation_results["valid"]:
                _LOGGER.error(
                    "Final validation failed: %s", validation_results["errors"]
                )
                return self.async_abort(reason="setup_validation_failed")

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
                return self.async_abort(reason="setup_failed")

    async def _perform_comprehensive_validation(self) -> dict[str, Any]:
        """Perform comprehensive final validation."""

        async with timed_operation("final_validation"):
            errors: list[str] = [
                f"Invalid dog configuration: {dog.get(CONF_DOG_ID, 'unknown')}"
                for dog in self._dogs
                if not is_dog_config_valid(dog)
            ]

            estimated_entities = self._estimate_total_entities_cached()
            if estimated_entities > 200:
                errors.append(f"Too many estimated entities: {estimated_entities}")

            if self._entity_profile not in VALID_PROFILES:
                errors.append(f"Invalid profile: {self._entity_profile}")

            result = {
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
            modules = dog.get("modules", {})
            if not self._entity_factory.validate_profile_for_modules(
                self._entity_profile, modules
            ):
                return False

        return True

    def _build_config_entry_data(self) -> tuple[dict[str, Any], dict[str, Any]]:
        """Build optimized config entry data.

        Returns:
            Tuple of (config_data, options_data)
        """
        config_data = {
            "name": self._integration_name,
            CONF_DOGS: self._dogs,
            "entity_profile": self._entity_profile,
            "setup_timestamp": dt_util.utcnow().isoformat(),
        }

        # Add discovery info if available
        if self._discovery_info:
            config_data["discovery_info"] = self._discovery_info

        options_data = {
            "entity_profile": self._entity_profile,
            "dashboard_enabled": True,
            "dashboard_auto_create": True,
            "performance_monitoring": True,
        }

        return config_data, options_data

    def _generate_entry_title(self, profile_info: dict[str, Any]) -> str:
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
            modules = dog.get("modules", {})
            enabled_modules = [name for name, enabled in modules.items() if enabled]
            module_summary = ", ".join(enabled_modules) if enabled_modules else "none"

            dogs_list.append(
                f"{i}. {dog[CONF_DOG_NAME]} ({dog[CONF_DOG_ID]})\n"
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
                modules = dog.get("modules", {})
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

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        """Handle reauthentication flow for Platinum compliance.

        Args:
            entry_data: Existing config entry data

        Returns:
            Config flow result
        """
        self.reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        if not self.reauth_entry:
            return self.async_abort(reason="reauth_failed")

        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm reauthentication with enhanced validation.

        Args:
            user_input: User provided data

        Returns:
            Config flow result
        """
        if not self.reauth_entry:
            return self.async_abort(reason="reauth_failed")

        errors: dict[str, str] = {}

        if user_input is not None:
            if user_input.get("confirm", False):
                try:
                    # Enhanced validation for reauthentication
                    await self.async_set_unique_id(self.reauth_entry.unique_id)
                    self._abort_if_unique_id_mismatch(reason="wrong_account")

                    # Perform configuration health check
                    config_health = await self._check_config_health(self.reauth_entry)
                    if not config_health["healthy"]:
                        _LOGGER.warning(
                            "Configuration health issues: %s", config_health["issues"]
                        )

                    return self.async_update_reload_and_abort(
                        self.reauth_entry,
                        data_updates={
                            "reauth_timestamp": dt_util.utcnow().isoformat(),
                        },
                    )
                except Exception as err:
                    _LOGGER.error("Reauthentication failed: %s", err)
                    errors["base"] = "reauth_failed"
            else:
                errors["base"] = "reauth_unsuccessful"

        # Show enhanced confirmation form
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required("confirm", default=True): cv.boolean,
                }
            ),
            errors=errors,
            description_placeholders={
                "integration_name": self.reauth_entry.title,
                "dogs_count": str(len(self.reauth_entry.data.get(CONF_DOGS, []))),
                "current_profile": self.reauth_entry.options.get(
                    "entity_profile", "unknown"
                ),
            },
        )

    async def _check_config_health(self, entry: ConfigEntry) -> dict[str, Any]:
        """Check configuration health.

        Args:
            entry: Config entry to check

        Returns:
            Health check results
        """
        dogs = entry.data.get(CONF_DOGS, [])
        issues = [
            f"Invalid dog config: {dog.get(CONF_DOG_ID, 'unknown')}"
            for dog in dogs
            if not is_dog_config_valid(dog)
        ]

        # Check profile validity
        profile = entry.options.get("entity_profile", "standard")
        if profile not in VALID_PROFILES:
            issues.append(f"Invalid profile: {profile}")

        return {
            "healthy": len(issues) == 0,
            "issues": issues,
            "dogs_count": len(dogs),
            "profile": profile,
        }

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reconfiguration flow with enhanced options.

        Args:
            user_input: User provided data

        Returns:
            Config flow result
        """
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        if not entry:
            return self.async_abort(reason="reconfigure_failed")

        if user_input is not None:
            try:
                # Enhanced reconfiguration validation
                profile_data = PROFILE_SCHEMA(user_input)
                new_profile = profile_data["entity_profile"]

                # Prevent changing underlying account
                await self.async_set_unique_id(entry.unique_id)
                self._abort_if_unique_id_mismatch(reason="wrong_account")

                # Validate profile compatibility with existing dogs
                dogs = entry.data.get(CONF_DOGS, [])
                compatibility_check = self._check_profile_compatibility(
                    new_profile, dogs
                )

                if not compatibility_check["compatible"]:
                    _LOGGER.warning(
                        "Profile compatibility warning: %s",
                        compatibility_check["warning"],
                    )

                # Update the config entry with enhanced data
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={
                        "entity_profile": new_profile,
                        "reconfigure_timestamp": dt_util.utcnow().isoformat(),
                    },
                    options_updates={
                        "entity_profile": new_profile,
                        "last_reconfigure": dt_util.utcnow().isoformat(),
                    },
                )

            except vol.Invalid as err:
                _LOGGER.warning("Reconfigure validation failed: %s", err)
                return self.async_show_form(
                    step_id="reconfigure",
                    data_schema=PROFILE_SCHEMA,
                    errors={"base": "invalid_profile"},
                )

        # Show enhanced reconfigure form
        current_profile = entry.options.get("entity_profile", "standard")
        dogs = entry.data.get(CONF_DOGS, [])

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required("entity_profile", default=current_profile): vol.In(
                        VALID_PROFILES
                    ),
                }
            ),
            description_placeholders={
                "current_profile": current_profile,
                "profiles_info": self._get_profiles_info_enhanced(),
                "dogs_count": str(len(dogs)),
                "compatibility_info": self._get_compatibility_info(
                    current_profile, dogs
                ),
            },
        )

    def _check_profile_compatibility(
        self, profile: str, dogs: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Check profile compatibility with existing dogs.

        Args:
            profile: Profile to check
            dogs: Existing dogs configuration

        Returns:
            Compatibility check results
        """
        warnings = []

        for dog in dogs:
            modules = dog.get("modules", {})
            if not self._entity_factory.validate_profile_for_modules(profile, modules):
                warnings.append(
                    f"Profile '{profile}' may not be optimal for {dog.get('dog_name', 'unknown')}"
                )

        return {
            "compatible": len(warnings) == 0,
            "warning": "; ".join(warnings) if warnings else None,
        }

    def _get_compatibility_info(
        self, current_profile: str, dogs: list[dict[str, Any]]
    ) -> str:
        """Get compatibility information for profile change.

        Args:
            current_profile: Current profile
            dogs: Dogs configuration

        Returns:
            Compatibility information text
        """
        dog_count = len(dogs)
        total_modules = sum(
            len([m for m, e in dog.get("modules", {}).items() if e]) for dog in dogs
        )

        if dog_count >= 5:
            return "High dog count - 'basic' profile recommended for performance"
        elif total_modules >= 20:
            return "Many modules enabled - consider 'standard' or 'basic' profile"
        else:
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
        return PawControlOptionsFlow(config_entry)
