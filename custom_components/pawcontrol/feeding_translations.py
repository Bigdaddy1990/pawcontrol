"""Localised templates for feeding compliance notifications."""

from collections import UserString
from collections.abc import Collection, Iterable, Iterator, Mapping, Sequence
from itertools import islice
import json
from math import isfinite
from numbers import Real
from os import PathLike, fspath
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, TypeVar, cast, overload

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant  # noqa: E111

    from .types import (  # noqa: E111
        FeedingComplianceDisplayMapping,
        FeedingComplianceLocalizedSummary,
    )

from .translation_helpers import (
    async_get_component_translation_lookup,
    resolve_component_translation,
)

FEEDING_COMPLIANCE_TRANSLATION_KEYS: Final[dict[str, str]] = {
    "no_data_title": "feeding_compliance_no_data_title",
    "no_data_fallback": "feeding_compliance_no_data_fallback",
    "alert_title": "feeding_compliance_alert_title",
    "score_line": "feeding_compliance_score_line",
    "missed_meals_header": "feeding_compliance_missed_meals_header",
    "missed_meal_item": "feeding_compliance_missed_meal_item",
    "issues_header": "feeding_compliance_issues_header",
    "issue_item": "feeding_compliance_issue_item",
    "recommendations_header": "feeding_compliance_recommendations_header",
    "recommendation_item": "feeding_compliance_recommendation_item",
    "no_recommendations": "feeding_compliance_no_recommendations",
}


def _resolve_feeding_compliance_translations(
    translations: Mapping[str, str],
    fallback: Mapping[str, str],
) -> dict[str, str]:
    """Build a localized translation mapping for feeding compliance strings."""  # noqa: E111

    return {  # noqa: E111
        key: resolve_component_translation(
            translations,
            fallback,
            translation_key,
            default=key,
        )
        for key, translation_key in FEEDING_COMPLIANCE_TRANSLATION_KEYS.items()
    }


async def async_get_feeding_compliance_translations(
    hass: HomeAssistant,
    language: str | None,
) -> dict[str, str]:
    """Return translations for the requested language with fallback."""  # noqa: E111

    translations, fallback = await async_get_component_translation_lookup(  # noqa: E111
        hass,
        language,
    )
    resolved = _resolve_feeding_compliance_translations(translations, fallback)  # noqa: E111

    if any(resolved[key] == key for key in FEEDING_COMPLIANCE_TRANSLATION_KEYS):  # noqa: E111
        static_translations = get_feeding_compliance_translations(language)
        return {
            key: static_translations.get(key, resolved[key])
            for key in FEEDING_COMPLIANCE_TRANSLATION_KEYS
        }

    return resolved  # noqa: E111


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
    """Return ``True`` when the message represents structured metadata."""  # noqa: E111

    if isinstance(value, str | UserString):  # noqa: E111
        return False

    if isinstance(value, bytes | bytearray | memoryview):  # noqa: E111
        return False

    if isinstance(value, PathLike):  # noqa: E111
        return False

    if isinstance(value, Collection):  # noqa: E111
        return True

    return isinstance(value, Iterable)  # noqa: E111


_T = TypeVar("_T")


def _normalise_sequence(
    value: object,
    *,
    limit: int | None = None,
) -> Sequence[_T] | None:
    """Return a bounded, re-iterable snapshot for sequence-like payloads."""  # noqa: E111

    if isinstance(value, str | bytes | bytearray | memoryview):  # noqa: E111
        return None

    max_allowed = (  # noqa: E111
        _SEQUENCE_SCAN_LIMIT
        if limit is None
        else min(
            limit,
            _SEQUENCE_SCAN_LIMIT,
        )
    )
    max_items = max(max_allowed, 0)  # noqa: E111
    if max_items == 0:  # noqa: E111
        return cast(Sequence[_T], ())

    if isinstance(value, Mapping):  # noqa: E111
        return cast(Sequence[_T], (value,))

    if isinstance(value, _BoundedSequenceSnapshot):  # noqa: E111
        return cast(Sequence[_T], value)

    if isinstance(value, Sequence):  # noqa: E111
        if not value:
            return cast(Sequence[_T], ())  # noqa: E111
        if len(value) <= max_items:
            return cast(Sequence[_T], tuple(value))  # noqa: E111
        return cast(Sequence[_T], tuple(islice(value, max_items)))

    if isinstance(value, Iterable):  # noqa: E111
        return _BoundedSequenceSnapshot(cast(Iterable[_T], value), max_items)

    return None  # noqa: E111


