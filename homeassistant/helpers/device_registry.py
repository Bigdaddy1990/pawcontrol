"""Device registry stubs for tests."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable, Any

@dataclass
class DeviceEntry:
    identifiers: Iterable[tuple[str, str]] | None = None
