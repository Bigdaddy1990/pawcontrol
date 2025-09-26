"""Loader utilities for the ``annotatedyaml`` stub package."""

from __future__ import annotations

from typing import Any

from . import Input

__all__ = ["load_yaml"]


def load_yaml(source: str | Input) -> Any:
    """Placeholder implementation compatible with Home Assistant tests.

    The real ``annotatedyaml`` package exposes ``load_yaml`` which returns a
    parsed representation of the provided YAML document.  The Home Assistant
    tests in this repository patch this function, so the implementation here is
    never executed.  It simply raises ``NotImplementedError`` to signal that the
    stub does not perform real YAML parsing.
    """

    raise NotImplementedError("annotatedyaml.loader.load_yaml is a stub")