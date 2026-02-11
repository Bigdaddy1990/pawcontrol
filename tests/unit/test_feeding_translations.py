"""Unit tests for feeding compliance localisation helpers."""

from __future__ import annotations

from collections import UserString
from collections.abc import Callable, Iterable, Iterator, Sequence
from itertools import count
from pathlib import Path
from typing import cast

from custom_components.pawcontrol.feeding_translations import (
  _MAX_ISSUES,
  _MAX_MISSED_MEALS,
  _MAX_RECOMMENDATIONS,
  _SEQUENCE_SCAN_LIMIT,
  _collect_issue_summaries,
  _collect_missed_meals,
  _collect_recommendations,
  _format_structured_message,
  _iter_text_candidates,
  _normalise_sequence,
  build_feeding_compliance_notification,
  build_feeding_compliance_summary,
  get_feeding_compliance_translations,
)


def _limited_generator(
  limit: int, factory: Callable[[int], object]
) -> Iterable[object]:
  """Yield a bounded sequence that raises if more than ``limit`` items are requested."""

  def _generator() -> Iterator[object]:
    for index in count():
      if index >= limit:
        raise AssertionError("Generator consumed too many entries")
      yield factory(index)

  return _generator()


def test_normalise_sequence_supports_nested_iteration() -> None:
  """Snapshots should remain reusable even with nested iteration."""

  generator = (value for value in range(5))
  snapshot: Sequence[object] | None = _normalise_sequence(generator)
  assert snapshot is not None
  typed_snapshot = cast(Sequence[object], snapshot)

  outer_iterator = iter(typed_snapshot)
  first_item = next(outer_iterator)
  assert first_item == 0

  # Re-iterate while the original iterator is still active.
  replayed = list(typed_snapshot)
  assert replayed == [0, 1, 2, 3, 4]

  remaining = list(outer_iterator)
  assert remaining == [1, 2, 3, 4]


def test_normalise_sequence_handles_parallel_iteration() -> None:
  """Multiple iterators should be able to advance in lockstep."""

  generator = (value for value in range(4))
  snapshot: Sequence[object] | None = _normalise_sequence(generator)
  assert snapshot is not None
  typed_snapshot = cast(Sequence[object], snapshot)

  paired = list(zip(typed_snapshot, typed_snapshot, strict=False))
  assert paired == [(0, 0), (1, 1), (2, 2), (3, 3)]


def test_normalise_sequence_preserves_bounded_snapshot_identity() -> None:
  """Bounded snapshots should be returned unchanged without consuming items."""

  consumed = 0

  def _source() -> Iterator[int]:
    nonlocal consumed
    for index in range(_SEQUENCE_SCAN_LIMIT * 2):
      consumed += 1
      yield index

  snapshot: Sequence[int] | None = _normalise_sequence(_source())
  assert snapshot is not None
  typed_snapshot = cast(Sequence[int], snapshot)
  assert consumed == 0

  reused: Sequence[int] | None = _normalise_sequence(typed_snapshot)
  assert reused is typed_snapshot
  assert consumed == 0

  first_pass = list(typed_snapshot)
  assert first_pass == list(range(_SEQUENCE_SCAN_LIMIT))
  assert consumed == _SEQUENCE_SCAN_LIMIT

  second_pass = list(typed_snapshot)
  assert second_pass == first_pass
  assert consumed == _SEQUENCE_SCAN_LIMIT


def test_format_structured_message_handles_recursive_mapping() -> None:
  """Structured message extraction should tolerate self-referential payloads."""

  payload: dict[str, object] = {"detail": "Telemetry offline"}
  payload["self"] = payload

  extracted = _format_structured_message(payload)

  assert extracted == "Telemetry offline"


def test_get_feeding_compliance_translations_falls_back_to_english() -> None:
  """Unknown languages should fall back to the English templates."""

  translations = get_feeding_compliance_translations("fr")

  assert translations["missed_meals_header"] == "Missed meals:"


