"""Localised templates for feeding compliance notifications."""

from __future__ import annotations

from collections import UserString
from collections.abc import Collection, Iterable, Iterator, Mapping, Sequence
from itertools import islice
from math import isfinite
from numbers import Real
from os import PathLike, fspath
from typing import TYPE_CHECKING, Any, Final, TypeVar, cast, overload

if TYPE_CHECKING:
  from .types import (
    FeedingComplianceDisplayMapping,
    FeedingComplianceLocalizedSummary,
  )

DEFAULT_LANGUAGE: Final[str] = "en"

_FEEDING_COMPLIANCE_TRANSLATIONS: dict[str, dict[str, str]] = {
  "en": {
    "no_data_title": "🍽️ Feeding telemetry missing for {display_name}",
    "no_data_fallback": "Feeding telemetry is unavailable.",
    "alert_title": "🍽️ Feeding compliance alert for {display_name}",
    "score_line": "Score: {score}% over {days_analyzed} days.",
    "missed_meals_header": "Missed meals:",
    "missed_meal_item": "{date}: {actual}/{expected} meals",
    "issues_header": "Key issues:",
    "issue_item": "{date}: {description}",
    "recommendations_header": "Next steps:",
    "recommendation_item": "{recommendation}",
    "no_recommendations": "No recommendations provided.",
  },
  "de": {
    "no_data_title": "🍽️ Fütterungstelemetrie fehlt für {display_name}",
    "no_data_fallback": "Fütterungstelemetrie ist nicht verfügbar.",
    "alert_title": "🍽️ Fütterungs-Compliance-Warnung für {display_name}",
    "score_line": "Punktzahl: {score}% über {days_analyzed} Tage.",
    "missed_meals_header": "Verpasste Mahlzeiten:",
    "missed_meal_item": "{date}: {actual}/{expected} Mahlzeiten",
    "issues_header": "Wichtige Probleme:",
    "issue_item": "{date}: {description}",
    "recommendations_header": "Nächste Schritte:",
    "recommendation_item": "{recommendation}",
    "no_recommendations": "Keine Empfehlungen verfügbar.",
  },
}


def get_feeding_compliance_translations(language: str | None) -> dict[str, str]:
  """Return translations for the requested language with fallback."""

  if not language:
    return _FEEDING_COMPLIANCE_TRANSLATIONS[DEFAULT_LANGUAGE]

  normalised = language.lower().split("-")[0]
  translations = _FEEDING_COMPLIANCE_TRANSLATIONS.get(normalised)
  if translations is None:
    return _FEEDING_COMPLIANCE_TRANSLATIONS[DEFAULT_LANGUAGE]
  return translations


_MAX_MISSED_MEALS: Final[int] = 3
_MAX_ISSUES: Final[int] = 3
_MAX_RECOMMENDATIONS: Final[int] = 2

_SEQUENCE_SCAN_LIMIT: Final[int] = 16

_PREFERRED_TEXT_KEYS: Final[tuple[str, ...]] = (
  "text",
  "description",
  "summary",
  "message",
  "recommendation",
  "detail",
  "details",
  "value",
  "reason",
  "title",
  "note",
  "notes",
  "info",
  "information",
  "content",
)

_ALLOWED_SINGLE_WORDS: Final[frozenset[str]] = frozenset(
  {
    "offline",
    "error",
    "warning",
    "critical",
    "stale",
    "missing",
    "unknown",
    "degraded",
  },
)


def _is_structured_message_payload(value: object) -> bool:
  """Return ``True`` when the message represents structured metadata."""

  if isinstance(value, str | UserString):
    return False

  if isinstance(value, bytes | bytearray | memoryview):
    return False

  if isinstance(value, PathLike):
    return False

  if isinstance(value, Collection):
    return True

  return isinstance(value, Iterable)


_T = TypeVar("_T")


