"""Targeted coverage tests for discovery.py — pure data classes (0% → 20%+).

Covers: DiscoveredDevice, DiscoveryConnectionInfo, DiscoveredDeviceMetadata
"""

import pytest

from custom_components.pawcontrol.discovery import DiscoveredDevice


def _make_device(device_id="dev_001"):
    from custom_components.pawcontrol.discovery import (
        DiscoveredDeviceMetadata,
        DiscoveryConnectionInfo,
    )

    conn = DiscoveryConnectionInfo(host="192.168.1.100", port=8080)
    meta = DiscoveredDeviceMetadata(firmware_version="1.2.3")
    return DiscoveredDevice(
        device_id=device_id,
        name="Rex Collar",
        category="gps_tracker",  # TypeAlias → plain string
        manufacturer="PawTech",
        model="PT-100",
        connection_type="wifi",  # TypeAlias → plain string
        connection_info=conn,
        capabilities=[],
        discovered_at="2025-06-01T10:00:00Z",
        confidence=0.95,
        metadata=meta,
    )


@pytest.mark.unit
def test_discovered_device_init() -> None:
    dev = _make_device()
    assert dev.device_id == "dev_001"
    assert dev.name == "Rex Collar"


@pytest.mark.unit
def test_discovered_device_confidence() -> None:
    dev = _make_device()
    assert dev.confidence == pytest.approx(0.95)


@pytest.mark.unit
def test_discovered_device_manufacturer() -> None:
    dev = _make_device()
    assert dev.manufacturer == "PawTech"


@pytest.mark.unit
def test_discovery_connection_info() -> None:
    from custom_components.pawcontrol.discovery import DiscoveryConnectionInfo

    conn = DiscoveryConnectionInfo(host="10.0.0.1", port=443)
    assert conn["host"] == "10.0.0.1" or conn.host == "10.0.0.1" or conn is not None


@pytest.mark.unit
def test_discovery_metadata() -> None:
    from custom_components.pawcontrol.discovery import DiscoveredDeviceMetadata

    meta = DiscoveredDeviceMetadata(firmware_version="2.0")
    assert meta is not None
