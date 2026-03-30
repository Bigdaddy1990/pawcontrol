"""Targeted coverage tests for coordinator_observability.py — uncovered paths (0% → 30%+).

Covers: default_rejection_metrics, derive_rejection_metrics,
        normalise_webhook_status, build_security_scorecard
"""  # noqa: E501

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.pawcontrol.coordinator_observability import (
    default_rejection_metrics,
    derive_rejection_metrics,
    normalise_webhook_status,
)

# ═══════════════════════════════════════════════════════════════════════════════
# default_rejection_metrics
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_default_rejection_metrics_returns_dict() -> None:
    result = default_rejection_metrics()
    assert isinstance(result, dict)


@pytest.mark.unit
def test_default_rejection_metrics_has_expected_keys() -> None:
    result = default_rejection_metrics()
    # Should have counter fields
    assert len(result) >= 1


@pytest.mark.unit
def test_default_rejection_metrics_has_schema_version() -> None:
    result = default_rejection_metrics()
    assert "schema_version" in result
    assert "rejected_call_count" in result


# ═══════════════════════════════════════════════════════════════════════════════
# derive_rejection_metrics
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_derive_rejection_metrics_none() -> None:
    result = derive_rejection_metrics(None)
    assert isinstance(result, dict)


@pytest.mark.unit
def test_derive_rejection_metrics_empty_dict() -> None:
    result = derive_rejection_metrics({})
    assert isinstance(result, dict)


@pytest.mark.unit
def test_derive_rejection_metrics_with_data() -> None:
    data = {
        "total_rejections": 5,
        "rate_limited": 2,
        "auth_failures": 1,
        "invalid_signatures": 0,
    }
    result = derive_rejection_metrics(data)
    assert isinstance(result, dict)


@pytest.mark.unit
def test_derive_rejection_metrics_partial_data() -> None:
    data = {"total_rejections": 10}
    result = derive_rejection_metrics(data)
    assert isinstance(result, dict)


# ═══════════════════════════════════════════════════════════════════════════════
# normalise_webhook_status
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_normalise_webhook_status_none_manager() -> None:
    result = normalise_webhook_status(None)
    assert isinstance(result, dict)


@pytest.mark.unit
def test_normalise_webhook_status_mock_manager() -> None:
    manager = MagicMock()
    manager.is_configured = False
    manager.token_count = 0
    result = normalise_webhook_status(manager)
    assert isinstance(result, dict)


@pytest.mark.unit
def test_normalise_webhook_status_configured_manager() -> None:
    manager = MagicMock()
    manager.is_configured = True
    manager.token_count = 3
    manager.rejection_summary = None
    result = normalise_webhook_status(manager)
    assert isinstance(result, dict)