def _as_float(value: Any) -> float | None:
    """Convert a value to a finite float when possible."""  # noqa: E111

    if isinstance(value, bool):  # noqa: E111
        return float(value)
    if isinstance(value, Real):  # noqa: E111
        result = float(value)
        return result if isfinite(result) else None
    if isinstance(value, str):  # noqa: E111
        text = value.strip()
        if not text:
            return None  # noqa: E111
        try:
            result = float(text)  # noqa: E111
        except ValueError:
            return None  # noqa: E111
        return result if isfinite(result) else None
    return None  # noqa: E111


def _normalise_count(value: Any) -> str:
    """Return a human-friendly representation of a meal count."""  # noqa: E111

    number = _as_float(value)  # noqa: E111
    if number is None:  # noqa: E111
        return "?"
    if float(number).is_integer():  # noqa: E111
        return str(int(number))
    return f"{number:.1f}"  # noqa: E111


def _normalise_date(value: Any) -> str:
    """Return a readable date string or a fallback."""  # noqa: E111

    if isinstance(value, str):  # noqa: E111
        text = value.strip()
        if text:
            return text  # noqa: E111
    return "unknown"  # noqa: E111


def _normalise_text(value: Any) -> str | None:
    """Normalise arbitrary values into cleaned text."""  # noqa: E111

    if isinstance(value, str):  # noqa: E111
        text = value.strip()
    elif isinstance(value, PathLike):  # noqa: E111
        fspath_value = fspath(value)
        if isinstance(fspath_value, bytes):
            text = fspath_value.decode("utf-8", "ignore").strip()  # noqa: E111
        else:
            text = fspath_value.strip()  # noqa: E111
    elif isinstance(value, bytes | bytearray):  # noqa: E111
        text = value.decode("utf-8", "ignore").strip()
    elif isinstance(value, memoryview):  # noqa: E111
        text = value.tobytes().decode("utf-8", "ignore").strip()
    elif value is None:  # noqa: E111
        return None
    else:  # noqa: E111
        text = str(value).strip()
    return text or None  # noqa: E111


def _iter_text_candidates(
    value: Any,
    *,
    _visited: set[int] | None = None,
) -> Iterable[str]:
    """Yield cleaned text candidates from arbitrary values."""  # noqa: E111

    if _visited is None:  # noqa: E111
        _visited = set()

    obj_id = id(value)  # noqa: E111
    if obj_id in _visited:  # noqa: E111
        return

    _visited.add(obj_id)  # noqa: E111
    try:  # noqa: E111
        if isinstance(value, Mapping):
            yield from _iter_mapping_text_candidates(value, _visited=_visited)  # noqa: E111
            return  # noqa: E111

        if isinstance(value, bytes | bytearray):
            candidate = value.decode("utf-8", "ignore").strip()  # noqa: E111
            if candidate:  # noqa: E111
                yield candidate
            return  # noqa: E111

        if isinstance(value, memoryview):
            candidate = value.tobytes().decode("utf-8", "ignore").strip()  # noqa: E111
            if candidate:  # noqa: E111
                yield candidate
            return  # noqa: E111

        sequence = cast(Sequence[object] | None, _normalise_sequence(value))
        if sequence is not None:
            for item in sequence:  # noqa: E111
                if item is value:
                    continue  # noqa: E111
                yield from _iter_text_candidates(item, _visited=_visited)
            return  # noqa: E111

        normalized_text = _normalise_text(value)
        if normalized_text:
            yield normalized_text  # noqa: E111
    finally:  # noqa: E111
        _visited.remove(obj_id)


