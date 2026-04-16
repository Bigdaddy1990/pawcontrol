"""Data privacy and redaction for PawControl integration.

This module handles PII redaction, data anonymization, and privacy controls
to ensure GDPR compliance and protect user privacy.

Quality Scale: Platinum target
Home Assistant: 2025.9.0+
Python: 3.13+
"""

from collections.abc import Callable
from dataclasses import dataclass, field
import hashlib
import re
from re import Pattern
from typing import Any

from homeassistant.core import HomeAssistant

from .logging_utils import StructuredLogger

_LOGGER = StructuredLogger(__name__)


@dataclass
class RedactionRule:
    """Redaction rule for PII.

    Attributes:
        pattern: Regex pattern to match
        replacement: Replacement string
        field_names: Specific field names to redact
        redactor: Custom redaction function
    """

    pattern: Pattern[str] | None = None
    replacement: str = "[REDACTED]"
    field_names: list[str] = field(default_factory=list)
    redactor: Callable[[str], str] | None = None


class PIIRedactor:
    """Redacts personally identifiable information (PII).

    Automatically detects and redacts common PII patterns like
    emails, phone numbers, IP addresses, and custom patterns.

    Examples:
        >>> redactor = PIIRedactor()
        >>> clean = redactor.redact_text("My email is user@example.com")
        >>> # Result: "My email is [EMAIL]"
    """

    def __init__(self) -> None:
        """Initialize PII redactor."""
        self._rules: list[RedactionRule] = []
        self._register_default_rules()

    def _register_default_rules(self) -> None:
        """Register default PII redaction rules."""
        # Email addresses
        self._rules.append(
            RedactionRule(
                pattern=re.compile(
                    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
                ),
                replacement="[EMAIL]",
            )
        )

        # Phone numbers (various formats)
        self._rules.append(
            RedactionRule(
                pattern=re.compile(
                    r"\b(?:\+?1[-.]?)?\(?([0-9]{3})\)?[-.]?([0-9]{3})[-.]?([0-9]{4})\b"
                ),
                replacement="[PHONE]",
            )
        )

        # IP addresses (IPv4)
        self._rules.append(
            RedactionRule(
                pattern=re.compile(r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b"),
                replacement="[IP_ADDRESS]",
            )
        )

        # Credit card numbers (basic pattern)
        self._rules.append(
            RedactionRule(
                pattern=re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b"),
                replacement="[CREDIT_CARD]",
            )
        )

        # Social Security Numbers (US)
        self._rules.append(
            RedactionRule(
                pattern=re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
                replacement="[SSN]",
            )
        )

    def add_rule(self, rule: RedactionRule) -> None:
        r"""Add custom redaction rule.

        Args:
            rule: Redaction rule to add

        Examples:
            >>> redactor.add_rule(
            ...     RedactionRule(
            ...         pattern=re.compile(r"dog_id_\d+"), replacement="[DOG_ID]"
            ...     )
            ... )
        """
        self._rules.append(rule)

    def redact_text(self, text: str) -> str:
        """Redact PII from text.

        Args:
            text: Text to redact

        Returns:
            Redacted text

        Examples:
            >>> redactor.redact_text("Contact: user@example.com, 555-1234")
            'Contact: [EMAIL], [PHONE]'
        """
        if not isinstance(text, str):
            return text
        result = text

        for rule in self._rules:
            if rule.pattern:
                result = rule.pattern.sub(rule.replacement, result)
            elif rule.redactor:
                result = rule.redactor(result)

        return result

    def redact_dict(
        self,
        data: dict[str, Any],
        *,
        recursive: bool = True,
    ) -> dict[str, Any]:
        """Redact PII from dictionary.

        Args:
            data: Dictionary to redact
            recursive: Recursively redact nested dicts

        Returns:
            Redacted dictionary

        Examples:
            >>> redactor.redact_dict({"email": "user@example.com"})
            {'email': '[EMAIL]'}
        """
        redacted: dict[str, Any] = {}

        for key, value in data.items():
            # Check if field should be redacted by name
            should_redact_field = any(key in rule.field_names for rule in self._rules)
            if should_redact_field:
                redacted[key] = "[REDACTED]"
            elif isinstance(value, str):
                redacted[key] = self.redact_text(value)
            elif isinstance(value, dict) and recursive:
                redacted[key] = self.redact_dict(value, recursive=True)
            elif isinstance(value, list) and recursive:
                redacted[key] = [
                    self.redact_dict(item, recursive=True)
                    if isinstance(item, dict)
                    else (self.redact_text(item) if isinstance(item, str) else item)
                    for item in value
                ]
            else:
                redacted[key] = value

        return redacted


class GPSAnonymizer:
    """Anonymizes GPS coordinates.

    Reduces precision of GPS coordinates to protect exact location
    while maintaining general area information.

    Examples:
        >>> anonymizer = GPSAnonymizer(precision=3)
        >>> anon_lat, anon_lon = anonymizer.anonymize(45.5231, -122.6765)
        >>> # Result: (45.523, -122.677)
    """

    def __init__(self, precision: int = 3) -> None:
        """Initialize GPS anonymizer.

        Args:
            precision: Decimal places to keep (3 = ~111m accuracy)
        """
        self._precision = precision

    def anonymize(
        self,
        latitude: float,
        longitude: float,
    ) -> tuple[float, float]:
        """Anonymize GPS coordinates.

        Args:
            latitude: Original latitude
            longitude: Original longitude

        Returns:
            Tuple of (anonymized_latitude, anonymized_longitude)

        Examples:
            >>> anonymizer.anonymize(45.523123, -122.676543)
            (45.523, -122.677)
        """
        anon_lat = round(latitude, self._precision)
        anon_lon = round(longitude, self._precision)
        return anon_lat, anon_lon

    def anonymize_dict(
        self,
        data: dict[str, Any],
        *,
        lat_key: str = "latitude",
        lon_key: str = "longitude",
    ) -> dict[str, Any]:
        """Anonymize GPS coordinates in dictionary.

        Args:
            data: Dictionary containing coordinates
            lat_key: Key for latitude
            lon_key: Key for longitude

        Returns:
            Dictionary with anonymized coordinates
        """
        result = dict(data)

        if lat_key in result and lon_key in result:
            anon_lat, anon_lon = self.anonymize(
                result[lat_key],
                result[lon_key],
            )
            result[lat_key] = anon_lat
            result[lon_key] = anon_lon
        return result


class DataHasher:
    """Hashes sensitive data for anonymization.

    Uses cryptographic hashing to create irreversible anonymized
    identifiers while maintaining uniqueness.

    Examples:
        >>> hasher = DataHasher()
        >>> hashed = hasher.hash_string("user@example.com")
    """

    def __init__(self, algorithm: str = "sha256") -> None:
        """Initialize data hasher.

        Args:
            algorithm: Hash algorithm (sha256, sha512)
        """
        self._algorithm = algorithm

    def hash_string(self, text: str, salt: str = "") -> str:
        """Hash a string.

        Args:
            text: Text to hash
            salt: Optional salt

        Returns:
            Hexadecimal hash

        Examples:
            >>> hasher.hash_string("sensitive_data")
            'a4e2f8c9...'
        """
        data = f"{salt}{text}".encode()
        hash_func = getattr(hashlib, self._algorithm)
        return hash_func(data).hexdigest()

    def hash_dict(
        self,
        data: dict[str, Any],
        fields: list[str],
        salt: str = "",
    ) -> dict[str, Any]:
        """Hash specific fields in dictionary.

        Args:
            data: Dictionary to process
            fields: Field names to hash
            salt: Optional salt

        Returns:
            Dictionary with hashed fields
        """
        result = dict(data)

        for field_name in fields:
            if field_name in result and isinstance(result[field_name], str):
                result[field_name] = self.hash_string(result[field_name], salt)

        return result


class PrivacyManager:
    """Manages data privacy controls.

    Coordinates PII redaction, GPS anonymization, and data hashing
    for comprehensive privacy protection.

    Examples:
        >>> manager = PrivacyManager(hass)
        >>> clean_data = await manager.async_sanitize_data(user_data)
    """

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        gps_precision: int = 3,
        hash_algorithm: str = "sha256",
    ) -> None:
        """Initialize privacy manager.

        Args:
            hass: Home Assistant instance
            gps_precision: GPS coordinate precision
            hash_algorithm: Hash algorithm for anonymization
        """
        self._hass = hass
        self._redactor = PIIRedactor()
        self._gps_anonymizer = GPSAnonymizer(precision=gps_precision)
        self._hasher = DataHasher(algorithm=hash_algorithm)
        self._logger = StructuredLogger(__name__)

    async def async_sanitize_data(
        self,
        data: dict[str, Any],
        *,
        redact_pii: bool = True,
        anonymize_gps: bool = True,
        hash_fields: list[str] | None = None,
    ) -> dict[str, Any]:
        """Sanitize data for privacy.

        Args:
            data: Data to sanitize
            redact_pii: Whether to redact PII
            anonymize_gps: Whether to anonymize GPS
            hash_fields: Fields to hash

        Returns:
            Sanitized data

        Examples:
            >>> clean = await manager.async_sanitize_data(
            ...     {"email": "user@example.com", "latitude": 45.5231},
            ...     redact_pii=True,
            ...     anonymize_gps=True,
            ... )
        """
        result = dict(data)

        # Redact PII
        if redact_pii:
            result = self._redactor.redact_dict(result)
        # Anonymize GPS
        if anonymize_gps and "latitude" in result and "longitude" in result:
            result = self._gps_anonymizer.anonymize_dict(result)
        # Hash fields
        if hash_fields:
            result = self._hasher.hash_dict(result, hash_fields)
        self._logger.debug(
            "Data sanitized",
            redact_pii=redact_pii,
            anonymize_gps=anonymize_gps,
            hashed_fields=hash_fields or [],
        )

        return result

    async def async_prepare_diagnostics(
        self,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """Prepare data for diagnostics export.

        Automatically sanitizes all sensitive data before export.

        Args:
            data: Raw diagnostics data

        Returns:
            Sanitized diagnostics data
        """
        return await self.async_sanitize_data(
            data,
            redact_pii=True,
            anonymize_gps=True,
            hash_fields=["device_id", "mac_address"],
        )

    def add_redaction_rule(self, rule: RedactionRule) -> None:
        """Add custom redaction rule.

        Args:
            rule: Redaction rule

        Examples:
            >>> manager.add_redaction_rule(
            ...     RedactionRule(
            ...         field_names=["api_key", "secret"],
            ...         replacement="[SECRET]",
            ...     )
            ... )
        """
        self._redactor.add_rule(rule)


# Privacy decorators


def sanitize_return_value(
    redact_pii: bool = True,
    anonymize_gps: bool = True,
) -> Any:
    """Decorator to sanitize function return value.

    Args:
        redact_pii: Whether to redact PII
        anonymize_gps: Whether to anonymize GPS

    Returns:
        Decorated function

    Examples:
        >>> @sanitize_return_value(redact_pii=True)
        ... async def get_user_data():
        ...     return {"email": "user@example.com"}
    """
    redactor = PIIRedactor()
    gps_anonymizer = GPSAnonymizer()

    def decorator(func: Any) -> Any:
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            result = await func(*args, **kwargs)
            if isinstance(result, dict):
                if redact_pii:
                    result = redactor.redact_dict(result)
                if anonymize_gps and "latitude" in result and "longitude" in result:
                    result = gps_anonymizer.anonymize_dict(result)
            return result

        return wrapper

    return decorator


# Utility functions


def mask_string(text: str, visible_chars: int = 4) -> str:
    """Mask string showing only first N characters.

    Args:
        text: String to mask
        visible_chars: Number of visible characters

    Returns:
        Masked string

    Examples:
        >>> mask_string("sensitive_data", visible_chars=4)
        'sens***********'
    """
    if len(text) <= visible_chars:
        return "*" * len(text)

    return text[:visible_chars] + "*" * (len(text) - visible_chars)


def anonymize_user_id(user_id: str) -> str:
    """Anonymize user ID.

    Args:
        user_id: User ID to anonymize

    Returns:
        Anonymized ID

    Examples:
        >>> anonymize_user_id("user_12345")
        'user_a4e2f...'
    """
    hasher = DataHasher()
    hash_value = hasher.hash_string(user_id)
    return f"user_{hash_value[:8]}"
