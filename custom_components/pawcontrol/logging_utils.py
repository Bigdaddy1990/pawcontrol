"""Enhanced logging utilities for PawControl integration.

This module provides structured logging, context tracking, and diagnostic
capabilities to improve troubleshooting and observability.

Quality Scale: Platinum target
Home Assistant: 2025.9.0+
Python: 3.13+
"""
from __future__ import annotations


import contextvars
import functools
import logging
import traceback
from collections import defaultdict
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from types import TracebackType
from typing import Any
from typing import ParamSpec
from typing import TypeVar
from uuid import uuid4

_LOGGER = logging.getLogger(__name__)

P = ParamSpec("P")
T = TypeVar("T")


# Context variables for tracking request flow
_correlation_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
  "correlation_id", default=None
)
_request_context: contextvars.ContextVar[dict[str, Any] | None] = (
  contextvars.ContextVar("request_context", default=None)
)


@dataclass
class LogEntry:
  """Structured log entry.

  Attributes:
      timestamp: When log was created
      level: Log level
      message: Log message
      correlation_id: Request correlation ID
      context: Additional context data
      exception: Exception info if present
  """

  timestamp: datetime
  level: str
  message: str
  correlation_id: str | None = None
  context: dict[str, Any] = field(default_factory=dict)
  exception: str | None = None

  def to_dict(self) -> dict[str, Any]:
    """Convert to dictionary."""
    data = {
      "timestamp": self.timestamp.isoformat(),
      "level": self.level,
      "message": self.message,
    }

    if self.correlation_id:
      data["correlation_id"] = self.correlation_id

    if self.context:
      data["context"] = self.context

    if self.exception:
      data["exception"] = self.exception

    return data


class StructuredLogger:
  """Structured logger with context support.

  Provides enhanced logging with automatic context tracking,
  correlation IDs, and structured data.

  Examples:
      >>> logger = StructuredLogger("pawcontrol.api")
      >>> logger.info("API call started", endpoint="/dogs", method="GET")
  """

  def __init__(self, name: str) -> None:
    """Initialize structured logger.

    Args:
        name: Logger name
    """
    self._logger = logging.getLogger(name)
    self._name = name

  def _log(
    self,
    level: int,
    message: str,
    *,
    exc_info: bool = False,
    **context: Any,
  ) -> None:
    """Internal logging method.

    Args:
        level: Log level
        message: Log message
        exc_info: Include exception info
        **context: Additional context
    """
    # Get correlation ID
    correlation_id = _correlation_id.get()

    # Merge with request context
    request_ctx = _request_context.get() or {}
    full_context = {**request_ctx, **context}

    # Build extra dict for logging
    extra: dict[str, Any] = {}
    if correlation_id:
      extra["correlation_id"] = correlation_id

    if full_context:
      extra["context"] = full_context

    # Format message with context
    if full_context:
      context_str = " ".join(f"{k}={v}" for k, v in full_context.items())
      formatted_message = f"{message} [{context_str}]"
    else:
      formatted_message = message

    # Add correlation ID to message
    if correlation_id:
      formatted_message = f"[{correlation_id[:8]}] {formatted_message}"

    # Log
    self._logger.log(level, formatted_message, extra=extra, exc_info=exc_info)

  def debug(self, message: str, **context: Any) -> None:
    """Log debug message.

    Args:
        message: Log message
        **context: Additional context
    """
    self._log(logging.DEBUG, message, **context)

  def info(self, message: str, **context: Any) -> None:
    """Log info message.

    Args:
        message: Log message
        **context: Additional context
    """
    self._log(logging.INFO, message, **context)

  def warning(self, message: str, **context: Any) -> None:
    """Log warning message.

    Args:
        message: Log message
        **context: Additional context
    """
    self._log(logging.WARNING, message, **context)

  def error(self, message: str, *, exc_info: bool = False, **context: Any) -> None:
    """Log error message.

    Args:
        message: Log message
        exc_info: Include exception traceback
        **context: Additional context
    """
    self._log(logging.ERROR, message, exc_info=exc_info, **context)

  def critical(self, message: str, *, exc_info: bool = False, **context: Any) -> None:
    """Log critical message.

    Args:
        message: Log message
        exc_info: Include exception traceback
        **context: Additional context
    """
    self._log(logging.CRITICAL, message, exc_info=exc_info, **context)

  def exception(self, message: str, **context: Any) -> None:
    """Log exception with traceback.

    Args:
        message: Log message
        **context: Additional context
    """
    self._log(logging.ERROR, message, exc_info=True, **context)


