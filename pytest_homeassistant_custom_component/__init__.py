"""Shim for pytest-homeassistant-custom-component.

The real plugin is optional for the lightweight stub environment. This module
only exposes a marker placeholder so pytest can start without external
dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest


@dataclass
class MockConfigEntry:
  """Minimal config entry stub for tests."""

  domain: str
  data: dict[str, object] = field(default_factory=dict)
  options: dict[str, object] = field(default_factory=dict)
  unique_id: str | None = None
  entry_id: str = "mock-entry"
  title: str | None = None
  runtime_data: object | None = None

  def add_to_hass(self, hass) -> None:
    """Attach the config entry to the stub Home Assistant instance."""

    if self.title is None:
      self.title = self.domain
    hass.data.setdefault("config_entries", {})[self.entry_id] = self


def pytest_configure(config: pytest.Config) -> None:
  """Register a marker placeholder used by the upstream plugin."""

  config.addinivalue_line(
    "markers", "hacc: compatibility marker for pytest-homeassistant stubs"
  )