def _normalise_sequence(
  value: object,
  *,
  limit: int | None = None,
) -> Sequence[_T] | None:
  """Return a bounded, re-iterable snapshot for sequence-like payloads."""

  if isinstance(value, str | bytes | bytearray | memoryview):
    return None

  max_allowed = (
    _SEQUENCE_SCAN_LIMIT
    if limit is None
    else min(
      limit,
      _SEQUENCE_SCAN_LIMIT,
    )
  )
  max_items = max(max_allowed, 0)
  if max_items == 0:
    return cast(Sequence[_T], ())

  if isinstance(value, Mapping):
    return cast(Sequence[_T], (value,))

  if isinstance(value, _BoundedSequenceSnapshot):
    return cast(Sequence[_T], value)

  if isinstance(value, Sequence):
    if not value:
      return cast(Sequence[_T], ())
    if len(value) <= max_items:
      return cast(Sequence[_T], tuple(value))
    return cast(Sequence[_T], tuple(islice(value, max_items)))

  if isinstance(value, Iterable):
    return _BoundedSequenceSnapshot(cast(Iterable[_T], value), max_items)

  return None


def _as_float(value: Any) -> float | None:
  """Convert a value to a finite float when possible."""

  if isinstance(value, bool):
    return float(value)
  if isinstance(value, Real):
    result = float(value)
    return result if isfinite(result) else None
  if isinstance(value, str):
    text = value.strip()
    if not text:
      return None
    try:
      result = float(text)
    except ValueError:
      return None
    return result if isfinite(result) else None
  return None


def _normalise_count(value: Any) -> str:
  """Return a human-friendly representation of a meal count."""

  number = _as_float(value)
  if number is None:
    return "?"
  if float(number).is_integer():
    return str(int(number))
  return f"{number:.1f}"


def _normalise_date(value: Any) -> str:
  """Return a readable date string or a fallback."""

  if isinstance(value, str):
    text = value.strip()
    if text:
      return text
  return "unknown"


def _normalise_text(value: Any) -> str | None:
  """Normalise arbitrary values into cleaned text."""

  if isinstance(value, str):
    text = value.strip()
  elif isinstance(value, PathLike):
    fspath_value = fspath(value)
    if isinstance(fspath_value, bytes):
      text = fspath_value.decode("utf-8", "ignore").strip()
    else:
      text = fspath_value.strip()
  elif isinstance(value, bytes | bytearray):
    text = value.decode("utf-8", "ignore").strip()
  elif isinstance(value, memoryview):
    text = value.tobytes().decode("utf-8", "ignore").strip()
  elif value is None:
    return None
  else:
    text = str(value).strip()
  return text or None


def _iter_text_candidates(
  value: Any,
  *,
  _visited: set[int] | None = None,
) -> Iterable[str]:
  """Yield cleaned text candidates from arbitrary values."""

  if _visited is None:
    _visited = set()

  obj_id = id(value)
  if obj_id in _visited:
    return

  _visited.add(obj_id)
  try:
    if isinstance(value, Mapping):
      yield from _iter_mapping_text_candidates(value, _visited=_visited)
      return

    if isinstance(value, bytes | bytearray):
      candidate = value.decode("utf-8", "ignore").strip()
      if candidate:
        yield candidate
      return

    if isinstance(value, memoryview):
      candidate = value.tobytes().decode("utf-8", "ignore").strip()
      if candidate:
        yield candidate
      return

    sequence = cast(Sequence[object] | None, _normalise_sequence(value))
    if sequence is not None:
      for item in sequence:
        if item is value:
          continue
        yield from _iter_text_candidates(item, _visited=_visited)
      return

    normalized_text = _normalise_text(value)
    if normalized_text:
      yield normalized_text
  finally:
    _visited.remove(obj_id)


def _iter_mapping_text_candidates(
  mapping: Mapping[str, object],
  *,
  _visited: set[int],
) -> Iterable[str]:
  """Yield textual candidates from a mapping, preferring descriptive keys."""

  string_keys: dict[str, str] = {}
  for key in mapping:
    if isinstance(key, str):
      string_keys[key.casefold()] = key

  seen: set[str] = set()
  for preferred_key in _PREFERRED_TEXT_KEYS:
    casefold_key = preferred_key.casefold()
    actual_key = string_keys.get(casefold_key)
    if actual_key is None:
      continue
    seen.add(actual_key)
    yield from _iter_text_candidates(mapping[actual_key], _visited=_visited)

  for key, value in mapping.items():
    if isinstance(key, str) and key in seen:
      continue
    if value is mapping:
      continue
    yield from _iter_text_candidates(value, _visited=_visited)


def _first_text_candidate(value: Any) -> str | None:
  """Return the first cleaned text candidate from an arbitrary value."""

  for text in _iter_text_candidates(value):
    if text:
      return text
  return None


