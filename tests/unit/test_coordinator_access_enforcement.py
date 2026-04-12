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

    def test_require_coordinator_allows_access_when_coordinator_exists(self) -> None:
        """Return wrapped value when coordinator is available."""

        class WithCoordinator:
            coordinator = SimpleNamespace(data={})

            @require_coordinator
            def wrapped(self, value: str) -> str:
                return value

        assert WithCoordinator().wrapped("ok") == "ok"


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

    def test_require_coordinator_data_missing_args(self) -> None:
        """Raise when wrapped method is called without self."""

        @require_coordinator_data()
        def wrapped() -> str:
            return "ok"

        with pytest.raises(CoordinatorAccessViolation, match="requires self"):
            wrapped()

    def test_require_coordinator_data_missing_coordinator_attribute(self) -> None:
        """Raise when instance has no coordinator attribute."""

        class NoCoordinator:
            entity_id = "sensor.paw"
            dog_id = "buddy"

            @require_coordinator_data()
            def wrapped(self) -> str:
                return "ok"

        with pytest.raises(CoordinatorAccessViolation, match="coordinator") as err:
            NoCoordinator().wrapped()

        assert err.value.entity_id == "sensor.paw"

    def test_require_coordinator_data_none_coordinator(self) -> None:
        """Raise when coordinator attribute exists but is None."""

        class NoneCoordinator:
            entity_id = "sensor.paw"
            dog_id = "buddy"
            coordinator = None

            @require_coordinator_data()
            def wrapped(self) -> str:
                return "ok"

        with pytest.raises(CoordinatorAccessViolation, match="Coordinator is None"):
            NoneCoordinator().wrapped()

    def test_require_coordinator_data_missing_dog_data_not_allowed(self) -> None:
        """Raise when dog data is missing and allow_missing is False."""

        class MissingDogData:
            entity_id = "sensor.paw"
            dog_id = "buddy"
            coordinator = SimpleNamespace(data={})

            @require_coordinator_data()
            def wrapped(self) -> str:
                return "ok"

        with pytest.raises(CoordinatorAccessViolation, match="no data for dog"):
            MissingDogData().wrapped()


def test_coordinator_only_property_wraps_validation() -> None:
    """Property should enforce coordinator access checks."""

    class Entity:
        coordinator = None

        @coordinator_only_property
        def status(self) -> str:
            return "ready"

    with pytest.raises(CoordinatorAccessViolation):
        _ = Entity().status


def test_coordinator_only_property_returns_value_when_valid() -> None:
    """Property should return wrapped function value when coordinator exists."""

    class Entity:
        coordinator = SimpleNamespace(data={})

        @coordinator_only_property
        def status(self) -> str:
            return "ready"

    assert Entity().status == "ready"


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


def test_log_direct_access_warning_without_recommendation() -> None:
    """Direct access warning should omit recommendation when not provided."""
    with patch(
        "custom_components.pawcontrol.coordinator_access_enforcement._LOGGER"
    ) as logger:
        log_direct_access_warning("sensor.buddy", "cache")

    logger.warning.assert_called_once()
    assert "instead" not in logger.warning.call_args[0][0]


def test_coordinator_data_proxy_access_tracking() -> None:
    """Proxy should track all access methods."""
    proxy = CoordinatorDataProxy({"buddy": {"name": "Buddy"}}, "sensor.paw")

    assert "buddy" in proxy
    assert proxy["buddy"] == {"name": "Buddy"}
    assert proxy.get("missing", "fallback") == "fallback"
    assert proxy.access_count == 2


def test_coordinator_data_proxy_getitem_logs_when_enabled() -> None:
    """Proxy __getitem__ should emit debug logs when access logging is enabled."""
    proxy = CoordinatorDataProxy({"buddy": {"name": "Buddy"}}, "sensor.paw")

    with patch(
        "custom_components.pawcontrol.coordinator_access_enforcement._LOGGER"
    ) as logger:
        assert proxy["buddy"] == {"name": "Buddy"}

    assert proxy.access_count == 1
    logger.debug.assert_called_once()


def test_coordinator_data_proxy_without_logging() -> None:
    """Proxy should support access counting even when debug logging is disabled."""
    proxy = CoordinatorDataProxy(
        {"buddy": {"name": "Buddy"}},
        "sensor.paw",
        log_access=False,
    )

    with patch(
        "custom_components.pawcontrol.coordinator_access_enforcement._LOGGER"
    ) as logger:
        assert proxy.get("buddy") == {"name": "Buddy"}
        assert proxy["buddy"] == {"name": "Buddy"}

    assert proxy.access_count == 2
    logger.debug.assert_not_called()


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


