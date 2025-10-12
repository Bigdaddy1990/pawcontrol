"""Resilience patterns for PawControl integration.

Provides circuit breaker, retry logic with exponential backoff, and graceful
degradation to ensure integration reliability even under adverse conditions.

Quality Scale: Bronze target
Home Assistant: 2025.9.0+
Python: 3.13+
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from importlib import import_module
from typing import TYPE_CHECKING, Any, TypeVar, cast

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.exceptions import HomeAssistantError as HomeAssistantErrorType
else:  # pragma: no cover - runtime fallback when Home Assistant is absent
    try:
        from homeassistant.core import HomeAssistant
    except ModuleNotFoundError:  # pragma: no cover - compatibility shim for tests

        class HomeAssistant:  # type: ignore[override]
            """Minimal stand-in used during unit tests."""

    try:
        from homeassistant.exceptions import (
            HomeAssistantError as HomeAssistantErrorType,
        )
    except ModuleNotFoundError:  # pragma: no cover - fallback to compat shim
        from .compat import HomeAssistantError as HomeAssistantErrorType


try:
    from homeassistant.util import dt as dt_util
except ModuleNotFoundError:  # pragma: no cover - compatibility shim for tests

    class _DateTimeModule:
        @staticmethod
        def utcnow() -> datetime:
            return datetime.now(UTC)

        @staticmethod
        def as_timestamp(value: datetime) -> float:
            if value.tzinfo is None:
                value = value.replace(tzinfo=UTC)
            return value.timestamp()

        @staticmethod
        def as_utc(value: datetime) -> datetime:
            if value.tzinfo is None:
                return value.replace(tzinfo=UTC)
            return value.astimezone(UTC)

    dt_util = _DateTimeModule()

from . import compat
from .compat import bind_exception_alias, ensure_homeassistant_exception_symbols

ensure_homeassistant_exception_symbols()
HomeAssistantError: type[Exception] = cast(
    type[Exception], compat.HomeAssistantError
)
bind_exception_alias("HomeAssistantError", combine_with_current=True)


def _resolve_homeassistant_error() -> type[Exception]:
    """Return the active Home Assistant error type."""

    try:
        module = import_module("custom_components.pawcontrol.data_manager")
    except Exception:  # pragma: no cover - fallback when data manager unavailable
        return HomeAssistantError

    resolver = getattr(module, "_resolve_homeassistant_error", None)
    if callable(resolver):
        try:
            return resolver()
        except Exception:  # pragma: no cover - defensive fallback
            return HomeAssistantError

    return HomeAssistantError


_LOGGER = logging.getLogger(__name__)

# Type variables for generic retry/circuit breaker
T = TypeVar("T")

AsyncCallable = Callable[..., Awaitable[T]]


class CircuitBreakerStateError(HomeAssistantError):
    """Raised when a circuit breaker rejects a call due to its state."""


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if recovered


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""

    failure_threshold: int = 5  # Failures before opening
    success_threshold: int = 2  # Successes in half-open before closing
    timeout_seconds: float = 60.0  # Time in open state before half-open
    half_open_max_calls: int = 3  # Max calls allowed in half-open state


@dataclass
class CircuitBreakerStats:
    """Statistics for circuit breaker monitoring."""

    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: float | None = None
    last_state_change: float | None = None
    last_success_time: float | None = None
    total_calls: int = 0
    total_failures: int = 0
    total_successes: int = 0
    rejected_calls: int = 0
    last_rejection_time: float | None = None
    _last_failure_monotonic: float | None = field(default=None, init=False, repr=False)
    _last_state_change_monotonic: float | None = field(
        default=None, init=False, repr=False
    )
    _last_success_monotonic: float | None = field(default=None, init=False, repr=False)


def _utc_timestamp() -> float:
    """Return the current UTC timestamp as a float."""

    now = dt_util.utcnow()
    convert = getattr(dt_util, "as_timestamp", None)
    if callable(convert):
        try:
            return float(convert(now))
        except (TypeError, ValueError, OverflowError):
            pass

    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)

    try:
        return float(now.timestamp())
    except (OverflowError, OSError, ValueError):  # pragma: no cover - fallback
        return time.time()


class CircuitBreaker:
    """Circuit breaker implementation for fault tolerance.

    Prevents cascading failures by stopping calls to failing services.
    """

    def __init__(
        self,
        name: str,
        config: CircuitBreakerConfig | None = None,
    ) -> None:
        """Initialize circuit breaker.

        Args:
            name: Circuit breaker identifier
            config: Configuration for circuit breaker behavior
        """
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self._stats = CircuitBreakerStats()
        self._lock = asyncio.Lock()
        self._half_open_calls = 0

        _LOGGER.info(
            "Initialized circuit breaker '%s': threshold=%d, timeout=%.1fs",
            name,
            self.config.failure_threshold,
            self.config.timeout_seconds,
        )

    @property
    def state(self) -> CircuitState:
        """Get current circuit state."""
        return self._stats.state

    @property
    def stats(self) -> CircuitBreakerStats:
        """Get circuit breaker statistics."""
        return self._stats

    async def call(
        self,
        func: AsyncCallable[T],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        """Execute function with circuit breaker protection.

        Args:
            func: Async function to execute
            *args: Positional arguments for function
            **kwargs: Keyword arguments for function

        Returns:
            Function result

        Raises:
            HomeAssistantError: If circuit is open or call fails
        """
        incremented_half_open = False

        async with self._lock:
            self._stats.total_calls += 1

            # Check if circuit should transition from open to half-open
            if self._stats.state == CircuitState.OPEN:
                if self._should_attempt_reset():
                    self._transition_to_half_open()
                else:
                    message = f"Circuit breaker '{self.name}' is OPEN - calls rejected"
                    self._record_rejection(message)
                    raise CircuitBreakerStateError(message)

            # Limit calls in half-open state
            if self._stats.state == CircuitState.HALF_OPEN:
                if self._half_open_calls >= self.config.half_open_max_calls:
                    self._stats.total_failures += 1
                    message = (
                        f"Circuit breaker '{self.name}' is HALF_OPEN - "
                        f"max concurrent calls reached"
                    )
                    self._record_rejection(message)
                    raise CircuitBreakerStateError(message)
                self._half_open_calls += 1
                incremented_half_open = True

        # Execute function outside lock to avoid blocking
        try:
            result = await func(*args, **kwargs)
            await self._record_success()
            return result

        except Exception as err:
            await self._record_failure(err)
            raise

        finally:
            if incremented_half_open:
                async with self._lock:
                    if self._half_open_calls > 0:
                        self._half_open_calls -= 1

    async def _record_success(self) -> None:
        """Record successful call and update state."""
        async with self._lock:
            self._stats.total_successes += 1
            self._stats.success_count += 1
            now_monotonic = time.monotonic()
            self._stats.last_success_time = _utc_timestamp()
            self._stats._last_success_monotonic = now_monotonic

            if self._stats.state == CircuitState.HALF_OPEN:
                if self._stats.success_count >= self.config.success_threshold:
                    self._transition_to_closed()

            elif self._stats.state == CircuitState.CLOSED:
                # Reset failure count on success
                self._stats.failure_count = 0

    async def _record_failure(self, error: Exception) -> None:
        """Record failed call and update state.

        Args:
            error: Exception that caused the failure
        """
        async with self._lock:
            self._stats.total_failures += 1
            self._stats.failure_count += 1
            now_monotonic = time.monotonic()
            self._stats._last_failure_monotonic = now_monotonic
            self._stats.last_failure_time = _utc_timestamp()

            _LOGGER.warning(
                "Circuit breaker '%s' recorded failure (%d/%d): %s",
                self.name,
                self._stats.failure_count,
                self.config.failure_threshold,
                error,
            )

            if self._stats.state == CircuitState.HALF_OPEN:
                # Any failure in half-open immediately opens circuit
                self._transition_to_open()

            elif (
                self._stats.state == CircuitState.CLOSED
                and self._stats.failure_count >= self.config.failure_threshold
            ):
                self._transition_to_open()

    def _record_rejection(self, message: str) -> None:
        """Record a rejected call for telemetry purposes."""

        self._stats.rejected_calls += 1
        self._stats.last_rejection_time = _utc_timestamp()
        _LOGGER.debug(
            "Circuit breaker '%s' rejected call while %s: %s",
            self.name,
            self._stats.state.value,
            message,
        )

    def _should_attempt_reset(self) -> bool:
        """Check if circuit should attempt reset from open to half-open.

        Returns:
            True if timeout has elapsed since last failure
        """
        reference = (
            self._stats._last_state_change_monotonic
            if self._stats._last_state_change_monotonic is not None
            else self._stats._last_failure_monotonic
        )

        if reference is None:
            return True

        elapsed = time.monotonic() - reference
        return elapsed >= self.config.timeout_seconds

    def _transition_to_open(self) -> None:
        """Transition circuit to OPEN state."""
        self._stats.state = CircuitState.OPEN
        now_monotonic = time.monotonic()
        self._stats._last_state_change_monotonic = now_monotonic
        self._stats.last_state_change = _utc_timestamp()
        self._stats.failure_count = 0
        self._stats.success_count = 0

        _LOGGER.error(
            "Circuit breaker '%s' OPENED - rejecting calls for %.1fs",
            self.name,
            self.config.timeout_seconds,
        )

    def _transition_to_half_open(self) -> None:
        """Transition circuit to HALF_OPEN state."""
        self._stats.state = CircuitState.HALF_OPEN
        now_monotonic = time.monotonic()
        self._stats._last_state_change_monotonic = now_monotonic
        self._stats.last_state_change = _utc_timestamp()
        self._stats.failure_count = 0
        self._stats.success_count = 0
        self._half_open_calls = 0

        _LOGGER.info(
            "Circuit breaker '%s' entered HALF_OPEN - testing recovery",
            self.name,
        )

    def _transition_to_closed(self) -> None:
        """Transition circuit to CLOSED state."""
        self._stats.state = CircuitState.CLOSED
        now_monotonic = time.monotonic()
        self._stats._last_state_change_monotonic = now_monotonic
        self._stats.last_state_change = _utc_timestamp()
        self._stats.failure_count = 0
        self._stats.success_count = 0

        _LOGGER.info(
            "Circuit breaker '%s' CLOSED - normal operation resumed",
            self.name,
        )

    async def reset(self) -> None:
        """Manually reset circuit breaker to closed state."""
        async with self._lock:
            self._transition_to_closed()
            _LOGGER.info("Circuit breaker '%s' manually reset", self.name)


@dataclass
class RetryConfig:
    """Configuration for retry logic."""

    max_attempts: int = 3
    initial_delay: float = 1.0  # seconds
    max_delay: float = 60.0  # seconds
    exponential_base: float = 2.0
    jitter: bool = True  # Add randomness to delays
    random_source: Callable[[], float] | None = None


class RetryExhaustedError(HomeAssistantErrorType):
    """Raised when all retry attempts are exhausted."""

    def __init__(self, attempts: int, last_error: Exception) -> None:
        """Initialize retry exhausted error.

        Args:
            attempts: Number of attempts made
            last_error: Last exception that occurred
        """
        super().__init__(f"Retry exhausted after {attempts} attempts: {last_error}")
        self.attempts = attempts
        self.last_error = last_error


async def retry_with_backoff[T](
    func: AsyncCallable[T],
    *args: Any,
    **kwargs: Any,
) -> T:
    """Retry function with exponential backoff.

    Args:
        func: Async function to retry
        *args: Positional arguments for function
        config: Retry configuration
        **kwargs: Keyword arguments for function

    Returns:
        Function result

    Raises:
        RetryExhaustedError: If all retry attempts fail
    """
    retry_config = kwargs.pop("config", None) or kwargs.pop("retry_config", None)
    retry_config = retry_config or RetryConfig()
    if retry_config.max_attempts < 1:
        raise _resolve_homeassistant_error()("Retry requires at least one attempt")
    last_exception: Exception | None = None

    for attempt in range(1, retry_config.max_attempts + 1):
        try:
            result = await func(*args, **kwargs)
            if attempt > 1:
                log_method = (
                    _LOGGER.info
                    if _LOGGER.isEnabledFor(logging.INFO)
                    else _LOGGER.warning
                )
                log_method(
                    "Retry succeeded on attempt %d/%d for %s",
                    attempt,
                    retry_config.max_attempts,
                    func.__name__,
                )
            return result

        except Exception as err:
            last_exception = err

            if attempt >= retry_config.max_attempts:
                _LOGGER.error(
                    "Retry exhausted after %d attempts for %s: %s",
                    attempt,
                    func.__name__,
                    err,
                )
                raise RetryExhaustedError(attempt, err) from err

            # Calculate delay with exponential backoff
            delay = min(
                retry_config.initial_delay
                * (retry_config.exponential_base ** (attempt - 1)),
                retry_config.max_delay,
            )

            # Add jitter if enabled
            if retry_config.jitter:
                import random

                random_value = (
                    retry_config.random_source()
                    if retry_config.random_source is not None
                    else random.SystemRandom().random()
                )
                delay = delay * (0.5 + random_value)

            _LOGGER.warning(
                "Retry attempt %d/%d failed for %s: %s - waiting %.1fs",
                attempt,
                retry_config.max_attempts,
                func.__name__,
                err,
                delay,
            )

            await asyncio.sleep(delay)

    # Should never reach here due to raise in loop, but satisfy type checker
    if last_exception:  # pragma: no cover - defensive safeguard
        raise RetryExhaustedError(retry_config.max_attempts, last_exception)
    raise _resolve_homeassistant_error()("Retry failed with no exception recorded")


class ResilienceManager:
    """Centralized resilience management for PawControl integration."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize resilience manager.

        Args:
            hass: Home Assistant instance
        """
        self.hass = hass
        self._circuit_breakers: dict[str, CircuitBreaker] = {}
        self._lock = asyncio.Lock()

        _LOGGER.info("Initialized ResilienceManager")

    async def get_circuit_breaker(
        self,
        name: str,
        config: CircuitBreakerConfig | None = None,
    ) -> CircuitBreaker:
        """Get or create circuit breaker.

        Args:
            name: Circuit breaker identifier
            config: Optional configuration

        Returns:
            Circuit breaker instance
        """
        async with self._lock:
            if name not in self._circuit_breakers:
                self._circuit_breakers[name] = CircuitBreaker(name, config)

            return self._circuit_breakers[name]

    async def execute_with_resilience(
        self,
        func: AsyncCallable[T],
        *args: Any,
        circuit_breaker_name: str | None = None,
        retry_config: RetryConfig | None = None,
        **kwargs: Any,
    ) -> T:
        """Execute function with full resilience patterns.

        Combines circuit breaker and retry logic for maximum reliability.

        Args:
            func: Async function to execute
            *args: Positional arguments
            circuit_breaker_name: Optional circuit breaker to use
            retry_config: Optional retry configuration
            **kwargs: Keyword arguments

        Returns:
            Function result

        Raises:
            HomeAssistantError: If execution fails after all resilience attempts
        """
        # If circuit breaker specified, wrap function
        if circuit_breaker_name:
            breaker = await self.get_circuit_breaker(circuit_breaker_name)

            async def wrapped_func(*inner_args: Any, **inner_kwargs: Any) -> T:
                return await breaker.call(func, *inner_args, **inner_kwargs)

            execution_func: AsyncCallable[T] = wrapped_func
        else:
            execution_func = func

        # Apply retry logic
        if retry_config:
            return await retry_with_backoff(
                execution_func, *args, config=retry_config, **kwargs
            )
        else:
            return await execution_func(*args, **kwargs)

    def get_all_circuit_breakers(self) -> dict[str, CircuitBreakerStats]:
        """Get statistics for all circuit breakers.

        Returns:
            Dictionary mapping circuit breaker names to their statistics
        """
        return {name: breaker.stats for name, breaker in self._circuit_breakers.items()}

    async def reset_circuit_breaker(self, name: str) -> bool:
        """Manually reset a circuit breaker.

        Args:
            name: Circuit breaker name

        Returns:
            True if circuit breaker was found and reset
        """
        async with self._lock:
            if name in self._circuit_breakers:
                await self._circuit_breakers[name].reset()
                return True
            return False

    async def reset_all_circuit_breakers(self) -> int:
        """Reset all circuit breakers.

        Returns:
            Number of circuit breakers reset
        """
        async with self._lock:
            reset_count = 0
            for breaker in self._circuit_breakers.values():
                await breaker.reset()
                reset_count += 1

            _LOGGER.info("Reset %d circuit breakers", reset_count)
            return reset_count
