"""Resilience patterns for PawControl integration.

This module implements circuit breaker, retry, and fallback patterns to ensure
the integration gracefully handles failures and recovers automatically.

Quality Scale: Platinum target
Home Assistant: 2025.9.0+
Python: 3.13+
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import Enum
import logging
import random
import time
from types import TracebackType
from typing import Any, ParamSpec, TypeVar, cast

from .exceptions import NetworkError, RateLimitError, ServiceUnavailableError

_LOGGER = logging.getLogger(__name__)
_SECURE_RANDOM = random.SystemRandom()

P = ParamSpec("P")
T = TypeVar("T")


class CircuitState(Enum):
  """Circuit breaker states."""  # noqa: E111

  CLOSED = "closed"  # Normal operation  # noqa: E111
  OPEN = "open"  # Failure threshold exceeded, blocking calls  # noqa: E111
  HALF_OPEN = "half_open"  # Testing if service recovered  # noqa: E111


@dataclass
class CircuitBreakerConfig:
  """Circuit breaker configuration.

  Attributes:
      failure_threshold: Number of failures before opening
      success_threshold: Number of successes to close from half-open
      timeout_seconds: Time to wait before half-open attempt
      excluded_exceptions: Exception types that don't count as failures
  """  # noqa: E111

  failure_threshold: int = 5  # noqa: E111
  success_threshold: int = 2  # noqa: E111
  timeout_seconds: float = 60.0  # noqa: E111
  excluded_exceptions: tuple[type[Exception], ...] = (RateLimitError,)  # noqa: E111


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
  """  # noqa: E111

  state: CircuitState = CircuitState.CLOSED  # noqa: E111
  failure_count: int = 0  # noqa: E111
  success_count: int = 0  # noqa: E111
  last_failure_time: float | None = None  # noqa: E111
  total_calls: int = 0  # noqa: E111
  total_failures: int = 0  # noqa: E111
  total_successes: int = 0  # noqa: E111

  def to_dict(self) -> dict[str, Any]:  # noqa: E111
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
  """  # noqa: E111

  def __init__(  # noqa: E111
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

  @property  # noqa: E111
  def name(self) -> str:  # noqa: E111
    """Return circuit breaker name."""
    return self._name

  @property  # noqa: E111
  def state(self) -> CircuitState:  # noqa: E111
    """Return current state."""
    return self._stats.state

  @property  # noqa: E111
  def is_closed(self) -> bool:  # noqa: E111
    """Return True if circuit is closed."""
    return self._stats.state == CircuitState.CLOSED

  @property  # noqa: E111
  def is_open(self) -> bool:  # noqa: E111
    """Return True if circuit is open."""
    return self._stats.state == CircuitState.OPEN

  @property  # noqa: E111
  def is_half_open(self) -> bool:  # noqa: E111
    """Return True if circuit is half-open."""
    return self._stats.state == CircuitState.HALF_OPEN

  async def call(  # noqa: E111
    self,
    func: Callable[P, Awaitable[T]],
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
      # Check if circuit should transition to half-open  # noqa: E114
      if self._stats.state == CircuitState.OPEN and self._should_attempt_reset():  # noqa: E111
        _LOGGER.info("Circuit breaker %s: OPEN → HALF_OPEN", self._name)
        self._stats.state = CircuitState.HALF_OPEN
        self._stats.success_count = 0

      # Block calls if open  # noqa: E114
      if self._stats.state == CircuitState.OPEN:  # noqa: E111
        self._stats.total_calls += 1
        raise ServiceUnavailableError(f"Circuit breaker {self._name} is OPEN")

    # Execute call
    try:
      self._stats.total_calls += 1  # noqa: E111
      result = await func(*args, **kwargs)  # noqa: E111
      await self._record_success()  # noqa: E111
      return result  # noqa: E111
    except Exception as e:
      # Check if exception should be excluded  # noqa: E114
      if isinstance(e, self._config.excluded_exceptions):  # noqa: E111
        raise

      await self._record_failure()  # noqa: E111
      raise  # noqa: E111

  async def _record_success(self) -> None:  # noqa: E111
    """Record successful call."""
    async with self._lock:
      self._stats.total_successes += 1  # noqa: E111

      if self._stats.state == CircuitState.HALF_OPEN:  # noqa: E111
        self._stats.success_count += 1
        if self._stats.success_count >= self._config.success_threshold:
          _LOGGER.info("Circuit breaker %s: HALF_OPEN → CLOSED", self._name)  # noqa: E111
          self._stats.state = CircuitState.CLOSED  # noqa: E111
          self._stats.failure_count = 0  # noqa: E111
          self._stats.success_count = 0  # noqa: E111

      elif self._stats.state == CircuitState.CLOSED:  # noqa: E111
        self._stats.failure_count = 0

  async def _record_failure(self) -> None:  # noqa: E111
    """Record failed call."""
    async with self._lock:
      self._stats.total_failures += 1  # noqa: E111
      self._stats.failure_count += 1  # noqa: E111
      self._stats.last_failure_time = time.time()  # noqa: E111

      if self._stats.state == CircuitState.HALF_OPEN:  # noqa: E111
        _LOGGER.warning(
          "Circuit breaker %s: HALF_OPEN → OPEN (recovery failed)",
          self._name,
        )
        self._stats.state = CircuitState.OPEN
        self._stats.success_count = 0

      elif self._stats.state == CircuitState.CLOSED:  # noqa: E111
        if self._stats.failure_count >= self._config.failure_threshold:
          _LOGGER.warning(  # noqa: E111
            "Circuit breaker %s: CLOSED → OPEN (%d failures)",
            self._name,
            self._stats.failure_count,
          )
          self._stats.state = CircuitState.OPEN  # noqa: E111

  def _should_attempt_reset(self) -> bool:  # noqa: E111
    """Check if enough time has passed to attempt reset."""
    if self._stats.last_failure_time is None:
      return True  # noqa: E111

    time_since_failure = time.time() - self._stats.last_failure_time
    return time_since_failure >= self._config.timeout_seconds

  async def __aenter__(self) -> CircuitBreaker:  # noqa: E111
    """Enter async context."""
    # Check state before allowing entry
    if self._stats.state == CircuitState.OPEN:
      if not self._should_attempt_reset():  # noqa: E111
        raise ServiceUnavailableError(f"Circuit breaker {self._name} is OPEN")
      async with self._lock:  # noqa: E111
        self._stats.state = CircuitState.HALF_OPEN
        self._stats.success_count = 0

    return self

  async def __aexit__(  # noqa: E111
    self,
    exc_type: type[BaseException] | None,
    exc_val: BaseException | None,
    exc_tb: TracebackType | None,
  ) -> None:
    """Exit async context."""
    if exc_type is None:
      await self._record_success()  # noqa: E111
    elif not isinstance(exc_val, self._config.excluded_exceptions):
      await self._record_failure()  # noqa: E111

  def get_stats(self) -> CircuitBreakerStats:  # noqa: E111
    """Return circuit breaker statistics."""
    return self._stats

  def reset(self) -> None:  # noqa: E111
    """Manually reset circuit breaker to closed state."""
    self._stats = CircuitBreakerStats()
    _LOGGER.info("Circuit breaker %s manually reset", self._name)


@dataclass
class RetryConfig:
  """Retry configuration.

  Attributes:
      max_attempts: Maximum retry attempts
      initial_delay: Base delay in seconds
      max_delay: Maximum delay in seconds
      exponential_base: Base for exponential backoff
      jitter: Add random jitter (boolean enables default 10%)
      retryable_exceptions: Exception types to retry
  """  # noqa: E111

  max_attempts: int = 3  # noqa: E111
  initial_delay: float = 1.0  # noqa: E111
  max_delay: float = 60.0  # noqa: E111
  exponential_base: float = 2.0  # noqa: E111
  jitter: bool | float = 0.1  # noqa: E111
  retryable_exceptions: tuple[type[Exception], ...] = (  # noqa: E111
    NetworkError,
    ServiceUnavailableError,
  )


class RetryStrategy:
  """Retry strategy with exponential backoff and jitter.

  Examples:
      >>> strategy = RetryStrategy()
      >>> result = await strategy.execute(api_call, arg1, arg2)
  """  # noqa: E111

  def __init__(self, config: RetryConfig | None = None) -> None:  # noqa: E111
    """Initialize retry strategy.

    Args:
        config: Optional retry configuration
    """
    self._config = config or RetryConfig()

  async def execute(  # noqa: E111
    self,
    func: Callable[P, Awaitable[T]],
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
      try:  # noqa: E111
        return await func(*args, **kwargs)
      except Exception as e:  # noqa: E111
        last_exception = e

        # Check if exception is retryable
        if not isinstance(e, self._config.retryable_exceptions):
          raise  # noqa: E111

        # Don't retry on last attempt
        if attempt == self._config.max_attempts - 1:
          raise  # noqa: E111

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
      raise last_exception  # noqa: E111
    raise RuntimeError("Retry logic failed unexpectedly")

  def _calculate_delay(self, attempt: int) -> float:  # noqa: E111
    """Calculate delay for retry attempt.

    Args:
        attempt: Attempt number (0-based)

    Returns:
        Delay in seconds
    """
    # Exponential backoff
    delay = self._config.initial_delay * (self._config.exponential_base**attempt)

    # Cap at max delay
    delay = min(delay, self._config.max_delay)

    # Add jitter
    jitter_factor: float
    if isinstance(self._config.jitter, bool):
      jitter_factor = 0.1 if self._config.jitter else 0.0  # noqa: E111
    else:
      jitter_factor = max(0.0, self._config.jitter)  # noqa: E111

    if jitter_factor > 0:
      jitter_amount = delay * jitter_factor  # noqa: E111
      delay += _SECURE_RANDOM.uniform(-jitter_amount, jitter_amount)  # noqa: E111

    return max(0.0, delay)


class FallbackStrategy:
  """Fallback strategy for when operations fail.

  Provides default values or alternative implementations when primary
  operations fail.

  Examples:
      >>> fallback = FallbackStrategy(default_value={})
      >>> result = await fallback.execute_with_fallback(fetch_data)
  """  # noqa: E111

  def __init__(  # noqa: E111
    self,
    *,
    default_value: Any = None,
    fallback_func: Callable[..., Awaitable[Any]] | None = None,
  ) -> None:
    """Initialize fallback strategy.

    Args:
        default_value: Default value to return on failure
        fallback_func: Alternative function to try
    """
    self._default_value = default_value
    self._fallback_func = fallback_func

  async def execute_with_fallback(  # noqa: E111
    self,
    func: Callable[P, Awaitable[T]],
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
      return await func(*args, **kwargs)  # noqa: E111
    except Exception as e:
      _LOGGER.warning("Primary operation failed: %s", e)  # noqa: E111

      # Try fallback function  # noqa: E114
      if self._fallback_func:  # noqa: E111
        try:
          _LOGGER.info("Attempting fallback function")  # noqa: E111
          return await self._fallback_func(*args, **kwargs)  # noqa: E111
        except Exception as fallback_error:
          _LOGGER.error("Fallback function failed: %s", fallback_error)  # noqa: E111

      # Return default value  # noqa: E114
      _LOGGER.info("Returning default value")  # noqa: E111
      return self._default_value  # noqa: E111


class ResilienceManager:
  """High-level facade that composes circuit breaker and retry behaviour."""  # noqa: E111

  def __init__(self, hass: object | None = None) -> None:  # noqa: E111
    """Initialise the resilience manager."""
    self._hass = hass

  async def execute_with_resilience(  # noqa: E111
    self,
    func: Callable[..., Awaitable[T]],
    *args: Any,
    circuit_breaker_name: str | None = None,
    retry_config: RetryConfig | None = None,
    **kwargs: Any,
  ) -> T:
    """Execute ``func`` with optional circuit breaker and retry protection."""

    async def _invoke() -> T:
      return await func(*args, **kwargs)  # noqa: E111

    wrapped_call: Callable[[], Any]
    if circuit_breaker_name:
      breaker = get_circuit_breaker(circuit_breaker_name)  # noqa: E111

      async def _invoke_with_breaker() -> T:  # noqa: E111
        return await breaker.call(_invoke)

      wrapped_call = _invoke_with_breaker  # noqa: E111
    else:
      wrapped_call = _invoke  # noqa: E111

    strategy = RetryStrategy(retry_config or RetryConfig())
    return await strategy.execute(wrapped_call)


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
  """  # noqa: E111
  if name not in _circuit_breakers:  # noqa: E111
    _circuit_breakers[name] = CircuitBreaker(name, config=config)
  return _circuit_breakers[name]  # noqa: E111


