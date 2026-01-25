"""Unit tests for diagnostics redaction helpers."""

from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_module(name: str, path: Path) -> ModuleType:
  spec = importlib.util.spec_from_file_location(name, path)
  if spec is None or spec.loader is None:
    raise RuntimeError(f"Cannot load module {name} from {path}")
  module = importlib.util.module_from_spec(spec)
  sys.modules[name] = module
  spec.loader.exec_module(module)
  return module


def _load_redaction_helpers() -> ModuleType:
  return _load_module(
    "pawcontrol_diagnostics_redaction",
    PROJECT_ROOT / "custom_components" / "pawcontrol" / "diagnostics_redaction.py",
  )


def _load_diagnostics() -> ModuleType:
  return importlib.import_module("custom_components.pawcontrol.diagnostics")


def test_redact_sensitive_keys_respects_word_boundaries() -> None:
  """Ensure redaction matches keys at boundaries without over-redacting."""

  module = _load_redaction_helpers()
  patterns = module.compile_redaction_patterns({"location", "api_key"})
  payload = {
    "allocation": "keep",
    "home_location": "secret",
    "stats": {"gps_location": "secret", "api_key": "token"},
  }

  redacted = module.redact_sensitive_data(payload, patterns=patterns)

  assert redacted["allocation"] == "keep"
  assert redacted["home_location"] == "**REDACTED**"
  assert redacted["stats"]["gps_location"] == "**REDACTED**"
  assert redacted["stats"]["api_key"] == "**REDACTED**"


def test_notification_rejection_metrics_defaults() -> None:
  """Notification rejection metrics should include full defaults."""

  diagnostics = _load_diagnostics()
  payload = diagnostics._build_notification_rejection_metrics(None)

  assert payload["schema_version"] == 1
  assert payload["total_services"] == 0
  assert payload["total_failures"] == 0
  assert payload["services_with_failures"] == []
  assert payload["service_failures"] == {}
  assert payload["service_consecutive_failures"] == {}
  assert payload["service_last_error_reasons"] == {}
  assert payload["service_last_errors"] == {}


def test_notification_rejection_metrics_summarises_services() -> None:
  """Service-level failures should be summarised for notification diagnostics."""

  diagnostics = _load_diagnostics()
  delivery = {
    "services": {
      "notify.mobile_app_pixel": {
        "total_failures": 3,
        "consecutive_failures": 2,
        "last_error_reason": "missing_notify_service",
        "last_error": "missing_notify_service",
      },
      "notify.webhook": {
        "total_failures": 0,
        "consecutive_failures": 0,
        "last_error_reason": None,
        "last_error": None,
      },
    },
  }

  payload = diagnostics._build_notification_rejection_metrics(delivery)

  assert payload["total_services"] == 2
  assert payload["total_failures"] == 3
  assert payload["services_with_failures"] == ["notify.mobile_app_pixel"]
  assert payload["service_failures"]["notify.mobile_app_pixel"] == 3
  assert payload["service_consecutive_failures"]["notify.mobile_app_pixel"] == 2
  assert payload["service_last_error_reasons"]["notify.mobile_app_pixel"] == (
    "missing_notify_service"
  )


def test_redacts_mac_strings_and_serial_numbers_in_nested_payloads() -> None:
  """MAC addresses and serial numbers must be redacted in nested structures."""

  diagnostics = _load_diagnostics()
  redaction = _load_redaction_helpers()
  patterns = redaction.compile_redaction_patterns(diagnostics.REDACTED_KEYS)
  payload = {
    "device": {
      "name": "PawControl Hub",
      "serial_number": "SN-12345",
      "hardware_id": "HW-9999",
      "nested": {
        "unique_id": "hub-001",
        "radio": {"macaddress": "aa:bb:cc:dd:ee:ff"},
      },
    },
    "network": {
      "gateway_mac": "11:22:33:44:55:66",
      "connection": ["ethernet", "AA:BB:CC:DD:EE:FF"],
    },
  }

  redacted = redaction.redact_sensitive_data(payload, patterns=patterns)

  assert redacted["device"]["serial_number"] == "**REDACTED**"
  assert redacted["device"]["hardware_id"] == "**REDACTED**"
  assert redacted["device"]["nested"]["unique_id"] == "**REDACTED**"
  assert redacted["device"]["nested"]["radio"]["macaddress"] == "**REDACTED**"
  assert redacted["network"]["gateway_mac"] == "**REDACTED**"
  assert redacted["network"]["connection"][1] == "**REDACTED**"


def test_redacts_connections_and_identifiers_payloads() -> None:
  """Connections and identifiers lists should redact MAC addresses."""

  diagnostics = _load_diagnostics()
  redaction = _load_redaction_helpers()
  patterns = redaction.compile_redaction_patterns(diagnostics.REDACTED_KEYS)
  payload = {
    "connections": [["mac", "12:34:56:78:9A:BC"], ["ip", "192.168.1.100"]],
    "identifiers": [["pawcontrol", "device-123"], ["mac", "AA:BB:CC:DD:EE:FF"]],
  }

  redacted = redaction.redact_sensitive_data(payload, patterns=patterns)

  assert redacted["connections"][0][1] == "**REDACTED**"
  assert redacted["connections"][1][1] == "**REDACTED**"
  assert redacted["identifiers"][0][1] == "device-123"
  assert redacted["identifiers"][1][1] == "**REDACTED**"
