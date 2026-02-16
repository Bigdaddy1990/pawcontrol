"""Common helpers exposed by the pytest-homeassistant-custom-component stub."""

from __future__ import annotations

import sys
from types import ModuleType
from typing import Any

from . import MockConfigEntry

__all__ = ["MockConfigEntry", "MockModule", "mock_integration", "patch_all"]


class MockModule(ModuleType):
  """Minimal integration module used to seed Home Assistant stubs in tests."""  # noqa: E111

  def __init__(  # noqa: E111
    self,
    *,
    domain: str,
    name: str | None = None,
    manifest: dict[str, Any] | None = None,
  ) -> None:
    module_name = name or domain
    super().__init__(module_name)
    self.domain = domain
    self.__file__ = f"<mocked module {module_name}>"
    self.__path__ = []  # type: ignore[attr-defined]
    self.manifest = manifest or {"domain": domain}


def mock_integration(hass, module: ModuleType) -> ModuleType:
  """Register a mocked integration with the Home Assistant test stubs."""  # noqa: E111

  domain = getattr(module, "domain", None) or getattr(module, "DOMAIN", None)  # noqa: E111
  if domain is None:  # noqa: E111
    raise ValueError("mock integration must provide a domain")

  hass.config.components.add(domain)  # noqa: E111
  sys.modules[module.__name__] = module  # noqa: E111
  sys.modules[f"homeassistant.components.{domain}"] = module  # noqa: E111
  return module  # noqa: E111


def patch_all(
  mock_config: dict[str, Any],
) -> dict[str, Any]:  # pragma: no cover - compat shim
  """Compatibility helper retained for third-party tests."""  # noqa: E111

  return mock_config  # noqa: E111
