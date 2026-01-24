"""GPS and geofencing configuration steps for Paw Control options flow.

This module re-exports the shared GPS mixin to keep import paths stable.
"""

from __future__ import annotations

from .flows.flow_gps import GPSOptionsMixin

__all__ = ["GPSOptionsMixin"]
