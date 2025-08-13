import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant

DOMAIN = "pawcontrol"


@pytest.mark.anyio
async def test_config_flow_user_starts(hass: HomeAssistant):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] in ("form", "abort")
    if result["type"] == "form":
        assert "step_id" in result
