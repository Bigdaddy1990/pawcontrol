import pytest  # noqa: D100

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


class _SessionUsingPrivateRequestFallback:
    closed = False

    def request(self, *_args, **_kwargs):
        return None

    async def _request(self, *_args, **_kwargs):
        return None


class _SessionWithNonBooleanClosed(_ValidSession):
    closed = "yes"


def test_ensure_shared_client_session_rejects_none() -> None:  # noqa: D103
    with pytest.raises(ValueError, match="received None"):
        ensure_shared_client_session(None, owner="test")


def test_ensure_shared_client_session_rejects_missing_request_coroutine() -> None:  # noqa: D103
    with pytest.raises(ValueError, match="aiohttp-compatible 'request' coroutine"):
        ensure_shared_client_session(_NoRequestCallable(), owner="test")


def test_ensure_shared_client_session_rejects_shadowed_sync_request() -> None:  # noqa: D103
    with pytest.raises(ValueError, match="aiohttp-compatible 'request' coroutine"):
        ensure_shared_client_session(_RequestShadowingSession(), owner="test")


def test_ensure_shared_client_session_rejects_sync_request_no_async_fallback() -> None:  # noqa: D103
    with pytest.raises(ValueError, match="aiohttp-compatible 'request' coroutine"):
        ensure_shared_client_session(
            _SyncRequestWithoutCoroutineFallback(),
            owner="test",
        )


def test_ensure_shared_client_session_rejects_closed_sessions() -> None:  # noqa: D103
    with pytest.raises(
        ValueError,
        match="received a closed aiohttp ClientSession",
    ):
        ensure_shared_client_session(_ClosedValidSession(), owner="test")


def test_ensure_shared_client_session_accepts_valid_session() -> None:  # noqa: D103
    session = _ValidSession()

    assert ensure_shared_client_session(session, owner="test") is session


def test_ensure_shared_client_session_accepts_private_request_fallback() -> None:
    """aiohttp-like sessions may expose the coroutine on ``_request`` only."""
    session = _SessionUsingPrivateRequestFallback()

    assert ensure_shared_client_session(session, owner="test") is session


def test_ensure_shared_client_session_ignores_non_boolean_closed_flag() -> None:
    """Non-boolean ``closed`` attributes should not force a false positive."""
    session = _SessionWithNonBooleanClosed()

    assert ensure_shared_client_session(session, owner="test") is session
