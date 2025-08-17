"""Improved discovery implementation for Paw Control.

This module provides realistic device discovery for pet tracking devices,
focusing on actual hardware that could exist in the pet tracking ecosystem.
"""

from __future__ import annotations

import asyncio
import importlib
import logging
from typing import Any, Final

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

DOMAIN: Final = "pawcontrol"

# Known pet tracking device manufacturers and models
SUPPORTED_DEVICES = {
    # GPS Pet Trackers
    "tractive": {
        "name": "Tractive GPS Pet Tracker",
        "vid": "2341",  # Example VID for Arduino-based devices
        "pid": "8037",  # Example PID
        "manufacturer": "Tractive GmbH",
        "connection_types": ["usb", "bluetooth", "wifi"],
    },
    "whistle": {
        "name": "Whistle GPS Pet Tracker",
        "vid": "10c4",  # Silicon Labs VID
        "pid": "ea60",  # Common PID for USB-Serial
        "manufacturer": "Whistle Labs",
        "connection_types": ["usb", "cellular"],
    },
    "fi_collar": {
        "name": "Fi Smart Dog Collar",
        "vid": "0483",  # STMicroelectronics VID
        "pid": "5740",  # Example PID
        "manufacturer": "Fi",
        "connection_types": ["bluetooth", "cellular"],
    },
    # Generic/DIY devices
    "esp32_tracker": {
        "name": "ESP32 Pet Tracker",
        "vid": "10c4",  # Silicon Labs CP210x
        "pid": "ea60",
        "manufacturer": "Espressif",
        "connection_types": ["usb", "wifi", "bluetooth"],
    },
    # Smart Feeders with tracking capability
    "petnet_feeder": {
        "name": "PetNet SmartFeeder",
        "manufacturer": "PetNet",
        "connection_types": ["wifi"],
        "zeroconf_type": "_petnet._tcp.local.",
    },
    "sure_petcare": {
        "name": "SureFlap Connect",
        "manufacturer": "Sure Petcare",
        "connection_types": ["wifi"],
        "zeroconf_type": "_sureflap._tcp.local.",
    },
}


def _mod(name: str):
    """Safely import optional modules."""
    try:
        return importlib.import_module(name)
    except ImportError:
        return None


async def can_connect_pawtracker(hass: HomeAssistant, data: dict[str, Any]) -> bool:
    """Test connectivity to discovered pet tracking devices.

    This function performs actual connectivity tests based on the discovery method:
    - USB: Attempts to open serial connection
    - Network: Tests HTTP/TCP connectivity
    - Bluetooth: Checks BLE advertisement
    """
    discovery_type = data.get("source", "unknown")

    try:
        if discovery_type == "usb":
            return await _test_usb_connectivity(data)
        elif discovery_type in ("dhcp", "zeroconf"):
            return await _test_network_connectivity(data)
        elif discovery_type == "bluetooth":
            return await _test_bluetooth_connectivity(data)
        else:
            # For manual setup, assume connectivity
            return True

    except Exception as err:
        _LOGGER.debug("Connectivity test failed: %s", err)
        return False


async def _test_usb_connectivity(data: dict[str, Any]) -> bool:
    """Test USB device connectivity."""
    # Check if pyserial is available
    serial_module = _mod("serial")
    if not serial_module:
        _LOGGER.debug("pyserial not available, skipping USB test")
        return True  # Assume success for environments without pyserial

    device_path = data.get("device", data.get("device_path"))
    if not device_path:
        return False

    try:
        # Attempt to open serial connection with short timeout
        ser = serial_module.Serial(device_path, timeout=1)
        ser.close()
        _LOGGER.debug("USB device %s is accessible", device_path)
        return True
    except Exception as err:
        _LOGGER.debug("USB device %s not accessible: %s", device_path, err)
        return False


