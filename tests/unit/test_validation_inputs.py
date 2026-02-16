"""Unit tests for input validation helpers."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from custom_components.pawcontrol.exceptions import ValidationError
from custom_components.pawcontrol.validation import (
  validate_gps_source,
  validate_notify_service,
)


class _FakeStates(dict[str, SimpleNamespace]):
  """Simple state registry for validation tests."""  # noqa: E111


class _FakeServices:
  """Simple service registry for validation tests."""  # noqa: E111

  def __init__(self, services: dict[str, dict[str, object]]) -> None:  # noqa: E111
    self._services = services

  def async_services(self) -> dict[str, dict[str, object]]:  # noqa: E111
    return self._services


@dataclass(slots=True)
class _FakeHomeAssistant:
  """Minimal Home Assistant stub for validation tests."""  # noqa: E111

  states: _FakeStates  # noqa: E111
  services: _FakeServices  # noqa: E111


def test_validate_gps_source_rejects_non_string() -> None:
  hass = _FakeHomeAssistant(states=_FakeStates(), services=_FakeServices({}))  # noqa: E111

  with pytest.raises(ValidationError) as err:  # noqa: E111
    validate_gps_source(hass, 123)

  assert err.value.constraint == "gps_source_required"  # noqa: E111


def test_validate_gps_source_rejects_unavailable_state() -> None:
  hass = _FakeHomeAssistant(  # noqa: E111
    states=_FakeStates({"device_tracker.gps": SimpleNamespace(state="unavailable")}),
    services=_FakeServices({}),
  )

  with pytest.raises(ValidationError) as err:  # noqa: E111
    validate_gps_source(hass, "device_tracker.gps")

  assert err.value.constraint == "gps_source_unavailable"  # noqa: E111


def test_validate_notify_service_rejects_invalid_format() -> None:
  hass = _FakeHomeAssistant(  # noqa: E111
    states=_FakeStates(),
    services=_FakeServices({"notify": {"mobile_app": object()}}),
  )

  with pytest.raises(ValidationError) as err:  # noqa: E111
    validate_notify_service(hass, "invalid-service")

  assert err.value.constraint == "notify_service_invalid"  # noqa: E111


def test_validate_notify_service_rejects_unknown_service() -> None:
  hass = _FakeHomeAssistant(  # noqa: E111
    states=_FakeStates(),
    services=_FakeServices({"notify": {"mobile_app_main_phone": object()}}),
  )

  with pytest.raises(ValidationError) as err:  # noqa: E111
    validate_notify_service(hass, "notify.unknown_service")

  assert err.value.constraint == "notify_service_not_found"  # noqa: E111