def test_build_notification_includes_translated_headers() -> None:
  """Notification templates should include language-specific headers."""

  compliance = {
    "status": "completed",
    "compliance_score": 80,
    "days_analyzed": 3,
    "compliance_issues": [
      {"date": "2024-05-01", "issues": ["Missed breakfast"], "severity": "high"}
    ],
    "missed_meals": [{"date": "2024-05-02", "actual": 1, "expected": 2}],
    "recommendations": ["Schedule a vet visit"],
  }

  title_en, message_en = build_feeding_compliance_notification(
    "en", display_name="Buddy", compliance=compliance
  )
  assert message_en is not None
  assert "Missed meals:" in message_en
  assert "Next steps:" in message_en
  assert "Buddy" in title_en

  title_de, message_de = build_feeding_compliance_notification(
    "de", display_name="Buddy", compliance=compliance
  )
  assert message_de is not None
  assert "Verpasste Mahlzeiten:" in message_de
  assert "Nächste Schritte:" in message_de
  assert "Buddy" in title_de


def test_build_notification_handles_no_data() -> None:
  """No-data results should return the fallback message."""

  compliance = {
    "status": "no_data",
    "message": "No telemetry available",
  }

  title, message = build_feeding_compliance_notification(
    "en", display_name="Buddy", compliance=compliance
  )
  assert "Feeding telemetry missing" in title
  assert message is not None
  assert "No telemetry available" in message


def test_build_notification_extracts_text_from_mapping_message() -> None:
  """Structured mapping payloads should surface readable text when available."""

  compliance = {
    "status": "no_data",
    "message": {"message": "Telemetry offline"},
  }

  title, message = build_feeding_compliance_notification(
    "en", display_name="Buddy", compliance=compliance
  )

  assert "Feeding telemetry missing" in title
  assert message == "Telemetry offline"


def test_build_notification_falls_back_for_unhelpful_mapping() -> None:
  """Mappings without descriptive text should use the default message."""

  compliance = {
    "status": "no_data",
    "message": {"unexpected": "mapping"},
  }

  title, message = build_feeding_compliance_notification(
    "en", display_name="Buddy", compliance=compliance
  )

  assert "Feeding telemetry missing" in title
  assert message == "Feeding telemetry is unavailable."


def test_build_notification_extracts_singleton_mapping_text() -> None:
  """Singleton mappings with unknown keys should still surface descriptive text."""

  compliance = {
    "status": "no_data",
    "message": {"custom": "Telemetry offline now"},
  }

  _, message = build_feeding_compliance_notification(
    "en", display_name="Buddy", compliance=compliance
  )

  assert message == "Telemetry offline now"


def test_build_notification_handles_case_variant_keys() -> None:
  """Preferred keys should match regardless of case."""

  compliance = {
    "status": "no_data",
    "message": {"Message": "Telemetry offline"},
  }

  _, message = build_feeding_compliance_notification(
    "en", display_name="Buddy", compliance=compliance
  )

  assert message == "Telemetry offline"


def test_iter_text_candidates_skips_none_values() -> None:
  """Iterators should not yield ``None`` even when mappings contain null entries."""

  payload = {"primary": None, "secondary": "ok"}

  candidates = list(_iter_text_candidates(payload))

  assert "ok" in candidates
  assert all(candidate is not None for candidate in candidates)


def test_bounded_sequence_snapshot_supports_slices() -> None:
  """Bounded snapshots should support slicing semantics."""

  generator = (value for value in range(_SEQUENCE_SCAN_LIMIT + 3))
  snapshot: Sequence[int] | None = _normalise_sequence(generator)
  assert snapshot is not None

  sliced = snapshot[1:4]
  assert list(sliced) == [1, 2, 3]


def test_build_notification_falls_back_for_collection_without_text() -> None:
  """Collections lacking descriptive text should use the fallback message."""

  compliance = {
    "status": "no_data",
    "message": {"unexpected", "values"},
  }

  title, message = build_feeding_compliance_notification(
    "en", display_name="Buddy", compliance=compliance
  )

  assert "Feeding telemetry missing" in title
  assert message == "Feeding telemetry is unavailable."


