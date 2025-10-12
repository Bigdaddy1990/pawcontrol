"""Integration-level fixtures for PawControl tests."""

from __future__ import annotations

import importlib
import sys
from collections.abc import Iterator
from types import ModuleType

import pytest
from tests.helpers.homeassistant_test_stubs import install_homeassistant_stubs

MODULE_NAME = "custom_components.pawcontrol.config_flow"


def _reload_config_flow_module() -> ModuleType:
    """Reload the PawControl config flow so it inherits the active stub base."""

    module = sys.modules.get(MODULE_NAME)
    if module is None:
        module = importlib.import_module(MODULE_NAME)
    else:
        module = importlib.reload(module)

    module.ConfigFlow = module.PawControlConfigFlow
    module.ConfigFlow.__doc__ = (
        "Compatibility alias for Home Assistant's config flow loader."
    )
    return module


@pytest.fixture(autouse=True)
def ensure_config_flow_registered() -> Iterator[None]:
    """Ensure Home Assistant stubs and the config flow alias stay aligned."""

    install_homeassistant_stubs()
    _reload_config_flow_module()
    yield
