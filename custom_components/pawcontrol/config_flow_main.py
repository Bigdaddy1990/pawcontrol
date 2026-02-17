"""Config flow for the PawControl integration."""

__all__ = ["ConfigFlow", "PawControlConfigFlow"]

from collections.abc import Awaitable, Mapping, Sequence
import copy
from datetime import datetime
import logging
import re
from typing import Any, cast

from homeassistant.config_entries import ConfigEntry, ConfigFlowResult
from homeassistant.core import callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.util import dt as dt_util
import voluptuous as vol

from .config_flow_base import INTEGRATION_SCHEMA, PawControlBaseConfigFlow
from .config_flow_dashboard_extension import DashboardFlowMixin
from .config_flow_discovery import DiscoveryFlowMixin
from .config_flow_dogs import DogManagementMixin
from .config_flow_external import ExternalEntityConfigurationMixin
from .config_flow_modules import ModuleConfigurationMixin
from .config_flow_monitor import config_flow_monitor, timed_operation
from .config_flow_placeholders import (
    _build_add_another_placeholders,
    _build_add_dog_summary_placeholders,
    _build_dog_modules_form_placeholders,
)
from .config_flow_profile import (
    DEFAULT_PROFILE,
    PROFILE_SCHEMA,
    build_profile_summary_text,
    validate_profile_selection,
)
from .config_flow_reauth import ReauthFlowMixin
from .config_flow_schemas import DOG_SCHEMA, MODULE_SELECTION_KEYS, MODULES_SCHEMA
from .const import (
    CONF_DOG_OPTIONS,
    CONF_DOG_SIZE,
    CONF_DOG_WEIGHT,
    CONF_DOGS,
    CONF_MODULES,
    CONF_NAME,
    CONFIG_ENTRY_VERSION,
    DEFAULT_DATA_RETENTION_DAYS,
    DEFAULT_PERFORMANCE_MODE,
    DOMAIN,
    MODULE_GPS,
)
from .entity_factory import ENTITY_PROFILES, EntityFactory, EntityProfileDefinition
from .exceptions import (
    ConfigurationError,
    FlowValidationError,
    PawControlSetupError,
    ReconfigureRequiredError,
    ValidationError,
)
from .flow_steps.gps import DogGPSFlowMixin, GPSModuleDefaultsMixin
from .flow_steps.health import DogHealthFlowMixin, HealthSummaryMixin
from .flow_validation import (
    is_dog_config_payload_valid,
    validate_dog_import_input,
    validate_dog_setup_input,
)
from .flow_validators import validate_flow_dog_name
from .options_flow import PawControlOptionsFlow
from .selector_shim import selector
from .types import (
    DOG_ID_FIELD,
    DOG_MODULES_FIELD,
    DOG_NAME_FIELD,
    MODULE_TOGGLE_FLAG_BY_KEY,
    MODULE_TOGGLE_KEYS,
    RECONFIGURE_FORM_PLACEHOLDERS_TEMPLATE,
    AddAnotherDogInput,
    ConfigEntryDataPayload,
    ConfigEntryOptionsPayload,
    ConfigFlowDiscoveryData,
    ConfigFlowDiscoveryProperties,
    ConfigFlowDiscoverySource,
    ConfigFlowImportData,
    ConfigFlowImportOptions,
    ConfigFlowImportResult,
    ConfigFlowInputMapping,
    ConfigFlowPlaceholders,
    ConfigFlowUserInput,
    DashboardConfigurationStepInput,
    DiscoveryUpdatePayload,
    DogConfigData,
    DogModulesConfig,
    DogModuleSelectionInput,
    DogSetupStepInput,
    DogValidationCacheEntry,
    ExternalEntityConfig,
    FinalSetupValidationResult,
    JSONMutableMapping,
    JSONValue,
    ModuleConfigurationStepInput,
    ModuleToggleKey,
    PerformanceMode,
    ProfileSelectionInput,
    ReconfigureCompatibilityResult,
    ReconfigureDataUpdates,
    ReconfigureFormPlaceholders,
    ReconfigureOptionsUpdates,
    ReconfigureProfileInput,
    ReconfigureTelemetry,
    clone_placeholders,
    coerce_dog_modules_config,
    dog_modules_from_flow_input,
    ensure_dog_modules_config,
    ensure_dog_modules_mapping,
    freeze_placeholders,
    normalize_performance_mode,
)
from .validation import InputCoercionError, normalize_dog_id

_LOGGER = logging.getLogger(__name__)

# Validation constants with performance optimization
MAX_DOGS_PER_INTEGRATION = 10

# Pre-compiled validation sets for O(1) lookups
VALID_PROFILES: frozenset[str] = frozenset(ENTITY_PROFILES.keys())

USER_SCHEMA = INTEGRATION_SCHEMA

DISCOVERY_SOURCE_SET: frozenset[str] = frozenset(
    {"zeroconf", "dhcp", "usb", "bluetooth", "import", "reauth"},
)
UNKNOWN_DISCOVERY_SOURCE: ConfigFlowDiscoverySource = "unknown"

_LIST_REMOVE_DIRECTIVE = "__pc_merge_remove__"

# PLATINUM: Enhanced timeouts for robust operations
NETWORK_OPERATION_TIMEOUT = 10.0


