"""Helpers for tracking performance metrics across PawControl tasks.

Simplified to lightweight logging with no persistent duration history.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from time import perf_counter
from typing import Any, Literal

from .types import CacheDiagnosticsCapture, PawControlRuntimeData

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class PerformanceResult:
  """Simple result container for tracked blocks."""

  success: bool = True
  error: Exception | None = None

  def mark_failure(self, error: Exception | None = None) -> None:
    self.success = False
    self.error = error


@contextmanager
def performance_tracker(
  runtime_data: PawControlRuntimeData | None,
  bucket_name: str,
  *,
  max_samples: int = 50,
) -> Iterator[PerformanceResult]:
  """Lightweight performance logger for long-running operations."""

  del runtime_data, max_samples
  start = perf_counter()
  result = PerformanceResult()

  try:
    yield result
  except Exception as err:
    result.mark_failure(err)
    raise
  finally:
    duration_s = perf_counter() - start
    if duration_s > 1.0:
      _LOGGER.debug("Task %s took %.2fs", bucket_name, duration_s)


def capture_cache_diagnostics(
  runtime_data: PawControlRuntimeData | None,
) -> CacheDiagnosticsCapture | None:
  """Cache diagnostics are disabled in minimal mode."""

  del runtime_data
  return None


def record_maintenance_result(
  runtime_data: PawControlRuntimeData | None,
  *,
  task: str,
  status: Literal["success", "error"],
  message: str | None = None,
  diagnostics: CacheDiagnosticsCapture | None = None,
  metadata: Mapping[str, Any] | None = None,
  details: Mapping[str, Any] | None = None,
) -> None:
  """Log maintenance results instead of storing telemetry history."""

  del runtime_data, diagnostics, metadata, details
  if status == "error":
    _LOGGER.warning("Maintenance task %s failed: %s", task, message or "unknown error")
  else:
    _LOGGER.debug("Maintenance task %s succeeded", task)
