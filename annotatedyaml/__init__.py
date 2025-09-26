"""Minimal stub of the ``annotatedyaml`` package for tests."""

from __future__ import annotations

from typing import Optional

__all__ = ["SECRET_YAML", "Input", "YamlTypeError"]

SECRET_YAML = "!secret"


class YamlTypeError(TypeError):
    """Exception raised when YAML content cannot be parsed."""


class Input(str):
    """Lightweight replacement for :class:`annotatedyaml.Input`.

    The real ``annotatedyaml`` package keeps track of the origin of YAML
    values.  For the purposes of the test-suite we only need an object that
    behaves like a string and optionally stores line/column information.
    """
    __slots__ = ("_column", "_line")
    __slots__ = ("_column", "_line")

    def __new__(
        cls,
        value: str,
        line: int | None = None,
        column: int | None = None,
    ) -> Input:
        obj = super().__new__(cls, value)
        obj._line = line
        obj._column = column
        return obj

    @property
    def line(self) -> int | None:
        """Return the line number associated with the value, if available."""

        return self._line

    @property
    def column(self) -> int | None:
        """Return the column number associated with the value, if available."""

        return self._column
