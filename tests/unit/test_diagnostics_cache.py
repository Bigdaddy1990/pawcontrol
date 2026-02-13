from __future__ import annotations

from datetime import UTC, datetime

from custom_components.pawcontrol import diagnostics
from custom_components.pawcontrol.types import (
  CacheDiagnosticsSnapshot,
  CacheRepairAggregate,
)


def _summary_payload() -> dict[str, object]:
  now = datetime.now(UTC).isoformat()
  return {
    "total_caches": 2,
    "anomaly_count": 1,
    "severity": "warning",
    "generated_at": now,
    "totals": {
      "entries": 10,
      "hits": 7,
      "misses": 3,
      "expired_entries": 1,
      "expired_via_override": 0,
      "pending_expired_entries": 0,
      "pending_override_candidates": 0,
      "active_override_flags": 0,
    },
  }


def test_serialise_cache_snapshot_coerces_repair_summary() -> None:
  """Serialisation should export dataclass-backed repair summaries as mappings."""

  summary = CacheRepairAggregate.from_mapping(_summary_payload())
  snapshot = CacheDiagnosticsSnapshot(
    stats={"entries": 10},
    repair_summary=summary,
  )

  payload = diagnostics._serialise_cache_snapshot(snapshot)

  assert payload["repair_summary"] == summary.to_mapping()


def test_snapshot_from_mapping_returns_dataclass() -> None:
  """Snapshots parsed from mappings should materialise dataclass summaries."""

  summary_payload = _summary_payload()
  snapshot = CacheDiagnosticsSnapshot.from_mapping({"repair_summary": summary_payload})

  assert isinstance(snapshot.repair_summary, CacheRepairAggregate)
  assert snapshot.repair_summary.to_mapping() == summary_payload


def test_serialise_cache_snapshot_drops_invalid_repair_summary() -> None:
  """Unexpected repair summary payloads should be dropped from diagnostics."""

  snapshot = CacheDiagnosticsSnapshot(
    stats={"entries": 5},
    repair_summary="unexpected",  # type: ignore[arg-type]
  )

  payload = diagnostics._serialise_cache_snapshot(snapshot)

  assert "repair_summary" not in payload


def test_normalise_cache_snapshot_reuses_reload_safe_helper(monkeypatch) -> None:
  """Cache repair summaries should flow through the reload-safe helper."""

  original_summary = CacheRepairAggregate.from_mapping(_summary_payload())
  replacement_summary = CacheRepairAggregate.from_mapping(_summary_payload())
  snapshot = CacheDiagnosticsSnapshot(repair_summary=original_summary)
  captured: dict[str, object] = {}

  def _fake_ensure(summary: object) -> CacheRepairAggregate:
    captured["summary"] = summary
    return replacement_summary

  monkeypatch.setattr(
    diagnostics, "ensure_cache_repair_aggregate", _fake_ensure, raising=False
  )

  result = diagnostics._normalise_cache_snapshot(snapshot)

  assert captured["summary"] is not None
  assert result.repair_summary is replacement_summary
  assert result.repair_summary is not original_summary
