import pytest

from custom_components.pawcontrol.http_client import ensure_shared_client_session


class _ValidSession:
    closed = False

    async def request(self, *_args, **_kwargs):
        return None


class _NoRequestCallable:
    request = "nope"
    closed = False


class _RequestShadowingSession:
    closed = False

    async def request(self, *_args, **_kwargs):
        return None

    def __init__(self) -> None:
        self.request = lambda *_args, **_kwargs: None


class _SyncRequestWithoutCoroutineFallback:
    closed = False

    def request(self, *_args, **_kwargs):
        return None


class _ClosedValidSession(_ValidSession):
    closed = True


def test_ensure_shared_client_session_rejects_none() -> None:
    with pytest.raises(ValueError, match="received None"):
        ensure_shared_client_session(None, owner="test")


def test_ensure_shared_client_session_rejects_missing_request_coroutine() -> None:
    with pytest.raises(ValueError, match="aiohttp-compatible 'request' coroutine"):
        ensure_shared_client_session(_NoRequestCallable(), owner="test")


def test_ensure_shared_client_session_rejects_shadowed_sync_request() -> None:
    with pytest.raises(ValueError, match="aiohttp-compatible 'request' coroutine"):
        ensure_shared_client_session(_RequestShadowingSession(), owner="test")


def test_ensure_shared_client_session_rejects_sync_request_no_async_fallback() -> None:
    with pytest.raises(ValueError, match="aiohttp-compatible 'request' coroutine"):
        ensure_shared_client_session(
            _SyncRequestWithoutCoroutineFallback(),
            owner="test",
        )


def test_ensure_shared_client_session_rejects_closed_sessions() -> None:
    with pytest.raises(
        ValueError,
        match="received a closed aiohttp ClientSession",
    ):
        ensure_shared_client_session(_ClosedValidSession(), owner="test")


def test_ensure_shared_client_session_accepts_valid_session() -> None:
    session = _ValidSession()

    assert ensure_shared_client_session(session, owner="test") is session
