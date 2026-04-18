"""Lightweight aiohttp compatibility shim for unit test collection."""

from dataclasses import dataclass
from typing import Any

from .client_exceptions import ClientError, ContentTypeError


@dataclass(slots=True)
class ClientTimeout:
    """Compatibility timeout container for test-only HTTP calls."""

    total: float | None = None


class ClientResponse:
    """Minimal response contract used by tests."""

    status: int = 200
    headers: dict[str, str]

    def __init__(self) -> None:
        """Initialise a default successful response shell."""
        self.headers = {}

    async def json(self) -> Any:
        """Return an empty JSON payload for shimmed responses."""
        return {}

    async def text(self) -> str:
        """Return an empty textual payload for shimmed responses."""
        return ""


class ClientSession:
    """Minimal client session stub."""

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        """Accept real-session constructor signatures used by tests."""
        self.closed = False

    async def request(self, *_args: Any, **_kwargs: Any) -> ClientResponse:
        """Return a generic successful response for all request calls."""
        return ClientResponse()

    async def close(self) -> None:
        """Mirror aiohttp session shutdown semantics for tests."""
        self.closed = True

    async def __aenter__(self) -> ClientSession:
        """Support ``async with ClientSession()`` patterns in tests."""
        return self

    async def __aexit__(self, *_args: Any) -> None:
        """Close the session when context manager scope exits."""
        await self.close()


__all__ = [
    "ClientError",
    "ClientResponse",
    "ClientSession",
    "ClientTimeout",
    "ContentTypeError",
]
