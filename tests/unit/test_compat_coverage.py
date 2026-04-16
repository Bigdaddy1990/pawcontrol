"""Targeted coverage tests for compat.py — pure helpers (0% → 20%+).

Covers: ensure_homeassistant_config_entry_symbols,
        ensure_homeassistant_exception_symbols
"""

import pytest

from custom_components.pawcontrol.compat import (
    ensure_homeassistant_config_entry_symbols,
    ensure_homeassistant_exception_symbols,
)


@pytest.mark.unit
def test_ensure_config_entry_symbols_no_raise() -> None:  # noqa: D103
    ensure_homeassistant_config_entry_symbols()  # must not raise


@pytest.mark.unit
def test_ensure_exception_symbols_no_raise() -> None:  # noqa: D103
    ensure_homeassistant_exception_symbols()


@pytest.mark.unit
def test_ensure_symbols_idempotent() -> None:  # noqa: D103
    ensure_homeassistant_config_entry_symbols()
    ensure_homeassistant_config_entry_symbols()  # safe to call twice


@pytest.mark.unit
def test_ensure_exception_symbols_idempotent() -> None:  # noqa: D103
    ensure_homeassistant_exception_symbols()
    ensure_homeassistant_exception_symbols()
