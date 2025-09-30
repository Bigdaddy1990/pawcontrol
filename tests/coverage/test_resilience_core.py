"""Focused coverage tests for the resilience utilities.

These tests exercise the circuit breaker, retry helper and manager coordination
without relying on the full Home Assistant runtime.  Lightweight stubs provide
just enough surface area for the integration code to run, making the suite
suitable for resource constrained CI environments.
"""

from __future__ import annotations

import asyncio
import importlib.machinery
import importlib.util
import pathlib
import sys
import types
from collections.abc import Callable
from unittest.mock import AsyncMock

import pytest

# ---------------------------------------------------------------------------
# Minimal Home Assistant and package stubs (only what the module requires)
# ---------------------------------------------------------------------------
if "homeassistant" not in sys.modules:
    sys.modules["homeassistant"] = types.ModuleType("homeassistant")

homeassistant = sys.modules["homeassistant"]

if not hasattr(homeassistant, "exceptions"):
    exceptions_module = types.ModuleType("homeassistant.exceptions")

    class HomeAssistantError(Exception):
        """Lightweight drop-in replacement used for testing."""

    exceptions_module.HomeAssistantError = HomeAssistantError
    HomeAssistantError = exceptions_module.HomeAssistantError
    sys.modules["homeassistant.exceptions"] = exceptions_module
    homeassistant.exceptions = exceptions_module
else:  # pragma: no cover - executed only when real HA is installed
    HomeAssistantError = homeassistant.exceptions.HomeAssistantError

if not hasattr(homeassistant, "core"):
    core_module = types.ModuleType("homeassistant.core")

    class HomeAssistant:  # pragma: no cover - simple attribute container
        pass

    core_module.HomeAssistant = HomeAssistant
    sys.modules["homeassistant.core"] = core_module
    homeassistant.core = core_module

if "custom_components" not in sys.modules:
    custom_components_pkg = types.ModuleType("custom_components")
    custom_components_pkg.__path__ = []  # type: ignore[attr-defined]
    sys.modules["custom_components"] = custom_components_pkg
else:  # pragma: no cover - executed when package already present
    custom_components_pkg = sys.modules["custom_components"]

if "custom_components.pawcontrol" not in sys.modules:
    pawcontrol_pkg = types.ModuleType("custom_components.pawcontrol")
    pawcontrol_pkg.__path__ = []  # type: ignore[attr-defined]
    sys.modules["custom_components.pawcontrol"] = pawcontrol_pkg
else:  # pragma: no cover - executed when package already present
    pawcontrol_pkg = sys.modules["custom_components.pawcontrol"]

custom_components_pkg.pawcontrol = pawcontrol_pkg

module_name = "custom_components.pawcontrol.resilience"
module_path = (
    pathlib.Path(__file__).resolve().parents[2]
    / "custom_components"
    / "pawcontrol"
    / "resilience.py"
)

loader = importlib.machinery.SourceFileLoader(module_name, str(module_path))
spec = importlib.util.spec_from_loader(module_name, loader)
assert spec is not None and spec.loader is not None
resilience = importlib.util.module_from_spec(spec)
sys.modules[module_name] = resilience
loader.exec_module(resilience)
pawcontrol_pkg.resilience = resilience

CircuitBreaker = resilience.CircuitBreaker
CircuitBreakerConfig = resilience.CircuitBreakerConfig
CircuitState = resilience.CircuitState
ResilienceManager = resilience.ResilienceManager
RetryConfig = resilience.RetryConfig
RetryExhaustedError = resilience.RetryExhaustedError
retry_with_backoff = resilience.retry_with_backoff


@pytest.fixture()
def fake_time(monkeypatch: pytest.MonkeyPatch) -> Callable[[float], None]:
    """Provide controllable monotonic time for deterministic tests."""

    timeline = {"value": 0.0}

    def monotonic() -> float:
        return timeline["value"]

    def advance(seconds: float) -> None:
        timeline["value"] += seconds

    monkeypatch.setattr(
        "custom_components.pawcontrol.resilience.time.monotonic",
        monotonic,
    )
    return advance


