"""Minimal aiohttp.web_protocol compatibility helpers."""

from collections.abc import Awaitable, Callable
from typing import Any

_RequestHandler = Callable[[Any], Awaitable[Any]]
