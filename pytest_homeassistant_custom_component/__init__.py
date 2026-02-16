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
  """Minimal config entry stub for tests."""  # noqa: E111

  domain: str  # noqa: E111
  data: dict[str, object] = field(default_factory=dict)  # noqa: E111
  options: dict[str, object] = field(default_factory=dict)  # noqa: E111
  unique_id: str | None = None  # noqa: E111
  entry_id: str = "mock-entry"  # noqa: E111
  title: str | None = None  # noqa: E111
  runtime_data: object | None = None  # noqa: E111

  def add_to_hass(self, hass) -> None:  # noqa: E111
    """Attach the config entry to the stub Home Assistant instance."""

    if self.title is None:
      self.title = self.domain  # noqa: E111
    hass.data.setdefault("config_entries", {})[self.entry_id] = self
    config_entries = getattr(hass, "config_entries", None)
    if config_entries is not None and hasattr(config_entries, "_entries"):
      config_entries._entries[self.entry_id] = self  # noqa: E111


def pytest_configure(config: pytest.Config) -> None:
  """Register a marker placeholder used by the upstream plugin."""  # noqa: E111

  config.addinivalue_line(  # noqa: E111
    "markers", "hacc: compatibility marker for pytest-homeassistant stubs"
  )
