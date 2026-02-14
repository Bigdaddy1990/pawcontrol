"""Regression tests ensuring key modules remain syntactically valid."""

from __future__ import annotations

from pathlib import Path
import py_compile

import pytest


SYNTAX_GUARD_MODULES = (
  "custom_components/pawcontrol/dashboard_cards.py",
  "custom_components/pawcontrol/dashboard_templates.py",
  "custom_components/pawcontrol/input_validation.py",
)


@pytest.mark.parametrize("module", SYNTAX_GUARD_MODULES)
def test_syntax_guard_modules_compile(module: str) -> None:
  """Guarded modules should compile without parser errors."""

  py_compile.compile(str(Path(module)), doraise=True)
