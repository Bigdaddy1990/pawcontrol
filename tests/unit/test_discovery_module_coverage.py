"""Coverage-focused tests for discovery helpers."""

from types import SimpleNamespace

import pytest

from custom_components.pawcontrol import discovery


@pytest.fixture
def discovery_manager() -> discovery.PawControlDiscovery:
    """Create a discovery manager with a lightweight Home Assistant stub."""
    return discovery.PawControlDiscovery(SimpleNamespace(data={}))


def test_deduplicate_devices_prefers_highest_confidence(
    discovery_manager: discovery.PawControlDiscovery,
) -> None:
    """Duplicate IDs should keep the highest-confidence device payload."""
    low = discovery.DiscoveredDevice(
        device_id="dog-1",
        name="Collar low",
        category="smart_collar",
        manufacturer="Vendor",
        model="Model",
        connection_type="bluetooth",
        connection_info={"address": "AA:BB"},
        capabilities=["gps"],
        discovered_at="2026-01-01T00:00:00+00:00",
        confidence=0.5,
        metadata={},
    )
    high = discovery.DiscoveredDevice(
        device_id="dog-1",
        name="Collar high",
        category="smart_collar",
        manufacturer="Vendor",
        model="Model",
        connection_type="bluetooth",
        connection_info={"address": "AA:BB"},
        capabilities=["gps"],
        discovered_at="2026-01-01T00:00:00+00:00",
        confidence=0.9,
        metadata={},
    )

    deduplicated = discovery_manager._deduplicate_devices([low, high])

    assert len(deduplicated) == 1
    assert deduplicated[0].name == "Collar high"
    assert deduplicated[0].confidence == pytest.approx(0.9)


def test_connection_details_includes_metadata(
    discovery_manager: discovery.PawControlDiscovery,
) -> None:
    """Connection helper should expose URL and via-device metadata."""
    entry = SimpleNamespace(
        connections=[
            ("bluetooth", "AA:BB:CC"),
        ],
        configuration_url="https://device.local",
        via_device_id="hub-1",
    )

    connection_type, details = discovery_manager._connection_details(entry)

    assert connection_type == "bluetooth"
    assert details == {
        "address": "AA:BB:CC",
        "configuration_url": "https://device.local",
        "via_device_id": "hub-1",
    }


def test_connection_details_prefers_last_detected_transport(
    discovery_manager: discovery.PawControlDiscovery,
) -> None:
    """Connection helper should include all identifiers and track final type."""
    entry = SimpleNamespace(
        connections=[
            ("mac", "11:22:33:44:55:66"),
            ("usb", "usb-1"),
        ],
        configuration_url=None,
        via_device_id=None,
    )

    connection_type, details = discovery_manager._connection_details(entry)

    assert connection_type == "usb"
    assert details == {
        "mac": "11:22:33:44:55:66",
        "usb": "usb-1",
    }


def test_classify_device_prefers_priority_category(
    discovery_manager: discovery.PawControlDiscovery,
) -> None:
    """Classification should honor priority ordering and confidence limits."""
    device_entry = SimpleNamespace(
        id="dev-1",
        manufacturer="Whistle",
        model="Go Explore",
        connections=[("bluetooth", "AA:BB")],
    )
    entity_registry = SimpleNamespace(
        entities={
            "a": SimpleNamespace(
                device_id="dev-1",
                domain="device_tracker",
                entity_id="device_tracker.dog",
                original_name="Dog tracker",
            ),
            "b": SimpleNamespace(
                device_id="dev-1",
                domain="sensor",
                entity_id="sensor.activity",
                original_name="Activity",
            ),
        },
    )

    classified = discovery_manager._classify_device(device_entry, entity_registry)

    assert classified is not None
    category, capabilities, confidence = classified
    assert category == "gps_tracker"
    assert capabilities == discovery.CATEGORY_CAPABILITIES["gps_tracker"]
    assert 0.4 < confidence <= 0.95


def test_classify_device_returns_none_without_match(
    discovery_manager: discovery.PawControlDiscovery,
) -> None:
    """Classification should return None when no rules match the device."""
    device_entry = SimpleNamespace(
        id="dev-none",
        manufacturer="Unknown",
        model="Generic",
        connections=[],
    )
    entity_registry = SimpleNamespace(
        entities={
            "x": SimpleNamespace(
                device_id="other-device",
                domain="sensor",
                entity_id="sensor.unrelated",
                original_name="Unrelated",
            ),
        },
    )

    assert discovery_manager._classify_device(device_entry, entity_registry) is None


