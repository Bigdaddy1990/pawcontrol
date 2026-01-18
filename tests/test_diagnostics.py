"""Unit tests for diagnostics redaction helpers."""

from __future__ import annotations

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
