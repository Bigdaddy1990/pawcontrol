"""Resilience patterns for PawControl integration.

This module implements circuit breaker, retry, and fallback patterns to ensure
the integration gracefully handles failures and recovers automatically.

Quality Scale: Platinum target
Home Assistant: 2025.9.0+
Python: 3.13+
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any
from typing import ParamSpec
from typing import TypeVar

from .exceptions import NetworkError
from .exceptions import RateLimitError
from .exceptions import ServiceUnavailableError

_LOGGER = logging.getLogger(__name__)
_SECURE_RANDOM = random.SystemRandom()

P = ParamSpec("P")
T = TypeVar("T")


class CircuitState(Enum):
  """Circuit breaker states."""

  CLOSED = "closed"  # Normal operation
  OPEN = "open"  # Failure threshold exceeded, blocking calls
  HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreakerConfig:
  """Circuit breaker configuration.

  Attributes:
      failure_threshold: Number of failures before opening
      success_threshold: Number of successes to close from half-open
      timeout_seconds: Time to wait before half-open attempt
      excluded_exceptions: Exception types that don't count as failures
  """

  failure_threshold: int = 5
  success_threshold: int = 2
  timeout_seconds: float = 60.0
  excluded_exceptions: tuple[type[Exception], ...] = (RateLimitError,)


@dataclass
class CircuitBreakerStats:
  """Circuit breaker statistics.

  Attributes:
      state: Current state
      failure_count: Consecutive failures
      success_count: Consecutive successes in half-open
      last_failure_time: Timestamp of last failure
      total_calls: Total calls attempted
      total_failures: Total failures
      total_successes: Total successes
  """

  state: CircuitState = CircuitState.CLOSED
  failure_count: int = 0
  success_count: int = 0
  last_failure_time: float | None = None
  total_calls: int = 0
  total_failures: int = 0
  total_successes: int = 0

  def to_dict(self) -> dict[str, Any]:
    """Convert to dictionary."""
    return {
      "state": self.state.value,
      "failure_count": self.failure_count,
      "success_count": self.success_count,
      "last_failure_time": self.last_failure_time,
      "total_calls": self.total_calls,
      "total_failures": self.total_failures,
      "total_successes": self.total_successes,
      "success_rate": (
        self.total_successes / self.total_calls if self.total_calls > 0 else 0.0
      ),
    }


class CircuitBreaker:
  """Circuit breaker pattern implementation.

  Prevents cascading failures by temporarily blocking calls to failing services.

  States:
      CLOSED: Normal operation, calls pass through
      OPEN: Too many failures, calls blocked immediately
      HALF_OPEN: Testing recovery, limited calls allowed

  Examples:
      >>> breaker = CircuitBreaker("api_client")
      >>> async with breaker:
      ...   await api.call()
  """

  def __init__(
    self,
    name: str,
    *,
    config: CircuitBreakerConfig | None = None,
  ) -> None:
    """Initialize circuit breaker.

    Args:
        name: Circuit breaker name
        config: Optional configuration
    """
    self._name = name
    self._config = config or CircuitBreakerConfig()
    self._stats = CircuitBreakerStats()
    self._lock = asyncio.Lock()

  @property
  def name(self) -> str:
    """Return circuit breaker name."""
    return self._name

  @property
  def state(self) -> CircuitState:
    """Return current state."""
    return self._stats.state

  @property
  def is_closed(self) -> bool:
    """Return True if circuit is closed."""
    return self._stats.state == CircuitState.CLOSED

  @property
  def is_open(self) -> bool:
    """Return True if circuit is open."""
    return self._stats.state == CircuitState.OPEN

  @property
  def is_half_open(self) -> bool:
    """Return True if circuit is half-open."""
    return self._stats.state == CircuitState.HALF_OPEN

  async def call(
    self,
    func: Callable[P, T],
    *args: P.args,
    **kwargs: P.kwargs,
  ) -> T:
    """Execute function with circuit breaker protection.

    Args:
        func: Function to call
        *args: Positional arguments
        **kwargs: Keyword arguments

    Returns:
        Function result

    Raises:
        ServiceUnavailableError: If circuit is open
    """
    async with self._lock:
      # Check if circuit should transition to half-open
      if self._stats.state == CircuitState.OPEN and self._should_attempt_reset():
        _LOGGER.info("Circuit breaker %s: OPEN → HALF_OPEN", self._name)
        self._stats.state = CircuitState.HALF_OPEN
        self._stats.success_count = 0

      # Block calls if open
      if self._stats.state == CircuitState.OPEN:
        self._stats.total_calls += 1
        raise ServiceUnavailableError(f"Circuit breaker {self._name} is OPEN")

    # Execute call
    try:
      self._stats.total_calls += 1
      result = await func(*args, **kwargs)
      await self._record_success()
      return result
    except Exception as e:
      # Check if exception should be excluded
      if isinstance(e, self._config.excluded_exceptions):
        raise

      await self._record_failure()
      raise

  async def _record_success(self) -> None:
    """Record successful call."""
    async with self._lock:
      self._stats.total_successes += 1

      if self._stats.state == CircuitState.HALF_OPEN:
        self._stats.success_count += 1
        if self._stats.success_count >= self._config.success_threshold:
          _LOGGER.info("Circuit breaker %s: HALF_OPEN → CLOSED", self._name)
          self._stats.state = CircuitState.CLOSED
          self._stats.failure_count = 0
          self._stats.success_count = 0

      elif self._stats.state == CircuitState.CLOSED:
        self._stats.failure_count = 0

  async def _record_failure(self) -> None:
    """Record failed call."""
    async with self._lock:
      self._stats.total_failures += 1
      self._stats.failure_count += 1
      self._stats.last_failure_time = time.time()

      if self._stats.state == CircuitState.HALF_OPEN:
        _LOGGER.warning(
          "Circuit breaker %s: HALF_OPEN → OPEN (recovery failed)",
          self._name,
        )
        self._stats.state = CircuitState.OPEN
        self._stats.success_count = 0

      elif self._stats.state == CircuitState.CLOSED:
        if self._stats.failure_count >= self._config.failure_threshold:
          _LOGGER.warning(
            "Circuit breaker %s: CLOSED → OPEN (%d failures)",
            self._name,
            self._stats.failure_count,
          )
          self._stats.state = CircuitState.OPEN

  def _should_attempt_reset(self) -> bool:
    """Check if enough time has passed to attempt reset."""
    if self._stats.last_failure_time is None:
      return True

    time_since_failure = time.time() - self._stats.last_failure_time
    return time_since_failure >= self._config.timeout_seconds

  async def __aenter__(self) -> CircuitBreaker:
    """Enter async context."""
    # Check state before allowing entry
    if self._stats.state == CircuitState.OPEN:
      if not self._should_attempt_reset():
        raise ServiceUnavailableError(f"Circuit breaker {self._name} is OPEN")
      async with self._lock:
        self._stats.state = CircuitState.HALF_OPEN
        self._stats.success_count = 0

    return self

  async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
    """Exit async context."""
    if exc_type is None:
      await self._record_success()
    elif not isinstance(exc_val, self._config.excluded_exceptions):
      await self._record_failure()

  def get_stats(self) -> CircuitBreakerStats:
    """Return circuit breaker statistics."""
    return self._stats

  def reset(self) -> None:
    """Manually reset circuit breaker to closed state."""
    self._stats = CircuitBreakerStats()
    _LOGGER.info("Circuit breaker %s manually reset", self._name)


@dataclass
class RetryConfig:
  """Retry configuration.

  Attributes:
      max_attempts: Maximum retry attempts
      base_delay: Base delay in seconds
      max_delay: Maximum delay in seconds
      exponential_base: Base for exponential backoff
      jitter: Add random jitter (0.0-1.0)
      retryable_exceptions: Exception types to retry
  """

  max_attempts: int = 3
  base_delay: float = 1.0
  max_delay: float = 60.0
  exponential_base: float = 2.0
  jitter: float = 0.1
  retryable_exceptions: tuple[type[Exception], ...] = (
    NetworkError,
    ServiceUnavailableError,
  )


class RetryStrategy:
  """Retry strategy with exponential backoff and jitter.

  Examples:
      >>> strategy = RetryStrategy()
      >>> result = await strategy.execute(api_call, arg1, arg2)
  """

  def __init__(self, config: RetryConfig | None = None) -> None:
    """Initialize retry strategy.

    Args:
        config: Optional retry configuration
    """
    self._config = config or RetryConfig()

  async def execute(
    self,
    func: Callable[P, T],
    *args: P.args,
    **kwargs: P.kwargs,
  ) -> T:
    """Execute function with retry logic.

    Args:
        func: Function to execute
        *args: Positional arguments
        **kwargs: Keyword arguments

    Returns:
        Function result

    Raises:
        Exception: Last exception if all retries fail
    """
    last_exception: Exception | None = None

    for attempt in range(self._config.max_attempts):
      try:
        return await func(*args, **kwargs)
      except Exception as e:
        last_exception = e

        # Check if exception is retryable
        if not isinstance(e, self._config.retryable_exceptions):
          raise

        # Don't retry on last attempt
        if attempt == self._config.max_attempts - 1:
          raise

        # Calculate delay
        delay = self._calculate_delay(attempt)

        _LOGGER.warning(
          "Retry attempt %d/%d failed: %s (waiting %.2fs)",
          attempt + 1,
          self._config.max_attempts,
          e,
          delay,
        )

        await asyncio.sleep(delay)

    # Should never reach here, but satisfy type checker
    if last_exception:
      raise last_exception
    raise RuntimeError("Retry logic failed unexpectedly")

  def _calculate_delay(self, attempt: int) -> float:
    """Calculate delay for retry attempt.

    Args:
        attempt: Attempt number (0-based)

    Returns:
        Delay in seconds
    """
    # Exponential backoff
    delay = self._config.base_delay * (self._config.exponential_base**attempt)

    # Cap at max delay
    delay = min(delay, self._config.max_delay)

    # Add jitter
    if self._config.jitter > 0:
      jitter_amount = delay * self._config.jitter
      delay += _SECURE_RANDOM.uniform(-jitter_amount, jitter_amount)

    return max(0.0, delay)


class FallbackStrategy:
  """Fallback strategy for when operations fail.

  Provides default values or alternative implementations when primary
  operations fail.

  Examples:
      >>> fallback = FallbackStrategy(default_value={})
      >>> result = await fallback.execute_with_fallback(fetch_data)
  """

  def __init__(
    self,
    *,
    default_value: Any = None,
    fallback_func: Callable[..., Any] | None = None,
  ) -> None:
    """Initialize fallback strategy.

    Args:
        default_value: Default value to return on failure
        fallback_func: Alternative function to try
    """
    self._default_value = default_value
    self._fallback_func = fallback_func

  async def execute_with_fallback(
    self,
    func: Callable[P, T],
    *args: P.args,
    **kwargs: P.kwargs,
  ) -> T | Any:
    """Execute function with fallback.

    Args:
        func: Primary function
        *args: Positional arguments
        **kwargs: Keyword arguments

    Returns:
        Primary result, fallback result, or default value
    """
    try:
      return await func(*args, **kwargs)
    except Exception as e:
      _LOGGER.warning("Primary operation failed: %s", e)

      # Try fallback function
      if self._fallback_func:
        try:
          _LOGGER.info("Attempting fallback function")
          return await self._fallback_func(*args, **kwargs)
        except Exception as fallback_error:
          _LOGGER.error("Fallback function failed: %s", fallback_error)

      # Return default value
      _LOGGER.info("Returning default value")
      return self._default_value


# Global circuit breaker registry

_circuit_breakers: dict[str, CircuitBreaker] = {}


def get_circuit_breaker(
  name: str,
  *,
  config: CircuitBreakerConfig | None = None,
) -> CircuitBreaker:
  """Get or create circuit breaker.

  Args:
      name: Circuit breaker name
      config: Optional configuration

  Returns:
      CircuitBreaker instance

  Examples:
      >>> breaker = get_circuit_breaker("api_client")
      >>> async with breaker:
      ...   await api.call()
  """
  if name not in _circuit_breakers:
    _circuit_breakers[name] = CircuitBreaker(name, config=config)
  return _circuit_breakers[name]


def get_all_circuit_breakers() -> dict[str, CircuitBreaker]:
  """Return all circuit breakers.

  Returns:
      Dictionary of circuit breakers
  """
  return dict(_circuit_breakers)


def reset_all_circuit_breakers() -> None:
  """Reset all circuit breakers."""
  for breaker in _circuit_breakers.values():
    breaker.reset()
  _LOGGER.info("All circuit breakers reset")


# Resilience decorators


def with_circuit_breaker(
  name: str,
  *,
  config: CircuitBreakerConfig | None = None,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
  """Decorator to protect function with circuit breaker.

  Args:
      name: Circuit breaker name
      config: Optional configuration

  Returns:
      Decorated function

  Examples:
      >>> @with_circuit_breaker("api_client")
      ... async def fetch_data():
      ...   return await api.get_data()
  """
  breaker = get_circuit_breaker(name, config=config)

  def decorator(func: Callable[P, T]) -> Callable[P, T]:
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
      return await breaker.call(func, *args, **kwargs)

    return wrapper  # type: ignore[return-value]

  return decorator


def with_retry(
  config: RetryConfig | None = None,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
  """Decorator to add retry logic to function.

  Args:
      config: Optional retry configuration

  Returns:
      Decorated function

  Examples:
      >>> @with_retry(RetryConfig(max_attempts=3))
      ... async def fetch_data():
      ...   return await api.get_data()
  """
  strategy = RetryStrategy(config)

  def decorator(func: Callable[P, T]) -> Callable[P, T]:
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
      return await strategy.execute(func, *args, **kwargs)

    return wrapper  # type: ignore[return-value]

  return decorator


def with_fallback(
  default_value: Any = None,
  fallback_func: Callable[..., Any] | None = None,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
  """Decorator to add fallback to function.

  Args:
      default_value: Default value on failure
      fallback_func: Alternative function

  Returns:
      Decorated function

  Examples:
      >>> @with_fallback(default_value={})
      ... async def fetch_data():
      ...   return await api.get_data()
  """
  strategy = FallbackStrategy(
    default_value=default_value,
    fallback_func=fallback_func,
  )

  def decorator(func: Callable[P, T]) -> Callable[P, T]:
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T | Any:
      return await strategy.execute_with_fallback(func, *args, **kwargs)

    return wrapper  # type: ignore[return-value]

  return decorator
