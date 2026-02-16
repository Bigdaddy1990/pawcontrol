"""Property-based tests using Hypothesis for PawControl.

This module tests properties that should always hold true, regardless of input,
using automated test case generation via Hypothesis.

Quality Scale: Platinum target
Home Assistant: 2025.9.0+
Python: 3.13+
"""


from datetime import datetime
from datetime import timedelta

import pytest
from hypothesis import given
from hypothesis import HealthCheck
from hypothesis import settings
from hypothesis import strategies as st

from custom_components.pawcontrol.coordinator_diffing import compute_coordinator_diff
from custom_components.pawcontrol.coordinator_diffing import compute_data_diff
from custom_components.pawcontrol.coordinator_diffing import compute_dog_diff
from custom_components.pawcontrol.const import MAX_DOG_NAME_LENGTH
from custom_components.pawcontrol.exceptions import InvalidCoordinatesError
from custom_components.pawcontrol.exceptions import ValidationError
from custom_components.pawcontrol.validation import validate_dog_name
from custom_components.pawcontrol.validation import validate_entity_id
from custom_components.pawcontrol.validation import validate_float_range
from custom_components.pawcontrol.validation import validate_gps_coordinates

# Hypothesis strategies for PawControl data types


@st.composite
def gps_coordinate_strategy(draw):
    """Strategy for generating valid GPS coordinates.

    Returns:
        Tuple of (latitude, longitude)
    """
    latitude = draw(st.floats(min_value=-90.0, max_value=90.0))
    longitude = draw(st.floats(min_value=-180.0, max_value=180.0))
    return (latitude, longitude)


@st.composite
def dog_name_strategy(draw):
    """Strategy for generating valid dog names.

    Returns:
        String dog name
    """
    # Valid names: 2-50 characters, letters/spaces/hyphens
    length = draw(st.integers(min_value=2, max_value=MAX_DOG_NAME_LENGTH))
    characters = st.characters(
        whitelist_categories=("Lu", "Ll"),
        whitelist_characters=" -",
    )
    name = draw(st.text(alphabet=characters, min_size=length, max_size=length))
    return name.strip()


@st.composite
def entity_id_strategy(draw):
    """Strategy for generating valid entity IDs.

    Returns:
        String entity ID
    """
    platform = draw(st.sampled_from(
        ["sensor", "binary_sensor", "switch", "number"]))
    name_part = draw(
        st.text(
            alphabet=st.characters(
                whitelist_categories=("Ll", "Nd"), whitelist_characters="_"
            ),
            min_size=3,
            max_size=20,
        )
    )
    return f"{platform}.{name_part}"


@st.composite
def coordinator_data_strategy(draw):
    """Strategy for generating coordinator data.

    Returns:
        Dictionary of coordinator data
    """
    num_dogs = draw(st.integers(min_value=1, max_value=5))
    data = {}

    for i in range(num_dogs):
        dog_id = f"dog_{i}"
        dog_data = {
            "gps": {
                "latitude": draw(st.floats(min_value=-90.0, max_value=90.0)),
                "longitude": draw(st.floats(min_value=-180.0, max_value=180.0)),
                "accuracy": draw(st.floats(min_value=0.1, max_value=100.0)),
            },
            "walk": {
                "active": draw(st.booleans()),
                "distance": draw(st.floats(min_value=0.0, max_value=50.0)),
                "duration": draw(st.integers(min_value=0, max_value=7200)),
            },
        }
        data[dog_id] = dog_data

    return data


# Property-based tests