def test_build_notification_extracts_generator_message_text() -> None:
  """Generator-based messages should surface their textual content."""

  def _message_generator() -> Iterable[str]:
    yield "Telemetry offline"

  compliance = {
    "status": "no_data",
    "message": _message_generator(),
  }

  title, message = build_feeding_compliance_notification(
    "en", display_name="Buddy", compliance=compliance
  )

  assert "Feeding telemetry missing" in title
  assert message == "Telemetry offline"


def test_build_notification_extracts_sequence_message_text() -> None:
  """Sequence-based messages should expose joined text content."""

  compliance = {
    "status": "no_data",
    "message": ("Telemetry offline", "Check scheduler"),
  }

  title, message = build_feeding_compliance_notification(
    "en", display_name="Buddy", compliance=compliance
  )

  assert "Feeding telemetry missing" in title
  assert message == "Telemetry offline; Check scheduler"


def test_format_structured_message_limits_generator_consumption() -> None:
  """Structured message parsing should only consume the required generator entries."""

  consumed = 0

  def _factory(index: int) -> dict[str, str]:
    nonlocal consumed
    consumed += 1
    return {"description": f"Issue {index}"}

  message = _format_structured_message(
    _limited_generator(_SEQUENCE_SCAN_LIMIT, _factory)
  )

  assert message == "Issue 0; Issue 1; Issue 2"
  assert consumed <= _SEQUENCE_SCAN_LIMIT


def test_build_notification_handles_recursive_mapping() -> None:
  """Self-referential mappings should fall back to the default message."""

  message_payload: dict[str, object] = {}
  message_payload["self"] = message_payload

  compliance = {
    "status": "no_data",
    "message": message_payload,
  }

  _, message = build_feeding_compliance_notification(
    "en", display_name="Buddy", compliance=compliance
  )

  assert message == "Feeding telemetry is unavailable."


def test_build_notification_handles_recursive_sequence() -> None:
  """Self-referential sequences should fall back to the default message."""

  loop: list[object] = []
  loop.append(loop)

  compliance = {
    "status": "no_data",
    "message": loop,
  }

  _, message = build_feeding_compliance_notification(
    "en", display_name="Buddy", compliance=compliance
  )

  assert message == "Feeding telemetry is unavailable."


def test_build_notification_decodes_bytes_message() -> None:
  """Byte payloads should surface readable text for no-data results."""

  compliance = {
    "status": "no_data",
    "message": b"unexpected",
  }

  title, message = build_feeding_compliance_notification(
    "en", display_name="Buddy", compliance=compliance
  )

  assert "Feeding telemetry missing" in title
  assert message == "unexpected"


def test_build_notification_decodes_bytearray_message() -> None:
  """Bytearray payloads should be decoded to UTF-8 text."""

  compliance = {
    "status": "no_data",
    "message": bytearray(b"unexpected"),
  }

  title, message = build_feeding_compliance_notification(
    "en", display_name="Buddy", compliance=compliance
  )

  assert "Feeding telemetry missing" in title
  assert message == "unexpected"


def test_build_notification_decodes_memoryview_message() -> None:
  """Memoryview payloads should surface decoded text."""

  compliance = {
    "status": "no_data",
    "message": memoryview(b"unexpected"),
  }

  title, message = build_feeding_compliance_notification(
    "en", display_name="Buddy", compliance=compliance
  )

  assert "Feeding telemetry missing" in title
  assert message == "unexpected"


def test_build_notification_accepts_user_string_message() -> None:
  """String wrappers should be treated as readable text."""

  compliance = {
    "status": "no_data",
    "message": UserString("Telemetry offline"),
  }

  title, message = build_feeding_compliance_notification(
    "en", display_name="Buddy", compliance=compliance
  )

  assert "Feeding telemetry missing" in title
  assert message == "Telemetry offline"


def test_build_notification_accepts_pathlike_message() -> None:
  """Path-like objects should surface their filesystem representation."""

  compliance = {
    "status": "no_data",
    "message": Path("/tmp/telemetry.log"),
  }

  title, message = build_feeding_compliance_notification(
    "en", display_name="Buddy", compliance=compliance
  )

  assert "Feeding telemetry missing" in title
  assert message == "/tmp/telemetry.log"