class LogBuffer:
  """Circular buffer for storing recent log entries.

  Useful for diagnostics and debugging - keeps last N log entries
  in memory for inspection.

  Examples:
      >>> buffer = LogBuffer(maxlen=1000)
      >>> buffer.add_entry(level="INFO", message="Test")
      >>> recent = buffer.get_recent_entries(10)
  """

  def __init__(self, maxlen: int = 1000) -> None:
    """Initialize log buffer.

    Args:
        maxlen: Maximum number of entries to keep
    """
    self._entries: deque[LogEntry] = deque(maxlen=maxlen)
    self._maxlen = maxlen

  def add_entry(
    self,
    level: str,
    message: str,
    *,
    correlation_id: str | None = None,
    context: dict[str, Any] | None = None,
    exception: str | None = None,
  ) -> None:
    """Add log entry to buffer.

    Args:
        level: Log level
        message: Log message
        correlation_id: Optional correlation ID
        context: Optional context data
        exception: Optional exception info
    """
    entry = LogEntry(
      timestamp=datetime.now(),
      level=level,
      message=message,
      correlation_id=correlation_id,
      context=context or {},
      exception=exception,
    )
    self._entries.append(entry)

  def get_recent_entries(self, count: int = 100) -> list[LogEntry]:
    """Get recent log entries.

    Args:
        count: Number of entries to return

    Returns:
        List of log entries (newest first)
    """
    entries = list(self._entries)
    return entries[-count:][::-1]

  def get_entries_by_correlation_id(self, correlation_id: str) -> list[LogEntry]:
    """Get entries for specific correlation ID.

    Args:
        correlation_id: Correlation ID to filter by

    Returns:
        List of matching log entries
    """
    return [entry for entry in self._entries if entry.correlation_id == correlation_id]

  def get_entries_by_level(self, level: str) -> list[LogEntry]:
    """Get entries by log level.

    Args:
        level: Log level to filter by

    Returns:
        List of matching log entries
    """
    return [entry for entry in self._entries if entry.level == level]

  def clear(self) -> None:
    """Clear all entries."""
    self._entries.clear()

  def get_stats(self) -> dict[str, Any]:
    """Get buffer statistics.

    Returns:
        Statistics dictionary
    """
    level_counts = defaultdict(int)
    for entry in self._entries:
      level_counts[entry.level] += 1

    return {
      "total_entries": len(self._entries),
      "max_entries": self._maxlen,
      "level_counts": dict(level_counts),
    }


# Global log buffer
_log_buffer = LogBuffer(maxlen=1000)


class CorrelationContext:
  """Context manager for request correlation.

  Automatically generates and tracks correlation IDs across
  async operations to trace request flow.

  Examples:
      >>> async with CorrelationContext(dog_id="buddy"):
      ...   await fetch_data()  # All logs get same correlation ID
  """

  def __init__(self, **context: Any) -> None:
    """Initialize correlation context.

    Args:
        **context: Context data to track
    """
    self._correlation_id = str(uuid4())
    self._context = context
    self._token_correlation: contextvars.Token[str | None] | None = None
    self._token_context: contextvars.Token[dict[str, Any]] | None = None

  async def __aenter__(self) -> str:
    """Enter async context.

    Returns:
        Correlation ID
    """
    self._token_correlation = _correlation_id.set(self._correlation_id)
    self._token_context = _request_context.set(self._context)
    return self._correlation_id

  async def __aexit__(
    self,
    exc_type: type[BaseException] | None,
    exc_val: BaseException | None,
    exc_tb: TracebackType | None,
  ) -> None:
    """Exit async context."""
    if self._token_correlation:
      _correlation_id.reset(self._token_correlation)
    if self._token_context:
      _request_context.reset(self._token_context)


def get_correlation_id() -> str | None:
  """Get current correlation ID.

  Returns:
      Correlation ID or None
  """
  return _correlation_id.get()


def set_correlation_id(correlation_id: str) -> None:
  """Set correlation ID.

  Args:
      correlation_id: Correlation ID to set
  """
  _correlation_id.set(correlation_id)


