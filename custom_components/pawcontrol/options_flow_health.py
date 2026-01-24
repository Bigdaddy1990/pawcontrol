"""Health configuration steps for Paw Control options flow.

This module re-exports the shared health mixin to keep import paths stable.
"""

from __future__ import annotations

from .flows.flow_health import HealthOptionsMixin

__all__ = ["HealthOptionsMixin"]
