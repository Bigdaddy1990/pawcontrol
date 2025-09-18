"""Runtime patches for compatibility with third-party dependencies.

This project runs on Python 3.13 during testing, but some third-party
packages that ship with the test suite still expect private helpers from
`uuid` that were removed in Python 3.13.  The Home Assistant test helper
`pytest-homeassistant-custom-component` depends on `freezegun`, which
tries to import ``uuid._uuid_generate_time`` and ``uuid._load_system_functions``.
Without shims the import fails before our tests even start.  We provide a
minimal, well-documented compatibility layer so that those modules can be
imported safely on modern Python versions.  The helpers delegate to the
public ``uuid._generate_time_safe`` implementation available since Python
3.8, keeping behaviour consistent with CPython's previous private APIs.
"""

from __future__ import annotations

import types
import uuid

if not hasattr(uuid, "_uuid_generate_time"):
    def _uuid_generate_time() -> bytes:
        """Return a time-based UUID byte sequence.

        This mirrors the return type of the legacy private CPython helper
        that `freezegun` expects.  ``uuid._generate_time_safe`` returns a
        tuple of ``(bytes, clock_seq)`` so we only expose the first element
        to match the historical API.
        """

        generated = uuid._generate_time_safe()  # type: ignore[attr-defined]
        # `_generate_time_safe` returns ``(bytes, clock_seq)``; the legacy
        # helper only returned the raw bytes payload used to build UUID1
        # instances.
        return generated[0]

    uuid._uuid_generate_time = _uuid_generate_time  # type: ignore[attr-defined]

if not hasattr(uuid, "_load_system_functions"):
    def _load_system_functions() -> None:
        """Compatibility no-op for removed CPython internals.

        Older versions of ``freezegun`` call this helper during import to
        populate the private ``_uuid_generate_time`` attribute.  Our shim
        ensures that attribute is available above, so the function simply
        verifies it exists.
        """

        if not hasattr(uuid, "_uuid_generate_time"):
            uuid._uuid_generate_time = _uuid_generate_time  # type: ignore[attr-defined]

    uuid._load_system_functions = _load_system_functions  # type: ignore[attr-defined]

# ``freezegun`` also checks for ``uuid._UuidCreate`` on Windows.  That
# attribute still exists on Python 3.13 when running on Windows, but the
# tests execute on Linux where it is missing.  The import only needs the
# attribute to exist so we provide a stub matching the old behaviour.
if not hasattr(uuid, "_UuidCreate"):
    uuid._UuidCreate = types.SimpleNamespace  # type: ignore[attr-defined]
