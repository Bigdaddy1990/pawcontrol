"""HMAC signing and verification helpers for PawControl webhooks."""

from __future__ import annotations

import base64
import binascii
import hmac
import secrets
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import ClassVar


@dataclass(slots=True)
class WebhookSignature:
    """Container for webhook signature metadata."""

    algorithm: str
    signature: str
    timestamp: int
    nonce: str


class WebhookSecurityError(Exception):
    """Raised when webhook signature validation fails."""


class WebhookSecurityManager:
    """Generate and validate HMAC signatures for webhook payloads."""

    DEFAULT_TOLERANCE_SECONDS: ClassVar[int] = 300
    SUPPORTED_ALGORITHMS: ClassVar[set[str]] = {"sha256", "sha512"}

    def __init__(
        self,
        secret: str,
        *,
        algorithm: str = "sha256",
        tolerance_seconds: int = DEFAULT_TOLERANCE_SECONDS,
    ) -> None:
        """Create a security manager for signing and verifying webhooks."""
        if not secret:
            raise ValueError("secret must not be empty")

        normalized_algorithm = algorithm.lower()
        if normalized_algorithm not in self.SUPPORTED_ALGORITHMS:
            raise ValueError(
                f"Unsupported HMAC algorithm: {algorithm}. Supported algorithms: {sorted(self.SUPPORTED_ALGORITHMS)}",
            )

        self._secret = secret.encode("utf-8")
        self._algorithm = normalized_algorithm
        self._tolerance = max(0, tolerance_seconds)

    def sign(
        self,
        payload: bytes,
        *,
        timestamp: int | None = None,
        nonce: str | None = None,
    ) -> WebhookSignature:
        """Create an HMAC signature for the provided payload."""

        ts = (
            timestamp
            if timestamp is not None
            else int(
                datetime.now(UTC).timestamp(),
            )
        )
        nonce_value = nonce if nonce is not None else secrets.token_hex(16)
        digest = hmac.new(
            self._secret,
            self._build_message(payload, ts, nonce_value),
            self._algorithm,
        ).digest()

        signature = base64.b64encode(digest).decode("ascii")
        return WebhookSignature(
            algorithm=self._algorithm,
            signature=signature,
            timestamp=ts,
            nonce=nonce_value,
        )

    def verify(self, payload: bytes, signature: WebhookSignature) -> bool:
        """Verify that a payload matches the provided signature."""

        if signature.algorithm.lower() != self._algorithm:
            return False

        current_ts = int(datetime.now(UTC).timestamp())
        if abs(current_ts - signature.timestamp) > self._tolerance:
            return False

        expected = hmac.new(
            self._secret,
            self._build_message(payload, signature.timestamp, signature.nonce),
            self._algorithm,
        ).digest()

        try:
            provided = base64.b64decode(signature.signature, validate=True)
        except binascii.Error:
            return False

        return hmac.compare_digest(expected, provided)

    def build_headers(
        self,
        payload: bytes,
        *,
        header_prefix: str = "X-PawControl",
    ) -> dict[str, str]:
        """Create HTTP headers containing an HMAC signature."""

        signature = self.sign(payload)
        return {
            f"{header_prefix}-Signature": signature.signature,
            f"{header_prefix}-Algorithm": signature.algorithm,
            f"{header_prefix}-Timestamp": str(signature.timestamp),
            f"{header_prefix}-Nonce": signature.nonce,
        }

    @staticmethod
    def extract_signature(
        headers: Mapping[str, str],
        *,
        header_prefix: str = "X-PawControl",
    ) -> WebhookSignature | None:
        """Extract a signature from HTTP headers if present."""

        try:
            algorithm = headers[f"{header_prefix}-Algorithm"]
            signature = headers[f"{header_prefix}-Signature"]
            timestamp_str = headers[f"{header_prefix}-Timestamp"]
            nonce = headers[f"{header_prefix}-Nonce"]
        except KeyError:
            return None

        try:
            timestamp = int(timestamp_str)
        except (TypeError, ValueError) as err:
            raise WebhookSecurityError(
                f"Invalid webhook timestamp: {timestamp_str}",
            ) from err

        return WebhookSignature(
            algorithm=algorithm,
            signature=signature,
            timestamp=timestamp,
            nonce=nonce,
        )

    def _build_message(self, payload: bytes, timestamp: int, nonce: str) -> bytes:
        """Build the message that is signed or verified."""

        prefix = f"{timestamp}.{nonce}".encode()
        return prefix + b"." + payload