def test_build_notification_salvages_nested_mapping_text() -> None:
  """Nested mappings without preferred keys should still surface text."""

  compliance = {
    "status": "no_data",
    "message": {"meta": {"info": "Telemetry offline"}, "code": 503},
  }

  title, message = build_feeding_compliance_notification(
    "en", display_name="Buddy", compliance=compliance
  )

  assert "Feeding telemetry missing" in title
  assert message == "Telemetry offline"


def test_build_notification_salvages_sequence_mapping_text() -> None:
  """Sequences containing mappings should provide readable text."""

  compliance = {
    "status": "no_data",
    "message": [
      {"details": {"text": "Telemetry offline"}},
      {"code": 503},
    ],
  }

  _, message = build_feeding_compliance_notification(
    "en", display_name="Buddy", compliance=compliance
  )

  assert message == "Telemetry offline"


def test_build_summary_decodes_byte_recommendations() -> None:
  """Recommendations supplied as bytes should be decoded to text."""

  compliance = {
    "status": "completed",
    "compliance_score": 90,
    "days_analyzed": 2,
    "recommendations": [b"Check feeder"],
    "missed_meals": [],
    "compliance_issues": [],
  }

  summary = build_feeding_compliance_summary(
    "en", display_name="Buddy", compliance=compliance
  )

  assert summary["recommendations"] == ["Check feeder"]
  message = summary["message"]
  assert message is not None
  assert "Check feeder" in message


def test_build_summary_decodes_scalar_byte_recommendations() -> None:
  """Singleton byte recommendations should be decoded to readable text."""

  compliance = {
    "status": "completed",
    "compliance_score": 88,
    "days_analyzed": 3,
    "recommendations": b"Offer puzzle feeder",
    "missed_meals": [],
    "compliance_issues": [],
  }

  summary = build_feeding_compliance_summary(
    "en", display_name="Buddy", compliance=compliance
  )

  assert summary["recommendations"] == ["Offer puzzle feeder"]
  message = summary["message"]
  assert message is not None
  assert "Offer puzzle feeder" in message


def test_build_summary_decodes_memoryview_recommendations() -> None:
  """Memoryview recommendations should be treated as readable text."""

  compliance = {
    "status": "completed",
    "compliance_score": 90,
    "days_analyzed": 2,
    "recommendations": memoryview(b"Check dispenser"),
    "missed_meals": [],
    "compliance_issues": [],
  }

  summary = build_feeding_compliance_summary(
    "en", display_name="Buddy", compliance=compliance
  )

  assert summary["recommendations"] == ["Check dispenser"]
  message = summary["message"]
  assert message is not None
  assert "Check dispenser" in message


def test_build_summary_handles_generator_recommendations() -> None:
  """Generator-backed recommendations should be materialised correctly."""

  compliance = {
    "status": "completed",
    "compliance_score": 92,
    "days_analyzed": 4,
    "recommendations": (value for value in ["Add lunchtime portion"]),
    "missed_meals": [],
    "compliance_issues": [],
  }

  summary = build_feeding_compliance_summary(
    "en", display_name="Buddy", compliance=compliance
  )

  assert summary["recommendations"] == ["Add lunchtime portion"]
  message = summary["message"]
  assert message is not None
  assert "Add lunchtime portion" in message


def test_build_summary_extracts_mapping_recommendations() -> None:
  """Mapping recommendations should surface descriptive text."""

  compliance = {
    "status": "completed",
    "compliance_score": 91,
    "days_analyzed": 3,
    "recommendations": {"text": "Refill the kibble hopper"},
    "missed_meals": [],
    "compliance_issues": [],
  }

  summary = build_feeding_compliance_summary(
    "en", display_name="Buddy", compliance=compliance
  )

  assert summary["recommendations"] == ["Refill the kibble hopper"]
  message = summary["message"]
  assert message is not None
  assert "Refill the kibble hopper" in message


