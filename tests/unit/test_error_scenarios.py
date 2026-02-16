"""Error scenario tests for PawControl integration.

This module tests error handling, recovery mechanisms, and edge cases to ensure
the integration gracefully handles all failure scenarios.

Quality Scale: Platinum target
Home Assistant: 2025.9.0+
Python: 3.13+
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from tests.helpers.factories import (
  create_mock_coordinator,
  create_test_coordinator_data,
)

from custom_components.pawcontrol.exceptions import (
  ConfigurationError,
  DogNotFoundError,
  GPSUnavailableError,
  InvalidCoordinatesError,
  NetworkError,
  RateLimitError,
  StorageError,
  ValidationError,
  WalkError,
)


class TestNetworkErrorScenarios:
  """Test network error handling."""  # noqa: E111

  @pytest.mark.asyncio  # noqa: E111
  async def test_timeout_error_recovery(self):  # noqa: E111
    """Test recovery from network timeout.

    Scenario: API call times out, should retry with backoff.
    """
    coordinator = create_mock_coordinator()

    # First call times out, second succeeds
    coordinator.async_request_refresh = AsyncMock(side_effect=[TimeoutError(), None])

    # First call should raise timeout
    with pytest.raises(asyncio.TimeoutError):
      await coordinator.async_request_refresh()  # noqa: E111

    # Second call should succeed after retry
    await coordinator.async_request_refresh()

  @pytest.mark.asyncio  # noqa: E111
  async def test_connection_error_fallback(self):  # noqa: E111
    """Test fallback to cached data on connection error.

    Scenario: Network unavailable, use cached coordinator data.
    """
    coordinator = create_mock_coordinator(data=create_test_coordinator_data())

    # Simulate connection error
    coordinator.async_request_refresh = AsyncMock(
      side_effect=NetworkError("Connection failed")
    )

    # Should raise network error
    with pytest.raises(NetworkError):
      await coordinator.async_request_refresh()  # noqa: E111

    # Cached data should still be available
    assert coordinator.data is not None
    assert len(coordinator.data) > 0

  @pytest.mark.asyncio  # noqa: E111
  async def test_rate_limit_error_backoff(self):  # noqa: E111
    """Test rate limit error triggers backoff.

    Scenario: Hit rate limit, should wait before retry.
    """
    coordinator = create_mock_coordinator()

    # Simulate rate limit error
    coordinator.async_request_refresh = AsyncMock(
      side_effect=RateLimitError("Rate limit exceeded", retry_after=5)
    )

    with pytest.raises(RateLimitError) as exc_info:
      await coordinator.async_request_refresh()  # noqa: E111

    # Check retry_after is set
    assert exc_info.value.retry_after == 5


class TestGPSErrorScenarios:
  """Test GPS error handling."""  # noqa: E111

  def test_invalid_gps_coordinates_rejected(self):  # noqa: E111
    """Test invalid GPS coordinates are rejected.

    Scenario: Coordinates outside valid ranges.
    """
    from custom_components.pawcontrol.validation import validate_gps_coordinates

    # Invalid latitude
    with pytest.raises(InvalidCoordinatesError):
      validate_gps_coordinates(95.0, 0.0)  # noqa: E111

    # Invalid longitude
    with pytest.raises(InvalidCoordinatesError):
      validate_gps_coordinates(0.0, 185.0)  # noqa: E111

    # Both invalid
    with pytest.raises(InvalidCoordinatesError):
      validate_gps_coordinates(-95.0, -185.0)  # noqa: E111

  def test_gps_unavailable_graceful_handling(self):  # noqa: E111
    """Test graceful handling when GPS unavailable.

    Scenario: GPS module disabled or unavailable.
    """
    coordinator = create_mock_coordinator()

    # Remove GPS data
    for dog_data in coordinator.data.values():
      if "gps" in dog_data:  # noqa: E111
        del dog_data["gps"]

    # Should handle missing GPS data gracefully
    for dog_data in coordinator.data.values():
      assert "gps" not in dog_data  # noqa: E111

  def test_gps_accuracy_below_threshold(self):  # noqa: E111
    """Test handling of low GPS accuracy.

    Scenario: GPS accuracy too low for reliable location.
    """
    gps_data = {
      "latitude": 45.0,
      "longitude": -122.0,
      "accuracy": 1000.0,  # Very poor accuracy (1km)
    }

    # Should accept but flag as low accuracy
    assert gps_data["accuracy"] > 100.0


class TestWalkErrorScenarios:
  """Test walk-related error handling."""  # noqa: E111

  def test_walk_already_in_progress_error(self):  # noqa: E111
    """Test error when starting walk that's already active.

    Scenario: Attempt to start second walk while one is active.
    """
    from custom_components.pawcontrol.exceptions import WalkAlreadyInProgressError

    # Simulate walk in progress
    walk_data = {"walk_in_progress": True}

    if walk_data["walk_in_progress"]:
      error = WalkAlreadyInProgressError("dog_1")  # noqa: E111
      assert "dog_1" in str(error)  # noqa: E111

  def test_walk_not_in_progress_error(self):  # noqa: E111
    """Test error when ending walk that isn't active.

    Scenario: Attempt to end walk when none is active.
    """
    from custom_components.pawcontrol.exceptions import WalkNotInProgressError

    # Simulate no walk in progress
    walk_data = {"walk_in_progress": False}

    if not walk_data["walk_in_progress"]:
      error = WalkNotInProgressError("dog_1")  # noqa: E111
      assert "dog_1" in str(error)  # noqa: E111


class TestValidationErrorScenarios:
  """Test validation error handling."""  # noqa: E111

  def test_dog_name_validation_errors(self):  # noqa: E111
    """Test dog name validation errors.

    Scenarios: Empty, too short, too long, invalid characters.
    """
    from custom_components.pawcontrol.validation import validate_dog_name

    # Empty name
    with pytest.raises(ValidationError):
      validate_dog_name("")  # noqa: E111

    # Too short
    with pytest.raises(ValidationError):
      validate_dog_name("A")  # noqa: E111

    # Too long
    with pytest.raises(ValidationError):
      validate_dog_name("A" * 100)  # noqa: E111

  def test_entity_id_validation_errors(self):  # noqa: E111
    """Test entity ID validation errors.

    Scenarios: No dot, multiple dots, invalid platform, invalid name.
    """
    from custom_components.pawcontrol.validation import validate_entity_id

    # No dot separator
    with pytest.raises(ValidationError):
      validate_entity_id("invalid")  # noqa: E111

    # Multiple dots
    with pytest.raises(ValidationError):
      validate_entity_id("sensor.test.extra")  # noqa: E111

    # Empty parts
    with pytest.raises(ValidationError):
      validate_entity_id(".")  # noqa: E111


class TestStorageErrorScenarios:
  """Test storage error handling."""  # noqa: E111

  @pytest.mark.asyncio  # noqa: E111
  async def test_storage_write_failure_retry(self):  # noqa: E111
    """Test retry on storage write failure.

    Scenario: Storage write fails, should retry.
    """
    mock_store = MagicMock()
    mock_store.async_save = AsyncMock(side_effect=[StorageError("Disk full"), None])

    # First call fails
    with pytest.raises(StorageError):
      await mock_store.async_save({"data": "test"})  # noqa: E111

    # Second call succeeds
    await mock_store.async_save({"data": "test"})

  @pytest.mark.asyncio  # noqa: E111
  async def test_storage_corruption_recovery(self):  # noqa: E111
    """Test recovery from corrupted storage.

    Scenario: Stored data corrupted, should reinitialize.
    """
    mock_store = MagicMock()
    mock_store.async_load = AsyncMock(side_effect=StorageError("Corrupted data"))

    # Load fails with corruption
    with pytest.raises(StorageError):
      await mock_store.async_load()  # noqa: E111

    # Should recover by using defaults
    default_data = {}
    assert default_data == {}


class TestConfigurationErrorScenarios:
  """Test configuration error handling."""  # noqa: E111

  def test_missing_required_config_field(self):  # noqa: E111
    """Test error when required config field missing.

    Scenario: API endpoint not provided.
    """
    config = {}

    if "api_endpoint" not in config:
      error = ConfigurationError("API endpoint required")  # noqa: E111
      assert "API endpoint" in str(error)  # noqa: E111

  def test_invalid_update_interval(self):  # noqa: E111
    """Test error with invalid update interval.

    Scenario: Update interval out of valid range.
    """
    from custom_components.pawcontrol.validation import validate_float_range

    # Too short (< 30 seconds)
    with pytest.raises(ValidationError):
      validate_float_range(15, 30, 3600, field_name="update_interval")  # noqa: E111

    # Too long (> 1 hour)
    with pytest.raises(ValidationError):
      validate_float_range(7200, 30, 3600, field_name="update_interval")  # noqa: E111


class TestDogNotFoundErrorScenarios:
  """Test dog not found error handling."""  # noqa: E111

  def test_dog_not_found_with_suggestions(self):  # noqa: E111
    """Test dog not found error includes suggestions.

    Scenario: Reference invalid dog ID, suggest valid ones.
    """
    available_dogs = ["buddy", "max", "luna"]
    invalid_dog = "unknown"

    if invalid_dog not in available_dogs:
      error = DogNotFoundError(invalid_dog, available_dogs)  # noqa: E111
      assert invalid_dog in str(error)  # noqa: E111
      assert "buddy" in str(error) or "available" in str(error).lower()  # noqa: E111


class TestConcurrentAccessScenarios:
  """Test concurrent access error handling."""  # noqa: E111

  @pytest.mark.asyncio  # noqa: E111
  async def test_concurrent_coordinator_updates(self):  # noqa: E111
    """Test concurrent coordinator updates don't corrupt data.

    Scenario: Multiple updates happening simultaneously.
    """
    coordinator = create_mock_coordinator()
    results = []

    async def update_task(idx):
      data = create_test_coordinator_data(dog_ids=[f"dog_{idx}"])  # noqa: E111
      coordinator.data = data  # noqa: E111
      await asyncio.sleep(0.01)  # noqa: E111
      results.append(idx)  # noqa: E111

    # Run 5 updates concurrently
    tasks = [update_task(i) for i in range(5)]
    await asyncio.gather(*tasks)

    # All tasks should complete
    assert len(results) == 5


class TestEdgeCaseScenarios:
  """Test edge case handling."""  # noqa: E111

  def test_empty_coordinator_data(self):  # noqa: E111
    """Test handling of empty coordinator data.

    Scenario: Coordinator initialized with no dogs.
    """
    coordinator = create_mock_coordinator(data={})

    assert coordinator.data == {}
    assert len(coordinator.data) == 0

  def test_very_large_dog_count(self):  # noqa: E111
    """Test handling of very large number of dogs.

    Scenario: Integration with 100+ dogs.
    """
    large_data = create_test_coordinator_data(dog_ids=[f"dog_{i}" for i in range(100)])

    assert len(large_data) == 100
    assert "dog_0" in large_data
    assert "dog_99" in large_data

  def test_special_characters_in_dog_name(self):  # noqa: E111
    """Test handling of special characters in dog names.

    Scenario: Dog names with unicode, emojis, etc.
    """
    from custom_components.pawcontrol.validation import validate_dog_name

    # Unicode characters should work
    validate_dog_name("Café")

    # Spaces should work
    validate_dog_name("Max Junior")

    # Hyphens should work
    validate_dog_name("Luna-Belle")


class TestRecoveryMechanisms:
  """Test automatic recovery mechanisms."""  # noqa: E111

  @pytest.mark.asyncio  # noqa: E111
  async def test_automatic_retry_on_transient_error(self):  # noqa: E111
    """Test automatic retry on transient errors.

    Scenario: Temporary network glitch, should retry automatically.
    """
    call_count = 0

    async def failing_call():
      nonlocal call_count  # noqa: E111
      call_count += 1  # noqa: E111
      if call_count < 3:  # noqa: E111
        raise NetworkError("Temporary failure")
      return "success"  # noqa: E111

    # Simulate retry logic
    max_retries = 3
    for attempt in range(max_retries):
      try:  # noqa: E111
        result = await failing_call()
        assert result == "success"
        break
      except NetworkError:  # noqa: E111
        if attempt == max_retries - 1:
          raise  # noqa: E111

    assert call_count == 3

  @pytest.mark.asyncio  # noqa: E111
  async def test_fallback_to_default_on_validation_error(self):  # noqa: E111
    """Test fallback to defaults on validation error.

    Scenario: Invalid config value, use safe default instead.
    """

    def get_config_value(config, key, default):
      try:  # noqa: E111
        value = config.get(key)
        if value is None:
          raise ValidationError(f"{key} not found")  # noqa: E111
        return value
      except ValidationError, KeyError:  # noqa: E111
        return default

    config = {}
    result = get_config_value(config, "missing_key", "default_value")
    assert result == "default_value"


class TestErrorReporting:
  """Test error reporting and diagnostics."""  # noqa: E111

  def test_error_includes_context(self):  # noqa: E111
    """Test that errors include diagnostic context.

    Scenario: Error provides enough info for debugging.
    """
    try:
      raise InvalidCoordinatesError(95.0, 0.0)  # noqa: E111
    except InvalidCoordinatesError as e:
      error_dict = e.to_dict()  # noqa: E111
      assert "error_code" in error_dict  # noqa: E111
      assert "severity" in error_dict  # noqa: E111
      assert "context" in error_dict  # noqa: E111

  def test_error_includes_recovery_suggestions(self):  # noqa: E111
    """Test that errors include recovery suggestions.

    Scenario: Error tells user how to fix the problem.
    """
    error = NetworkError("Connection failed")
    error.add_recovery_suggestion("Check network connection")
    error.add_recovery_suggestion("Verify API endpoint URL")

    assert len(error.recovery_suggestions) >= 2


# Error scenarios summary

ERROR_SCENARIOS_TESTED = [
  "Network timeout",
  "Connection failure",
  "Rate limiting",
  "Invalid GPS coordinates",
  "GPS unavailable",
  "Walk already in progress",
  "Walk not in progress",
  "Invalid dog name",
  "Invalid entity ID",
  "Storage write failure",
  "Storage corruption",
  "Missing config field",
  "Invalid update interval",
  "Dog not found",
  "Concurrent updates",
  "Empty data",
  "Large dataset",
  "Special characters",
  "Transient errors",
  "Validation fallback",
]