def _clean_structured_text_candidate(text: str | None) -> str | None:
  """Filter out non-descriptive structured text candidates."""

  if text is None:
    return None

  stripped = text.strip()
  if not stripped:
    return None

  if stripped.startswith("<") and stripped.endswith(">") and " object at " in stripped:
    return None

  if stripped.startswith("{") and stripped.endswith("}") and ":" in stripped:
    return None

  if stripped.startswith("[") and stripped.endswith("]") and "," in stripped:
    return None

  if stripped.startswith("(") and stripped.endswith(")") and "," in stripped:
    return None

  if " " not in stripped and stripped.casefold() not in _ALLOWED_SINGLE_WORDS:
    return None

  return stripped


def _format_structured_message(value: Any) -> str | None:
  """Extract readable text from structured compliance message payloads."""

  texts: list[str] = []
  seen: set[str] = set()
  for candidate in _iter_text_candidates(value):
    cleaned = _clean_structured_text_candidate(candidate)
    if not cleaned:
      continue
    key = cleaned.casefold()
    if key in seen:
      continue
    texts.append(cleaned)
    seen.add(key)
    if len(texts) >= 3:
      break

  if not texts:
    return None

  if len(texts) == 1:
    return texts[0]

  return "; ".join(texts)


def _collect_missed_meals(
  translations: Mapping[str, str],
  raw_entries: object,
) -> list[str]:
  """Build the missed meals section with sanitised values."""

  entries = cast(
    Sequence[Mapping[str, object]] | None,
    _normalise_sequence(raw_entries),
  )
  if entries is None:
    return []

  summary: list[str] = []
  for entry in entries:
    if not isinstance(entry, Mapping):
      continue

    summary.append(
      translations["missed_meal_item"].format(
        date=_normalise_date(entry.get("date")),
        actual=_normalise_count(entry.get("actual")),
        expected=_normalise_count(entry.get("expected")),
      ),
    )
    if len(summary) >= _MAX_MISSED_MEALS:
      break
  return summary


def _describe_issue(issue: Mapping[str, object]) -> str:
  """Return a readable description for an issue entry."""

  issues = cast(
    Sequence[object] | None,
    _normalise_sequence(issue.get("issues")),
  )
  if issues:
    for candidate in issues:
      text = _first_text_candidate(candidate)
      if text:
        return text

  for key in ("description", "summary", "severity"):
    text = _first_text_candidate(issue.get(key))
    if text:
      return text

  fallback = issue.get("issues")
  text = _first_text_candidate(fallback)
  if text:
    return text
  return "issue"


def _collect_issue_summaries(
  translations: Mapping[str, str],
  raw_entries: object,
) -> list[str]:
  """Return normalised issue summary lines."""

  entries = cast(
    Sequence[Mapping[str, object]] | None,
    _normalise_sequence(raw_entries),
  )
  if entries is None:
    return []

  summary: list[str] = []
  for entry in entries:
    if not isinstance(entry, Mapping):
      continue

    summary.append(
      translations["issue_item"].format(
        date=_normalise_date(entry.get("date")),
        description=_describe_issue(entry),
      ),
    )
    if len(summary) >= _MAX_ISSUES:
      break
  return summary


def _collect_recommendations(
  translations: Mapping[str, str],
  raw_entries: object,
) -> list[str]:
  """Return cleaned recommendation text entries."""

  entries = cast(Sequence[object] | None, _normalise_sequence(raw_entries))
  if entries is None:
    if raw_entries is None:
      return []
    iterable: Iterable[object] = (raw_entries,)
  else:
    iterable = entries

  summary: list[str] = []
  for entry in iterable:
    text = _first_text_candidate(entry)
    if not text:
      continue
    summary.append(
      translations["recommendation_item"].format(recommendation=text),
    )
    if len(summary) >= _MAX_RECOMMENDATIONS:
      break
  return summary


def _build_localised_sections(
  translations: Mapping[str, str],
  compliance: FeedingComplianceDisplayMapping,
) -> tuple[list[str], list[str], list[str]]:
  """Return localised summary sections for missed meals, issues, and recommendations."""

  missed_summary = _collect_missed_meals(
    translations,
    compliance.get("missed_meals"),
  )
  issue_summary = _collect_issue_summaries(
    translations,
    compliance.get("compliance_issues"),
  )
  recommendation_summary = _collect_recommendations(
    translations,
    compliance.get("recommendations"),
  )

  if not recommendation_summary and (issue_summary or missed_summary):
    recommendation_summary.append(translations["no_recommendations"])

  return missed_summary, issue_summary, recommendation_summary