def test_validate_coordinator_usage_without_warnings_in_normal_state() -> None:
    """Validation should stay quiet when optional managers are absent in quiet mode."""
    runtime_managers = SimpleNamespace(data_manager=object(), feeding_manager=None)
    coordinator = SimpleNamespace(data={"buddy": {}}, runtime_managers=runtime_managers)

    with patch(
        "custom_components.pawcontrol.coordinator_access_enforcement._LOGGER"
    ) as logger:
        result = validate_coordinator_usage(coordinator, log_warnings=False)

    assert result == {"has_issues": False, "issue_count": 0, "issues": []}
    logger.warning.assert_not_called()
    logger.debug.assert_not_called()


def test_validate_coordinator_usage_logs_optional_manager_hint() -> None:
    """Validation should log debug hint when feeding manager is missing."""
    runtime_managers = SimpleNamespace(
        data_manager=object(),
        feeding_manager=None,
    )
    coordinator = SimpleNamespace(data={"buddy": {}}, runtime_managers=runtime_managers)

    with patch(
        "custom_components.pawcontrol.coordinator_access_enforcement._LOGGER"
    ) as logger:
        result = validate_coordinator_usage(coordinator, log_warnings=True)

    assert result == {"has_issues": False, "issue_count": 0, "issues": []}
    logger.debug.assert_called_once_with(
        "Feeding manager not attached (may be intentional)"
    )
    logger.warning.assert_not_called()


def test_validate_coordinator_usage_skips_adaptive_polling_without_hook() -> None:
    """Validation should ignore adaptive polling objects without diagnostics hook."""
    runtime_managers = SimpleNamespace(
        data_manager=object(),
        feeding_manager=object(),
    )
    coordinator = SimpleNamespace(
        data={"buddy": {}},
        runtime_managers=runtime_managers,
        _adaptive_polling=SimpleNamespace(),
    )

    with patch(
        "custom_components.pawcontrol.coordinator_access_enforcement._LOGGER"
    ) as logger:
        result = validate_coordinator_usage(coordinator, log_warnings=True)

    assert result == {"has_issues": False, "issue_count": 0, "issues": []}
    logger.warning.assert_not_called()


def test_validate_coordinator_usage_does_not_warn_below_saturation_threshold() -> None:
    """Validation should avoid warnings when saturation remains under threshold."""
    adaptive_polling = SimpleNamespace(
        as_diagnostics=lambda: {"entity_saturation": 0.9}
    )
    runtime_managers = SimpleNamespace(
        data_manager=object(),
        feeding_manager=object(),
    )
    coordinator = SimpleNamespace(
        data={"buddy": {}},
        runtime_managers=runtime_managers,
        _adaptive_polling=adaptive_polling,
    )

    with patch(
        "custom_components.pawcontrol.coordinator_access_enforcement._LOGGER"
    ) as logger:
        result = validate_coordinator_usage(coordinator, log_warnings=True)

    assert result == {"has_issues": False, "issue_count": 0, "issues": []}
    logger.warning.assert_not_called()


def test_create_coordinator_access_guard_strict_mode_logs_info() -> None:
    """Strict mode should emit an info log and return proxy."""
    coordinator = SimpleNamespace(data={"buddy": {}})

    with patch(
        "custom_components.pawcontrol.coordinator_access_enforcement._LOGGER"
    ) as logger:
        guard = create_coordinator_access_guard(coordinator, strict_mode=True)

    assert isinstance(guard, CoordinatorDataProxy)
    logger.info.assert_called_once()


def test_create_coordinator_access_guard_monitoring_mode_logs_debug() -> None:
    """Monitoring mode should emit a debug log and return proxy."""
    coordinator = SimpleNamespace(data={"buddy": {}})

    with patch(
        "custom_components.pawcontrol.coordinator_access_enforcement._LOGGER"
    ) as logger:
        guard = create_coordinator_access_guard(coordinator, strict_mode=False)

    assert isinstance(guard, CoordinatorDataProxy)
    logger.debug.assert_called_once()


def test_print_access_guidelines_logs_expected_text() -> None:
    """Guideline printer should emit static guidance text."""
    with patch(
        "custom_components.pawcontrol.coordinator_access_enforcement._LOGGER"
    ) as logger:
        print_access_guidelines()

    logger.info.assert_called_once_with(COORDINATOR_ACCESS_GUIDELINES)
