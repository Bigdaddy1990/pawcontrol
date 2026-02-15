"""Webhook security for PawControl integration.

This module provides HMAC signature verification, rate limiting, and request
validation for webhook endpoints to prevent unauthorized access and abuse.

Quality Scale: Platinum target
Home Assistant: 2025.9.0+
Python: 3.13+
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
from collections import defaultdict
from collections import deque
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from typing import Any

from homeassistant.core import HomeAssistant

from .exceptions import AuthenticationError
from .exceptions import RateLimitError
from .exceptions import ValidationError
from .logging_utils import StructuredLogger

_LOGGER = logging.getLogger(__name__)


class WebhookSecurityError(ValidationError):
  """Error raised when webhook payload validation fails."""

  def __init__(self, message: str) -> None:
    """Initialize webhook security error."""
    super().__init__(
      message,
      field_name="webhook",
      expected_type="signed request",
      received_value=None,
    )


@dataclass
class WebhookRequest:
  """Represents a webhook request.

  Attributes:
      payload: Request payload
      signature: HMAC signature from headers
      timestamp: Request timestamp
      source_ip: Source IP address
      headers: Request headers
  """

  payload: bytes
  signature: str | None
  timestamp: float
  source_ip: str | None = None
  headers: dict[str, str] = field(default_factory=dict)


@dataclass
class RateLimitConfig:
  """Rate limit configuration.

  Attributes:
      requests_per_minute: Maximum requests per minute
      requests_per_hour: Maximum requests per hour
      burst_size: Maximum burst size
      ban_duration_seconds: Ban duration after limit exceeded
  """

  requests_per_minute: int = 60
  requests_per_hour: int = 1000
  burst_size: int = 10
  ban_duration_seconds: float = 300.0  # 5 minutes


@dataclass
class RateLimitState:
  """Rate limit state for a source.

  Attributes:
      source: Source identifier (IP or user)
      requests_minute: Requests in last minute
      requests_hour: Requests in last hour
      banned_until: Ban expiration timestamp
      total_requests: Total requests from this source
  """

  source: str
  requests_minute: deque[float] = field(default_factory=lambda: deque(maxlen=100))
  requests_hour: deque[float] = field(default_factory=lambda: deque(maxlen=1000))
  banned_until: float | None = None
  total_requests: int = 0

  def is_banned(self) -> bool:
    """Check if source is currently banned."""
    if self.banned_until is None:
      return False
    return time.time() < self.banned_until

  def add_request(self, timestamp: float | None = None) -> None:
    """Record a request."""
    if timestamp is None:
      timestamp = time.time()
    self.requests_minute.append(timestamp)
    self.requests_hour.append(timestamp)
    self.total_requests += 1

  def get_minute_count(self) -> int:
    """Get request count in last minute."""
    cutoff = time.time() - 60
    return sum(1 for ts in self.requests_minute if ts > cutoff)

  def get_hour_count(self) -> int:
    """Get request count in last hour."""
    cutoff = time.time() - 3600
    return sum(1 for ts in self.requests_hour if ts > cutoff)


class WebhookAuthenticator:
  """HMAC-based webhook authentication.

  Verifies webhook requests using HMAC signatures to prevent
  unauthorized access and replay attacks.

  Examples:
      >>> auth = WebhookAuthenticator(secret="my_secret")
      >>> is_valid = auth.verify_signature(payload, signature)
  """

  def __init__(
    self,
    secret: str,
    *,
    algorithm: str = "sha256",
    max_timestamp_diff: float = 300.0,
  ) -> None:
    """Initialize webhook authenticator.

    Args:
        secret: Shared secret for HMAC
        algorithm: Hash algorithm (sha256, sha512)
        max_timestamp_diff: Maximum timestamp difference in seconds
    """
    self._secret = secret.encode() if isinstance(secret, str) else secret
    self._algorithm = algorithm
    self._max_timestamp_diff = max_timestamp_diff
    self._logger = StructuredLogger(__name__)

  def generate_signature(
    self,
    payload: bytes,
    timestamp: float | None = None,
  ) -> tuple[str, float]:
    """Generate HMAC signature for payload.

    Args:
        payload: Request payload
        timestamp: Optional timestamp (uses current time if None)

    Returns:
        Tuple of (signature, timestamp)

    Examples:
        >>> signature, ts = auth.generate_signature(b"payload")
    """
    if timestamp is None:
      timestamp = time.time()

    # Combine payload with timestamp
    message = f"{timestamp}:{payload.decode()}".encode()

    # Generate HMAC
    signature = hmac.new(
      self._secret,
      message,
      getattr(hashlib, self._algorithm),
    ).hexdigest()

    return signature, timestamp

  def verify_signature(
    self,
    payload: bytes,
    signature: str,
    timestamp: float,
  ) -> bool:
    """Verify HMAC signature.

    Args:
        payload: Request payload
        signature: Provided signature
        timestamp: Request timestamp

    Returns:
        True if signature is valid

    Raises:
        AuthenticationError: If verification fails
    """
    # Check timestamp is recent
    current_time = time.time()
    time_diff = abs(current_time - timestamp)

    if time_diff > self._max_timestamp_diff:
      self._logger.warning(
        "Webhook timestamp too old",
        timestamp=timestamp,
        current_time=current_time,
        diff=time_diff,
      )
      raise AuthenticationError(f"Timestamp difference too large: {time_diff:.1f}s")

    # Generate expected signature
    expected_signature, _ = self.generate_signature(payload, timestamp)

    # Constant-time comparison
    if not hmac.compare_digest(signature, expected_signature):
      self._logger.error(
        "Webhook signature verification failed",
        provided_signature=signature[:16] + "...",
      )
      raise AuthenticationError("Invalid signature")

    return True

  def verify_request(self, request: WebhookRequest) -> bool:
    """Verify complete webhook request.

    Args:
        request: Webhook request to verify

    Returns:
        True if request is valid

    Raises:
        AuthenticationError: If verification fails
    """
    if request.signature is None:
      raise AuthenticationError("Missing signature")

    return self.verify_signature(
      request.payload,
      request.signature,
      request.timestamp,
    )


class WebhookRateLimiter:
  """Rate limiter for webhook endpoints.

  Prevents abuse by limiting request rate per source (IP address).

  Examples:
      >>> limiter = WebhookRateLimiter(config)
      >>> limiter.check_limit("192.168.1.1")
  """

  def __init__(self, config: RateLimitConfig | None = None) -> None:
    """Initialize rate limiter.

    Args:
        config: Rate limit configuration
    """
    self._config = config or RateLimitConfig()
    self._states: dict[str, RateLimitState] = defaultdict(
      lambda: RateLimitState(source="unknown")
    )
    self._logger = StructuredLogger(__name__)

  def check_limit(self, source: str) -> None:
    """Check if source is within rate limits.

    Args:
        source: Source identifier (IP address)

    Raises:
        RateLimitError: If rate limit exceeded
    """
    state = self._states[source]
    state.source = source

    # Check if banned
    if state.is_banned():
      remaining = state.banned_until - time.time() if state.banned_until else 0
      self._logger.warning(
        "Blocked request from banned source",
        source=source,
        remaining_seconds=remaining,
      )
      raise RateLimitError(
        f"Source banned for {remaining:.0f}s more",
        retry_after=remaining,
      )

    # Record request
    state.add_request()

    # Check minute limit
    minute_count = state.get_minute_count()
    if minute_count > self._config.requests_per_minute:
      self._ban_source(state)
      raise RateLimitError(
        f"Rate limit exceeded: {minute_count} requests/minute",
        retry_after=self._config.ban_duration_seconds,
      )

    # Check hour limit
    hour_count = state.get_hour_count()
    if hour_count > self._config.requests_per_hour:
      self._ban_source(state)
      raise RateLimitError(
        f"Rate limit exceeded: {hour_count} requests/hour",
        retry_after=self._config.ban_duration_seconds,
      )

    # Log if approaching limit
    if minute_count > self._config.requests_per_minute * 0.8:
      self._logger.warning(
        "Source approaching rate limit",
        source=source,
        minute_count=minute_count,
        limit=self._config.requests_per_minute,
      )

  def _ban_source(self, state: RateLimitState) -> None:
    """Ban a source temporarily.

    Args:
        state: Rate limit state
    """
    state.banned_until = time.time() + self._config.ban_duration_seconds
    self._logger.warning(
      "Banned source for rate limit violation",
      source=state.source,
      duration=self._config.ban_duration_seconds,
      total_requests=state.total_requests,
    )

  def get_stats(self) -> dict[str, Any]:
    """Get rate limiter statistics.

    Returns:
        Statistics dictionary
    """
    total_requests = sum(s.total_requests for s in self._states.values())
    banned_sources = sum(1 for s in self._states.values() if s.is_banned())

    return {
      "total_sources": len(self._states),
      "total_requests": total_requests,
      "banned_sources": banned_sources,
      "config": {
        "requests_per_minute": self._config.requests_per_minute,
        "requests_per_hour": self._config.requests_per_hour,
        "ban_duration": self._config.ban_duration_seconds,
      },
    }

  def reset_source(self, source: str) -> None:
    """Reset rate limit for a source.

    Args:
        source: Source identifier
    """
    if source in self._states:
      del self._states[source]
      self._logger.info("Reset rate limit for source", source=source)


class WebhookValidator:
  """Validates webhook payloads.

  Ensures webhook payloads conform to expected schema and
  contain required fields.

  Examples:
      >>> validator = WebhookValidator(required_fields=["dog_id", "event"])
      >>> validator.validate_payload(payload)
  """

  def __init__(
    self,
    *,
    required_fields: list[str] | None = None,
    max_payload_size: int = 1024 * 100,  # 100KB
  ) -> None:
    """Initialize webhook validator.

    Args:
        required_fields: Required payload fields
        max_payload_size: Maximum payload size in bytes
    """
    self._required_fields = required_fields or []
    self._max_payload_size = max_payload_size
    self._logger = StructuredLogger(__name__)

  def validate_payload(self, payload: bytes | dict[str, Any]) -> dict[str, Any]:
    """Validate webhook payload.

    Args:
        payload: Payload to validate

    Returns:
        Validated payload as dictionary

    Raises:
        ValidationError: If validation fails
    """
    # Check size
    if isinstance(payload, bytes):
      if len(payload) > self._max_payload_size:
        raise ValidationError(
          f"Payload too large: {len(payload)} bytes (max: {self._max_payload_size})"
        )

      # Parse JSON
      import json

      try:
        data = json.loads(payload)
      except json.JSONDecodeError as e:
        self._logger.error("Invalid JSON payload", error=str(e))
        raise ValidationError(f"Invalid JSON: {e}") from e
    else:
      data = payload

    # Validate type
    if not isinstance(data, dict):
      raise ValidationError(f"Payload must be a dictionary, got {type(data)}")

    # Check required fields
    missing_fields = [f for f in self._required_fields if f not in data]
    if missing_fields:
      raise ValidationError(f"Missing required fields: {missing_fields}")

    # Sanitize strings
    sanitized = self._sanitize_payload(data)

    return sanitized

  def _sanitize_payload(self, data: dict[str, Any]) -> dict[str, Any]:
    """Sanitize payload data.

    Args:
        data: Raw payload data

    Returns:
        Sanitized payload
    """
    sanitized = {}

    for key, value in data.items():
      # Sanitize key
      clean_key = str(key).strip()

      # Sanitize value
      if isinstance(value, str):
        # Remove control characters
        clean_value = "".join(
          char for char in value if ord(char) >= 32 or char in "\n\r\t"
        )
        sanitized[clean_key] = clean_value.strip()
      elif isinstance(value, dict):
        sanitized[clean_key] = self._sanitize_payload(value)
      elif isinstance(value, list):
        sanitized[clean_key] = [
          self._sanitize_payload(item) if isinstance(item, dict) else item
          for item in value
        ]
      else:
        sanitized[clean_key] = value

    return sanitized


class WebhookSecurityManager:
  """Manages webhook security.

  Combines authentication, rate limiting, and validation for
  comprehensive webhook security.

  Examples:
      >>> manager = WebhookSecurityManager(hass, secret="my_secret")
      >>> await manager.async_process_webhook(request)
  """

  def __init__(
    self,
    hass: HomeAssistant,
    *,
    secret: str,
    rate_limit_config: RateLimitConfig | None = None,
    required_fields: list[str] | None = None,
  ) -> None:
    """Initialize webhook security manager.

    Args:
        hass: Home Assistant instance
        secret: Shared secret for HMAC
        rate_limit_config: Rate limit configuration
        required_fields: Required payload fields
    """
    self._hass = hass
    self._authenticator = WebhookAuthenticator(secret)
    self._rate_limiter = WebhookRateLimiter(rate_limit_config)
    self._validator = WebhookValidator(required_fields=required_fields)
    self._logger = StructuredLogger(__name__)

  async def async_process_webhook(
    self,
    request: WebhookRequest,
  ) -> dict[str, Any]:
    """Process webhook with security checks.

    Args:
        request: Webhook request

    Returns:
        Validated payload

    Raises:
        AuthenticationError: If authentication fails
        RateLimitError: If rate limit exceeded
        ValidationError: If validation fails
    """
    # Check rate limit
    if request.source_ip:
      self._rate_limiter.check_limit(request.source_ip)

    # Verify signature
    self._authenticator.verify_request(request)

    # Validate payload
    validated_payload = self._validator.validate_payload(request.payload)

    self._logger.info(
      "Webhook processed successfully",
      source_ip=request.source_ip,
      payload_size=len(request.payload),
    )

    return validated_payload

  def get_security_stats(self) -> dict[str, Any]:
    """Get security statistics.

    Returns:
        Statistics dictionary
    """
    return {
      "rate_limiter": self._rate_limiter.get_stats(),
      "timestamp": datetime.now().isoformat(),
    }
