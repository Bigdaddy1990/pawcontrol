"""Unit tests for :mod:`tests.helpers`."""

from __future__ import annotations

from typing import TypedDict

import pytest
from tests.helpers import typed_deepcopy


class _ExamplePayload(TypedDict):
  """TypedDict that mimics a FeedingManager setup payload snippet."""  # noqa: E111

  dog_id: str  # noqa: E111
  modules: dict[str, bool]  # noqa: E111


@pytest.mark.unit
def test_typed_deepcopy_returns_fully_detached_clone() -> None:
  """Ensure ``typed_deepcopy`` returns a deep copy that preserves typing."""  # noqa: E111

  original: _ExamplePayload = {  # noqa: E111
    "dog_id": "buddy",
    "modules": {"feeding": True, "walk": True},
  }

  clone = typed_deepcopy(original)  # noqa: E111

  assert clone == original  # noqa: E111
  assert clone is not original  # noqa: E111
  assert clone["modules"] is not original["modules"]  # noqa: E111

  clone["modules"]["walk"] = False  # noqa: E111

  assert original["modules"]["walk"] is True  # noqa: E111