def test_build_summary_extracts_nested_mapping_recommendations() -> None:
  """Nested mapping recommendations should decode nested entries."""

  compliance = {
    "status": "completed",
    "compliance_score": 87,
    "days_analyzed": 4,
    "recommendations": {"details": [memoryview(b"Warm meals during cold snaps"), None]},
    "missed_meals": [],
    "compliance_issues": [],
  }

  summary = build_feeding_compliance_summary(
    "en", display_name="Buddy", compliance=compliance
  )

  assert summary["recommendations"] == ["Warm meals during cold snaps"]
  message = summary["message"]
  assert message is not None
  assert "Warm meals during cold snaps" in message


def test_build_summary_decodes_byte_issue_details() -> None:
  """Issue metadata provided as bytes should surface readable text."""

  compliance = {
    "status": "completed",
    "compliance_score": 65,
    "days_analyzed": 5,
    "missed_meals": [],
    "recommendations": [],
    "compliance_issues": [
      {
        "date": "2024-05-02",
        "description": b"Sensor unreachable",
      }
    ],
  }

  summary = build_feeding_compliance_summary(
    "en", display_name="Buddy", compliance=compliance
  )

  assert summary["issues"][0].endswith("Sensor unreachable")
  message = summary["message"]
  assert message is not None
  assert "Sensor unreachable" in message


def test_build_summary_decodes_memoryview_issue_details() -> None:
  """Memoryview issue details should surface readable text."""

  compliance = {
    "status": "completed",
    "compliance_score": 65,
    "days_analyzed": 5,
    "missed_meals": [],
    "recommendations": [],
    "compliance_issues": [
      {
        "date": "2024-05-02",
        "description": memoryview(b"Scale offline"),
      }
    ],
  }

  summary = build_feeding_compliance_summary(
    "en", display_name="Buddy", compliance=compliance
  )

  assert summary["issues"][0].endswith("Scale offline")
  message = summary["message"]
  assert message is not None
  assert "Scale offline" in message


def test_build_summary_accepts_mapping_issue() -> None:
  """Single mapping issue entries should still be captured."""

  compliance = {
    "status": "completed",
    "compliance_score": 75,
    "days_analyzed": 2,
    "compliance_issues": {
      "date": "2024-03-12",
      "description": "Late breakfast",
    },
    "missed_meals": [],
    "recommendations": [],
  }

  summary = build_feeding_compliance_summary(
    "en", display_name="Buddy", compliance=compliance
  )

  assert summary["issues"] == ["2024-03-12: Late breakfast"]
  message = summary["message"]
  assert message is not None
  assert "Late breakfast" in message


def test_build_summary_handles_nested_issue_mapping() -> None:
  """Issue entries containing nested mappings should prefer descriptive text."""

  compliance = {
    "status": "completed",
    "compliance_score": 70,
    "days_analyzed": 3,
    "compliance_issues": [
      {
        "date": "2024-05-05",
        "issues": [{"text": "Skipped evening meal"}],
      }
    ],
    "missed_meals": [],
    "recommendations": [],
  }

  summary = build_feeding_compliance_summary(
    "en", display_name="Buddy", compliance=compliance
  )

  assert summary["issues"] == ["2024-05-05: Skipped evening meal"]
  message = summary["message"]
  assert message is not None
  assert "Skipped evening meal" in message


def test_build_summary_accepts_mapping_missed_meal() -> None:
  """Single missed meal mappings should be materialised correctly."""

  compliance = {
    "status": "completed",
    "compliance_score": 80,
    "days_analyzed": 2,
    "missed_meals": {"date": "2024-04-11", "actual": 0, "expected": 2},
    "compliance_issues": [],
    "recommendations": [],
  }

  summary = build_feeding_compliance_summary(
    "en", display_name="Buddy", compliance=compliance
  )

  assert summary["missed_meals"] == ["2024-04-11: 0/2 meals"]
  message = summary["message"]
  assert message is not None
  assert "0/2 meals" in message


