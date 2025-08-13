import asyncio
from collections.abc import Generator

import pytest
from homeassistant.core import HomeAssistant


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def enable_event_loop_debug() -> Generator[None, None, None]:
    """Ensure an event loop exists and enable debug mode for tests."""
    created_loop = False
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        created_loop = True
    loop.set_debug(True)
    try:
        yield
    finally:
        if created_loop:
            loop.close()
            asyncio.set_event_loop(None)
