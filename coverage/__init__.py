"""Small coverage.py shim used for dependency-light test collection."""

from __future__ import annotations


class Coverage:
    def __init__(self, *args, **kwargs) -> None:
        self.args = args
        self.kwargs = kwargs

    def start(self) -> None:
        return None

    def stop(self) -> None:
        return None

    def save(self) -> None:
        return None


__all__ = ["Coverage"]
