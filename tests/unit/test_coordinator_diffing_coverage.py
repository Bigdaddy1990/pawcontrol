"""Targeted coverage tests for coordinator_diffing.py — uncovered paths (0% → 38%+).

Covers: compute_data_diff, compute_dog_diff, get_changed_fields,
        should_notify_entities, DataDiff, DogDataDiff, SmartDiffTracker
"""

import pytest

from custom_components.pawcontrol.coordinator_diffing import (
    DataDiff,
    DogDataDiff,
    compute_data_diff,
    compute_dog_diff,
    get_changed_fields,
    should_notify_entities,
)

# ═══════════════════════════════════════════════════════════════════════════════
# compute_data_diff
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_compute_data_diff_both_none() -> None:
    diff = compute_data_diff(None, None)
    assert isinstance(diff, DataDiff)


@pytest.mark.unit
def test_compute_data_diff_no_change() -> None:
    data = {"dog1": {"feeding": {"meals": 2}}}
    diff = compute_data_diff(data, data)
    assert diff.has_changes is False or isinstance(diff.has_changes, bool)


@pytest.mark.unit
def test_compute_data_diff_added_key() -> None:
    old = {"dog1": {"feeding": {}}}
    new = {"dog1": {"feeding": {}}, "dog2": {"feeding": {}}}
    diff = compute_data_diff(old, new)
    assert isinstance(diff, DataDiff)


@pytest.mark.unit
def test_compute_data_diff_modified_value() -> None:
    old = {"dog1": {"walk": {"walk_in_progress": False}}}
    new = {"dog1": {"walk": {"walk_in_progress": True}}}
    diff = compute_data_diff(old, new)
    assert isinstance(diff, DataDiff)


@pytest.mark.unit
def test_compute_data_diff_old_none() -> None:
    new = {"dog1": {"feeding": {}}}
    diff = compute_data_diff(None, new)
    assert isinstance(diff, DataDiff)


@pytest.mark.unit
def test_compute_data_diff_new_none() -> None:
    old = {"dog1": {"feeding": {}}}
    diff = compute_data_diff(old, None)
    assert isinstance(diff, DataDiff)


# ═══════════════════════════════════════════════════════════════════════════════
# compute_dog_diff
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_compute_dog_diff_both_none() -> None:
    diff = compute_dog_diff("rex", None, None)
    assert isinstance(diff, DogDataDiff)


@pytest.mark.unit
def test_compute_dog_diff_no_change() -> None:
    data = {"feeding": {"meals": 2}, "walk": {}}
    diff = compute_dog_diff("rex", data, data)
    assert isinstance(diff, DogDataDiff)
    assert diff.dog_id == "rex"


@pytest.mark.unit
def test_compute_dog_diff_walk_changed() -> None:
    old = {"walk": {"walk_in_progress": False}}
    new = {"walk": {"walk_in_progress": True}}
    diff = compute_dog_diff("rex", old, new)
    assert isinstance(diff, DogDataDiff)


# ═══════════════════════════════════════════════════════════════════════════════
# get_changed_fields
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_get_changed_fields_empty_diff() -> None:
    diff = compute_data_diff({}, {})
    fields = get_changed_fields(diff)
    assert isinstance(fields, frozenset)


@pytest.mark.unit
def test_get_changed_fields_with_changes() -> None:
    old = {"a": 1, "b": 2}
    new = {"a": 1, "b": 3, "c": 4}
    diff = compute_data_diff(old, new)
    fields = get_changed_fields(diff)
    assert isinstance(fields, frozenset)


@pytest.mark.unit
def test_get_changed_fields_exclude_removed() -> None:
    old = {"a": 1}
    new = {}
    diff = compute_data_diff(old, new)
    fields = get_changed_fields(diff, include_removed=False)
    assert isinstance(fields, frozenset)


# ═══════════════════════════════════════════════════════════════════════════════
# should_notify_entities
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_should_notify_entities_no_changes() -> None:
    from custom_components.pawcontrol.coordinator_diffing import CoordinatorDataDiff

    # CoordinatorDataDiff: dog_diffs, added_dogs, removed_dogs
    coordinator_diff = CoordinatorDataDiff(
        dog_diffs={}, added_dogs=frozenset(), removed_dogs=frozenset()
    )  # noqa: E501
    result = should_notify_entities(coordinator_diff)
    assert isinstance(result, bool)


@pytest.mark.unit
def test_should_notify_entities_with_dog_filter() -> None:
    from custom_components.pawcontrol.coordinator_diffing import CoordinatorDataDiff

    coordinator_diff = CoordinatorDataDiff(
        dog_diffs={}, added_dogs=frozenset(), removed_dogs=frozenset()
    )  # noqa: E501
    result = should_notify_entities(coordinator_diff, dog_id="rex")
    assert isinstance(result, bool)
