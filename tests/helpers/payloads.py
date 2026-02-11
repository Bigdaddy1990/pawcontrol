"""Payload helper utilities for tests."""

from __future__ import annotations

from copy import deepcopy
from typing import TypeVar

T = TypeVar("T")


def typed_deepcopy[T](value: T) -> T:
    """Return a type-preserving deep copy for complex fixtures."""

    return deepcopy(value)
