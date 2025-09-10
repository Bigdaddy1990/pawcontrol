"""Minimal test scaffolding for Home Assistant components.

If the real Home Assistant package isn't available, this module
creates lightweight stand‑ins for the parts of the API used in tests.
"""

from __future__ import annotations

import os
import sys
from enum import StrEnum
from types import ModuleType
from typing import Callable

# Prevent unexpected plugins from loading during test collection
os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"

try:  # pragma: no cover - prefer real Home Assistant when present
    import homeassistant  # noqa: F401
except Exception:  # pragma: no cover - fall back to minimal stubs
    ha = sys.modules.setdefault("homeassistant", ModuleType("homeassistant"))
    ha.__path__ = []

    helpers = ModuleType("homeassistant.helpers")
    helpers.__path__ = []
    ha.helpers = helpers
    sys.modules["homeassistant.helpers"] = helpers

    # ---- config validation -------------------------------------------------
    config_validation = ModuleType("homeassistant.helpers.config_validation")
    helpers.config_validation = config_validation
    sys.modules["homeassistant.helpers.config_validation"] = config_validation

    def ensure_list(value):  # pragma: no cover
        return [] if value is None else (value if isinstance(value, list) else [value])

    def config_entry_only_config_schema(domain):
        def schema(config):
            return config

        return schema

    config_validation.ensure_list = ensure_list
    config_validation.config_entry_only_config_schema = config_entry_only_config_schema
    config_validation.string = str
    config_validation.boolean = bool

    # ---- typing ------------------------------------------------------------
    helpers_typing = ModuleType("homeassistant.helpers.typing")
    helpers_typing.ConfigType = dict
    helpers.typing = helpers_typing
    sys.modules["homeassistant.helpers.typing"] = helpers_typing

    # ---- selector ----------------------------------------------------------
    selector = ModuleType("homeassistant.helpers.selector")
    helpers.selector = selector
    sys.modules["homeassistant.helpers.selector"] = selector

    class BooleanSelector:  # pragma: no cover - simple placeholder
        def __init__(self, *args, **kwargs):
            pass

    class NumberSelector:  # pragma: no cover - simple placeholder
        def __init__(self, *args, **kwargs):
            pass

    class NumberSelectorMode(StrEnum):  # pragma: no cover
        BOX = "box"

    class NumberSelectorConfig:  # pragma: no cover
        def __init__(self, *args, **kwargs):
            pass

    class SelectSelector:  # pragma: no cover - simple placeholder
        def __init__(self, *args, **kwargs):
            pass

    class SelectSelectorMode(StrEnum):  # pragma: no cover
        DROPDOWN = "dropdown"

    class SelectSelectorConfig:  # pragma: no cover
        def __init__(self, *args, **kwargs):
            pass

    def _selector(cfg):
        return cfg

    selector.BooleanSelector = BooleanSelector
    selector.NumberSelector = NumberSelector
    selector.NumberSelectorMode = NumberSelectorMode
    selector.NumberSelectorConfig = NumberSelectorConfig
    selector.SelectSelector = SelectSelector
    selector.SelectSelectorMode = SelectSelectorMode
    selector.SelectSelectorConfig = SelectSelectorConfig
    selector.selector = _selector

    # ---- entity platform ---------------------------------------------------
    entity_platform = ModuleType("homeassistant.helpers.entity_platform")
    helpers.entity_platform = entity_platform
    sys.modules["homeassistant.helpers.entity_platform"] = entity_platform
    entity_platform.AddEntitiesCallback = Callable[..., None]

    # ---- storage -----------------------------------------------------------
    storage = ModuleType("homeassistant.helpers.storage")
    helpers.storage = storage
    sys.modules["homeassistant.helpers.storage"] = storage

    class Store:  # pragma: no cover - minimal in-memory store
        def __init__(self, *args, **kwargs):
            self.data = None

        async def async_load(self):
            return self.data

        async def async_save(self, data):
            self.data = data

    storage.Store = Store
