"""Config flow entrypoint for PawControl.

The full config flow implementation lives in :mod:`.config_flow_main`.
This shim exists to keep the Home Assistant entry module small and stable.
"""
from __future__ import annotations

from .config_flow_main import ConfigFlow
from .config_flow_main import PawControlConfigFlow

__all__ = ['ConfigFlow', 'PawControlConfigFlow']
