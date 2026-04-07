"""Lightweight aiohttp compatibility shim for unit test collection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .client_exceptions import ClientError, ContentTypeError


@dataclass(slots=True)
class ClientTimeout:
    total: float | None = None


class ClientResponse:
    """Minimal response contract used by tests."""

    status: int = 200
    headers: dict[str, str]

    def __init__(self) -> None:
        self.headers = {}

    async def json(self) -> Any:
        return {}

    async def text(self) -> str:
        return ""


class ClientSession:
    """Minimal client session stub."""

    closed = False

    async def request(self, *_args: Any, **_kwargs: Any) -> ClientResponse:
        return ClientResponse()


__all__ = [
    "ClientError",
    "ClientResponse",
    "ClientSession",
    "ClientTimeout",
    "ContentTypeError",
]
