"""Minimal dumper helpers for the ``annotatedyaml`` stub package.

The real :mod:`annotatedyaml.dumper` module is fairly feature rich and wraps
`PyYAML <https://pyyaml.org/>`_.  The Home Assistant test-suite only needs the
module to exist so that imports succeed and, on occasion, to serialise a small
object graph back to YAML.  This lightweight re-implementation focuses on the
behaviour that the tests rely on while remaining entirely dependency free.

If :mod:`yaml` (PyYAML) is available it is used to produce the output; otherwise
the functions fall back to a very small in-memory representation that mirrors
the structure of the provided data.  The fallback keeps the return types stable
for the tests without pulling a heavy dependency into the execution environment.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable
from pathlib import Path
from typing import Any, TextIO

try:  # pragma: no cover - optional dependency
    import yaml
except ImportError:  # pragma: no cover - PyYAML is optional for the stub
    yaml = None  # type: ignore[assignment]

__all__ = ["add_representer", "dump", "represent_odict", "save_yaml"]

# ``yaml`` maintains global registries for representers.  The real implementation
# forwards the registration to PyYAML, so we simply do the same when available
# and otherwise keep track of the request so the API surface remains compatible.
_registered_representers: dict[type[Any], Callable[..., Any]] = {}


def add_representer(data_type: type[Any], representer: Callable[..., Any]) -> None:
    """Register a custom representer with PyYAML if available.

    When PyYAML is not installed we store the registration request so that tests
    inspecting the registry can still observe the representative metadata.  This
    mirrors the behaviour relied upon by the Home Assistant utilities without
    introducing a hard dependency on PyYAML.
    """

    if yaml is not None:  # pragma: no branch - trivial guard
        yaml.add_representer(data_type, representer)
    _registered_representers[data_type] = representer


def represent_odict(
    value: OrderedDict[Any, Any] | dict[Any, Any],
) -> list[tuple[Any, Any]]:
    """Return a list representation for ordered dictionaries.

    PyYAML uses ``represent_odict`` to convert ordered dictionaries into a
    sequence of key/value pairs.  Returning a list keeps the ordering intact for
    :class:`collections.OrderedDict` and mirrors CPython's insertion-ordered
    ``dict`` implementation.
    """

    return list(value.items())


def dump(data: Any, stream: TextIO | None = None, **kwargs: Any) -> str | None:
    """Serialise ``data`` to YAML.

    When a stream is provided the YAML representation is written to it and the
    function returns ``None`` (matching :func:`yaml.dump`).  Without PyYAML we
    fall back to a small, built-in serialiser that covers the primitive data
    structures used within the test-suite.
    """

    if yaml is not None:  # pragma: no cover - exercised indirectly via tests
        rendered = yaml.safe_dump(data, **kwargs)
    else:
        rendered = _minimal_yaml_serialize(data)

    if stream is None:
        return rendered

    stream.write(rendered)
    return None


def save_yaml(filename: str | Path, data: Any) -> None:
    """Persist ``data`` as YAML to ``filename``.

    The helper mirrors the behaviour of the real ``save_yaml`` function which
    always overwrites the target file.  We rely on :func:`dump` so that both the
    PyYAML-backed and fallback implementations are covered.
    """

    path = Path(filename)
    try:
        with path.open("w", encoding="utf-8") as handle:
            dump(data, stream=handle)
    except OSError as exc:
        raise OSError(f"Failed to save YAML to {filename}: {exc}") from exc


def _minimal_yaml_serialize(data: Any, *, _indent: int = 0) -> str:
    """Serialise ``data`` into a simple YAML representation."""

    indent = " " * _indent
    if data is None:
        return f"{indent}null\n"
    if isinstance(data, bool):
        return f"{indent}{'true' if data else 'false'}\n"
    if isinstance(data, int | float):
        return f"{indent}{data}\n"
    if isinstance(data, str):
        return f"{indent}{data}\n"
    if isinstance(data, list | tuple):
        if not data:
            return f"{indent}[]\n"
        lines: list[str] = []
        for item in data:
            if isinstance(item, list | tuple | dict):
                lines.append(f"{indent}-\n")
                lines.append(_minimal_yaml_serialize(item, _indent=_indent + 2))
            else:
                rendered = _minimal_yaml_serialize(item, _indent=_indent + 2)
                lines.append(f"{indent}- {rendered.strip()}\n")
        return "".join(lines)
    if isinstance(data, dict):
        if not data:
            return f"{indent}{{}}\n"
        lines = []
        for key, value in data.items():
            if isinstance(value, list | tuple | dict):
                lines.append(f"{indent}{key}:\n")
                lines.append(_minimal_yaml_serialize(value, _indent=_indent + 2))
            else:
                rendered = _minimal_yaml_serialize(value, _indent=_indent + 2)
                lines.append(f"{indent}{key}: {rendered.strip()}\n")
        return "".join(lines)
    return f"{indent}{data!r}\n"
