from unittest.mock import AsyncMock

import pytest
from custom_components.pawcontrol import config_flow

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize("step", ["dhcp", "zeroconf", "usb"])
async def test_discovery_invalid_info_aborts(hass, step):
    flow = config_flow.ConfigFlow()
    flow.hass = hass
    flow.context = {}
    method = getattr(flow, f"async_step_{step}")
    result = await method(None)  # type: ignore[arg-type]
    assert result["type"] == "abort"
    assert result["reason"] == "not_supported"


@pytest.mark.parametrize(
    "step, source",
    [("dhcp", "dhcp"), ("zeroconf", "zeroconf"), ("usb", "usb")],
)
async def test_discovery_creates_entry(hass, monkeypatch, step, source):
    flow = config_flow.ConfigFlow()
    flow.hass = hass
    flow.context = {}
    monkeypatch.setattr(config_flow, "_can_connect", AsyncMock(return_value=True))
    discovery_info = {"mac": "aa:bb:cc:dd:ee:ff", "name": "Device"}
    result = await getattr(flow, f"async_step_{step}")(discovery_info)
    assert result["type"] == "create_entry"
    assert result["data"][config_flow.CONF_SOURCE] == source
