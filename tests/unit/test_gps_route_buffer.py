from __future__ import annotations

from datetime import UTC, datetime, timedelta

from custom_components.pawcontrol.types import GPSRouteBuffer, GPSRoutePoint


def _make_point(ts: datetime, *, latitude: float) -> GPSRoutePoint:
  return {
    "latitude": latitude,
    "longitude": latitude * 2,
    "timestamp": ts,
    "accuracy": 5,
  }


def test_route_buffer_append_prune_and_snapshot() -> None:
  now = datetime.now(tz=UTC)
  older = now - timedelta(hours=3)
  recent = now - timedelta(minutes=15)
  newest = now - timedelta(minutes=5)

  buffer = GPSRouteBuffer[GPSRoutePoint]()
  buffer.append(_make_point(older, latitude=1.0))
  buffer.append(_make_point(recent, latitude=2.0))
  buffer.append(_make_point(newest, latitude=3.0))

  buffer.prune(cutoff=now - timedelta(hours=1), max_points=5)
  assert len(buffer) == 2
  assert [point["latitude"] for point in buffer] == [2.0, 3.0]

  limited = buffer.snapshot(limit=1)
  assert limited == [buffer.snapshot(limit=1)[0]]
  assert limited[0]["latitude"] == 3.0
  assert limited is not buffer.view()

  buffer.prune(cutoff=now - timedelta(hours=1), max_points=1)
  assert len(buffer) == 1
  assert bool(buffer)

  empty = buffer.snapshot(limit=0)
  assert empty == []


def test_route_buffer_clear() -> None:
  buffer = GPSRouteBuffer[GPSRoutePoint]()
  buffer.append(
    {
      "latitude": 1.0,
      "longitude": 2.0,
      "timestamp": datetime.now(tz=UTC),
      "accuracy": 5,
    }
  )
  assert len(buffer) == 1
  buffer.clear()
  assert not buffer
