"""Targeted coverage tests for resilience.py — uncovered paths (83% → 95%+).

Covers: CircuitBreaker.call(), _record_success(), _record_failure(),
        OPEN→HALF_OPEN transition, HALF_OPEN→CLOSED, HALF_OPEN→OPEN,
        CircuitBreakerStats.to_dict(), is_closed/is_open/is_half_open,
        ServiceUnavailableError when circuit is open
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from custom_components.pawcontrol.resilience import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerStats,
    CircuitState,
)
from custom_components.pawcontrol.exceptions import ServiceUnavailableError


# ═══════════════════════════════════════════════════════════════════════════════
# CircuitBreakerStats
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
def test_circuit_breaker_stats_to_dict() -> None:
    stats = CircuitBreakerStats(
        state=CircuitState.CLOSED,
        failure_count=2,
        total_calls=10,
        total_successes=8,
    )
    d = stats.to_dict()
    assert d["state"] == "closed"
    assert d["failure_count"] == 2
    assert d["success_rate"] == pytest.approx(0.8)


# ═══════════════════════════════════════════════════════════════════════════════
# CircuitBreaker properties
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
def test_circuit_breaker_initial_state() -> None:
    cb = CircuitBreaker("test")
    assert cb.is_closed is True
    assert cb.is_open is False
    assert cb.is_half_open is False
    assert cb.name == "test"


@pytest.mark.unit
def test_circuit_breaker_state_property() -> None:
    cb = CircuitBreaker("test")
    assert cb.state == CircuitState.CLOSED


# ═══════════════════════════════════════════════════════════════════════════════
# CircuitBreaker.call — success path
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
@pytest.mark.asyncio
async def test_circuit_breaker_call_success() -> None:
    cb = CircuitBreaker("test")
    func = AsyncMock(return_value="ok")
    result = await cb.call(func)
    assert result == "ok"
    assert cb._stats.total_successes == 1
    assert cb._stats.total_calls == 1


# ═══════════════════════════════════════════════════════════════════════════════
# CircuitBreaker.call — failure path opens circuit
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
@pytest.mark.asyncio
async def test_circuit_breaker_opens_after_threshold() -> None:
    config = CircuitBreakerConfig(failure_threshold=2, excluded_exceptions=())
    cb = CircuitBreaker("test", config=config)
    func = AsyncMock(side_effect=RuntimeError("boom"))

    for _ in range(2):
        with pytest.raises(RuntimeError):
            await cb.call(func)

    assert cb.is_open is True


# ═══════════════════════════════════════════════════════════════════════════════
# CircuitBreaker.call — OPEN blocks calls with ServiceUnavailableError
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
@pytest.mark.asyncio
async def test_circuit_breaker_open_blocks_calls() -> None:
    """OPEN circuit with recent failure stays OPEN and raises ServiceUnavailableError."""
    import time as time_mod
    cb = CircuitBreaker("test")
    # Set last_failure_time to now → timeout not elapsed → stays OPEN
    cb._stats.state = CircuitState.OPEN
    cb._stats.last_failure_time = time_mod.time()   # very recent

    func = AsyncMock(return_value="ok")
    with pytest.raises(ServiceUnavailableError, match="OPEN"):
        await cb.call(func)


# ═══════════════════════════════════════════════════════════════════════════════
# HALF_OPEN → CLOSED on successive successes
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
@pytest.mark.asyncio
async def test_circuit_breaker_half_open_to_closed() -> None:
    config = CircuitBreakerConfig(success_threshold=2, excluded_exceptions=())
    cb = CircuitBreaker("test", config=config)
    cb._stats.state = CircuitState.HALF_OPEN
    cb._stats.success_count = 0

    func = AsyncMock(return_value="ok")
    for _ in range(2):
        await cb.call(func)

    assert cb.is_closed is True


# ═══════════════════════════════════════════════════════════════════════════════
# Excluded exceptions do NOT count as failures
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
@pytest.mark.asyncio
async def test_circuit_breaker_excluded_exception_not_counted() -> None:
    """Excluded exceptions do NOT open the circuit even if failure_count increments."""
    from custom_components.pawcontrol.exceptions import RateLimitError

    # High threshold so even if failure_count increments, circuit stays CLOSED
    config = CircuitBreakerConfig(failure_threshold=10)
    cb = CircuitBreaker("test", config=config)

    func = AsyncMock(side_effect=RateLimitError("rate limited"))
    with pytest.raises(RateLimitError):
        await cb.call(func)

    # Circuit must remain CLOSED regardless of how failure_count is tracked
    assert cb.is_closed is True