class TestGPSValidationProperties:
    """Property-based tests for GPS coordinate validation."""

    @given(gps_coordinate_strategy())
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_valid_gps_coordinates_always_accepted(self, coords):
        """Test that valid GPS coordinates are always accepted.

        Property: All GPS coordinates within valid ranges should be accepted.
        """
        latitude, longitude = coords
        # Should not raise
        validate_gps_coordinates(latitude, longitude)

    @given(
        st.floats(min_value=-180.0, max_value=-90.01)
        | st.floats(min_value=90.01, max_value=180.0)
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_invalid_latitude_always_rejected(self, invalid_lat):
        """Test that invalid latitudes are always rejected.

        Property: Latitudes outside [-90, 90] should always raise.
        """
        with pytest.raises(InvalidCoordinatesError):
            validate_gps_coordinates(invalid_lat, 0.0)

    @given(
        st.floats(min_value=-360.0, max_value=-180.01)
        | st.floats(min_value=180.01, max_value=360.0)
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_invalid_longitude_always_rejected(self, invalid_lon):
        """Test that invalid longitudes are always rejected.

        Property: Longitudes outside [-180, 180] should always raise.
        """
        with pytest.raises(InvalidCoordinatesError):
            validate_gps_coordinates(0.0, invalid_lon)

    @given(gps_coordinate_strategy(), gps_coordinate_strategy())
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_gps_validation_idempotent(self, coords1, coords2):
        """Test that GPS validation is idempotent.

        Property: Validating the same coordinates twice should have same result.
        """
        lat1, lon1 = coords1
        lat2, lon2 = coords2

        # First validation
        try:
            validate_gps_coordinates(lat1, lon1)
            result1 = True
        except InvalidCoordinatesError:
            result1 = False

        # Second validation (same coords)
        try:
            validate_gps_coordinates(lat1, lon1)
            result2 = True
        except InvalidCoordinatesError:
            result2 = False

        # Results should match
        assert result1 == result2


class TestDogNameValidationProperties:
    """Property-based tests for dog name validation."""

    @given(dog_name_strategy())
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_valid_dog_names_accepted(self, name):
        """Test that valid dog names are accepted.

        Property: Names matching criteria should always be valid.
        """
        if 2 <= len(name.strip()) <= MAX_DOG_NAME_LENGTH:
            # Should not raise
            validate_dog_name(name)

    @given(st.text(min_size=MAX_DOG_NAME_LENGTH + 1, max_size=100))
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_long_names_rejected(self, long_name):
        """Test that overly long names are rejected.

        Property: Names longer than the configured limit should be invalid.
        """
        if len(long_name) > MAX_DOG_NAME_LENGTH:
            with pytest.raises(ValidationError):
                validate_dog_name(long_name)

    @given(st.text(min_size=0, max_size=1))
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_short_names_rejected(self, short_name):
        """Test that very short names are rejected.

        Property: Names shorter than 2 characters should be invalid.
        """
        if len(short_name.strip()) < 2:
            with pytest.raises(ValidationError):
                validate_dog_name(short_name)


class TestRangeValidationProperties:
    """Property-based tests for numeric range validation."""

    @given(
        st.floats(min_value=0.0, max_value=100.0),
        st.floats(min_value=0.0, max_value=100.0),
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_value_in_range_accepted(self, min_val, max_val):
        """Test that values within range are accepted.

        Property: Any value between min and max should be valid.
        """
        if min_val > max_val:
            min_val, max_val = max_val, min_val

        # Value exactly between min and max
        mid_value = (min_val + max_val) / 2

        # Should not raise
        validate_float_range(mid_value, min_val, max_val, field_name="test")

    @given(
        st.floats(min_value=-100.0, max_value=-1.0),
        st.floats(min_value=0.0, max_value=100.0),
        st.floats(min_value=101.0, max_value=200.0),
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_value_outside_range_rejected(self, value, min_val, max_val):
        """Test that values outside range are rejected.

        Property: Values less than min or greater than max should be invalid.
        """
        if value < min_val or value > max_val:
            with pytest.raises(ValidationError):
                validate_float_range(
                    value, min_val, max_val, field_name="test")


class TestEntityIDValidationProperties:
    """Property-based tests for entity ID validation."""

    @given(entity_id_strategy())
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_valid_entity_ids_accepted(self, entity_id):
        """Test that valid entity IDs are accepted.

        Property: Well-formed entity IDs should always validate.
        """
        # Should not raise
        validate_entity_id(entity_id)

    @given(st.text(min_size=1, max_size=50))
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_malformed_entity_ids_rejected(self, text):
        """Test that malformed entity IDs are rejected.

        Property: Strings without platform.name format should be invalid.
        """
        if "." not in text or text.count(".") != 1:
            with pytest.raises(ValidationError):
                validate_entity_id(text)


class TestCoordinatorDiffProperties:
    """Property-based tests for coordinator diffing."""

    @given(coordinator_data_strategy())
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_diff_with_self_shows_no_changes(self, data):
        """Test that diffing data with itself shows no changes.

        Property: diff(X, X) should always show no changes.
        """
        diff = compute_coordinator_diff(data, data)
        assert not diff.has_changes
        assert diff.change_count == 0

    @given(coordinator_data_strategy(), coordinator_data_strategy())
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_diff_symmetry(self, data1, data2):
        """Test that diff operation is symmetric.

        Property: Changes in diff(A, B) should be opposite of diff(B, A).
        """
        diff_forward = compute_coordinator_diff(data1, data2)
        diff_backward = compute_coordinator_diff(data2, data1)

        # Added in forward = removed in backward
        assert diff_forward.added_dogs == diff_backward.removed_dogs
        assert diff_forward.removed_dogs == diff_backward.added_dogs

    @given(coordinator_data_strategy())
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_diff_with_empty_shows_all_added(self, data):
        """Test that diffing from empty shows all as added.

        Property: diff({}, X) should show all items as added.
        """
        diff = compute_coordinator_diff({}, data)
        assert len(diff.added_dogs) == len(data)
        assert len(diff.removed_dogs) == 0

    @given(coordinator_data_strategy())
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_diff_to_empty_shows_all_removed(self, data):
        """Test that diffing to empty shows all as removed.

        Property: diff(X, {}) should show all items as removed.
        """
        if len(data) > 0:
            diff = compute_coordinator_diff(data, {})
            assert len(diff.removed_dogs) == len(data)
            assert len(diff.added_dogs) == 0


class TestDataDiffProperties:
    """Property-based tests for data diffing."""

    @given(st.dictionaries(st.text(), st.integers()))
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_diff_commutativity_of_unchanged(self, data):
        """Test that unchanged detection is order-independent.

        Property: unchanged keys should be same regardless of diff direction.
        """
        diff = compute_data_diff(data, data)
        assert len(diff.unchanged_keys) == len(data)
        assert diff.change_count == 0

    @given(
        st.dictionaries(st.text(min_size=1), st.integers(), min_size=1),
        st.text(min_size=1),
        st.integers(),
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_single_modification_detected(self, base_data, key, new_value):
        """Test that single value changes are detected.

        Property: Changing one value should show exactly one modification.
        """
        # Ensure key exists in original
        if key not in base_data:
            base_data[key] = 0

        # Create modified version
        modified_data = dict(base_data)
        old_value = modified_data[key]
        modified_data[key] = new_value

        diff = compute_data_diff(base_data, modified_data)

        if old_value != new_value:
            assert key in diff.modified_keys
            assert diff.change_count >= 1
        else:
            assert key not in diff.modified_keys


class TestSerializationRoundTripProperties:
    """Property-based tests for serialization round-trips."""

    @given(
        st.dictionaries(
            st.text(min_size=1, max_size=20),
            st.one_of(
                st.none(),
                st.booleans(),
                st.integers(),
                st.floats(allow_nan=False, allow_infinity=False),
                st.text(max_size=100),
            ),
        )
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_json_serializable_data_roundtrip(self, data):
        """Test that JSON-serializable data survives round-trip.

        Property: Serializing and deserializing should preserve data.
        """
        import json

        try:
            serialized = json.dumps(data)
            deserialized = json.loads(serialized)
            assert deserialized == data
        except TypeError, ValueError:
            # Some valid Python data isn't JSON-serializable (expected)
            pass

    @given(
        st.datetimes(
            min_value=datetime(2020, 1, 1),
            max_value=datetime(2030, 12, 31),
        )
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_datetime_serialization_roundtrip(self, dt):
        """Test that datetime serialization preserves information.

        Property: Datetime → ISO string → datetime should be lossless.
        """
        iso_string = dt.isoformat()
        parsed = datetime.fromisoformat(iso_string)

        # Should be equal (within microsecond precision)
        assert abs((parsed - dt).total_seconds()) < 0.001

    @given(
        st.timedeltas(
            min_value=timedelta(seconds=0),
            max_value=timedelta(days=365),
        )
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_timedelta_serialization_roundtrip(self, td):
        """Test that timedelta serialization preserves duration.

        Property: timedelta → seconds → timedelta should be lossless.
        """
        seconds = td.total_seconds()
        reconstructed = timedelta(seconds=seconds)

        # Should be equal
        assert abs((reconstructed - td).total_seconds()) < 0.001


# Configuration for hypothesis
#
# These settings control hypothesis behavior:
# - max_examples: Number of test cases to generate
# - deadline: Maximum time per test case
# - suppress_health_check: Skip health checks that don't apply

DEFAULT_HYPOTHESIS_SETTINGS = settings(
    max_examples=50,  # Run 50 test cases per property
    deadline=None,  # No time limit per test
    suppress_health_check=[
        HealthCheck.function_scoped_fixture,  # Allow function-scoped fixtures
        HealthCheck.too_slow,  # Allow slower tests
    ],
)

# Apply settings to all tests in this module
settings.register_profile("default", DEFAULT_HYPOTHESIS_SETTINGS)
settings.load_profile("default")
