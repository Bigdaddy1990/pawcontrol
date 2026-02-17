"""Input validation and sanitization for PawControl integration.

This module provides comprehensive input validation and sanitization to prevent
injection attacks, ensure data integrity, and protect against malicious inputs.

Quality Scale: Platinum target
Home Assistant: 2025.9.0+
Python: 3.13+
"""

from dataclasses import dataclass
import html
from pathlib import Path
import re
from typing import Any
import urllib.parse

from .exceptions import ValidationError
from .logging_utils import StructuredLogger

_LOGGER = StructuredLogger(__name__)


@dataclass
class ValidationResult:
    """Result of validation.

    Attributes:
        is_valid: Whether input is valid
        sanitized_value: Sanitized value
        errors: List of validation errors
    """
    is_valid: bool
    sanitized_value: Any
    errors: list[str]
    def __bool__(self) -> bool:
        """Boolean conversion returns is_valid."""
        return self.is_valid


class InputSanitizer:
    """Sanitizes user inputs to prevent injection attacks.

    Provides HTML escaping, SQL injection prevention, and
    general string sanitization.

    Examples:
        >>> sanitizer = InputSanitizer()
        >>> clean = sanitizer.sanitize_html("<script>alert('xss')</script>")
        >>> # Result: "&lt;script&gt;alert('xss')&lt;/script&gt;"
    """
    # Dangerous patterns to detect  # noqa: E114
    SQL_INJECTION_PATTERNS = [
        re.compile(r"(\bUNION\b.*\bSELECT\b)", re.IGNORECASE),
        re.compile(r"(\bDROP\b.*\bTABLE\b)", re.IGNORECASE),
        re.compile(r"(;.*\bDELETE\b.*\bFROM\b)", re.IGNORECASE),
        re.compile(r"(;.*\bINSERT\b.*\bINTO\b)", re.IGNORECASE),
        re.compile(r"(;.*\bUPDATE\b.*\bSET\b)", re.IGNORECASE),
    ]

    # NOTE:
    # We intentionally avoid regex-based HTML sanitization patterns here.
    # Filtering HTML with regular expressions is fragile and can lead to false
    # negatives/positives. `sanitize_html` uses `html.escape` for safe output.

    PATH_TRAVERSAL_PATTERNS = [
        re.compile(r"\.\./"),
        re.compile(r"\.\./"),
        re.compile(r"\.\.\\"),
    ]

    def sanitize_html(self, text: str) -> str:
        """Sanitize HTML to prevent XSS.

        Args:
            text: Text to sanitize

        Returns:
            HTML-escaped text

        Examples:
            >>> sanitizer.sanitize_html("<b>Bold</b>")
            '&lt;b&gt;Bold&lt;/b&gt;'
        """
        return html.escape(text)

    def sanitize_sql(self, text: str) -> str:
        """Sanitize SQL input.

        Args:
            text: Text to sanitize

        Returns:
            Sanitized text

        Raises:
            ValidationError: If SQL injection pattern detected

        Examples:
            >>> sanitizer.sanitize_sql("user_input")
            'user_input'
        """
        # Check for injection patterns
        for pattern in self.SQL_INJECTION_PATTERNS:
            if pattern.search(text):
                _LOGGER.error(
                    "SQL injection pattern detected",
                    pattern=pattern.pattern,
                    input_length=len(text),
                )
                raise ValidationError("Invalid input: SQL injection pattern detected")

        # Escape single quotes
        return text.replace("'", "''")

    def sanitize_url(self, url: str) -> str:
        """Sanitize URL.

        Args:
            url: URL to sanitize

        Returns:
            Sanitized URL

        Raises:
            ValidationError: If URL is invalid

        Examples:
            >>> sanitizer.sanitize_url("https://example.com/path?query=value")
            'https://example.com/path?query=value'
        """
        # Parse URL
        try:
            parsed = urllib.parse.urlparse(url)
        except Exception as e:
            raise ValidationError(f"Invalid URL: {e}") from e
        # Check scheme
        if parsed.scheme not in ("http", "https", ""):
            raise ValidationError(f"Invalid URL scheme: {parsed.scheme}")
        # Check for javascript: protocol
        if "javascript:" in url.lower():
            raise ValidationError("Invalid URL: JavaScript protocol not allowed")
        # URL encode and return
        return urllib.parse.urlunparse(parsed)

    def sanitize_path(self, path: str) -> str:
        """Sanitize file path to prevent traversal attacks.

        Args:
            path: File path to sanitize

        Returns:
            Sanitized path

        Raises:
            ValidationError: If path traversal detected

        Examples:
            >>> sanitizer.sanitize_path("files/document.txt")
            'files/document.txt'
        """
        # Check for traversal patterns
        for pattern in self.PATH_TRAVERSAL_PATTERNS:
            if pattern.search(path):
                raise ValidationError("Invalid path: Path traversal not allowed")

        # Normalize path
        normalized = str(Path(path).resolve())

        return normalized

    def sanitize_string(
        self,
        text: str,
        *,
        max_length: int | None = None,
        allowed_chars: str | None = None,
        strip_whitespace: bool = True,
    ) -> str:
        """Sanitize general string input.

        Args:
            text: Text to sanitize
            max_length: Maximum length (None for no limit)
            allowed_chars: Regex pattern for allowed characters
            strip_whitespace: Whether to strip leading/trailing whitespace

        Returns:
            Sanitized string

        Examples:
            >>> sanitizer.sanitize_string("  user input  ", max_length=50)
            'user input'
        """
        result = text

        # Strip whitespace
        if strip_whitespace:
            result = result.strip()
        # Check length
        if max_length and len(result) > max_length:
            _LOGGER.warning(
                "Input exceeds maximum length",
                length=len(result),
                max_length=max_length,
            )
            result = result[:max_length]
        # Filter characters
        if allowed_chars:
            pattern = re.compile(f"[^{allowed_chars}]")
            result = pattern.sub("", result)
        # Remove control characters (except newline, tab)
        result = "".join(char for char in result if ord(char) >= 32 or char in "\n\r\t")

        return result


