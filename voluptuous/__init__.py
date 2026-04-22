"""Lightweight voluptuous compatibility shim for dependency-light test runs."""

from collections.abc import Callable, Mapping
from typing import Any as AnyType

UNDEFINED = object()
ALLOW_EXTRA = object()


class Invalid(Exception):
    """Validation error compatible with voluptuous.Invalid."""


class _ErrorModule:
    Invalid = Invalid


error = _ErrorModule()


class Marker:
    """Marker wrapper used by Schema definitions."""

    def __init__(self, schema: AnyType, default: AnyType = UNDEFINED) -> None:
        """Store wrapped schema metadata and resolve default provider."""
        self.schema = schema
        if default is UNDEFINED:
            self.default = _undefined_default
        elif callable(default):
            self.default = default
        else:
            self.default = _constant_default(default)

    def __hash__(self) -> int:
        """Return a stable hash for marker identity checks."""
        return hash((self.schema, id(self.default)))


class Optional(Marker):
    """Optional marker."""


class Required(Marker):
    """Required marker."""


def _undefined_default() -> AnyType:
    """Return voluptuous sentinel for undefined defaults."""
    return UNDEFINED


def _constant_default(value: AnyType) -> Callable[[], AnyType]:
    """Create a default provider returning a fixed value."""

    def _default() -> AnyType:
        return value

    return _default


def Coerce(target_type: type[AnyType]) -> Callable[[AnyType], AnyType]:
    """Return a validator that coerces incoming values to ``target_type``."""

    def _coerce(value: AnyType) -> AnyType:
        return target_type(value)

    return _coerce


def In(
    options: Mapping[AnyType, AnyType]
    | list[AnyType]
    | tuple[AnyType, ...]
    | set[AnyType],
) -> Callable[[AnyType], AnyType]:
    """Return a validator that accepts only configured options."""

    def _validate(value: AnyType) -> AnyType:
        if value in options:
            return value
        raise Invalid(f"value {value!r} not in allowed options")

    return _validate


def Any(*validators: AnyType) -> Callable[[AnyType], AnyType]:
    """Return a validator that accepts first matching validator/value."""

    def _validate(value: AnyType) -> AnyType:
        for validator in validators:
            try:
                if callable(validator):
                    return validator(value)
                if value == validator:
                    return value
            except Exception:
                continue
        return value

    return _validate


def All(*validators: AnyType) -> Callable[[AnyType], AnyType]:
    """Return a validator that runs validators in sequence."""

    def _validate(value: AnyType) -> AnyType:
        current = value
        for validator in validators:
            if callable(validator):
                current = validator(current)
        return current

    return _validate


def Range(
    *, min: float | int | None = None, max: float | int | None = None
) -> Callable[[AnyType], AnyType]:
    """Return a validator that enforces optional min/max boundaries."""

    def _validate(value: AnyType) -> AnyType:
        if min is not None and value < min:
            raise Invalid(f"value {value!r} is below minimum {min}")
        if max is not None and value > max:
            raise Invalid(f"value {value!r} is above maximum {max}")
        return value

    return _validate


class Schema:
    """Minimal schema wrapper used by tests."""

    def __init__(self, schema: AnyType, extra: AnyType | None = None) -> None:
        """Store schema configuration for later validation calls."""
        self.schema = schema
        self.extra = extra

    def __call__(self, value: AnyType) -> AnyType:
        """Validate mappings and apply marker defaults in the shim."""
        if isinstance(self.schema, list):
            if not isinstance(value, list):
                raise Invalid("list value required")
            if not self.schema:
                return value
            validators = tuple(self.schema)
            result: list[AnyType] = []
            for item in value:
                validated = None
                matched = False
                for validator in validators:
                    try:
                        validated = self._validate_value(validator, item)
                    except Invalid:
                        continue
                    matched = True
                    break
                if not matched:
                    raise Invalid(f"invalid list item: {item!r}")
                result.append(validated)
            return result

        if not isinstance(self.schema, Mapping):
            return value
        if not isinstance(value, Mapping):
            raise Invalid("mapping value required")

        result: dict[AnyType, AnyType] = (
            dict(value) if self.extra is ALLOW_EXTRA else {}
        )
        for key, validator in self.schema.items():
            marker = key if isinstance(key, Marker) else None
            target_key = marker.schema if marker is not None else key
            if target_key in value:
                raw = value[target_key]
            elif marker is not None:
                default_value = marker.default()
                if default_value is UNDEFINED:
                    continue
                raw = default_value
            else:
                continue
            result[target_key] = self._validate_value(validator, raw)

        if self.extra is not ALLOW_EXTRA:
            valid_keys = {
                key.schema if isinstance(key, Marker) else key for key in self.schema
            }
            unknown = [key for key in value if key not in valid_keys]
            if unknown:
                raise Invalid(f"extra keys not allowed: {unknown!r}")
        return result

    @staticmethod
    def _validate_value(validator: AnyType, value: AnyType) -> AnyType:
        """Validate values using callable, type, or equality checks."""
        if callable(validator):
            try:
                return validator(value)
            except Exception as err:
                raise Invalid(str(err)) from err
        if value != validator:
            raise Invalid(f"expected {validator!r}")
        return value

    def extend(self, schema: Mapping[AnyType, AnyType]) -> Schema:
        """Return a new schema containing the merged mapping definition."""
        if isinstance(self.schema, Mapping):
            merged = dict(self.schema)
            merged.update(schema)
            return Schema(merged, extra=self.extra)
        return Schema(schema, extra=self.extra)


__all__ = [
    "ALLOW_EXTRA",
    "All",
    "Any",
    "Coerce",
    "In",
    "Invalid",
    "Marker",
    "Optional",
    "Range",
    "Required",
    "Schema",
    "UNDEFINED",
    "error",
]
