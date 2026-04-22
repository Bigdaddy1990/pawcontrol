"""Exceptions exposed by the local coverage compatibility shim."""


class NoDataError(Exception):
    """Raised when coverage data is unavailable for reporting."""


class DataError(Exception):
    """Raised when coverage data cannot be processed."""


class CoverageWarning(Warning):
    """Compatibility warning used by the local coverage shim."""
