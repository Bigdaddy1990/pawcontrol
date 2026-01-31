"""Unit tests for diagnostics redaction helpers."""

from __future__ import annotations

import ast
import asyncio
import importlib
import importlib.util
import json
import sys
from dataclasses import dataclass, is_dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from types import ModuleType

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PAWCONTROL_ROOT = PROJECT_ROOT / "custom_components" / "pawcontrol"


def _assert_json_serialisable(value: Any) -> None:
  if isinstance(value, dict):
    for item in value.values():
      _assert_json_serialisable(item)
    return
  if isinstance(value, list):
    for item in value:
      _assert_json_serialisable(item)
    return

  assert not isinstance(value, datetime)
  assert not isinstance(value, timedelta)
  assert not isinstance(value, set)
  assert not is_dataclass(value)


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


def test_rejection_metrics_capture_failure_reasons() -> None:
  """Rejection metrics should surface aggregated failure reasons."""

  from custom_components.pawcontrol.coordinator_tasks import derive_rejection_metrics

  summary = {
    "failure_reasons": {"auth_error": 2, "device_unreachable": 1},
    "last_failure_reason": "auth_error",
  }

  metrics = derive_rejection_metrics(summary)

  assert metrics["failure_reasons"] == {"auth_error": 2, "device_unreachable": 1}
  assert metrics["last_failure_reason"] == "auth_error"


def test_guard_notification_error_metrics_aggregate_counts() -> None:
  """Guard and notification errors should aggregate into a shared snapshot."""

  diagnostics = _load_diagnostics()
  guard_metrics = {
    "executed": 4,
    "skipped": 3,
    "reasons": {
      "missing_instance": 2,
      "missing_services_api": 1,
    },
  }
  delivery = {
    "services": {
      "notify.mobile_app_pixel": {
        "total_failures": 4,
        "consecutive_failures": 3,
        "last_error_reason": "exception",
        "last_error": "Unauthorized",
      },
      "notify.webhook": {
        "total_failures": 2,
        "consecutive_failures": 1,
        "last_error_reason": "exception",
        "last_error": "Device unreachable",
      },
    },
  }

  payload = diagnostics._build_guard_notification_error_metrics(
    guard_metrics,
    delivery,
  )

  assert payload["available"] is True
  assert payload["total_errors"] == 9
  assert payload["guard"]["skipped"] == 3
  assert payload["guard"]["reasons"]["missing_instance"] == 2
  assert payload["notifications"]["total_failures"] == 6
  assert payload["notifications"]["services_with_failures"] == [
    "notify.mobile_app_pixel",
    "notify.webhook",
  ]
  assert payload["classified_errors"]["missing_service"] == 3
  assert payload["classified_errors"]["auth_error"] == 4
  assert payload["classified_errors"]["device_unreachable"] == 2


def test_service_guard_metrics_defaults_to_zero_payload() -> None:
  """Service guard metrics should always export default-zero payloads."""

  diagnostics = _load_diagnostics()
  runtime_data = type("RuntimeData", (), {"performance_stats": {}})()

  payload = asyncio.run(diagnostics._get_service_execution_diagnostics(runtime_data))

  assert payload["guard_metrics"] == {
    "executed": 0,
    "skipped": 0,
    "reasons": {},
    "last_results": [],
  }


def test_configuration_url_redacted_in_diagnostics() -> None:
  """Ensure configuration_url fields are redacted in diagnostics payloads."""

  diagnostics = _load_diagnostics()
  payload = {
    "devices": [
      {
        "id": "device-1",
        "configuration_url": (
          "https://example.com/config?token=supersecrettoken&ip=192.168.1.12"
        ),
      }
    ]
  }

  redacted = diagnostics._redact_sensitive_data(payload)

  assert redacted["devices"][0]["configuration_url"] == "**REDACTED**"


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


def test_entity_attribute_normalisation_is_json_serialisable() -> None:
  """Entity attribute normalization must yield JSON-serialisable values."""

  from custom_components.pawcontrol.utils import normalise_entity_attributes

  @dataclass
  class SamplePayload:
    """Dataclass payload used to validate JSON normalization."""

    label: str
    created_at: datetime
    window: timedelta

  sample = SamplePayload(
    label="demo",
    created_at=datetime(2024, 1, 2, 3, 4, 5, tzinfo=UTC),
    window=timedelta(minutes=15),
  )

  attributes = {
    "timestamp": datetime(2024, 1, 2, 3, 4, 5, tzinfo=UTC),
    "duration": timedelta(seconds=90),
    "tags": {"alpha", "beta"},
    "payload": sample,
    "nested": {
      "dates": [date(2024, 1, 2), time(3, 4, 5)],
      "samples": [
        SamplePayload(
          "nested",
          datetime(2024, 1, 2, tzinfo=UTC),
          timedelta(minutes=2),
        )
      ],
    },
  }

  normalised = normalise_entity_attributes(attributes)

  _assert_json_serialisable(normalised)
  json.dumps(normalised)


def test_extra_state_attributes_use_normalisation_helpers() -> None:
  """extra_state_attributes implementations must normalise payloads."""

  missing = []
  for path in PAWCONTROL_ROOT.rglob("*.py"):
    source = path.read_text(encoding="utf-8")
    module = ast.parse(source)
    for node in ast.walk(module):
      if isinstance(node, ast.FunctionDef) and node.name == "extra_state_attributes":
        calls = {
          call.func.attr if isinstance(call.func, ast.Attribute) else call.func.id
          for call in ast.walk(node)
          if isinstance(call, ast.Call)
          and isinstance(call.func, (ast.Attribute, ast.Name))
        }
        if not {
          "normalise_entity_attributes",
          "ensure_json_mapping",
          "_finalize_entity_attributes",
          "_normalise_attributes",
        }.intersection(calls):
          missing.append(f"{path}:{node.lineno}")

  assert not missing, "Missing attribute normalization helpers:\n" + "\n".join(
    sorted(missing),
  )
