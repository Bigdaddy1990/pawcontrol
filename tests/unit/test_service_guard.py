"""Unit tests for service guard telemetry models."""

from __future__ import annotations

import pytest

from custom_components.pawcontrol.service_guard import (
  ServiceGuardResult,
  ServiceGuardSnapshot,
  normalise_guard_history,
  normalise_guard_result_payload,
)
from custom_components.pawcontrol.types import JSONMutableMapping


def test_service_guard_result_to_mapping() -> None:
  """Service guard results should emit structured payloads."""  # noqa: E111

  result = ServiceGuardResult(  # noqa: E111
    domain="notify",
    service="mobile_app",
    executed=False,
    reason="timeout",
    description="notification blocked by guard",
  )

  payload = result.to_mapping()  # noqa: E111

  assert payload["domain"] == "notify"  # noqa: E111
  assert payload["service"] == "mobile_app"  # noqa: E111
  assert payload["reason"] == "timeout"  # noqa: E111
  assert payload["description"] == "notification blocked by guard"  # noqa: E111
  assert payload["executed"] is False  # noqa: E111


def test_service_guard_snapshot_summary_and_metrics() -> None:
  """Snapshots should summarise guard telemetry consistently."""  # noqa: E111

  results = (  # noqa: E111
    ServiceGuardResult("notify", "mobile_app", True),
    ServiceGuardResult("light", "turn_on", False, reason="cooldown"),
    ServiceGuardResult("automation", "trigger", False, reason="cooldown"),
    ServiceGuardResult("script", "turn_on", False, reason="safety"),
  )

  snapshot = ServiceGuardSnapshot.from_sequence(results)  # noqa: E111

  summary = snapshot.to_summary()  # noqa: E111
  assert summary["executed"] == 1  # noqa: E111
  assert summary["skipped"] == 3  # noqa: E111
  assert summary["reasons"] == {"cooldown": 2, "safety": 1}  # noqa: E111
  assert [entry["service"] for entry in summary["results"]] == [  # noqa: E111
    "mobile_app",
    "turn_on",
    "trigger",
    "turn_on",
  ]

  metrics: JSONMutableMapping = {  # noqa: E111
    "executed": 2,
    "skipped": 1,
    "reasons": {"cooldown": 1},
  }
  payload = snapshot.accumulate(metrics)  # noqa: E111

  assert metrics["executed"] == 3  # noqa: E111
  assert metrics["skipped"] == 4  # noqa: E111
  assert metrics["reasons"] == {"cooldown": 3, "safety": 1}  # noqa: E111
  assert payload["last_results"][0]["domain"] == "notify"  # noqa: E111
  assert payload["last_results"][-1]["service"] == "turn_on"  # noqa: E111


@pytest.mark.parametrize(
  "raw_payload, expected",
  [
    ({"service": "light.turn_on", "reason": "guard"}, False),
    ({"executed": True, "domain": "notify"}, True),
    ({"executed": 0, "description": "skipped"}, False),
  ],
)
def test_normalise_guard_result_payload(
  raw_payload: JSONMutableMapping, expected: bool
) -> None:
  """Guard result payload normalisation should coerce booleans and text."""  # noqa: E111

  payload = normalise_guard_result_payload(raw_payload)  # noqa: E111
  assert payload["executed"] is expected  # noqa: E111
  assert all(isinstance(value, str | bool) for value in payload.values())  # noqa: E111


def test_normalise_guard_history_handles_mixed_entries() -> None:
  """Guard history normalisation must handle results and mappings."""  # noqa: E111

  history = normalise_guard_history([  # noqa: E111
    ServiceGuardResult("notify", "persistent_notification", True),
    {"domain": "script", "service": "turn_on", "reason": "cooldown"},
    object(),
  ])

  assert len(history) == 2  # noqa: E111
  assert history[0]["executed"] is True  # noqa: E111
  assert history[1]["domain"] == "script"  # noqa: E111
  assert history[1]["executed"] is False  # noqa: E111