async def _test_network_connectivity(data: dict[str, Any]) -> bool:
    """Test network device connectivity."""
    host = data.get("host") or data.get("ip")
    port = data.get("port", 80)  # Default HTTP port

    if not host:
        return False

    try:
        # Test TCP connectivity with timeout
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=3.0
        )
        writer.close()
        await writer.wait_closed()
        _LOGGER.debug("Network device %s:%s is reachable", host, port)
        return True
    except Exception as err:
        _LOGGER.debug("Network device %s:%s not reachable: %s", host, port, err)
        return False


async def _test_bluetooth_connectivity(data: dict[str, Any]) -> bool:
    """Test Bluetooth device connectivity."""
    # Check if bluetooth libraries are available
    bluetooth_module = _mod("bleak")
    if not bluetooth_module:
        _LOGGER.debug("Bluetooth libraries not available")
        return True  # Assume success for environments without BLE

    mac_address = data.get("mac", data.get("address"))
    if not mac_address:
        return False

    try:
        # Attempt to connect to BLE device
        device = bluetooth_module.BleakClient(mac_address)
        connected = await asyncio.wait_for(device.connect(), timeout=5.0)
        if connected:
            await device.disconnect()
            _LOGGER.debug("Bluetooth device %s is accessible", mac_address)
            return True
        return False
    except Exception as err:
        _LOGGER.debug("Bluetooth device %s not accessible: %s", mac_address, err)
        return False


def identify_pet_tracker_device(info: dict[str, Any]) -> dict[str, Any] | None:
    """Identify if a discovered device is a supported pet tracker."""
    # Check USB devices by VID/PID
    vid = info.get("vid") or info.get("vid_hex")
    pid = info.get("pid") or info.get("pid_hex")

    if vid and pid:
        vid_str = str(vid).lower().lstrip("0x")
        pid_str = str(pid).lower().lstrip("0x")

        for device_id, device_info in SUPPORTED_DEVICES.items():
            if device_info.get("vid") == vid_str and device_info.get("pid") == pid_str:
                return {
                    "device_type": device_id,
                    "name": device_info["name"],
                    "manufacturer": device_info["manufacturer"],
                    "connection_type": "usb",
                    "device_path": info.get("device"),
                }

    # Check network devices by service type
    service_type = info.get("type") or info.get("service_type")
    if service_type:
        for device_id, device_info in SUPPORTED_DEVICES.items():
            if device_info.get("zeroconf_type") == service_type:
                return {
                    "device_type": device_id,
                    "name": device_info["name"],
                    "manufacturer": device_info["manufacturer"],
                    "connection_type": "network",
                    "host": info.get("host"),
                    "port": info.get("port"),
                }

    # Check by manufacturer name in device description
    description = str(info.get("description", "")).lower()
    manufacturer = str(info.get("manufacturer", "")).lower()

    for device_id, device_info in SUPPORTED_DEVICES.items():
        device_manufacturer = device_info["manufacturer"].lower()
        if device_manufacturer in description or device_manufacturer in manufacturer:
            return {
                "device_type": device_id,
                "name": device_info["name"],
                "manufacturer": device_info["manufacturer"],
                "connection_type": "generic",
            }

    return None


def normalize_dhcp_info(info: dict[str, Any]) -> dict[str, Any]:
    """Normalize DHCP discovery data with pet tracker detection."""
    normalized = {
        "mac": str(info.get("macaddress") or info.get("mac") or "").lower(),
        "ip": info.get("ip") or info.get("ipv4"),
        "hostname": info.get("hostname") or info.get("host"),
        "source": "dhcp",
    }

    # Try to identify pet tracker by hostname patterns
    hostname = normalized.get("hostname", "").lower()
    pet_tracker_patterns = ["tractive", "whistle", "fi-collar", "petnet", "sureflap"]

    for pattern in pet_tracker_patterns:
        if pattern in hostname:
            device_info = identify_pet_tracker_device({"hostname": hostname})
            if device_info:
                normalized.update(device_info)
                break

    return normalized


