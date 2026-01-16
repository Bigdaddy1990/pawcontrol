"""Discovery helpers for PawControl hardware.

This module inspects Home Assistant registries and scheduled listeners to
surface smart collars, feeders, trackers, and other accessories that PawControl
manages. The implementation targets Home Assistant's Platinum quality scale,
keeps all runtime interactions asynchronous, and leans on typed payloads so the
strict mypy gate can reason about gathered devices.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Final, Literal, TypedDict, cast

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntry, DeviceRegistryEvent
from homeassistant.helpers.entity_registry import EntityRegistryEvent
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util.dt import utcnow

from . import compat
from .compat import bind_exception_alias, ensure_homeassistant_exception_symbols
from .const import DEVICE_CATEGORIES, DOMAIN
from .exceptions import PawControlError

_LOGGER = logging.getLogger(__name__)

# Discovery scan intervals
DISCOVERY_SCAN_INTERVAL: Final[timedelta] = timedelta(minutes=5)
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
    """Connection metadata extracted from the device registry."""

    address: str
    mac: str
    usb: str
    configuration_url: str
    via_device_id: str


class DiscoveredDeviceMetadata(TypedDict, total=False):
    """Extra metadata describing the registry device."""

    identifiers: list[str]
    via_device_id: str | None
    sw_version: str | None
    hw_version: str | None
    configuration_url: str
    area_id: str


class LegacyDiscoveryData(DiscoveryConnectionInfo):
    """Legacy payload exported for config flow consumers."""

    device_id: str
    name: str
    manufacturer: str
    category: DiscoveryCategory


class LegacyDiscoveryEntry(TypedDict):
    """Legacy compatibility wrapper used by config flows."""

    source: DiscoveryConnectionType
    data: LegacyDiscoveryData


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
    """Represents a discovered dog-related device."""

    device_id: str
    name: str
    category: DiscoveryCategory
    manufacturer: str
    model: str
    connection_type: DiscoveryConnectionType
    connection_info: DiscoveryConnectionInfo
    capabilities: DiscoveryCapabilityList
    discovered_at: str
    confidence: float  # 0.0 - 1.0, discovery confidence
    metadata: DiscoveredDeviceMetadata


class PawControlDiscovery:
    """Advanced discovery manager for dog-related hardware devices.

    Provides comprehensive device detection across multiple protocols with
    intelligent device classification, confidence scoring, and automatic
    device capability detection.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the discovery manager.

        Args:
            hass: Home Assistant instance
        """
        self.hass = hass
        self._discovered_devices: dict[str, DiscoveredDevice] = {}
        self._discovery_tasks: set[asyncio.Task[Any]] = set()
        self._scan_active = False
        self._listeners: list[CALLBACK_TYPE] = []
        self._device_registry: dr.DeviceRegistry | None = None
        self._entity_registry: er.EntityRegistry | None = None

    async def async_initialize(self) -> None:
        """Initialize discovery systems and start background scanning."""
        _LOGGER.debug("Initializing Paw Control device discovery")

        try:
            self._device_registry = dr.async_get(self.hass)
            self._entity_registry = er.async_get(self.hass)

            # Start background discovery scanning
            await self._start_background_scanning()

            # Register discovery listeners for real-time detection
            await self._register_discovery_listeners()

            _LOGGER.info("Paw Control discovery initialized successfully")

        except Exception as err:
            _LOGGER.error(
                "Failed to initialize discovery: %s",
                err,
                exc_info=True,
            )
            raise HomeAssistantError(
                f"Discovery initialization failed: {err}",
            ) from err

    async def async_discover_devices(
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
            _LOGGER.warning(
                "Discovery scan already active, waiting for completion",
            )
            await self._wait_for_scan_completion()

        categories_list: list[DiscoveryCategory]
        if categories is None:
            categories_list = [
                cast(DiscoveryCategory, category) for category in DEVICE_CATEGORIES
            ]
        else:
            categories_list = list(categories)
        scan_timeout = DISCOVERY_TIMEOUT if quick_scan else DISCOVERY_TIMEOUT * 3

        _LOGGER.info(
            "Starting %s device discovery for categories: %s",
            "quick" if quick_scan else "thorough",
            categories_list,
        )

        self._scan_active = True
        discovered_devices: list[DiscoveredDevice] = []

        try:
            # Use timeout to prevent hanging scans
            async with asyncio.timeout(scan_timeout):
                discovery_results = await asyncio.gather(
                    self._discover_registry_devices(categories_list),
                    return_exceptions=True,
                )

                for result in discovery_results:
                    if isinstance(result, BaseException):
                        _LOGGER.warning("Discovery method failed: %s", result)
                        continue

                    discovered_devices.extend(result)

            # Remove duplicates and update stored devices
            unique_devices = self._deduplicate_devices(discovered_devices)

            for device in unique_devices:
                self._discovered_devices[device.device_id] = device

            _LOGGER.info(
                "Discovery completed: %d devices found (%d unique)",
                len(discovered_devices),
                len(unique_devices),
            )

            return unique_devices

        except TimeoutError:
            _LOGGER.warning(
                "Device discovery timed out after %ds",
                scan_timeout,
            )
            return list(self._discovered_devices.values())
        except Exception as err:
            _LOGGER.error("Discovery failed: %s", err, exc_info=True)
            raise PawControlError(f"Device discovery failed: {err}") from err
        finally:
            self._scan_active = False

    async def _discover_usb_devices(
        self,
        categories: list[DiscoveryCategory],
    ) -> list[DiscoveredDevice]:
        """Discover USB-connected dog devices (placeholder)."""

        _LOGGER.debug("USB discovery currently relies on registry data only")
        return []

    async def _discover_registry_devices(
        self,
        categories: list[DiscoveryCategory],
    ) -> list[DiscoveredDevice]:
        """Discover devices by inspecting Home Assistant registries."""

        device_registry = self._device_registry or dr.async_get(self.hass)
        entity_registry = self._entity_registry or er.async_get(self.hass)

        discovered: list[DiscoveredDevice] = []
        now_iso = utcnow().isoformat()

        for device_entry in device_registry.devices.values():
            classification = self._classify_device(
                device_entry,
                entity_registry,
            )
            if not classification:
                continue

            category, capabilities, confidence = classification
            if category not in categories:
                continue

            connection_type, connection_info = self._connection_details(
                device_entry,
            )
            manufacturer = device_entry.manufacturer or "Unknown"
            model = device_entry.model or device_entry.hw_version or "Unknown"
            name = (
                device_entry.name_by_user
                or device_entry.name
                or f"{manufacturer} {model}".strip()
            )

            metadata: DiscoveredDeviceMetadata = {
                "identifiers": [
                    f"{domain}:{identifier}"
                    for domain, identifier in device_entry.identifiers
                ],
                "via_device_id": device_entry.via_device_id,
                "sw_version": device_entry.sw_version,
                "hw_version": device_entry.hw_version,
            }
            if device_entry.configuration_url:
                metadata["configuration_url"] = device_entry.configuration_url
            if device_entry.area_id:
                metadata["area_id"] = device_entry.area_id

            discovered.append(
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

    def _classify_device(
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
            nonlocal confidence
            if category in matched_categories:
                return
            matched_categories.add(category)
            confidence += boost

        for category, keywords in CATEGORY_KEYWORDS.items():
            if any(keyword in manufacturer or keyword in model for keyword in keywords):
                _register_category(category, 0.15)

        entry_names = [
            (getattr(entry, "original_name", None) or entry.entity_id).lower()
            for entry in related_entities
        ]

        if "device_tracker" in domains:
            _register_category("gps_tracker", 0.2)

        bluetooth_aliases = {
            getattr(dr, "CONNECTION_BLUETOOTH", "bluetooth"),
            "bluetooth",
        }
        if any(
            conn_type in bluetooth_aliases for conn_type, _ in device_entry.connections
        ):
            _register_category("smart_collar", 0.1)

        if {
            "switch",
            "select",
        } & domains and any(
            term in name
            for name in entry_names
            for term in ("feed", "feeder", "meal", "portion")
        ):
            _register_category("smart_feeder", 0.1)

        if {
            "switch",
            "sensor",
        } & domains and any(
            term in name
            for name in entry_names
            for term in ("fountain", "water", "hydration", "drink")
        ):
            _register_category("water_fountain", 0.1)

        if {
            "button",
            "switch",
        } & domains and any(
            term in name
            for name in entry_names
            for term in ("treat", "reward", "snack", "dispenser")
        ):
            _register_category("treat_dispenser", 0.1)

        if "camera" in domains:
            _register_category("camera", 0.1)

        if "sensor" in domains:
            for name in entry_names:
                if "activity" in name:
                    _register_category("activity_monitor", 0.1)
                if any(term in name for term in ("health", "weight", "vet")):
                    _register_category("health_device", 0.1)
                if "collar" in name:
                    _register_category("smart_collar", 0.1)

        if "binary_sensor" in domains and any(
            term in name for name in entry_names for term in ("door", "gate", "entry")
        ):
            _register_category("door_sensor", 0.1)

        if not matched_categories:
            return None

        for candidate in CATEGORY_PRIORITY:
            if candidate in matched_categories:
                category = candidate
                break
        else:
            category = next(iter(matched_categories))

        capabilities = CATEGORY_CAPABILITIES.get(category, [])
        confidence = min(confidence, 0.95)
        return category, capabilities, confidence

    def _connection_details(
        self,
        device_entry: DeviceEntry,
    ) -> tuple[DiscoveryConnectionType, DiscoveryConnectionInfo]:
        connection_info: DiscoveryConnectionInfo = {}
        connection_type: DiscoveryConnectionType = "unknown"

        for conn_type, conn_id in device_entry.connections:
            if conn_type in (dr.CONNECTION_BLUETOOTH, "bluetooth"):
                connection_type = "bluetooth"
                connection_info.setdefault("address", conn_id)
            elif conn_type in (dr.CONNECTION_NETWORK_MAC, "mac"):
                connection_type = "network"
                connection_info.setdefault("mac", conn_id)
            elif conn_type == "usb":
                connection_type = "usb"
                connection_info.setdefault("usb", conn_id)

        if (
            device_entry.configuration_url
            and "configuration_url" not in connection_info
        ):
            connection_info["configuration_url"] = device_entry.configuration_url
        if device_entry.via_device_id:
            connection_info["via_device_id"] = device_entry.via_device_id

        return connection_type, connection_info

    async def _start_background_scanning(self) -> None:
        """Start background device scanning."""

        @callback
        def _scheduled_scan(now: datetime) -> None:
            """Callback for scheduled device scanning."""

            if self._scan_active:
                return

            task = self.hass.async_create_task(
                self.async_discover_devices(quick_scan=True),
                name="paw_control_background_discovery",
            )
            self._discovery_tasks.add(task)
            task.add_done_callback(self._discovery_tasks.discard)

        # Schedule regular discovery scans
        self._listeners.append(
            async_track_time_interval(
                self.hass,
                _scheduled_scan,
                DISCOVERY_SCAN_INTERVAL,
            ),
        )

        _LOGGER.debug("Background discovery scanning started")

    async def _register_discovery_listeners(self) -> None:
        """Register real-time discovery listeners."""

        try:
            device_registry = self._device_registry or dr.async_get(self.hass)
            entity_registry = self._entity_registry or er.async_get(self.hass)

            @callback
            def _handle_device_event(event: DeviceRegistryEvent) -> None:
                _LOGGER.debug(
                    "Device registry event: action=%s device=%s",
                    event.action,
                    event.device_id,
                )
                if not self._scan_active:
                    self.hass.async_create_task(
                        self.async_discover_devices(quick_scan=True),
                    )

            @callback
            def _handle_entity_event(event: EntityRegistryEvent) -> None:
                _LOGGER.debug(
                    "Entity registry event: action=%s entity=%s",
                    event.action,
                    event.entity_id,
                )
                if not self._scan_active:
                    self.hass.async_create_task(
                        self.async_discover_devices(quick_scan=True),
                    )

            self._listeners.append(
                device_registry.async_listen(_handle_device_event),
            )
            self._listeners.append(
                entity_registry.async_listen(_handle_entity_event),
            )

            _LOGGER.debug("Discovery listeners registered")

        except Exception as err:  # pragma: no cover - listener errors are rare
            _LOGGER.warning(
                "Failed to register some discovery listeners: %s",
                err,
            )

    async def _wait_for_scan_completion(self) -> None:
        """Wait for active discovery scan to complete."""

        max_wait = 30  # Maximum wait time in seconds
        waited = 0.0

        while self._scan_active and waited < max_wait:
            await asyncio.sleep(0.5)
            waited += 0.5

        if self._scan_active:
            _LOGGER.warning(
                "Discovery scan did not complete within %ds",
                max_wait,
            )

    async def async_shutdown(self) -> None:
        """Shutdown discovery and cleanup resources."""

        _LOGGER.debug("Shutting down Paw Control discovery")

        # Cancel background tasks
        for task in set(self._discovery_tasks):
            if task.done():
                continue
            task.cancel()

        if self._discovery_tasks:
            await asyncio.gather(*self._discovery_tasks, return_exceptions=True)
        self._discovery_tasks.clear()

        # Remove listeners
        for listener in self._listeners:
            listener()
        self._listeners.clear()

        # Clear discovered devices
        self._discovered_devices.clear()

        _LOGGER.info("Paw Control discovery shutdown complete")

    def _deduplicate_devices(
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
            existing = deduplicated.get(device.device_id)
            if existing is None or existing.confidence < device.confidence:
                deduplicated[device.device_id] = device

        return list(deduplicated.values())

    @callback
    def get_discovered_devices(
        self,
        category: str | None = None,
    ) -> list[DiscoveredDevice]:
        """Get all discovered devices, optionally filtered by category."""

        if category:
            return [
                device
                for device in self._discovered_devices.values()
                if device.category == category
            ]
        return list(self._discovered_devices.values())

    @callback
    def get_device_by_id(self, device_id: str) -> DiscoveredDevice | None:
        """Get a specific device by ID."""

        return self._discovered_devices.get(device_id)

    @callback
    def is_scanning(self) -> bool:
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
    """
    discovery = PawControlDiscovery(hass)
    hass.data.setdefault(DOMAIN, {})["legacy_discovery"] = discovery

    try:
        await discovery.async_initialize()
        devices = await discovery.async_discover_devices(quick_scan=True)

        # Convert to legacy format
        legacy_devices: list[LegacyDiscoveryEntry] = []
        for device in devices:
            data: LegacyDiscoveryData = {
                "device_id": device.device_id,
                "name": device.name,
                "manufacturer": device.manufacturer,
                "category": device.category,
            }
            if address := device.connection_info.get("address"):
                data["address"] = address
            if mac := device.connection_info.get("mac"):
                data["mac"] = mac
            if usb := device.connection_info.get("usb"):
                data["usb"] = usb
            if configuration_url := device.connection_info.get("configuration_url"):
                data["configuration_url"] = configuration_url
            if via_device_id := device.connection_info.get("via_device_id"):
                data["via_device_id"] = via_device_id

            legacy_devices.append(
                {
                    "source": device.connection_type,
                    "data": data,
                },
            )

        return legacy_devices

    except Exception as err:
        _LOGGER.error("Legacy discovery failed: %s", err)
        return []
    finally:
        await discovery.async_shutdown()
        hass.data[DOMAIN].pop("legacy_discovery", None)


async def async_start_discovery() -> bool:
    """Legacy compatibility function that always returns True.

    Returns:
        True to maintain backward compatibility
    """
    return True


# Device discovery manager instance (singleton pattern)
_discovery_manager: PawControlDiscovery | None = None


async def async_get_discovery_manager(hass: HomeAssistant) -> PawControlDiscovery:
    """Get or create the global discovery manager instance.

    Args:
        hass: Home Assistant instance

    Returns:
        Discovery manager instance
    """
    global _discovery_manager

    if _discovery_manager is None:
        _discovery_manager = PawControlDiscovery(hass)
        await _discovery_manager.async_initialize()

    return _discovery_manager


async def async_shutdown_discovery_manager() -> None:
    """Shutdown the global discovery manager."""
    global _discovery_manager

    if _discovery_manager:
        await _discovery_manager.async_shutdown()
        _discovery_manager = None


ensure_homeassistant_exception_symbols()
HomeAssistantError: type[Exception] = cast(
    type[Exception],
    compat.HomeAssistantError,
)
bind_exception_alias("HomeAssistantError", combine_with_current=True)
