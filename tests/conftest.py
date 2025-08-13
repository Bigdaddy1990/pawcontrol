import pytest
from homeassistant.core import HomeAssistant


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"
