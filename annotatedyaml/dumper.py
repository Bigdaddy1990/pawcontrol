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
from pathlib import Path
from typing import Any, Callable, Iterable

try:  # pragma: no cover - optional dependency
    import yaml
except Exception:  # pragma: no cover - PyYAML is optional for the stub
    yaml = None  # type: ignore[assignment]

__all__ = ["add_representer", "dump", "represent_odict", "save_yaml"]

# ``yaml`` maintains global registries for representers.  The real implementation
# forwards the registration to PyYAML, so we simply do the same when available
# and otherwise keep track of the request so the API surface remains compatible.
_registered_representers: list[tuple[type[Any], Callable[..., Any]]] = []


def add_representer(data_type: type[Any], representer: Callable[..., Any]) -> None:
    """Register a custom representer with PyYAML if available.

    When PyYAML is not installed we store the registration request so that tests
    inspecting the registry can still observe the representative metadata.  This
    mirrors the behaviour relied upon by the Home Assistant utilities without
    introducing a hard dependency on PyYAML.
    """

    if yaml is not None:  # pragma: no branch - trivial guard
        yaml.add_representer(data_type, representer)
    _registered_representers.append((data_type, representer))


def represent_odict(value: OrderedDict[Any, Any] | dict[str, Any]) -> list[tuple[Any, Any]]:
    """Return a list representation for ordered dictionaries.

    PyYAML uses ``represent_odict`` to convert ordered dictionaries into a
    sequence of key/value pairs.  Returning a list keeps the ordering intact and
    works for both the real dumper and the simplified fallback used in tests.
    """

    if isinstance(value, OrderedDict):
        items: Iterable[tuple[Any, Any]] = value.items()
    else:
        items = value.items()
    return list(items)


def dump(data: Any, stream: Any | None = None, **kwargs: Any) -> str | None:
    """Serialise ``data`` to YAML.

    When a stream is provided the YAML representation is written to it and the
    function returns ``None`` (matching :func:`yaml.dump`).  Without PyYAML we
    fall back to :func:`repr`, which is sufficient for the unit tests that only
    need deterministic string output.
    """

    if yaml is None:
        rendered = repr(data)
    else:  # pragma: no cover - exercised indirectly via tests
        rendered = yaml.safe_dump(data, **kwargs)

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
    with path.open("w", encoding="utf-8") as handle:
        dump(data, stream=handle)

