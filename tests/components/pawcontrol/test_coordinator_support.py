"""Tests for coordinator support helpers."""

import pytest

pytest.importorskip("homeassistant")

from custom_components.pawcontrol.const import (
    CONF_DOG_ID,
    CONF_MODULES,
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
                    CONF_MODULES: {MODULE_GPS: True},
                }
            ]
        )

        with pytest.raises(ValidationError):
            registry.calculate_update_interval(options={"gps_update_interval": -5})