def test_build_summary_returns_localised_sections() -> None:
  """Summary builder should expose localised sections for repairs."""

  compliance = {
    "status": "completed",
    "compliance_score": 75,
    "days_analyzed": 4,
    "compliance_issues": [
      {"date": "2024-05-02", "issues": ["Skipped dinner"], "severity": "high"}
    ],
    "missed_meals": [
      {"date": "2024-05-01", "actual": 1, "expected": 2},
      {"date": "2024-05-03", "actual": 0, "expected": 2},
    ],
    "recommendations": ["Schedule a vet visit"],
  }

  summary = build_feeding_compliance_summary(
    "en", display_name="Buddy", compliance=compliance
  )

  assert summary["title"].startswith("🍽️ Feeding compliance alert")
  score_line = summary["score_line"]
  assert score_line is not None
  assert score_line.startswith("Score: 75.0%")
  assert summary["missed_meals"][0].startswith("2024-05-01")
  assert summary["issues"][0].startswith("2024-05-02")
  assert summary["recommendations"] == ["Schedule a vet visit"]

  summary_de = build_feeding_compliance_summary(
    "de", display_name="Buddy", compliance=compliance
  )

  assert summary_de["title"].startswith("🍽️ Fütterungs-Compliance-Warnung")
  score_line_de = summary_de["score_line"]
  assert score_line_de is not None
  assert score_line_de.startswith("Punktzahl")
  assert summary_de["missed_meals"][0].endswith("Mahlzeiten")


def test_build_summary_handles_malformed_payload() -> None:
  """Summary builder should sanitise malformed payload data."""

  compliance = {
    "status": "completed",
    "compliance_score": "82.45",
    "days_analyzed": "2",
    "compliance_issues": [
      {"date": " ", "issues": ["  Missed lunch  "], "severity": "HIGH"},
      {"date": "2024-05-03", "severity": "  medium  "},
      "invalid",
    ],
    "missed_meals": [
      {"date": None, "actual": " 2 ", "expected": " 3 "},
      {"date": "2024-05-04", "actual": None, "expected": None},
      "unexpected",
    ],
    "recommendations": ["  Check portions  ", "", None, 42],
  }

  summary = build_feeding_compliance_summary(
    "en", display_name="Buddy", compliance=compliance
  )

  assert summary["score_line"] == "Score: 82.5% over 2 days."
  assert summary["missed_meals"] == [
    "unknown: 2/3 meals",
    "2024-05-04: ?/? meals",
  ]
  assert summary["issues"] == [
    "unknown: Missed lunch",
    "2024-05-03: medium",
  ]
  assert summary["recommendations"] == ["Check portions", "42"]


def test_collect_missed_meals_limits_generator_consumption() -> None:
  """Missed meal aggregation should stop iterating once the limit is reached."""

  translations = get_feeding_compliance_translations("en")
  consumed = 0

  def _factory(index: int) -> dict[str, object]:
    nonlocal consumed
    consumed += 1
    return {"date": f"2024-05-0{index + 1}", "actual": index, "expected": 2}

  summary = _collect_missed_meals(
    translations, _limited_generator(_SEQUENCE_SCAN_LIMIT, _factory)
  )

  assert len(summary) == _MAX_MISSED_MEALS
  assert consumed == _MAX_MISSED_MEALS


def test_collect_issue_summaries_limits_generator_consumption() -> None:
  """Issue aggregation should consume at most the configured number of entries."""

  translations = get_feeding_compliance_translations("en")
  consumed = 0

  def _factory(index: int) -> dict[str, object]:
    nonlocal consumed
    consumed += 1
    return {
      "date": f"2024-05-0{index + 1}",
      "issues": [{"description": f"Problem {index}"}],
    }

  summary = _collect_issue_summaries(
    translations, _limited_generator(_SEQUENCE_SCAN_LIMIT, _factory)
  )

  assert len(summary) == _MAX_ISSUES
  assert consumed == _MAX_ISSUES


def test_collect_recommendations_limits_generator_consumption() -> None:
  """Recommendation aggregation should not exhaust unbounded iterables."""

  translations = get_feeding_compliance_translations("en")
  consumed = 0

  def _factory(index: int) -> dict[str, str]:
    nonlocal consumed
    consumed += 1
    return {"text": f"Recommendation {index}"}

  summary = _collect_recommendations(
    translations, _limited_generator(_SEQUENCE_SCAN_LIMIT, _factory)
  )

  assert len(summary) == _MAX_RECOMMENDATIONS
  assert consumed == _MAX_RECOMMENDATIONS
