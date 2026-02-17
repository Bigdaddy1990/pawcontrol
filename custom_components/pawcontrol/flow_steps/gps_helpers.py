"""GPS helper utilities for Paw Control flows."""

from collections.abc import Mapping

from ..exceptions import ValidationError
from ..types import (
    DOG_GPS_PLACEHOLDERS_TEMPLATE,
    ConfigFlowPlaceholders,
    clone_placeholders,
    freeze_placeholders,
)


def validation_error_key(error: ValidationError, fallback: str) -> str:
    """Return a translation key for a validation error."""  # noqa: E111

    return error.constraint or fallback  # noqa: E111


def build_dog_gps_placeholders(*, dog_name: str) -> ConfigFlowPlaceholders:
    """Return immutable placeholders for the GPS configuration step."""  # noqa: E111

    placeholders = clone_placeholders(DOG_GPS_PLACEHOLDERS_TEMPLATE)  # noqa: E111
    placeholders["dog_name"] = dog_name  # noqa: E111
    return freeze_placeholders(placeholders)  # noqa: E111


def build_gps_source_options(
    gps_sources: Mapping[str, str],
) -> dict[str, str]:
    """Return ordered GPS source options with push/manual defaults."""  # noqa: E111

    base_push_sources = {  # noqa: E111
        "webhook": "Webhook (Push)",
        "mqtt": "MQTT (Push)",
    }
    if not gps_sources:  # noqa: E111
        return {
            **base_push_sources,
            "manual": "Manual Location Entry",
        }

    return {  # noqa: E111
        **gps_sources,
        **base_push_sources,
        "manual": "Manual Location Entry",
    }
