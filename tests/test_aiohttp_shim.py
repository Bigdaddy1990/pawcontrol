"""Coverage tests for local ``aiohttp`` compatibility shims."""

from __future__ import annotations

import asyncio
import json

from aiohttp import ClientResponse, ClientSession
from aiohttp.test_utils import (
    RawTestServer as _RawTestServer,
    TestClient as _TestClient,
    TestServer as _TestServer,
)
from aiohttp.web import Application, BaseRequest, Request, json_response


def test_client_session_and_response_defaults() -> None:
    """ClientSession returns response objects with stable default payloads."""
    session = ClientSession()
    response = asyncio.run(session.request("GET", "https://example.test"))

    assert isinstance(response, ClientResponse)
    assert asyncio.run(response.json()) == {}
    assert asyncio.run(response.text()) == ""


def test_web_json_response_encodes_payload_with_status() -> None:
    """json_response serializes payloads for webhook tests and fixtures."""
    response = json_response({"ok": True, "count": 2}, status=201)

    assert response.status == 201
    assert json.loads(response.body.decode("utf-8")) == {"ok": True, "count": 2}


def test_test_utils_servers_and_client_store_wrapped_objects() -> None:
    """Test utility wrappers retain app/handler references for fixture wiring."""

    async def handler(_request: BaseRequest) -> object:
        return object()

    app = Application(example="value")
    test_server = _TestServer(app)
    raw_server = _RawTestServer(handler)
    client = _TestClient(test_server)

    assert isinstance(test_server.app, Application)
    assert test_server.app["example"] == "value"
    assert raw_server.handler is handler
    assert client.server is test_server
    assert Request.__mro__[1] is BaseRequest
