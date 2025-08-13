class GPSError(Exception):
    """Generic GPS error."""


class InvalidCoordinates(ValueError):
    """Thrown when invalid coordinates are provided."""


class GPSProviderError(Exception):
    """Upstream GPS provider error."""


class DataValidationError(ValueError):
    """Validation error for provided data."""
