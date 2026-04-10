"""Minimal aiohttp.test_utils compatibility layer for pytest plugin loading."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any


class BaseTestServer:
    """No-op base server used by the local aiohttp compatibility shim."""

    @classmethod
    def __class_getitem__(cls, _item: object) -> type[BaseTestServer]:
        """Support runtime generic aliases used by pytest-aiohttp annotations."""
        return cls

    async def start_server(self) -> None:
        """Start the stub server."""

    async def close(self) -> None:
        """Close the stub server."""


class TestServer(BaseTestServer):
    """Server wrapper for aiohttp-style application callables."""

    def __init__(self, app: Any, *_args: Any, **_kwargs: Any) -> None:
        """Store the wrapped application object."""
        self.app = app


class RawTestServer(BaseTestServer):
    """Server wrapper for raw aiohttp-style handlers."""

    def __init__(
        self,
        handler: Callable[..., Awaitable[Any]],
        *_args: Any,
        **_kwargs: Any,
    ) -> None:
        """Store the wrapped raw request handler."""
        self.handler = handler


class TestClient:
    """No-op test client matching the interface used by pytest-aiohttp."""

    @classmethod
    def __class_getitem__(cls, _item: object) -> type[TestClient]:
        """Support runtime generic aliases used by pytest-aiohttp annotations."""
        return cls

    def __init__(self, server: BaseTestServer, *_args: Any, **_kwargs: Any) -> None:
        """Store the server instance used by the client wrapper."""
        self.server = server

    async def start_server(self) -> None:
        """Start the wrapped server."""
        await self.server.start_server()

    async def close(self) -> None:
        """Close the wrapped server."""
        await self.server.close()
