import asyncio
import pytest

from custom_components.pawcontrol.discovery import (
    can_connect_pawtracker,
    normalize_dhcp_info,
    normalize_zeroconf_info,
    normalize_usb_info,
)


pytestmark = pytest.mark.asyncio


@pytest.mark.enable_socket
async def test_can_connect_pawtracker_tcp_success(hass, socket_enabled):
    async def handle(reader, writer):
        writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    host, port = server.sockets[0].getsockname()[:2]
    data = {"host": host, "port": port}
    try:
        assert await can_connect_pawtracker(hass, data) is True
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.enable_socket
async def test_can_connect_pawtracker_tcp_fail(hass, socket_enabled):
    async def handle(reader, writer):
        writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    host, port = server.sockets[0].getsockname()[:2]
    server.close()
    await server.wait_closed()

    data = {"host": host, "port": port}
    assert await can_connect_pawtracker(hass, data) is False


def test_normalize_dhcp_info():
    info = {"macaddress": "AA-BB-CC-DD-EE-FF", "ip": "1.2.3.4", "hostname": "dog"}
    assert normalize_dhcp_info(info) == {
        "mac": "aa:bb:cc:dd:ee:ff",
        "ip": "1.2.3.4",
        "hostname": "dog",
    }


def test_normalize_zeroconf_info():
    info = {"name": "Test._tcp.local.", "host": "test.local", "port": "80", "properties": {}}
    assert normalize_zeroconf_info(info) == {
        "name": "Test._tcp.local",
        "host": "test.local",
        "port": 80,
        "properties": {},
    }


def test_normalize_usb_info():
    info = {"vid": "10c4", "pid": "ea60", "serial_number": "123", "manufacturer": "ACME", "description": "USB"}
    norm = normalize_usb_info(info)
    assert norm["device_id"] == "usb:VID_10C4&PID_EA60"
    assert norm["vid"] == "10c4"
    assert norm["pid"] == "ea60"
