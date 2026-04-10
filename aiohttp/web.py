"""Minimal aiohttp.web compatibility helpers for local unit tests."""

from dataclasses import dataclass
import json
from typing import Any


class BaseRequest:
    """Base request placeholder for type compatibility."""


class Request(BaseRequest):
    """Request placeholder for type compatibility."""


class Application(dict[str, Any]):
    """Dictionary-like app container used by pytest-aiohttp fixtures."""


@dataclass(slots=True)
class Response:
    """Simple JSON response object matching aiohttp attributes used in tests."""

    status: int = 200
    body: bytes = b""


def json_response(payload: dict[str, Any], *, status: int = 200) -> Response:
    """Encode a dictionary payload into a response-like object."""
    return Response(status=status, body=json.dumps(payload).encode("utf-8"))
