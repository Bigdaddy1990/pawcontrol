"""Utilities for building configuration and option schemas."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

import voluptuous as vol

from .const import CONF_CREATE_DASHBOARD
from .module_registry import MODULES

if TYPE_CHECKING:
    from collections.abc import Mapping


def build_module_schema(data: Mapping[str, Any] | None = None) -> dict[Any, Any]:
    """Create schema entries for module toggles.

    When ``data`` is provided, values are taken as defaults; otherwise the
    module's default value is used.
    """

    defaults = data or {}
    schema: dict[Any, Any] = {
        vol.Optional(key, default=defaults.get(key, module.default)): bool
        for key, module in MODULES.items()
    }
    schema[vol.Optional(
        CONF_CREATE_DASHBOARD, default=defaults.get(CONF_CREATE_DASHBOARD, False)
    )] = bool
    return schema