def _iter_mapping_text_candidates(
    mapping: Mapping[str, object],
    *,
    _visited: set[int],
) -> Iterable[str]:
    """Yield textual candidates from a mapping, preferring descriptive keys."""  # noqa: E111

    string_keys: dict[str, str] = {}  # noqa: E111
    for key in mapping:  # noqa: E111
        if isinstance(key, str):
            string_keys[key.casefold()] = key  # noqa: E111

    seen: set[str] = set()  # noqa: E111
    for preferred_key in _PREFERRED_TEXT_KEYS:  # noqa: E111
        casefold_key = preferred_key.casefold()
        actual_key = string_keys.get(casefold_key)
        if actual_key is None:
            continue  # noqa: E111
        seen.add(actual_key)
        yield from _iter_text_candidates(mapping[actual_key], _visited=_visited)

    for key, value in mapping.items():  # noqa: E111
        if isinstance(key, str) and key in seen:
            continue  # noqa: E111
        if value is mapping:
            continue  # noqa: E111
        yield from _iter_text_candidates(value, _visited=_visited)


def _first_text_candidate(value: Any) -> str | None:
    """Return the first cleaned text candidate from an arbitrary value."""  # noqa: E111

    for text in _iter_text_candidates(value):  # noqa: E111
        if text:
            return text  # noqa: E111
    return None  # noqa: E111


def _clean_structured_text_candidate(text: str | None) -> str | None:
    """Filter out non-descriptive structured text candidates."""  # noqa: E111

    if text is None:  # noqa: E111
        return None

    stripped = text.strip()  # noqa: E111
    if not stripped:  # noqa: E111
        return None

    if (
        stripped.startswith("<")
        and stripped.endswith(">")
        and " object at " in stripped
    ):  # noqa: E111
        return None

    if stripped.startswith("{") and stripped.endswith("}") and ":" in stripped:  # noqa: E111
        return None

    if stripped.startswith("[") and stripped.endswith("]") and "," in stripped:  # noqa: E111
        return None

    if stripped.startswith("(") and stripped.endswith(")") and "," in stripped:  # noqa: E111
        return None

    if " " not in stripped and stripped.casefold() not in _ALLOWED_SINGLE_WORDS:  # noqa: E111
        return None

    return stripped  # noqa: E111


def _format_structured_message(value: Any) -> str | None:
    """Extract readable text from structured compliance message payloads."""  # noqa: E111

    texts: list[str] = []  # noqa: E111
    seen: set[str] = set()  # noqa: E111
    for candidate in _iter_text_candidates(value):  # noqa: E111
        cleaned = _clean_structured_text_candidate(candidate)
        if not cleaned:
            continue  # noqa: E111
        key = cleaned.casefold()
        if key in seen:
            continue  # noqa: E111
        texts.append(cleaned)
        seen.add(key)
        if len(texts) >= 3:
            break  # noqa: E111

    if not texts:  # noqa: E111
        return None

    if len(texts) == 1:  # noqa: E111
        return texts[0]

    return "; ".join(texts)  # noqa: E111


def _collect_missed_meals(
    translations: Mapping[str, str],
    raw_entries: object,
) -> list[str]:
    """Build the missed meals section with sanitised values."""  # noqa: E111

    entries = cast(  # noqa: E111
        Sequence[Mapping[str, object]] | None,
        _normalise_sequence(raw_entries),
    )
    if entries is None:  # noqa: E111
        return []

    summary: list[str] = []  # noqa: E111
    for entry in entries:  # noqa: E111
        if not isinstance(entry, Mapping):
            continue  # noqa: E111

        summary.append(
            translations["missed_meal_item"].format(
                date=_normalise_date(entry.get("date")),
                actual=_normalise_count(entry.get("actual")),
                expected=_normalise_count(entry.get("expected")),
            ),
        )
        if len(summary) >= _MAX_MISSED_MEALS:
            break  # noqa: E111
    return summary  # noqa: E111


