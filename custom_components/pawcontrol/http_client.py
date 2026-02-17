"""Helpers for working with Home Assistant's shared aiohttp session."""

from collections.abc import Callable
from inspect import iscoroutinefunction, unwrap
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
    """  # noqa: E111

    if session is None:  # noqa: E111
        raise ValueError(
            f"{owner} requires Home Assistant's shared aiohttp ClientSession; received None.",
        )

    request = getattr(session, "request", None)  # noqa: E111
    if not callable(request):  # noqa: E111
        raise ValueError(
            f"{owner} received an object without an aiohttp-compatible 'request' coroutine.",
        )

    def _is_coroutine(func: Callable[..., Any] | None) -> bool:  # noqa: E111
        if func is None:
            return False  # noqa: E111

        candidate = unwrap(getattr(func, "__func__", func))

        return iscoroutinefunction(candidate)

    request_attr = getattr(type(session), "request", None)  # noqa: E111

    if (  # noqa: E111
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

    closed_attr = getattr(session, "closed", False)  # noqa: E111
    closed = closed_attr if isinstance(closed_attr, bool) else False  # noqa: E111
    if closed:  # noqa: E111
        raise ValueError(
            f"{owner} received a closed aiohttp ClientSession. Inject Home Assistant's managed session instead.",  # noqa: E501
        )

    return cast(ClientSession, session)  # noqa: E111


__all__ = ["ensure_shared_client_session"]
