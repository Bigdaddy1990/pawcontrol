"""Typed payload helpers for PawControl tests."""

from __future__ import annotations

from copy import deepcopy
from typing import cast


def typed_deepcopy[T](payload: T) -> T:
    """Return a deep copy of ``payload`` that preserves static typing."""

    return cast(T, deepcopy(payload))
