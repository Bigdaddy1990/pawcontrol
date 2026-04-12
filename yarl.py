"""Small yarl.URL compatibility shim used in dependency-light tests."""

from dataclasses import dataclass
from urllib.parse import urljoin, urlparse


@dataclass(frozen=True)
class URL:
    """Minimal URL object supporting properties used by the integration."""

    raw: str

    @property
    def scheme(self) -> str:
        """Return the URL scheme."""
        return urlparse(self.raw).scheme

    @property
    def host(self) -> str | None:
        """Return the hostname component."""
        return urlparse(self.raw).hostname

    def join(self, other: URL) -> URL:
        """Join this URL with another relative URL."""
        return URL(urljoin(self.raw.rstrip("/") + "/", other.raw.lstrip("/")))

    def __str__(self) -> str:
        """Return the raw URL string."""
        return self.raw
