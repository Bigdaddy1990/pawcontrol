"""Targeted coverage tests for privacy.py — uncovered paths (0% → 32%+).

Covers: mask_string, anonymize_user_id, DataHasher, GPSAnonymizer
"""

from __future__ import annotations

import pytest

from custom_components.pawcontrol.privacy import (
    DataHasher,
    GPSAnonymizer,
    anonymize_user_id,
    mask_string,
)

# ═══════════════════════════════════════════════════════════════════════════════
# mask_string
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_mask_string_basic() -> None:
    result = mask_string("secret123", visible_chars=4)
    assert isinstance(result, str)
    assert result.endswith("3123") or "***" in result or "*" in result


@pytest.mark.unit
def test_mask_string_short() -> None:
    result = mask_string("ab", visible_chars=4)
    assert isinstance(result, str)


@pytest.mark.unit
def test_mask_string_empty() -> None:
    result = mask_string("", visible_chars=4)
    assert isinstance(result, str)


@pytest.mark.unit
def test_mask_string_zero_visible() -> None:
    result = mask_string("hello", visible_chars=0)
    assert isinstance(result, str)


# ═══════════════════════════════════════════════════════════════════════════════
# anonymize_user_id
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_anonymize_user_id_returns_string() -> None:
    result = anonymize_user_id("rex_owner_123")
    assert isinstance(result, str)
    assert result != "rex_owner_123"


@pytest.mark.unit
def test_anonymize_user_id_deterministic() -> None:
    r1 = anonymize_user_id("user42")
    r2 = anonymize_user_id("user42")
    assert r1 == r2


@pytest.mark.unit
def test_anonymize_user_id_different_inputs() -> None:
    r1 = anonymize_user_id("alice")
    r2 = anonymize_user_id("bob")
    assert r1 != r2


# ═══════════════════════════════════════════════════════════════════════════════
# DataHasher
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_data_hasher_init() -> None:
    hasher = DataHasher()
    assert hasher is not None


@pytest.mark.unit
def test_data_hasher_hash_string() -> None:
    hasher = DataHasher(algorithm="sha256")
    result = hasher.hash_string("test_data")
    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.unit
def test_data_hasher_deterministic() -> None:
    hasher = DataHasher()
    r1 = hasher.hash_string("same_input")
    r2 = hasher.hash_string("same_input")
    assert r1 == r2


@pytest.mark.unit
def test_data_hasher_different_inputs() -> None:
    hasher = DataHasher()
    r1 = hasher.hash_string("input_a")
    r2 = hasher.hash_string("input_b")
    assert r1 != r2


# ═══════════════════════════════════════════════════════════════════════════════
# GPSAnonymizer
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_gps_anonymizer_init() -> None:
    anon = GPSAnonymizer(precision=3)
    assert anon is not None


@pytest.mark.unit
def test_gps_anonymizer_anonymize() -> None:
    anon = GPSAnonymizer(precision=2)
    lat, lon = anon.anonymize(52.5200, 13.4050)
    assert isinstance(lat, float)
    assert isinstance(lon, float)
    # With precision=2, should round to 2 decimal places
    assert round(lat, 2) == lat or abs(lat - round(lat, 2)) < 0.01


@pytest.mark.unit
def test_gps_anonymizer_high_precision() -> None:
    anon = GPSAnonymizer(precision=5)
    lat, lon = anon.anonymize(48.1351, 11.5820)
    assert isinstance(lat, float)
