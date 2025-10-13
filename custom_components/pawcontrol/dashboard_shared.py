"""Shared helpers and typing aliases for PawControl dashboard orchestration."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

type CardConfig = dict[str, Any]
type CardCollection = list[CardConfig]

__all__ = ["CardCollection", "CardConfig", "unwrap_async_result"]


def unwrap_async_result[T](
    result: T | BaseException,
    *,
    context: str,
    logger: logging.Logger,
    level: int = logging.WARNING,
    suppress_cancelled: bool = False,
) -> T | None:
    """Return ``result`` when successful, logging and returning ``None`` otherwise.

    Args:
        result: Payload produced by an ``asyncio.gather`` call.
        context: Human-readable context explaining the gather operation.
        logger: Logger used to emit cancellation and error details.
        level: Logging level for non-fatal failures.
        suppress_cancelled: When ``True`` cancelled tasks are logged instead of
            re-raised.

    Returns:
        The successful payload when ``result`` is not an exception, otherwise
        ``None``.

    Raises:
        asyncio.CancelledError: Raised when a gather task is cancelled and
            ``suppress_cancelled`` is ``False``.
    """

    if isinstance(result, asyncio.CancelledError):
        if suppress_cancelled:
            logger.log(level, "%s: task cancelled", context)
            return None
        raise result

    if isinstance(result, BaseException):
        logger.log(
            level,
            "%s: %s",
            context,
            result,
            exc_info=(type(result), result, result.__traceback__),
        )
        return None

    return result