class InputValidator:
    """Validates user inputs against defined constraints.

    Provides validation for common data types and custom rules.

    Examples:
        >>> validator = InputValidator()
        >>> result = validator.validate_email("user@example.com")
        >>> assert result.is_valid
    """
    def __init__(self) -> None:
        """Initialize input validator."""
        self._sanitizer = InputSanitizer()

    def validate_email(self, email: str) -> ValidationResult:
        """Validate email address.

        Args:
            email: Email to validate

        Returns:
            ValidationResult

        Examples:
            >>> result = validator.validate_email("user@example.com")
            >>> assert result.is_valid
        """
        errors = []

        # Sanitize
        sanitized = self._sanitizer.sanitize_string(email, max_length=255)

        # Check format
        pattern = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
        if not pattern.match(sanitized):
            errors.append("Invalid email format")
        return ValidationResult(
            is_valid=len(errors) == 0,
            sanitized_value=sanitized,
            errors=errors,
        )

    def validate_phone(self, phone: str) -> ValidationResult:
        """Validate phone number.

        Args:
            phone: Phone number to validate

        Returns:
            ValidationResult

        Examples:
            >>> result = validator.validate_phone("+1-555-1234")
            >>> assert result.is_valid
        """
        errors = []

        # Sanitize (keep only digits, +, -, space, parentheses)
        sanitized = self._sanitizer.sanitize_string(
            phone,
            allowed_chars=r"0-9+\-() ",
            max_length=20,
        )

        # Remove formatting
        digits_only = re.sub(r"[^0-9]", "", sanitized)

        # Check length (7-15 digits)
        if len(digits_only) < 7 or len(digits_only) > 15:
            errors.append(f"Invalid phone number length: {len(digits_only)}")
        return ValidationResult(
            is_valid=len(errors) == 0,
            sanitized_value=sanitized,
            errors=errors,
        )

    def validate_integer(
        self,
        value: Any,
        *,
        min_value: int | None = None,
        max_value: int | None = None,
    ) -> ValidationResult:
        """Validate integer value.

        Args:
            value: Value to validate
            min_value: Minimum allowed value
            max_value: Maximum allowed value

        Returns:
            ValidationResult

        Examples:
            >>> result = validator.validate_integer("42", min_value=0, max_value=100)
            >>> assert result.is_valid
        """
        errors = []

        # Convert to int
        try:
            int_value = int(value)
        except ValueError:
            errors.append(f"Cannot convert to integer: {value}")
            return ValidationResult(
                is_valid=False,
                sanitized_value=None,
                errors=errors,
            )
        except TypeError:
            errors.append(f"Cannot convert to integer: {value}")
            return ValidationResult(
                is_valid=False,
                sanitized_value=None,
                errors=errors,
            )

        # Check range
        if min_value is not None and int_value < min_value:
            errors.append(f"Value {int_value} < minimum {min_value}")
        if max_value is not None and int_value > max_value:
            errors.append(f"Value {int_value} > maximum {max_value}")
        return ValidationResult(
            is_valid=len(errors) == 0,
            sanitized_value=int_value,
            errors=errors,
        )

    def validate_float(
        self,
        value: Any,
        *,
        min_value: float | None = None,
        max_value: float | None = None,
    ) -> ValidationResult:
        """Validate float value.

        Args:
            value: Value to validate
            min_value: Minimum allowed value
            max_value: Maximum allowed value

        Returns:
            ValidationResult
        """
        errors = []

        # Convert to float
        try:
            float_value = float(value)
        except ValueError:
            errors.append(f"Cannot convert to float: {value}")
            return ValidationResult(
                is_valid=False,
                sanitized_value=None,
                errors=errors,
            )
        except TypeError:
            errors.append(f"Cannot convert to float: {value}")
            return ValidationResult(
                is_valid=False,
                sanitized_value=None,
                errors=errors,
            )

        # Check range
        if min_value is not None and float_value < min_value:
            errors.append(f"Value {float_value} < minimum {min_value}")
        if max_value is not None and float_value > max_value:
            errors.append(f"Value {float_value} > maximum {max_value}")
        return ValidationResult(
            is_valid=len(errors) == 0,
            sanitized_value=float_value,
            errors=errors,
        )

    def validate_url(self, url: str) -> ValidationResult:
        """Validate URL.

        Args:
            url: URL to validate

        Returns:
            ValidationResult
        """
        errors = []

        try:
            sanitized = self._sanitizer.sanitize_url(url)
        except ValidationError as e:
            errors.append(str(e))
            return ValidationResult(
                is_valid=False,
                sanitized_value=url,
                errors=errors,
            )

        return ValidationResult(
            is_valid=True,
            sanitized_value=sanitized,
            errors=[],
        )

    def validate_dict(
        self,
        data: dict[str, Any],
        schema: dict[str, dict[str, Any]],
    ) -> ValidationResult:
        """Validate dictionary against schema.

        Args:
            data: Data to validate
            schema: Validation schema

        Returns:
            ValidationResult

        Examples:
            >>> schema = {
            ...     "name": {"type": "str", "required": True, "max_length": 50},
            ...     "age": {"type": "int", "min_value": 0, "max_value": 150},
            ... }
            >>> result = validator.validate_dict({"name": "Buddy", "age": 5}, schema)
        """
        errors = []
        sanitized = {}

        for field, rules in schema.items():
            # Check required  # noqa: E114
            if rules.get("required") and field not in data:
                errors.append(f"Missing required field: {field}")
                continue

            # Skip if not present and not required  # noqa: E114
            if field not in data:
                continue

            value = data[field]
            # Validate by type  # noqa: E114
            field_type = rules.get("type", "str")
            if field_type == "str":
                result = self.validate_string(
                    value,
                    max_length=rules.get("max_length"),
                )
            elif field_type == "int":
                result = self.validate_integer(
                    value,
                    min_value=rules.get("min_value"),
                    max_value=rules.get("max_value"),
                )
            elif field_type == "float":
                result = self.validate_float(
                    value,
                    min_value=rules.get("min_value"),
                    max_value=rules.get("max_value"),
                )
            elif field_type == "email":
                result = self.validate_email(value)
            elif field_type == "url":
                result = self.validate_url(value)
            else:
                result = ValidationResult(True, value, [])

            if not result.is_valid:
                errors.extend([f"{field}: {e}" for e in result.errors])
            else:
                sanitized[field] = result.sanitized_value

        return ValidationResult(
            is_valid=len(errors) == 0,
            sanitized_value=sanitized,
            errors=errors,
        )

    def validate_string(
        self,
        value: str,
        *,
        min_length: int | None = None,
        max_length: int | None = None,
        pattern: str | None = None,
    ) -> ValidationResult:
        """Validate string value.

        Args:
            value: String to validate
            min_length: Minimum length
            max_length: Maximum length
            pattern: Regex pattern to match

        Returns:
            ValidationResult
        """
        errors = []

        # Sanitize
        sanitized = self._sanitizer.sanitize_string(value, max_length=max_length)

        # Check min length
        if min_length and len(sanitized) < min_length:
            errors.append(f"String too short: {len(sanitized)} < {min_length}")
        # Check pattern
        if pattern and not re.match(pattern, sanitized):
            errors.append(f"String does not match pattern: {pattern}")
        return ValidationResult(
            is_valid=len(errors) == 0,
            sanitized_value=sanitized,
            errors=errors,
        )


# Convenience functions


def sanitize_user_input(text: str, max_length: int = 1000) -> str:
    """Sanitize general user input.

    Args:
        text: User input
        max_length: Maximum length

    Returns:
        Sanitized text

    Examples:
        >>> sanitize_user_input("user input")
        'user input'
    """
    sanitizer = InputSanitizer()
    return sanitizer.sanitize_string(text, max_length=max_length)
def validate_and_sanitize(
    value: Any,
    validator_func: str,
    **kwargs: Any,
) -> Any:
    """Validate and sanitize value.

    Args:
        value: Value to validate
        validator_func: Validator function name
        **kwargs: Validator arguments

    Returns:
        Sanitized value

    Raises:
        ValidationError: If validation fails

    Examples:
        >>> clean = validate_and_sanitize("user@example.com", "validate_email")
    """
    validator = InputValidator()
    validate_method = getattr(validator, validator_func)
    result = validate_method(value, **kwargs)
    if not result.is_valid:
        raise ValidationError(f"Validation failed: {result.errors}")

    return result.sanitized_value