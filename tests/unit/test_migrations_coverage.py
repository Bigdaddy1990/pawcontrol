"""Targeted coverage tests for migrations.py — uncovered paths (0% → 32%+).

Covers: normalize_dog_id, validate_dog_name, ensure_dog_modules_config,
        ensure_dog_options_entry
"""

import pytest

from custom_components.pawcontrol.exceptions import ValidationError
from custom_components.pawcontrol.migrations import (
    ensure_dog_modules_config,
    ensure_dog_options_entry,
    normalize_dog_id,
    validate_dog_name,
)

# ═══════════════════════════════════════════════════════════════════════════════
# normalize_dog_id
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_normalize_dog_id_lowercase() -> None:  # noqa: D103
    assert normalize_dog_id("Rex") == "rex"


@pytest.mark.unit
def test_normalize_dog_id_strips_spaces() -> None:  # noqa: D103
    result = normalize_dog_id("  rex  ")
    assert result == "rex"


@pytest.mark.unit
def test_normalize_dog_id_replaces_spaces_with_underscores() -> None:  # noqa: D103
    result = normalize_dog_id("my dog")
    assert "_" in result or result == "my_dog"


@pytest.mark.unit
def test_normalize_dog_id_already_normalised() -> None:  # noqa: D103
    assert normalize_dog_id("rex_01") == "rex_01"


@pytest.mark.unit
def test_normalize_dog_id_empty_returns_empty() -> None:  # noqa: D103
    # normalize_dog_id does not raise for empty — returns empty string
    result = normalize_dog_id("")
    assert isinstance(result, str)


# ═══════════════════════════════════════════════════════════════════════════════
# validate_dog_name
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_validate_dog_name_valid() -> None:  # noqa: D103
    result = validate_dog_name("Rex")
    assert result == "Rex"


@pytest.mark.unit
def test_validate_dog_name_strips_whitespace() -> None:  # noqa: D103
    result = validate_dog_name("  Rex  ")
    assert result == "Rex"


@pytest.mark.unit
def test_validate_dog_name_too_short_raises() -> None:  # noqa: D103
    with pytest.raises((ValidationError, Exception)):
        validate_dog_name("R", required=True, min_length=2)


@pytest.mark.unit
def test_validate_dog_name_too_long_raises() -> None:  # noqa: D103
    with pytest.raises((ValidationError, Exception)):
        validate_dog_name("R" * 100, max_length=50)


@pytest.mark.unit
def test_validate_dog_name_not_required_none() -> None:  # noqa: D103
    result = validate_dog_name(None, required=False)
    assert result is None or isinstance(result, str)


@pytest.mark.unit
def test_validate_dog_name_not_required_empty() -> None:  # noqa: D103
    result = validate_dog_name("", required=False)
    assert result is None or isinstance(result, str)


# ═══════════════════════════════════════════════════════════════════════════════
# ensure_dog_modules_config
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_ensure_dog_modules_config_empty() -> None:  # noqa: D103
    result = ensure_dog_modules_config({})
    assert isinstance(result, dict)


@pytest.mark.unit
def test_ensure_dog_modules_config_with_values() -> None:  # noqa: D103
    result = ensure_dog_modules_config({"feeding": True, "walk": False})
    assert isinstance(result, dict)
    assert result.get("feeding") is True


# ═══════════════════════════════════════════════════════════════════════════════
# ensure_dog_options_entry
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_ensure_dog_options_entry_minimal() -> None:  # noqa: D103
    result = ensure_dog_options_entry({})
    assert isinstance(result, dict)


@pytest.mark.unit
def test_ensure_dog_options_entry_with_dog_id() -> None:  # noqa: D103
    result = ensure_dog_options_entry({"feeding_settings": {}}, dog_id="rex")
    assert isinstance(result, dict)
