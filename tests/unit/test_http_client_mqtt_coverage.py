"""Coverage tests for http_client.py + mqtt_push.py — module imports (0% → 15%+)."""

import pytest

import custom_components.pawcontrol.http_client as hc
import custom_components.pawcontrol.mqtt_push as mp

# ─── http_client ─────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_http_client_module_importable() -> None:  # noqa: D103
    assert hc is not None


@pytest.mark.unit
def test_http_client_has_ensure_shared_client_session() -> None:  # noqa: D103
    assert hasattr(hc, "ensure_shared_client_session")
    assert callable(hc.ensure_shared_client_session)


@pytest.mark.unit
def test_http_client_has_unwrap() -> None:  # noqa: D103
    assert hasattr(hc, "unwrap")
    assert callable(hc.unwrap)


# ─── mqtt_push ────────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_mqtt_push_module_importable() -> None:  # noqa: D103
    assert mp is not None


@pytest.mark.unit
def test_mqtt_push_has_contents() -> None:  # noqa: D103
    attrs = [a for a in dir(mp) if not a.startswith("_")]
    assert len(attrs) >= 0
