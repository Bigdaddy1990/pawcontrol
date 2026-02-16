import importlib
from pathlib import Path
import sys

from tests.helpers import ensure_package, install_homeassistant_stubs, load_module


def test_exceptions_module_uses_homeassistant_service_validation_error() -> None:
  """Exceptions should reuse Home Assistant's ServiceValidationError."""  # noqa: E111

  repo_root = Path(__file__).resolve().parents[2]  # noqa: E111
  package_root = repo_root / "custom_components"  # noqa: E111
  integration_root = package_root / "pawcontrol"  # noqa: E111

  ensure_package("custom_components", package_root)  # noqa: E111
  ensure_package("custom_components.pawcontrol", integration_root)  # noqa: E111
  install_homeassistant_stubs()  # noqa: E111

  sys.modules.pop("custom_components.pawcontrol.compat", None)  # noqa: E111
  sys.modules.pop("custom_components.pawcontrol.exceptions", None)  # noqa: E111

  module = load_module(  # noqa: E111
    "custom_components.pawcontrol.exceptions",
    integration_root / "exceptions.py",
  )

  assert (  # noqa: E111
    module.ServiceValidationError
    is importlib.import_module("homeassistant.exceptions").ServiceValidationError
  )