def _describe_issue(issue: Mapping[str, object]) -> str:
    """Return a readable description for an issue entry."""  # noqa: E111

    issues = cast(  # noqa: E111
        Sequence[object] | None,
        _normalise_sequence(issue.get("issues")),
    )
    if issues:  # noqa: E111
        for candidate in issues:
            text = _first_text_candidate(candidate)  # noqa: E111
            if text:  # noqa: E111
                return text

    for key in ("description", "summary", "severity"):  # noqa: E111
        text = _first_text_candidate(issue.get(key))
        if text:
            return text  # noqa: E111

    fallback = issue.get("issues")  # noqa: E111
    text = _first_text_candidate(fallback)  # noqa: E111
    if text:  # noqa: E111
        return text
    return "issue"  # noqa: E111


def _collect_issue_summaries(
    translations: Mapping[str, str],
    raw_entries: object,
) -> list[str]:
    """Return normalised issue summary lines."""  # noqa: E111

    entries = cast(  # noqa: E111
        Sequence[Mapping[str, object]] | None,
        _normalise_sequence(raw_entries),
    )
    if entries is None:  # noqa: E111
        return []

    summary: list[str] = []  # noqa: E111
    for entry in entries:  # noqa: E111
        if not isinstance(entry, Mapping):
            continue  # noqa: E111

        summary.append(
            translations["issue_item"].format(
                date=_normalise_date(entry.get("date")),
                description=_describe_issue(entry),
            ),
        )
        if len(summary) >= _MAX_ISSUES:
            break  # noqa: E111
    return summary  # noqa: E111


def _collect_recommendations(
    translations: Mapping[str, str],
    raw_entries: object,
) -> list[str]:
    """Return cleaned recommendation text entries."""  # noqa: E111

    entries = cast(Sequence[object] | None, _normalise_sequence(raw_entries))  # noqa: E111
    if entries is None:  # noqa: E111
        if raw_entries is None:
            return []  # noqa: E111
        iterable: Iterable[object] = (raw_entries,)
    else:  # noqa: E111
        iterable = entries

    summary: list[str] = []  # noqa: E111
    for entry in iterable:  # noqa: E111
        text = _first_text_candidate(entry)
        if not text:
            continue  # noqa: E111
        summary.append(
            translations["recommendation_item"].format(recommendation=text),
        )
        if len(summary) >= _MAX_RECOMMENDATIONS:
            break  # noqa: E111
    return summary  # noqa: E111


def _build_localised_sections(
    translations: Mapping[str, str],
    compliance: FeedingComplianceDisplayMapping,
) -> tuple[list[str], list[str], list[str]]:
    """Return localised summary sections for missed meals, issues, and recommendations."""  # noqa: E111

    missed_summary = _collect_missed_meals(  # noqa: E111
        translations,
        compliance.get("missed_meals"),
    )
    issue_summary = _collect_issue_summaries(  # noqa: E111
        translations,
        compliance.get("compliance_issues"),
    )
    recommendation_summary = _collect_recommendations(  # noqa: E111
        translations,
        compliance.get("recommendations"),
    )

    if not recommendation_summary and (issue_summary or missed_summary):  # noqa: E111
        recommendation_summary.append(translations["no_recommendations"])

    return missed_summary, issue_summary, recommendation_summary  # noqa: E111


