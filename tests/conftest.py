import pytest
from homeassistant.core import HomeAssistant


@pytest.fixture
def anyio_backend():
    return "asyncio"
