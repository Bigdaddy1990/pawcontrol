"""Unit tests for shared aiohttp session validation helpers."""

from functools import wraps

import pytest

from custom_components.pawcontrol.http_client import ensure_shared_client_session


class _NoRequestSession:
    closed = False


class _SyncRequestSession:
    closed = False

    def request(self, *_args: object, **_kwargs: object) -> None:
        return None


class _WrappedRequestSession:
    closed = False

    async def _actual_request(self, *_args: object, **_kwargs: object) -> None:
        return None

    @wraps(_actual_request)
    def request(self, *_args: object, **_kwargs: object):
        return self._actual_request(*_args, **_kwargs)


class _ClosedSession:
    closed = True

    async def request(self, *_args: object, **_kwargs: object) -> None:
        return None


class _ClassCoroutineRequestSession:
    closed = False

    async def request(self, *_args: object, **_kwargs: object) -> None:
        return None


class _RequestFallbackSession:
    closed = "nope"

    def request(self, *_args: object, **_kwargs: object) -> None:
        return None

    async def _request(self, *_args: object, **_kwargs: object) -> None:
        return None


def test_rejects_none_session() -> None:  # noqa: D103
    with pytest.raises(ValueError, match="received None"):
        ensure_shared_client_session(None, owner="test-owner")


def test_rejects_missing_request_callable() -> None:  # noqa: D103
    with pytest.raises(
        ValueError,
        match="without an aiohttp-compatible 'request' coroutine",
    ):
        ensure_shared_client_session(_NoRequestSession(), owner="test-owner")


def test_rejects_sync_request_without_fallback() -> None:  # noqa: D103
    with pytest.raises(
        ValueError,
        match="without an aiohttp-compatible 'request' coroutine",
    ):
        ensure_shared_client_session(_SyncRequestSession(), owner="test-owner")


def test_accepts_wrapped_coroutine_request() -> None:  # noqa: D103
    session = _WrappedRequestSession()

    assert ensure_shared_client_session(session, owner="test-owner") is session


def test_rejects_closed_session() -> None:  # noqa: D103
    with pytest.raises(ValueError, match="received a closed aiohttp ClientSession"):
        ensure_shared_client_session(_ClosedSession(), owner="test-owner")


def test_rejects_instance_override_when_class_request_is_coroutine() -> None:  # noqa: D103
    session = _ClassCoroutineRequestSession()
    session.request = lambda *_args, **_kwargs: None

    with pytest.raises(
        ValueError,
        match="without an aiohttp-compatible 'request' coroutine",
    ):
        ensure_shared_client_session(session, owner="test-owner")


def test_accepts_private_request_coroutine_fallback() -> None:  # noqa: D103
    session = _RequestFallbackSession()

    assert ensure_shared_client_session(session, owner="test-owner") is session
