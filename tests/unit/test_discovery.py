"""Tests for the discovery helpers."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from homeassistant.core import HomeAssistant
import pytest

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
)


@pytest.mark.asyncio
async def test_async_get_discovered_devices_exports_typed_payload(
  hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
  """Ensure the legacy discovery wrapper emits typed payloads."""  # noqa: E111

  connection_info: DiscoveryConnectionInfo = {  # noqa: E111
    "address": "192.168.1.25",
    "mac": "AA:BB:CC:DD:EE:FF",
    "configuration_url": "https://pawcontrol.local/configure",
    "via_device_id": "parent-device",
  }
  metadata: DiscoveredDeviceMetadata = {  # noqa: E111
    "identifiers": ["pawcontrol:device-1"],
    "sw_version": "2025.1",
    "hw_version": "rev-b",
    "via_device_id": "parent-device",
  }
  capabilities: DiscoveryCapabilityList = ["gps", "geofence"]  # noqa: E111

  discovered_device = DiscoveredDevice(  # noqa: E111
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

  call_order: list[str] = []  # noqa: E111

  async def _async_initialize(self: PawControlDiscovery) -> None:  # noqa: E111
    call_order.append("initialize")

  async def _async_discover_devices(  # noqa: E111
    self: PawControlDiscovery,
    categories: Iterable[DiscoveryCategory] | None = None,
    quick_scan: bool = False,
  ) -> list[DiscoveredDevice]:
    call_order.append("discover")
    assert quick_scan is True
    assert categories is None
    return [discovered_device]

  async def _async_shutdown(self: PawControlDiscovery) -> None:  # noqa: E111
    call_order.append("shutdown")

  monkeypatch.setattr(PawControlDiscovery, "async_initialize", _async_initialize)  # noqa: E111
  monkeypatch.setattr(  # noqa: E111
    PawControlDiscovery, "async_discover_devices", _async_discover_devices
  )
  monkeypatch.setattr(PawControlDiscovery, "async_shutdown", _async_shutdown)  # noqa: E111

  legacy_payload = await async_get_discovered_devices(hass)  # noqa: E111

  expected: list[LegacyDiscoveryEntry] = [  # noqa: E111
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

  assert legacy_payload == expected  # noqa: E111
  assert call_order == ["initialize", "discover", "shutdown"]  # noqa: E111
  assert hass.data[DOMAIN] == {}  # noqa: E111


@dataclass(slots=True)
class _StubDeviceEntry:
  """Lightweight device entry for classification tests."""  # noqa: E111

  id: str  # noqa: E111
  manufacturer: str | None = None  # noqa: E111
  model: str | None = None  # noqa: E111
  connections: set[tuple[str, str]] = field(default_factory=set)  # noqa: E111
  configuration_url: str | None = None  # noqa: E111
  via_device_id: str | None = None  # noqa: E111


@dataclass(slots=True)
class _StubEntityEntry:
  """Minimal entity registry entry for discovery classification."""  # noqa: E111

  entity_id: str  # noqa: E111
  domain: str  # noqa: E111
  device_id: str  # noqa: E111
  original_name: str | None = None  # noqa: E111
  platform: str | None = None  # noqa: E111


class _StubEntityRegistry:
  """Entity registry adapter exposing the mapping interface used by discovery."""  # noqa: E111

  def __init__(self, entries: Iterable[_StubEntityEntry]) -> None:  # noqa: E111
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
  """Ensure the extended discovery categories are classified correctly."""  # noqa: E111

  device_entry = _StubDeviceEntry(  # noqa: E111
    id="device-1",
    manufacturer=manufacturer,
    model=model,
    connections=connections,
  )
  registry_entries = [  # noqa: E111
    _StubEntityEntry(
      entity_id=f"{domain}.{slug}",
      domain=domain,
      device_id="device-1",
      original_name=name,
      platform=domain,
    )
    for domain, slug, name in domains_with_names
  ]
  entity_registry = _StubEntityRegistry(registry_entries)  # noqa: E111

  discovery = PawControlDiscovery(hass)  # noqa: E111
  result = discovery._classify_device(device_entry, entity_registry)  # noqa: E111

  assert result is not None  # noqa: E111
  category, capabilities, confidence = result  # noqa: E111
  assert category == expected_category  # noqa: E111
  assert capabilities == CATEGORY_CAPABILITIES[expected_category]  # noqa: E111
  assert 0.5 <= confidence <= 0.95  # noqa: E111
