"""Unit tests for resilience helpers."""

import pytest

from custom_components.pawcontrol import resilience
from custom_components.pawcontrol.exceptions import (
    NetworkError,
    RateLimitError,
    ServiceUnavailableError,
)


@pytest.fixture(autouse=True)
def clear_registry() -> None:  # noqa: D103
    resilience._circuit_breakers.clear()


@pytest.mark.asyncio
async def test_circuit_breaker_opens_and_recovers(  # noqa: D103
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    breaker = resilience.CircuitBreaker(
        "api",
        config=resilience.CircuitBreakerConfig(
            failure_threshold=2,
            success_threshold=1,
            timeout_seconds=10,
        ),
    )

    async def fail() -> None:
        raise NetworkError("down")

    for _ in range(2):
        with pytest.raises(NetworkError):
            await breaker.call(fail)

    assert breaker.is_open is True

    with pytest.raises(ServiceUnavailableError, match="OPEN"):
        await breaker.call(fail)

    monkeypatch.setattr(resilience.time, "time", lambda: 11.0)
    breaker.get_stats().last_failure_time = 0.0

    async def ok() -> str:
        return "ok"

    assert await breaker.call(ok) == "ok"
    assert breaker.is_closed is True


@pytest.mark.asyncio
async def test_circuit_breaker_excludes_configured_exception() -> None:  # noqa: D103
    breaker = resilience.CircuitBreaker("api")

    async def limited() -> None:
        raise RateLimitError("later")

    with pytest.raises(RateLimitError):
        await breaker.call(limited)

    stats = breaker.get_stats()
    assert stats.total_calls == 1
    assert stats.total_failures == 0
    assert stats.failure_count == 0


@pytest.mark.asyncio
async def test_circuit_breaker_context_manager_records_results() -> None:  # noqa: D103
    breaker = resilience.CircuitBreaker(
        "ctx",
        config=resilience.CircuitBreakerConfig(failure_threshold=1),
    )

    async with breaker:
        pass

    with pytest.raises(NetworkError):
        async with breaker:
            raise NetworkError("boom")

    assert breaker.is_open is True


@pytest.mark.asyncio
async def test_retry_strategy_retries_and_computes_delay(  # noqa: D103
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    strategy = resilience.RetryStrategy(
        resilience.RetryConfig(max_attempts=3, initial_delay=1, jitter=False)
    )
    attempts = 0
    sleeps: list[float] = []

    async def sometimes() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise NetworkError("retry")
        return "done"

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr(resilience.asyncio, "sleep", fake_sleep)

    assert await strategy.execute(sometimes) == "done"
    assert attempts == 3
    assert sleeps == [1.0, 2.0]


@pytest.mark.asyncio
async def test_retry_strategy_non_retryable_exception_bubbles() -> None:  # noqa: D103
    strategy = resilience.RetryStrategy()

    async def bad() -> None:
        raise ValueError("no retry")

    with pytest.raises(ValueError, match="no retry"):
        await strategy.execute(bad)


def test_retry_calculate_delay_applies_float_jitter(  # noqa: D103
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    strategy = resilience.RetryStrategy(
        resilience.RetryConfig(initial_delay=10, max_delay=10, jitter=0.2)
    )
    monkeypatch.setattr(resilience._SECURE_RANDOM, "uniform", lambda low, high: high)

    assert strategy._calculate_delay(0) == 12.0


@pytest.mark.asyncio
async def test_fallback_strategy_uses_fallback_then_default() -> None:  # noqa: D103
    async def main_fail() -> None:
        raise RuntimeError("main")

    async def backup() -> str:
        return "fallback"

    strategy = resilience.FallbackStrategy(
        default_value="default", fallback_func=backup
    )
    assert await strategy.execute_with_fallback(main_fail) == "fallback"

    async def backup_fail() -> None:
        raise RuntimeError("backup")

    strategy = resilience.FallbackStrategy(
        default_value="default",
        fallback_func=backup_fail,
    )
    assert await strategy.execute_with_fallback(main_fail) == "default"


@pytest.mark.asyncio
async def test_resilience_manager_uses_registry_breaker(  # noqa: D103
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = resilience.ResilienceManager()
    created: list[str] = []

    def fake_get(
        name: str, *, config: resilience.CircuitBreakerConfig | None = None
    ) -> resilience.CircuitBreaker:
        created.append(name)
        return resilience.CircuitBreaker(name, config=config)

    monkeypatch.setattr(resilience, "get_circuit_breaker", fake_get)

    async def echo(value: str) -> str:
        return value

    result = await manager.execute_with_resilience(
        echo, "ok", circuit_breaker_name="svc"
    )
    assert result == "ok"
    assert created == ["svc"]


@pytest.mark.asyncio
async def test_resilience_manager_without_breaker_uses_retry() -> None:  # noqa: D103
    manager = resilience.ResilienceManager()

    async def echo(value: str) -> str:
        return value

    assert await manager.execute_with_resilience(echo, "v") == "v"


def test_registry_helpers_reuse_breakers() -> None:  # noqa: D103
    first = resilience.get_circuit_breaker("name")
    second = resilience.get_circuit_breaker("name")

    all_breakers = resilience.get_all_circuit_breakers()
    assert first is second
    assert all_breakers["name"] is first

    first.reset()
    stats = first.get_stats().to_dict()
    assert stats["state"] == resilience.CircuitState.CLOSED.value


@pytest.mark.asyncio
async def test_circuit_breaker_half_open_failure_reopens() -> None:  # noqa: D103
    breaker = resilience.CircuitBreaker(
        "recover",
        config=resilience.CircuitBreakerConfig(failure_threshold=1, timeout_seconds=1),
    )

    async def fail() -> None:
        raise NetworkError("boom")

    with pytest.raises(NetworkError):
        await breaker.call(fail)

    breaker.get_stats().last_failure_time = 0.0
    async with breaker:
        pass

    assert breaker.is_half_open is True
    assert breaker.name == "recover"
    assert breaker.state == resilience.CircuitState.HALF_OPEN

    with pytest.raises(NetworkError):
        await breaker.call(fail)

    assert breaker.is_open is True


def test_reset_all_circuit_breakers_resets_state() -> None:  # noqa: D103
    breaker = resilience.get_circuit_breaker("bulk")
    breaker.get_stats().state = resilience.CircuitState.OPEN

    resilience.reset_all_circuit_breakers()

    assert breaker.state == resilience.CircuitState.CLOSED


@pytest.mark.asyncio
async def test_resilience_decorators_apply_wrappers() -> None:  # noqa: D103
    @resilience.with_circuit_breaker("decorator")
    async def guarded(value: str) -> str:
        return value

    @resilience.with_retry(resilience.RetryConfig(max_attempts=1))
    async def retried(value: str) -> str:
        return value

    @resilience.with_fallback(default_value="default")
    async def fallback_fail() -> str:
        raise RuntimeError("nope")

    assert await guarded("ok") == "ok"
    assert await retried("ok") == "ok"
    assert await fallback_fail() == "default"


@pytest.mark.asyncio
async def test_retry_strategy_zero_attempts_raises_runtime_error() -> None:  # noqa: D103
    strategy = resilience.RetryStrategy(resilience.RetryConfig(max_attempts=0))

    async def should_not_run() -> None:
        raise AssertionError("should not run")

    with pytest.raises(RuntimeError, match="failed unexpectedly"):
        await strategy.execute(should_not_run)


@pytest.mark.asyncio
async def test_circuit_breaker_enter_blocks_when_open_without_reset() -> None:  # noqa: D103
    breaker = resilience.CircuitBreaker("blocked")
    stats = breaker.get_stats()
    stats.state = resilience.CircuitState.OPEN
    stats.last_failure_time = resilience.time.time()

    with pytest.raises(ServiceUnavailableError, match="OPEN"):
        async with breaker:
            pytest.fail("context should not be entered")


def test_circuit_breaker_should_attempt_reset_when_no_failure_time() -> None:  # noqa: D103
    breaker = resilience.CircuitBreaker("fresh")
    assert breaker._should_attempt_reset() is True


@pytest.mark.asyncio
async def test_retry_strategy_raises_on_last_retryable_attempt() -> None:  # noqa: D103
    strategy = resilience.RetryStrategy(resilience.RetryConfig(max_attempts=1))

    async def always_fail() -> None:
        raise NetworkError("still down")

    with pytest.raises(NetworkError, match="still down"):
        await strategy.execute(always_fail)
