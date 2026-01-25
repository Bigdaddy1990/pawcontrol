"""Options flow entrypoint for PawControl.

The full options flow implementation lives in :mod:`.options_flow_main`.
This shim exists to keep the Home Assistant entry module small and stable.
"""

from __future__ import annotations

from .options_flow_main import PawControlOptionsFlow

__all__ = [
  "PawControlOptionsFlow",
]
