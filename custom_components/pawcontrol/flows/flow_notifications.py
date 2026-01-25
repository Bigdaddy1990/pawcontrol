"""Notification flow mixins for Paw Control.

This module re-exports the shared notification helpers to keep import paths stable.
"""

from __future__ import annotations

from .notifications import NotificationOptionsMixin

__all__ = ["NotificationOptionsMixin"]
