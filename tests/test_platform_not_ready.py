import pytest
from homeassistant.exceptions import PlatformNotReady
from pytest_homeassistant_custom_component.common import MockConfigEntry

pytestmark = pytest.mark.asyncio


async def test_sensor_platform_not_ready(hass):
    """Sensor setup should raise PlatformNotReady when coordinator has no data."""
    import custom_components.pawcontrol.sensor as sensor

    entry = MockConfigEntry(domain=sensor.DOMAIN, data={}, options={"dogs": []})
    entry.add_to_hass(hass)

    class DummyCoordinator:
        last_update_success = False

        async def async_refresh(self):
            return None

    entry.runtime_data = type("RD", (), {"coordinator": DummyCoordinator()})()

    with pytest.raises(PlatformNotReady):
        await sensor.async_setup_entry(hass, entry, lambda *args, **kwargs: None)
