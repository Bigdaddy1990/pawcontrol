"""Coverage tests for selected helpers in ``utils._legacy``."""

from custom_components.pawcontrol.utils._legacy import (
    build_error_context,
    deep_merge_dicts,
    is_number,
    sanitize_dog_id,
)


def test_build_error_context_prefers_error_message_over_reason() -> None:
    """The context message should mirror the error string when provided."""
    error = ValueError("invalid profile")

    context = build_error_context("timeout", error)

    assert context.error is error
    assert context.reason == "timeout"
    assert context.message == "invalid profile"
    assert context.classification


def test_build_error_context_uses_reason_when_error_missing() -> None:
    """The reason should be used as message when no exception exists."""
    context = build_error_context("auth_failed", None)

    assert context.reason == "auth_failed"
    assert context.error is None
    assert context.message == "auth_failed"
    assert context.classification


def test_deep_merge_dicts_returns_merged_copy_without_mutating_input() -> None:
    """Nested mappings should merge recursively on a copied output mapping."""
    base = {
        "dog": {"name": "Luna", "age": 5},
        "active": True,
    }
    updates = {
        "dog": {"age": 6, "breed": "Collie"},
        "last_feed": "2026-03-27T07:30:00+00:00",
    }

    merged = deep_merge_dicts(base, updates)

    assert merged == {
        "dog": {"name": "Luna", "age": 6, "breed": "Collie"},
        "active": True,
        "last_feed": "2026-03-27T07:30:00+00:00",
    }
    assert base == {
        "dog": {"name": "Luna", "age": 5},
        "active": True,
    }


def test_is_number_accepts_real_numbers_but_rejects_booleans() -> None:
    """`is_number` should keep bool values out of numeric flows."""
    assert is_number(1)
    assert is_number(3.14)
    assert not is_number(True)
    assert not is_number("3.14")


def test_sanitize_dog_id_handles_prefix_and_hash_fallback() -> None:
    """Dog IDs should normalize, prepend prefix, and hash empty results."""
    assert sanitize_dog_id("Nova 007") == "nova_007"
    assert sanitize_dog_id("007") == "dog_007"

    hashed = sanitize_dog_id("***")

    assert hashed.startswith("dog_")
    assert len(hashed) == 12
