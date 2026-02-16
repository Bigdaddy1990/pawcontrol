from datetime import UTC, datetime, timedelta

from custom_components.pawcontrol.types import GPSRouteBuffer, GPSRoutePoint


def _make_point(ts: datetime, *, latitude: float) -> GPSRoutePoint:
  return {  # noqa: E111
    "latitude": latitude,
    "longitude": latitude * 2,
    "timestamp": ts,
    "accuracy": 5,
  }


def test_route_buffer_append_prune_and_snapshot() -> None:
  now = datetime.now(tz=UTC)  # noqa: E111
  older = now - timedelta(hours=3)  # noqa: E111
  recent = now - timedelta(minutes=15)  # noqa: E111
  newest = now - timedelta(minutes=5)  # noqa: E111

  buffer = GPSRouteBuffer[GPSRoutePoint]()  # noqa: E111
  buffer.append(_make_point(older, latitude=1.0))  # noqa: E111
  buffer.append(_make_point(recent, latitude=2.0))  # noqa: E111
  buffer.append(_make_point(newest, latitude=3.0))  # noqa: E111

  buffer.prune(cutoff=now - timedelta(hours=1), max_points=5)  # noqa: E111
  assert len(buffer) == 2  # noqa: E111
  assert [point["latitude"] for point in buffer] == [2.0, 3.0]  # noqa: E111

  limited = buffer.snapshot(limit=1)  # noqa: E111
  assert limited == [buffer.snapshot(limit=1)[0]]  # noqa: E111
  assert limited[0]["latitude"] == 3.0  # noqa: E111
  assert limited is not buffer.view()  # noqa: E111

  buffer.prune(cutoff=now - timedelta(hours=1), max_points=1)  # noqa: E111
  assert len(buffer) == 1  # noqa: E111
  assert bool(buffer)  # noqa: E111

  empty = buffer.snapshot(limit=0)  # noqa: E111
  assert empty == []  # noqa: E111


def test_route_buffer_clear() -> None:
  buffer = GPSRouteBuffer[GPSRoutePoint]()  # noqa: E111
  buffer.append({  # noqa: E111
    "latitude": 1.0,
    "longitude": 2.0,
    "timestamp": datetime.now(tz=UTC),
    "accuracy": 5,
  })
  assert len(buffer) == 1  # noqa: E111
  buffer.clear()  # noqa: E111
  assert not buffer  # noqa: E111
