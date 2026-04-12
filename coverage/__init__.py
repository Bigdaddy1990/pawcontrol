"""Small coverage.py shim used for dependency-light test collection."""


class Coverage:
    """Tiny subset of ``coverage.Coverage`` used during tests."""

    def __init__(self, *args, **kwargs) -> None:
        """Store constructor arguments for compatibility checks."""
        self.args = args
        self.kwargs = kwargs

    def start(self) -> None:
        """Start collection (no-op in shim)."""
        return None

    def stop(self) -> None:
        """Stop collection (no-op in shim)."""
        return None

    def save(self) -> None:
        """Persist collected data (no-op in shim)."""
        return None


__all__ = ["Coverage"]
