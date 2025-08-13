import asyncio
import sys
import types
from collections.abc import Generator

import pytest

try:  # pragma: no cover - fallback when Home Assistant isn't installed
    from homeassistant.core import HomeAssistant
except ModuleNotFoundError:  # pragma: no cover
    ha_core = types.ModuleType("homeassistant.core")

    class HomeAssistant:  # minimal stub for tests
        pass

    class ServiceCall:  # minimal stub for tests
        pass

    ha_core.HomeAssistant = HomeAssistant
    ha_core.ServiceCall = ServiceCall
    sys.modules.setdefault("homeassistant", types.ModuleType("homeassistant"))
    sys.modules["homeassistant.core"] = ha_core


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
