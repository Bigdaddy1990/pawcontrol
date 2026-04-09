"""Small yarl.URL compatibility shim used in dependency-light tests."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urljoin, urlparse


@dataclass(frozen=True)
class URL:
    """Minimal URL object supporting properties used by the integration."""

    raw: str

    @property
    def scheme(self) -> str:
        return urlparse(self.raw).scheme

    @property
    def host(self) -> str | None:
        return urlparse(self.raw).hostname

    def join(self, other: URL) -> URL:
        return URL(urljoin(self.raw.rstrip("/") + "/", other.raw.lstrip("/")))

    def __str__(self) -> str:
        return self.raw
