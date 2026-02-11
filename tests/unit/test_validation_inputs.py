"""Unit tests for input validation helpers."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from custom_components.pawcontrol.exceptions import ValidationError
from custom_components.pawcontrol.validation import (
  validate_gps_source,
  validate_notify_service,
)


class _FakeStates(dict[str, SimpleNamespace]):
  """Simple state registry for validation tests."""


class _FakeServices:
  """Simple service registry for validation tests."""

  def __init__(self, services: dict[str, dict[str, object]]) -> None:
    self._services = services

  def async_services(self) -> dict[str, dict[str, object]]:
    return self._services


class _FakeHomeAssistant:
  """Minimal Home Assistant stub for validation tests."""

  def __init__(self, *, states: _FakeStates, services: _FakeServices) -> None:
    self.states = states
    self.services = services


def test_validate_gps_source_rejects_non_string() -> None:
  hass = _FakeHomeAssistant(states=_FakeStates(), services=_FakeServices({}))

  with pytest.raises(ValidationError) as err:
    validate_gps_source(hass, 123)

  assert err.value.constraint == "gps_source_required"


def test_validate_gps_source_rejects_unavailable_state() -> None:
  hass = _FakeHomeAssistant(
    states=_FakeStates({"device_tracker.gps": SimpleNamespace(state="unavailable")}),
    services=_FakeServices({}),
  )

  with pytest.raises(ValidationError) as err:
    validate_gps_source(hass, "device_tracker.gps")

  assert err.value.constraint == "gps_source_unavailable"


def test_validate_notify_service_rejects_invalid_format() -> None:
  hass = _FakeHomeAssistant(
    states=_FakeStates(),
    services=_FakeServices({"notify": {"mobile_app": object()}}),
  )

  with pytest.raises(ValidationError) as err:
    validate_notify_service(hass, "invalid-service")

  assert err.value.constraint == "notify_service_invalid"


def test_validate_notify_service_rejects_unknown_service() -> None:
  hass = _FakeHomeAssistant(
    states=_FakeStates(),
    services=_FakeServices({"notify": {"mobile_app_main_phone": object()}}),
  )

  with pytest.raises(ValidationError) as err:
    validate_notify_service(hass, "notify.unknown_service")

  assert err.value.constraint == "notify_service_not_found"
