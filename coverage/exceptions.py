"""coverage.exceptions shim for dependency-light test execution."""


class NoDataError(Exception):
    """Raised when coverage data is not available."""


class DataError(Exception):
    """Raised when coverage input data is invalid."""


class CoverageWarning(Warning):
    """Warning class used by coverage shim integration."""
