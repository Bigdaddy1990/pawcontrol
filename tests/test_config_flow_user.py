import pytest
from homeassistant.core import HomeAssistant

from custom_components.pawcontrol import config_flow as cf


@pytest.mark.anyio
async def test_config_flow_user_starts(hass: HomeAssistant):
    flow = cf.PawControlConfigFlow()
    flow.hass = hass
    flow.context = {}
    result = await flow.async_step_user()
    assert result["type"] in ("form", "abort")
    if result["type"] == "form":
        assert "step_id" in result
