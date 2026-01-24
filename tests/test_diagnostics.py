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
