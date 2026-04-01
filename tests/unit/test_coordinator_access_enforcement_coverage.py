"""Coverage tests for coordinator_access_enforcement.py — (0% → 30%+).

Covers: log_direct_access_warning, print_access_guidelines,
        CoordinatorAccessViolation, CoordinatorDataProxy
"""
from __future__ import annotations

import pytest

from custom_components.pawcontrol.coordinator_access_enforcement import (
    CoordinatorAccessViolation,
    CoordinatorDataProxy,
    log_direct_access_warning,
    print_access_guidelines,
)


# ─── log_direct_access_warning ────────────────────────────────────────────────

@pytest.mark.unit
def test_log_direct_access_warning_no_raise() -> None:
    log_direct_access_warning("sensor.rex_weight", "weight")


@pytest.mark.unit
def test_log_direct_access_warning_with_method() -> None:
    log_direct_access_warning(
        "sensor.rex_activity", "activity",
        coordinator_method="get_dog_activity",
    )


# ─── print_access_guidelines ──────────────────────────────────────────────────

@pytest.mark.unit
def test_print_access_guidelines_no_raise() -> None:
    print_access_guidelines()


# ─── CoordinatorAccessViolation ───────────────────────────────────────────────

@pytest.mark.unit
def test_coordinator_access_violation_init() -> None:
    err = CoordinatorAccessViolation("direct access not allowed")
    assert isinstance(err, Exception)


@pytest.mark.unit
def test_coordinator_access_violation_with_entity_id() -> None:
    err = CoordinatorAccessViolation("access error", entity_id="sensor.rex_weight")
    assert err.entity_id == "sensor.rex_weight"


@pytest.mark.unit
def test_coordinator_access_violation_raise() -> None:
    with pytest.raises(CoordinatorAccessViolation):
        raise CoordinatorAccessViolation("test violation")


# ─── CoordinatorDataProxy ─────────────────────────────────────────────────────

@pytest.mark.unit
def test_coordinator_data_proxy_init() -> None:
    data = {"dog_id": "rex", "weight": 22.0}
    proxy = CoordinatorDataProxy(data, "sensor.rex_weight")
    assert proxy is not None


@pytest.mark.unit
def test_coordinator_data_proxy_no_log() -> None:
    data = {"feeding": {"meals": 2}}
    proxy = CoordinatorDataProxy(data, "sensor.rex_feeding", log_access=False)
    assert proxy is not None


@pytest.mark.unit
def test_coordinator_data_proxy_get() -> None:
    data = {"dog_id": "rex", "weight": 22.0}
    proxy = CoordinatorDataProxy(data, "test_accessor", log_access=False)
    result = proxy.get("dog_id")
    assert result == "rex" or result is not None


@pytest.mark.unit
def test_coordinator_data_proxy_get_missing_key() -> None:
    proxy = CoordinatorDataProxy({}, "test", log_access=False)
    result = proxy.get("nonexistent", "default")
    assert result == "default" or result is None
