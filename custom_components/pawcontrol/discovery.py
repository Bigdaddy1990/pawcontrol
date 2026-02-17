"""Discovery helpers for PawControl hardware.

This module inspects Home Assistant registries and scheduled listeners to
surface smart collars, feeders, trackers, and other accessories that PawControl
manages. The implementation targets Home Assistant's Platinum quality scale,
keeps all runtime interactions asynchronous, and leans on typed payloads so the
strict mypy gate can reason about gathered devices.
"""

import asyncio
from collections.abc import Iterable
from dataclasses import dataclass
import logging
from typing import Final, Literal, TypedDict, cast

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntry, DeviceRegistryEvent
from homeassistant.helpers.entity_registry import EntityRegistryEvent
from homeassistant.util.dt import utcnow

from .const import DEVICE_CATEGORIES, DOMAIN
from .exceptions import PawControlError

_LOGGER = logging.getLogger(__name__)

DISCOVERY_TIMEOUT: Final[float] = 10.0

type DiscoveryCategory = Literal[
    "gps_tracker",
    "smart_feeder",
    "activity_monitor",
    "health_device",
    "smart_collar",
    "treat_dispenser",
    "water_fountain",
    "camera",
    "door_sensor",
]

type DiscoveryConnectionType = Literal[
    "bluetooth",
    "network",
    "usb",
    "unknown",
]

type DiscoveryCapabilityList = list[str]


class DiscoveryConnectionInfo(TypedDict, total=False):
    """Connection metadata extracted from the device registry."""  # noqa: E111

    address: str  # noqa: E111
    mac: str  # noqa: E111
    usb: str  # noqa: E111
    configuration_url: str  # noqa: E111
    via_device_id: str  # noqa: E111


class DiscoveredDeviceMetadata(TypedDict, total=False):
    """Extra metadata describing the registry device."""  # noqa: E111

    identifiers: list[str]  # noqa: E111
    via_device_id: str | None  # noqa: E111
    sw_version: str | None  # noqa: E111
    hw_version: str | None  # noqa: E111
    configuration_url: str  # noqa: E111
    area_id: str  # noqa: E111


class LegacyDiscoveryData(DiscoveryConnectionInfo):
    """Legacy payload exported for config flow consumers."""  # noqa: E111

    device_id: str  # noqa: E111
    name: str  # noqa: E111
    manufacturer: str  # noqa: E111
    category: DiscoveryCategory  # noqa: E111


class LegacyDiscoveryEntry(TypedDict):
    """Legacy compatibility wrapper used by config flows."""  # noqa: E111

    source: DiscoveryConnectionType  # noqa: E111
    data: LegacyDiscoveryData  # noqa: E111


CATEGORY_KEYWORDS: Final[dict[DiscoveryCategory, tuple[str, ...]]] = {
    "gps_tracker": ("tractive", "whistle", "fi", "link", "pawtrack"),
    "smart_feeder": ("petnet", "sureflap", "pawcontrol feeder", "smartfeeder"),
    "activity_monitor": ("fitbark", "whistle", "fi", "activity"),
    "health_device": ("whistle", "fitbark", "petpuls", "vital"),
    "smart_collar": ("collar", "halo", "wagz", "pawcontrol collar"),
    "treat_dispenser": ("furbo", "petcube", "treat", "petzi"),
    "water_fountain": ("fountain", "petlibro", "drinkwell", "hydration"),
    "camera": ("camera", "pawcam", "pawcontrol cam", "petcam"),
    "door_sensor": ("door", "gate", "entry", "petdoor"),
}

CATEGORY_CAPABILITIES: Final[dict[DiscoveryCategory, DiscoveryCapabilityList]] = {
    "gps_tracker": ["gps", "activity_tracking", "geofence"],
    "smart_feeder": ["portion_control", "scheduling", "monitoring"],
    "activity_monitor": ["activity_tracking", "sleep_tracking"],
    "health_device": ["health_monitoring", "weight_tracking"],
    "smart_collar": ["gps", "activity_tracking", "health_monitoring"],
    "treat_dispenser": ["remote_treats", "camera_stream", "two_way_audio"],
    "water_fountain": ["water_monitoring", "filter_tracking", "flow_control"],
    "camera": ["camera_stream", "two_way_audio"],
    "door_sensor": ["door_state", "entry_logging"],
}

