"""Tests for datetime conversion utilities."""

from datetime import UTC, date, datetime

import pytest

from custom_components.pawcontrol.utils import ensure_utc_datetime


@pytest.mark.parametrize(
  "value,expected",
  [
    (None, None),
    (
      datetime(2024, 1, 1, 12, 30, tzinfo=UTC),
      datetime(2024, 1, 1, 12, 30, tzinfo=UTC),
    ),
    (date(2024, 1, 1), datetime(2024, 1, 1, tzinfo=UTC)),
    ("2024-01-01T12:30:00+02:00", datetime(2024, 1, 1, 10, 30, tzinfo=UTC)),
    ("2024-01-01", datetime(2024, 1, 1, tzinfo=UTC)),
    (1700000000, datetime(2023, 11, 14, 22, 13, 20, tzinfo=UTC)),
    (1700000000.0, datetime(2023, 11, 14, 22, 13, 20, tzinfo=UTC)),
  ],
)
def test_ensure_utc_datetime_handles_supported_inputs(value, expected) -> None:
  """ensure_utc_datetime should coerce supported types into UTC datetimes."""  # noqa: E111

  result = ensure_utc_datetime(value)  # noqa: E111

  if expected is None:  # noqa: E111
    assert result is None
  else:  # noqa: E111
    assert result == expected
    assert result.tzinfo is UTC


def test_ensure_utc_datetime_rejects_invalid_strings() -> None:
  """Invalid string inputs should return ``None``."""  # noqa: E111

  assert ensure_utc_datetime("") is None  # noqa: E111
  assert ensure_utc_datetime("not-a-date") is None  # noqa: E111


@pytest.mark.parametrize("value", [object(), [2024, 1, 1]])
def test_ensure_utc_datetime_rejects_unsupported_types(value) -> None:
  """Unsupported input types should return ``None``."""  # noqa: E111

  assert ensure_utc_datetime(value) is None  # noqa: E111


def test_ensure_utc_datetime_converts_naive_datetimes_to_utc() -> None:
  """Naive datetimes should be normalised to UTC."""  # noqa: E111

  naive = datetime(2024, 1, 1, 12, 0, 0)  # noqa: E111

  result = ensure_utc_datetime(naive)  # noqa: E111

  assert result == datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)  # noqa: E111
  assert result.tzinfo is UTC  # noqa: E111