class PawControlConfigFlow(
    DiscoveryFlowMixin,
    ModuleConfigurationMixin,
    DashboardFlowMixin,
    ExternalEntityConfigurationMixin,
    GPSModuleDefaultsMixin,
    DogGPSFlowMixin,
    DogHealthFlowMixin,
    DogManagementMixin,
    HealthSummaryMixin,
    ReauthFlowMixin,
    PawControlBaseConfigFlow,
):
    """Enhanced configuration flow for Paw Control integration.

    Features:
    - Device discovery support (Zeroconf, DHCP)
    - Import from configuration.yaml
    - Optimized validation with set operations
    - Comprehensive error handling
    - Performance monitoring
    """  # noqa: E111

    VERSION = CONFIG_ENTRY_VERSION  # noqa: E111
    MINOR_VERSION = 3  # noqa: E111

    def __init__(self) -> None:  # noqa: E111
        """Initialize configuration flow with enhanced state management."""
        # Some protocol-backed runtime shim bases in the mixin graph resolve to
        # ``object`` and can short-circuit cooperative init before the base flow
        # state is established. Initialize the config-flow base explicitly so
        # required attributes (for example ``_dogs``) always exist.
        PawControlBaseConfigFlow.__init__(self)
        super().__init__()
        self._integration_name = "Paw Control"
        self._entity_profile = "standard"
        self.reauth_entry: ConfigEntry | None = None
        self._existing_dog_ids: set[str] = set()  # Performance: O(1) lookups
        self._entity_factory = EntityFactory(None)

        # Validation and estimation caches for improved responsiveness
        self._profile_estimates_cache: dict[str, int] = {}
        self._enabled_modules: DogModulesConfig = {}
        self._external_entities: ExternalEntityConfig = {}
        self._discovery_info: ConfigFlowDiscoveryData = {}

    async def async_step_user(  # noqa: E111
        self,
        user_input: ConfigFlowUserInput | None = None,
    ) -> ConfigFlowResult:
        """Handle initial step with enhanced uniqueness validation.

        Args:
            user_input: User provided data

        Returns:
            Config flow result
        """
        async with timed_operation("user_step"):
            # Ensure single instance before showing any user-step UI.  # noqa: E114
            await self.async_set_unique_id(DOMAIN)  # noqa: E111
            self._abort_if_unique_id_configured(  # noqa: E111
                updates={},
                reload_on_update=False,
            )

            if user_input is None:  # noqa: E111
                return self.async_show_form(
                    step_id="user",
                    data_schema=USER_SCHEMA,
                )

            integration_name_raw = user_input.get(CONF_NAME, self._integration_name)  # noqa: E111
            integration_name = (  # noqa: E111
                str(integration_name_raw).strip()
                if integration_name_raw is not None
                else self._integration_name
            )
            name_validation = await self._async_validate_integration_name(
                integration_name
            )  # noqa: E111
            if not name_validation["valid"]:  # noqa: E111
                return self.async_show_form(
                    step_id="user",
                    data_schema=USER_SCHEMA,
                    errors=name_validation["errors"],
                )

            self._integration_name = integration_name  # noqa: E111
            # NOTE: this value is stored as metadata in config entry data only.  # noqa: E114
            # The config entry title remains generated by profile helpers in  # noqa: E114
            # ``_generate_entry_title`` during final setup.  # noqa: E114
            # Start the dog setup form with a clean payload after the integration  # noqa: E114, E501
            # name is validated. ``async_step_add_dog`` handles ``None`` by showing  # noqa: E114, E501
            # the first dog form.  # noqa: E114
            return await self.async_step_add_dog(  # noqa: E111
                cast(DogSetupStepInput | None, None),
            )

    async def async_step_import(  # noqa: E111
        self,
        import_config: ConfigFlowInputMapping,
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
            # Ensure single instance  # noqa: E114
            await self.async_set_unique_id(DOMAIN)  # noqa: E111
            self._abort_if_unique_id_configured()  # noqa: E111

            try:  # noqa: E111
                validated_config = await self._validate_import_config_enhanced(
                    import_config,
                )

                return self.async_create_entry(
                    title="PawControl (Imported)",
                    data=validated_config["data"],
                    options=validated_config["options"],
                )

            except vol.Invalid as err:  # noqa: E111
                _LOGGER.error("Invalid import configuration: %s", err)
                raise ConfigEntryNotReady(
                    "Invalid import configuration format",
                ) from err
            except ValidationError as err:  # noqa: E111
                _LOGGER.error("Import validation failed: %s", err)
                raise ConfigEntryNotReady(
                    f"Import validation failed: {err}",
                ) from err

    async def _validate_import_config(  # noqa: E111
        self,
        import_config: ConfigFlowUserInput,
    ) -> ConfigFlowImportResult:
        """Backward-compatible wrapper for enhanced import validation.

        Args:
            import_config: Configuration to validate

        Returns:
            Validated configuration result
        """
        return await self._validate_import_config_enhanced(import_config)

    async def _validate_import_config_enhanced(  # noqa: E111
        self,
        import_config: ConfigFlowUserInput,
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
            validation_errors: list[str] = []  # noqa: E111

            try:  # noqa: E111
                dogs_config = import_config.get(CONF_DOGS, [])
                if not isinstance(dogs_config, list):
                    raise ConfigurationError(  # noqa: E111
                        "dogs",
                        dogs_config,
                        "Dogs configuration must be a list",
                    )

                validated_dogs: list[DogConfigData] = []
                seen_ids: set[str] = set()
                seen_names: set[str] = set()

                for index, dog_config in enumerate(dogs_config):
                    if not isinstance(dog_config, Mapping):  # noqa: E111
                        validation_errors.append(
                            f"Dog entry at position {index + 1} must be a mapping",
                        )
                        config_flow_monitor.record_validation(
                            "import_dog_invalid",
                        )
                        continue

                    try:  # noqa: E111
                        validated_dog = validate_dog_import_input(
                            cast(ConfigFlowInputMapping, dog_config),
                            existing_ids=seen_ids,
                            existing_names=seen_names,
                            current_dog_count=len(validated_dogs),
                            max_dogs=MAX_DOGS_PER_INTEGRATION,
                        )
                    except (FlowValidationError, ValidationError) as err:  # noqa: E111
                        validation_errors.append(
                            f"Dog validation failed at position {index + 1}: {err}",
                        )
                        config_flow_monitor.record_validation(
                            "import_dog_invalid",
                        )
                        continue

                    dog_id_raw = validated_dog.get(DOG_ID_FIELD)  # noqa: E111
                    dog_name_raw = validated_dog.get(DOG_NAME_FIELD)  # noqa: E111
                    # MYPY FIX: Type guard before adding to set  # noqa: E114
                    if isinstance(dog_id_raw, str):  # noqa: E111
                        seen_ids.add(dog_id_raw)
                    if isinstance(dog_name_raw, str):  # noqa: E111
                        seen_names.add(dog_name_raw)
                    validated_dogs.append(validated_dog)  # noqa: E111
                    config_flow_monitor.record_validation(  # noqa: E111
                        "import_dog_valid",
                    )

                if not validated_dogs:
                    if validation_errors:  # noqa: E111
                        raise ValidationError(
                            "import_dogs",
                            constraint="No valid dogs found. Errors: "
                            + "; ".join(validation_errors),
                        )
                    raise ValidationError(  # noqa: E111
                        "import_dogs",
                        constraint="No valid dogs found in import configuration",
                    )

                profile_raw = import_config.get("entity_profile", "standard")
                profile = (
                    profile_raw if isinstance(profile_raw, str) else str(profile_raw)
                )
                if profile not in VALID_PROFILES:
                    validation_errors.append(  # noqa: E111
                        f"Invalid profile '{profile}', using 'standard'",
                    )
                    profile = "standard"  # noqa: E111

                for dog in validated_dogs:
                    modules = ensure_dog_modules_mapping(dog)  # noqa: E111
                    if not self._entity_factory.validate_profile_for_modules(  # noqa: E111
                        profile,
                        modules,
                    ):
                        dog_name = dog.get(DOG_NAME_FIELD)
                        dog_name_str = (
                            str(dog_name) if dog_name is not None else "unknown"
                        )
                        validation_errors.append(
                            f"Profile '{profile}' may not be optimal for dog '{dog_name_str}'",
                        )

                if validation_errors:
                    _LOGGER.warning(  # noqa: E111
                        "Import validation warnings: %s",
                        "; ".join(validation_errors),
                    )

                config_flow_monitor.record_validation("import_validated")

                name_raw = import_config.get("name", "PawControl (Imported)")
                name_str = (
                    str(name_raw) if name_raw is not None else "PawControl (Imported)"
                )

                data_payload: ConfigFlowImportData = {
                    "name": name_str,
                    "dogs": validated_dogs,
                    "entity_profile": profile,
                    "import_warnings": validation_errors,
                    "import_timestamp": dt_util.utcnow().isoformat(),
                }
                options_payload: ConfigFlowImportOptions = {
                    "entity_profile": profile,
                    "dashboard_enabled": bool(
                        import_config.get("dashboard_enabled", True),
                    ),
                    "dashboard_auto_create": bool(
                        import_config.get("dashboard_auto_create", True),
                    ),
                    "import_source": "configuration_yaml",
                }

                result: ConfigFlowImportResult = {
                    "data": data_payload,
                    "options": options_payload,
                }
                return result

            except Exception as err:  # noqa: E111
                raise ValidationError(
                    "import_configuration",
                    constraint=f"Import configuration validation failed: {err}",
                ) from err

    def _is_supported_device(  # noqa: E111
        self,
        hostname: str,
        properties: ConfigFlowDiscoveryProperties,
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

    def _extract_device_id(  # noqa: E111
        self,
        properties: ConfigFlowDiscoveryProperties,
    ) -> str | None:
        """Extract device ID from discovery properties.

        Args:
            properties: Device properties

        Returns:
            Device ID if found
        """
        # Look for common device ID fields
        for field in ["serial", "device_id", "mac", "uuid"]:
            if field in properties:  # noqa: E111
                value = properties[field]
                return str(value) if value is not None else None
        return None

    def _normalise_discovery_metadata(  # noqa: E111
        self,
        payload: Mapping[str, object] | None,
        *,
        source: ConfigFlowDiscoverySource | None = None,
        include_last_seen: bool = True,
    ) -> ConfigFlowDiscoveryData:
        """Return a normalised discovery metadata payload.

        Args:
            payload: Discovery data to normalize
            source: Discovery source type
            include_last_seen: Whether to add timestamp

        Returns:
            Normalized discovery data
        """
        data = payload if isinstance(payload, Mapping) else {}

        candidate_source = source or data.get("source") or UNKNOWN_DISCOVERY_SOURCE
        candidate_source_str = str(candidate_source).lower()
        resolved_source = (
            candidate_source_str
            if candidate_source_str in DISCOVERY_SOURCE_SET
            else UNKNOWN_DISCOVERY_SOURCE
        )

        normalised: JSONMutableMapping = {
            "source": cast(ConfigFlowDiscoverySource, resolved_source),
        }

        if include_last_seen:
            normalised["last_seen"] = dt_util.utcnow().isoformat()  # noqa: E111

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
            value = data.get(field)  # noqa: E111
            if isinstance(value, str):  # noqa: E111
                trimmed = value.strip()
                if trimmed:
                    normalised[field] = trimmed  # noqa: E111
            elif value not in (None, ""):  # noqa: E111
                normalised[field] = str(value)

        # MYPY FIX: Type guard for port value
        port_value = data.get("port")
        if isinstance(port_value, int):
            normalised["port"] = port_value  # noqa: E111
        elif isinstance(port_value, str):
            stripped = port_value.strip()  # noqa: E111
            if stripped.isdigit():  # noqa: E111
                normalised["port"] = int(stripped)

        properties_value = data.get("properties")
        if isinstance(properties_value, Mapping):
            properties: ConfigFlowDiscoveryProperties = {}  # noqa: E111
            for key, value in properties_value.items():  # noqa: E111
                key_str = str(key)
                if isinstance(value, str | int | float | bool):
                    properties[key_str] = value  # noqa: E111
                elif isinstance(value, bytes):
                    try:  # noqa: E111
                        properties[key_str] = value.decode()
                    except Exception:  # noqa: E111
                        properties[key_str] = value.decode(errors="ignore")
                elif value is None:
                    continue  # noqa: E111
                else:
                    properties[key_str] = str(value)  # noqa: E111
            if properties:  # noqa: E111
                normalised["properties"] = properties

        service_uuids_value = data.get("service_uuids")
        if isinstance(service_uuids_value, Sequence) and not isinstance(
            service_uuids_value,
            str | bytes,
        ):
            service_uuids: list[str] = []  # noqa: E111
            for item in service_uuids_value:  # noqa: E111
                if isinstance(item, str):
                    trimmed = item.strip()  # noqa: E111
                    if trimmed:  # noqa: E111
                        service_uuids.append(trimmed)
                elif isinstance(item, bytes):
                    try:  # noqa: E111
                        decoded = item.decode()
                    except Exception:  # noqa: E111
                        decoded = item.decode(errors="ignore")
                    if decoded:  # noqa: E111
                        service_uuids.append(decoded)
                elif item is not None:
                    service_uuids.append(str(item))  # noqa: E111
            if service_uuids:  # noqa: E111
                normalised["service_uuids"] = service_uuids

        return cast(ConfigFlowDiscoveryData, normalised)

    def _strip_dynamic_discovery_fields(  # noqa: E111
        self,
        info: Mapping[str, object],
    ) -> ConfigFlowDiscoveryData:
        """Remove dynamic fields (like timestamps) for comparison.

        Args:
            info: Discovery info to process

        Returns:
            Cleaned discovery data
        """
        cleaned = {key: value for key, value in info.items() if key != "last_seen"}
        return cast(ConfigFlowDiscoveryData, cleaned)

    async def _async_get_entry_for_unique_id(self) -> ConfigEntry | None:  # noqa: E111
        """Return the current entry matching the configured unique ID.

        Returns:
            Config entry if found
        """
        unique_id = getattr(self, "_unique_id", None)
        if not unique_id:
            return None  # noqa: E111

        entries = self._async_current_entries()
        if isinstance(entries, Awaitable):
            entries_list = await entries  # noqa: E111
        else:
            entries_list = entries  # noqa: E111

        for entry in entries_list:
            if entry.unique_id == unique_id:  # noqa: E111
                return entry

        if isinstance(unique_id, str):
            normalised_unique_id = unique_id.casefold()  # noqa: E111
            for entry in entries_list:  # noqa: E111
                entry_id = entry.unique_id
                if (
                    isinstance(entry_id, str)
                    and entry_id.casefold() == normalised_unique_id
                ):
                    return entry  # noqa: E111
        return None

    def _discovery_update_required(  # noqa: E111
        self,
        entry: ConfigEntry,
        *,
        updates: Mapping[str, object],
        comparison: Mapping[str, object],
    ) -> bool:
        """Return whether discovery updates require entry persistence.

        Args:
            entry: Config entry to check
            updates: Proposed updates
            comparison: Comparison baseline

        Returns:
            True if update is needed
        """
        existing_data = entry.data

        if "discovery_info" in updates:
            existing_info_raw = existing_data.get("discovery_info")  # noqa: E111
            if isinstance(existing_info_raw, Mapping):  # noqa: E111
                normalised_existing = self._normalise_discovery_metadata(
                    existing_info_raw,
                    source=existing_info_raw.get("source"),
                    include_last_seen=False,
                )
            else:  # noqa: E111
                normalised_existing = self._normalise_discovery_metadata(
                    None,
                    source=None,
                    include_last_seen=False,
                )

            if self._strip_dynamic_discovery_fields(normalised_existing) != comparison:  # noqa: E111
                return True

        for key, value in updates.items():
            if key == "discovery_info":  # noqa: E111
                continue
            if existing_data.get(key) != value:  # noqa: E111
                return True

        return False

    async def _handle_existing_discovery_entry(  # noqa: E111
        self,
        *,
        updates: Mapping[str, object],
        comparison: Mapping[str, object],
        reload_on_update: bool,
    ) -> ConfigFlowResult:
        """Abort or update when discovery encounters an existing entry.

        Args:
            updates: Updates to apply
            comparison: Comparison baseline
            reload_on_update: Whether to reload on update

        Returns:
            Config flow result
        """
        entry = await self._async_get_entry_for_unique_id()
        if entry is None:
            return self._abort_if_unique_id_configured(  # noqa: E111
                updates=dict(updates),
                reload_on_update=reload_on_update,
            )

        if not self._discovery_update_required(
            entry,
            updates=updates,
            comparison=comparison,
        ):
            return self.async_abort(reason="already_configured")  # noqa: E111

        if not reload_on_update:
            return self.async_abort(reason="already_configured")  # noqa: E111

        return await self.async_update_reload_and_abort(
            entry,
            data_updates=dict(updates),
            reason="already_configured",
        )

    def _prepare_discovery_updates(  # noqa: E111
        self,
        payload: Mapping[str, object],
        *,
        source: ConfigFlowDiscoverySource,
    ) -> tuple[DiscoveryUpdatePayload, ConfigFlowDiscoveryData]:
        """Normalise discovery metadata and build update payloads.

        Args:
            payload: Discovery payload
            source: Discovery source

        Returns:
            Tuple of (updates, comparison_baseline)
        """
        normalised = self._normalise_discovery_metadata(payload, source=source)
        comparison = self._strip_dynamic_discovery_fields(normalised)

        discovery_info: ConfigFlowDiscoveryData = copy.deepcopy(normalised)
        self._discovery_info = copy.deepcopy(normalised)

        updates: DiscoveryUpdatePayload = {
            "discovery_info": copy.deepcopy(normalised),
        }

        host = discovery_info.get("host") or discovery_info.get("ip")
        if host and isinstance(host, str):
            updates["host"] = host  # noqa: E111

        device = discovery_info.get("device")
        if device and isinstance(device, str):
            updates["device"] = device  # noqa: E111

        address = discovery_info.get("address")
        if address and isinstance(address, str):
            updates["address"] = address  # noqa: E111

        return updates, comparison

    def _format_discovery_info(self) -> str:  # noqa: E111
        """Format discovery info for display.

        Returns:
            Formatted discovery information
        """
        info = self._discovery_info
        source = info.get("source")
        if source == "zeroconf":
            hostname = info.get("hostname", "Unknown")  # noqa: E111
            host = info.get("host", "Unknown")  # noqa: E111
            return f"Device: {hostname}\nHost: {host}"  # noqa: E111
        if source == "dhcp":
            hostname = info.get("hostname", "Unknown")  # noqa: E111
            ip = info.get("ip", "Unknown")  # noqa: E111
            return f"Device: {hostname}\nIP: {ip}"  # noqa: E111
        return "Unknown device"

    @staticmethod  # noqa: E111
    def _is_dog_config_valid_for_flow(dog: Mapping[str, object]) -> bool:  # noqa: E111
        """Check if dog config is valid for flow.

        Args:
            dog: Dog configuration

        Returns:
            True if valid
        """
        return is_dog_config_payload_valid(
            cast(Mapping[str, JSONValue], dog),
        )

    async def async_step_add_dog(  # noqa: E111
        self,
        user_input: DogSetupStepInput | None = None,
    ) -> ConfigFlowResult:
        """Add a dog configuration with optimized validation.

        Args:
            user_input: User provided data

        Returns:
            Config flow result
        """
        async with timed_operation("add_dog_step"):
            errors: dict[str, str] = {}  # noqa: E111

            if user_input is not None:  # noqa: E111
                user_input_dict = cast(DogSetupStepInput, dict(user_input))
                try:
                    validated_input = await self._validate_dog_input_cached(  # noqa: E111
                        user_input_dict,
                    )
                    if validated_input:  # noqa: E111
                        dog_config = await self._create_dog_config(validated_input)
                        self._dogs.append(dog_config)
                        dog_id = dog_config.get(DOG_ID_FIELD)
                        if isinstance(dog_id, str):
                            self._existing_dog_ids.add(dog_id)  # noqa: E111
                        self._invalidate_profile_caches()
                        return await self.async_step_dog_modules()

                except FlowValidationError as err:
                    errors.update(err.as_form_errors())  # noqa: E111
                    if "base" not in errors:  # noqa: E111
                        _LOGGER.warning("Dog validation failed: %s", err)
                    else:  # noqa: E111
                        _LOGGER.warning(
                            "Dog validation failed: %s",
                            errors["base"],
                        )
                except Exception as err:
                    _LOGGER.error(  # noqa: E111
                        "Unexpected error during dog validation: %s",
                        err,
                    )
                    errors["base"] = "unknown_error"  # noqa: E111

            return self.async_show_form(  # noqa: E111
                step_id="add_dog",
                data_schema=DOG_SCHEMA,
                errors=errors,
                description_placeholders=dict(
                    cast(
                        Mapping[str, str],
                        _build_add_dog_summary_placeholders(
                            dogs_configured=len(self._dogs),
                            max_dogs=MAX_DOGS_PER_INTEGRATION,
                            discovery_hint=self._get_discovery_hint(),
                        ),
                    ),
                ),
            )

    def _get_validation_state_signature(self) -> str:  # noqa: E111
        """Get a signature representing current validation state.

        Returns:
            Validation state signature
        """
        existing_ids = "|".join(sorted(self._existing_dog_ids))
        return f"{len(self._dogs)}::{existing_ids}"

    async def _validate_dog_input_cached(  # noqa: E111
        self,
        user_input: DogSetupStepInput,
    ) -> DogSetupStepInput | None:
        """Validate dog input with caching for repeated validations.

        Args:
            user_input: User input to validate

        Returns:
            Validated input or None
        """
        config_flow_monitor.record_validation("dog_input_attempt")

        # MYPY FIX: Safe string conversion
        dog_id = user_input.get("dog_id")
        dog_name = user_input.get("dog_name")
        dog_weight = user_input.get("dog_weight")

        dog_id_str = str(dog_id) if dog_id is not None else ""
        dog_name_str = str(dog_name) if dog_name is not None else ""
        dog_weight_str = str(dog_weight) if dog_weight is not None else "0"

        cache_key = "_".join([dog_id_str, dog_name_str, dog_weight_str])
        state_signature = self._get_validation_state_signature()
        cached_entry = self._validation_cache.get(cache_key)
        now_ts = dt_util.utcnow().timestamp()

        if cached_entry is not None:
            cached_result_raw = cached_entry.get("result")  # noqa: E111
            cached_result = (  # noqa: E111
                cast(DogSetupStepInput, cached_result_raw)
                if isinstance(cached_result_raw, Mapping)
                else None
            )
            cached_state = cached_entry.get("state_signature")  # noqa: E111
            cached_at_raw = cached_entry.get("cached_at")  # noqa: E111
            cached_at = (  # noqa: E111
                float(cached_at_raw) if isinstance(cached_at_raw, int | float) else 0.0
            )

            if (  # noqa: E111
                cached_state == state_signature
                and cached_result is not None
                and now_ts - cached_at < 60
            ):
                config_flow_monitor.record_validation("dog_input_cache_hit")
                return cast(DogSetupStepInput, dict(cached_result))

        try:
            result = await self._validate_dog_input_optimized(user_input)  # noqa: E111
        except FlowValidationError:
            config_flow_monitor.record_validation("dog_input_error")  # noqa: E111
            raise  # noqa: E111

        cloned_result: DogSetupStepInput | None
        cloned_result = (
            None if result is None else cast(DogSetupStepInput, dict(result))
        )

        cache_payload: DogValidationCacheEntry = {
            "result": cloned_result,
            "cached_at": now_ts,
            "state_signature": state_signature,
        }
        self._validation_cache[cache_key] = cache_payload
        config_flow_monitor.record_validation("dog_input_validated")
        return cloned_result

    def _invalidate_profile_caches(self) -> None:  # noqa: E111
        """Invalidate cached profile estimates when configuration changes."""
        self._profile_estimates_cache.clear()

    async def _estimate_total_entities_cached(self) -> int:  # noqa: E111
        """Estimate total entities with improved caching.

        Returns:
            Estimated entity count
        """
        dogs_signature = hash(
            str(
                [
                    (
                        dog.get(DOG_ID_FIELD),
                        tuple(sorted(ensure_dog_modules_mapping(dog).items())),
                    )
                    for dog in self._dogs
                ],
            ),
        )
        cache_key = f"{self._entity_profile}_{len(self._dogs)}_{dogs_signature}"

        cached = self._profile_estimates_cache.get(cache_key)
        if cached is not None:
            return cached  # noqa: E111

        total = 0
        for dog in self._dogs:
            module_flags_mapping = ensure_dog_modules_mapping(dog)  # noqa: E111
            module_flags = {
                key: bool(value) for key, value in module_flags_mapping.items()
            }  # noqa: E111
            total += await self._entity_factory.estimate_entity_count_async(  # noqa: E111
                self._entity_profile,
                module_flags,
            )

        self._profile_estimates_cache[cache_key] = total
        return total

    def _get_discovery_hint(self) -> str:  # noqa: E111
        """Get hint text based on discovery info.

        Returns:
            Discovery hint text
        """
        if self._discovery_info:
            hostname = self._discovery_info.get("hostname", "Unknown")  # noqa: E111
            return f"Discovered device: {hostname}"  # noqa: E111
        return ""

    async def _validate_dog_input_optimized(  # noqa: E111
        self,
        user_input: DogSetupStepInput,
    ) -> DogSetupStepInput:
        """Validate dog input data with optimized performance.

        Args:
            user_input: Raw user input

        Returns:
            Validated input

        Raises:
            FlowValidationError: If validation fails
        """
        existing_names_set: set[str] = set()
        for dog in self._dogs:
            dog_name = dog.get(DOG_NAME_FIELD)  # noqa: E111
            if isinstance(dog_name, str):  # noqa: E111
                stripped = dog_name.strip().lower()
                if stripped:
                    existing_names_set.add(stripped)  # noqa: E111

        return validate_dog_setup_input(
            cast(Mapping[str, JSONValue], user_input),
            existing_ids=self._existing_dog_ids,
            existing_names=existing_names_set,
            current_dog_count=len(self._dogs),
            max_dogs=MAX_DOGS_PER_INTEGRATION,
        )

    async def _create_dog_config(  # noqa: E111
        self,
        validated_input: DogSetupStepInput,
    ) -> DogConfigData:
        """Create dog configuration from validated input.

        Args:
            validated_input: Validated input data

        Returns:
            Dog configuration data
        """
        dog_id_raw = validated_input.get("dog_id", "")
        dog_name_raw = validated_input.get("dog_name", "")

        dog_id = str(dog_id_raw).strip() if dog_id_raw is not None else ""
        dog_name = str(dog_name_raw).strip() if dog_name_raw is not None else ""

        breed_raw = validated_input.get("dog_breed")
        dog_breed: str | None
        if isinstance(breed_raw, str):
            stripped = breed_raw.strip()  # noqa: E111
            dog_breed = stripped or None  # noqa: E111
        else:
            dog_breed = None  # noqa: E111

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
            config["dog_breed"] = dog_breed  # noqa: E111
        if dog_age is not None:
            config["dog_age"] = dog_age  # noqa: E111
        if dog_weight is not None:
            config["dog_weight"] = dog_weight  # noqa: E111
        if dog_size is not None:
            config["dog_size"] = dog_size  # noqa: E111

        if self._discovery_info:
            config["discovery_info"] = cast(  # noqa: E111
                ConfigFlowDiscoveryData,
                dict(self._discovery_info),
            )

        return config

    async def async_step_dog_modules(  # noqa: E111
        self,
        user_input: DogModuleSelectionInput | None = None,
    ) -> ConfigFlowResult:
        """Configure optional modules for the newly added dog.

        Args:
            user_input: User provided data

        Returns:
            Config flow result
        """
        if not self._dogs:
            return await self.async_step_add_dog()  # noqa: E111

        current_dog = self._dogs[-1]

        if user_input is not None:
            existing_modules = current_dog.get(DOG_MODULES_FIELD)  # noqa: E111
            mapping_candidate: DogModulesConfig  # noqa: E111
            raw_mapping: DogModuleSelectionInput = {}  # noqa: E111

            if isinstance(user_input, Mapping):  # noqa: E111
                raw_mapping = cast(DogModuleSelectionInput, dict(user_input))

            if raw_mapping and any(  # noqa: E111
                flag in raw_mapping for flag in MODULE_TOGGLE_FLAG_BY_KEY.values()
            ):
                mapping_candidate = dog_modules_from_flow_input(
                    raw_mapping,
                    existing=existing_modules,
                )
            elif raw_mapping:  # noqa: E111
                mapping_candidate = cast(DogModulesConfig, dict(raw_mapping))
            else:  # noqa: E111
                mapping_candidate = coerce_dog_modules_config(user_input)

            filtered_candidate = cast(  # noqa: E111
                DogModulesConfig,
                {
                    key: bool(mapping_candidate.get(key))
                    for key in MODULE_SELECTION_KEYS
                    if key in mapping_candidate
                },
            )

            try:  # noqa: E111
                # Validate modules configuration
                modules = MODULES_SCHEMA(filtered_candidate)
                typed_modules = cast(DogModulesConfig, dict(modules))
                current_dog[DOG_MODULES_FIELD] = typed_modules
                self._invalidate_profile_caches()
                return await self.async_step_add_another_dog()

            except vol.Invalid as err:  # noqa: E111
                _LOGGER.warning("Module validation failed: %s", err)
                dog_name = current_dog.get(DOG_NAME_FIELD)
                dog_name_str = str(dog_name) if dog_name is not None else "Unknown"
                return self.async_show_form(
                    step_id="dog_modules",
                    data_schema=MODULES_SCHEMA,
                    errors={"base": "invalid_modules"},
                    description_placeholders=dict(
                        cast(
                            Mapping[str, str],
                            _build_dog_modules_form_placeholders(
                                dog_name=dog_name_str,
                                dogs_configured=len(self._dogs),
                                smart_defaults=self._get_smart_module_defaults(
                                    current_dog,
                                ),
                            ),
                        ),
                    ),
                )

        # Enhanced schema with smart defaults based on discovery
        enhanced_schema = self._get_enhanced_modules_schema(current_dog)
        dog_name = current_dog.get(DOG_NAME_FIELD)
        dog_name_str = str(dog_name) if dog_name is not None else "Unknown"

        return self.async_show_form(
            step_id="dog_modules",
            data_schema=enhanced_schema,
            description_placeholders=dict(
                cast(
                    Mapping[str, str],
                    _build_dog_modules_form_placeholders(
                        dog_name=dog_name_str,
                        dogs_configured=len(self._dogs),
                        smart_defaults=self._get_smart_module_defaults(
                            current_dog,
                        ),
                    ),
                ),
            ),
        )

    async def async_step_add_another(  # noqa: E111
        self,
        user_input: AddAnotherDogInput | None = None,
    ) -> ConfigFlowResult:
        """Ask if user wants to add another dog with enhanced logic.

        Args:
            user_input: User provided data

        Returns:
            Config flow result
        """
        if user_input is not None:
            add_another = user_input.get("add_another", False)  # noqa: E111
            at_limit = len(self._dogs) >= MAX_DOGS_PER_INTEGRATION  # noqa: E111

            if add_another and not at_limit:  # noqa: E111
                return await self.async_step_add_dog()
            return await self.async_step_entity_profile()  # noqa: E111

        # Enhanced logic for smart recommendations
        can_add_more = len(self._dogs) < MAX_DOGS_PER_INTEGRATION

        schema = (
            vol.Schema(
                {
                    vol.Optional(
                        "add_another", default=False
                    ): selector.BooleanSelector(),
                },
            )
            if can_add_more
            else vol.Schema({})
        )

        return self.async_show_form(
            step_id="add_another",
            data_schema=schema,
            description_placeholders=dict(
                cast(
                    Mapping[str, str],
                    _build_add_another_placeholders(
                        dogs_configured=len(self._dogs),
                        dogs_list=self._format_dogs_list_enhanced(),
                        can_add_more=can_add_more,
                        max_dogs=MAX_DOGS_PER_INTEGRATION,
                        performance_note=self._get_performance_note(),
                    ),
                ),
            ),
        )

    def _get_performance_note(self) -> str:  # noqa: E111
        """Get performance note based on current configuration.

        Returns:
            Performance guidance text
        """
        dog_count = len(self._dogs)
        if dog_count >= 5:
            return "Consider 'basic' profile for better performance with many dogs"  # noqa: E111
        if dog_count >= 3:
            return "Multiple dogs configured - 'standard' profile recommended"  # noqa: E111
        return "Single/few dogs - 'advanced' profile available for full features"

    async def async_step_entity_profile(  # noqa: E111
        self,
        user_input: ProfileSelectionInput | None = None,
    ) -> ConfigFlowResult:
        """Select entity profile with performance guidance.

        Args:
            user_input: User provided data

        Returns:
            Config flow result
        """
        if user_input is not None:
            try:  # noqa: E111
                self._entity_profile = validate_profile_selection(
                    user_input,
                )
                modules = self._aggregate_enabled_modules()
                gps_enabled = modules.get(MODULE_GPS, False)
                if gps_enabled:
                    self._enabled_modules = modules  # noqa: E111
                    return await self.async_step_configure_modules()  # noqa: E111
                return await self.async_step_final_setup()

            except vol.Invalid as err:  # noqa: E111
                _LOGGER.warning("Profile validation failed: %s", err)
                return self.async_show_form(
                    step_id="entity_profile",
                    data_schema=PROFILE_SCHEMA,
                    errors={"base": "invalid_profile"},
                    description_placeholders=dict(
                        cast(
                            Mapping[str, str],
                            freeze_placeholders(
                                {
                                    "dogs_count": str(len(self._dogs)),
                                    "profiles_info": self._get_profiles_info_enhanced(),
                                    "profiles_summary": build_profile_summary_text(),
                                    "recommendation": self._get_profile_recommendation(),
                                },
                            ),
                        ),
                    ),
                )

        estimated_entities = await self._estimate_total_entities()
        return self.async_show_form(
            step_id="entity_profile",
            data_schema=PROFILE_SCHEMA,
            description_placeholders=dict(
                cast(
                    Mapping[str, str],
                    freeze_placeholders(
                        {
                            "dogs_count": str(len(self._dogs)),
                            "profiles_info": self._get_profiles_info_enhanced(),
                            "estimated_entities": str(estimated_entities),
                            "profiles_summary": build_profile_summary_text(),
                            "recommendation": self._get_profile_recommendation(),
                        },
                    ),
                ),
            ),
        )

    def _get_profile_recommendation(self) -> str:  # noqa: E111
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
            return "Recommended: 'basic' profile for optimal performance"  # noqa: E111
        if dog_count >= 3 or total_modules >= 12:
            return "Recommended: 'standard' profile for balanced functionality"  # noqa: E111
        return "Recommended: 'standard' or 'advanced' profile for full features"

    async def async_step_final_setup(  # noqa: E111
        self,
        user_input: ConfigFlowUserInput | None = None,
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
            if user_input is None:  # noqa: E111
                return self.async_show_form(
                    step_id="final_setup", data_schema=vol.Schema({})
                )

            if not self._dogs:  # noqa: E111
                raise PawControlSetupError("No dogs configured for setup")

            validation_results = await self._perform_comprehensive_validation()  # noqa: E111
            if not validation_results["valid"]:  # noqa: E111
                _LOGGER.error(
                    "Final validation failed: %s",
                    validation_results["errors"],
                )
                raise PawControlSetupError(
                    f"Setup validation failed: {'; '.join(validation_results['errors'])}",
                )

            if not self._validate_profile_compatibility():  # noqa: E111
                _LOGGER.warning("Profile compatibility issues detected")

            try:  # noqa: E111
                config_data, options_data = self._build_config_entry_data()

                profile_info = ENTITY_PROFILES[self._entity_profile]
                title = self._generate_entry_title(profile_info)

                return self.async_create_entry(
                    title=title,
                    data=config_data,
                    options=options_data,
                )

            except Exception as err:  # noqa: E111
                _LOGGER.error("Final setup failed: %s", err)
                raise PawControlSetupError(f"Setup failed: {err}") from err

    async def _perform_comprehensive_validation(self) -> FinalSetupValidationResult:  # noqa: E111
        """Perform comprehensive final validation.

        Returns:
            Validation result
        """
        async with timed_operation("final_validation"):
            errors: list[str] = []  # noqa: E111

            for dog in self._dogs:  # noqa: E111
                if not self._is_dog_config_valid_for_flow(
                    cast(Mapping[str, object], dog),
                ):
                    dog_id = dog.get(DOG_ID_FIELD, "unknown")  # noqa: E111
                    dog_id_str = str(dog_id) if dog_id is not None else "unknown"  # noqa: E111
                    errors.append(f"Invalid dog configuration: {dog_id_str}")  # noqa: E111

            estimated_entities = await self._estimate_total_entities_cached()  # noqa: E111
            if estimated_entities > 200:  # noqa: E111
                errors.append(
                    f"Too many estimated entities: {estimated_entities}",
                )

            if self._entity_profile not in VALID_PROFILES:  # noqa: E111
                errors.append(f"Invalid profile: {self._entity_profile}")

            result: FinalSetupValidationResult = {  # noqa: E111
                "valid": len(errors) == 0,
                "errors": errors,
                "estimated_entities": estimated_entities,
            }

        config_flow_monitor.record_validation("final_validation")
        return result

    def _validate_profile_compatibility(self) -> bool:  # noqa: E111
        """Validate profile compatibility with configuration.

        Returns:
            True if profile is compatible
        """
        for dog in self._dogs:
            modules = ensure_dog_modules_mapping(dog)  # noqa: E111
            if not self._entity_factory.validate_profile_for_modules(  # noqa: E111
                self._entity_profile,
                modules,
            ):
                return False

        return True

    def _build_config_entry_data(  # noqa: E111
        self,
    ) -> tuple[ConfigEntryDataPayload, ConfigEntryOptionsPayload]:
        """Build optimized config entry data.

        Returns:
            Tuple of (config_data, options_data)
        """
        config_data: ConfigEntryDataPayload = {
            "name": self._integration_name,
            "dogs": self._dogs,
            "entity_profile": self._entity_profile,
            "setup_timestamp": dt_util.utcnow().isoformat(),
        }

        if self._external_entities:
            config_data = cast(ConfigEntryDataPayload, dict(config_data))  # noqa: E111
            config_data["external_entities"] = cast(  # noqa: E111
                ExternalEntityConfig,
                dict(self._external_entities),
            )

        # Add discovery info if available
        if self._discovery_info:
            config_data["discovery_info"] = self._discovery_info  # noqa: E111

        options_data: ConfigEntryOptionsPayload = {
            "entity_profile": self._entity_profile,
            "dashboard_enabled": True,
            "dashboard_auto_create": True,
            "performance_monitoring": True,
        }

        settings = self._global_settings
        performance_mode = normalize_performance_mode(
            settings.get("performance_mode"),
            fallback=cast(PerformanceMode, DEFAULT_PERFORMANCE_MODE),
        )
        options_data["performance_mode"] = performance_mode

        options_data["enable_analytics"] = bool(
            settings.get("enable_analytics", False),
        )
        options_data["enable_cloud_backup"] = bool(
            settings.get("enable_cloud_backup", False),
        )
        options_data["debug_logging"] = bool(
            settings.get("debug_logging", False),
        )

        data_retention_raw = settings.get(
            "data_retention_days", DEFAULT_DATA_RETENTION_DAYS
        )
        options_data["data_retention_days"] = (
            int(data_retention_raw)
            if isinstance(data_retention_raw, int | float)
            else DEFAULT_DATA_RETENTION_DAYS
        )

        # Derive default API endpoint/token from discovery results when available
        discovery_info = self._discovery_info or {}
        if discovery_info:
            host = discovery_info.get("host") or discovery_info.get("ip")  # noqa: E111
            port = discovery_info.get("port")  # noqa: E111
            properties = discovery_info.get("properties", {})  # noqa: E111

            if host and isinstance(host, str) and "api_endpoint" not in options_data:  # noqa: E111
                raw_https: object = (
                    properties.get("https") if isinstance(properties, dict) else None
                )
                if isinstance(raw_https, str):
                    normalized = raw_https.strip().lower()  # noqa: E111
                    https_enabled = normalized in {"true", "1", "on", "yes"}  # noqa: E111
                elif isinstance(raw_https, bool | int | float):
                    https_enabled = bool(raw_https)  # noqa: E111
                else:
                    https_enabled = False  # noqa: E111

                scheme = "https" if https_enabled else "http"
                if port and isinstance(port, int):
                    options_data["api_endpoint"] = f"{scheme}://{host}:{port}"  # noqa: E111
                else:
                    options_data["api_endpoint"] = f"{scheme}://{host}"  # noqa: E111

            if isinstance(properties, dict):  # noqa: E111
                api_token = properties.get("api_key") or discovery_info.get("api_key")
                if (
                    isinstance(api_token, str)
                    and api_token
                    and "api_token" not in options_data
                ):
                    options_data["api_token"] = api_token  # noqa: E111

        return config_data, options_data

    def _generate_entry_title(self, profile_info: EntityProfileDefinition) -> str:  # noqa: E111
        """Generate descriptive entry title.

        Args:
            profile_info: Profile information

        Returns:
            Entry title
        """
        profile_name = profile_info.get("name", "Unknown")
        return f"Paw Control ({profile_name})"

    async def _estimate_total_entities(self) -> int:  # noqa: E111
        """Estimate total entities with caching.

        Returns:
            Estimated total entity count
        """
        return await self._estimate_total_entities_cached()

    def _format_dogs_list_enhanced(self) -> str:  # noqa: E111
        """Format enhanced list of configured dogs.

        Returns:
            Formatted dogs list with module info
        """
        if not self._dogs:
            return "No dogs configured yet."  # noqa: E111

        dogs_list = []
        for i, dog in enumerate(self._dogs, 1):
            modules = ensure_dog_modules_mapping(dog)  # noqa: E111
            enabled_modules = [name for name, enabled in modules.items() if enabled]  # noqa: E111
            module_summary = ", ".join(enabled_modules) if enabled_modules else "none"  # noqa: E111

            dog_name = dog.get(DOG_NAME_FIELD)  # noqa: E111
            dog_id = dog.get(DOG_ID_FIELD)  # noqa: E111
            dog_size = dog.get(CONF_DOG_SIZE, "unknown")  # noqa: E111
            dog_weight = dog.get(CONF_DOG_WEIGHT, 0)  # noqa: E111

            dog_name_str = str(dog_name) if dog_name is not None else "Unknown"  # noqa: E111
            dog_id_str = str(dog_id) if dog_id is not None else "unknown"  # noqa: E111
            dog_size_str = str(dog_size) if dog_size is not None else "unknown"  # noqa: E111
            dog_weight_num = (
                float(dog_weight) if isinstance(dog_weight, int | float) else 0
            )  # noqa: E111

            dogs_list.append(  # noqa: E111
                f"{i}. {dog_name_str} ({dog_id_str})\n"
                f"   Size: {dog_size_str}, "
                f"Weight: {dog_weight_num}kg\n"
                f"   Modules: {module_summary}",
            )

        return "\n\n".join(dogs_list)

    def _get_profiles_info_enhanced(self) -> str:  # noqa: E111
        """Get enhanced entity profiles information.

        Returns:
            Formatted profiles information with performance guidance
        """
        profiles_info = []
        for config in ENTITY_PROFILES.values():
            estimated_for_profile = 0  # noqa: E111
            for dog in self._dogs:  # noqa: E111
                modules = ensure_dog_modules_mapping(dog)
                # Rough estimation without full factory
                estimated_for_profile += sum(
                    3 if enabled else 0 for enabled in modules.values()
                )

            name = config.get("name", "Unknown")  # noqa: E111
            description = config.get("description", "")  # noqa: E111
            performance_impact = config.get("performance_impact", "Unknown")  # noqa: E111
            recommended_for = config.get("recommended_for", "")  # noqa: E111

            profiles_info.append(  # noqa: E111
                f"• {name}: {description}\n"
                f"  Performance: {performance_impact}\n"
                f"  Estimated entities: ~{estimated_for_profile} per dog\n"
                f"  Best for: {recommended_for}",
            )
        return "\n\n".join(profiles_info)

    @staticmethod  # noqa: E111
    def _normalise_string_list(values: Any) -> list[str]:  # noqa: E111
        """Normalise arbitrary iterables to a list of non-empty strings.

        Args:
            values: Values to normalize

        Returns:
            List of strings
        """
        if not values:
            return []  # noqa: E111

        normalised: list[str] = []
        for value in values:
            if value is None:  # noqa: E111
                continue
            if isinstance(value, str):  # noqa: E111
                candidate = value.strip()
                if candidate:
                    normalised.append(candidate)  # noqa: E111
                continue
            normalised.append(str(value))  # noqa: E111
        return normalised

    def _aggregate_enabled_modules(self) -> DogModulesConfig:  # noqa: E111
        """Aggregate enabled modules across all configured dogs.

        Returns:
            Aggregated module configuration
        """
        aggregated: DogModulesConfig = {}
        for dog in self._dogs:
            modules = ensure_dog_modules_mapping(dog)  # noqa: E111
            for module, enabled in modules.items():  # noqa: E111
                if module not in MODULE_TOGGLE_KEYS:
                    continue  # noqa: E111

                module_key = cast(ModuleToggleKey, module)
                if enabled:
                    aggregated[module_key] = True  # noqa: E111
                else:
                    aggregated.setdefault(module_key, False)  # noqa: E111

        return aggregated

    async def async_step_configure_modules(  # noqa: E111
        self,
        user_input: ModuleConfigurationStepInput | None = None,
    ) -> ConfigFlowResult:
        """Update cached module summary before delegating to mixin.

        Args:
            user_input: User input

        Returns:
            Config flow result
        """
        self._enabled_modules = self._aggregate_enabled_modules()
        return await super().async_step_configure_modules(user_input)

    async def async_step_configure_dashboard(  # noqa: E111
        self,
        user_input: DashboardConfigurationStepInput | None = None,
    ) -> ConfigFlowResult:
        """Delegate dashboard configuration to the dashboard mixin implementation.

        Args:
            user_input: User input

        Returns:
            Config flow result
        """
        return await DashboardFlowMixin.async_step_configure_dashboard(self, user_input)

    async def async_step_reconfigure(  # noqa: E111
        self,
        user_input: ReconfigureProfileInput | None = None,
    ) -> ConfigFlowResult:
        """Handle reconfiguration with typed telemetry and validation.

        Args:
            user_input: User input

        Returns:
            Config flow result
        """
        entry_id = self.context.get("entry_id")
        entry = (
            self.hass.config_entries.async_get_entry(entry_id)
            if entry_id is not None
            else None
        )
        if entry is None:
            reconfigure_error = ReconfigureRequiredError(  # noqa: E111
                "Config entry not found for reconfiguration",
                context={"entry_id": entry_id},
            )
            raise ConfigEntryNotReady(str(reconfigure_error)) from reconfigure_error  # noqa: E111

        dogs, merge_notes = self._extract_entry_dogs(entry)
        current_profile = self._resolve_entry_profile(entry)
        form_schema = vol.Schema(
            {
                vol.Required("entity_profile", default=current_profile): vol.In(
                    VALID_PROFILES,
                ),
            },
        )
        base_placeholders = await self._build_reconfigure_placeholders(
            entry,
            dogs,
            current_profile,
            merge_notes,
        )

        if user_input is not None:
            try:  # noqa: E111
                profile_data = cast(
                    ReconfigureProfileInput,
                    PROFILE_SCHEMA(dict(user_input)),
                )
                new_profile = profile_data["entity_profile"]
            except vol.Invalid as err:  # noqa: E111
                return self.async_show_form(
                    step_id="reconfigure",
                    data_schema=form_schema,
                    errors={"base": "invalid_profile"},
                    description_placeholders=dict(
                        cast(
                            Mapping[str, str],
                            freeze_placeholders(
                                {**base_placeholders, "error_details": str(err)},
                            ),
                        ),
                    ),
                )

            if new_profile == current_profile:  # noqa: E111
                return self.async_show_form(
                    step_id="reconfigure",
                    data_schema=form_schema,
                    errors={"base": "profile_unchanged"},
                    description_placeholders=dict(
                        cast(
                            Mapping[str, str],
                            freeze_placeholders(
                                {**base_placeholders, "requested_profile": new_profile},
                            ),
                        ),
                    ),
                )

            unique_id = entry.unique_id  # noqa: E111
            if unique_id:  # noqa: E111
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_mismatch(reason="wrong_account")
            else:  # noqa: E111
                _LOGGER.debug(
                    "Skipping unique_id guard for reconfigure entry %s",
                    entry.entry_id,
                )

            compatibility = self._check_profile_compatibility(  # noqa: E111
                new_profile,
                dogs,
            )
            if compatibility["warnings"]:  # noqa: E111
                _LOGGER.warning(
                    "Profile %s compatibility warnings: %s",
                    new_profile,
                    "; ".join(compatibility["warnings"]),
                )

            health_check = await self._check_config_health_enhanced(entry)  # noqa: E111
            if not health_check.get("healthy", True):  # noqa: E111
                issues = self._normalise_string_list(
                    health_check.get("issues", []),
                )
                if issues:
                    _LOGGER.warning(  # noqa: E111
                        "Configuration health issues before reconfigure: %s",
                        "; ".join(issues),
                    )

            timestamp = dt_util.utcnow().isoformat()  # noqa: E111
            estimated_entities = await self._estimate_entities_for_reconfigure(  # noqa: E111
                dogs,
                new_profile,
            )
            previous_profile = current_profile  # noqa: E111
            valid_dogs = sum(  # noqa: E111
                1
                for dog in dogs
                if self._is_dog_config_valid_for_flow(
                    cast(Mapping[str, object], dog),
                )
            )

            telemetry: ReconfigureTelemetry = {  # noqa: E111
                "requested_profile": new_profile,
                "previous_profile": previous_profile,
                "dogs_count": len(dogs),
                "estimated_entities": estimated_entities,
                "timestamp": timestamp,
                "version": self.VERSION,
            }
            if compatibility["warnings"]:  # noqa: E111
                telemetry["compatibility_warnings"] = compatibility["warnings"]
            telemetry["health_summary"] = health_check  # noqa: E111
            telemetry["valid_dogs"] = valid_dogs  # noqa: E111
            merge_notes_normalised = self._normalise_string_list(merge_notes)  # noqa: E111
            if merge_notes_normalised:  # noqa: E111
                telemetry["merge_notes"] = merge_notes_normalised

            data_updates: ReconfigureDataUpdates = {  # noqa: E111
                "entity_profile": new_profile,
                "reconfigure_timestamp": timestamp,
                "reconfigure_version": self.VERSION,
            }
            options_updates: ReconfigureOptionsUpdates = {  # noqa: E111
                "entity_profile": new_profile,
                "last_reconfigure": timestamp,
                "previous_profile": previous_profile,
                "reconfigure_telemetry": telemetry,
            }

            return await self.async_update_reload_and_abort(  # noqa: E111
                entry,
                data_updates=data_updates,
                options_updates=options_updates,
                reason="reconfigure_successful",
            )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=form_schema,
            description_placeholders=dict(cast(Mapping[str, str], base_placeholders)),
        )

    def _extract_entry_dogs(  # noqa: E111
        self,
        entry: ConfigEntry,
    ) -> tuple[list[DogConfigData], list[str]]:
        """Return the typed dog configuration list for the given entry.

        Args:
            entry: Config entry

        Returns:
            Tuple of (dogs, merge_notes)
        """
        merged: dict[str, DogConfigData] = {}
        merge_notes: list[str] = []

        for dog in self._normalise_entry_dogs(entry):
            self._merge_dog_entry(  # noqa: E111
                merged,
                dog,
                merge_notes,
                source="config_entry_data",
            )

        if isinstance(entry.options, Mapping):
            dogs_raw = entry.options.get(CONF_DOGS)  # noqa: E111
            for dog in self._normalise_dogs_payload(dogs_raw):  # noqa: E111
                self._merge_dog_entry(
                    merged,
                    dog,
                    merge_notes,
                    source="config_entry_options",
                )

            dog_options_raw = entry.options.get(CONF_DOG_OPTIONS)  # noqa: E111
            for dog in self._normalise_dogs_payload(dog_options_raw):  # noqa: E111
                self._merge_dog_entry(
                    merged,
                    dog,
                    merge_notes,
                    source="options_dog_options",
                )

        data_dog_options_raw = entry.data.get(CONF_DOG_OPTIONS)
        for dog in self._normalise_dogs_payload(data_dog_options_raw):
            self._merge_dog_entry(  # noqa: E111
                merged,
                dog,
                merge_notes,
                source="data_dog_options",
            )

        return list(merged.values()), merge_notes

    def _resolve_entry_profile(self, entry: ConfigEntry) -> str:  # noqa: E111
        """Resolve the current profile from entry options or data.

        Args:
            entry: Config entry

        Returns:
            Profile name
        """
        profile_candidate = entry.options.get("entity_profile")
        if isinstance(profile_candidate, str) and profile_candidate in VALID_PROFILES:
            return profile_candidate  # noqa: E111

        data_profile = entry.data.get("entity_profile")
        if isinstance(data_profile, str) and data_profile in VALID_PROFILES:
            return data_profile  # noqa: E111

        return DEFAULT_PROFILE

    async def _build_reconfigure_placeholders(  # noqa: E111
        self,
        entry: ConfigEntry,
        dogs: list[DogConfigData],
        profile: str,
        merge_notes: Sequence[str],
    ) -> ConfigFlowPlaceholders:
        """Build description placeholders for the reconfigure form.

        Args:
            entry: Config entry
            dogs: Dogs configuration
            profile: Current profile
            merge_notes: Merge notes

        Returns:
            Placeholders dict
        """
        estimated_entities = await self._estimate_entities_for_reconfigure(
            dogs,
            profile,
        )
        valid_dogs = sum(
            1
            for dog in dogs
            if self._is_dog_config_valid_for_flow(
                cast(Mapping[str, object], dog),
            )
        )
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
            },
        )
        placeholders.update(
            self._reconfigure_history_placeholders(
                cast(Mapping[str, JSONValue], entry.options),
            ),
        )
        return freeze_placeholders(
            cast(dict[str, bool | int | float | str], placeholders),
        )

    def _reconfigure_history_placeholders(  # noqa: E111
        self,
        options: Mapping[str, JSONValue],
    ) -> ReconfigureFormPlaceholders:
        """Return placeholders describing the latest reconfigure telemetry.

        Args:
            options: Entry options

        Returns:
            History placeholders
        """
        telemetry_raw = options.get("reconfigure_telemetry")
        telemetry = telemetry_raw if isinstance(telemetry_raw, Mapping) else None
        timestamp_raw = options.get("last_reconfigure")

        history: ReconfigureFormPlaceholders = cast(
            ReconfigureFormPlaceholders,
            clone_placeholders(RECONFIGURE_FORM_PLACEHOLDERS_TEMPLATE),
        )

        if telemetry is None:
            history["last_reconfigure"] = self._format_local_timestamp(  # noqa: E111
                timestamp_raw,
            )
            history["reconfigure_requested_profile"] = "Not recorded"  # noqa: E111
            history["reconfigure_previous_profile"] = "Not recorded"  # noqa: E111
            history["reconfigure_dogs"] = "0"  # noqa: E111
            history["reconfigure_entities"] = "0"  # noqa: E111
            history["reconfigure_health"] = "No recent health summary"  # noqa: E111
            history["reconfigure_warnings"] = "None"  # noqa: E111
            return history  # noqa: E111

        requested_profile_raw = telemetry.get("requested_profile", "")
        previous_profile_raw = telemetry.get("previous_profile", "")

        requested_profile = (
            str(requested_profile_raw) if requested_profile_raw else "Unknown"
        )
        previous_profile = (
            str(previous_profile_raw) if previous_profile_raw else "Unknown"
        )

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

        history["last_reconfigure"] = self._format_local_timestamp(
            last_recorded,
        )
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
        history["reconfigure_health"] = self._summarise_health_summary(
            health_summary,
        )
        history["reconfigure_warnings"] = ", ".join(warnings) if warnings else "None"
        if merge_notes:
            history["reconfigure_merge_notes"] = "\n".join(merge_notes)  # noqa: E111
        return history

    def _format_local_timestamp(self, timestamp: Any) -> str:  # noqa: E111
        """Return a human-friendly representation for an ISO timestamp.

        Args:
            timestamp: ISO timestamp

        Returns:
            Formatted timestamp
        """
        if not isinstance(timestamp, str) or not timestamp:
            return "Never reconfigured"  # noqa: E111

        parse_datetime = getattr(dt_util, "parse_datetime", None)
        parsed = parse_datetime(timestamp) if callable(parse_datetime) else None
        if parsed is None:
            candidate = timestamp.replace("Z", "+00:00")  # noqa: E111
            try:  # noqa: E111
                parsed = datetime.fromisoformat(candidate)
            except ValueError:  # noqa: E111
                return timestamp

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt_util.UTC)  # noqa: E111

        as_local = getattr(dt_util, "as_local", None)
        local_dt = as_local(parsed) if callable(as_local) else parsed.astimezone()
        return local_dt.strftime("%Y-%m-%d %H:%M:%S %Z")

    def _normalise_entry_dogs(self, entry: ConfigEntry) -> list[DogConfigData]:  # noqa: E111
        """Normalise raw dog payloads from a config entry to typed dictionaries.

        Args:
            entry: Config entry

        Returns:
            List of dog configurations
        """
        dogs_raw = entry.data.get(CONF_DOGS)
        return self._normalise_dogs_payload(
            dogs_raw,
            preserve_empty_name=True,
        )

    def _clone_merge_value(self, value: Any) -> Any:  # noqa: E111
        """Return a defensive copy of ``value`` for nested migration merges.

        Args:
            value: Value to clone

        Returns:
            Cloned value
        """
        if isinstance(value, Mapping):
            return self._merge_nested_mapping(value, {})  # noqa: E111
        if isinstance(value, Sequence) and not isinstance(
            value,
            str | bytes | bytearray,
        ):
            return [self._clone_merge_value(item) for item in value]  # noqa: E111
        return value

    def _sequence_requests_removal(self, value: Sequence[Any]) -> bool:  # noqa: E111
        """Return ``True`` when ``value`` signals that the list should clear.

        Args:
            value: Sequence to check

        Returns:
            True if removal requested
        """
        for item in value:
            if isinstance(item, Mapping) and item.get(_LIST_REMOVE_DIRECTIVE):  # noqa: E111
                return True
            if item == _LIST_REMOVE_DIRECTIVE:  # noqa: E111
                return True
        return False

    def _sequence_contains(self, items: Sequence[Any], candidate: Any) -> bool:  # noqa: E111
        """Return ``True`` when ``candidate`` already exists in ``items``.

        Args:
            items: Items to search
            candidate: Value to find

        Returns:
            True if found
        """
        return any(existing == candidate for existing in items)

    def _merge_sequence_values(  # noqa: E111
        self,
        existing: Any,
        override: Sequence[Any],
    ) -> list[Any]:
        """Merge sequence values without mutating the originals.

        Args:
            existing: Existing sequence
            override: Override sequence

        Returns:
            Merged list
        """
        if self._sequence_requests_removal(override):
            return []  # noqa: E111

        existing_sequence: Sequence[Any] | None
        if isinstance(existing, Sequence) and not isinstance(
            existing,
            str | bytes | bytearray,
        ):
            existing_sequence = existing  # noqa: E111
        else:
            existing_sequence = None  # noqa: E111

        override_items = [self._clone_merge_value(item) for item in override]

        if override_items:
            merged_items = list(override_items)  # noqa: E111
            if existing_sequence is not None:  # noqa: E111
                for item in existing_sequence:
                    cloned_item = self._clone_merge_value(item)  # noqa: E111
                    if not self._sequence_contains(merged_items, cloned_item):  # noqa: E111
                        merged_items.append(cloned_item)
            return merged_items  # noqa: E111

        if existing_sequence is None:
            return []  # noqa: E111

        return [self._clone_merge_value(item) for item in existing_sequence]

    def _merge_nested_mapping(  # noqa: E111
        self,
        base: Mapping[str, object] | None,
        override: Mapping[str, object],
    ) -> JSONMutableMapping:
        """Merge nested mappings without mutating the original payloads.

        Args:
            base: Base mapping
            override: Override mapping

        Returns:
            Merged mapping
        """
        merged: JSONMutableMapping = {}

        if isinstance(base, Mapping):
            for key, value in base.items():  # noqa: E111
                merged[key] = self._clone_merge_value(value)

        for key, value in override.items():
            if value is None:  # noqa: E111
                continue
            if isinstance(value, Mapping):  # noqa: E111
                existing = merged.get(key)
                existing_mapping = existing if isinstance(existing, Mapping) else None
                merged[key] = self._merge_nested_mapping(
                    existing_mapping,
                    value,
                )
                continue
            if isinstance(value, Sequence) and not isinstance(  # noqa: E111
                value,
                str | bytes | bytearray,
            ):
                merged[key] = self._merge_sequence_values(
                    merged.get(key),
                    value,
                )
                continue
            merged[key] = cast(JSONValue, value)  # noqa: E111

        return merged

    def _merge_dog_entry(  # noqa: E111
        self,
        merged: dict[str, DogConfigData],
        candidate: DogConfigData,
        merge_notes: list[str],
        *,
        source: str,
    ) -> None:
        """Merge ``candidate`` into ``merged`` keyed by dog identifier.

        Args:
            merged: Target dictionary
            candidate: Dog to merge
            merge_notes: Notes list to update
            source: Source identifier
        """
        dog_id = candidate.get(DOG_ID_FIELD)
        if not isinstance(dog_id, str) or not dog_id:
            return  # noqa: E111

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
            merged[dog_id] = candidate  # noqa: E111
            if not baseline_source:  # noqa: E111
                merge_notes.append(
                    f"{candidate_name}: your {source_label} added a dog configuration.",
                )
            return  # noqa: E111

        combined: JSONMutableMapping = cast(JSONMutableMapping, dict(existing))

        existing_name_value = existing.get(DOG_NAME_FIELD)
        existing_name = (
            existing_name_value.strip()
            if isinstance(existing_name_value, str) and existing_name_value.strip()
            else ""
        )

        module_changes: list[str] = []
        modules_override = candidate.get(DOG_MODULES_FIELD)
        if isinstance(modules_override, Mapping):
            current_modules = coerce_dog_modules_config(  # noqa: E111
                cast(
                    Mapping[str, object] | None,
                    combined.get(DOG_MODULES_FIELD),
                ),
            )
            override_modules = coerce_dog_modules_config(modules_override)  # noqa: E111
            merged_modules: DogModulesConfig = cast(  # noqa: E111
                DogModulesConfig,
                dict(current_modules),
            )
            for module, enabled in override_modules.items():  # noqa: E111
                toggle = cast(ModuleToggleKey, module)
                enabled_flag = cast(bool, enabled)
                if current_modules.get(toggle) != enabled_flag:
                    action = "enabled" if enabled_flag else "disabled"  # noqa: E111
                    module_changes.append(f"{action} {module}")  # noqa: E111
                merged_modules[toggle] = enabled_flag
            combined[DOG_MODULES_FIELD] = cast(JSONValue, merged_modules)  # noqa: E111

        for key, value in candidate.items():
            if key in (DOG_ID_FIELD, DOG_MODULES_FIELD):  # noqa: E111
                continue
            if key == DOG_NAME_FIELD:  # noqa: E111
                if isinstance(value, str):
                    trimmed_name = value.strip()  # noqa: E111
                    if not trimmed_name:  # noqa: E111
                        continue
                    if trimmed_name == dog_id:  # noqa: E111
                        combined_name_value = combined.get(DOG_NAME_FIELD)
                        if (
                            not isinstance(combined_name_value, str)
                            or not combined_name_value.strip()
                        ):
                            combined[DOG_NAME_FIELD] = trimmed_name  # noqa: E111
                    else:  # noqa: E111
                        combined[DOG_NAME_FIELD] = trimmed_name
                continue
            if value is None:  # noqa: E111
                continue
            if isinstance(value, Mapping):  # noqa: E111
                existing_value = combined.get(key)
                existing_mapping = (
                    existing_value if isinstance(existing_value, Mapping) else None
                )
                combined[key] = self._merge_nested_mapping(
                    existing_mapping,
                    value,
                )
                continue
            if isinstance(value, Sequence) and not isinstance(  # noqa: E111
                value,
                str | bytes | bytearray,
            ):
                combined[key] = self._merge_sequence_values(
                    combined.get(key),
                    value,
                )
                continue
            combined[key] = cast(JSONValue, value)  # noqa: E111

        merged[dog_id] = cast(DogConfigData, combined)

        updated_name_value = combined.get(DOG_NAME_FIELD)
        updated_name = (
            updated_name_value.strip()
            if isinstance(updated_name_value, str) and updated_name_value.strip()
            else ""
        )
        display_target = updated_name or dog_id

        if baseline_source:
            return  # noqa: E111

        if module_changes:
            formatted_changes = ", ".join(sorted(module_changes))  # noqa: E111
            merge_notes.append(  # noqa: E111
                f"{display_target}: your {source_label} {formatted_changes}.",
            )

        if updated_name and updated_name != existing_name:
            if existing_name:  # noqa: E111
                merge_notes.append(
                    f"{dog_id}: your {source_label} renamed this dog from '{existing_name}' to '{updated_name}'.",  # noqa: E501
                )
            else:  # noqa: E111
                merge_notes.append(
                    f"{dog_id}: your {source_label} set the name to '{updated_name}'.",
                )

    def _normalise_dogs_payload(  # noqa: E111
        self,
        payload: Any,
        *,
        preserve_empty_name: bool = False,
    ) -> list[DogConfigData]:
        """Return a list of dog mappings extracted from ``payload``.

        Args:
            payload: Payload to normalize
            preserve_empty_name: Whether to preserve empty names

        Returns:
            List of dog configs
        """
        dogs: list[DogConfigData] = []

        if isinstance(payload, Sequence) and not isinstance(
            payload,
            str | bytes | bytearray,
        ):
            for raw in payload:  # noqa: E111
                candidate = self._build_dog_candidate(
                    raw,
                    preserve_empty_name=preserve_empty_name,
                )
                if candidate is not None:
                    dogs.append(candidate)  # noqa: E111
            return dogs  # noqa: E111

        if isinstance(payload, Mapping):
            for key, raw in payload.items():  # noqa: E111
                fallback_id = key if isinstance(key, str) and key else None
                candidate = self._build_dog_candidate(
                    raw,
                    fallback_id=fallback_id,
                    preserve_empty_name=preserve_empty_name,
                )
                if candidate is not None:
                    dogs.append(candidate)  # noqa: E111

        return dogs

    def _build_dog_candidate(  # noqa: E111
        self,
        raw: Any,
        *,
        fallback_id: str | None = None,
        preserve_empty_name: bool = False,
    ) -> DogConfigData | None:
        """Normalise ``raw`` dog payloads into ``DogConfigData`` mappings.

        Args:
            raw: Raw dog data
            fallback_id: Fallback ID if not in data
            preserve_empty_name: Whether to preserve empty names

        Returns:
            Dog config or None
        """
        if not isinstance(raw, Mapping):
            return None  # noqa: E111

        candidate: JSONMutableMapping = {
            str(key): value for key, value in raw.items() if isinstance(key, str)
        }

        dog_id = self._resolve_dog_identifier(candidate, fallback_id)
        if dog_id is None:
            return None  # noqa: E111
        candidate[DOG_ID_FIELD] = dog_id

        legacy_name = candidate.get("name")
        dog_name = candidate.get(DOG_NAME_FIELD)
        if preserve_empty_name and isinstance(dog_name, str) and not dog_name.strip():
            candidate[DOG_NAME_FIELD] = dog_name  # noqa: E111
        else:
            resolved_name: str | None = None  # noqa: E111
            for raw_name in (dog_name, legacy_name):  # noqa: E111
                try:
                    resolved_name = validate_flow_dog_name(raw_name, required=False)  # noqa: E111
                except ValidationError:
                    continue  # noqa: E111
                if resolved_name:
                    break  # noqa: E111
            candidate[DOG_NAME_FIELD] = resolved_name or dog_id  # noqa: E111

        modules = candidate.get(DOG_MODULES_FIELD)
        if isinstance(modules, Mapping):
            candidate[DOG_MODULES_FIELD] = dict(  # noqa: E111
                ensure_dog_modules_mapping(candidate),
            )
        elif isinstance(modules, Sequence) and not isinstance(
            modules,
            str | bytes | bytearray,
        ):
            toggles: DogModulesConfig = {}  # noqa: E111
            for module in modules:  # noqa: E111
                if isinstance(module, str):
                    key = module.strip()  # noqa: E111
                    if key in MODULE_TOGGLE_KEYS:  # noqa: E111
                        toggles[cast(ModuleToggleKey, key)] = True
                    continue  # noqa: E111

                if not isinstance(module, Mapping):
                    continue  # noqa: E111

                legacy_key = None
                for key_name in ("module", "key", "name"):
                    raw_key = module.get(key_name)  # noqa: E111
                    if isinstance(raw_key, str) and raw_key.strip():  # noqa: E111
                        legacy_key = raw_key.strip()
                        break

                if legacy_key is None or legacy_key not in MODULE_TOGGLE_KEYS:
                    continue  # noqa: E111

                enabled_value = module.get("enabled")
                if "value" in module:
                    enabled_value = module["value"]  # noqa: E111
                toggles[cast(ModuleToggleKey, legacy_key)] = self._coerce_legacy_toggle(
                    enabled_value,
                )

            if toggles:  # noqa: E111
                candidate[DOG_MODULES_FIELD] = cast(JSONValue, toggles)
            else:  # noqa: E111
                candidate.pop(DOG_MODULES_FIELD, None)
        elif modules is not None:
            candidate.pop(DOG_MODULES_FIELD, None)  # noqa: E111

        return cast(DogConfigData, candidate)

    @staticmethod  # noqa: E111
    def _resolve_dog_identifier(  # noqa: E111
        candidate: Mapping[str, object],
        fallback_id: str | None,
    ) -> str | None:
        """Return a trimmed dog identifier from legacy payloads when available.

        Args:
            candidate: Candidate dog data
            fallback_id: Fallback ID

        Returns:
            Dog ID or None
        """
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
            value = candidate.get(key)  # noqa: E111
            if isinstance(value, str):  # noqa: E111
                try:
                    normalized = normalize_dog_id(value)  # noqa: E111
                except InputCoercionError:
                    continue  # noqa: E111
                if normalized:
                    return normalized  # noqa: E111

        if isinstance(fallback_id, str) and fallback_id.strip():
            try:  # noqa: E111
                normalized_fallback = normalize_dog_id(fallback_id)
            except InputCoercionError:  # noqa: E111
                return fallback_id.strip()
            return normalized_fallback or fallback_id.strip()  # noqa: E111

        return None

    @staticmethod  # noqa: E111
    def _coerce_legacy_toggle(value: Any) -> bool:  # noqa: E111
        """Best-effort coercion for legacy module toggle payloads.

        Args:
            value: Value to coerce

        Returns:
            Boolean value
        """
        if value is None:
            return True  # noqa: E111
        if isinstance(value, bool):
            return value  # noqa: E111
        if isinstance(value, (int | float)):
            return value != 0  # noqa: E111
        if isinstance(value, str):
            text = value.strip().lower()  # noqa: E111
            if not text:  # noqa: E111
                return True
            if text in {"0", "false", "no", "n", "off", "disabled"}:  # noqa: E111
                return False
            return text in {"1", "true", "yes", "y", "on", "enabled"}  # noqa: E111
        return bool(value)

    def _normalise_dog_modules(self, dog: DogConfigData) -> DogModulesConfig:  # noqa: E111
        """Return a normalised modules mapping for a dog configuration.

        Args:
            dog: Dog configuration

        Returns:
            Normalized module config
        """
        modules_raw = dog.get(CONF_MODULES)
        if isinstance(modules_raw, Mapping):
            return ensure_dog_modules_config(cast(Mapping[str, object], modules_raw))  # noqa: E111
        return cast(DogModulesConfig, {})

    async def _estimate_entities_for_reconfigure(  # noqa: E111
        self,
        dogs: list[DogConfigData],
        profile: str,
    ) -> int:
        """Estimate entities for reconfiguration display.

        Args:
            dogs: Dogs list
            profile: Profile name

        Returns:
            Estimated entity count
        """
        try:
            total = 0  # noqa: E111
            for dog in dogs:  # noqa: E111
                if not self._is_dog_config_valid_for_flow(
                    cast(Mapping[str, object], dog),
                ):
                    continue  # noqa: E111
                total += await self._entity_factory.estimate_entity_count_async(
                    profile,
                    ensure_dog_modules_mapping(dog),
                )
            return total  # noqa: E111
        except Exception as err:  # pragma: no cover - defensive guard
            _LOGGER.debug("Entity estimation failed: %s", err)  # noqa: E111
            return 0  # noqa: E111

    def _check_profile_compatibility(  # noqa: E111
        self,
        profile: str,
        dogs: list[DogConfigData],
    ) -> ReconfigureCompatibilityResult:
        """Check profile compatibility with existing dogs.

        Args:
            profile: Profile name
            dogs: Dogs list

        Returns:
            Compatibility result
        """
        warnings: list[str] = []

        try:
            for dog in dogs:  # noqa: E111
                modules = self._normalise_dog_modules(dog)
                if modules and not self._entity_factory.validate_profile_for_modules(
                    profile,
                    modules,
                ):
                    dog_name_raw = dog.get(DOG_NAME_FIELD) or dog.get(
                        DOG_ID_FIELD, "unknown"
                    )  # noqa: E111
                    dog_name = (
                        str(dog_name_raw) if dog_name_raw is not None else "unknown"
                    )  # noqa: E111
                    warnings.append(  # noqa: E111
                        f"Profile '{profile}' may not be optimal for {dog_name}",
                    )
        except Exception as err:  # pragma: no cover - defensive guard
            warnings.append(f"Profile validation error: {err}")  # noqa: E111

        return {
            "compatible": not warnings,
            "warnings": self._normalise_string_list(warnings),
        }

    def _get_compatibility_info(  # noqa: E111
        self,
        current_profile: str,
        dogs: list[DogConfigData],
    ) -> str:
        """Get compatibility information for profile change.

        Args:
            current_profile: Current profile
            dogs: Dogs list

        Returns:
            Compatibility info text
        """
        dog_count = len(dogs)
        total_modules = sum(
            sum(1 for enabled in modules.values() if enabled)
            for modules in (self._normalise_dog_modules(dog) for dog in dogs)
        )

        if dog_count >= 5:
            return "High dog count - 'basic' profile recommended for performance"  # noqa: E111
        if total_modules >= 20:
            return "Many modules enabled - consider 'standard' or 'basic' profile"  # noqa: E111
        return "Current configuration supports all profiles"

    @staticmethod  # noqa: E111
    @callback  # type: ignore[untyped-decorator,misc]    # noqa: E111
    def async_get_options_flow(config_entry: ConfigEntry) -> PawControlOptionsFlow:  # noqa: E111
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
