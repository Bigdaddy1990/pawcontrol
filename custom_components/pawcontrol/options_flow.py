"""Options flow entrypoint for PawControl.

The full options flow implementation lives in :mod:`.options_flow_main`.
This shim exists to keep the Home Assistant entry module small and stable.
"""

from __future__ import annotations

from typing import Final, Literal

from .options_flow_main import PawControlOptionsFlow

__all__: Final[tuple[Literal["PawControlOptionsFlow"]]] = ("PawControlOptionsFlow",)