CATEGORY_PRIORITY: Final[tuple[DiscoveryCategory, ...]] = (
    "gps_tracker",
    "smart_feeder",
    "smart_collar",
    "activity_monitor",
    "health_device",
    "treat_dispenser",
    "water_fountain",
    "camera",
    "door_sensor",
)


@dataclass(frozen=True)
class DiscoveredDevice:
    """Represents a discovered dog-related device."""  # noqa: E111

    device_id: str  # noqa: E111
    name: str  # noqa: E111
    category: DiscoveryCategory  # noqa: E111
    manufacturer: str  # noqa: E111
    model: str  # noqa: E111
    connection_type: DiscoveryConnectionType  # noqa: E111
    connection_info: DiscoveryConnectionInfo  # noqa: E111
    capabilities: DiscoveryCapabilityList  # noqa: E111
    discovered_at: str  # noqa: E111
    confidence: float  # 0.0 - 1.0, discovery confidence  # noqa: E111
    metadata: DiscoveredDeviceMetadata  # noqa: E111


class PawControlDiscovery:
    """Advanced discovery manager for dog-related hardware devices.

    Provides comprehensive device detection across multiple protocols with
    intelligent device classification, confidence scoring, and automatic
    device capability detection.
    """  # noqa: E111

    def __init__(self, hass: HomeAssistant) -> None:  # noqa: E111
        """Initialize the discovery manager.

        Args:
            hass: Home Assistant instance
        """
        self.hass = hass
        self._discovered_devices: dict[str, DiscoveredDevice] = {}
        self._scan_active = False
        self._listeners: list[CALLBACK_TYPE] = []
        self._device_registry: dr.DeviceRegistry | None = None
        self._entity_registry: er.EntityRegistry | None = None

    async def async_initialize(self) -> None:  # noqa: E111
        """Initialize discovery systems and start background scanning."""
        _LOGGER.debug("Initializing Paw Control device discovery")

        try:
            self._device_registry = dr.async_get(self.hass)  # noqa: E111
            self._entity_registry = er.async_get(self.hass)  # noqa: E111

            # Perform an initial scan so consumers have current state  # noqa: E114
            await self.async_discover_devices(quick_scan=True)  # noqa: E111

            # Register discovery listeners for real-time detection  # noqa: E114
            await self._register_discovery_listeners()  # noqa: E111

            _LOGGER.info("Paw Control discovery initialized successfully")  # noqa: E111

        except Exception as err:
            _LOGGER.error(  # noqa: E111
                "Failed to initialize discovery: %s",
                err,
                exc_info=True,
            )
            raise HomeAssistantError(  # noqa: E111
                f"Discovery initialization failed: {err}",
            ) from err

    async def async_discover_devices(  # noqa: E111
        self,
        categories: list[DiscoveryCategory] | None = None,
        quick_scan: bool = False,
    ) -> list[DiscoveredDevice]:
        """Perform comprehensive device discovery.

        Args:
            categories: Device categories to search for, or None for all
            quick_scan: Whether to perform a quick scan vs thorough scan

        Returns:
            List of discovered devices

        Raises:
            PawControlError: If discovery fails
        """
        if self._scan_active:
            _LOGGER.warning(  # noqa: E111
                "Discovery scan already active, waiting for completion",
            )
            await self._wait_for_scan_completion()  # noqa: E111

        categories_list: list[DiscoveryCategory]
        if categories is None:
            categories_list = [  # noqa: E111
                cast(DiscoveryCategory, category) for category in DEVICE_CATEGORIES
            ]
        else:
            categories_list = list(categories)  # noqa: E111
        scan_timeout = DISCOVERY_TIMEOUT if quick_scan else DISCOVERY_TIMEOUT * 3

        _LOGGER.info(
            "Starting %s device discovery for categories: %s",
            "quick" if quick_scan else "thorough",
            categories_list,
        )

        self._scan_active = True
        discovered_devices: list[DiscoveredDevice] = []

        try:
            # Use timeout to prevent hanging scans  # noqa: E114
            async with asyncio.timeout(scan_timeout):  # noqa: E111
                discovery_results = await asyncio.gather(
                    self._discover_registry_devices(categories_list),
                    return_exceptions=True,
                )

                for result in discovery_results:
                    if isinstance(result, BaseException):  # noqa: E111
                        _LOGGER.warning("Discovery method failed: %s", result)
                        continue

                    discovered_devices.extend(result)  # noqa: E111

            # Remove duplicates and update stored devices  # noqa: E114
            unique_devices = self._deduplicate_devices(discovered_devices)  # noqa: E111

            for device in unique_devices:  # noqa: E111
                self._discovered_devices[device.device_id] = device

            _LOGGER.info(  # noqa: E111
                "Discovery completed: %d devices found (%d unique)",
                len(discovered_devices),
                len(unique_devices),
            )

            return unique_devices  # noqa: E111

        except TimeoutError:
            _LOGGER.warning(  # noqa: E111
                "Device discovery timed out after %ds",
                scan_timeout,
            )
            return list(self._discovered_devices.values())  # noqa: E111
        except Exception as err:
            _LOGGER.error("Discovery failed: %s", err, exc_info=True)  # noqa: E111
            raise PawControlError(f"Device discovery failed: {err}") from err  # noqa: E111
        finally:
            self._scan_active = False  # noqa: E111

    async def _discover_usb_devices(  # noqa: E111
        self,
        categories: list[DiscoveryCategory],
    ) -> list[DiscoveredDevice]:
        """Discover USB-connected dog devices (placeholder)."""

        _LOGGER.debug("USB discovery currently relies on registry data only")
        return []

    async def _discover_registry_devices(  # noqa: E111
        self,
        categories: list[DiscoveryCategory],
    ) -> list[DiscoveredDevice]:
        """Discover devices by inspecting Home Assistant registries."""

        device_registry = self._device_registry or dr.async_get(self.hass)
        entity_registry = self._entity_registry or er.async_get(self.hass)

        discovered: list[DiscoveredDevice] = []
        now_iso = utcnow().isoformat()

        for device_entry in device_registry.devices.values():
            classification = self._classify_device(  # noqa: E111
                device_entry,
                entity_registry,
            )
            if not classification:  # noqa: E111
                continue

            category, capabilities, confidence = classification  # noqa: E111
            if category not in categories:  # noqa: E111
                continue

            connection_type, connection_info = self._connection_details(  # noqa: E111
                device_entry,
            )
            manufacturer = device_entry.manufacturer or "Unknown"  # noqa: E111
            model = device_entry.model or device_entry.hw_version or "Unknown"  # noqa: E111
            name = (  # noqa: E111
                device_entry.name_by_user
                or device_entry.name
                or f"{manufacturer} {model}".strip()
            )

            metadata: DiscoveredDeviceMetadata = {  # noqa: E111
                "identifiers": [
                    f"{domain}:{identifier}"
                    for domain, identifier in device_entry.identifiers
                ],
                "via_device_id": device_entry.via_device_id,
                "sw_version": device_entry.sw_version,
                "hw_version": device_entry.hw_version,
            }
            if device_entry.configuration_url:  # noqa: E111
                metadata["configuration_url"] = device_entry.configuration_url
            if device_entry.area_id:  # noqa: E111
                metadata["area_id"] = device_entry.area_id

            discovered.append(  # noqa: E111
                DiscoveredDevice(
                    device_id=device_entry.id,
                    name=name,
                    category=category,
                    manufacturer=manufacturer,
                    model=model,
                    connection_type=connection_type,
                    connection_info=connection_info,
                    capabilities=capabilities,
                    discovered_at=now_iso,
                    confidence=confidence,
                    metadata=metadata,
                ),
            )

        _LOGGER.debug("Registry discovery found %d devices", len(discovered))
        return discovered

    def _classify_device(  # noqa: E111
        self,
        device_entry: DeviceEntry,
        entity_registry: er.EntityRegistry,
    ) -> tuple[DiscoveryCategory, DiscoveryCapabilityList, float] | None:
        manufacturer = (device_entry.manufacturer or "").lower()
        model = (device_entry.model or "").lower()
        related_entities = [
            entry
            for entry in entity_registry.entities.values()
            if entry.device_id == device_entry.id
        ]
        domains = {entry.domain for entry in related_entities}

        matched_categories: set[DiscoveryCategory] = set()
        confidence = 0.4

        def _register_category(category: DiscoveryCategory, boost: float) -> None:
            nonlocal confidence  # noqa: E111
            if category in matched_categories:  # noqa: E111
                return
            matched_categories.add(category)  # noqa: E111
            confidence += boost  # noqa: E111

        for category, keywords in CATEGORY_KEYWORDS.items():
            if any(keyword in manufacturer or keyword in model for keyword in keywords):  # noqa: E111
                _register_category(category, 0.15)

        entry_names = [
            (getattr(entry, "original_name", None) or entry.entity_id).lower()
            for entry in related_entities
        ]

        if "device_tracker" in domains:
            _register_category("gps_tracker", 0.2)  # noqa: E111

        bluetooth_aliases = {
            getattr(dr, "CONNECTION_BLUETOOTH", "bluetooth"),
            "bluetooth",
        }
        if any(
            conn_type in bluetooth_aliases for conn_type, _ in device_entry.connections
        ):
            _register_category("smart_collar", 0.1)  # noqa: E111

        if {
            "switch",
            "select",
        } & domains and any(
            term in name
            for name in entry_names
            for term in ("feed", "feeder", "meal", "portion")
        ):
            _register_category("smart_feeder", 0.1)  # noqa: E111

        if {
            "switch",
            "sensor",
        } & domains and any(
            term in name
            for name in entry_names
            for term in ("fountain", "water", "hydration", "drink")
        ):
            _register_category("water_fountain", 0.1)  # noqa: E111

        if {
            "button",
            "switch",
        } & domains and any(
            term in name
            for name in entry_names
            for term in ("treat", "reward", "snack", "dispenser")
        ):
            _register_category("treat_dispenser", 0.1)  # noqa: E111

        if "camera" in domains:
            _register_category("camera", 0.1)  # noqa: E111

        if "sensor" in domains:
            for name in entry_names:  # noqa: E111
                if "activity" in name:
                    _register_category("activity_monitor", 0.1)  # noqa: E111
                if any(term in name for term in ("health", "weight", "vet")):
                    _register_category("health_device", 0.1)  # noqa: E111
                if "collar" in name:
                    _register_category("smart_collar", 0.1)  # noqa: E111

        if "binary_sensor" in domains and any(
            term in name for name in entry_names for term in ("door", "gate", "entry")
        ):
            _register_category("door_sensor", 0.1)  # noqa: E111

        if not matched_categories:
            return None  # noqa: E111

        for candidate in CATEGORY_PRIORITY:
            if candidate in matched_categories:  # noqa: E111
                category = candidate
                break
        else:
            category = next(iter(matched_categories))  # noqa: E111

        capabilities = CATEGORY_CAPABILITIES.get(category, [])
        confidence = min(confidence, 0.95)
        return category, capabilities, confidence

    def _connection_details(  # noqa: E111
        self,
        device_entry: DeviceEntry,
    ) -> tuple[DiscoveryConnectionType, DiscoveryConnectionInfo]:
        connection_info: DiscoveryConnectionInfo = {}
        connection_type: DiscoveryConnectionType = "unknown"

        for conn_type, conn_id in device_entry.connections:
            if conn_type in (dr.CONNECTION_BLUETOOTH, "bluetooth"):  # noqa: E111
                connection_type = "bluetooth"
                connection_info.setdefault("address", conn_id)
            elif conn_type in (dr.CONNECTION_NETWORK_MAC, "mac"):  # noqa: E111
                connection_type = "network"
                connection_info.setdefault("mac", conn_id)
            elif conn_type == "usb":  # noqa: E111
                connection_type = "usb"
                connection_info.setdefault("usb", conn_id)

        if (
            device_entry.configuration_url
            and "configuration_url" not in connection_info
        ):
            connection_info["configuration_url"] = device_entry.configuration_url  # noqa: E111
        if device_entry.via_device_id:
            connection_info["via_device_id"] = device_entry.via_device_id  # noqa: E111

        return connection_type, connection_info

    async def _register_discovery_listeners(self) -> None:  # noqa: E111
        """Register real-time discovery listeners."""

        try:
            device_registry = self._device_registry or dr.async_get(self.hass)  # noqa: E111
            entity_registry = self._entity_registry or er.async_get(self.hass)  # noqa: E111

            @callback  # noqa: E111
            def _handle_device_event(event: DeviceRegistryEvent) -> None:  # noqa: E111
                _LOGGER.debug(
                    "Device registry event: action=%s device=%s",
                    event.action,
                    event.device_id,
                )
                if not self._scan_active:
                    self.hass.async_create_task(  # noqa: E111
                        self.async_discover_devices(quick_scan=True),
                    )

            @callback  # noqa: E111
            def _handle_entity_event(event: EntityRegistryEvent) -> None:  # noqa: E111
                _LOGGER.debug(
                    "Entity registry event: action=%s entity=%s",
                    event.action,
                    event.entity_id,
                )
                if not self._scan_active:
                    self.hass.async_create_task(  # noqa: E111
                        self.async_discover_devices(quick_scan=True),
                    )

            self._listeners.append(  # noqa: E111
                device_registry.async_listen(_handle_device_event),
            )
            self._listeners.append(  # noqa: E111
                entity_registry.async_listen(_handle_entity_event),
            )

            _LOGGER.debug("Discovery listeners registered")  # noqa: E111

        except Exception as err:  # pragma: no cover - listener errors are rare
            _LOGGER.warning(  # noqa: E111
                "Failed to register some discovery listeners: %s",
                err,
            )

    async def _wait_for_scan_completion(self) -> None:  # noqa: E111
        """Wait for active discovery scan to complete."""

        max_wait = 30  # Maximum wait time in seconds
        waited = 0.0

        while self._scan_active and waited < max_wait:
            await asyncio.sleep(0.5)  # noqa: E111
            waited += 0.5  # noqa: E111

        if self._scan_active:
            _LOGGER.warning(  # noqa: E111
                "Discovery scan did not complete within %ds",
                max_wait,
            )

    async def async_shutdown(self) -> None:  # noqa: E111
        """Shutdown discovery and cleanup resources."""

        _LOGGER.debug("Shutting down Paw Control discovery")

        # Remove listeners
        for listener in self._listeners:
            listener()  # noqa: E111
        self._listeners.clear()

        # Clear discovered devices
        self._discovered_devices.clear()

        _LOGGER.info("Paw Control discovery shutdown complete")

    def _deduplicate_devices(  # noqa: E111
        self,
        devices: Iterable[DiscoveredDevice],
    ) -> list[DiscoveredDevice]:
        """Return a list of devices keyed by the strongest confidence value.

        Multiple discovery strategies may surface the same Home Assistant device
        identifier. When that happens we keep the entry that recorded the highest
        confidence score so diagnostics and UI copy reflect the best evidence we
        have without leaking duplicates.
        """

        deduplicated: dict[str, DiscoveredDevice] = {}
        for device in devices:
            existing = deduplicated.get(device.device_id)  # noqa: E111
            if existing is None or existing.confidence < device.confidence:  # noqa: E111
                deduplicated[device.device_id] = device

        return list(deduplicated.values())

    @callback  # noqa: E111
    def get_discovered_devices(  # noqa: E111
        self,
        category: str | None = None,
    ) -> list[DiscoveredDevice]:
        """Get all discovered devices, optionally filtered by category."""

        if category:
            return [  # noqa: E111
                device
                for device in self._discovered_devices.values()
                if device.category == category
            ]
        return list(self._discovered_devices.values())

    @callback  # noqa: E111
    def get_device_by_id(self, device_id: str) -> DiscoveredDevice | None:  # noqa: E111
        """Get a specific device by ID."""

        return self._discovered_devices.get(device_id)

    @callback  # noqa: E111
    def is_scanning(self) -> bool:  # noqa: E111
        """Check if a discovery scan is currently active."""

        return self._scan_active