def test_discovery_manager_accessors_and_filters() -> None:
    """Accessor callbacks should reflect internal discovery state."""
    manager = discovery.PawControlDiscovery(SimpleNamespace(data={}))
    manager._scan_active = True
    dog_tracker = discovery.DiscoveredDevice(
        device_id="dog-1",
        name="Tracker",
        category="gps_tracker",
        manufacturer="Whistle",
        model="Go",
        connection_type="bluetooth",
        connection_info={"address": "AA"},
        capabilities=["gps"],
        discovered_at="2026-01-01T00:00:00+00:00",
        confidence=0.8,
        metadata={},
    )
    feeder = discovery.DiscoveredDevice(
        device_id="dog-2",
        name="Feeder",
        category="smart_feeder",
        manufacturer="PetNet",
        model="V2",
        connection_type="network",
        connection_info={"mac": "BB"},
        capabilities=["portion_control"],
        discovered_at="2026-01-01T00:00:00+00:00",
        confidence=0.7,
        metadata={},
    )
    manager._discovered_devices = {"dog-1": dog_tracker, "dog-2": feeder}

    assert manager.is_scanning() is True
    assert manager.get_device_by_id("dog-1") is dog_tracker
    assert manager.get_device_by_id("missing") is None
    assert manager.get_discovered_devices("gps_tracker") == [dog_tracker]
    assert manager.get_discovered_devices() == [dog_tracker, feeder]


@pytest.mark.asyncio
async def test_async_get_discovered_devices_cleans_legacy_handle() -> None:
    """Legacy wrapper should convert discovered devices and cleanup state."""
    fake_hass = SimpleNamespace(data={})

    async def _fake_initialize(self: discovery.PawControlDiscovery) -> None:
        return None

    async def _fake_discover(
        self: discovery.PawControlDiscovery,
        categories: list[discovery.DiscoveryCategory] | None = None,
        quick_scan: bool = False,
    ) -> list[discovery.DiscoveredDevice]:
        return [
            discovery.DiscoveredDevice(
                device_id="dev-2",
                name="Smart feeder",
                category="smart_feeder",
                manufacturer="PetNet",
                model="V2",
                connection_type="network",
                connection_info={
                    "mac": "11:22:33:44:55:66",
                    "configuration_url": "https://feeder.local",
                },
                capabilities=["portion_control"],
                discovered_at="2026-01-01T00:00:00+00:00",
                confidence=0.8,
                metadata={},
            ),
        ]

    async def _fake_shutdown(self: discovery.PawControlDiscovery) -> None:
        return None

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        discovery.PawControlDiscovery, "async_initialize", _fake_initialize
    )
    monkeypatch.setattr(
        discovery.PawControlDiscovery,
        "async_discover_devices",
        _fake_discover,
    )
    monkeypatch.setattr(discovery.PawControlDiscovery, "async_shutdown", _fake_shutdown)

    try:
        devices = await discovery.async_get_discovered_devices(fake_hass)
    finally:
        monkeypatch.undo()

    assert devices == [
        {
            "source": "network",
            "data": {
                "device_id": "dev-2",
                "name": "Smart feeder",
                "manufacturer": "PetNet",
                "category": "smart_feeder",
                "mac": "11:22:33:44:55:66",
                "configuration_url": "https://feeder.local",
            },
        },
    ]
    assert fake_hass.data[discovery.DOMAIN] == {}


@pytest.mark.asyncio
async def test_async_get_discovered_devices_handles_failures() -> None:
    """Legacy wrapper should return empty payloads when discovery fails."""
    fake_hass = SimpleNamespace(data={})

    async def _failing_initialize(self: discovery.PawControlDiscovery) -> None:
        raise RuntimeError("boom")

    async def _fake_shutdown(self: discovery.PawControlDiscovery) -> None:
        return None

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        discovery.PawControlDiscovery, "async_initialize", _failing_initialize
    )
    monkeypatch.setattr(
        discovery.PawControlDiscovery,
        "async_shutdown",
        _fake_shutdown,
    )

    try:
        devices = await discovery.async_get_discovered_devices(fake_hass)
    finally:
        monkeypatch.undo()

    assert devices == []
    assert fake_hass.data[discovery.DOMAIN] == {}


@pytest.mark.asyncio
async def test_discovery_manager_singleton_lifecycle() -> None:
    """Singleton manager helper should initialize once and reset on shutdown."""
    fake_hass = SimpleNamespace(data={})
    monkeypatch = pytest.MonkeyPatch()

    async def _fake_initialize(self: discovery.PawControlDiscovery) -> None:
        return None

    async def _fake_shutdown(self: discovery.PawControlDiscovery) -> None:
        return None

    monkeypatch.setattr(
        discovery.PawControlDiscovery, "async_initialize", _fake_initialize
    )
    monkeypatch.setattr(discovery.PawControlDiscovery, "async_shutdown", _fake_shutdown)
    monkeypatch.setattr(discovery, "_discovery_manager", None)

    try:
        first = await discovery.async_get_discovery_manager(fake_hass)
        second = await discovery.async_get_discovery_manager(fake_hass)
        assert first is second
        await discovery.async_shutdown_discovery_manager()
        assert discovery._discovery_manager is None
    finally:
        monkeypatch.undo()
