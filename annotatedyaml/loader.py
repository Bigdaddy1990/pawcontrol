"""Loader stub patched by tests."""

from __future__ import annotations

from typing import Any
def load_yaml(path: str) -> Any:  # pragma: no cover - replaced during tests

def load_yaml(path: str) -> Any:  # pragma: no cover - replaced during tests
    raise NotImplementedError(
        "annotatedyaml.loader.load_yaml is patched by the hassfest tests"
    )


__all__ = ["load_yaml"]