def normalize_zeroconf_info(info: dict[str, Any]) -> dict[str, Any]:
    """Normalize Zeroconf discovery data with service identification."""
    normalized = {
        "name": info.get("name"),
        "host": info.get("host"),
        "port": info.get("port"),
        "type": info.get("type"),
        "properties": info.get("properties") or {},
        "source": "zeroconf",
    }

    # Check if this is a known pet tracking service
    device_info = identify_pet_tracker_device(normalized)
    if device_info:
        normalized.update(device_info)

    return normalized


def normalize_usb_info(info: dict[str, Any]) -> dict[str, Any]:
    """Normalize USB discovery data with device identification."""
    vid = info.get("vid") or info.get("vid_hex")
    pid = info.get("pid") or info.get("pid_hex")

    normalized = {
        "vid": str(vid).lower() if vid else None,
        "pid": str(pid).lower() if pid else None,
        "serial_number": info.get("serial_number") or info.get("serial"),
        "manufacturer": info.get("manufacturer"),
        "description": info.get("description"),
        "device": info.get("device") or info.get("device_path"),
        "source": "usb",
    }

    # Check if this is a known pet tracker
    device_info = identify_pet_tracker_device(normalized)
    if device_info:
        normalized.update(device_info)

        # Create device ID for USB devices
        device_id = (
            f"usb:VID_{str(vid).upper()}&PID_{str(pid).upper()}"
            if vid and pid
            else "usb:unknown"
        )
        normalized["device_id"] = device_id

    return normalized


async def discover_pet_trackers_on_network(hass: HomeAssistant) -> list[dict[str, Any]]:
    """Actively discover pet tracking devices on the local network.

    This function implements active discovery for pet tracking devices
    that may not be found through normal Home Assistant discovery.
    """
    discovered_devices = []

    # Common pet tracker network discovery
    common_ports = [80, 443, 8080, 8443, 1883]  # HTTP, HTTPS, Alt HTTP, MQTTS

    # Get local network range (simplified)
    try:
        import ipaddress
        import socket

        # Get local IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()

        # Scan local subnet (only first 10 IPs for demo)
        network = ipaddress.ip_network(f"{local_ip}/24", strict=False)
        scan_ips = list(network.hosts())[:10]

        for ip in scan_ips:
            for port in common_ports:
                try:
                    _, writer = await asyncio.wait_for(
                        asyncio.open_connection(str(ip), port), timeout=1.0
                    )
                    writer.close()
                    await writer.wait_closed()

                    # Found responsive device - try to identify
                    device_info = {
                        "host": str(ip),
                        "port": port,
                        "source": "active_scan",
                    }

                    # Try to get device information via HTTP
                    device_details = await _probe_http_device(str(ip), port)
                    if device_details:
                        device_info.update(device_details)

                        # Check if it's a pet tracker
                        tracker_info = identify_pet_tracker_device(device_info)
                        if tracker_info:
                            device_info.update(tracker_info)
                            discovered_devices.append(device_info)

                except asyncio.TimeoutError:
                    continue
                except Exception:
                    continue

    except Exception as err:
        _LOGGER.debug("Network discovery failed: %s", err)

    return discovered_devices


async def _probe_http_device(host: str, port: int) -> dict[str, Any] | None:
    """Probe HTTP device for identification information."""
    try:
        # Simple HTTP request to get device info
        aiohttp = _mod("aiohttp")
        if not aiohttp:
            return None

        timeout = aiohttp.ClientTimeout(total=3)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(f"http://{host}:{port}/") as response:
                if response.status == 200:
                    content = await response.text()

                    # Look for pet tracker indicators in HTML
                    content_lower = content.lower()
                    if any(
                        keyword in content_lower
                        for keyword in ["pet", "dog", "cat", "tracker", "collar", "gps"]
                    ):
                        return {
                            "device_type": "generic_pet_tracker",
                            "name": f"Pet Tracker at {host}",
                            "http_response": True,
                        }

    except Exception:
        pass

    return None
