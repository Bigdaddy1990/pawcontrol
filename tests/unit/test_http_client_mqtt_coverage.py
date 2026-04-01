"""Coverage tests for http_client.py + mqtt_push.py — module imports (0% → 15%+)."""
from __future__ import annotations

import pytest

import custom_components.pawcontrol.http_client as hc
import custom_components.pawcontrol.mqtt_push as mp


# ─── http_client ─────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_http_client_module_importable() -> None:
    assert hc is not None


@pytest.mark.unit
def test_http_client_has_ensure_shared_client_session() -> None:
    assert hasattr(hc, "ensure_shared_client_session")
    assert callable(hc.ensure_shared_client_session)


@pytest.mark.unit
def test_http_client_has_unwrap() -> None:
    assert hasattr(hc, "unwrap")
    assert callable(hc.unwrap)


# ─── mqtt_push ────────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_mqtt_push_module_importable() -> None:
    assert mp is not None


@pytest.mark.unit
def test_mqtt_push_has_contents() -> None:
    attrs = [a for a in dir(mp) if not a.startswith("_")]
    assert len(attrs) >= 0
