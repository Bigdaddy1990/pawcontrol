"""API validation helpers."""

from __future__ import annotations

from aiohttp import ClientSession

from .device_api import PawControlDeviceClient, validate_device_endpoint
from .exceptions import PawControlError


async def async_validate_api(
  session: ClientSession,
  endpoint: str,
  api_key: str | None,
) -> bool:
  """Validate API reachability and credentials.

  The validator is intentionally strict: endpoint normalization and an
  authenticated `/api/status` probe must both succeed. Failures are surfaced as
  ``PawControlError`` so config flows can present clear setup errors.
  """

  try:
    validate_device_endpoint(endpoint)

    client = PawControlDeviceClient(
      session=session,
      endpoint=endpoint,
      api_key=api_key,
    )

    await client.async_get_json("/api/status")

    return True

  except PawControlError:
    raise
  except Exception as err:
    raise PawControlError(f"Connection failed: {err}") from err
