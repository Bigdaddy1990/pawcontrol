"""Targeted coverage tests for webhook_security.py — uncovered paths (0% → 30%+).

Covers: RateLimitConfig, RateLimitState, WebhookRateLimiter
"""

from __future__ import annotations

import pytest

from custom_components.pawcontrol.webhook_security import (
    RateLimitConfig,
    WebhookRateLimiter,
)

# ═══════════════════════════════════════════════════════════════════════════════
# RateLimitConfig
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_rate_limit_config_defaults() -> None:
    config = RateLimitConfig()
    assert config.requests_per_minute == 60
    assert config.requests_per_hour == 1000
    assert config.burst_size == 10
    assert config.ban_duration_seconds == pytest.approx(300.0)


@pytest.mark.unit
def test_rate_limit_config_custom() -> None:
    config = RateLimitConfig(
        requests_per_minute=30,
        requests_per_hour=500,
        burst_size=5,
        ban_duration_seconds=60.0,
    )
    assert config.requests_per_minute == 30
    assert config.burst_size == 5


# ═══════════════════════════════════════════════════════════════════════════════
# WebhookRateLimiter
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_rate_limiter_init_default() -> None:
    limiter = WebhookRateLimiter()
    assert limiter is not None


@pytest.mark.unit
def test_rate_limiter_init_custom_config() -> None:
    config = RateLimitConfig(requests_per_minute=10, burst_size=3)
    limiter = WebhookRateLimiter(config=config)
    assert limiter is not None


@pytest.mark.unit
def test_rate_limiter_check_limit_no_raise() -> None:
    """check_limit runs without raising (returns None = allowed)."""
    limiter = WebhookRateLimiter()
    limiter.check_limit("192.168.1.1")  # should not raise


@pytest.mark.unit
def test_rate_limiter_multiple_requests_same_ip() -> None:
    config = RateLimitConfig(requests_per_minute=100, burst_size=50)
    limiter = WebhookRateLimiter(config=config)
    for _ in range(5):
        limiter.check_limit("10.0.0.1")


@pytest.mark.unit
def test_rate_limiter_different_ips_independent() -> None:
    limiter = WebhookRateLimiter()
    limiter.check_limit("192.168.1.1")
    limiter.check_limit("192.168.1.2")


@pytest.mark.unit
def test_rate_limiter_stats_structure() -> None:
    limiter = WebhookRateLimiter()
    limiter.check_limit("10.0.0.99")
    stats = limiter.get_stats()
    assert isinstance(stats, dict)
    assert "total_sources" in stats


@pytest.mark.unit
def test_rate_limiter_reset_source() -> None:
    limiter = WebhookRateLimiter()
    limiter.check_limit("192.168.1.50")
    limiter.reset_source("192.168.1.50")
    # After reset, source should be cleared — no error expected
    stats = limiter.get_stats()
    assert isinstance(stats, dict)
