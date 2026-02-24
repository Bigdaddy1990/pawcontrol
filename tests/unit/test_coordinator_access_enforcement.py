"""Unit tests for coordinator access enforcement helpers."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from custom_components.pawcontrol.coordinator_access_enforcement import (
    COORDINATOR_ACCESS_GUIDELINES,
    CoordinatorAccessViolation,
    CoordinatorDataProxy,
    coordinator_only_property,
    create_coordinator_access_guard,
    log_direct_access_warning,
    print_access_guidelines,
    require_coordinator,
    require_coordinator_data,
    validate_coordinator_usage,
)


class TestRequireCoordinator:
    """Tests for require_coordinator decorator."""

    def test_require_coordinator_missing_args(self) -> None:
        """Raise when wrapped function is called without self."""

        @require_coordinator
        def wrapped() -> str:
            return "ok"

        with pytest.raises(CoordinatorAccessViolation, match="requires self"):
            wrapped()

    def test_require_coordinator_missing_attribute(self) -> None:
        """Raise when instance has no coordinator attribute."""

        class NoCoordinator:
            entity_id = "sensor.paw"

            @require_coordinator
            def wrapped(self) -> str:
                return "ok"

        with pytest.raises(CoordinatorAccessViolation) as err:
            NoCoordinator().wrapped()
        assert err.value.entity_id == "sensor.paw"

    def test_require_coordinator_none(self) -> None:
        """Raise when coordinator exists but is None."""

        class EmptyCoordinator:
            entity_id = "sensor.paw"
            coordinator = None

            @require_coordinator
            def wrapped(self) -> str:
                return "ok"

        with pytest.raises(CoordinatorAccessViolation, match="Coordinator is None"):
            EmptyCoordinator().wrapped()


class TestRequireCoordinatorData:
    """Tests for require_coordinator_data decorator."""

    def test_require_coordinator_data_missing_dog_attribute(self) -> None:
        """Raise when configured dog_id attribute is unavailable."""

        class MissingDogId:
            entity_id = "sensor.paw"
            coordinator = SimpleNamespace(data={"buddy": {}})

            @require_coordinator_data(dog_id_attr="profile_id")
            def wrapped(self) -> str:
                return "ok"

        with pytest.raises(CoordinatorAccessViolation, match="profile_id"):
            MissingDogId().wrapped()

    def test_require_coordinator_data_missing_data_allowed(self) -> None:
        """Allow missing dog data when allow_missing=True."""

        class AllowMissing:
            entity_id = "sensor.paw"
            dog_id = "unknown"
            coordinator = SimpleNamespace(data={})

            @require_coordinator_data(allow_missing=True)
            def wrapped(self) -> str:
                return "ok"

        assert AllowMissing().wrapped() == "ok"


def test_coordinator_only_property_wraps_validation() -> None:
    """Property should enforce coordinator access checks."""

    class Entity:
        coordinator = None

        @coordinator_only_property
        def status(self) -> str:
            return "ready"

    with pytest.raises(CoordinatorAccessViolation):
        _ = Entity().status


def test_log_direct_access_warning_includes_recommendation() -> None:
    """Direct access warning should include recommended method."""
    with patch(
        "custom_components.pawcontrol.coordinator_access_enforcement._LOGGER"
    ) as logger:
        log_direct_access_warning(
            "sensor.buddy", "cache", coordinator_method="coordinator.get_dog_data()"
        )

    logger.warning.assert_called_once()
    assert "coordinator.get_dog_data()" in logger.warning.call_args[0][0]


def test_coordinator_data_proxy_access_tracking() -> None:
    """Proxy should track all access methods."""
    proxy = CoordinatorDataProxy({"buddy": {"name": "Buddy"}}, "sensor.paw")

    assert "buddy" in proxy
    assert proxy["buddy"] == {"name": "Buddy"}
    assert proxy.get("missing", "fallback") == "fallback"
    assert proxy.access_count == 2


def test_validate_coordinator_usage_warns_for_saturation() -> None:
    """Validation should report issues and saturation warnings."""
    adaptive_polling = SimpleNamespace(
        as_diagnostics=lambda: {"entity_saturation": 0.95}
    )
    runtime_managers = SimpleNamespace(data_manager=None, feeding_manager=None)
    coordinator = SimpleNamespace(
        data=None,
        runtime_managers=runtime_managers,
        _adaptive_polling=adaptive_polling,
    )

    with patch(
        "custom_components.pawcontrol.coordinator_access_enforcement._LOGGER"
    ) as logger:
        result = validate_coordinator_usage(coordinator, log_warnings=True)

    assert result["has_issues"] is True
    assert result["issue_count"] == 2
    assert "Coordinator data is None" in result["issues"]
    logger.warning.assert_called_once()


def test_create_coordinator_access_guard_strict_mode_logs_info() -> None:
    """Strict mode should emit an info log and return proxy."""
    coordinator = SimpleNamespace(data={"buddy": {}})

    with patch(
        "custom_components.pawcontrol.coordinator_access_enforcement._LOGGER"
    ) as logger:
        guard = create_coordinator_access_guard(coordinator, strict_mode=True)

    assert isinstance(guard, CoordinatorDataProxy)
    logger.info.assert_called_once()


def test_print_access_guidelines_logs_expected_text() -> None:
    """Guideline printer should emit static guidance text."""
    with patch(
        "custom_components.pawcontrol.coordinator_access_enforcement._LOGGER"
    ) as logger:
        print_access_guidelines()

    logger.info.assert_called_once_with(COORDINATOR_ACCESS_GUIDELINES)
