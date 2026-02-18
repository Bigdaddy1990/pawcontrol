"""Regression tests ensuring key modules remain syntactically valid."""

from pathlib import Path
import py_compile

import pytest

SYNTAX_GUARD_MODULES = (
    Path("custom_components/pawcontrol/dashboard_cards.py"),
    Path("custom_components/pawcontrol/dashboard_templates.py"),
    Path("custom_components/pawcontrol/input_validation.py"),
)


@pytest.mark.parametrize("module", SYNTAX_GUARD_MODULES, ids=str)
def test_syntax_guard_modules_compile(module: Path) -> None:
    """Guarded modules should compile without parser errors."""
    py_compile.compile(module, doraise=True)