def build_feeding_compliance_summary(
  language: str | None,
  *,
  display_name: str,
  compliance: FeedingComplianceDisplayMapping,
) -> FeedingComplianceLocalizedSummary:
  """Return a localised summary for a feeding compliance result."""

  translations = get_feeding_compliance_translations(language)
  status = compliance.get("status")

  if status != "completed":
    raw_message = compliance.get("message")
    if _is_structured_message_payload(raw_message):
      message = _format_structured_message(raw_message)
    else:
      message = _normalise_text(raw_message)
    if not message:
      message = translations["no_data_fallback"]

    title = translations["no_data_title"].format(display_name=display_name)
    return {
      "title": title,
      "message": message,
      "score_line": None,
      "missed_meals": [],
      "issues": [],
      "recommendations": [],
    }

  score = _as_float(compliance.get("compliance_score")) or 0.0
  days_value = _as_float(compliance.get("days_analyzed"))
  days_analyzed = int(days_value) if days_value is not None else 0
  missed_summary, issue_summary, recommendation_summary = _build_localised_sections(
    translations,
    compliance,
  )

  score_line = translations["score_line"].format(
    score=f"{score:.1f}",
    days_analyzed=days_analyzed,
  )
  lines: list[str] = [score_line]

  if missed_summary:
    lines.append(translations["missed_meals_header"])
    lines.extend(f"- {entry}" for entry in missed_summary)

  if issue_summary:
    lines.append(translations["issues_header"])
    lines.extend(f"- {entry}" for entry in issue_summary)

  if recommendation_summary:
    lines.append(translations["recommendations_header"])
    lines.extend(f"- {entry}" for entry in recommendation_summary)

  title = translations["alert_title"].format(display_name=display_name)
  message = "\n".join(lines) if lines else None
  return {
    "title": title,
    "message": message,
    "score_line": score_line,
    "missed_meals": missed_summary,
    "issues": issue_summary,
    "recommendations": recommendation_summary,
  }


def build_feeding_compliance_notification(
  language: str | None,
  *,
  display_name: str,
  compliance: FeedingComplianceDisplayMapping,
) -> tuple[str, str | None]:
  """Return localised title and body for a feeding compliance result."""

  summary = build_feeding_compliance_summary(
    language,
    display_name=display_name,
    compliance=compliance,
  )
  return summary["title"], summary["message"]


T = TypeVar("T")


class _BoundedSequenceSnapshot(Sequence[T]):
  """Cache at most ``limit`` items from an iterable for safe re-iteration."""

  __slots__ = ("_cache", "_iterator", "_limit")

  def __init__(self, source: Iterable[T], limit: int) -> None:
    self._iterator: Iterator[T] | None = iter(source)
    self._cache: list[T] = []
    self._limit = limit

  def __iter__(self) -> Iterator[T]:
    index = 0
    while True:
      self._consume_to(index + 1)
      if index >= len(self._cache):
        break
      yield self._cache[index]
      index += 1

  def __len__(self) -> int:  # pragma: no cover - rarely exercised
    self._consume_to(self._limit)
    return len(self._cache)

  @overload
  def __getitem__(self, index: int, /) -> T:  # pragma: no cover - defensive
    """Return the cached item at ``index``."""

  @overload
  def __getitem__(
    self,
    index: slice,
    /,
  ) -> Sequence[T]:  # pragma: no cover - defensive
    """Return a sliced view of the cached items."""

  def __getitem__(self, index: int | slice, /) -> T | Sequence[T]:
    """Return cached values, supporting both index and slice access."""

    if isinstance(index, slice):
      self._consume_to(self._limit)
      return self._cache[index]

    if index < 0:
      self._consume_to(self._limit)
    else:
      self._consume_to(index + 1)
    return self._cache[index]

  def _consume_to(self, count: int) -> None:
    if self._iterator is None:
      return

    target = min(self._limit, max(count, 0))
    remaining = target - len(self._cache)
    if remaining <= 0:
      if target >= self._limit:
        self._iterator = None
      return

    iterator = self._iterator
    assert iterator is not None

    start_len = len(self._cache)
    for item in islice(iterator, remaining):
      self._cache.append(item)

    if (
      len(self._cache) >= self._limit
      or target >= self._limit
      or len(self._cache) == start_len
    ):
      self._iterator = None
