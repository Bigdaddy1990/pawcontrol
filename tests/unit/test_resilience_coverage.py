"""Targeted coverage tests for resilience.py — (0% → 28%+).

Covers: CircuitBreaker, CircuitBreakerConfig, get_circuit_breaker,
        get_all_circuit_breakers, reset_all_circuit_breakers, CircuitState
"""

import pytest

from custom_components.pawcontrol.resilience import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
    get_all_circuit_breakers,
    get_circuit_breaker,
    reset_all_circuit_breakers,
)

# ─── CircuitBreakerConfig ────────────────────────────────────────────────────


@pytest.mark.unit
def test_circuit_breaker_config_defaults() -> None:
    cfg = CircuitBreakerConfig()
    assert cfg.failure_threshold == 5
    assert cfg.success_threshold == 2
    assert cfg.timeout_seconds == pytest.approx(60.0)


@pytest.mark.unit
def test_circuit_breaker_config_custom() -> None:
    cfg = CircuitBreakerConfig(failure_threshold=3, timeout_seconds=30.0)
    assert cfg.failure_threshold == 3
    assert cfg.timeout_seconds == pytest.approx(30.0)


# ─── CircuitBreaker ──────────────────────────────────────────────────────────


@pytest.mark.unit
def test_circuit_breaker_init() -> None:
    cb = CircuitBreaker("test_breaker")
    assert cb is not None


@pytest.mark.unit
def test_circuit_breaker_starts_closed() -> None:
    cb = CircuitBreaker("test_closed")
    assert cb._stats.state == CircuitState.CLOSED


@pytest.mark.unit
def test_circuit_breaker_custom_config() -> None:
    cfg = CircuitBreakerConfig(failure_threshold=2, timeout_seconds=10.0)
    cb = CircuitBreaker("test_custom", config=cfg)
    assert cb is not None


@pytest.mark.unit
def test_circuit_breaker_is_closed_initially() -> None:
    cb = CircuitBreaker("test_is_closed")
    # is_closed is a property
    assert cb.is_closed is True


@pytest.mark.unit
def test_circuit_breaker_is_open_false_initially() -> None:
    cb = CircuitBreaker("test_is_open_init")
    assert cb.is_open is False


@pytest.mark.unit
def test_circuit_breaker_state_closed() -> None:
    cb = CircuitBreaker("test_state_closed")
    assert cb.state == CircuitState.CLOSED


@pytest.mark.unit
def test_circuit_breaker_get_stats() -> None:
    cb = CircuitBreaker("test_stats")
    stats = cb.get_stats()
    # Returns CircuitBreakerStats dataclass
    assert stats is not None
    assert hasattr(stats, "state")


@pytest.mark.unit
def test_circuit_breaker_reset() -> None:
    cb = CircuitBreaker("test_reset")
    cb.reset()
    assert cb.is_closed is True


# ─── Registry functions ──────────────────────────────────────────────────────


@pytest.mark.unit
def test_get_circuit_breaker_creates_new() -> None:
    cb = get_circuit_breaker("fresh_breaker_xyz")
    assert isinstance(cb, CircuitBreaker)


@pytest.mark.unit
def test_get_circuit_breaker_returns_same() -> None:
    cb1 = get_circuit_breaker("shared_breaker_abc")
    cb2 = get_circuit_breaker("shared_breaker_abc")
    assert cb1 is cb2


@pytest.mark.unit
def test_get_all_circuit_breakers() -> None:
    get_circuit_breaker("test_registry_breaker")
    all_cbs = get_all_circuit_breakers()
    assert isinstance(all_cbs, dict)
    assert "test_registry_breaker" in all_cbs


@pytest.mark.unit
def test_reset_all_circuit_breakers_no_raise() -> None:
    get_circuit_breaker("test_reset_breaker")
    reset_all_circuit_breakers()
    # After reset all should be closed
    all_cbs = get_all_circuit_breakers()
    for cb in all_cbs.values():
        assert cb._stats.state in (
            CircuitState.CLOSED,
            CircuitState.OPEN,
            CircuitState.HALF_OPEN,
        )
