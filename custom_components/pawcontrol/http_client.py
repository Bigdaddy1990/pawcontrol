"""Helpers for working with Home Assistant's shared aiohttp session."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from inspect import unwrap
from typing import Any, cast

from aiohttp import ClientSession


def ensure_shared_client_session(session: Any, *, owner: str) -> ClientSession:
  """Validate that a helper received Home Assistant's shared session.

  Args:
      session: Object expected to behave like :class:`aiohttp.ClientSession`.
      owner: Human readable name of the consumer for error messages.

  Returns:
      The validated session cast to :class:`aiohttp.ClientSession`.

  Raises:
      ValueError: If ``session`` is ``None``, closed, or does not look like an
          aiohttp client session. The error message explains what the helper
          should receive instead.
  """

  if session is None:
    raise ValueError(
      f"{owner} requires Home Assistant's shared aiohttp ClientSession; received None.",
    )

  request = getattr(session, "request", None)
  if not callable(request):
    raise ValueError(
      f"{owner} received an object without an aiohttp-compatible 'request' coroutine.",
    )

  def _is_coroutine(func: Callable[..., Any] | None) -> bool:
    if func is None:
      return False

    candidate = unwrap(getattr(func, "__func__", func))

    return asyncio.iscoroutinefunction(candidate)

  request_attr = getattr(type(session), "request", None)

  if (
    not _is_coroutine(request)
    and not _is_coroutine(request_attr)
    and (
      not callable(request_attr)
      or (
        not _is_coroutine(getattr(session, "_request", None))
        and not _is_coroutine(getattr(type(session), "_request", None))
      )
    )
  ):
    # ``aiohttp.ClientSession.request`` is a thin synchronous wrapper around the
    # private ``_request`` coroutine. Accept this pattern to avoid rejecting the
    # managed Home Assistant session while still guarding synchronous callables.
    raise ValueError(
      f"{owner} received an object without an aiohttp-compatible 'request' coroutine.",
    )

  closed_attr = getattr(session, "closed", False)
  closed = closed_attr if isinstance(closed_attr, bool) else False
  if closed:
    raise ValueError(
      f"{owner} received a closed aiohttp ClientSession. Inject Home Assistant's managed session instead.",
    )

  return cast(ClientSession, session)


__all__ = ["ensure_shared_client_session"]