def _build_feeding_compliance_summary_from_translations(
    translations: Mapping[str, str],
    *,
    display_name: str,
    compliance: FeedingComplianceDisplayMapping,
) -> FeedingComplianceLocalizedSummary:
    """Build a localised feeding summary from an already-resolved catalog."""  # noqa: E111

    status = compliance.get("status")  # noqa: E111

    if status != "completed":  # noqa: E111
        raw_message = compliance.get("message")
        if _is_structured_message_payload(raw_message):
            message = _format_structured_message(raw_message)  # noqa: E111
        else:
            message = _normalise_text(raw_message)  # noqa: E111
        if not message:
            message = translations["no_data_fallback"]  # noqa: E111

        title = translations["no_data_title"].format(display_name=display_name)
        return {
            "title": title,
            "message": message,
            "score_line": None,
            "missed_meals": [],
            "issues": [],
            "recommendations": [],
        }

    score = _as_float(compliance.get("compliance_score")) or 0.0  # noqa: E111
    days_value = _as_float(compliance.get("days_analyzed"))  # noqa: E111
    days_analyzed = int(days_value) if days_value is not None else 0  # noqa: E111
    missed_summary, issue_summary, recommendation_summary = _build_localised_sections(  # noqa: E111
        translations,
        compliance,
    )

    score_line = translations["score_line"].format(  # noqa: E111
        score=f"{score:.1f}",
        days_analyzed=days_analyzed,
    )
    lines: list[str] = [score_line]  # noqa: E111

    if missed_summary:  # noqa: E111
        lines.append(translations["missed_meals_header"])
        lines.extend(f"- {entry}" for entry in missed_summary)

    if issue_summary:  # noqa: E111
        lines.append(translations["issues_header"])
        lines.extend(f"- {entry}" for entry in issue_summary)

    if recommendation_summary:  # noqa: E111
        lines.append(translations["recommendations_header"])
        lines.extend(f"- {entry}" for entry in recommendation_summary)

    title = translations["alert_title"].format(display_name=display_name)  # noqa: E111
    message = "\n".join(lines) if lines else None  # noqa: E111
    return {  # noqa: E111
        "title": title,
        "message": message,
        "score_line": score_line,
        "missed_meals": missed_summary,
        "issues": issue_summary,
        "recommendations": recommendation_summary,
    }


async def async_build_feeding_compliance_summary(
    hass: HomeAssistant,
    language: str | None,
    *,
    display_name: str,
    compliance: FeedingComplianceDisplayMapping,
) -> FeedingComplianceLocalizedSummary:
    """Return a localised summary for a feeding compliance result."""  # noqa: E111

    translations = await async_get_feeding_compliance_translations(hass, language)  # noqa: E111
    return _build_feeding_compliance_summary_from_translations(  # noqa: E111
        translations,
        display_name=display_name,
        compliance=compliance,
    )


def _load_static_common_translations(language: str | None) -> Mapping[str, str]:
    """Load translation ``common`` entries from packaged JSON files."""  # noqa: E111

    normalized_language = (language or "en").lower()  # noqa: E111
    translations_path = Path(__file__).resolve().parent / "translations"  # noqa: E111

    def _read_common(lang: str) -> dict[str, str]:  # noqa: E111
        file_path = translations_path / f"{lang}.json"
        if not file_path.exists():
            return {}  # noqa: E111
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))  # noqa: E111
        except (OSError, ValueError):
            return {}  # noqa: E111
        common = data.get("common", {})
        return common if isinstance(common, dict) else {}

    localized = _read_common(normalized_language)  # noqa: E111
    fallback = _read_common("en")  # noqa: E111
    return {**fallback, **localized}  # noqa: E111


def get_feeding_compliance_translations(language: str | None) -> dict[str, str]:
    """Return static feeding compliance translations for non-HA unit tests."""  # noqa: E111

    common = _load_static_common_translations(language)  # noqa: E111
    return {  # noqa: E111
        key: str(common.get(translation_key, key))
        for key, translation_key in FEEDING_COMPLIANCE_TRANSLATION_KEYS.items()
    }


