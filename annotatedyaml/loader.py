"""Loader stub patched by tests."""

from __future__ import annotations


def load_yaml(path: str):  # pragma: no cover - replaced during tests
    raise NotImplementedError(
        "annotatedyaml.loader.load_yaml is patched by the hassfest tests"
    )


__all__ = ["load_yaml"]
