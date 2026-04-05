"""Tests for the discovery helpers."""

from collections.abc import Iterable
from dataclasses import dataclass, field

from homeassistant.core import HomeAssistant
import pytest

from custom_components.pawcontrol import discovery as discovery_module
from custom_components.pawcontrol.const import DOMAIN
from custom_components.pawcontrol.discovery import (
    CATEGORY_CAPABILITIES,
    DiscoveredDevice,
    DiscoveredDeviceMetadata,
    DiscoveryCapabilityList,
    DiscoveryCategory,
    DiscoveryConnectionInfo,
    LegacyDiscoveryEntry,
    PawControlDiscovery,
    async_get_discovered_devices,
    async_get_discovery_manager,
    async_shutdown_discovery_manager,
)


@pytest.mark.asyncio
async def test_async_get_discovered_devices_exports_typed_payload(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ensure the legacy discovery wrapper emits typed payloads."""
    connection_info: DiscoveryConnectionInfo = {
        "address": "192.168.1.25",
        "mac": "AA:BB:CC:DD:EE:FF",
        "configuration_url": "https://pawcontrol.local/configure",
        "via_device_id": "parent-device",
    }
    metadata: DiscoveredDeviceMetadata = {
        "identifiers": ["pawcontrol:device-1"],
        "sw_version": "2025.1",
        "hw_version": "rev-b",
        "via_device_id": "parent-device",
    }
    capabilities: DiscoveryCapabilityList = ["gps", "geofence"]

    discovered_device = DiscoveredDevice(
        device_id="device-1",
        name="Tracker",
        category="gps_tracker",
        manufacturer="PawControl",
        model="Tracker 2",
        connection_type="network",
        connection_info=connection_info,
        capabilities=capabilities,
        discovered_at="2025-02-03T04:05:06+00:00",
        confidence=0.93,
        metadata=metadata,
    )

    call_order: list[str] = []

    async def _async_initialize(self: PawControlDiscovery) -> None:
        call_order.append("initialize")

    async def _async_discover_devices(
        self: PawControlDiscovery,
        categories: Iterable[DiscoveryCategory] | None = None,
        quick_scan: bool = False,
    ) -> list[DiscoveredDevice]:
        call_order.append("discover")
        assert quick_scan is True
        assert categories is None
        return [discovered_device]

    async def _async_shutdown(self: PawControlDiscovery) -> None:
        call_order.append("shutdown")

    monkeypatch.setattr(PawControlDiscovery, "async_initialize", _async_initialize)
    monkeypatch.setattr(
        PawControlDiscovery, "async_discover_devices", _async_discover_devices
    )
    monkeypatch.setattr(PawControlDiscovery, "async_shutdown", _async_shutdown)

    legacy_payload = await async_get_discovered_devices(hass)

    expected: list[LegacyDiscoveryEntry] = [
        {
            "source": "network",
            "data": {
                "device_id": "device-1",
                "name": "Tracker",
                "manufacturer": "PawControl",
                "category": "gps_tracker",
                "address": "192.168.1.25",
                "mac": "AA:BB:CC:DD:EE:FF",
                "configuration_url": "https://pawcontrol.local/configure",
                "via_device_id": "parent-device",
            },
        }
    ]

    assert legacy_payload == expected
    assert call_order == ["initialize", "discover", "shutdown"]
    assert hass.data[DOMAIN] == {}


@dataclass(slots=True)
class _StubDeviceEntry:
    """Lightweight device entry for classification tests."""

    id: str
    manufacturer: str | None = None
    model: str | None = None
    connections: set[tuple[str, str]] = field(default_factory=set)
    configuration_url: str | None = None
    via_device_id: str | None = None


@dataclass(slots=True)
class _StubEntityEntry:
    """Minimal entity registry entry for discovery classification."""

    entity_id: str
    domain: str
    device_id: str
    original_name: str | None = None
    platform: str | None = None


class _StubEntityRegistry:
    """Entity registry adapter exposing the mapping interface used by discovery."""

    def __init__(self, entries: Iterable[_StubEntityEntry]) -> None:
        self.entities = {entry.entity_id: entry for entry in entries}


@pytest.mark.parametrize(
    (
        "manufacturer",
        "model",
        "domains_with_names",
        "connections",
        "expected_category",
    ),
    [
        (
            "Halo",
            "Collar 3",
            [("sensor", "halo_activity", "Halo Collar Activity")],
            {("bluetooth", "AA:BB:CC:DD:EE:FF")},
            "smart_collar",
        ),
        (
            "Furbo",
            "Treat Cam",
            [
                ("camera", "furbo_cam", "Furbo Treat Camera"),
                ("button", "dispense", "Dispense Treat"),
            ],
            set(),
            "treat_dispenser",
        ),
        (
            "Petlibro",
            "Smart Fountain",
            [("switch", "water_fountain", "Petlibro Water Fountain")],
            set(),
            "water_fountain",
        ),
        (
            "PawCam",
            "Indoor Camera",
            [("camera", "pawcam", "PawCam Indoor Camera")],
            set(),
            "camera",
        ),
        (
            "PawControl",
            "Door Guard",
            [("binary_sensor", "front_door", "Front Door Sensor")],
            set(),
            "door_sensor",
        ),
    ],
)
def test_classify_device_covers_extended_categories(
    hass: HomeAssistant,
    manufacturer: str,
    model: str,
    domains_with_names: list[tuple[str, str, str]],
    connections: set[tuple[str, str]],
    expected_category: DiscoveryCategory,
) -> None:
    """Ensure the extended discovery categories are classified correctly."""
    device_entry = _StubDeviceEntry(
        id="device-1",
        manufacturer=manufacturer,
        model=model,
        connections=connections,
    )
    registry_entries = [
        _StubEntityEntry(
            entity_id=f"{domain}.{slug}",
            domain=domain,
            device_id="device-1",
            original_name=name,
            platform=domain,
        )
        for domain, slug, name in domains_with_names
    ]
    entity_registry = _StubEntityRegistry(registry_entries)

    discovery = PawControlDiscovery(hass)
    result = discovery._classify_device(device_entry, entity_registry)

    assert result is not None
    category, capabilities, confidence = result
    assert category == expected_category
    assert capabilities == CATEGORY_CAPABILITIES[expected_category]
    assert 0.5 <= confidence <= 0.95


def test_connection_details_collects_known_connection_metadata(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Connection detail extraction should include known IDs and metadata."""
    device_entry = _StubDeviceEntry(
        id="device-2",
        connections=[
            ("bluetooth", "AA:BB:CC:DD:EE:FF"),
            ("mac", "11:22:33:44:55:66"),
            ("usb", "usb-1"),
        ],
        configuration_url="https://pawcontrol.local/device-2",
        via_device_id="bridge-1",
    )
    discovery = PawControlDiscovery(hass)
    monkeypatch.setattr(
        discovery_module.dr,
        "CONNECTION_BLUETOOTH",
        "bluetooth",
        raising=False,
    )
    monkeypatch.setattr(
        discovery_module.dr,
        "CONNECTION_NETWORK_MAC",
        "mac",
        raising=False,
    )

    connection_type, connection_info = discovery._connection_details(device_entry)

    assert connection_type == "usb"
    assert connection_info["address"] == "AA:BB:CC:DD:EE:FF"
    assert connection_info["mac"] == "11:22:33:44:55:66"
    assert connection_info["usb"] == "usb-1"
    assert connection_info["configuration_url"] == "https://pawcontrol.local/device-2"
    assert connection_info["via_device_id"] == "bridge-1"


def test_deduplicate_and_getters_prefer_stronger_confidence(
    hass: HomeAssistant,
) -> None:
    """Deduplication should keep the highest-confidence device per id."""
    discovery = PawControlDiscovery(hass)
    low_confidence = DiscoveredDevice(
        device_id="dup-id",
        name="Tracker A",
        category="gps_tracker",
        manufacturer="PawControl",
        model="A",
        connection_type="network",
        connection_info={},
        capabilities=["gps"],
        discovered_at="2026-01-01T00:00:00+00:00",
        confidence=0.41,
        metadata={},
    )
    high_confidence = DiscoveredDevice(
        device_id="dup-id",
        name="Tracker A+",
        category="gps_tracker",
        manufacturer="PawControl",
        model="A+",
        connection_type="network",
        connection_info={},
        capabilities=["gps", "geofence"],
        discovered_at="2026-01-01T00:00:00+00:00",
        confidence=0.92,
        metadata={},
    )

    deduplicated = discovery._deduplicate_devices([low_confidence, high_confidence])

    assert len(deduplicated) == 1
    kept_device = deduplicated[0]
    assert kept_device.name == "Tracker A+"
    discovery._discovered_devices[kept_device.device_id] = kept_device
    assert discovery.get_device_by_id("dup-id") == kept_device
    assert discovery.get_discovered_devices(category="gps_tracker") == [kept_device]
    assert discovery.is_scanning() is False


@pytest.mark.asyncio
async def test_discovery_manager_singleton_lifecycle(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The global discovery manager should initialize once and reset on shutdown."""
    initialize_calls = 0

    async def _async_initialize(self: PawControlDiscovery) -> None:
        nonlocal initialize_calls
        initialize_calls += 1

    monkeypatch.setattr(PawControlDiscovery, "async_initialize", _async_initialize)

    manager_one = await async_get_discovery_manager(hass)
    manager_two = await async_get_discovery_manager(hass)

    assert manager_one is manager_two
    assert initialize_calls == 1

    await async_shutdown_discovery_manager()

    manager_three = await async_get_discovery_manager(hass)
    assert manager_three is not manager_one
    assert initialize_calls == 2

    await async_shutdown_discovery_manager()
