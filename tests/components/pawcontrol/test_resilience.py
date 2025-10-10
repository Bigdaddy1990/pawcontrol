"""Tests for resilience module.

Comprehensive tests for circuit breaker, retry logic, and resilience manager.

Quality Scale: Bronze target
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest
from custom_components.pawcontrol.resilience import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
    ResilienceManager,
    RetryConfig,
    RetryExhaustedError,
    retry_with_backoff,
)
from homeassistant.exceptions import HomeAssistantError


class TestCircuitBreaker:
    """Tests for CircuitBreaker class."""

    async def test_circuit_breaker_normal_operation(self) -> None:
        """Test circuit breaker in normal operation."""
        breaker = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=3))

        async def successful_func() -> str:
            return "success"

        result = await breaker.call(successful_func)
        assert result == "success"
        assert breaker.state == CircuitState.CLOSED
        assert breaker.stats.total_calls == 1
        assert breaker.stats.total_successes == 1

    async def test_circuit_breaker_opens_on_failures(self) -> None:
        """Test circuit breaker opens after threshold failures."""
        breaker = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=3))

        async def failing_func() -> None:
            raise ValueError("Test failure")

        # First 3 failures should be allowed
        for _i in range(3):
            with pytest.raises(ValueError):
                await breaker.call(failing_func)

        assert breaker.state == CircuitState.OPEN
        assert breaker.stats.total_failures == 3

        # Next call should be rejected without executing function
        with pytest.raises(
            HomeAssistantError,
            match=r"Circuit breaker 'test' is OPEN - calls rejected",
        ):
            await breaker.call(failing_func)

        # Total failures should still be 3 (function not executed)
        assert breaker.stats.total_failures == 3

    async def test_circuit_breaker_half_open_recovery(self) -> None:
        """Test circuit breaker recovery through half-open state."""
        config = CircuitBreakerConfig(
            failure_threshold=2,
            success_threshold=2,
            timeout_seconds=0.1,
        )
        breaker = CircuitBreaker("test", config)

        async def failing_func() -> None:
            raise ValueError("Test failure")

        async def successful_func() -> str:
            return "success"

        # Open the circuit
        for _ in range(2):
            with pytest.raises(ValueError):
                await breaker.call(failing_func)

        assert breaker.state == CircuitState.OPEN

        # Wait for timeout
        await asyncio.sleep(0.15)

        # First call after timeout should work (half-open)
        result = await breaker.call(successful_func)
        assert result == "success"
        assert breaker.state == CircuitState.HALF_OPEN

        # Second successful call should close circuit
        result = await breaker.call(successful_func)
        assert result == "success"
        assert breaker.state == CircuitState.CLOSED

    async def test_circuit_breaker_half_open_reopens_on_failure(self) -> None:
        """Test circuit breaker reopens if failure occurs in half-open state."""
        config = CircuitBreakerConfig(
            failure_threshold=2,
            timeout_seconds=0.1,
        )
        breaker = CircuitBreaker("test", config)

        async def failing_func() -> None:
            raise ValueError("Test failure")

        # Open the circuit
        for _ in range(2):
            with pytest.raises(ValueError):
                await breaker.call(failing_func)

        assert breaker.state == CircuitState.OPEN

        # Wait for timeout
        await asyncio.sleep(0.15)

        # Failure in half-open immediately reopens
        with pytest.raises(ValueError):
            await breaker.call(failing_func)

        assert breaker.state == CircuitState.OPEN

    async def test_circuit_breaker_manual_reset(self) -> None:
        """Test manual circuit breaker reset."""
        breaker = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=2))

        async def failing_func() -> None:
            raise ValueError("Test failure")

        # Open the circuit
        for _ in range(2):
            with pytest.raises(ValueError):
                await breaker.call(failing_func)

        assert breaker.state == CircuitState.OPEN

        # Manual reset
        await breaker.reset()
        assert breaker.state == CircuitState.CLOSED

    async def test_circuit_breaker_statistics(self) -> None:
        """Test circuit breaker statistics tracking."""
        breaker = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=5))

        async def successful_func() -> str:
            return "success"

        async def failing_func() -> None:
            raise ValueError("Test failure")

        # Execute some successful calls
        for _ in range(3):
            await breaker.call(successful_func)

        # Execute some failures
        for _ in range(2):
            with pytest.raises(ValueError):
                await breaker.call(failing_func)

        stats = breaker.stats
        assert stats.total_calls == 5
        assert stats.total_successes == 3
        assert stats.total_failures == 2
        assert stats.state == CircuitState.CLOSED
        assert stats.last_success_time is not None
        assert stats.last_failure_time is not None
        now = time.time()
        assert abs(stats.last_success_time - now) < 5
        assert abs(stats.last_failure_time - now) < 5

    async def test_circuit_breaker_records_timestamps(self) -> None:
        """Circuit breaker should capture epoch timestamps for telemetry."""

        config = CircuitBreakerConfig(
            failure_threshold=1,
            timeout_seconds=0.05,
            success_threshold=2,
        )
        breaker = CircuitBreaker("timestamp", config)

        async def failing() -> None:
            raise ValueError("boom")

        async def succeeding() -> str:
            return "ok"

        with pytest.raises(ValueError):
            await breaker.call(failing)

        failure_snapshot = breaker.stats.last_failure_time
        assert failure_snapshot is not None
        assert abs(failure_snapshot - time.time()) < 5

        await asyncio.sleep(0.06)

        assert breaker.state is CircuitState.OPEN

        # Two successful calls transition HALF_OPEN -> CLOSED
        assert await breaker.call(succeeding) == "ok"
        assert breaker.state is CircuitState.HALF_OPEN
        assert await breaker.call(succeeding) == "ok"
        assert breaker.state is CircuitState.CLOSED

        success_snapshot = breaker.stats.last_success_time
        assert success_snapshot is not None
        assert abs(success_snapshot - time.time()) < 5
        assert success_snapshot >= failure_snapshot


class TestRetryLogic:
    """Tests for retry with backoff functionality."""

    async def test_retry_succeeds_immediately(self) -> None:
        """Test retry when function succeeds on first attempt."""
        mock_func = AsyncMock(return_value="success")

        result = await retry_with_backoff(mock_func, config=RetryConfig(max_attempts=3))

        assert result == "success"
        assert mock_func.call_count == 1

    async def test_retry_succeeds_after_failures(self) -> None:
        """Test retry succeeds after some failures."""
        mock_func = AsyncMock(
            side_effect=[ValueError("fail1"), ValueError("fail2"), "success"]
        )

        config = RetryConfig(
            max_attempts=3,
            initial_delay=0.01,  # Fast for testing
        )

        result = await retry_with_backoff(mock_func, config=config)

        assert result == "success"
        assert mock_func.call_count == 3

    async def test_retry_exhausted(self) -> None:
        """Test retry exhausted after max attempts."""
        mock_func = AsyncMock(side_effect=ValueError("persistent failure"))

        config = RetryConfig(
            max_attempts=3,
            initial_delay=0.01,
        )

        with pytest.raises(RetryExhaustedError) as exc_info:
            await retry_with_backoff(mock_func, config=config)

        assert exc_info.value.attempts == 3
        assert mock_func.call_count == 3

    async def test_retry_exponential_backoff(self) -> None:
        """Test exponential backoff delays."""
        mock_func = AsyncMock(side_effect=ValueError("fail"))

        config = RetryConfig(
            max_attempts=3,
            initial_delay=0.1,
            exponential_base=2.0,
            jitter=False,  # Disable jitter for predictable testing
        )

        start_time = asyncio.get_event_loop().time()

        with pytest.raises(RetryExhaustedError):
            await retry_with_backoff(mock_func, config=config)

        elapsed = asyncio.get_event_loop().time() - start_time

        # Expected delays: 0.1 + 0.2 = 0.3 seconds minimum
        assert elapsed >= 0.3
        assert mock_func.call_count == 3

    async def test_retry_with_max_delay(self) -> None:
        """Test retry respects max delay cap."""
        mock_func = AsyncMock(side_effect=ValueError("fail"))

        config = RetryConfig(
            max_attempts=5,
            initial_delay=1.0,
            max_delay=2.0,  # Cap at 2 seconds
            exponential_base=2.0,
            jitter=False,
        )

        start_time = asyncio.get_event_loop().time()

        with pytest.raises(RetryExhaustedError):
            await retry_with_backoff(mock_func, config=config)

        elapsed = asyncio.get_event_loop().time() - start_time

        # Expected delays capped: 1.0 + 2.0 + 2.0 + 2.0 = 7.0 seconds
        # (without cap would be: 1.0 + 2.0 + 4.0 + 8.0 = 15.0)
        assert elapsed >= 7.0
        assert elapsed < 10.0  # Should be well under uncapped time


class TestResilienceManager:
    """Tests for ResilienceManager class."""

    async def test_resilience_manager_creates_circuit_breaker(self, hass) -> None:
        """Test resilience manager creates circuit breakers."""
        manager = ResilienceManager(hass)

        breaker = await manager.get_circuit_breaker("test")
        assert breaker.name == "test"
        assert breaker.state == CircuitState.CLOSED

        # Getting same breaker returns cached instance
        breaker2 = await manager.get_circuit_breaker("test")
        assert breaker is breaker2

    async def test_resilience_manager_execute_with_circuit_breaker(self, hass) -> None:
        """Test execute with circuit breaker protection."""
        manager = ResilienceManager(hass)

        mock_func = AsyncMock(return_value="success")

        result = await manager.execute_with_resilience(
            mock_func,
            circuit_breaker_name="test_breaker",
        )

        assert result == "success"
        assert mock_func.call_count == 1

        # Verify circuit breaker was created
        stats = manager.get_all_circuit_breakers()
        assert "test_breaker" in stats

    async def test_resilience_manager_execute_with_retry(self, hass) -> None:
        """Test execute with retry logic."""
        manager = ResilienceManager(hass)

        mock_func = AsyncMock(side_effect=[ValueError("fail"), "success"])

        config = RetryConfig(max_attempts=3, initial_delay=0.01)

        result = await manager.execute_with_resilience(
            mock_func,
            retry_config=config,
        )

        assert result == "success"
        assert mock_func.call_count == 2

    async def test_resilience_manager_combined_resilience(self, hass) -> None:
        """Test combined circuit breaker and retry logic."""
        manager = ResilienceManager(hass)

        mock_func = AsyncMock(side_effect=[ValueError("fail"), "success"])

        retry_config = RetryConfig(max_attempts=3, initial_delay=0.01)

        result = await manager.execute_with_resilience(
            mock_func,
            circuit_breaker_name="test",
            retry_config=retry_config,
        )

        assert result == "success"
        assert mock_func.call_count == 2

    async def test_resilience_manager_reset_circuit_breaker(self, hass) -> None:
        """Test manual circuit breaker reset through manager."""
        manager = ResilienceManager(hass)

        breaker = await manager.get_circuit_breaker("test")

        # Open the circuit
        async def failing_func() -> None:
            raise ValueError("fail")

        config = CircuitBreakerConfig(failure_threshold=2)
        breaker.config = config

        for _ in range(2):
            with pytest.raises(ValueError):
                await breaker.call(failing_func)

        assert breaker.state == CircuitState.OPEN

        # Reset through manager
        reset_success = await manager.reset_circuit_breaker("test")
        assert reset_success is True
        assert breaker.state == CircuitState.CLOSED

    async def test_resilience_manager_reset_all(self, hass) -> None:
        """Test reset all circuit breakers."""
        manager = ResilienceManager(hass)

        # Create multiple circuit breakers
        await manager.get_circuit_breaker("breaker1")
        await manager.get_circuit_breaker("breaker2")
        await manager.get_circuit_breaker("breaker3")

        # Reset all
        count = await manager.reset_all_circuit_breakers()
        assert count == 3


# Integration fixtures
@pytest.fixture
def hass():
    """Mock Home Assistant instance."""
    from unittest.mock import MagicMock

    mock_hass = MagicMock()
    return mock_hass
