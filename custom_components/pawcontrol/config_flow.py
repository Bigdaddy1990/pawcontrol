"""Config flow entrypoint for PawControl.

The full config flow implementation lives in :mod:`.config_flow_main`.
This shim exists to keep the Home Assistant entry module small and stable.
"""

from __future__ import annotations

from .config_flow_main import ConfigFlow, PawControlConfigFlow
from .config_flow_placeholders import (
    _build_add_another_placeholders,
    _build_add_dog_summary_placeholders,
    _build_dog_modules_form_placeholders,
)

__all__ = [
    "ConfigFlow",
    "PawControlConfigFlow",
    "_build_add_another_placeholders",
    "_build_add_dog_summary_placeholders",
    "_build_dog_modules_form_placeholders",
]
