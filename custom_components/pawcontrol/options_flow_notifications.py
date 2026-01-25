"""Notification options normalization helpers for the options flow.

This module re-exports the notification options normalizer to keep import paths stable.
"""

from __future__ import annotations

from .flows.notifications import NotificationOptionsNormalizerMixin

__all__ = ["NotificationOptionsNormalizerMixin"]
