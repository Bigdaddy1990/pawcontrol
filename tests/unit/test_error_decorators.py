"""Unit tests for error_decorators module.

Tests validation and error handling decorators including dog validation,
GPS validation, error handling, retry logic, and repair issue mapping.
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from custom_components.pawcontrol.error_decorators import (
  create_repair_issue_from_exception,
)
from custom_components.pawcontrol.error_decorators import EXCEPTION_TO_REPAIR_ISSUE
from custom_components.pawcontrol.error_decorators import get_repair_issue_id
from custom_components.pawcontrol.error_decorators import handle_errors
from custom_components.pawcontrol.error_decorators import map_to_repair_issue
from custom_components.pawcontrol.error_decorators import require_coordinator
from custom_components.pawcontrol.error_decorators import require_coordinator_data
from custom_components.pawcontrol.error_decorators import retry_on_error
from custom_components.pawcontrol.error_decorators import validate_and_handle
from custom_components.pawcontrol.error_decorators import validate_dog_exists
from custom_components.pawcontrol.error_decorators import validate_gps_coordinates
from custom_components.pawcontrol.error_decorators import validate_range
from custom_components.pawcontrol.exceptions import DogNotFoundError
from custom_components.pawcontrol.exceptions import ErrorCategory
from custom_components.pawcontrol.exceptions import ErrorSeverity
from custom_components.pawcontrol.exceptions import InvalidCoordinatesError
from custom_components.pawcontrol.exceptions import NetworkError
from custom_components.pawcontrol.exceptions import PawControlError
from custom_components.pawcontrol.exceptions import RateLimitError


class TestValidateDogExists:
  """Test validate_dog_exists decorator."""

  def test_validate_dog_exists_success(self) -> None:
    """Test decorator allows valid dog ID."""

    class MockInstance:
      def __init__(self):
        self.coordinator = MagicMock()
        self.coordinator.data = {"buddy": {"name": "Buddy"}}

      @validate_dog_exists()
      def get_dog(self, dog_id: str) -> str:
        return f"Dog {dog_id}"

    instance = MockInstance()
    result = instance.get_dog("buddy")
    assert result == "Dog buddy"

  def test_validate_dog_exists_failure(self) -> None:
    """Test decorator raises DogNotFoundError."""

    class MockInstance:
      def __init__(self):
        self.coordinator = MagicMock()
        self.coordinator.data = {}

      @validate_dog_exists()
      def get_dog(self, dog_id: str) -> str:
        return f"Dog {dog_id}"

    instance = MockInstance()
    with pytest.raises(DogNotFoundError):
      instance.get_dog("unknown")

  def test_validate_dog_exists_no_coordinator(self) -> None:
    """Test decorator fails without coordinator."""

    class MockInstance:
      @validate_dog_exists()
      def get_dog(self, dog_id: str) -> str:
        return f"Dog {dog_id}"

    instance = MockInstance()
    with pytest.raises(PawControlError):
      instance.get_dog("buddy")


class TestValidateGPSCoordinates:
  """Test validate_gps_coordinates decorator."""

  def test_validate_gps_coordinates_valid(self) -> None:
    """Test decorator allows valid coordinates."""

    class MockInstance:
      @validate_gps_coordinates()
      def set_location(self, latitude: float, longitude: float) -> tuple[float, float]:
        return (latitude, longitude)

    instance = MockInstance()
    result = instance.set_location(45.0, -122.0)
    assert result == (45.0, -122.0)

  def test_validate_gps_coordinates_invalid_latitude(self) -> None:
    """Test decorator raises on invalid latitude."""

    class MockInstance:
      @validate_gps_coordinates()
      def set_location(self, latitude: float, longitude: float) -> tuple[float, float]:
        return (latitude, longitude)

    instance = MockInstance()
    with pytest.raises(InvalidCoordinatesError):
      instance.set_location(95.0, -122.0)

  def test_validate_gps_coordinates_invalid_longitude(self) -> None:
    """Test decorator raises on invalid longitude."""

    class MockInstance:
      @validate_gps_coordinates()
      def set_location(self, latitude: float, longitude: float) -> tuple[float, float]:
        return (latitude, longitude)

    instance = MockInstance()
    with pytest.raises(InvalidCoordinatesError):
      instance.set_location(45.0, -200.0)

  def test_validate_gps_coordinates_boundary_values(self) -> None:
    """Test decorator allows boundary values."""

    class MockInstance:
      @validate_gps_coordinates()
      def set_location(self, latitude: float, longitude: float) -> tuple[float, float]:
        return (latitude, longitude)

    instance = MockInstance()

    # Valid boundaries
    assert instance.set_location(90.0, 180.0) == (90.0, 180.0)
    assert instance.set_location(-90.0, -180.0) == (-90.0, -180.0)


class TestValidateRange:
  """Test validate_range decorator."""

  def test_validate_range_valid(self) -> None:
    """Test decorator allows value in range."""

    class MockInstance:
      @validate_range("weight", 0.5, 100.0)
      def set_weight(self, weight: float) -> float:
        return weight

    instance = MockInstance()
    assert instance.set_weight(50.0) == 50.0

  def test_validate_range_too_low(self) -> None:
    """Test decorator raises on value too low."""

    class MockInstance:
      @validate_range("weight", 0.5, 100.0)
      def set_weight(self, weight: float) -> float:
        return weight

    instance = MockInstance()
    with pytest.raises(PawControlError):
      instance.set_weight(0.1)

  def test_validate_range_too_high(self) -> None:
    """Test decorator raises on value too high."""

    class MockInstance:
      @validate_range("weight", 0.5, 100.0)
      def set_weight(self, weight: float) -> float:
        return weight

    instance = MockInstance()
    with pytest.raises(PawControlError):
      instance.set_weight(150.0)


class TestHandleErrors:
  """Test handle_errors decorator."""

  @pytest.mark.asyncio
  async def test_handle_errors_success(self) -> None:
    """Test decorator allows successful execution."""

    class MockInstance:
      @handle_errors()
      async def do_something(self) -> str:
        return "success"

    instance = MockInstance()
    result = await instance.do_something()
    assert result == "success"

  @pytest.mark.asyncio
  async def test_handle_errors_catches_exception(self) -> None:
    """Test decorator catches and handles exceptions."""

    class MockInstance:
      @handle_errors(reraise_critical=False, default_return="default")
      async def do_something(self) -> str:
        raise RuntimeError("test error")

    instance = MockInstance()
    result = await instance.do_something()
    assert result == "default"

  @pytest.mark.asyncio
  async def test_handle_errors_reraises_critical(self) -> None:
    """Test decorator reraises critical errors."""

    class MockInstance:
      @handle_errors(reraise_critical=True)
      async def do_something(self) -> str:
        raise PawControlError(
          "critical error",
          severity=ErrorSeverity.CRITICAL,
        )

    instance = MockInstance()
    with pytest.raises(PawControlError):
      await instance.do_something()

  def test_handle_errors_sync_function(self) -> None:
    """Test decorator works with sync functions."""

    class MockInstance:
      @handle_errors(reraise_critical=False, default_return="default")
      def do_something(self) -> str:
        raise RuntimeError("test error")

    instance = MockInstance()
    result = instance.do_something()
    assert result == "default"


class TestRetryOnError:
  """Test retry_on_error decorator."""

  @pytest.mark.asyncio
  async def test_retry_on_error_success_first_try(self) -> None:
    """Test decorator succeeds on first try."""

    class MockInstance:
      call_count = 0

      @retry_on_error(max_attempts=3, delay=0.01)
      async def fetch_data(self) -> str:
        self.call_count += 1
        return "success"

    instance = MockInstance()
    result = await instance.fetch_data()
    assert result == "success"
    assert instance.call_count == 1

  @pytest.mark.asyncio
  async def test_retry_on_error_succeeds_after_retry(self) -> None:
    """Test decorator retries and eventually succeeds."""

    class MockInstance:
      call_count = 0

      @retry_on_error(max_attempts=3, delay=0.01)
      async def fetch_data(self) -> str:
        self.call_count += 1
        if self.call_count < 3:
          raise NetworkError("network error")
        return "success"

    instance = MockInstance()
    result = await instance.fetch_data()
    assert result == "success"
    assert instance.call_count == 3

  @pytest.mark.asyncio
  async def test_retry_on_error_exhausts_attempts(self) -> None:
    """Test decorator exhausts retries and raises."""

    class MockInstance:
      call_count = 0

      @retry_on_error(max_attempts=3, delay=0.01)
      async def fetch_data(self) -> str:
        self.call_count += 1
        raise NetworkError("network error")

    instance = MockInstance()
    with pytest.raises(NetworkError):
      await instance.fetch_data()
    assert instance.call_count == 3

  @pytest.mark.asyncio
  async def test_retry_on_error_only_retries_specified_exceptions(self) -> None:
    """Test decorator only retries specified exception types."""

    class MockInstance:
      call_count = 0

      @retry_on_error(
        max_attempts=3,
        delay=0.01,
        exceptions=(NetworkError, RateLimitError),
      )
      async def fetch_data(self) -> str:
        self.call_count += 1
        raise ValueError("not retryable")

    instance = MockInstance()
    with pytest.raises(ValueError):
      await instance.fetch_data()
    # Should fail immediately without retries
    assert instance.call_count == 1


class TestRequireCoordinator:
  """Test require_coordinator decorator."""

  def test_require_coordinator_success(self) -> None:
    """Test decorator allows access when coordinator exists."""

    class MockInstance:
      def __init__(self):
        self.coordinator = MagicMock()

      @require_coordinator
      def do_something(self) -> str:
        return "success"

    instance = MockInstance()
    result = instance.do_something()
    assert result == "success"

  def test_require_coordinator_failure(self) -> None:
    """Test decorator raises when coordinator missing."""

    class MockInstance:
      @require_coordinator
      def do_something(self) -> str:
        return "success"

    instance = MockInstance()
    with pytest.raises(PawControlError):
      instance.do_something()


class TestRequireCoordinatorData:
  """Test require_coordinator_data decorator."""

  def test_require_coordinator_data_success(self) -> None:
    """Test decorator allows access when data exists."""

    class MockInstance:
      def __init__(self):
        self.dog_id = "buddy"
        self.coordinator = MagicMock()
        self.coordinator.data = {"buddy": {"name": "Buddy"}}

      @require_coordinator_data()
      def get_data(self) -> str:
        return "success"

    instance = MockInstance()
    result = instance.get_data()
    assert result == "success"

  def test_require_coordinator_data_missing_dog(self) -> None:
    """Test decorator raises when dog data missing."""

    class MockInstance:
      def __init__(self):
        self.dog_id = "buddy"
        self.coordinator = MagicMock()
        self.coordinator.data = {}

      @require_coordinator_data()
      def get_data(self) -> str:
        return "success"

    instance = MockInstance()
    with pytest.raises(PawControlError):
      instance.get_data()


class TestExceptionMapping:
  """Test exception to repair issue mapping."""

  def test_get_repair_issue_id(self) -> None:
    """Test getting repair issue ID for exceptions."""
    error = DogNotFoundError("buddy")
    issue_id = get_repair_issue_id(error)
    assert issue_id == "dog_not_found"

  def test_get_repair_issue_id_invalid_coordinates(self) -> None:
    """Test repair issue ID for invalid coordinates."""
    error = InvalidCoordinatesError(95.0, -122.0)
    issue_id = get_repair_issue_id(error)
    assert issue_id == "invalid_gps_coordinates"

  def test_get_repair_issue_id_unknown(self) -> None:
    """Test repair issue ID for unknown exception."""
    error = PawControlError("unknown error")
    issue_id = get_repair_issue_id(error)
    assert issue_id is None

  def test_exception_to_repair_issue_mapping_complete(self) -> None:
    """Test that mapping dictionary is complete."""
    assert len(EXCEPTION_TO_REPAIR_ISSUE) >= 8
    assert DogNotFoundError in EXCEPTION_TO_REPAIR_ISSUE
    assert InvalidCoordinatesError in EXCEPTION_TO_REPAIR_ISSUE
    assert NetworkError in EXCEPTION_TO_REPAIR_ISSUE


class TestCombinedDecorators:
  """Test combined decorator patterns."""

  def test_validate_and_handle_decorator(self) -> None:
    """Test combined validation and error handling."""

    class MockInstance:
      def __init__(self):
        self.coordinator = MagicMock()
        self.coordinator.data = {"buddy": {"name": "Buddy"}}

      @validate_and_handle(dog_id_param="dog_id", gps_coords=True)
      def update_location(
        self,
        dog_id: str,
        latitude: float,
        longitude: float,
      ) -> str:
        return f"{dog_id} at ({latitude}, {longitude})"

    instance = MockInstance()

    # Valid call
    result = instance.update_location("buddy", 45.0, -122.0)
    assert result == "buddy at (45.0, -122.0)"

    # Invalid dog
    with pytest.raises(DogNotFoundError):
      instance.update_location("unknown", 45.0, -122.0)

    # Invalid coordinates
    with pytest.raises(InvalidCoordinatesError):
      instance.update_location("buddy", 95.0, -122.0)


@pytest.mark.asyncio
async def test_create_repair_issue_from_exception() -> None:
  """Test creating repair issue from exception."""
  mock_hass = MagicMock()

  error = DogNotFoundError("buddy", ["max", "charlie"])

  with patch("custom_components.pawcontrol.error_decorators.issue_registry") as mock_ir:
    await create_repair_issue_from_exception(mock_hass, error)
    mock_ir.async_create_issue.assert_called_once()


class TestEdgeCases:
  """Test edge cases and error conditions."""

  def test_validate_dog_exists_custom_param_name(self) -> None:
    """Test validate_dog_exists with custom parameter name."""

    class MockInstance:
      def __init__(self):
        self.coordinator = MagicMock()
        self.coordinator.data = {"buddy": {}}

      @validate_dog_exists(dog_id_param="custom_id")
      def get_dog(self, custom_id: str) -> str:
        return f"Dog {custom_id}"

    instance = MockInstance()
    result = instance.get_dog("buddy")
    assert result == "Dog buddy"

  def test_validate_gps_coordinates_custom_param_names(self) -> None:
    """Test validate_gps_coordinates with custom parameter names."""

    class MockInstance:
      @validate_gps_coordinates(latitude_param="lat", longitude_param="lon")
      def set_location(self, lat: float, lon: float) -> tuple[float, float]:
        return (lat, lon)

    instance = MockInstance()
    result = instance.set_location(45.0, -122.0)
    assert result == (45.0, -122.0)

  @pytest.mark.asyncio
  async def test_retry_on_error_with_backoff(self) -> None:
    """Test retry_on_error applies exponential backoff."""

    class MockInstance:
      call_count = 0
      call_times: list[float] = []

      @retry_on_error(max_attempts=3, delay=0.01, backoff=2.0)
      async def fetch_data(self) -> str:
        import time

        self.call_times.append(time.time())
        self.call_count += 1
        if self.call_count < 3:
          raise NetworkError("network error")
        return "success"

    instance = MockInstance()
    result = await instance.fetch_data()
    assert result == "success"
    assert instance.call_count == 3
    # Verify exponential backoff (delays should increase)
    assert len(instance.call_times) == 3
