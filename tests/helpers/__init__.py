"""Shared test helpers for the PawControl integration."""

from __future__ import annotations

from copy import deepcopy
from typing import TypeVar

from . import homeassistant_test_stubs
from .homeassistant_test_stubs import (
    ConfigEntryNotReady,
    HomeAssistantError,
    install_homeassistant_stubs,
)

__all__ = [
    "ConfigEntryNotReady",
    "HomeAssistantError",
    "homeassistant_test_stubs",
    "install_homeassistant_stubs",
    "typed_deepcopy",
]

T = TypeVar("T")


def typed_deepcopy[T](value: T) -> T:
    """Return a type-preserving deep copy for complex fixtures."""

    return deepcopy(value)