def get_request_context() -> dict[str, Any]:
  """Get current request context.

  Returns:
      Request context dictionary
  """
  return _request_context.get() or {}


def update_request_context(**context: Any) -> None:
  """Update request context.

  Args:
      **context: Context data to add
  """
  current = dict(_request_context.get() or {})
  current.update(context)
  _request_context.set(current)


# Logging decorators


def log_calls(
  logger: StructuredLogger | None = None,
  *,
  log_args: bool = True,
  log_result: bool = False,
  log_duration: bool = True,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
  """Decorator to log function calls.

  Args:
      logger: Logger instance (creates one if None)
      log_args: Whether to log arguments
      log_result: Whether to log result
      log_duration: Whether to log duration

  Returns:
      Decorated function

  Examples:
      >>> @log_calls(log_args=True, log_duration=True)
      ... async def fetch_data(dog_id: str):
      ...   return await api.get(dog_id)
  """

  def decorator(func: Callable[P, T]) -> Callable[P, T]:
    nonlocal logger
    if logger is None:
      logger = StructuredLogger(func.__module__)

    @functools.wraps(func)
    async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
      import time

      # Log call start
      context = {}
      if log_args:
        context["args"] = str(args)
        context["kwargs"] = str(kwargs)

      logger.debug(f"Calling {func.__name__}", **context)

      # Execute
      start = time.time()
      try:
        result = await func(*args, **kwargs)

        # Log result
        result_context = {}
        if log_duration:
          result_context["duration_ms"] = (time.time() - start) * 1000

        if log_result:
          result_context["result"] = str(result)

        logger.debug(f"{func.__name__} completed", **result_context)

        return result

      except Exception as e:
        logger.error(
          f"{func.__name__} failed",
          exc_info=True,
          error=str(e),
          duration_ms=(time.time() - start) * 1000,
        )
        raise

    @functools.wraps(func)
    def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
      import time

      # Log call start
      context = {}
      if log_args:
        context["args"] = str(args)
        context["kwargs"] = str(kwargs)

      logger.debug(f"Calling {func.__name__}", **context)

      # Execute
      start = time.time()
      try:
        result = func(*args, **kwargs)

        # Log result
        result_context = {}
        if log_duration:
          result_context["duration_ms"] = (time.time() - start) * 1000

        if log_result:
          result_context["result"] = str(result)

        logger.debug(f"{func.__name__} completed", **result_context)

        return result

      except Exception as e:
        logger.error(
          f"{func.__name__} failed",
          exc_info=True,
          error=str(e),
          duration_ms=(time.time() - start) * 1000,
        )
        raise

    # Return appropriate wrapper
    import asyncio

    if asyncio.iscoroutinefunction(func):
      return async_wrapper  # type: ignore[return-value]
    return sync_wrapper  # type: ignore[return-value]

  return decorator


# Log buffer integration


def get_recent_logs(count: int = 100) -> list[dict[str, Any]]:
  """Get recent log entries.

  Args:
      count: Number of entries to return

  Returns:
      List of log entries as dictionaries
  """
  entries = _log_buffer.get_recent_entries(count)
  return [entry.to_dict() for entry in entries]


def get_logs_by_correlation_id(correlation_id: str) -> list[dict[str, Any]]:
  """Get logs for specific correlation ID.

  Args:
      correlation_id: Correlation ID

  Returns:
      List of log entries as dictionaries
  """
  entries = _log_buffer.get_entries_by_correlation_id(correlation_id)
  return [entry.to_dict() for entry in entries]


def get_log_stats() -> dict[str, Any]:
  """Get log buffer statistics.

  Returns:
      Statistics dictionary
  """
  return _log_buffer.get_stats()


def clear_log_buffer() -> None:
  """Clear log buffer."""
  _log_buffer.clear()


# Exception formatting


def format_exception_with_context(
  exception: Exception,
  include_traceback: bool = True,
) -> dict[str, Any]:
  """Format exception with context.

  Args:
      exception: Exception to format
      include_traceback: Include traceback

  Returns:
      Formatted exception data
  """
  data: dict[str, Any] = {
    "type": exception.__class__.__name__,
    "message": str(exception),
    "correlation_id": get_correlation_id(),
    "context": get_request_context(),
  }

  if include_traceback:
    data["traceback"] = traceback.format_exc()

  return data
