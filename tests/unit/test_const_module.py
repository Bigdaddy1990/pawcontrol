"""Coverage-focused tests for the constants module."""

from custom_components.pawcontrol import const


def test_platforms_contains_expected_entities() -> None:
    """The integration should expose all supported Home Assistant platforms."""
    platform_values = {str(platform) for platform in const.PLATFORMS}

    assert {
        "binary_sensor",
        "button",
        "date",
        "datetime",
        "device_tracker",
        "number",
        "select",
        "sensor",
        "switch",
        "text",
    }.issubset(platform_values)


def test_update_interval_aliases_match_balanced_defaults() -> None:
    """Backward-compat aliases should point to the balanced update cadence."""
    assert const.UPDATE_INTERVALS["balanced"] == 120
    assert const.UPDATE_INTERVALS["standard"] == const.UPDATE_INTERVALS["balanced"]
    assert const.MAX_POLLING_INTERVAL_SECONDS == 15 * 60


def test_exported_module_constants_are_publicly_available() -> None:
    """Frequently used constants must stay available through ``__all__``."""
    exported = set(const.__all__)

    assert "DOMAIN" in exported
    assert "MODULE_GPS" in exported
    assert "PLATFORMS" in exported
    assert const.DOMAIN == "pawcontrol"
