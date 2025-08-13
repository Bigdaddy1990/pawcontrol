import pytest
from custom_components.pawcontrol.const import DOMAIN
from custom_components.pawcontrol.repairs import create_repair_issue
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir


class DummyEntry:
    domain = DOMAIN
    entry_id = "entry1"
    title = "Dummy"


@pytest.mark.anyio
async def test_create_repair_issue_registers(hass: HomeAssistant):
    issue_reg = ir.async_get(hass)
    create_repair_issue(hass, "missing_door_sensor", DummyEntry())
    issues = list(issue_reg.issues.values())
    assert any(i.domain == DOMAIN for i in issues)
