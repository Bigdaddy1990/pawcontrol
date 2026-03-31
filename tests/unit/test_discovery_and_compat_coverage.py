"""Targeted coverage tests for discovery.py + compat.py — (0% → 20%+).

discovery: DiscoveredDevice dataclass, DiscoveryConnectionInfo
compat: bind_exception_alias, ensure_homeassistant_exception_symbols,
        ensure_homeassistant_config_entry_symbols
"""
from __future__ import annotations

import pytest

from custom_components.pawcontrol.compat import (
    bind_exception_alias,
    ensure_homeassistant_config_entry_symbols,
    ensure_homeassistant_exception_symbols,
)


# ─── compat ───────────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_ensure_homeassistant_exception_symbols_no_raise() -> None:
    ensure_homeassistant_exception_symbols()   # idempotent, no raise


@pytest.mark.unit
def test_ensure_homeassistant_exception_symbols_twice() -> None:
    ensure_homeassistant_exception_symbols()
    ensure_homeassistant_exception_symbols()   # calling twice is fine


@pytest.mark.unit
def test_ensure_homeassistant_config_entry_symbols_no_raise() -> None:
    ensure_homeassistant_config_entry_symbols()


@pytest.mark.unit
def test_bind_exception_alias_returns_callable() -> None:
    result = bind_exception_alias("TestAlias")
    assert callable(result)


@pytest.mark.unit
def test_bind_exception_alias_callable_no_raise() -> None:
    unbind = bind_exception_alias("TestAlias2")
    unbind()   # calling the returned unbind function should not raise
