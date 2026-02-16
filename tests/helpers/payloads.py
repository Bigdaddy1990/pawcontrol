"""Payload helper utilities for tests."""

from copy import deepcopy
from typing import TypeVar

T = TypeVar("T")


def typed_deepcopy[T](value: T) -> T:
  """Return a type-preserving deep copy for complex fixtures."""  # noqa: E111

  return deepcopy(value)  # noqa: E111
