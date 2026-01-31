"""Config flow entrypoint for PawControl.

The full config flow implementation lives in :mod:`.config_flow_main`.
This shim exists to keep the Home Assistant entry module small and stable.
"""

from __future__ import annotations

from typing import Final, Literal

from .config_flow_main import ConfigFlow, PawControlConfigFlow

__all__: Final[tuple[Literal["ConfigFlow"], Literal["PawControlConfigFlow"]]] = (
  "ConfigFlow",
  "PawControlConfigFlow",
)
