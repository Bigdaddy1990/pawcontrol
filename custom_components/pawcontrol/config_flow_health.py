"""Health summary helpers for the PawControl config flow.

This module re-exports the shared health summary mixin to keep import paths stable.
"""

from __future__ import annotations

from .flows.health import HealthSummaryMixin

__all__ = ["HealthSummaryMixin"]