def get_all_circuit_breakers() -> dict[str, CircuitBreaker]:
  """Return all circuit breakers.

  Returns:
      Dictionary of circuit breakers
  """  # noqa: E111
  return dict(_circuit_breakers)  # noqa: E111


def reset_all_circuit_breakers() -> None:
  """Reset all circuit breakers."""  # noqa: E111
  for breaker in _circuit_breakers.values():  # noqa: E111
    breaker.reset()
  _LOGGER.info("All circuit breakers reset")  # noqa: E111


# Resilience decorators


def with_circuit_breaker(
  name: str,
  *,
  config: CircuitBreakerConfig | None = None,
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
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
  """  # noqa: E111
  breaker = get_circuit_breaker(name, config=config)  # noqa: E111

  def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:  # noqa: E111
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
      return await breaker.call(func, *args, **kwargs)  # noqa: E111

    return wrapper

  return decorator  # noqa: E111


def with_retry(
  config: RetryConfig | None = None,
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
  """Decorator to add retry logic to function.

  Args:
      config: Optional retry configuration

  Returns:
      Decorated function

  Examples:
      >>> @with_retry(RetryConfig(max_attempts=3))
      ... async def fetch_data():
      ...   return await api.get_data()
  """  # noqa: E111
  strategy = RetryStrategy(config)  # noqa: E111

  def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:  # noqa: E111
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
      return await strategy.execute(func, *args, **kwargs)  # noqa: E111

    return wrapper

  return decorator  # noqa: E111


def with_fallback(
  default_value: Any = None,
  fallback_func: Callable[..., Awaitable[Any]] | None = None,
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T | Any]]]:
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
  """  # noqa: E111
  strategy = FallbackStrategy(  # noqa: E111
    default_value=default_value,
    fallback_func=fallback_func,
  )

  def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T | Any]]:  # noqa: E111
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T | Any:
      return await strategy.execute_with_fallback(func, *args, **kwargs)  # noqa: E111

    return cast(Callable[P, Awaitable[T | Any]], wrapper)

  return decorator  # noqa: E111
