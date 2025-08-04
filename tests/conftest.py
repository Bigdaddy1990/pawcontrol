# conftest.py – globale Test-Hooks für pytest
import pytest

@pytest.fixture(scope="session")
def basic_config():
    return {"dummy": True}
