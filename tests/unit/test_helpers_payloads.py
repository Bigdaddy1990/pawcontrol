"""Unit tests for :mod:`tests.helpers`."""

from __future__ import annotations

from typing import TypedDict

import pytest
from tests.helpers import typed_deepcopy


class _ExamplePayload(TypedDict):
  """TypedDict that mimics a FeedingManager setup payload snippet."""

  dog_id: str
  modules: dict[str, bool]


@pytest.mark.unit
def test_typed_deepcopy_returns_fully_detached_clone() -> None:
  """Ensure ``typed_deepcopy`` returns a deep copy that preserves typing."""

  original: _ExamplePayload = {
    "dog_id": "buddy",
    "modules": {"feeding": True, "walk": True},
  }

  clone = typed_deepcopy(original)

  assert clone == original
  assert clone is not original
  assert clone["modules"] is not original["modules"]

  clone["modules"]["walk"] = False

  assert original["modules"]["walk"] is True
