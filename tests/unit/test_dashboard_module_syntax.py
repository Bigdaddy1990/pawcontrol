"""Regression tests ensuring dashboard modules remain syntactically valid."""

from __future__ import annotations

from pathlib import Path
import py_compile


DASHBOARD_MODULES = (
  "custom_components/pawcontrol/dashboard_cards.py",
  "custom_components/pawcontrol/dashboard_templates.py",
)


def test_dashboard_modules_compile() -> None:
  """Dashboard modules should compile without parser errors."""

  for module in DASHBOARD_MODULES:
    py_compile.compile(str(Path(module)), doraise=True)
