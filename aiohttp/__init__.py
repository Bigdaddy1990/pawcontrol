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

    closed = False

    async def request(self, *_args: Any, **_kwargs: Any) -> ClientResponse:
        """Return a generic successful response for all request calls."""
        return ClientResponse()


__all__ = [
    "ClientError",
    "ClientResponse",
    "ClientSession",
    "ClientTimeout",
    "ContentTypeError",
]
