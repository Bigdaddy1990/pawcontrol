from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from custom_components.pawcontrol.datetime import PawControlLastGroomingDateTime
from homeassistant.core import HomeAssistant


class _StubCoordinator:
  """Lightweight coordinator stub for datetime entity tests."""

  def __init__(self, hass: HomeAssistant) -> None:
    self.hass = hass
    self.config_entry = SimpleNamespace(entry_id="test-entry", data={}, options={})
    self.data: dict[str, dict[str, object]] = {"test_dog": {"health": {}}}
    self.last_update_success = True

  def async_add_listener(self, update_callback: object) -> callable:  # type: ignore[override]
    """Return a no-op unsubscribe callback."""

    return lambda: None

  def get_dog_data(self, dog_id: str) -> dict[str, object]:
    """Return stored dog payloads for tests."""

    return self.data.get(dog_id, {})


@pytest.mark.asyncio
async def test_last_grooming_datetime_localizes_notes(hass: HomeAssistant) -> None:
  """The grooming datetime entity should localize manual notes."""

  coordinator = _StubCoordinator(hass)
  hass.config.language = "de"

  entity = PawControlLastGroomingDateTime(
    coordinator,
    dog_id="test_dog",
    dog_name="Test Dog",
  )
  entity.hass = hass
  entity.async_write_ha_state = Mock()
  entity._async_call_hass_service = AsyncMock(return_value=True)  # type: ignore[attr-defined]

  value = datetime(2024, 1, 2, tzinfo=UTC)
  await entity.async_set_value(value)

  entity._async_call_hass_service.assert_awaited_once()  # type: ignore[attr-defined]
  domain, service, payload = entity._async_call_hass_service.await_args.args  # type: ignore[attr-defined]

  assert domain == "pawcontrol"
  assert service == "start_grooming"
  assert payload["notes"] == "Pflegesitzung am 2024-01-02"
