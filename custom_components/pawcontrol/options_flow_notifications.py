"""Notification configuration steps for Paw Control options flow.

This module re-exports the shared notifications mixin to keep import paths stable.
"""

from __future__ import annotations

from .flows.flow_notifications import NotificationOptionsMixin

__all__ = ["NotificationOptionsMixin"]
