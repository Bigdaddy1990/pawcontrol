"""Tests for the discovery helpers."""

from __future__ import annotations

from collections.abc import Iterable

import pytest
from custom_components.pawcontrol.const import DOMAIN
from custom_components.pawcontrol.discovery import (
    DiscoveredDevice,
    DiscoveredDeviceMetadata,
    DiscoveryCapabilityList,
    DiscoveryCategory,
    DiscoveryConnectionInfo,
    LegacyDiscoveryEntry,
    PawControlDiscovery,
    async_get_discovered_devices,
)
from homeassistant.core import HomeAssistant


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
