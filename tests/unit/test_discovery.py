"""Tests for the discovery helpers."""

import asyncio
from collections.abc import Iterable
from dataclasses import dataclass, field
from types import SimpleNamespace

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
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
from custom_components.pawcontrol.exceptions import PawControlError


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


@pytest.mark.asyncio
async def test_async_discover_devices_returns_cached_devices_after_timeout(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Timeouts should gracefully fall back to the cache."""
    discovery = PawControlDiscovery(hass)
    cached_device = DiscoveredDevice(
        device_id="cached",
        name="Cached Tracker",
        category="gps_tracker",
        manufacturer="PawControl",
        model="C-1",
        connection_type="network",
        connection_info={},
        capabilities=["gps"],
        discovered_at="2026-01-01T00:00:00+00:00",
        confidence=0.8,
        metadata={},
    )
    discovery._discovered_devices[cached_device.device_id] = cached_device

    async def _slow_discovery(_: list[DiscoveryCategory]) -> list[DiscoveredDevice]:
        await asyncio.sleep(0.02)
        return []

    monkeypatch.setattr(discovery_module, "DISCOVERY_TIMEOUT", 0.001)
    monkeypatch.setattr(discovery, "_discover_registry_devices", _slow_discovery)

    devices = await discovery.async_discover_devices(quick_scan=True)

    assert devices == [cached_device]
    assert discovery.is_scanning() is False


@pytest.mark.asyncio
async def test_async_discover_devices_handles_method_errors(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Per-method failures should be tolerated and return no new devices."""
    discovery = PawControlDiscovery(hass)

    async def _failing_discovery(_: list[DiscoveryCategory]) -> list[DiscoveredDevice]:
        raise RuntimeError("boom")

    monkeypatch.setattr(discovery, "_discover_registry_devices", _failing_discovery)

    devices = await discovery.async_discover_devices()

    assert devices == []
    assert discovery.is_scanning() is False


@pytest.mark.asyncio
async def test_discover_registry_devices_builds_expected_metadata(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Registry discovery should map core device fields into metadata payloads."""
    discovery = PawControlDiscovery(hass)

    device_entry = SimpleNamespace(
        id="device-123",
        name_by_user="Backyard Tracker",
        name=None,
        manufacturer="PawControl",
        model="Tracker Pro",
        hw_version="rev-2",
        sw_version="2026.4",
        connections={("bluetooth", "AA:BB:CC")},
        identifiers={("pawcontrol", "device-123")},
        via_device_id="bridge-7",
        configuration_url="https://pawcontrol.local/device-123",
        area_id="garden",
    )
    discovery._device_registry = SimpleNamespace(
        devices={device_entry.id: device_entry}
    )
    discovery._entity_registry = SimpleNamespace(entities={})

    monkeypatch.setattr(
        discovery,
        "_classify_device",
        lambda _device, _registry: ("gps_tracker", ["gps"], 0.9),
    )
    monkeypatch.setattr(
        discovery,
        "_connection_details",
        lambda _device: ("bluetooth", {"address": "AA:BB:CC"}),
    )

    devices = await discovery._discover_registry_devices(["gps_tracker"])

    assert len(devices) == 1
    found = devices[0]
    assert found.device_id == "device-123"
    assert found.name == "Backyard Tracker"
    assert found.connection_info == {"address": "AA:BB:CC"}
    assert found.metadata == {
        "identifiers": ["pawcontrol:device-123"],
        "via_device_id": "bridge-7",
        "sw_version": "2026.4",
        "hw_version": "rev-2",
        "configuration_url": "https://pawcontrol.local/device-123",
        "area_id": "garden",
    }


def _build_discovered_device(
    *,
    device_id: str,
    category: DiscoveryCategory = "gps_tracker",
    connection_info: DiscoveryConnectionInfo | None = None,
    confidence: float = 0.8,
) -> DiscoveredDevice:
    return DiscoveredDevice(
        device_id=device_id,
        name=f"Device {device_id}",
        category=category,
        manufacturer="PawControl",
        model="Model",
        connection_type="network",
        connection_info=connection_info or {},
        capabilities=["gps"],
        discovered_at="2026-01-01T00:00:00+00:00",
        confidence=confidence,
        metadata={},
    )


@pytest.mark.asyncio
async def test_async_initialize_success_path_sets_registries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Initialization should set registries, scan once, and register listeners."""
    hass = SimpleNamespace(data={})
    discovery = PawControlDiscovery(hass)

    fake_device_registry = SimpleNamespace(devices={})
    fake_entity_registry = SimpleNamespace(entities={})

    monkeypatch.setattr(
        discovery_module.dr,
        "async_get",
        lambda _hass: fake_device_registry,
    )
    monkeypatch.setattr(
        discovery_module.er,
        "async_get",
        lambda _hass: fake_entity_registry,
    )

    discover_calls: list[bool] = []
    register_calls = 0

    async def _discover_devices(
        categories: Iterable[DiscoveryCategory] | None = None,
        quick_scan: bool = False,
    ) -> list[DiscoveredDevice]:
        del categories
        discover_calls.append(quick_scan)
        return []

    async def _register_listeners() -> None:
        nonlocal register_calls
        register_calls += 1

    monkeypatch.setattr(discovery, "async_discover_devices", _discover_devices)
    monkeypatch.setattr(
        discovery,
        "_register_discovery_listeners",
        _register_listeners,
    )

    await discovery.async_initialize()

    assert discovery._device_registry is fake_device_registry
    assert discovery._entity_registry is fake_entity_registry
    assert discover_calls == [True]
    assert register_calls == 1


@pytest.mark.asyncio
async def test_async_initialize_raises_home_assistant_error_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Initialization errors should be wrapped in HomeAssistantError."""
    discovery = PawControlDiscovery(SimpleNamespace(data={}))

    def _raise_registry_error(_hass: object) -> object:
        raise RuntimeError("registry unavailable")

    monkeypatch.setattr(discovery_module.dr, "async_get", _raise_registry_error)

    with pytest.raises(HomeAssistantError, match="Discovery initialization failed"):
        await discovery.async_initialize()


@pytest.mark.asyncio
async def test_async_discover_devices_waits_when_scan_already_active(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Active scans should wait first, then merge and store unique devices."""
    discovery = PawControlDiscovery(SimpleNamespace(data={}))
    discovery._scan_active = True
    wait_calls = 0

    async def _wait() -> None:
        nonlocal wait_calls
        wait_calls += 1
        discovery._scan_active = False

    expected = _build_discovered_device(device_id="discovered-1")

    async def _discover_registry(
        categories: list[DiscoveryCategory],
    ) -> list[DiscoveredDevice]:
        assert categories == ["gps_tracker"]
        return [expected]

    monkeypatch.setattr(discovery, "_wait_for_scan_completion", _wait)
    monkeypatch.setattr(discovery, "_discover_registry_devices", _discover_registry)

    devices = await discovery.async_discover_devices(categories=("gps_tracker",))

    assert wait_calls == 1
    assert devices == [expected]
    assert discovery._discovered_devices == {expected.device_id: expected}


@pytest.mark.asyncio
async def test_async_discover_devices_wraps_unexpected_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unexpected failures should be raised as PawControlError."""
    discovery = PawControlDiscovery(SimpleNamespace(data={}))

    async def _discover_registry(
        _categories: list[DiscoveryCategory],
    ) -> list[DiscoveredDevice]:
        return [_build_discovered_device(device_id="result")]

    def _raise_deduplicate(
        _devices: Iterable[DiscoveredDevice],
    ) -> list[DiscoveredDevice]:
        raise RuntimeError("deduplicate failed")

    monkeypatch.setattr(discovery, "_discover_registry_devices", _discover_registry)
    monkeypatch.setattr(discovery, "_deduplicate_devices", _raise_deduplicate)

    with pytest.raises(PawControlError, match="Device discovery failed"):
        await discovery.async_discover_devices()


@pytest.mark.asyncio
async def test_discover_usb_devices_returns_empty_list(
    hass: HomeAssistant,
) -> None:
    """USB discovery helper currently returns an empty placeholder payload."""
    discovery = PawControlDiscovery(hass)
    assert await discovery._discover_usb_devices(["gps_tracker"]) == []


@pytest.mark.asyncio
async def test_discover_registry_devices_filters_unclassified_and_unrequested(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Registry discovery should skip unknown and out-of-scope categories."""
    discovery = PawControlDiscovery(hass)

    device_skip_none = SimpleNamespace(
        id="skip-none",
        name_by_user=None,
        name="Skip None",
        manufacturer="PawControl",
        model="Tracker",
        hw_version=None,
        sw_version=None,
        connections=set(),
        identifiers={("pawcontrol", "skip-none")},
        via_device_id=None,
        configuration_url=None,
        area_id=None,
    )
    device_skip_category = SimpleNamespace(
        id="skip-category",
        name_by_user=None,
        name="Skip Category",
        manufacturer="PawControl",
        model="Tracker",
        hw_version=None,
        sw_version=None,
        connections=set(),
        identifiers={("pawcontrol", "skip-category")},
        via_device_id=None,
        configuration_url=None,
        area_id=None,
    )
    device_match = SimpleNamespace(
        id="match",
        name_by_user=None,
        name="Matched",
        manufacturer="PawControl",
        model="Tracker",
        hw_version=None,
        sw_version="1.0",
        connections=set(),
        identifiers={("pawcontrol", "match")},
        via_device_id=None,
        configuration_url=None,
        area_id=None,
    )

    discovery._device_registry = SimpleNamespace(
        devices={
            device_skip_none.id: device_skip_none,
            device_skip_category.id: device_skip_category,
            device_match.id: device_match,
        }
    )
    discovery._entity_registry = SimpleNamespace(entities={})

    def _classify(
        device_entry: object,
        _entity_registry: object,
    ) -> tuple[DiscoveryCategory, DiscoveryCapabilityList, float] | None:
        device_id = str(getattr(device_entry, "id", ""))
        if device_id == "skip-none":
            return None
        if device_id == "skip-category":
            return ("camera", ["camera_stream"], 0.6)
        return ("gps_tracker", ["gps"], 0.9)

    monkeypatch.setattr(discovery, "_classify_device", _classify)
    monkeypatch.setattr(
        discovery,
        "_connection_details",
        lambda _device: ("unknown", {}),
    )

    devices = await discovery._discover_registry_devices(["gps_tracker"])

    assert [device.device_id for device in devices] == ["match"]
    assert "configuration_url" not in devices[0].metadata
    assert "area_id" not in devices[0].metadata


def test_classify_device_covers_feeder_and_health_branches(
    hass: HomeAssistant,
) -> None:
    """Classifier should evaluate feeder and health keyword branches."""
    discovery = PawControlDiscovery(hass)
    device_entry = SimpleNamespace(
        id="device-branch",
        manufacturer="Unknown",
        model="Unknown",
        connections=[],
    )
    entity_registry = SimpleNamespace(
        entities={
            "switch.feeder": SimpleNamespace(
                device_id="device-branch",
                domain="switch",
                entity_id="switch.feeder",
                original_name="Smart feeder portion",
            ),
            "sensor.health": SimpleNamespace(
                device_id="device-branch",
                domain="sensor",
                entity_id="sensor.health",
                original_name="Health weight",
            ),
        }
    )

    result = discovery._classify_device(device_entry, entity_registry)

    assert result is not None
    category, capabilities, _confidence = result
    assert category == "smart_feeder"
    assert capabilities == CATEGORY_CAPABILITIES["smart_feeder"]


def test_classify_device_falls_back_when_priority_order_empty(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Classifier fallback should use an arbitrary matched category if needed."""
    discovery = PawControlDiscovery(hass)
    device_entry = SimpleNamespace(
        id="device-fallback",
        manufacturer="Tractive",
        model="Tracker",
        connections=[],
    )
    entity_registry = SimpleNamespace(entities={})

    monkeypatch.setattr(discovery_module, "CATEGORY_PRIORITY", ())

    result = discovery._classify_device(device_entry, entity_registry)

    assert result is not None
    category, _capabilities, _confidence = result
    assert category == "gps_tracker"


def test_connection_details_ignores_unknown_connection_types(
    hass: HomeAssistant,
) -> None:
    """Unknown connection tuples should not modify the discovery payload."""
    discovery = PawControlDiscovery(hass)
    device_entry = SimpleNamespace(
        connections=[("zigbee", "abcd")],
        configuration_url=None,
        via_device_id=None,
    )

    connection_type, connection_info = discovery._connection_details(device_entry)

    assert connection_type == "unknown"
    assert connection_info == {}


class _ListenerRegistry:
    """Minimal registry listener harness for discovery callback tests."""

    def __init__(self) -> None:
        self.callbacks: list[object] = []

    def async_listen(self, callback_obj):
        self.callbacks.append(callback_obj)

        def _unsubscribe() -> None:
            if callback_obj in self.callbacks:
                self.callbacks.remove(callback_obj)

        return _unsubscribe


@pytest.mark.asyncio
async def test_register_discovery_listeners_registers_and_triggers_callbacks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Listener registration should attach callbacks and trigger quick scans."""
    created_tasks: list[asyncio.Task[object]] = []

    class _TaskHass:
        data: dict[str, object] = {}

        def async_create_task(self, coro):
            task = asyncio.create_task(coro)
            created_tasks.append(task)
            return task

    hass = _TaskHass()
    discovery = PawControlDiscovery(hass)
    device_registry = _ListenerRegistry()
    entity_registry = _ListenerRegistry()

    monkeypatch.setattr(discovery_module.dr, "async_get", lambda _hass: device_registry)
    monkeypatch.setattr(discovery_module.er, "async_get", lambda _hass: entity_registry)

    scan_calls: list[bool] = []

    async def _discover_devices(
        categories: Iterable[DiscoveryCategory] | None = None,
        quick_scan: bool = False,
    ) -> list[DiscoveredDevice]:
        del categories
        scan_calls.append(quick_scan)
        return []

    monkeypatch.setattr(discovery, "async_discover_devices", _discover_devices)

    await discovery._register_discovery_listeners()

    assert len(discovery._listeners) == 2
    assert len(device_registry.callbacks) == 1
    assert len(entity_registry.callbacks) == 1

    device_callback = device_registry.callbacks[0]
    entity_callback = entity_registry.callbacks[0]
    device_callback(SimpleNamespace(action="create", device_id="dev-1"))
    entity_callback(SimpleNamespace(action="create", entity_id="sensor.dev_1"))

    if created_tasks:
        await asyncio.gather(*created_tasks)
    assert scan_calls == [True, True]

    # Active scans should skip scheduling follow-up discovery tasks.
    discovery._scan_active = True
    device_callback(SimpleNamespace(action="update", device_id="dev-1"))
    entity_callback(SimpleNamespace(action="update", entity_id="sensor.dev_1"))
    assert scan_calls == [True, True]
    assert len(created_tasks) == 2


@pytest.mark.asyncio
async def test_wait_for_scan_completion_warns_when_still_active(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Wait helper should eventually give up when scans never complete."""
    discovery = PawControlDiscovery(SimpleNamespace(data={}))
    discovery._scan_active = True

    async def _fast_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(discovery_module.asyncio, "sleep", _fast_sleep)

    await discovery._wait_for_scan_completion()

    assert discovery._scan_active is True


@pytest.mark.asyncio
async def test_wait_for_scan_completion_returns_when_scan_finishes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Wait helper should stop polling once scan state flips to inactive."""
    discovery = PawControlDiscovery(SimpleNamespace(data={}))
    discovery._scan_active = True

    async def _finish_scan(_seconds: float) -> None:
        discovery._scan_active = False

    monkeypatch.setattr(discovery_module.asyncio, "sleep", _finish_scan)

    await discovery._wait_for_scan_completion()

    assert discovery._scan_active is False


@pytest.mark.asyncio
async def test_async_shutdown_invokes_listener_callbacks(
    hass: HomeAssistant,
) -> None:
    """Shutdown should call all listener unsubscribers and clear runtime state."""
    discovery = PawControlDiscovery(hass)
    calls: list[str] = []

    def _listener() -> None:
        calls.append("unsubscribed")

    discovery._listeners = [_listener]
    discovery._discovered_devices = {
        "device": _build_discovered_device(device_id="device")
    }

    await discovery.async_shutdown()

    assert calls == ["unsubscribed"]
    assert discovery._listeners == []
    assert discovery._discovered_devices == {}


def test_deduplicate_devices_keeps_existing_when_new_confidence_is_lower(
    hass: HomeAssistant,
) -> None:
    """Deduplication should keep the first entry when the replacement is weaker."""
    discovery = PawControlDiscovery(hass)
    high = _build_discovered_device(device_id="dup", confidence=0.9)
    low = _build_discovered_device(device_id="dup", confidence=0.5)

    deduplicated = discovery._deduplicate_devices([high, low])

    assert deduplicated == [high]


@pytest.mark.asyncio
async def test_async_get_discovered_devices_maps_usb_without_optional_keys(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Legacy conversion should include USB while skipping absent optional fields."""

    async def _initialize(self: PawControlDiscovery) -> None:
        return None

    async def _discover(
        self: PawControlDiscovery,
        categories: Iterable[DiscoveryCategory] | None = None,
        quick_scan: bool = False,
    ) -> list[DiscoveredDevice]:
        del categories, quick_scan
        return [
            _build_discovered_device(
                device_id="usb-device",
                category="smart_feeder",
                connection_info={"usb": "usb-2"},
            )
        ]

    async def _shutdown(self: PawControlDiscovery) -> None:
        return None

    monkeypatch.setattr(PawControlDiscovery, "async_initialize", _initialize)
    monkeypatch.setattr(PawControlDiscovery, "async_discover_devices", _discover)
    monkeypatch.setattr(PawControlDiscovery, "async_shutdown", _shutdown)

    devices = await async_get_discovered_devices(hass)

    assert devices == [
        {
            "source": "network",
            "data": {
                "device_id": "usb-device",
                "name": "Device usb-device",
                "manufacturer": "PawControl",
                "category": "smart_feeder",
                "usb": "usb-2",
            },
        }
    ]


@pytest.mark.asyncio
async def test_async_start_discovery_returns_true() -> None:
    """Legacy start helper should remain a constant True response."""
    assert await discovery_module.async_start_discovery() is True


@pytest.mark.asyncio
async def test_async_shutdown_discovery_manager_noops_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Shutdown helper should no-op when no singleton manager exists."""
    monkeypatch.setattr(discovery_module, "_discovery_manager", None)

    await async_shutdown_discovery_manager()
