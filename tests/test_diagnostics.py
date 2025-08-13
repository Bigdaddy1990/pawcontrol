from types import SimpleNamespace

import pytest
from custom_components.pawcontrol import diagnostics as diag
from custom_components.pawcontrol.const import DOMAIN
from homeassistant.core import HomeAssistant


class DummyCoordinator:
    def __init__(self):
        self._dog_data = {
            "dog1": {
                "location": {"is_home": False, "current_location": "SECRET"},
                "health": {"health_notes": "private"},
                "training": {"training_history": [1, 2, 3]},
            }
        }

    def get_dog_data(self, dog_id):
        return self._dog_data[dog_id]


@pytest.mark.anyio
async def test_diagnostics_redacts_sensitive(hass: HomeAssistant):
    entry = SimpleNamespace(
        entry_id="abc123", version=1, domain=DOMAIN, title="Paw Control"
    )
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "coordinator": DummyCoordinator()
    }
    result = await diag.async_get_config_entry_diagnostics(hass, entry)
    dog = result["dogs"]["dog1"]
    assert dog["location"]["current_location"] == "REDACTED"
    assert "training_history" in dog.get("training", {})
    assert "notes" in dog.get("health", {}).get("health_notes", "[]")
