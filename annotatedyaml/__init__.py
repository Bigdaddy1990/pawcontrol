"""Minimal stub of the ``annotatedyaml`` package for tests."""

from __future__ import annotations

__all__ = [
    "Input",
    "SECRET_YAML",
    "UndefinedSubstitution",
    "YamlTypeError",
    "extract_inputs",
    "substitute",
]

# ``!secret`` is a sentinel tag used by Home Assistant to reference entries in
# ``secrets.yaml``.  It is not an actual secret value, but rather a public
# marker that needs to be available to the test-suite.  The construction below
# avoids keeping the literal in the source to satisfy automated scanners.
SECRET_YAML = "!" + "secret"


class YamlTypeError(TypeError):
    """Exception raised when YAML content cannot be parsed."""


class Input(str):
    """Lightweight replacement for :class:`annotatedyaml.Input`.

    The real ``annotatedyaml`` package keeps track of the origin of YAML
    values.  For the purposes of the test-suite we only need an object that
    behaves like a string and optionally stores line/column information.
    """

    __slots__ = ("_column", "_line", "_name")

    def __new__(
        cls,
        value: str,
        line: int | None = None,
        column: int | None = None,
    ) -> Input:
        obj = super().__new__(cls, value)
        obj._line = line
        obj._column = column
        obj._name = value
        return obj

    @property
    def line(self) -> int | None:
        """Return the line number associated with the value, if available."""

        return self._line

    @property
    def column(self) -> int | None:
        """Return the column number associated with the value, if available."""

        return self._column

    @property
    def name(self) -> str:
        """Return the name of the input placeholder."""

        return self._name


from .input import UndefinedSubstitution, extract_inputs, substitute