@pytest.fixture()
def fast_sleep(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Patch ``asyncio.sleep`` to avoid real delays and capture durations."""

    recorded: list[float] = []

    async def _sleep(duration: float) -> None:  # pragma: no cover - trivial wrapper
        recorded.append(duration)

    monkeypatch.setattr(
        "custom_components.pawcontrol.resilience.asyncio.sleep",
        _sleep,
    )
    return recorded


def test_circuit_breaker_open_and_recover(fake_time: Callable[[float], None]) -> None:
    """Circuit breaker opens after failures and closes after successful reset."""

    async def scenario() -> None:
        breaker = CircuitBreaker(
            "sensor_api",
            CircuitBreakerConfig(
                failure_threshold=2, success_threshold=1, timeout_seconds=30.0
            ),
        )

        async def failing() -> None:
            raise ValueError("boom")

        async def succeed() -> str:
            return "ok"

        # Trigger two failures to open the circuit
        for _ in range(2):
            with pytest.raises(ValueError):
                await breaker.call(failing)

        assert breaker.state is CircuitState.OPEN

        # Additional call while open should be rejected immediately
        with pytest.raises(HomeAssistantError):
            await breaker.call(failing)

        # Advance time to allow half-open transition and verify it closes again
        fake_time(31.0)
        result = await breaker.call(succeed)
        assert result == "ok"
        assert breaker.state is CircuitState.CLOSED

    asyncio.run(scenario())


def test_circuit_breaker_half_open_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    """Half-open state enforces concurrent call limit and re-opens on failure."""

    async def scenario() -> None:
        config = CircuitBreakerConfig(
            failure_threshold=1,
            success_threshold=2,
            half_open_max_calls=1,
            timeout_seconds=5.0,
        )
        breaker = CircuitBreaker("limited", config)

        async def failing() -> None:
            raise RuntimeError("nope")

        # First failure opens the circuit immediately
        with pytest.raises(RuntimeError):
            await breaker.call(failing)

        assert breaker.state is CircuitState.OPEN

        # Force half-open state and simulate one call in flight
        breaker._stats.state = CircuitState.HALF_OPEN  # type: ignore[attr-defined]
        breaker._half_open_calls = config.half_open_max_calls  # type: ignore[attr-defined]

        with pytest.raises(HomeAssistantError, match="max concurrent calls"):
            await breaker.call(failing)

        # Allow a single call in half-open and ensure a failure re-opens the circuit
        breaker._half_open_calls = 0  # type: ignore[attr-defined]
        with pytest.raises(RuntimeError):
            await breaker.call(failing)

        assert breaker.state is CircuitState.OPEN

    asyncio.run(scenario())


def test_circuit_breaker_half_open_cleanup() -> None:
    """Successful calls in half-open decrement in-flight counter."""

    async def scenario() -> None:
        config = CircuitBreakerConfig(success_threshold=3, half_open_max_calls=2)
        breaker = CircuitBreaker("cleanup", config)

        breaker._stats.state = CircuitState.HALF_OPEN  # type: ignore[attr-defined]
        breaker._stats.success_count = 0  # type: ignore[attr-defined]
        breaker._half_open_calls = 1  # type: ignore[attr-defined]

        async def succeed() -> str:
            return "ok"

        result = await breaker.call(succeed)
        assert result == "ok"
        assert breaker.stats.state is CircuitState.HALF_OPEN
        assert breaker._half_open_calls == 1  # type: ignore[attr-defined]

    asyncio.run(scenario())


def test_retry_with_backoff_success_and_failure(
    fast_sleep: list[float], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Retry helper handles successes, jitter and exhausted attempts."""

    async def scenario() -> None:
        # Deterministic jitter
        monkeypatch.setattr("random.random", lambda: 0.5)

        # Succeeds on second attempt
        flakey = AsyncMock(side_effect=[ValueError("fail"), "good"])
        result = await retry_with_backoff(
            flakey,
            config=RetryConfig(
                max_attempts=3, initial_delay=0.1, exponential_base=2.0, jitter=True
            ),
        )
        assert result == "good"
        assert flakey.call_count == 2
        assert pytest.approx(fast_sleep[0], rel=0.01) == 0.1

        # Always failing case should raise after exhausting retries
        fast_sleep.clear()
        always_fail = AsyncMock(side_effect=RuntimeError("still bad"))
        with pytest.raises(RetryExhaustedError) as exc:
            await retry_with_backoff(
                always_fail,
                config=RetryConfig(
                    max_attempts=3,
                    initial_delay=0.2,
                    exponential_base=3.0,
                    max_delay=0.5,
                    jitter=False,
                ),
            )
        assert exc.value.attempts == 3
        assert always_fail.call_count == 3
        # Expected sleeps: min(0.2, 0.5) + min(0.6, 0.5) = 0.2 + 0.5
        assert fast_sleep == pytest.approx([0.2, 0.5])

    asyncio.run(scenario())


def test_retry_with_backoff_immediate_success(fast_sleep: list[float]) -> None:
    """Immediate success returns without retries."""

    async def scenario() -> None:
        async def succeed() -> str:
            return "instant"

        result = await retry_with_backoff(succeed, config=RetryConfig(max_attempts=3))
        assert result == "instant"
        assert fast_sleep == []

    asyncio.run(scenario())


def test_retry_with_backoff_logs_subsequent_success(
    fast_sleep: list[float], caplog: pytest.LogCaptureFixture
) -> None:
    """Second attempt success logs the retry outcome."""

    async def scenario() -> None:
        flakey = AsyncMock(side_effect=[RuntimeError("boom"), "done"])

        with caplog.at_level("INFO"):
            result = await retry_with_backoff(
                flakey,
                config=RetryConfig(max_attempts=3, initial_delay=0.01, jitter=False),
            )

        assert result == "done"
        assert any(
            "Retry succeeded on attempt" in message for message in caplog.messages
        )
        assert fast_sleep == pytest.approx([0.01])

    asyncio.run(scenario())


def test_resilience_manager_coordinates_retry(
    fake_time: Callable[[float], None], fast_sleep: list[float]
) -> None:
    """Manager combines circuit breaker and retry logic when requested."""

    async def scenario() -> None:
        hass = homeassistant.core.HomeAssistant()  # type: ignore[attr-defined]
        manager = ResilienceManager(hass)

        flakey = AsyncMock(side_effect=[ValueError("nope"), "done"])

        result = await manager.execute_with_resilience(
            flakey,
            circuit_breaker_name="api",
            retry_config=RetryConfig(max_attempts=2, initial_delay=0.01, jitter=False),
        )

        assert result == "done"
        assert flakey.call_count == 2

        stats = manager.get_all_circuit_breakers()
        assert "api" in stats
        assert stats["api"].total_calls == 2

        # Reset specific and all breakers
        assert await manager.reset_circuit_breaker("api") is True
        assert await manager.reset_circuit_breaker("missing") is False

        await manager.get_circuit_breaker("secondary")
        assert await manager.reset_all_circuit_breakers() == 2

    asyncio.run(scenario())
    assert fast_sleep == pytest.approx([0.01])


def test_retry_with_backoff_propagates_last_error() -> None:
    """Ensure synchronous failures propagate cleanly through the helper."""

    async def scenario() -> None:
        async def raises() -> None:
            raise KeyError("broken")

        with pytest.raises(RetryExhaustedError) as exc:
            await retry_with_backoff(
                raises,
                config=RetryConfig(max_attempts=1, initial_delay=0.01, jitter=False),
            )
        assert isinstance(exc.value.last_error, KeyError)

    asyncio.run(scenario())


def test_retry_with_backoff_invalid_attempts() -> None:
    """Zero attempts configuration raises a HomeAssistantError."""

    async def scenario() -> None:
        async def failing() -> None:
            raise RuntimeError("nope")

        with pytest.raises(HomeAssistantError):
            await retry_with_backoff(failing, config=RetryConfig(max_attempts=0))

    asyncio.run(scenario())


def test_record_success_resets_failure_count() -> None:
    """Closed-state success clears accumulated failures."""

    async def scenario() -> None:
        breaker = CircuitBreaker("reset")
        breaker._stats.state = CircuitState.CLOSED  # type: ignore[attr-defined]
        breaker._stats.failure_count = 5  # type: ignore[attr-defined]
        await breaker._record_success()
        assert breaker.stats.failure_count == 0

    asyncio.run(scenario())


def test_record_success_noop_while_open() -> None:
    """Calling record_success in OPEN state leaves counters untouched."""

    async def scenario() -> None:
        breaker = CircuitBreaker("open")
        breaker._stats.state = CircuitState.OPEN  # type: ignore[attr-defined]
        breaker._stats.failure_count = 3  # type: ignore[attr-defined]

        await breaker._record_success()

        assert breaker.stats.state is CircuitState.OPEN
        assert breaker.stats.failure_count == 3

    asyncio.run(scenario())


def test_half_open_success_requires_threshold() -> None:
    """Half-open circuits stay half-open until the success threshold is met."""

    async def scenario() -> None:
        breaker = CircuitBreaker(
            "half-open-threshold",
            CircuitBreakerConfig(success_threshold=2, half_open_max_calls=1),
        )
        breaker._stats.state = CircuitState.HALF_OPEN  # type: ignore[attr-defined]
        breaker._stats.success_count = 0  # type: ignore[attr-defined]

        await breaker._record_success()

        assert breaker.stats.state is CircuitState.HALF_OPEN
        assert breaker.stats.success_count == 1

    asyncio.run(scenario())


def test_should_attempt_reset_without_failure() -> None:
    """Reset checks return true when no failures recorded."""

    breaker = CircuitBreaker("fresh")
    assert breaker._should_attempt_reset() is True


def test_resilience_manager_direct_execution(fast_sleep: list[float]) -> None:
    """Manager executes function without circuit breaker or retry."""

    async def scenario() -> None:
        hass = homeassistant.core.HomeAssistant()  # type: ignore[attr-defined]
        manager = ResilienceManager(hass)

        async def pure() -> str:
            return "direct"

        result = await manager.execute_with_resilience(pure)
        assert result == "direct"

        first = await manager.get_circuit_breaker("existing")
        second = await manager.get_circuit_breaker("existing")
        assert first is second

        # No retry configuration -> no sleeps should be recorded
        assert fast_sleep == []

    asyncio.run(scenario())