def build_feeding_compliance_summary(
    language: str | None,
    *,
    display_name: str,
    compliance: FeedingComplianceDisplayMapping,
) -> FeedingComplianceLocalizedSummary:
    """Return a localized summary without requiring a Home Assistant instance."""  # noqa: E111

    return _build_feeding_compliance_summary_from_translations(  # noqa: E111
        get_feeding_compliance_translations(language),
        display_name=display_name,
        compliance=compliance,
    )


def build_feeding_compliance_notification(
    language: str | None,
    *,
    display_name: str,
    compliance: FeedingComplianceDisplayMapping,
) -> tuple[str, str | None]:
    """Return localised title and body for non-HA unit tests."""  # noqa: E111

    summary = build_feeding_compliance_summary(  # noqa: E111
        language,
        display_name=display_name,
        compliance=compliance,
    )
    return summary["title"], summary["message"]  # noqa: E111


async def async_build_feeding_compliance_notification(
    hass: HomeAssistant,
    language: str | None,
    *,
    display_name: str,
    compliance: FeedingComplianceDisplayMapping,
) -> tuple[str, str | None]:
    """Return localised title and body for a feeding compliance result."""  # noqa: E111

    summary = await async_build_feeding_compliance_summary(  # noqa: E111
        hass,
        language,
        display_name=display_name,
        compliance=compliance,
    )
    return summary["title"], summary["message"]  # noqa: E111


T = TypeVar("T")


class _BoundedSequenceSnapshot(Sequence[T]):
    """Cache at most ``limit`` items from an iterable for safe re-iteration."""  # noqa: E111

    __slots__ = ("_cache", "_iterator", "_limit")  # noqa: E111

    def __init__(self, source: Iterable[T], limit: int) -> None:  # noqa: E111
        self._iterator: Iterator[T] | None = iter(source)
        self._cache: list[T] = []
        self._limit = limit

    def __iter__(self) -> Iterator[T]:  # noqa: E111
        index = 0
        while True:
            self._consume_to(index + 1)  # noqa: E111
            if index >= len(self._cache):  # noqa: E111
                break
            yield self._cache[index]  # noqa: E111
            index += 1  # noqa: E111

    def __len__(self) -> int:  # pragma: no cover - rarely exercised  # noqa: E111
        self._consume_to(self._limit)
        return len(self._cache)

    @overload  # noqa: E111
    def __getitem__(  # noqa: E111
        self, index: int, /
    ) -> T:  # pragma: no cover - defensive
        """Return the cached item at ``index``."""

    @overload  # noqa: E111
    def __getitem__(  # noqa: E111
        self,
        index: slice,
        /,
    ) -> Sequence[T]:  # pragma: no cover - defensive
        """Return a sliced view of the cached items."""

    def __getitem__(self, index: int | slice, /) -> T | Sequence[T]:  # noqa: E111
        """Return cached values, supporting both index and slice access."""

        if isinstance(index, slice):
            self._consume_to(self._limit)  # noqa: E111
            return self._cache[index]  # noqa: E111

        if index < 0:
            self._consume_to(self._limit)  # noqa: E111
        else:
            self._consume_to(index + 1)  # noqa: E111
        return self._cache[index]

    def _consume_to(self, count: int) -> None:  # noqa: E111
        if self._iterator is None:
            return  # noqa: E111

        target = min(self._limit, max(count, 0))
        remaining = target - len(self._cache)
        if remaining <= 0:
            if target >= self._limit:  # noqa: E111
                self._iterator = None
            return  # noqa: E111

        iterator = self._iterator
        assert iterator is not None

        start_len = len(self._cache)
        for item in islice(iterator, remaining):
            self._cache.append(item)  # noqa: E111

        if (
            len(self._cache) >= self._limit
            or target >= self._limit
            or len(self._cache) == start_len
        ):
            self._iterator = None  # noqa: E111
