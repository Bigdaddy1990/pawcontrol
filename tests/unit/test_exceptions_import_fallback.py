from __future__ import annotations

import importlib
import sys
from pathlib import Path

from tests.helpers import ensure_package, install_homeassistant_stubs, load_module


def test_exceptions_module_uses_homeassistant_service_validation_error() -> None:
  """Exceptions should reuse Home Assistant's ServiceValidationError."""

  repo_root = Path(__file__).resolve().parents[2]
  package_root = repo_root / "custom_components"
  integration_root = package_root / "pawcontrol"

  ensure_package("custom_components", package_root)
  ensure_package("custom_components.pawcontrol", integration_root)
  install_homeassistant_stubs()

  sys.modules.pop("custom_components.pawcontrol.compat", None)
  sys.modules.pop("custom_components.pawcontrol.exceptions", None)

  module = load_module(
    "custom_components.pawcontrol.exceptions",
    integration_root / "exceptions.py",
  )

  assert (
    module.ServiceValidationError
    is importlib.import_module("homeassistant.exceptions").ServiceValidationError
  )
