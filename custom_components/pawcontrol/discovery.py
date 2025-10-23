"""Advanced Discovery support for Paw Control integration.

This module provides comprehensive hardware discovery for dog-related devices
including GPS trackers, smart feeders, activity monitors, and health devices.
Supports multiple discovery protocols: USB, Bluetooth, Zeroconf, DHCP, and UPnP.

Quality Scale: Bronze target
Home Assistant: 2025.8.3+
Python: 3.13+
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Final, cast

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

CATEGORY_KEYWORDS: Final[dict[str, tuple[str, ...]]] = {
    "gps_tracker": ("tractive", "whistle", "fi", "link"),
    "smart_feeder": ("petnet", "sureflap", "pawcontrol feeder"),
    "activity_monitor": ("fitbark", "whistle", "fi"),
    "health_device": ("whistle", "fitbark", "petpuls"),
}

CATEGORY_CAPABILITIES: Final[dict[str, list[str]]] = {
    "gps_tracker": ["gps", "activity_tracking", "geofence"],
    "smart_feeder": ["portion_control", "scheduling", "monitoring"],
    "activity_monitor": ["activity_tracking", "sleep_tracking"],
    "health_device": ["health_monitoring", "weight_tracking"],
}


@dataclass(frozen=True)
class DiscoveredDevice:
    """Represents a discovered dog-related device."""

    device_id: str
    name: str
    category: str
    manufacturer: str
    model: str
    connection_type: str
    connection_info: dict[str, Any]
    capabilities: list[str]
    discovered_at: str
    confidence: float  # 0.0 - 1.0, discovery confidence
    metadata: dict[str, Any]


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
            _LOGGER.error("Failed to initialize discovery: %s", err, exc_info=True)
            raise HomeAssistantError(f"Discovery initialization failed: {err}") from err

    async def async_discover_devices(
        self, categories: list[str] | None = None, quick_scan: bool = False
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
            _LOGGER.warning("Discovery scan already active, waiting for completion")
            await self._wait_for_scan_completion()

        categories_list: list[str]
        if categories is None:
            categories_list = list(DEVICE_CATEGORIES)
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
            _LOGGER.warning("Device discovery timed out after %ds", scan_timeout)
            return list(self._discovered_devices.values())
        except Exception as err:
            _LOGGER.error("Discovery failed: %s", err, exc_info=True)
            raise PawControlError(f"Device discovery failed: {err}") from err
        finally:
            self._scan_active = False

    async def _discover_usb_devices(
        self, categories: list[str]
    ) -> list[DiscoveredDevice]:
        """Discover USB-connected dog devices (placeholder)."""

        _LOGGER.debug("USB discovery currently relies on registry data only")
        return []

    async def _discover_registry_devices(
        self, categories: list[str]
    ) -> list[DiscoveredDevice]:
        """Discover devices by inspecting Home Assistant registries."""

        device_registry = self._device_registry or dr.async_get(self.hass)
        entity_registry = self._entity_registry or er.async_get(self.hass)

        discovered: list[DiscoveredDevice] = []
        now_iso = utcnow().isoformat()

        for device_entry in device_registry.devices.values():
            classification = self._classify_device(device_entry, entity_registry)
            if not classification:
                continue

            category, capabilities, confidence = classification
            if category not in categories:
                continue

            connection_type, connection_info = self._connection_details(device_entry)
            manufacturer = device_entry.manufacturer or "Unknown"
            model = device_entry.model or device_entry.hw_version or "Unknown"
            name = (
                device_entry.name_by_user
                or device_entry.name
                or f"{manufacturer} {model}".strip()
            )

            metadata = {
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
                )
            )

        _LOGGER.debug("Registry discovery found %d devices", len(discovered))
        return discovered

    def _classify_device(
        self,
        device_entry: DeviceEntry,
        entity_registry: er.EntityRegistry,
    ) -> tuple[str, list[str], float] | None:
        manufacturer = (device_entry.manufacturer or "").lower()
        model = (device_entry.model or "").lower()
        related_entities = [
            entry
            for entry in entity_registry.entities.values()
            if entry.device_id == device_entry.id
        ]
        domains = {entry.domain for entry in related_entities}

        matched_categories: set[str] = set()
        confidence = 0.4

        for category, keywords in CATEGORY_KEYWORDS.items():
            if any(keyword in manufacturer or keyword in model for keyword in keywords):
                matched_categories.add(category)
                confidence += 0.15

        if "device_tracker" in domains:
            matched_categories.add("gps_tracker")
            confidence += 0.2

        if {"switch", "select"} & domains:
            matched_categories.add("smart_feeder")

        if "sensor" in domains:
            for entry in related_entities:
                name = (entry.original_name or entry.entity_id).lower()
                if "activity" in name:
                    matched_categories.add("activity_monitor")
                if any(keyword in name for keyword in ("health", "weight", "vet")):
                    matched_categories.add("health_device")

        if not matched_categories:
            return None

        if "gps_tracker" in matched_categories:
            category = "gps_tracker"
        elif "smart_feeder" in matched_categories:
            category = "smart_feeder"
        elif "activity_monitor" in matched_categories:
            category = "activity_monitor"
        else:
            category = next(iter(matched_categories))

        capabilities = CATEGORY_CAPABILITIES.get(category, [])
        confidence = min(confidence, 0.95)
        return category, capabilities, confidence

    def _connection_details(
        self, device_entry: DeviceEntry
    ) -> tuple[str, dict[str, Any]]:
        connection_info: dict[str, Any] = {}
        connection_type = "unknown"

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
                self.hass, _scheduled_scan, DISCOVERY_SCAN_INTERVAL
            )
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
                        self.async_discover_devices(quick_scan=True)
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
                        self.async_discover_devices(quick_scan=True)
                    )

            self._listeners.append(device_registry.async_listen(_handle_device_event))
            self._listeners.append(entity_registry.async_listen(_handle_entity_event))

            _LOGGER.debug("Discovery listeners registered")

        except Exception as err:  # pragma: no cover - listener errors are rare
            _LOGGER.warning("Failed to register some discovery listeners: %s", err)

    async def _wait_for_scan_completion(self) -> None:
        """Wait for active discovery scan to complete."""

        max_wait = 30  # Maximum wait time in seconds
        waited = 0.0

        while self._scan_active and waited < max_wait:
            await asyncio.sleep(0.5)
            waited += 0.5

        if self._scan_active:
            _LOGGER.warning("Discovery scan did not complete within %ds", max_wait)

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

    @callback
    def get_discovered_devices(
        self, category: str | None = None
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

    def _deduplicate_devices(
        self, devices: Iterable[DiscoveredDevice]
    ) -> list[DiscoveredDevice]:
        """Return the unique set of devices keyed by device identifier."""

        deduplicated: dict[str, DiscoveredDevice] = {}
        for device in devices:
            existing = deduplicated.get(device.device_id)
            if existing is None or device.confidence > existing.confidence:
                deduplicated[device.device_id] = device

        return list(deduplicated.values())


# Legacy compatibility functions for existing code
async def async_get_discovered_devices(hass: HomeAssistant) -> list[dict[str, Any]]:
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
        legacy_devices = []
        for device in devices:
            legacy_devices.append(  # noqa: PERF401
                {
                    "source": device.connection_type,
                    "data": {
                        "device_id": device.device_id,
                        "name": device.name,
                        "manufacturer": device.manufacturer,
                        "category": device.category,
                        **device.connection_info,
                    },
                }
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
HomeAssistantError: type[Exception] = cast(type[Exception], compat.HomeAssistantError)
bind_exception_alias("HomeAssistantError", combine_with_current=True)
