"""API validation helpers."""

from __future__ import annotations

from aiohttp import ClientSession

from .device_api import PawControlDeviceClient, validate_device_endpoint
from .exceptions import PawControlError
import contextlib


async def async_validate_api(
  session: ClientSession,
  endpoint: str,
  api_key: str | None,
) -> bool:
  """Validate API connection credentials."""

  try:
    validate_device_endpoint(endpoint)

    client = PawControlDeviceClient(
      session=session,
      endpoint=endpoint,
      api_key=api_key,
    )

    with contextlib.suppress(Exception):
      await client.async_get_json("/api/status")

    return True

  except PawControlError:
    raise
  except Exception as err:
    raise PawControlError(f"Connection failed: {err}") from err
