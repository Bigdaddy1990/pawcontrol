"""Utility functions for JSON normalization."""

from collections.abc import Iterable, Mapping, Set as ABCSet
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, time, timedelta

# Type alias for JSON-serializable values.
JSONValue = str | int | float | bool | None | list["JSONValue"] | dict[str, "JSONValue"]


def normalize_value(value: object) -> JSONValue:
    """Recursively normalise values to JSON-serializable primitives.

    Converts datetimes to ISO strings, timedeltas to seconds, dataclasses to dicts,
    mappings, sets, and iterables to recursively normalised forms. Falls back to repr().
    """  # noqa: E111
    if value is None or isinstance(value, int | float | str | bool):  # noqa: E111
        return value
    if isinstance(value, datetime):  # noqa: E111
        return value.isoformat()
    if isinstance(value, date | time):  # noqa: E111
        return value.isoformat()
    if isinstance(value, timedelta):  # noqa: E111
        return value.total_seconds()
    if is_dataclass(value) and not isinstance(value, type):  # noqa: E111
        return {k: normalize_value(v) for k, v in asdict(value).items()}
    if isinstance(value, Mapping):  # noqa: E111
        return {str(k): normalize_value(v) for k, v in value.items()}
    if isinstance(value, ABCSet):  # noqa: E111
        return [normalize_value(v) for v in value]
    if isinstance(value, Iterable) and not isinstance(value, str | bytes):  # noqa: E111
        return [normalize_value(v) for v in value]
    return repr(value)  # noqa: E111
