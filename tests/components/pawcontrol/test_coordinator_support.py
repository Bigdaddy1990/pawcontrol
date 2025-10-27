"""Tests for coordinator support helpers."""

import pytest

pytest.importorskip("homeassistant")

from custom_components.pawcontrol.const import (
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_MODULES,
    MAX_IDLE_POLL_INTERVAL,
    MAX_POLLING_INTERVAL_SECONDS,
    MODULE_GPS,
    MODULE_HEALTH,
)
from custom_components.pawcontrol.coordinator_support import DogConfigRegistry
from custom_components.pawcontrol.exceptions import ValidationError


@pytest.mark.usefixtures("enable_custom_integrations")
class TestDogConfigRegistry:
    """Validate polling interval calculations for the coordinator."""

    def test_minimal_interval_without_dogs(self) -> None:
        """Ensure an empty configuration honours the Platinum poll ceiling."""

        registry = DogConfigRegistry([])
        interval = registry.calculate_update_interval(options={})
        assert interval == min(300, MAX_POLLING_INTERVAL_SECONDS)

    def test_gps_interval_clamped_to_platinum_limit(self) -> None:
        """Verify GPS-heavy setups clamp to the maximum supported interval."""

        registry = DogConfigRegistry(
            [
                {
                    CONF_DOG_ID: "buddy",
                    CONF_DOG_NAME: "Buddy",
                    CONF_MODULES: {MODULE_GPS: True},
                }
            ]
        )

        interval = registry.calculate_update_interval(
            options={"gps_update_interval": MAX_POLLING_INTERVAL_SECONDS * 5}
        )

        assert interval == MAX_POLLING_INTERVAL_SECONDS

    def test_module_count_balances_interval_with_limit(self) -> None:
        """Large module counts should still respect the hard clamp."""

        registry = DogConfigRegistry(
            [
                {
                    CONF_DOG_ID: f"dog_{idx}",
                    CONF_DOG_NAME: f"Dog {idx}",
                    CONF_MODULES: {MODULE_HEALTH: True},
                }
                for idx in range(10)
            ]
        )

        interval = registry.calculate_update_interval(options={})
        assert interval == min(120, MAX_POLLING_INTERVAL_SECONDS)

    def test_invalid_interval_raises_validation_error(self) -> None:
        """Non-integer values should raise a validation error."""

        registry = DogConfigRegistry(
            [
                {
                    CONF_DOG_ID: "buddy",
                    CONF_DOG_NAME: "Buddy",
                    CONF_MODULES: {MODULE_HEALTH: True},
                }
            ]
        )

        with pytest.raises(ValidationError):
            registry.calculate_update_interval(options={"gps_update_interval": "fast"})

    def test_negative_interval_raises_validation_error(self) -> None:
        """Negative values are explicitly rejected."""

        registry = DogConfigRegistry(
            [
                {
                    CONF_DOG_ID: "buddy",
                    CONF_DOG_NAME: "Buddy",
                    CONF_MODULES: {MODULE_GPS: True},
                }
            ]
        )

        with pytest.raises(ValidationError):
            registry.calculate_update_interval(options={"gps_update_interval": -5})

    def test_registry_trims_identifiers_and_names(self) -> None:
        """Whitespace-only identifiers and names are discarded during normalisation."""

        registry = DogConfigRegistry(
            [
                {
                    CONF_DOG_ID: "  luna  ",
                    CONF_DOG_NAME: "  Luna  ",
                    CONF_MODULES: {MODULE_HEALTH: True},
                },
                {
                    CONF_DOG_ID: "   ",
                    CONF_DOG_NAME: "Unnamed",
                },
                {
                    CONF_DOG_ID: "luna",
                    CONF_DOG_NAME: "   ",
                },
            ]
        )

        assert registry.ids() == ["luna"]
        assert registry.get("luna") is not None
        assert registry.get_name("luna") == "Luna"

    @pytest.mark.parametrize(
        "interval",
        [0, -1, "fast", None],
    )
    def test_enforce_polling_limits_rejects_invalid_values(
        self, interval: object
    ) -> None:
        """Invalid polling intervals should raise validation errors."""

        with pytest.raises(ValidationError):
            DogConfigRegistry._enforce_polling_limits(interval)  # type: ignore[arg-type]

    def test_enforce_polling_limits_caps_large_values(self) -> None:
        """Extremely large intervals clamp to the allowed maximum."""

        capped = DogConfigRegistry._enforce_polling_limits(
            MAX_POLLING_INTERVAL_SECONDS * 50
        )
        assert capped == min(
            MAX_POLLING_INTERVAL_SECONDS * 50,
            MAX_IDLE_POLL_INTERVAL,
            MAX_POLLING_INTERVAL_SECONDS,
        )

    @pytest.mark.parametrize(
        "value",
        [True, False, "", "   ", "invalid", -5, 0, 3.5],
    )
    def test_validate_gps_interval_rejects_invalid_inputs(self, value: object) -> None:
        """GPS intervals must be positive integers."""

        with pytest.raises(ValidationError):
            DogConfigRegistry._validate_gps_interval(value)

    @pytest.mark.parametrize("value", ["30", " 120 ", 45])
    def test_validate_gps_interval_accepts_positive_integers(
        self, value: object
    ) -> None:
        """Valid integers or strings should return the coerced interval."""

        assert DogConfigRegistry._validate_gps_interval(value) == int(
            str(value).strip()
        )
