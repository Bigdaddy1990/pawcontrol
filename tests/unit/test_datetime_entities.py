from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from homeassistant.core import HomeAssistant
import pytest

from custom_components.pawcontrol.datetime import PawControlLastGroomingDateTime


class _StubCoordinator:
  """Lightweight coordinator stub for datetime entity tests."""  # noqa: E111

  def __init__(self, hass: HomeAssistant) -> None:  # noqa: E111
    self.hass = hass
    self.config_entry = SimpleNamespace(entry_id="test-entry", data={}, options={})
    self.data: dict[str, dict[str, object]] = {"test_dog": {"health": {}}}
    self.last_update_success = True

  def async_add_listener(self, update_callback: object) -> callable:  # type: ignore[override]  # noqa: E111
    """Return a no-op unsubscribe callback."""

    return lambda: None

  def get_dog_data(self, dog_id: str) -> dict[str, object]:  # noqa: E111
    """Return stored dog payloads for tests."""

    return self.data.get(dog_id, {})


@pytest.mark.asyncio
async def test_last_grooming_datetime_localizes_notes(hass: HomeAssistant) -> None:
  """The grooming datetime entity should localize manual notes."""  # noqa: E111

  coordinator = _StubCoordinator(hass)  # noqa: E111
  hass.config.language = "de"  # noqa: E111

  entity = PawControlLastGroomingDateTime(  # noqa: E111
    coordinator,
    dog_id="test_dog",
    dog_name="Test Dog",
  )
  entity.hass = hass  # noqa: E111
  entity.async_write_ha_state = Mock()  # noqa: E111
  entity._async_call_hass_service = AsyncMock(return_value=True)  # type: ignore[attr-defined]  # noqa: E111

  value = datetime(2024, 1, 2, tzinfo=UTC)  # noqa: E111
  await entity.async_set_value(value)  # noqa: E111

  entity._async_call_hass_service.assert_awaited_once()  # type: ignore[attr-defined]  # noqa: E111
  domain, service, payload = entity._async_call_hass_service.await_args.args  # type: ignore[attr-defined]  # noqa: E111

  assert domain == "pawcontrol"  # noqa: E111
  assert service == "start_grooming"  # noqa: E111
  assert payload["notes"] == "Pflegesitzung am 2024-01-02"  # noqa: E111
