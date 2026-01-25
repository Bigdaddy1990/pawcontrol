"""GPS defaults for the PawControl config flow.

This module re-exports the GPS defaults mixin to keep import paths stable.
"""

from __future__ import annotations

from .flows.gps import GPSModuleDefaultsMixin

__all__ = ["GPSModuleDefaultsMixin"]
