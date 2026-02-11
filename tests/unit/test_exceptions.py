"""Tests for the enhanced PawControl error helpers."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from custom_components.pawcontrol.exceptions import (
  ErrorSeverity,
  GPSError,
  PawControlError,
  create_error_context,
  handle_exception_gracefully,
)
from custom_components.pawcontrol.types import GPSLocation


def test_paw_control_error_context_serialization() -> None:
  """PawControlError should serialise complex context payloads to JSON-safe data."""

  timestamp = datetime(2024, 1, 1, tzinfo=UTC)
  error = PawControlError(
    "failure",
    context={
      "timestamp": timestamp,
      "details": {1: ["value", timestamp]},
    },
  )

  payload = error.to_dict()
  assert payload["context"]["timestamp"] == timestamp.isoformat()

  details = payload["context"]["details"]
  assert isinstance(details, dict)
  assert details["1"][1] == timestamp.isoformat()


def test_gps_error_context_serialization() -> None:
  """GPSError should serialise GPSLocation dataclasses into JSON payloads."""

  location = GPSLocation(
    latitude=1.0, longitude=2.0, timestamp=datetime(2024, 5, 1, tzinfo=UTC)
  )
  error = GPSError("gps failure", dog_id="spot", location=location)

  location_context = error.context["location"]
  assert isinstance(location_context, dict)
  assert location_context["timestamp"] == location.timestamp.isoformat()


def test_create_error_context_filters_none_and_serialises_values() -> None:
  """create_error_context should drop ``None`` entries and serialise datetimes."""

  payload = create_error_context(
    dog_id="spot",
    operation="sync",
    extra=datetime(2023, 8, 15, tzinfo=UTC),
    optional=None,
  )

  assert payload["dog_id"] == "spot"
  assert payload["operation"] == "sync"
  assert payload["extra"] == datetime(2023, 8, 15, tzinfo=UTC).isoformat()
  assert "optional" not in payload


def test_handle_exception_gracefully_returns_default_for_non_critical() -> None:
  """Non-critical PawControlError instances should return the provided default."""

  error = PawControlError("boom", severity=ErrorSeverity.LOW)

  wrapped = handle_exception_gracefully(
    lambda: (_ for _ in ()).throw(error),
    default_return="fallback",
    log_errors=False,
  )
  assert wrapped() == "fallback"


def test_handle_exception_gracefully_reraises_critical() -> None:
  """Critical errors should bubble up when reraise_critical is enabled."""

  error = PawControlError("boom", severity=ErrorSeverity.CRITICAL)

  wrapped = handle_exception_gracefully(
    lambda: (_ for _ in ()).throw(error), log_errors=False
  )

  with pytest.raises(PawControlError):
    wrapped()