# Legacy compatibility functions for existing code
async def async_get_discovered_devices(
    hass: HomeAssistant,
) -> list[LegacyDiscoveryEntry]:
    """Legacy compatibility function for basic device discovery.

    Args:
        hass: Home Assistant instance

    Returns:
        List of discovered devices in legacy format
    """  # noqa: E111
    discovery = PawControlDiscovery(hass)  # noqa: E111
    hass.data.setdefault(DOMAIN, {})["legacy_discovery"] = discovery  # noqa: E111

    try:  # noqa: E111
        await discovery.async_initialize()
        devices = await discovery.async_discover_devices(quick_scan=True)

        # Convert to legacy format
        legacy_devices: list[LegacyDiscoveryEntry] = []
        for device in devices:
            data: LegacyDiscoveryData = {  # noqa: E111
                "device_id": device.device_id,
                "name": device.name,
                "manufacturer": device.manufacturer,
                "category": device.category,
            }
            if address := device.connection_info.get("address"):  # noqa: E111
                data["address"] = address
            if mac := device.connection_info.get("mac"):  # noqa: E111
                data["mac"] = mac
            if usb := device.connection_info.get("usb"):  # noqa: E111
                data["usb"] = usb
            if configuration_url := device.connection_info.get("configuration_url"):  # noqa: E111
                data["configuration_url"] = configuration_url
            if via_device_id := device.connection_info.get("via_device_id"):  # noqa: E111
                data["via_device_id"] = via_device_id

            legacy_devices.append(  # noqa: E111
                {
                    "source": device.connection_type,
                    "data": data,
                },
            )

        return legacy_devices

    except Exception as err:  # noqa: E111
        _LOGGER.error("Legacy discovery failed: %s", err)
        return []
    finally:  # noqa: E111
        await discovery.async_shutdown()
        hass.data[DOMAIN].pop("legacy_discovery", None)


async def async_start_discovery() -> bool:
    """Legacy compatibility function that always returns True.

    Returns:
        True to maintain backward compatibility
    """  # noqa: E111
    return True  # noqa: E111


# Device discovery manager instance (singleton pattern)
_discovery_manager: PawControlDiscovery | None = None


async def async_get_discovery_manager(hass: HomeAssistant) -> PawControlDiscovery:
    """Get or create the global discovery manager instance.

    Args:
        hass: Home Assistant instance

    Returns:
        Discovery manager instance
    """  # noqa: E111
    global _discovery_manager  # noqa: E111

    if _discovery_manager is None:  # noqa: E111
        _discovery_manager = PawControlDiscovery(hass)
        await _discovery_manager.async_initialize()

    return _discovery_manager  # noqa: E111


async def async_shutdown_discovery_manager() -> None:
    """Shutdown the global discovery manager."""  # noqa: E111
    global _discovery_manager  # noqa: E111

    if _discovery_manager:  # noqa: E111
        await _discovery_manager.async_shutdown()
        _discovery_manager = None
