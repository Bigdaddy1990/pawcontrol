"""Unit tests for resilience.py.

Covers CircuitBreaker state transitions, RetryStrategy exponential backoff,
FallbackStrategy default/fallback resolution, ResilienceManager composition,
global registry helpers, and decorator wrappers.
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("homeassistant")

from custom_components.pawcontrol.exceptions import (
    NetworkError,
    RateLimitError,
    ServiceUnavailableError,
)
from custom_components.pawcontrol.resilience import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerStats,
    CircuitState,
    FallbackStrategy,
    ResilienceManager,
    RetryConfig,
    RetryStrategy,
    get_all_circuit_breakers,
    get_circuit_breaker,
    reset_all_circuit_breakers,
    with_circuit_breaker,
    with_fallback,
    with_retry,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _ok() -> str:
    return "ok"


async def _raise(exc: Exception) -> str:
    raise exc


# ---------------------------------------------------------------------------
# CircuitBreakerConfig defaults
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_circuit_breaker_config_defaults() -> None:
    """Default config has sensible failure threshold and timeout."""
    cfg = CircuitBreakerConfig()
    assert cfg.failure_threshold == 5
    assert cfg.success_threshold == 2
    assert cfg.timeout_seconds == 60.0
    assert RateLimitError in cfg.excluded_exceptions


# ---------------------------------------------------------------------------
# CircuitBreakerStats.to_dict
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_circuit_breaker_stats_to_dict_zero_calls() -> None:
    """Success rate is 0.0 when total_calls is 0."""
    stats = CircuitBreakerStats()
    d = stats.to_dict()
    assert d["state"] == "closed"
    assert d["success_rate"] == 0.0


@pytest.mark.unit
def test_circuit_breaker_stats_to_dict_with_calls() -> None:
    """Success rate computed from total_calls and total_successes."""
    stats = CircuitBreakerStats(total_calls=4, total_successes=3)
    d = stats.to_dict()
    assert d["success_rate"] == pytest.approx(0.75)


# ---------------------------------------------------------------------------
# CircuitBreaker — happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.unit
async def test_circuit_breaker_call_success_stays_closed() -> None:
    """Successful calls keep circuit closed."""
    breaker = CircuitBreaker("test_ok")
    result = await breaker.call(_ok)
    assert result == "ok"
    assert breaker.is_closed


@pytest.mark.asyncio
@pytest.mark.unit
async def test_circuit_breaker_context_manager_success() -> None:
    """Async context manager records success without raising."""
    breaker = CircuitBreaker("ctx_ok")
    async with breaker:
        pass
    assert breaker.is_closed
    stats = breaker.get_stats()
    assert stats.total_successes == 1


# ---------------------------------------------------------------------------
# CircuitBreaker — failure → OPEN transition
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.unit
async def test_circuit_breaker_opens_after_threshold() -> None:
    """Circuit opens after hitting failure_threshold consecutive errors."""
    cfg = CircuitBreakerConfig(failure_threshold=3, timeout_seconds=9999.0)
    breaker = CircuitBreaker("open_test", config=cfg)

    for _ in range(3):
        with pytest.raises(NetworkError):
            await breaker.call(_raise, NetworkError("fail"))

    assert breaker.is_open


@pytest.mark.asyncio
@pytest.mark.unit
async def test_circuit_breaker_open_blocks_calls() -> None:
    """Open circuit raises ServiceUnavailableError without calling func."""
    cfg = CircuitBreakerConfig(failure_threshold=1, timeout_seconds=9999.0)
    breaker = CircuitBreaker("block_test", config=cfg)

    with pytest.raises(NetworkError):
        await breaker.call(_raise, NetworkError("x"))

    spy = AsyncMock(return_value="should_not_reach")
    with pytest.raises(ServiceUnavailableError):
        await breaker.call(spy)
    spy.assert_not_awaited()


# ---------------------------------------------------------------------------
# CircuitBreaker — excluded exceptions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.unit
async def test_circuit_breaker_excluded_exception_does_not_count() -> None:
    """RateLimitError (excluded) does not increment failure count."""
    cfg = CircuitBreakerConfig(failure_threshold=2, timeout_seconds=9999.0)
    breaker = CircuitBreaker("excluded_test", config=cfg)

    for _ in range(5):
        with pytest.raises(RateLimitError):
            await breaker.call(_raise, RateLimitError("rate"))

    assert breaker.is_closed
    assert breaker.get_stats().failure_count == 0


# ---------------------------------------------------------------------------
# CircuitBreaker — HALF_OPEN transition
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.unit
async def test_circuit_breaker_half_open_to_closed_on_success() -> None:
    """After timeout, successful calls in HALF_OPEN state close the circuit."""
    cfg = CircuitBreakerConfig(
        failure_threshold=1,
        success_threshold=2,
        timeout_seconds=0.0,
    )
    breaker = CircuitBreaker("halfopen_close", config=cfg)

    with pytest.raises(NetworkError):
        await breaker.call(_raise, NetworkError("x"))

    assert breaker.is_open

    # First success → still half-open
    result = await breaker.call(_ok)
    assert result == "ok"

    # Second success → closed
    await breaker.call(_ok)
    assert breaker.is_closed


@pytest.mark.asyncio
@pytest.mark.unit
async def test_circuit_breaker_half_open_reopens_on_failure() -> None:
    """Failure in HALF_OPEN returns circuit to OPEN."""
    cfg = CircuitBreakerConfig(
        failure_threshold=1,
        success_threshold=5,
        timeout_seconds=0.0,
    )
    breaker = CircuitBreaker("halfopen_reopen", config=cfg)

    with pytest.raises(NetworkError):
        await breaker.call(_raise, NetworkError("x"))

    assert breaker.is_open

    with pytest.raises(NetworkError):
        await breaker.call(_raise, NetworkError("y"))

    assert breaker.is_open


# ---------------------------------------------------------------------------
# CircuitBreaker — reset
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_circuit_breaker_reset_clears_state() -> None:
    """Manual reset returns circuit to initial CLOSED state."""
    cfg = CircuitBreakerConfig(failure_threshold=1)
    breaker = CircuitBreaker("reset_test", config=cfg)
    breaker._stats.state = CircuitState.OPEN
    breaker._stats.failure_count = 10
    breaker.reset()
    assert breaker.is_closed
    assert breaker.get_stats().failure_count == 0


# ---------------------------------------------------------------------------
# RetryConfig defaults
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_retry_config_defaults() -> None:
    """Default retry config has 3 attempts and NetworkError retryable."""
    cfg = RetryConfig()
    assert cfg.max_attempts == 3
    assert NetworkError in cfg.retryable_exceptions


# ---------------------------------------------------------------------------
# RetryStrategy — success on first attempt
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.unit
async def test_retry_strategy_success_first_attempt() -> None:
    """No retries needed when function succeeds on first call."""
    calls = 0

    async def func() -> int:
        nonlocal calls
        calls += 1
        return 42

    strategy = RetryStrategy()
    result = await strategy.execute(func)
    assert result == 42
    assert calls == 1


# ---------------------------------------------------------------------------
# RetryStrategy — retries on retryable exception
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.unit
async def test_retry_strategy_retries_on_network_error() -> None:
    """NetworkError triggers retries up to max_attempts."""
    cfg = RetryConfig(max_attempts=3, initial_delay=0.0, jitter=False)
    calls = 0

    async def flaky() -> str:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise NetworkError("flaky")
        return "recovered"

    strategy = RetryStrategy(cfg)
    result = await strategy.execute(flaky)
    assert result == "recovered"
    assert calls == 3


@pytest.mark.asyncio
@pytest.mark.unit
async def test_retry_strategy_raises_after_max_attempts() -> None:
    """Raises last exception when all retries exhausted."""
    cfg = RetryConfig(max_attempts=2, initial_delay=0.0, jitter=False)

    strategy = RetryStrategy(cfg)
    with pytest.raises(NetworkError):
        await strategy.execute(_raise, NetworkError("persistent"))


# ---------------------------------------------------------------------------
# RetryStrategy — non-retryable exception is re-raised immediately
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.unit
async def test_retry_strategy_non_retryable_raises_immediately() -> None:
    """ValueError (non-retryable) is raised without retrying."""
    cfg = RetryConfig(max_attempts=5, initial_delay=0.0, jitter=False)
    calls = 0

    async def boom() -> None:
        nonlocal calls
        calls += 1
        raise ValueError("not retryable")

    strategy = RetryStrategy(cfg)
    with pytest.raises(ValueError):
        await strategy.execute(boom)
    assert calls == 1


# ---------------------------------------------------------------------------
# RetryStrategy — delay calculation
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_retry_calculate_delay_exponential() -> None:
    """Delay grows exponentially and is capped at max_delay."""
    cfg = RetryConfig(
        initial_delay=1.0,
        exponential_base=2.0,
        max_delay=5.0,
        jitter=False,
    )
    strategy = RetryStrategy(cfg)
    assert strategy._calculate_delay(0) == pytest.approx(1.0)
    assert strategy._calculate_delay(1) == pytest.approx(2.0)
    assert strategy._calculate_delay(2) == pytest.approx(4.0)
    assert strategy._calculate_delay(3) == pytest.approx(5.0)  # capped


@pytest.mark.unit
def test_retry_calculate_delay_with_jitter_range() -> None:
    """Jitter keeps delay within expected bounds."""
    cfg = RetryConfig(
        initial_delay=10.0,
        exponential_base=1.0,  # constant base
        max_delay=100.0,
        jitter=0.1,  # 10%
    )
    strategy = RetryStrategy(cfg)
    # Run several times to verify bounds
    for _ in range(20):
        d = strategy._calculate_delay(0)
        assert 9.0 <= d <= 11.0


# ---------------------------------------------------------------------------
# FallbackStrategy — default value
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.unit
async def test_fallback_returns_default_on_failure() -> None:
    """Returns default_value when primary function raises."""
    fallback = FallbackStrategy(default_value={"empty": True})
    result = await fallback.execute_with_fallback(_raise, RuntimeError("x"))
    assert result == {"empty": True}


@pytest.mark.asyncio
@pytest.mark.unit
async def test_fallback_returns_primary_on_success() -> None:
    """Returns primary function result when it succeeds."""
    fallback = FallbackStrategy(default_value="default")
    result = await fallback.execute_with_fallback(_ok)
    assert result == "ok"


# ---------------------------------------------------------------------------
# FallbackStrategy — fallback_func
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.unit
async def test_fallback_calls_fallback_func_on_primary_failure() -> None:
    """Calls fallback_func when primary raises and fallback_func is set."""
    fallback_called = False

    async def _secondary(*_: object, **__: object) -> str:
        nonlocal fallback_called
        fallback_called = True
        return "secondary"

    fallback = FallbackStrategy(fallback_func=_secondary)
    result = await fallback.execute_with_fallback(_raise, RuntimeError("x"))
    assert result == "secondary"
    assert fallback_called


@pytest.mark.asyncio
@pytest.mark.unit
async def test_fallback_uses_default_when_fallback_func_also_fails() -> None:
    """Returns default_value when both primary and fallback_func fail."""

    async def _bad_secondary(*_: object, **__: object) -> str:
        raise RuntimeError("secondary also failed")

    fallback = FallbackStrategy(
        default_value="final_fallback",
        fallback_func=_bad_secondary,
    )
    result = await fallback.execute_with_fallback(_raise, RuntimeError("primary"))
    assert result == "final_fallback"


# ---------------------------------------------------------------------------
# ResilienceManager
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.unit
async def test_resilience_manager_execute_success() -> None:
    """ResilienceManager.execute_with_resilience returns function result."""
    manager = ResilienceManager()
    result = await manager.execute_with_resilience(_ok)
    assert result == "ok"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_resilience_manager_with_circuit_breaker_name() -> None:
    """ResilienceManager uses named circuit breaker when provided."""
    manager = ResilienceManager()
    result = await manager.execute_with_resilience(
        _ok, circuit_breaker_name="mgr_test_cb"
    )
    assert result == "ok"
    # Circuit breaker was created in the registry
    breakers = get_all_circuit_breakers()
    assert "mgr_test_cb" in breakers


# ---------------------------------------------------------------------------
# Global registry helpers
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_get_circuit_breaker_returns_same_instance() -> None:
    """get_circuit_breaker returns the same instance for same name."""
    b1 = get_circuit_breaker("registry_same")
    b2 = get_circuit_breaker("registry_same")
    assert b1 is b2


@pytest.mark.unit
def test_reset_all_circuit_breakers() -> None:
    """reset_all_circuit_breakers resets all registered breakers."""
    b = get_circuit_breaker("reset_all_test")
    b._stats.state = CircuitState.OPEN
    b._stats.failure_count = 99

    reset_all_circuit_breakers()

    assert b.is_closed
    assert b.get_stats().failure_count == 0


@pytest.mark.unit
def test_get_all_circuit_breakers_returns_dict_copy() -> None:
    """get_all_circuit_breakers returns a copy (mutations don't affect registry)."""
    get_circuit_breaker("get_all_test")
    all_breakers = get_all_circuit_breakers()
    assert isinstance(all_breakers, dict)
    all_breakers.clear()  # Mutate the copy
    # Original registry still has the entry
    assert "get_all_test" in get_all_circuit_breakers()


# ---------------------------------------------------------------------------
# Decorators
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.unit
async def test_with_circuit_breaker_decorator() -> None:
    """with_circuit_breaker wraps a function with circuit breaker protection."""

    @with_circuit_breaker("dec_cb_test")
    async def my_func() -> str:
        return "decorated_ok"

    result = await my_func()
    assert result == "decorated_ok"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_with_retry_decorator_retries() -> None:
    """with_retry decorator retries on NetworkError."""
    calls = 0

    @with_retry(RetryConfig(max_attempts=3, initial_delay=0.0, jitter=False))
    async def flaky_decorated() -> str:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise NetworkError("retry me")
        return "done"

    result = await flaky_decorated()
    assert result == "done"
    assert calls == 3


@pytest.mark.asyncio
@pytest.mark.unit
async def test_with_fallback_decorator_returns_default() -> None:
    """with_fallback decorator returns default_value on failure."""

    @with_fallback(default_value="fallback_value")
    async def always_fails() -> str:
        raise RuntimeError("boom")

    result = await always_fails()
    assert result == "fallback_value"
