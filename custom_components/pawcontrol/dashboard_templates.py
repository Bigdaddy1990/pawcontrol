"""Dashboard template caching system for Paw Control with multiple themes.

This module provides efficient template caching and management for dashboard
card generation with multiple visual themes and layouts. It implements LRU
caching, template validation, and async template loading with various styles.

Quality Scale: Platinum target
Home Assistant: 2025.9.0+
Python: 3.13+
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from functools import lru_cache
import json
import logging
from math import isfinite
from typing import Final, NotRequired, TypedDict, TypeVar, cast

from homeassistant.const import STATE_UNKNOWN
from homeassistant.core import HomeAssistant, State, callback
from homeassistant.util import dt as dt_util

from .const import (
  DEFAULT_REGULAR_FEEDING_AMOUNT,
  DOMAIN,
  MODULE_FEEDING,
  MODULE_GPS,
  MODULE_HEALTH,
  MODULE_NOTIFICATIONS,
  MODULE_WALK,
)
from .coordinator_tasks import (
  default_rejection_metrics,
  derive_rejection_metrics,
  merge_rejection_metric_values,
)
from .dashboard_shared import CardCollection, CardConfig, coerce_dog_configs
from .service_guard import ServiceGuardResultPayload, normalise_guard_history
from .translation_helpers import (
  async_get_component_translation_lookup,
  get_cached_component_translation_lookup,
  resolve_component_translation,
)
from .types import (
  CardModConfig,
  CoordinatorRejectionMetrics,
  CoordinatorResilienceSummary,
  CoordinatorStatisticsPayload,
  DogModulesConfig,
  HelperManagerGuardMetrics,
  JSONMapping,
  JSONMutableMapping,
  JSONValue,
  RawDogConfig,
  TemplateCacheDiagnosticsMetadata,
  TemplateCacheSnapshot,
  TemplateCacheStats,
  coerce_dog_modules_config,
)

type TranslationLookup = tuple[Mapping[str, str], Mapping[str, str]]

STATISTICS_LABEL_KEYS: Final[tuple[str, ...]] = (
  "statistics_header",
  "dogs_managed",
  "active_modules",
  "module_feeding",
  "module_walks",
  "module_health",
  "module_gps",
  "module_notifications",
  "last_updated",
  "summary_card_title",
  "resilience_metrics_header",
  "coordinator_resilience_label",
  "service_resilience_label",
  "guard_metrics_header",
  "guard_executed",
  "guard_skipped",
  "guard_reasons",
  "guard_last_results",
  "guard_result_executed",
  "guard_result_skipped",
  "guard_result_reason",
  "rejected_calls",
  "rejecting_breakers",
  "rejection_rate",
  "last_rejection",
  "open_breaker_names",
  "half_open_breaker_names",
  "unknown_breaker_names",
  "rejection_breaker_names",
  "open_breaker_ids",
  "half_open_breaker_ids",
  "unknown_breaker_ids",
  "rejection_breaker_ids",
  "last_rejecting_breaker",
)

STATISTICS_FALLBACK_KEYS: Final[tuple[str, ...]] = (
  "no_rejection_rate",
  "no_last_rejection",
  "no_guard_reasons",
  "no_guard_results",
)

NOTIFICATION_LABEL_KEYS: Final[tuple[str, ...]] = (
  "sent_today",
  "failed_deliveries",
  "quiet_hours_active",
  "preferred_channels",
  "recent_notification",
  "type",
  "priority",
  "sent",
  "send_test_notification",
  "reset_quiet_hours",
)

NOTIFICATION_TEMPLATE_KEYS: Final[tuple[str, ...]] = (
  "overview_heading",
  "settings_title",
)

NOTIFICATION_FALLBACK_KEYS: Final[tuple[str, ...]] = (
  "default_channels",
  "no_notifications",
  "unknown_value",
  "default_priority",
  "diagnostics_title",
  "diagnostics_message",
)

FEEDING_LABEL_KEYS: Final[tuple[str, ...]] = (
  "feeding_schedule",
  "meal_breakfast",
  "meal_lunch",
  "meal_dinner",
  "meal_snack",
)

HEALTH_LABEL_KEYS: Final[tuple[str, ...]] = (
  "health_check_button",
  "health_metrics",
  "weight",
  "health_score",
  "health_gauge",
  "activity",
  "health_trends",
  "timeline_last_health_check",
  "weather_health_score",
  "temperature_risk",
  "activity_level",
  "walk_safety",
)

HEALTH_TEMPLATE_KEYS: Final[tuple[str, ...]] = (
  "statistics_health_section",
  "weather_health_compact_name",
  "weather_health_card_title",
  "weather_health_chart_title",
)

DASHBOARD_TRANSLATION_KEYS: Final[frozenset[str]] = frozenset(
  {"dashboard_statistics_empty_list"}
  | {f"dashboard_statistics_label_{key}" for key in STATISTICS_LABEL_KEYS}
  | {f"dashboard_statistics_fallback_{key}" for key in STATISTICS_FALLBACK_KEYS}
  | {f"dashboard_notification_label_{key}" for key in NOTIFICATION_LABEL_KEYS}
  | {f"dashboard_notification_template_{key}" for key in NOTIFICATION_TEMPLATE_KEYS}
  | {f"dashboard_notification_fallback_{key}" for key in NOTIFICATION_FALLBACK_KEYS}
  | {f"dashboard_feeding_label_{key}" for key in FEEDING_LABEL_KEYS}
  | {f"dashboard_health_label_{key}" for key in HEALTH_LABEL_KEYS}
  | {f"dashboard_health_template_{key}" for key in HEALTH_TEMPLATE_KEYS}
)


def _format_breaker_list(
  entries: Sequence[str],
  translation_lookup: TranslationLookup,
) -> str:
  """Return a human readable summary for breaker identifier lists."""  # noqa: E111

  if entries:  # noqa: E111
    return ", ".join(entries)

  translations, fallback = translation_lookup  # noqa: E111
  return resolve_component_translation(  # noqa: E111
    translations,
    fallback,
    "dashboard_statistics_empty_list",
    default="none",
  )


def _format_guard_reasons(
  reasons: Mapping[str, int],
  translation_lookup: TranslationLookup,
) -> list[str]:
  """Return formatted guard skip reasons for summary output."""  # noqa: E111

  if not reasons:  # noqa: E111
    default_value = _format_breaker_list((), translation_lookup)
    fallback = _translated_statistics_fallback(
      translation_lookup,
      "no_guard_reasons",
      default_value,
    )
    return [fallback]

  sorted_reasons = sorted(  # noqa: E111
    ((reason, count) for reason, count in reasons.items()),
    key=lambda item: (-item[1], item[0]),
  )

  return [f"{reason}: {count}" for reason, count in sorted_reasons]  # noqa: E111


def _format_guard_results(
  results: Sequence[ServiceGuardResultPayload],
  translation_lookup: TranslationLookup,
  *,
  limit: int = 5,
) -> list[str]:
  """Return formatted guard result summaries for the statistics markdown."""  # noqa: E111

  formatted: list[str] = []  # noqa: E111
  for entry in list(results)[:limit]:  # noqa: E111
    if not isinstance(entry, Mapping):
      continue  # noqa: E111

    domain = str(entry.get("domain", "unknown"))
    service = str(entry.get("service", "unknown"))
    executed = bool(entry.get("executed"))

    outcome_key = "guard_result_executed" if executed else "guard_result_skipped"
    outcome_label = _translated_statistics_label(translation_lookup, outcome_key)

    reason = entry.get("reason")
    if isinstance(reason, str) and reason:
      reason_label = _translated_statistics_label(  # noqa: E111
        translation_lookup,
        "guard_result_reason",
      )
      outcome_label = f"{outcome_label} ({reason_label}: {reason})"  # noqa: E111

    description = entry.get("description")
    if isinstance(description, str) and description:
      outcome_label = f"{outcome_label} - {description}"  # noqa: E111

    formatted.append(f"{domain}.{service}: {outcome_label}")

  if formatted:  # noqa: E111
    return formatted

  default_value = _format_breaker_list((), translation_lookup)  # noqa: E111
  fallback = _translated_statistics_fallback(  # noqa: E111
    translation_lookup,
    "no_guard_results",
    default_value,
  )
  return [fallback]  # noqa: E111


class WeatherThemeConfig(TypedDict):
  """Color palette for weather dashboards."""  # noqa: E111

  primary_color: str  # noqa: E111
  accent_color: str  # noqa: E111
  success_color: str  # noqa: E111
  warning_color: str  # noqa: E111
  danger_color: str  # noqa: E111


class ThemeIconStyle(TypedDict, total=False):
  """Icon styling flags used by themed dashboards."""  # noqa: E111

  style: str  # noqa: E111
  animated: bool  # noqa: E111
  bounce: bool  # noqa: E111
  glow: bool  # noqa: E111


class ThemeColorPalette(TypedDict):
  """Named colors exposed to templates and helper methods."""  # noqa: E111

  primary: str  # noqa: E111
  accent: str  # noqa: E111
  background: str  # noqa: E111
  text: str  # noqa: E111


class ThemeStyles(TypedDict):
  """Theme metadata applied to generated card templates."""  # noqa: E111

  colors: ThemeColorPalette  # noqa: E111
  card_mod: NotRequired[CardModConfig]  # noqa: E111
  icons: NotRequired[ThemeIconStyle]  # noqa: E111


class MapCardOptions(TypedDict, total=False):
  """Options that adjust the generated map card template."""  # noqa: E111

  zoom: int  # noqa: E111
  default_zoom: int  # noqa: E111
  dark_mode: bool  # noqa: E111
  hours_to_show: int  # noqa: E111


type _MapOptionPairs = Iterable[tuple[str, object]]
type MapOptionsInput = (
  MapCardOptions
  | Mapping[
    str,
    object,
  ]
  | _MapOptionPairs
  | None
)


class NotificationLastEvent(TypedDict, total=False):
  """Details about the most recent notification sent for a dog."""  # noqa: E111

  type: str  # noqa: E111
  priority: str  # noqa: E111
  sent_at: str  # noqa: E111
  title: str  # noqa: E111
  message: str  # noqa: E111
  channel: str  # noqa: E111
  status: str  # noqa: E111


class NotificationDogOverview(TypedDict, total=False):
  """Per-dog delivery metrics tracked by the notifications dashboard."""  # noqa: E111

  sent_today: int  # noqa: E111
  quiet_hours_active: bool  # noqa: E111
  channels: list[str]  # noqa: E111
  last_notification: NotRequired[NotificationLastEvent]  # noqa: E111


class NotificationPerformanceMetrics(TypedDict, total=False):
  """High-level delivery metrics exported by the notifications sensor."""  # noqa: E111

  notifications_failed: int  # noqa: E111


class NotificationOverviewAttributes(TypedDict, total=False):
  """Attributes exposed by ``sensor.pawcontrol_notifications``."""  # noqa: E111

  performance_metrics: NotificationPerformanceMetrics  # noqa: E111
  per_dog: dict[str, NotificationDogOverview]  # noqa: E111


_LOGGER = logging.getLogger(__name__)


def _translated_statistics_fallback(
  translation_lookup: TranslationLookup,
  label: str,
  default: str,
) -> str:
  """Return a localized fallback string for statistics summaries."""  # noqa: E111

  translations, fallback = translation_lookup  # noqa: E111
  return resolve_component_translation(  # noqa: E111
    translations,
    fallback,
    f"dashboard_statistics_fallback_{label}",
    default=default,
  )


def _translated_statistics_label(
  translation_lookup: TranslationLookup,
  label: str,
) -> str:
  """Return a localized statistics label for the configured language."""  # noqa: E111

  translations, fallback = translation_lookup  # noqa: E111
  return resolve_component_translation(  # noqa: E111
    translations,
    fallback,
    f"dashboard_statistics_label_{label}",
    default=label,
  )


def _translated_notification_label(
  translation_lookup: TranslationLookup,
  label: str,
) -> str:
  """Return a localized notification dashboard label."""  # noqa: E111

  translations, fallback = translation_lookup  # noqa: E111
  return resolve_component_translation(  # noqa: E111
    translations,
    fallback,
    f"dashboard_notification_label_{label}",
    default=label,
  )


def _translated_notification_template(
  translation_lookup: TranslationLookup,
  template: str,
  **values: str,
) -> str:
  """Return a formatted notification dashboard template string."""  # noqa: E111

  translations, fallback = translation_lookup  # noqa: E111
  template_value = resolve_component_translation(  # noqa: E111
    translations,
    fallback,
    f"dashboard_notification_template_{template}",
    default=template,
  )
  return template_value.format(**values)  # noqa: E111


def _translated_notification_fallback(
  translation_lookup: TranslationLookup,
  label: str,
  default: str,
) -> str:
  """Return a localized fallback string for notification dashboards."""  # noqa: E111

  translations, fallback = translation_lookup  # noqa: E111
  return resolve_component_translation(  # noqa: E111
    translations,
    fallback,
    f"dashboard_notification_fallback_{label}",
    default=default,
  )


def _translated_feeding_label(
  translation_lookup: TranslationLookup,
  label: str,
) -> str:
  """Return a localized feeding dashboard label."""  # noqa: E111

  translations, fallback = translation_lookup  # noqa: E111
  return resolve_component_translation(  # noqa: E111
    translations,
    fallback,
    f"dashboard_feeding_label_{label}",
    default=label,
  )


def _translated_health_label(
  translation_lookup: TranslationLookup,
  label: str,
) -> str:
  """Return a localized health dashboard label."""  # noqa: E111

  translations, fallback = translation_lookup  # noqa: E111
  return resolve_component_translation(  # noqa: E111
    translations,
    fallback,
    f"dashboard_health_label_{label}",
    default=label,
  )


def _translated_health_template(
  translation_lookup: TranslationLookup,
  template: str,
  **values: object,
) -> str:
  """Return a localized health dashboard template string."""  # noqa: E111

  translations, fallback = translation_lookup  # noqa: E111
  template_value = resolve_component_translation(  # noqa: E111
    translations,
    fallback,
    f"dashboard_health_template_{template}",
    default=template,
  )
  return template_value.format(**values)  # noqa: E111


# Weather dashboard constants
WEATHER_THEMES: Final[dict[str, WeatherThemeConfig]] = {
  "modern": {
    "primary_color": "#2196F3",
    "accent_color": "#FF5722",
    "success_color": "#4CAF50",
    "warning_color": "#FF9800",
    "danger_color": "#F44336",
  },
  "playful": {
    "primary_color": "#FF6B6B",
    "accent_color": "#4ECDC4",
    "success_color": "#95E1D3",
    "warning_color": "#FFE66D",
    "danger_color": "#FF8B94",
  },
  "minimal": {
    "primary_color": "#000000",
    "accent_color": "#666666",
    "success_color": "#333333",
    "warning_color": "#999999",
    "danger_color": "#CCCCCC",
  },
  "dark": {
    "primary_color": "#0F3460",
    "accent_color": "#E94560",
    "success_color": "#16213E",
    "warning_color": "#0F4C75",
    "danger_color": "#3282B8",
  },
}

WEATHER_CARD_TYPES: Final[list[str]] = [
  "weather_status",
  "weather_alerts",
  "weather_recommendations",
  "weather_chart",
  "weather_breed_advisory",
  "weather_action_buttons",
  "weather_dashboard_layout",
]

# Cache configuration
TEMPLATE_CACHE_SIZE: Final[int] = 128
TEMPLATE_TTL_SECONDS: Final[int] = 300  # 5 minutes
MAX_TEMPLATE_SIZE: Final[int] = 1024 * 1024  # 1MB per template

MAP_ZOOM_MIN: Final[int] = 1
MAP_ZOOM_MAX: Final[int] = 20
DEFAULT_MAP_ZOOM: Final[int] = 15
DEFAULT_MAP_HOURS_TO_SHOW: Final[int] = 2
MAP_HISTORY_MIN_HOURS: Final[int] = 1
MAP_HISTORY_MAX_HOURS: Final[int] = 168
MAP_OPTION_KEYS: Final[frozenset[str]] = frozenset(
  {"zoom", "default_zoom", "dark_mode", "hours_to_show"},
)


type CardTemplatePayload = CardConfig | CardCollection


PayloadT = TypeVar("PayloadT", bound=CardTemplatePayload)


def _clone_template[PayloadT: CardTemplatePayload](template: PayloadT) -> PayloadT:
  """Return a shallow copy of a cached template payload."""  # noqa: E111

  if isinstance(template, list):  # noqa: E111
    return cast(PayloadT, [card.copy() for card in template])
  return cast(PayloadT, template.copy())  # noqa: E111


class TemplateCache[PayloadT: CardTemplatePayload]:
  """High-performance template cache with LRU eviction and TTL.

  Provides memory-efficient caching of dashboard card templates with
  automatic expiration and memory management.
  """  # noqa: E111

  def __init__(self, maxsize: int = TEMPLATE_CACHE_SIZE) -> None:  # noqa: E111
    """Initialize template cache.

    Args:
        maxsize: Maximum number of templates to cache
    """
    self._cache: dict[str, PayloadT] = {}
    self._access_times: dict[str, float] = {}
    self._maxsize = maxsize
    self._hits = 0
    self._misses = 0
    self._evictions = 0
    self._lock = asyncio.Lock()

  async def get(self, key: str) -> PayloadT | None:  # noqa: E111
    """Get template from cache.

    Args:
        key: Template cache key

    Returns:
        Cached template or None if not found/expired
    """
    async with self._lock:
      current_time = dt_util.utcnow().timestamp()  # noqa: E111

      if key not in self._cache:  # noqa: E111
        self._misses += 1
        return None

      # Check TTL  # noqa: E114
      if current_time - self._access_times[key] > TEMPLATE_TTL_SECONDS:  # noqa: E111
        del self._cache[key]
        del self._access_times[key]
        self._misses += 1
        return None

      # Update access time  # noqa: E114
      self._access_times[key] = current_time  # noqa: E111
      self._hits += 1  # noqa: E111

      return _clone_template(self._cache[key])  # noqa: E111

  async def set(self, key: str, template: PayloadT) -> None:  # noqa: E111
    """Store template in cache.

    Args:
        key: Template cache key
        template: Template to cache
    """
    async with self._lock:
      # Check template size to prevent memory bloat  # noqa: E114
      template_size = len(json.dumps(template, separators=(",", ":")))  # noqa: E111
      if template_size > MAX_TEMPLATE_SIZE:  # noqa: E111
        _LOGGER.warning(
          "Template %s too large (%d bytes), not caching",
          key,
          template_size,
        )
        return

      current_time = dt_util.utcnow().timestamp()  # noqa: E111

      # Evict LRU items if needed  # noqa: E114
      while len(self._cache) >= self._maxsize:  # noqa: E111
        await self._evict_lru()

      self._cache[key] = _clone_template(template)  # noqa: E111
      self._access_times[key] = current_time  # noqa: E111

  async def _evict_lru(self) -> None:  # noqa: E111
    """Evict least recently used template."""
    if not self._access_times:
      return  # noqa: E111

    lru_key = min(
      self._access_times,
      key=lambda key: self._access_times[key],
    )
    del self._cache[lru_key]
    del self._access_times[lru_key]
    self._evictions += 1

  async def clear(self) -> None:  # noqa: E111
    """Clear all cached templates."""
    async with self._lock:
      self._cache.clear()  # noqa: E111
      self._access_times.clear()  # noqa: E111
      self._hits = 0  # noqa: E111
      self._misses = 0  # noqa: E111
      self._evictions = 0  # noqa: E111

  @callback  # noqa: E111
  def get_stats(self) -> TemplateCacheStats:  # noqa: E111
    """Get cache statistics."""
    total = self._hits + self._misses
    hit_rate = (self._hits / total * 100.0) if total > 0 else 0.0

    stats: TemplateCacheStats = {
      "hits": self._hits,
      "misses": self._misses,
      "hit_rate": hit_rate,
      "cached_items": len(self._cache),
      "evictions": self._evictions,
      "max_size": self._maxsize,
    }

    return stats

  @callback  # noqa: E111
  def get_metadata(self) -> TemplateCacheDiagnosticsMetadata:  # noqa: E111
    """Return metadata describing cache configuration."""

    metadata: TemplateCacheDiagnosticsMetadata = {
      "cached_keys": sorted(self._cache),
      "ttl_seconds": TEMPLATE_TTL_SECONDS,
      "max_size": self._maxsize,
      "evictions": self._evictions,
    }

    return metadata

  @callback  # noqa: E111
  def coordinator_snapshot(self) -> TemplateCacheSnapshot:  # noqa: E111
    """Return a snapshot suitable for diagnostics collectors."""

    return TemplateCacheSnapshot(
      stats=self.get_stats(),
      metadata=self.get_metadata(),
    )


class DashboardTemplates:
  """Dashboard template manager with caching, themes, and multiple layouts.

  Provides efficient template generation and caching for dashboard cards
  with automatic optimization based on usage patterns and multiple visual themes.
  """  # noqa: E111

  def __init__(self, hass: HomeAssistant) -> None:  # noqa: E111
    """Initialize template manager.

    Args:
        hass: Home Assistant instance
    """
    self.hass = hass
    self._cache: TemplateCache[CardTemplatePayload] = TemplateCache()

  @staticmethod  # noqa: E111
  @lru_cache(maxsize=64)  # noqa: E111
  def _get_base_card_template(card_type: str) -> CardConfig:  # noqa: E111
    """Get base template for card type with LRU caching.

    Args:
        card_type: Type of card to get template for

    Returns:
        Base card template
    """
    base_templates: dict[str, CardConfig] = {
      "status": {
        "type": "entities",
        "state_color": True,
        "show_header_toggle": False,
      },
      "button": {
        "type": "button",
        "show_state": True,
        "show_icon": True,
      },
      "horizontal_stack": {
        "type": "horizontal-stack",
        "cards": [],
      },
      "vertical_stack": {
        "type": "vertical-stack",
        "cards": [],
      },
      "grid": {
        "type": "grid",
        "columns": 2,
        "cards": [],
      },
      "map": {
        "type": "map",
        "default_zoom": DEFAULT_MAP_ZOOM,
        "dark_mode": False,
        "hours_to_show": DEFAULT_MAP_HOURS_TO_SHOW,
      },
      "history_graph": {
        "type": "history-graph",
        "hours_to_show": 24,
        "refresh_interval": 0,
      },
      "statistics_graph": {
        "type": "statistics-graph",
        "stat_types": ["mean", "min", "max"],
        "days_to_show": 30,
      },
      "markdown": {
        "type": "markdown",
        "content": "",
      },
      "conditional": {
        "type": "conditional",
        "conditions": [],
        "card": {},
      },
      "gauge": {
        "type": "gauge",
        "min": 0,
        "max": 100,
        "unit": "%",
      },
      "picture_elements": {
        "type": "picture-elements",
        "elements": [],
      },
      "custom:mushroom-entity": {
        "type": "custom:mushroom-entity",
        "icon_color": "blue",
        "fill_container": True,
      },
      "custom:mini-graph-card": {
        "type": "custom:mini-graph-card",
        "hours_to_show": 24,
        "points_per_hour": 2,
        "line_width": 2,
      },
    }

    template = base_templates.get(card_type)
    if template is None:
      return {"type": card_type}  # noqa: E111

    return template.copy()

  def _get_theme_styles(self, theme: str = "modern") -> ThemeStyles:  # noqa: E111
    """Get theme-specific styling options.

    Args:
        theme: Theme name (modern, playful, minimal, dark)

    Returns:
        Theme styling dictionary
    """
    themes: dict[str, ThemeStyles] = {
      "modern": {
        "card_mod": {
          "style": """
                        ha-card {
                            background: linear-gradient(135deg, rgba(255,255,255,0.9) 0%, rgba(250,250,250,0.95) 100%);
                            border-radius: 16px;
                            box-shadow: 0 4px 20px rgba(0,0,0,0.08);
                            transition: all 0.3s ease;
                        }
                        ha-card:hover {
                            transform: translateY(-2px);
                            box-shadow: 0 8px 30px rgba(0,0,0,0.12);
                        }
                    """,  # noqa: E501
        },
        "colors": {
          "primary": "#2196F3",
          "accent": "#FF5722",
          "background": "#FAFAFA",
          "text": "#212121",
        },
        "icons": {
          "style": "rounded",
          "animated": True,
        },
      },
      "playful": {
        "card_mod": {
          "style": """
                        ha-card {
                            background: linear-gradient(45deg, #FF6B6B 0%, #4ECDC4 100%);
                            border-radius: 24px;
                            border: 3px solid white;
                            box-shadow: 0 8px 32px rgba(31,38,135,0.37);
                            backdrop-filter: blur(4px);
                            animation: float 6s ease-in-out infinite;
                        }
                        @keyframes float {
                            0% { transform: translateY(0px); }
                            50% { transform: translateY(-10px); }
                            100% { transform: translateY(0px); }
                        }
                    """,  # noqa: E501
        },
        "colors": {
          "primary": "#FF6B6B",
          "accent": "#4ECDC4",
          "background": "#FFE66D",
          "text": "#292F36",
        },
        "icons": {
          "style": "emoji",
          "animated": True,
          "bounce": True,
        },
      },
      "minimal": {
        "card_mod": {
          "style": """
                        ha-card {
                            background: white;
                            border-radius: 4px;
                            border: 1px solid #E0E0E0;
                            box-shadow: none;
                        }
                    """,
        },
        "colors": {
          "primary": "#000000",
          "accent": "#666666",
          "background": "#FFFFFF",
          "text": "#000000",
        },
        "icons": {
          "style": "outlined",
          "animated": False,
        },
      },
      "dark": {
        "card_mod": {
          "style": """
                        ha-card {
                            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
                            border-radius: 12px;
                            border: 1px solid rgba(255,255,255,0.1);
                            box-shadow: 0 8px 32px rgba(0,0,0,0.4);
                        }
                    """,  # noqa: E501
        },
        "colors": {
          "primary": "#0F3460",
          "accent": "#E94560",
          "background": "#1A1A2E",
          "text": "#FFFFFF",
        },
        "icons": {
          "style": "filled",
          "animated": True,
          "glow": True,
        },
      },
    }

    return themes.get(theme, themes["modern"])

  def _card_mod(self, theme_styles: ThemeStyles) -> CardModConfig:  # noqa: E111
    """Return a mutable card-mod payload for template assembly."""

    card_mod = theme_styles.get("card_mod")
    if card_mod is None:
      return cast(CardModConfig, {})  # noqa: E111
    return cast(CardModConfig, card_mod.copy())

  def _ensure_card_mod(  # noqa: E111
    self,
    template: CardConfig,
    theme_styles: ThemeStyles,
  ) -> CardModConfig:
    """Return a card-mod payload attached to ``template``."""

    existing = template.get("card_mod")
    if isinstance(existing, dict):
      return cast(CardModConfig, existing)  # noqa: E111

    card_mod = self._card_mod(theme_styles)
    template["card_mod"] = card_mod
    return card_mod

  @staticmethod  # noqa: E111
  def _parse_int(value: object, *, default: int = 0) -> int:  # noqa: E111
    """Return an integer coerced from ``value`` with ``default`` fallback."""

    if isinstance(value, bool):
      return int(value)  # noqa: E111
    if isinstance(value, int):
      return value  # noqa: E111
    if isinstance(value, float):
      return int(value)  # noqa: E111
    if isinstance(value, str):
      try:  # noqa: E111
        return int(float(value))
      except ValueError:  # noqa: E111
        return default
    return default

  @staticmethod  # noqa: E111
  def _parse_bool(value: object) -> bool:  # noqa: E111
    """Return a boolean coerced from arbitrary payloads."""

    if isinstance(value, bool):
      return value  # noqa: E111
    if isinstance(value, int | float):
      return value != 0  # noqa: E111
    if isinstance(value, str):
      return value.strip().lower() in {"1", "true", "yes", "on"}  # noqa: E111
    return False

  @staticmethod  # noqa: E111
  def _parse_channels(value: object) -> list[str]:  # noqa: E111
    """Return a list of channel labels extracted from ``value``."""

    if isinstance(value, str):
      return [chunk for chunk in (part.strip() for part in value.split(",")) if chunk]  # noqa: E111

    if isinstance(value, Sequence) and not isinstance(
      value,
      str | bytes | bytearray,
    ):
      channels: list[str] = []  # noqa: E111
      for item in value:  # noqa: E111
        candidate = item.strip() if isinstance(item, str) else str(item).strip()
        if candidate:
          channels.append(candidate)  # noqa: E111
      return channels  # noqa: E111

    return []

  @staticmethod  # noqa: E111
  def _parse_last_notification(value: object) -> NotificationLastEvent | None:  # noqa: E111
    """Return a structured notification payload extracted from ``value``."""

    if not isinstance(value, Mapping):
      return None  # noqa: E111

    event: NotificationLastEvent = {}

    for key in ("type", "priority", "title", "message", "channel", "status"):
      raw = value.get(key)  # noqa: E111
      if raw is None:  # noqa: E111
        continue
      event[key] = str(raw)  # noqa: E111

    sent_at = value.get("sent_at")
    if isinstance(sent_at, str):
      event["sent_at"] = sent_at  # noqa: E111
    elif sent_at is not None:
      event["sent_at"] = str(sent_at)  # noqa: E111

    return event or None

  @staticmethod  # noqa: E111
  def _normalise_notifications_state(  # noqa: E111
    state: State | None,
  ) -> tuple[NotificationPerformanceMetrics, dict[str, NotificationDogOverview]]:
    """Return typed metrics extracted from ``sensor.pawcontrol_notifications``."""

    metrics: NotificationPerformanceMetrics = {"notifications_failed": 0}
    per_dog: dict[str, NotificationDogOverview] = {}

    if state is None:
      return metrics, per_dog  # noqa: E111

    attributes = getattr(state, "attributes", None)
    if not isinstance(attributes, Mapping):
      return metrics, per_dog  # noqa: E111

    raw_metrics = attributes.get("performance_metrics")
    if isinstance(raw_metrics, Mapping):
      metrics["notifications_failed"] = DashboardTemplates._parse_int(  # noqa: E111
        raw_metrics.get("notifications_failed"),
        default=0,
      )

    raw_per_dog = attributes.get("per_dog")
    if isinstance(raw_per_dog, Mapping):
      for dog_id, raw_stats in raw_per_dog.items():  # noqa: E111
        if not isinstance(dog_id, str) or not isinstance(raw_stats, Mapping):
          continue  # noqa: E111

        dog_overview: NotificationDogOverview = {
          "sent_today": DashboardTemplates._parse_int(
            raw_stats.get("sent_today"),
            default=0,
          ),
          "quiet_hours_active": DashboardTemplates._parse_bool(
            raw_stats.get("quiet_hours_active"),
          ),
          "channels": DashboardTemplates._parse_channels(
            raw_stats.get("channels"),
          ),
        }

        last_notification = DashboardTemplates._parse_last_notification(
          raw_stats.get("last_notification"),
        )
        if last_notification is not None:
          dog_overview["last_notification"] = last_notification  # noqa: E111

        per_dog[dog_id] = dog_overview

    return metrics, per_dog

  async def get_dog_status_card_template(  # noqa: E111
    self,
    dog_id: str,
    dog_name: str,
    modules: DogModulesConfig,
    theme: str = "modern",
  ) -> CardConfig:
    """Get themed dog status card template.

    Args:
        dog_id: Dog identifier
        dog_name: Dog display name
        modules: Enabled modules for the dog
        theme: Visual theme to apply

    Returns:
        Complete status card template with theme
    """
    cache_key = f"dog_status_{dog_id}_{hash(frozenset(modules.items()))}_{theme}"

    # Try cache first
    cached = await self._cache.get(cache_key)
    if isinstance(cached, dict):
      return cached  # noqa: E111

    # Generate template
    template = await self._generate_dog_status_template(
      dog_id,
      dog_name,
      modules,
      theme,
    )

    # Cache for future use
    await self._cache.set(cache_key, template)

    return template

  async def _generate_dog_status_template(  # noqa: E111
    self,
    dog_id: str,
    dog_name: str,
    modules: DogModulesConfig,
    theme: str = "modern",
  ) -> CardConfig:
    """Generate themed dog status card template.

    Args:
        dog_id: Dog identifier
        dog_name: Dog display name
        modules: Enabled modules
        theme: Visual theme

    Returns:
        Status card template with theme styling
    """
    base_template = self._get_base_card_template("status")
    theme_styles = self._get_theme_styles(theme)

    # Core entities - always present
    entities = [
      f"sensor.{dog_id}_status",
      f"sensor.{dog_id}_last_activity",
    ]

    # Add module-specific entities
    if modules.get("feeding"):
      entities.extend(  # noqa: E111
        [
          f"sensor.{dog_id}_last_fed",
          f"sensor.{dog_id}_meals_today",
          f"sensor.{dog_id}_daily_food_consumed",
        ],
      )

    if modules.get("walk"):
      entities.extend(  # noqa: E111
        [
          f"binary_sensor.{dog_id}_is_walking",
          f"sensor.{dog_id}_last_walk",
          f"sensor.{dog_id}_daily_walk_time",
        ],
      )

    if modules.get("health"):
      entities.extend(  # noqa: E111
        [
          f"sensor.{dog_id}_weight",
          f"sensor.{dog_id}_health_status",
          f"sensor.{dog_id}_health_score",
        ],
      )

    if modules.get("gps"):
      entities.extend(  # noqa: E111
        [
          f"device_tracker.{dog_id}_location",
          f"sensor.{dog_id}_distance_from_home",
          f"sensor.{dog_id}_current_speed",
        ],
      )

    # Build template with theme
    card_mod = self._card_mod(theme_styles)
    template: CardConfig = {
      **base_template,
      "title": f"{self._get_dog_emoji(theme)} {dog_name} Status",
      "entities": entities,
      "card_mod": card_mod,
    }

    # Add theme-specific enhancements
    if theme == "playful":
      template["icon"] = "mdi:dog-side"  # noqa: E111
      template["icon_color"] = theme_styles["colors"]["primary"]  # noqa: E111
    elif theme == "modern":
      template["show_state"] = True  # noqa: E111
      template["state_color"] = True  # noqa: E111

    return template

  def _get_dog_emoji(self, theme: str) -> str:  # noqa: E111
    """Get theme-appropriate dog emoji.

    Args:
        theme: Theme name

    Returns:
        Dog emoji for the theme
    """
    emojis = {
      "modern": "🐕",
      "playful": "🐶",
      "minimal": "•",
      "dark": "🌙",
    }
    return emojis.get(theme, "🐕")

  async def get_action_buttons_template(  # noqa: E111
    self,
    dog_id: str,
    modules: DogModulesConfig,
    theme: str = "modern",
    layout: str = "cards",
  ) -> CardCollection:
    """Get themed action buttons template for dog."""
    cache_key = (
      f"action_buttons_{dog_id}_{hash(frozenset(modules.items()))}_{theme}_{layout}"
    )

    cached = await self._cache.get(cache_key)
    if isinstance(cached, list):
      return cached  # noqa: E111

    base_button = self._get_base_card_template("button")
    theme_styles = self._get_theme_styles(theme)
    button_style = self._get_button_style(theme)

    buttons: CardCollection = []
    if modules.get("feeding"):
      buttons.append(  # noqa: E111
        self._create_feeding_button(
          dog_id,
          base_button,
          button_style,
          theme_styles,
          theme,
        ),
      )

    if modules.get("walk"):
      buttons.extend(  # noqa: E111
        self._create_walk_buttons(
          dog_id,
          base_button,
          button_style,
          theme_styles,
          theme,
        ),
      )

    if modules.get("health"):
      buttons.append(  # noqa: E111
        self._create_health_button(
          dog_id,
          base_button,
          button_style,
          theme_styles,
          theme,
        ),
      )

    result = self._wrap_buttons_layout(buttons, layout)
    if result is None:
      result = buttons  # noqa: E111

    await self._cache.set(cache_key, result)
    return result

  def _gradient_style(self, primary: str, secondary: str) -> CardConfig:  # noqa: E111
    """Return gradient card_mod style with provided colors."""
    return {
      "card_mod": {
        "style": f"""
                    ha-card {{
                        background: linear-gradient(135deg, {primary} 0%, {secondary} 100%);
                        color: white;
                        border-radius: 12px;
                        transition: all 0.3s;
                    }}
                    ha-card:hover {{
                        transform: scale(1.05);
                    }}
                """,  # noqa: E501
      },
    }

  def _get_button_style(self, theme: str) -> CardConfig:  # noqa: E111
    """Return card style based on theme."""
    if theme == "modern":
      return self._gradient_style("#667eea", "#764ba2")  # noqa: E111
    if theme == "playful":
      return {  # noqa: E111
        "card_mod": {
          "style": """
                        ha-card {
                            background: linear-gradient(45deg, #f093fb 0%, #f5576c 100%);
                            color: white;
                            border-radius: 50px;
                            animation: pulse 2s infinite;
                        }
                        @keyframes pulse {
                            0% { box-shadow: 0 0 0 0 rgba(245,87,108,0.7); }
                            70% { box-shadow: 0 0 0 10px rgba(245,87,108,0); }
                            100% { box-shadow: 0 0 0 0 rgba(245,87,108,0); }
                        }
                    """,  # noqa: E501
        },
      }
    return {}

  def _create_feeding_button(  # noqa: E111
    self,
    dog_id: str,
    base_button: CardConfig,
    button_style: CardConfig,
    theme_styles: ThemeStyles,
    theme: str,
  ) -> CardConfig:
    """Create feeding button card."""
    return {
      **base_button,
      **button_style,
      "name": "Feed",
      "icon": "mdi:food-drumstick" if theme != "playful" else "mdi:bone",
      "icon_color": theme_styles["colors"]["accent"],
      "tap_action": {
        "action": "call-service",
        "service": f"{DOMAIN}.add_feeding",
        "service_data": {
          "dog_id": dog_id,
          "meal_type": "regular",
          "amount": DEFAULT_REGULAR_FEEDING_AMOUNT,
        },
      },
    }

  def _create_walk_buttons(  # noqa: E111
    self,
    dog_id: str,
    base_button: CardConfig,
    button_style: CardConfig,
    theme_styles: ThemeStyles,
    theme: str,
  ) -> CardCollection:
    """Create start/end walk buttons."""
    walk_style = (
      self._gradient_style("#00bfa5", "#00acc1") if theme == "modern" else button_style
    )

    cards: CardCollection = []

    start_card: CardConfig = dict(base_button)
    start_card.update(walk_style)
    start_card.update(
      {
        "name": "Start Walk",
        "icon": "mdi:walk",
        "icon_color": theme_styles["colors"]["primary"],
        "tap_action": {
          "action": "call-service",
          "service": f"{DOMAIN}.gps_start_walk",
          "service_data": {"dog_id": dog_id},
        },
      },
    )
    start_wrapper: CardConfig = {
      "type": "conditional",
      "conditions": [
        {"entity": f"binary_sensor.{dog_id}_is_walking", "state": "off"},
      ],
      "card": start_card,
    }
    cards.append(start_wrapper)

    end_card: CardConfig = dict(base_button)
    end_card.update(walk_style)
    end_card.update(
      {
        "name": "End Walk",
        "icon": "mdi:stop",
        "icon_color": "red",
        "tap_action": {
          "action": "call-service",
          "service": f"{DOMAIN}.gps_end_walk",
          "service_data": {"dog_id": dog_id},
        },
      },
    )
    end_wrapper: CardConfig = {
      "type": "conditional",
      "conditions": [
        {"entity": f"binary_sensor.{dog_id}_is_walking", "state": "on"},
      ],
      "card": end_card,
    }
    cards.append(end_wrapper)

    return cards

  def _create_health_button(  # noqa: E111
    self,
    dog_id: str,
    base_button: CardConfig,
    button_style: CardConfig,
    theme_styles: ThemeStyles,
    theme: str,
  ) -> CardConfig:
    """Create health check button."""
    health_style = (
      self._gradient_style("#e91e63", "#f06292") if theme == "modern" else button_style
    )
    hass_language: str | None = getattr(self.hass.config, "language", None)
    translation_lookup = get_cached_component_translation_lookup(
      self.hass,
      hass_language,
    )

    return {
      **base_button,
      **health_style,
      "name": _translated_health_label(
        translation_lookup,
        "health_check_button",
      ),
      "icon": "mdi:heart-pulse",
      "icon_color": theme_styles["colors"]["accent"],
      "tap_action": {
        "action": "call-service",
        "service": f"{DOMAIN}.log_health",
        "service_data": {"dog_id": dog_id},
      },
    }

  def _wrap_buttons_layout(  # noqa: E111
    self,
    buttons: CardCollection,
    layout: str,
  ) -> CardCollection | None:
    """Wrap buttons in layout-specific containers."""
    if layout == "grid":
      return [{"type": "grid", "columns": 3, "cards": buttons}]  # noqa: E111
    if layout == "panels":
      return [{"type": "horizontal-stack", "cards": buttons[:3]}]  # noqa: E111
    return None

  @staticmethod  # noqa: E111
  def _normalise_map_options(  # noqa: E111
    options: MapOptionsInput,
  ) -> MapCardOptions:
    """Return a typed ``MapCardOptions`` payload extracted from ``options``."""

    resolved: MapCardOptions = {
      "zoom": DEFAULT_MAP_ZOOM,
      "default_zoom": DEFAULT_MAP_ZOOM,
      "hours_to_show": DEFAULT_MAP_HOURS_TO_SHOW,
    }

    if not options:
      return resolved  # noqa: E111

    options_mapping: Mapping[str, object]

    if isinstance(options, Mapping):
      filtered_options: dict[str, object] = {}  # noqa: E111
      for key, value in options.items():  # noqa: E111
        if not isinstance(key, str):
          _LOGGER.debug(  # noqa: E111
            "Skipping map option entry with non-string key from mapping: %r",
            key,
          )
          continue  # noqa: E111

        if key not in MAP_OPTION_KEYS:
          _LOGGER.debug(  # noqa: E111
            "Ignoring unsupported map option key '%s' from mapping payload",
            key,
          )
          continue  # noqa: E111

        filtered_options[key] = value

      if not filtered_options:  # noqa: E111
        _LOGGER.debug(
          "Ignoring map options mapping payload without supported entries: %s",
          type(options).__name__,
        )
        return resolved

      options_mapping = filtered_options  # noqa: E111
    elif isinstance(options, Iterable) and not isinstance(options, str | bytes):
      candidate_pairs: list[tuple[str, object]] = []  # noqa: E111
      for item in options:  # noqa: E111
        if isinstance(item, Mapping):
          for key, value in item.items():  # noqa: E111
            if not isinstance(key, str):
              _LOGGER.debug(  # noqa: E111
                "Skipping map option entry with non-string key from mapping: %r",
                key,
              )
              continue  # noqa: E111

            if key not in MAP_OPTION_KEYS:
              _LOGGER.debug(  # noqa: E111
                "Ignoring unsupported map option key '%s' from iterable mapping",
                key,
              )
              continue  # noqa: E111

            candidate_pairs.append((key, value))
          continue  # noqa: E111

        if (
          isinstance(item, Sequence)
          and not isinstance(item, str | bytes)
          and len(item) == 2
        ):
          key, value = item  # noqa: E111
          if isinstance(key, str):  # noqa: E111
            if key not in MAP_OPTION_KEYS:
              _LOGGER.debug(  # noqa: E111
                "Ignoring unsupported map option key '%s' from iterable pair",
                key,
              )
              continue  # noqa: E111

            candidate_pairs.append((key, value))
          else:  # noqa: E111
            _LOGGER.debug(
              "Skipping map option entry with non-string key: %r",
              key,
            )
        else:
          _LOGGER.debug(  # noqa: E111
            "Skipping unsupported map option entry: %s",
            type(
              item,
            ).__name__,
          )

      if not candidate_pairs:  # noqa: E111
        _LOGGER.debug(
          "Ignoring map options iterable payload without usable entries: %s",
          type(options).__name__,
        )
        return resolved

      options_mapping = dict(candidate_pairs)  # noqa: E111
    else:
      _LOGGER.debug(  # noqa: E111
        "Ignoring map options payload with unsupported type: %s",
        type(options).__name__,
      )
      return resolved  # noqa: E111

    def _coerce_int(candidate: object | None) -> int | None:
      """Convert ``candidate`` to ``int`` when possible."""  # noqa: E111

      if candidate is None:  # noqa: E111
        return None
      if isinstance(candidate, bool):  # noqa: E111
        return None
      if isinstance(candidate, int):  # noqa: E111
        return candidate
      if isinstance(candidate, float):  # noqa: E111
        if not isfinite(candidate):
          return None  # noqa: E111
        return int(candidate)
      if isinstance(candidate, str):  # noqa: E111
        stripped = candidate.strip()
        if not stripped:
          return None  # noqa: E111
        try:
          numeric = float(stripped)  # noqa: E111
        except ValueError:
          return None  # noqa: E111
        if not isfinite(numeric):
          return None  # noqa: E111
        return int(numeric)
      return None  # noqa: E111

    zoom_candidate = options_mapping.get("zoom")
    zoom_value = _coerce_int(zoom_candidate)
    if zoom_value is not None:
      resolved_zoom = max(MAP_ZOOM_MIN, min(MAP_ZOOM_MAX, zoom_value))  # noqa: E111
      resolved["zoom"] = resolved_zoom  # noqa: E111

    default_zoom_candidate = options_mapping.get("default_zoom")
    default_zoom_value = _coerce_int(default_zoom_candidate)
    if default_zoom_value is not None:
      resolved_default_zoom = max(  # noqa: E111
        MAP_ZOOM_MIN,
        min(MAP_ZOOM_MAX, default_zoom_value),
      )
      resolved["default_zoom"] = resolved_default_zoom  # noqa: E111
      if zoom_value is None:  # noqa: E111
        resolved["zoom"] = resolved_default_zoom
    elif zoom_value is not None:
      # Mirror the explicitly provided zoom when no default override exists.  # noqa: E114
      resolved["default_zoom"] = resolved["zoom"]  # noqa: E111

    dark_mode = options_mapping.get("dark_mode")
    if isinstance(dark_mode, bool):
      resolved["dark_mode"] = dark_mode  # noqa: E111
    elif isinstance(dark_mode, int | float):
      resolved["dark_mode"] = bool(dark_mode)  # noqa: E111
    elif isinstance(dark_mode, str):
      lowered = dark_mode.strip().casefold()  # noqa: E111
      if lowered in {"1", "true", "yes", "on"}:  # noqa: E111
        resolved["dark_mode"] = True
      elif lowered in {"0", "false", "no", "off"}:  # noqa: E111
        resolved["dark_mode"] = False

    hours_candidate = options_mapping.get("hours_to_show")
    hours_value = _coerce_int(hours_candidate)
    if hours_value is not None:
      resolved["hours_to_show"] = max(  # noqa: E111
        MAP_HISTORY_MIN_HOURS,
        min(MAP_HISTORY_MAX_HOURS, hours_value),
      )

    return resolved

  async def get_map_card_template(  # noqa: E111
    self,
    dog_id: str,
    options: MapOptionsInput = None,
    theme: str = "modern",
  ) -> CardConfig:
    """Get themed GPS map card template.

    Args:
        dog_id: Dog identifier
        options: Map display options
        theme: Visual theme

    Returns:
        Map card template with theme styling
    """
    resolved_options = self._normalise_map_options(options)
    self._get_theme_styles(theme)

    resolved_zoom = resolved_options.get("zoom")
    resolved_default_zoom = resolved_options.get("default_zoom")

    if resolved_zoom is None and resolved_default_zoom is not None:
      resolved_zoom = resolved_default_zoom  # noqa: E111
    elif resolved_zoom is not None and resolved_default_zoom is None:
      resolved_default_zoom = resolved_zoom  # noqa: E111

    final_zoom = resolved_zoom if resolved_zoom is not None else DEFAULT_MAP_ZOOM
    final_default_zoom = (
      resolved_default_zoom if resolved_default_zoom is not None else final_zoom
    )

    dark_mode_override = resolved_options.get("dark_mode")
    dark_mode_enabled = (
      theme == "dark" if dark_mode_override is None else dark_mode_override
    )

    template: CardConfig = {
      **self._get_base_card_template("map"),
      "entities": [f"device_tracker.{dog_id}_location"],
      "default_zoom": final_default_zoom,
      "zoom": final_zoom,
      "dark_mode": dark_mode_enabled,
      "hours_to_show": resolved_options.get(
        "hours_to_show",
        DEFAULT_MAP_HOURS_TO_SHOW,
      ),
    }

    # Add theme-specific map styling
    if theme == "modern":
      card_mod = CardModConfig(  # noqa: E111
        style="""
                    ha-card {
                        border-radius: 16px;
                        overflow: hidden;
                    }
                """,
      )
      template["card_mod"] = card_mod  # noqa: E111
    elif theme == "playful":
      card_mod = CardModConfig(  # noqa: E111
        style="""
                    ha-card {
                        border-radius: 24px;
                        border: 4px solid #4ECDC4;
                    }
                """,
      )
      template["card_mod"] = card_mod  # noqa: E111

    return template

  async def get_statistics_card_template(  # noqa: E111
    self,
    dog_id: str,
    dog_name: str,
    modules: DogModulesConfig,
    theme: str = "modern",
  ) -> CardConfig:
    """Get themed statistics card template.

    Args:
        dog_id: Dog identifier
        dog_name: Dog name
        modules: Enabled modules
        theme: Visual theme

    Returns:
        Statistics card template
    """
    theme_styles = self._get_theme_styles(theme)
    hass_language: str | None = getattr(self.hass.config, "language", None)
    translation_lookup = await async_get_component_translation_lookup(
      self.hass,
      hass_language,
    )

    # Build statistics based on enabled modules
    stats_content = f"## 📊 {dog_name} Statistics\n\n"

    if modules.get("feeding"):
      stats_content += f"""
### 🍖 Feeding
- **Today's Meals**: {{{{ states('sensor.{dog_id}_meals_today') }}}}
- **Daily Amount**: {{{{ states('sensor.{dog_id}_daily_food_consumed') }}}}g
- **Schedule Adherence**: {{{{ states('sensor.{dog_id}_feeding_schedule_adherence') }}}}%
"""  # noqa: E111, E501

    if modules.get("walk"):
      stats_content += f"""
### 🚶 Walking
- **Daily Walk Time**: {{{{ states('sensor.{dog_id}_daily_walk_time') }}}} min
- **Daily Distance**: {{{{ states('sensor.{dog_id}_daily_walk_distance') }}}} km
- **Walk Goal**: {{{{ states('sensor.{dog_id}_walk_goal_progress') }}}}%
"""  # noqa: E111

    if modules.get("health"):
      stats_content += _translated_health_template(  # noqa: E111
        translation_lookup,
        "statistics_health_section",
        dog_id=dog_id,
      )

    card_mod = self._card_mod(theme_styles)
    template: CardConfig = {
      "type": "markdown",
      "content": stats_content,
      "card_mod": card_mod,
    }

    return template

  async def get_statistics_graph_template(  # noqa: E111
    self,
    title: str,
    entities: Sequence[str],
    stat_types: Sequence[str],
    *,
    days_to_show: int,
    theme: str = "modern",
  ) -> CardConfig | None:
    """Return a typed statistics-graph card for analytics dashboards."""

    if not entities:
      return None  # noqa: E111

    theme_styles = self._get_theme_styles(theme)
    card_mod = self._card_mod(theme_styles)

    template: CardConfig = {
      "type": "statistics-graph",
      "title": title,
      "entities": list(entities),
      "stat_types": list(stat_types),
      "days_to_show": days_to_show,
    }

    if card_mod:
      template["card_mod"] = card_mod  # noqa: E111

    return template

  def get_statistics_summary_template(  # noqa: E111
    self,
    dogs: Sequence[RawDogConfig],
    theme: str = "modern",
    *,
    coordinator_statistics: CoordinatorStatisticsPayload | JSONMapping | None = None,
    service_execution_metrics: CoordinatorRejectionMetrics | JSONMapping | None = None,
    service_guard_metrics: HelperManagerGuardMetrics | JSONMapping | None = None,
  ) -> CardConfig:
    """Return a summary markdown card for analytics dashboards."""

    typed_dogs = coerce_dog_configs(dogs)

    module_counts = {
      MODULE_FEEDING: 0,
      MODULE_WALK: 0,
      MODULE_HEALTH: 0,
      MODULE_GPS: 0,
      MODULE_NOTIFICATIONS: 0,
    }

    for dog in typed_dogs:
      modules = coerce_dog_modules_config(dog.get("modules"))  # noqa: E111
      for module_name in module_counts:  # noqa: E111
        if modules.get(module_name):
          module_counts[module_name] += 1  # noqa: E111

    hass_language: str | None = getattr(self.hass.config, "language", None)
    translation_lookup = get_cached_component_translation_lookup(
      self.hass,
      hass_language,
    )

    statistics_header = _translated_statistics_label(
      translation_lookup,
      "statistics_header",
    )
    dogs_managed_label = _translated_statistics_label(
      translation_lookup,
      "dogs_managed",
    )
    active_modules_label = _translated_statistics_label(
      translation_lookup,
      "active_modules",
    )
    module_labels = {
      MODULE_FEEDING: _translated_statistics_label(
        translation_lookup,
        "module_feeding",
      ),
      MODULE_WALK: _translated_statistics_label(translation_lookup, "module_walks"),
      MODULE_HEALTH: _translated_statistics_label(translation_lookup, "module_health"),
      MODULE_GPS: _translated_statistics_label(translation_lookup, "module_gps"),
      MODULE_NOTIFICATIONS: _translated_statistics_label(
        translation_lookup,
        "module_notifications",
      ),
    }
    last_updated_label = _translated_statistics_label(
      translation_lookup,
      "last_updated",
    )

    content_lines = [
      f"## {statistics_header}",
      "",
      f"**{dogs_managed_label}:** {len(typed_dogs)}",
      "",
      f"**{active_modules_label}:**",
    ]

    for module_name, count in module_counts.items():
      content_lines.append(f"- {module_labels[module_name]}: {count}")  # noqa: E111

    content_lines.extend(
      [
        "",
        ("*" + last_updated_label + ": {{ now().strftime('%Y-%m-%d %H:%M') }}*"),
      ],
    )

    def _coerce_rejection_metrics(
      payload: JSONMapping | CoordinatorRejectionMetrics | None,
    ) -> CoordinatorRejectionMetrics | None:
      if payload is None:  # noqa: E111
        return None

      if isinstance(payload, Mapping):  # noqa: E111
        nested = payload.get("rejection_metrics")
        metrics_source = (
          nested
          if isinstance(
            nested,
            Mapping,
          )
          else payload
        )

        metrics = default_rejection_metrics()
        merge_rejection_metric_values(metrics, metrics_source)
        return metrics

      return None  # noqa: E111

    def _coerce_guard_metrics(
      payload: JSONMapping | HelperManagerGuardMetrics | None,
    ) -> HelperManagerGuardMetrics | None:
      if payload is None:  # noqa: E111
        return None

      if isinstance(payload, Mapping):  # noqa: E111

        def _int_value(value: JSONValue | object) -> int:
          if isinstance(value, bool):  # noqa: E111
            return int(value)
          if isinstance(value, int):  # noqa: E111
            return value
          if isinstance(value, float):  # noqa: E111
            return int(value)
          if isinstance(value, str):  # noqa: E111
            try:
              return int(float(value))  # noqa: E111
            except ValueError:
              return 0  # noqa: E111
          return 0  # noqa: E111

        reasons_payload: dict[str, int] = {}
        raw_reasons = payload.get("reasons")
        if isinstance(raw_reasons, Mapping):
          reasons_payload = {  # noqa: E111
            str(key): _int_value(value)
            for key, value in raw_reasons.items()
            if isinstance(key, str)
          }

        raw_last_results = payload.get("last_results")
        last_results_payload = normalise_guard_history(
          raw_last_results,
        )

        return {
          "executed": _int_value(payload.get("executed")),
          "skipped": _int_value(payload.get("skipped")),
          "reasons": reasons_payload,
          "last_results": last_results_payload,
        }

      return None  # noqa: E111

    coordinator_metrics: CoordinatorRejectionMetrics | None = None
    if isinstance(coordinator_statistics, Mapping):
      raw_metrics = coordinator_statistics.get("rejection_metrics")  # noqa: E111
      if isinstance(raw_metrics, Mapping):  # noqa: E111
        metrics_source = cast(
          JSONMapping | CoordinatorResilienceSummary | None,
          raw_metrics,
        )
        coordinator_metrics = derive_rejection_metrics(metrics_source)

    service_metrics = _coerce_rejection_metrics(service_execution_metrics)
    guard_metrics = _coerce_guard_metrics(service_guard_metrics)

    def _format_resilience_section(
      metrics_payload: CoordinatorRejectionMetrics,
      *,
      guard_payload: HelperManagerGuardMetrics | None = None,
    ) -> list[str]:
      lines: list[str] = []  # noqa: E111

      last_rejection_value = metrics_payload["last_rejection_time"]  # noqa: E111
      has_rejection_history = (  # noqa: E111
        metrics_payload["rejected_call_count"] > 0
        or metrics_payload["rejection_breaker_count"] > 0
        or last_rejection_value is not None
      )

      rejection_rate = metrics_payload["rejection_rate"]  # noqa: E111
      if (  # noqa: E111
        has_rejection_history
        and rejection_rate is not None
        and isfinite(rejection_rate)
      ):
        rate_display = f"{rejection_rate * 100:.2f}%"
      else:  # noqa: E111
        rate_display = _translated_statistics_fallback(
          translation_lookup,
          "no_rejection_rate",
          "n/a",
        )

      if last_rejection_value is not None:  # noqa: E111
        try:
          last_rejection_iso = datetime.fromtimestamp(  # noqa: E111
            float(last_rejection_value),
            tz=UTC,
          ).isoformat()
        except Exception:  # pragma: no cover - defensive guard
          last_rejection_iso = str(last_rejection_value)  # noqa: E111
      else:  # noqa: E111
        last_rejection_iso = _translated_statistics_fallback(
          translation_lookup,
          "no_last_rejection",
          "never",
        )

      lines.extend(  # noqa: E111
        [
          (
            "- "
            + _translated_statistics_label(translation_lookup, "rejected_calls")
            + f": {metrics_payload['rejected_call_count']}"
          ),
          (
            "- "
            + _translated_statistics_label(
              translation_lookup,
              "rejecting_breakers",
            )
            + f": {metrics_payload['rejection_breaker_count']}"
          ),
          (
            "- "
            + _translated_statistics_label(translation_lookup, "rejection_rate")
            + f": {rate_display}"
          ),
          (
            "- "
            + _translated_statistics_label(translation_lookup, "last_rejection")
            + f": {last_rejection_iso}"
          ),
        ],
      )

      breaker_label_value = (  # noqa: E111
        metrics_payload["last_rejection_breaker_name"]
        or metrics_payload["last_rejection_breaker_id"]
      )
      if breaker_label_value:  # noqa: E111
        lines.append(
          "- "
          + _translated_statistics_label(
            translation_lookup,
            "last_rejecting_breaker",
          )
          + f": {breaker_label_value}",
        )

      breaker_name_lists = {  # noqa: E111
        _translated_statistics_label(
          translation_lookup,
          "open_breaker_names",
        ): metrics_payload["open_breakers"],
        _translated_statistics_label(
          translation_lookup,
          "half_open_breaker_names",
        ): metrics_payload["half_open_breakers"],
        _translated_statistics_label(
          translation_lookup,
          "unknown_breaker_names",
        ): metrics_payload["unknown_breakers"],
        _translated_statistics_label(
          translation_lookup,
          "rejection_breaker_names",
        ): metrics_payload["rejection_breakers"],
      }

      for label, breaker_names in breaker_name_lists.items():  # noqa: E111
        lines.append(
          f"- {label}: {_format_breaker_list(breaker_names, translation_lookup)}",
        )

      breaker_lists = {  # noqa: E111
        _translated_statistics_label(
          translation_lookup,
          "open_breaker_ids",
        ): metrics_payload["open_breaker_ids"],
        _translated_statistics_label(
          translation_lookup,
          "half_open_breaker_ids",
        ): metrics_payload["half_open_breaker_ids"],
        _translated_statistics_label(
          translation_lookup,
          "unknown_breaker_ids",
        ): metrics_payload["unknown_breaker_ids"],
        _translated_statistics_label(
          translation_lookup,
          "rejection_breaker_ids",
        ): metrics_payload["rejection_breaker_ids"],
      }

      for label, breaker_ids in breaker_lists.items():  # noqa: E111
        lines.append(
          f"- {label}: {_format_breaker_list(breaker_ids, translation_lookup)}",
        )

      if guard_payload is not None:  # noqa: E111
        guard_header = _translated_statistics_label(
          translation_lookup,
          "guard_metrics_header",
        )
        lines.append(f"- {guard_header}:")

        executed_label = _translated_statistics_label(
          translation_lookup,
          "guard_executed",
        )
        lines.append(
          f"  - {executed_label}: {guard_payload['executed']}",
        )

        skipped_label = _translated_statistics_label(
          translation_lookup,
          "guard_skipped",
        )
        lines.append(
          f"  - {skipped_label}: {guard_payload['skipped']}",
        )

        reasons_label = _translated_statistics_label(
          translation_lookup,
          "guard_reasons",
        )
        lines.append(f"  - {reasons_label}:")
        lines.extend(
          f"    - {reason_line}"
          for reason_line in _format_guard_reasons(
            guard_payload["reasons"],
            translation_lookup,
          )
        )

        results_label = _translated_statistics_label(
          translation_lookup,
          "guard_last_results",
        )
        lines.append(f"  - {results_label}:")
        lines.extend(
          f"    - {result_line}"
          for result_line in _format_guard_results(
            guard_payload["last_results"],
            translation_lookup,
          )
        )

      return lines  # noqa: E111

    metrics_sections: list[
      tuple[
        str,
        CoordinatorRejectionMetrics,
        HelperManagerGuardMetrics | None,
      ]
    ] = []
    if coordinator_metrics is not None:
      metrics_sections.append(  # noqa: E111
        ("coordinator_resilience_label", coordinator_metrics, None),
      )
    if service_metrics is not None:
      metrics_sections.append(  # noqa: E111
        ("service_resilience_label", service_metrics, guard_metrics),
      )

    if metrics_sections:
      resilience_header = _translated_statistics_label(  # noqa: E111
        translation_lookup,
        "resilience_metrics_header",
      )
      content_lines.append("")  # noqa: E111
      content_lines.append(f"### {resilience_header}")  # noqa: E111

      for index, (label_key, metrics_payload, guard_payload) in enumerate(  # noqa: E111
        metrics_sections,
      ):
        if index > 0:
          content_lines.append("")  # noqa: E111
        section_label = _translated_statistics_label(
          translation_lookup,
          label_key,
        )
        content_lines.append(f"**{section_label}:**")
        content_lines.extend(
          _format_resilience_section(
            metrics_payload,
            guard_payload=guard_payload,
          ),
        )

    theme_styles = self._get_theme_styles(theme)

    summary_title = _translated_statistics_label(
      translation_lookup,
      "summary_card_title",
    )

    card_mod = self._card_mod(theme_styles)
    template: CardConfig = {
      "type": "markdown",
      "title": summary_title,
      "content": "\n".join(content_lines),
      "card_mod": card_mod,
    }

    return template

  def get_diagnostics_guard_metrics_card_template(  # noqa: E111
    self,
    theme: str = "modern",
  ) -> CardConfig:
    """Return a Lovelace markdown card for service guard metrics."""

    theme_styles = self._get_theme_styles(theme)
    card_mod = self._card_mod(theme_styles)

    content = (
      "{% set service = state_attr('sensor.pawcontrol_statistics',"
      " 'service_execution') or {} %}\n"
      "{% set guard = service.get('guard_metrics', {}) %}\n"
      "## 🛡️ Guard metrics\n"
      "- **Executed:** {{ guard.get('executed', 0) }}\n"
      "- **Skipped:** {{ guard.get('skipped', 0) }}\n"
      "- **Reasons:** {{ guard.get('reasons', {}) | tojson }}\n"
      "- **Last results:** {{ guard.get('last_results', []) | tojson }}\n"
    )

    template: CardConfig = {
      "type": "markdown",
      "title": "Service guard metrics",
      "content": content,
      "card_mod": card_mod,
    }

    return template

  def get_notification_rejection_metrics_card_template(  # noqa: E111
    self,
    theme: str = "modern",
  ) -> CardConfig:
    """Return a Lovelace markdown card for notification rejection metrics."""

    theme_styles = self._get_theme_styles(theme)
    card_mod = self._card_mod(theme_styles)

    content = (
      "{% set notifications = state_attr('sensor.pawcontrol_diagnostics',"
      " 'notifications') or {} %}\n"
      "{% set rejection = notifications.get('rejection_metrics', {}) %}\n"
      "## 🔔 Notification failures\n"
      "- **Total services:** {{ rejection.get('total_services', 0) }}\n"
      "- **Total failures:** {{ rejection.get('total_failures', 0) }}\n"
      "- **Services with failures:**"
      " {{ rejection.get('services_with_failures', []) | tojson }}\n"
      "- **Last error reasons:**"
      " {{ rejection.get('service_last_error_reasons', {}) | tojson }}\n"
    )

    template: CardConfig = {
      "type": "markdown",
      "title": "Notification rejection metrics",
      "content": content,
      "card_mod": card_mod,
    }

    return template

  def get_guard_notification_error_metrics_card_template(  # noqa: E111
    self,
    theme: str = "modern",
  ) -> CardConfig:
    """Return a Lovelace markdown card for combined guard error metrics."""

    theme_styles = self._get_theme_styles(theme)
    card_mod = self._card_mod(theme_styles)

    content = (
      "{% set metrics = state_attr('sensor.pawcontrol_diagnostics',"
      " 'guard_notification_error_metrics') or {} %}\n"
      "{% set guard = metrics.get('guard', {}) %}\n"
      "{% set notifications = metrics.get('notifications', {}) %}\n"
      "## 🚨 Combined error metrics\n"
      "- **Available:** {{ metrics.get('available', false) }}\n"
      "- **Total errors:** {{ metrics.get('total_errors', 0) }}\n"
      "- **Guard skipped:** {{ guard.get('skipped', 0) }}\n"
      "- **Guard reasons:** {{ guard.get('reasons', {}) | tojson }}\n"
      "- **Notification failures:** {{ notifications.get('total_failures', 0) }}\n"
      "- **Classified errors:** {{ metrics.get('classified_errors', {}) | tojson }}\n"
    )

    template: CardConfig = {
      "type": "markdown",
      "title": "Guard + notification errors",
      "content": content,
      "card_mod": card_mod,
    }

    return template

  async def get_notification_settings_card_template(  # noqa: E111
    self,
    dog_id: str,
    dog_name: str,
    entities: Sequence[str],
    theme: str = "modern",
  ) -> CardConfig | None:
    """Return the notification control entities card."""

    if not entities:
      return None  # noqa: E111

    theme_styles = self._get_theme_styles(theme)
    hass_language: str | None = getattr(self.hass.config, "language", None)
    translation_lookup = await async_get_component_translation_lookup(
      self.hass,
      hass_language,
    )
    title_text = _translated_notification_template(
      translation_lookup,
      "settings_title",
      dog_name=dog_name,
    )

    card_mod = self._card_mod(theme_styles)
    template: CardConfig = {
      "type": "entities",
      "title": f"🔔 {title_text}",
      "entities": list(entities),
      "state_color": True,
      "card_mod": card_mod,
    }

    return template

  async def get_notifications_overview_card_template(  # noqa: E111
    self,
    dog_id: str,
    dog_name: str,
    theme: str = "modern",
  ) -> CardConfig:
    """Return a markdown overview for the notification dashboard."""

    theme_styles = self._get_theme_styles(theme)
    card_mod = self._card_mod(theme_styles)
    hass_language: str | None = getattr(self.hass.config, "language", None)
    translation_lookup = await async_get_component_translation_lookup(
      self.hass,
      hass_language,
    )

    notifications_state = self.hass.states.get(
      "sensor.pawcontrol_notifications",
    )
    metrics, per_dog = self._normalise_notifications_state(
      notifications_state,
    )

    default_overview: NotificationDogOverview = {
      "sent_today": 0,
      "quiet_hours_active": False,
      "channels": [],
    }
    dog_overview = per_dog.get(dog_id, default_overview)

    sent_today = dog_overview.get("sent_today", 0)
    failed_deliveries = metrics.get("notifications_failed", 0)
    quiet_hours_active = dog_overview.get("quiet_hours_active", False)
    channels = dog_overview.get("channels", [])
    last_notification = dog_overview.get("last_notification")

    quiet_hours_display = "✅" if quiet_hours_active else "❌"

    overview_heading = _translated_notification_template(
      translation_lookup,
      "overview_heading",
      dog_name=dog_name,
    )
    content_lines = [
      f"## 🔔 {overview_heading}",
      "",
      (
        "**"
        + _translated_notification_label(translation_lookup, "sent_today")
        + f":** {sent_today}"
      ),
      (
        "**"
        + _translated_notification_label(translation_lookup, "failed_deliveries")
        + f":** {failed_deliveries}"
      ),
      (
        "**"
        + _translated_notification_label(translation_lookup, "quiet_hours_active")
        + f":** {quiet_hours_display}"
      ),
      "",
      "### " + _translated_notification_label(translation_lookup, "preferred_channels"),
    ]

    if channels:
      content_lines.extend(f"• {channel.capitalize()}" for channel in channels)  # noqa: E111
    else:
      content_lines.append(  # noqa: E111
        "• "
        + _translated_notification_fallback(
          translation_lookup,
          "default_channels",
          "Using default integration channels",
        ),
      )

    content_lines.append("")
    content_lines.append(
      "### "
      + _translated_notification_label(translation_lookup, "recent_notification"),
    )
    if last_notification:
      notification_type_raw = last_notification.get("type")  # noqa: E111
      notification_type = (  # noqa: E111
        str(notification_type_raw)
        if notification_type_raw not in (None, "")
        else _translated_notification_fallback(
          translation_lookup,
          "unknown_value",
          "unknown",
        )
      )
      priority_raw = last_notification.get("priority", "normal")  # noqa: E111
      priority = (  # noqa: E111
        str(priority_raw).capitalize()
        if priority_raw not in (None, "")
        else _translated_notification_fallback(
          translation_lookup,
          "default_priority",
          "Normal",
        )
      )
      sent_at_raw = last_notification.get("sent_at", "unknown")  # noqa: E111
      sent_at = (  # noqa: E111
        str(sent_at_raw)
        if sent_at_raw not in (None, "")
        else _translated_notification_fallback(
          translation_lookup,
          "unknown_value",
          "unknown",
        )
      )

      content_lines.extend(  # noqa: E111
        [
          (
            "- **"
            + _translated_notification_label(translation_lookup, "type")
            + f":** {notification_type}"
          ),
          (
            "- **"
            + _translated_notification_label(translation_lookup, "priority")
            + f":** {priority}"
          ),
          (
            "- **"
            + _translated_notification_label(translation_lookup, "sent")
            + f":** {sent_at}"
          ),
        ],
      )
    else:
      content_lines.append(  # noqa: E111
        _translated_notification_fallback(
          translation_lookup,
          "no_notifications",
          "No notifications recorded for this dog yet.",
        ),
      )

    content = "\n".join(content_lines)

    return {
      "type": "markdown",
      "content": content,
      "card_mod": card_mod,
    }

  async def get_notifications_actions_card_template(  # noqa: E111
    self,
    dog_id: str,
    theme: str = "modern",
  ) -> CardConfig:
    """Return quick action buttons for notification workflows."""

    theme_styles = self._get_theme_styles(theme)
    base_button = self._get_base_card_template("button")
    hass_language: str | None = getattr(self.hass.config, "language", None)
    translation_lookup = await async_get_component_translation_lookup(
      self.hass,
      hass_language,
    )

    buttons: CardCollection = [
      {
        **base_button,
        "name": _translated_notification_label(
          translation_lookup,
          "send_test_notification",
        ),
        "icon": "mdi:bell-check",
        "tap_action": {
          "action": "call-service",
          "service": f"{DOMAIN}.send_notification",
          "service_data": {
            "dog_id": dog_id,
            "notification_type": "system_info",
            "title": _translated_notification_fallback(
              translation_lookup,
              "diagnostics_title",
              "PawControl Diagnostics",
            ),
            "message": _translated_notification_fallback(
              translation_lookup,
              "diagnostics_message",
              "Test notification from dashboard",
            ),
          },
        },
      },
      {
        **base_button,
        "name": _translated_notification_label(
          translation_lookup,
          "reset_quiet_hours",
        ),
        "icon": "mdi:weather-night",
        "tap_action": {
          "action": "call-service",
          "service": f"{DOMAIN}.configure_alerts",
          "service_data": {
            "dog_id": dog_id,
            "feeding_alerts": True,
            "walk_alerts": True,
            "health_alerts": True,
            "gps_alerts": True,
          },
        },
      },
    ]

    card_mod = self._card_mod(theme_styles)
    template: CardConfig = {
      "type": "horizontal-stack",
      "cards": buttons,
      "card_mod": card_mod,
    }

    return template

  async def get_feeding_schedule_template(  # noqa: E111
    self,
    dog_id: str,
    theme: str = "modern",
  ) -> CardConfig:
    """Get themed feeding schedule template.

    Args:
        dog_id: Dog identifier
        theme: Visual theme

    Returns:
        Feeding schedule card template
    """
    theme_styles = self._get_theme_styles(theme)
    hass_language: str | None = getattr(self.hass.config, "language", None)
    translation_lookup = await async_get_component_translation_lookup(
      self.hass,
      hass_language,
    )
    schedule_label = _translated_feeding_label(
      translation_lookup,
      "feeding_schedule",
    )

    template: CardConfig
    if theme == "modern":
      # Use a clean timeline view  # noqa: E114
      card_mod = self._card_mod(theme_styles)  # noqa: E111
      template = {  # noqa: E111
        "type": "custom:scheduler-card",
        "title": f"🍽️ {schedule_label}",
        "discover_existing": False,
        "standard_configuration": True,
        "entities": [f"sensor.{dog_id}_feeding_schedule"],
        "card_mod": card_mod,
      }
    elif theme == "playful":
      # Use colorful meal buttons  # noqa: E114
      template = await self.get_feeding_controls_template(dog_id, theme)  # noqa: E111
    else:
      # Minimal text-based schedule  # noqa: E114
      template = {  # noqa: E111
        "type": "entities",
        "title": schedule_label,
        "entities": [
          f"sensor.{dog_id}_breakfast_time",
          f"sensor.{dog_id}_lunch_time",
          f"sensor.{dog_id}_dinner_time",
        ],
      }

    return template

  async def get_feeding_controls_template(  # noqa: E111
    self,
    dog_id: str,
    theme: str = "modern",
  ) -> CardConfig:
    """Get themed feeding control buttons template.

    Args:
        dog_id: Dog identifier
        theme: Visual theme

    Returns:
        Feeding controls template
    """
    base_button = self._get_base_card_template("button")
    self._get_theme_styles(theme)
    hass_language: str | None = getattr(self.hass.config, "language", None)
    translation_lookup = await async_get_component_translation_lookup(
      self.hass,
      hass_language,
    )

    meal_types = [
      (
        "breakfast",
        _translated_feeding_label(translation_lookup, "meal_breakfast"),
        "mdi:weather-sunny",
        "#FFA726",
      ),
      (
        "lunch",
        _translated_feeding_label(translation_lookup, "meal_lunch"),
        "mdi:weather-partly-cloudy",
        "#66BB6A",
      ),
      (
        "dinner",
        _translated_feeding_label(translation_lookup, "meal_dinner"),
        "mdi:weather-night",
        "#5C6BC0",
      ),
      (
        "snack",
        _translated_feeding_label(translation_lookup, "meal_snack"),
        "mdi:cookie",
        "#EC407A",
      ),
    ]

    buttons: CardCollection = []
    for meal_type, name, icon, color in meal_types:
      button_style = {}  # noqa: E111

      if theme == "modern":  # noqa: E111
        button_style = {
          "card_mod": {
            "style": f"""
                            ha-card {{
                                background: linear-gradient(135deg, {color} 0%, {color}CC 100%);
                                color: white;
                                border-radius: 12px;
                            }}
                        """,  # noqa: E501
          },
        }
      elif theme == "playful":  # noqa: E111
        button_style = {
          "card_mod": {
            "style": f"""
                            ha-card {{
                                background: {color};
                                color: white;
                                border-radius: 50%;
                                width: 80px;
                                height: 80px;
                                animation: bounce 1s infinite;
                            }}
                            @keyframes bounce {{
                                0%, 100% {{ transform: translateY(0); }}
                                50% {{ transform: translateY(-10px); }}
                            }}
                        """,
          },
        }

      buttons.append(  # noqa: E111
        {
          **base_button,
          **button_style,
          "name": name,
          "icon": icon,
          "tap_action": {
            "action": "call-service",
            "service": f"{DOMAIN}.add_feeding",
            "service_data": {
              "dog_id": dog_id,
              "meal_type": meal_type,
              "amount": DEFAULT_REGULAR_FEEDING_AMOUNT,
            },
          },
        },
      )

    # Group buttons based on theme
    if theme == "playful":
      # Circular arrangement  # noqa: E114
      return {  # noqa: E111
        "type": "horizontal-stack",
        "cards": buttons,
      }
    # Grid arrangement
    grouped_buttons: CardCollection = []
    for i in range(0, len(buttons), 2):
      button_pair = buttons[i : i + 2]  # noqa: E111
      grouped_buttons.append(  # noqa: E111
        {
          "type": "horizontal-stack",
          "cards": button_pair,
        },
      )

    return {
      "type": "vertical-stack",
      "cards": grouped_buttons,
    }

  async def get_health_charts_template(  # noqa: E111
    self,
    dog_id: str,
    theme: str = "modern",
  ) -> CardConfig:
    """Get themed health charts template.

    Args:
        dog_id: Dog identifier
        theme: Visual theme

    Returns:
        Health charts template
    """
    theme_styles = self._get_theme_styles(theme)
    hass_language: str | None = getattr(self.hass.config, "language", None)
    translation_lookup = await async_get_component_translation_lookup(
      self.hass,
      hass_language,
    )

    template: CardConfig
    if theme in ["modern", "dark"]:
      # Use advanced graph card  # noqa: E114
      card_mod = self._card_mod(theme_styles)  # noqa: E111
      template = {  # noqa: E111
        "type": "custom:mini-graph-card",
        "name": _translated_health_label(translation_lookup, "health_metrics"),
        "entities": [
          {
            "entity": f"sensor.{dog_id}_weight",
            "name": _translated_health_label(translation_lookup, "weight"),
            "color": theme_styles["colors"]["primary"],
          },
          {
            "entity": f"sensor.{dog_id}_health_score",
            "name": _translated_health_label(translation_lookup, "health_score"),
            "color": theme_styles["colors"]["accent"],
            "y_axis": "secondary",
          },
        ],
        "hours_to_show": 168,  # 1 week
        "points_per_hour": 0.5,
        "line_width": 3,
        "animate": True,
        "show": {
          "labels": True,
          "points": True,
          "legend": True,
          "average": True,
          "extrema": True,
        },
        "card_mod": card_mod,
      }
    elif theme == "playful":
      # Use colorful gauge cards  # noqa: E114
      template = {  # noqa: E111
        "type": "horizontal-stack",
        "cards": [
          {
            "type": "gauge",
            "entity": f"sensor.{dog_id}_health_score",
            "name": _translated_health_label(translation_lookup, "health_gauge"),
            "min": 0,
            "max": 100,
            "severity": {
              "green": 70,
              "yellow": 40,
              "red": 0,
            },
            "card_mod": {
              "style": """
                                ha-card {
                                    background: linear-gradient(45deg, #FF6B6B, #4ECDC4);
                                    border-radius: 50%;
                                }
                            """,  # noqa: E501
            },
          },
          {
            "type": "gauge",
            "entity": f"sensor.{dog_id}_activity_level",
            "name": _translated_health_label(translation_lookup, "activity"),
            "min": 0,
            "max": 100,
            "severity": {
              "green": 60,
              "yellow": 30,
              "red": 0,
            },
            "card_mod": {
              "style": """
                                ha-card {
                                    background: linear-gradient(45deg, #4ECDC4, #FFE66D);
                                    border-radius: 50%;
                                }
                            """,  # noqa: E501
            },
          },
        ],
      }
    else:
      # Minimal line graph  # noqa: E114
      template = {  # noqa: E111
        "type": "history-graph",
        "title": _translated_health_label(translation_lookup, "health_trends"),
        "entities": [
          f"sensor.{dog_id}_weight",
          f"sensor.{dog_id}_health_score",
        ],
        "hours_to_show": 168,
      }

    return template

  async def get_timeline_template(  # noqa: E111
    self,
    dog_id: str,
    dog_name: str,
    theme: str = "modern",
  ) -> CardConfig:
    """Get activity timeline template.

    Args:
        dog_id: Dog identifier
        dog_name: Dog name
        theme: Visual theme

    Returns:
        Timeline template
    """
    theme_styles = self._get_theme_styles(theme)
    hass_language: str | None = getattr(self.hass.config, "language", None)
    translation_lookup = await async_get_component_translation_lookup(
      self.hass,
      hass_language,
    )
    last_health_label = _translated_health_label(
      translation_lookup,
      "timeline_last_health_check",
    )

    timeline_content = f"""
## 📅 {dog_name}'s Activity Timeline

### Today
{{{{ states.sensor.{dog_id}_last_activity.attributes.timeline | default('No activities yet') }}}}

### Recent Events
- **Last Fed**: {{{{ states('sensor.{dog_id}_last_fed') }}}}
- **Last Walk**: {{{{ states('sensor.{dog_id}_last_walk') }}}}
- **{last_health_label}**: {{{{ states('sensor.{dog_id}_last_health_check') }}}}
"""  # noqa: E501

    card_mod = self._card_mod(theme_styles)
    template: CardConfig = {
      "type": "markdown",
      "content": timeline_content,
      "card_mod": card_mod,
    }

    return template

  async def get_weather_status_card_template(  # noqa: E111
    self,
    dog_id: str,
    dog_name: str,
    theme: str = "modern",
    compact: bool = False,
  ) -> CardConfig:
    """Get weather status card template for dog health monitoring.

    Args:
        dog_id: Dog identifier
        dog_name: Dog display name
        theme: Visual theme to apply
        compact: Whether to use compact layout

    Returns:
        Weather status card template with health indicators
    """
    cache_key = f"weather_status_{dog_id}_{theme}_{compact}"
    cached = await self._cache.get(cache_key)
    if isinstance(cached, dict):
      return cached  # noqa: E111

    theme_styles = self._get_theme_styles(theme)
    weather_icon = self._get_weather_icon(theme)
    hass_language: str | None = getattr(self.hass.config, "language", None)
    translation_lookup = await async_get_component_translation_lookup(
      self.hass,
      hass_language,
    )

    template: CardConfig
    if compact:
      # Compact card for mobile/small spaces  # noqa: E114
      card_mod = self._card_mod(theme_styles)  # noqa: E111
      template = {  # noqa: E111
        "type": "custom:mushroom-entity",
        "entity": f"sensor.{dog_id}_weather_health_score",
        "name": _translated_health_template(
          translation_lookup,
          "weather_health_compact_name",
          icon=weather_icon,
        ),
        "icon": "mdi:weather-partly-cloudy",
        "icon_color": self._get_weather_color_by_score(theme),
        "secondary_info": "state",
        "tap_action": {
          "action": "more-info",
        },
        "card_mod": card_mod,
      }
    else:
      # Full weather status card  # noqa: E114
      entities = [  # noqa: E111
        {
          "entity": f"sensor.{dog_id}_weather_health_score",
          "name": _translated_health_label(
            translation_lookup,
            "weather_health_score",
          ),
          "icon": "mdi:heart-pulse",
        },
        {
          "entity": f"sensor.{dog_id}_weather_temperature_risk",
          "name": _translated_health_label(translation_lookup, "temperature_risk"),
          "icon": "mdi:thermometer-alert",
        },
        {
          "entity": f"sensor.{dog_id}_weather_activity_recommendation",
          "name": _translated_health_label(translation_lookup, "activity_level"),
          "icon": "mdi:run",
        },
        {
          "entity": f"binary_sensor.{dog_id}_weather_safe_for_walks",
          "name": _translated_health_label(translation_lookup, "walk_safety"),
          "icon": "mdi:walk",
        },
      ]

      card_mod = self._card_mod(theme_styles)  # noqa: E111
      template = {  # noqa: E111
        "type": "entities",
        "title": _translated_health_template(
          translation_lookup,
          "weather_health_card_title",
          icon=weather_icon,
          dog_name=dog_name,
        ),
        "entities": entities,
        "state_color": True,
        "show_header_toggle": False,
        "card_mod": card_mod,
      }

      # Add theme-specific styling  # noqa: E114
      if theme == "modern":  # noqa: E111
        style = card_mod.get("style", "")
        style += """
                    .card-header {
                        background: linear-gradient(90deg, #2196F3, #21CBF3);
                        color: white;
                        border-radius: 16px 16px 0 0;
                    }
                """
        card_mod["style"] = style
      elif theme == "playful":  # noqa: E111
        style = card_mod.get("style", "")
        style += """
                    .card-header {
                        background: linear-gradient(45deg, #FF6B6B, #4ECDC4, #FFE66D);
                        background-size: 300% 300%;
                        animation: gradient 3s ease infinite;
                        color: white;
                    }
                    @keyframes gradient {
                        0% { background-position: 0% 50%; }
                        50% { background-position: 100% 50%; }
                        100% { background-position: 0% 50%; }
                    }
                """
        card_mod["style"] = style

    await self._cache.set(cache_key, template)
    return template

  async def get_weather_alerts_card_template(  # noqa: E111
    self,
    dog_id: str,
    dog_name: str,
    theme: str = "modern",
    max_alerts: int = 3,
  ) -> CardConfig:
    """Get weather alerts card template.

    Args:
        dog_id: Dog identifier
        dog_name: Dog display name
        theme: Visual theme
        max_alerts: Maximum number of alerts to display

    Returns:
        Weather alerts card template
    """
    theme_styles = self._get_theme_styles(theme)
    alert_icon = "⚠️" if theme == "playful" else "mdi:weather-lightning"

    # Dynamic content based on current alerts
    alerts_content = f"""
## {alert_icon} Weather Alerts for {dog_name}

{{%- set alerts = states.sensor.{dog_id}_weather_alerts.attributes.active_alerts | default([]) -%}}
{{%- if alerts | length > 0 -%}}
{{%- for alert in alerts[:3] -%}}
### {{ alert.severity | title }} Alert: {{ alert.title }}
{{ alert.message }}

**Impact:** {{ alert.impact }}
**Recommendation:** {{ alert.recommendation }}

---
{{%- endfor -%}}
{{%- else -%}}
### ✅ No Weather Alerts
{dog_name} can enjoy normal outdoor activities today!

**Current Conditions:** Perfect for walks and outdoor play.
{{%- endif -%}}

**Last Updated:** {{{{ states('sensor.{dog_id}_weather_last_update') }}}}
"""  # noqa: E501

    # Conditional styling based on alert severity
    if theme == "modern":
      card_mod_style = """
                ha-card {
                    background: linear-gradient(135deg,
                        {% if states('sensor.{dog_id}_weather_alerts') | int > 0 %}
                            rgba(244, 67, 54, 0.1) 0%, rgba(255, 152, 0, 0.1) 100%
                        {% else %}
                            rgba(76, 175, 80, 0.1) 0%, rgba(139, 195, 74, 0.1) 100%
                        {% endif %}
                    );
                    border-left: 4px solid
                        {% if states('sensor.{dog_id}_weather_alerts') | int > 0 %}
                            #FF5722
                        {% else %}
                            #4CAF50
                        {% endif %};
                }
            """.replace("{dog_id}", dog_id)  # noqa: E111
    elif theme == "playful":
      card_mod_style = """
                ha-card {
                    background: {% if states('sensor.{dog_id}_weather_alerts') | int > 0 %}
                        linear-gradient(45deg, #FF6B6B, #FF8E53)
                    {% else %}
                        linear-gradient(45deg, #4ECDC4, #44A08D)
                    {% endif %};
                    color: white;
                    animation: pulse 2s infinite;
                }
                @keyframes pulse {
                    0% { transform: scale(1); }
                    50% { transform: scale(1.02); }
                    100% { transform: scale(1); }
                }
            """.replace("{dog_id}", dog_id)  # noqa: E111, E501
    else:
      card_mod_style = self._card_mod(theme_styles).get("style", "")  # noqa: E111

    template: CardConfig = {
      "type": "markdown",
      "content": alerts_content,
      "card_mod": {
        "style": card_mod_style,
      },
    }

    return template

  async def get_weather_recommendations_card_template(  # noqa: E111
    self,
    dog_id: str,
    dog_name: str,
    theme: str = "modern",
    include_breed_specific: bool = True,
    recommendations: Sequence[str] | None = None,
    *,
    overflow_recommendations: int = 0,
  ) -> CardConfig:
    """Get weather recommendations card template.

    Args:
        dog_id: Dog identifier
        dog_name: Dog display name
        theme: Visual theme
        include_breed_specific: Whether to include breed-specific advice
        recommendations: Sanitised recommendation strings to embed in content
        overflow_recommendations: Number of hidden recommendations to note in output

    Returns:
        Weather recommendations card template
    """

    theme_styles = self._get_theme_styles(theme)
    rec_icon = "💡" if theme == "playful" else "mdi:lightbulb-on"

    bullet_lines: list[str] = []
    if recommendations:
      for item in recommendations:  # noqa: E111
        entry = item.strip()
        if entry:
          bullet_lines.append(f"• {entry}")  # noqa: E111

    if not bullet_lines:
      bullet_lines.extend(  # noqa: E111
        [
          "• Perfect weather for normal activities!",
          "• Maintain regular exercise schedule",
          "• Keep hydration available",
        ],
      )

    if overflow_recommendations > 0:
      bullet_lines.append(  # noqa: E111
        f"*... and {overflow_recommendations} more recommendations*",
      )

    breed_section: list[str] = []
    if include_breed_specific:
      breed_section = [  # noqa: E111
        "### 🐕 Breed-Specific Advice",
        "{{%- set breed = states.sensor.{dog_id}_breed.state | default('Mixed') -%}}",
        "{{{{ states.sensor.{dog_id}_breed_weather_advice.attributes.advice | default('No specific advice available for this breed.') }}}}",  # noqa: E501
      ]

    lines = [
      f"## {rec_icon} Weather Recommendations for {dog_name}",
      "",
      "### 🌡️ Temperature Guidance",
      f"**Current Feel:** {{{{ states('sensor.{dog_id}_weather_feels_like') }}}}°C",
      f"**Recommendation:** {{{{ states('sensor.{dog_id}_weather_activity_recommendation') }}}}",  # noqa: E501
      "",
      "### 🚶 Activity Suggestions",
      *bullet_lines,
    ]

    if breed_section:
      lines.extend(["", *breed_section])  # noqa: E111

    lines.extend(
      [
        "",
        "### ⏰ Best Activity Times",
        f"**Optimal Walk Time:** {{{{ states('sensor.{dog_id}_optimal_walk_time') }}}}",
        f"**Avoid Outdoors:** {{{{ states('sensor.{dog_id}_weather_avoid_times') }}}}",
        "",
        f"**Last Updated:** {{{{ states('sensor.{dog_id}_weather_last_update') }}}}",
      ],
    )

    recommendations_content = "\n".join(lines).replace("{dog_id}", dog_id)

    card_mod = self._card_mod(theme_styles)
    template: CardConfig = {
      "type": "markdown",
      "content": recommendations_content,
      "card_mod": card_mod,
    }

    if theme == "modern":
      style = card_mod.get("style", "")  # noqa: E111
      style += """
                .card-content {
                    padding-bottom: 60px;
                }
                .card-content::after {
                    content: '';
                    position: absolute;
                    bottom: 10px;
                    left: 10px;
                    right: 10px;
                    height: 40px;
                    background: linear-gradient(90deg, #2196F3, #21CBF3);
                    border-radius: 20px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                }
            """  # noqa: E111
      card_mod["style"] = style  # noqa: E111

    return template

  async def get_weather_chart_template(  # noqa: E111
    self,
    dog_id: str,
    chart_type: str = "health_score",
    theme: str = "modern",
    time_range: str = "24h",
  ) -> CardConfig:
    """Get weather impact chart template.

    Args:
        dog_id: Dog identifier
        chart_type: Type of chart (health_score, temperature, activity)
        theme: Visual theme
        time_range: Time range (24h, 7d, 30d)

    Returns:
        Weather chart template
    """
    theme_styles = self._get_theme_styles(theme)
    hass_language: str | None = getattr(self.hass.config, "language", None)
    translation_lookup = await async_get_component_translation_lookup(
      self.hass,
      hass_language,
    )

    hours_map = {
      "24h": 24,
      "7d": 168,
      "30d": 720,
    }
    hours_to_show = hours_map.get(time_range, 24)

    entities: list[JSONMutableMapping]

    if chart_type == "health_score":
      entities = [  # noqa: E111
        {
          "entity": f"sensor.{dog_id}_weather_health_score",
          "name": _translated_health_label(
            translation_lookup,
            "weather_health_score",
          ),
          "color": theme_styles["colors"]["primary"],
        },
        {
          "entity": f"sensor.{dog_id}_outdoor_temperature",
          "name": "Temperature",
          "color": theme_styles["colors"]["accent"],
          "y_axis": "secondary",
        },
      ]
      chart_title = _translated_health_template(  # noqa: E111
        translation_lookup,
        "weather_health_chart_title",
      )
    elif chart_type == "temperature":
      entities = [  # noqa: E111
        {
          "entity": f"sensor.{dog_id}_outdoor_temperature",
          "name": "Temperature",
          "color": "#FF5722",
        },
        {
          "entity": f"sensor.{dog_id}_feels_like_temperature",
          "name": "Feels Like",
          "color": "#FF9800",
        },
        {
          "entity": f"sensor.{dog_id}_temperature_comfort_zone",
          "name": "Comfort Zone",
          "color": "#4CAF50",
          "show_fill": True,
        },
      ]
      chart_title = "Temperature Trends"  # noqa: E111
    else:  # activity
      entities = [  # noqa: E111
        {
          "entity": f"sensor.{dog_id}_weather_activity_level",
          "name": "Recommended Activity",
          "color": theme_styles["colors"]["primary"],
        },
        {
          "entity": f"sensor.{dog_id}_actual_activity_level",
          "name": "Actual Activity",
          "color": theme_styles["colors"]["accent"],
        },
      ]
      chart_title = "Activity vs Weather"  # noqa: E111

    template: CardConfig
    if theme in ["modern", "dark"]:
      card_mod = self._card_mod(theme_styles)  # noqa: E111
      template = {  # noqa: E111
        "type": "custom:mini-graph-card",
        "name": chart_title,
        "entities": entities,
        "hours_to_show": hours_to_show,
        "points_per_hour": 2 if hours_to_show <= 24 else 1,
        "line_width": 3,
        "animate": True,
        "show": {
          "labels": True,
          "points": True,
          "legend": True,
          "average": True,
          "extrema": True,
          "fill": "fade",
        },
        "color_thresholds": [
          {"value": 30, "color": "#4CAF50"},
          {"value": 60, "color": "#FF9800"},
          {"value": 80, "color": "#F44336"},
        ],
        "card_mod": card_mod,
      }
    else:
      # Fallback to simple history graph  # noqa: E114
      card_mod = self._card_mod(theme_styles)  # noqa: E111
      template = {  # noqa: E111
        "type": "history-graph",
        "title": chart_title,
        "entities": [entity["entity"] for entity in entities],
        "hours_to_show": hours_to_show,
        "card_mod": card_mod,
      }

    return template

  async def get_weather_breed_advisory_template(  # noqa: E111
    self,
    dog_id: str,
    dog_name: str,
    breed: str,
    theme: str = "modern",
  ) -> CardConfig:
    """Get breed-specific weather advisory template.

    Args:
        dog_id: Dog identifier
        dog_name: Dog display name
        breed: Dog breed
        theme: Visual theme

    Returns:
        Breed-specific weather advisory template
    """
    theme_styles = self._get_theme_styles(theme)
    breed_icon = self._get_breed_emoji(breed, theme)

    advisory_content = f"""
## {breed_icon} {breed} Weather Advisory for {dog_name}

{{%- set breed_advice = states.sensor.{dog_id}_breed_weather_advice.attributes -%}}
{{%- set current_temp = states('sensor.{dog_id}_outdoor_temperature') | float -%}}
{{%- set breed_comfort_min = breed_advice.comfort_range.min | default(10) -%}}
{{%- set breed_comfort_max = breed_advice.comfort_range.max | default(25) -%}}

### 🌡️ Breed Comfort Zone
**Optimal Range:** {{ breed_comfort_min }}°C - {{ breed_comfort_max }}°C
**Current:** {{ current_temp }}°C

{{%- if current_temp < breed_comfort_min -%}}
### ❄️ Cold Weather Precautions
{{ breed_advice.cold_weather_advice | default('Monitor for signs of cold stress') }}
{{%- elif current_temp > breed_comfort_max -%}}
### 🔥 Hot Weather Precautions
{{ breed_advice.hot_weather_advice | default('Provide shade and fresh water') }}
{{%- else -%}}
### ✅ Perfect Weather for {{ breed }}s
{{ breed_advice.optimal_weather_advice | default('Great conditions for normal activities') }}
{{%- endif -%}}

### 🔍 Breed-Specific Monitoring
{{%- for warning in breed_advice.breed_warnings | default([]) -%}}
• {{ warning }}
{{%- endfor -%}}

### 💡 Activity Adjustments
**Exercise Modifications:** {{ breed_advice.exercise_modifications | default('No modifications needed') }}
**Special Considerations:** {{ breed_advice.special_considerations | default('Standard care applies') }}

**Breed Profile Last Updated:** {{{{ states('sensor.{dog_id}_breed_profile_updated') }}}}
"""  # noqa: E501

    breed_advice_state = self.hass.states.get(
      f"sensor.{dog_id}_breed_weather_advice",
    )
    breed_advice_attrs: Mapping[str, object] = {}
    if breed_advice_state is not None:
      attrs = getattr(breed_advice_state, "attributes", {})  # noqa: E111
      if isinstance(attrs, Mapping):  # noqa: E111
        breed_advice_attrs = attrs

    comfort_range_obj = breed_advice_attrs.get("comfort_range", {})
    comfort_range: Mapping[str, object]
    comfort_range = comfort_range_obj if isinstance(comfort_range_obj, Mapping) else {}

    def _coerce_temperature(value: object, fallback: float) -> float:
      if isinstance(value, int | float):  # noqa: E111
        return float(value)
      if isinstance(value, str):  # noqa: E111
        try:
          return float(value)  # noqa: E111
        except ValueError:
          return fallback  # noqa: E111
      return fallback  # noqa: E111

    comfort_min_value = _coerce_temperature(comfort_range.get("min"), 10.0)
    comfort_max_value = _coerce_temperature(comfort_range.get("max"), 25.0)

    # Breed-specific styling
    if theme == "modern":
      card_style = (  # noqa: E111
        """
                ha-card {
                    background: linear-gradient(135deg,
                        {% if states('sensor.{dog_id}_outdoor_temperature') | float < breed_comfort_min %}
                            rgba(33, 150, 243, 0.1) 0%, rgba(3, 169, 244, 0.1) 100%
                        {% elif states('sensor.{dog_id}_outdoor_temperature') | float > breed_comfort_max %}
                            rgba(255, 87, 34, 0.1) 0%, rgba(255, 152, 0, 0.1) 100%
                        {% else %}
                            rgba(76, 175, 80, 0.1) 0%, rgba(139, 195, 74, 0.1) 100%
                        {% endif %}
                    );
                    border-left: 6px solid
                        {% if states('sensor.{dog_id}_outdoor_temperature') | float < breed_comfort_min %}
                            #2196F3
                        {% elif states('sensor.{dog_id}_outdoor_temperature') | float > breed_comfort_max %}
                            #FF5722
                        {% else %}
                            #4CAF50
                        {% endif %};
                }
            """  # noqa: E501
        .replace("{dog_id}", dog_id)
        .replace("breed_comfort_min", str(comfort_min_value))
        .replace("breed_comfort_max", str(comfort_max_value))
      )
    else:
      card_style = self._card_mod(theme_styles).get("style", "")  # noqa: E111

    template: CardConfig = {
      "type": "markdown",
      "content": advisory_content,
      "card_mod": {
        "style": card_style,
      },
    }

    return template

  async def get_weather_action_buttons_template(  # noqa: E111
    self,
    dog_id: str,
    theme: str = "modern",
    layout: str = "horizontal",
  ) -> CardConfig:
    """Get weather action buttons template.

    Args:
        dog_id: Dog identifier
        theme: Visual theme
        layout: Button layout (horizontal, vertical, grid)

    Returns:
        Weather action buttons template
    """
    base_button = self._get_base_card_template("button")
    theme_styles = self._get_theme_styles(theme)

    # Weather update button
    update_button: CardConfig = dict(base_button)
    update_button.update(
      {
        "name": "Update Weather",
        "icon": "mdi:weather-cloudy-arrow-right",
        "icon_color": theme_styles["colors"]["primary"],
        "tap_action": {
          "action": "call-service",
          "service": f"{DOMAIN}.update_weather",
          "service_data": {"force_update": True},
        },
      },
    )

    # Get weather alerts button
    alerts_button: CardConfig = dict(base_button)
    alerts_button.update(
      {
        "name": "Check Alerts",
        "icon": "mdi:weather-lightning",
        "icon_color": "orange",
        "tap_action": {
          "action": "call-service",
          "service": f"{DOMAIN}.get_weather_alerts",
          "service_data": {"dog_id": dog_id},
        },
      },
    )

    # Get recommendations button
    recommendations_button: CardConfig = dict(base_button)
    recommendations_button.update(
      {
        "name": "Get Advice",
        "icon": "mdi:lightbulb-on",
        "icon_color": theme_styles["colors"]["accent"],
        "tap_action": {
          "action": "call-service",
          "service": f"{DOMAIN}.get_weather_recommendations",
          "service_data": {
            "dog_id": dog_id,
            "include_breed_specific": True,
          },
        },
      },
    )

    buttons: CardCollection = [
      update_button,
      alerts_button,
      recommendations_button,
    ]

    # Apply theme styling to buttons
    if theme == "modern":
      colors = ["#2196F3", "#FF9800", "#4CAF50"]  # noqa: E111
      for index, button in enumerate(buttons):  # noqa: E111
        card_mod = CardModConfig(
          style=f"""
                        ha-card {{
                            background: linear-gradient(135deg, {colors[index]}, {colors[index]}CC);
                            color: white;
                            border-radius: 12px;
                            transition: all 0.3s ease;
                        }}
                        ha-card:hover {{
                            transform: translateY(-2px);
                            box-shadow: 0 8px 20px rgba(0,0,0,0.15);
                        }}
                    """,  # noqa: E501
        )
        button["card_mod"] = card_mod
    elif theme == "playful":
      playful_card_mod = CardModConfig(  # noqa: E111
        style="""
                    ha-card {
                        background: linear-gradient(45deg, #FF6B6B, #4ECDC4);
                        color: white;
                        border-radius: 50px;
                        animation: wiggle 2s ease-in-out infinite;
                    }
                    @keyframes wiggle {
                        0%, 100% { transform: rotate(0deg); }
                        25% { transform: rotate(-1deg); }
                        75% { transform: rotate(1deg); }
                    }
                """,
      )
      for button in buttons:  # noqa: E111
        button["card_mod"] = playful_card_mod

    # Layout buttons according to specified layout
    if layout == "vertical":
      return {  # noqa: E111
        "type": "vertical-stack",
        "cards": buttons,
      }
    if layout == "grid":
      return {  # noqa: E111
        "type": "grid",
        "columns": 3,
        "cards": buttons,
      }
    # horizontal (default)
    return {
      "type": "horizontal-stack",
      "cards": buttons,
    }

  def _get_weather_icon(self, theme: str) -> str:  # noqa: E111
    """Get theme-appropriate weather icon.

    Args:
        theme: Theme name

    Returns:
        Weather icon for the theme
    """
    icons = {
      "modern": "🌤️",
      "playful": "☀️",
      "minimal": "○",
      "dark": "🌙",
    }
    return icons.get(theme, "🌤️")

  def _get_weather_color_by_score(self, theme: str) -> str:  # noqa: E111
    """Get weather health score color by theme.

    Args:
        theme: Theme name

    Returns:
        Color for weather health score
    """
    theme_styles = self._get_theme_styles(theme)
    return theme_styles["colors"]["primary"]

  def _get_breed_emoji(self, breed: str, theme: str) -> str:  # noqa: E111
    """Get breed-specific emoji.

    Args:
        breed: Dog breed name
        theme: Theme name

    Returns:
        Breed-appropriate emoji
    """
    if theme != "playful":
      return "🐕"  # noqa: E111

    # Breed-specific emojis for playful theme
    breed_emojis = {
      "husky": "🐺",
      "golden retriever": "🦮",
      "bulldog": "🐶",
      "poodle": "🐩",
      "german shepherd": "🦮",
      "labrador": "🦮",
      "chihuahua": "🐕‍🦺",
      "beagle": "🐕",
    }

    breed_lower = breed.lower().strip()
    for breed_key, emoji in breed_emojis.items():
      if breed_key in breed_lower:  # noqa: E111
        return emoji

    return "🐶"  # Default playful dog emoji

  async def get_history_graph_template(  # noqa: E111
    self,
    entities: list[str],
    title: str,
    hours_to_show: int = 24,
    theme: str = "modern",
  ) -> CardConfig:
    """Get themed history graph template.

    Args:
        entities: Entity IDs to display
        title: Graph title
        hours_to_show: Hours of history to show
        theme: Visual theme

    Returns:
        History graph template
    """
    # Filter entities that likely exist
    valid_entities = await self._filter_valid_entities(entities)

    if not valid_entities:
      # Return empty markdown card if no valid entities  # noqa: E114
      return {  # noqa: E111
        "type": "markdown",
        "content": f"**{title}**\n\nNo data available",
      }

    theme_styles = self._get_theme_styles(theme)

    card_mod = self._card_mod(theme_styles)
    template: CardConfig = {
      **self._get_base_card_template("history_graph"),
      "title": title,
      "entities": valid_entities,
      "hours_to_show": hours_to_show,
      "card_mod": card_mod,
    }

    return template

  async def _filter_valid_entities(self, entities: list[str]) -> list[str]:  # noqa: E111
    """Filter entities to only include those that exist.

    Args:
        entities: List of entity IDs to check

    Returns:
        List of existing entity IDs
    """
    valid_entities = []

    for entity_id in entities:
      state = self.hass.states.get(entity_id)  # noqa: E111
      if state and state.state != STATE_UNKNOWN:  # noqa: E111
        valid_entities.append(entity_id)

    return valid_entities

  async def cleanup(self) -> None:  # noqa: E111
    """Clean up template cache and resources."""
    await self._cache.clear()

  async def get_weather_dashboard_layout_template(  # noqa: E111
    self,
    dog_id: str,
    dog_name: str,
    breed: str,
    theme: str = "modern",
    layout: str = "full",
  ) -> CardConfig:
    """Get complete weather dashboard layout template.

    Args:
        dog_id: Dog identifier
        dog_name: Dog display name
        breed: Dog breed
        theme: Visual theme
        layout: Layout type (full, compact, mobile)

    Returns:
        Complete weather dashboard layout
    """
    if layout == "compact":
      # Compact layout for smaller screens  # noqa: E114
      compact_cards: CardCollection = [  # noqa: E111
        await self.get_weather_status_card_template(
          dog_id,
          dog_name,
          theme,
          compact=True,
        ),
        await self.get_weather_alerts_card_template(
          dog_id,
          dog_name,
          theme,
          max_alerts=1,
        ),
        await self.get_weather_action_buttons_template(
          dog_id,
          theme,
          layout="horizontal",
        ),
      ]

      return {  # noqa: E111
        "type": "vertical-stack",
        "cards": compact_cards,
      }

    if layout == "mobile":
      # Mobile-optimized layout  # noqa: E114
      mobile_cards: CardCollection = [  # noqa: E111
        await self.get_weather_status_card_template(
          dog_id,
          dog_name,
          theme,
          compact=True,
        ),
        await self.get_weather_chart_template(
          dog_id,
          "health_score",
          theme,
          "24h",
        ),
        await self.get_weather_action_buttons_template(
          dog_id,
          theme,
          layout="grid",
        ),
      ]

      return {  # noqa: E111
        "type": "vertical-stack",
        "cards": mobile_cards,
      }

    # full layout
    # Full desktop layout with all weather components
    full_cards: CardCollection = [
      # Top row: Status and alerts
      {
        "type": "horizontal-stack",
        "cards": [
          await self.get_weather_status_card_template(
            dog_id,
            dog_name,
            theme,
          ),
          await self.get_weather_alerts_card_template(
            dog_id,
            dog_name,
            theme,
          ),
        ],
      },
      # Second row: Charts
      {
        "type": "horizontal-stack",
        "cards": [
          await self.get_weather_chart_template(
            dog_id,
            "health_score",
            theme,
            "24h",
          ),
          await self.get_weather_chart_template(
            dog_id,
            "temperature",
            theme,
            "24h",
          ),
        ],
      },
      # Third row: Recommendations and breed advice
      {
        "type": "horizontal-stack",
        "cards": [
          await self.get_weather_recommendations_card_template(
            dog_id,
            dog_name,
            theme,
          ),
          await self.get_weather_breed_advisory_template(
            dog_id,
            dog_name,
            breed,
            theme,
          ),
        ],
      },
      # Bottom row: Action buttons
      await self.get_weather_action_buttons_template(
        dog_id,
        theme,
        layout="horizontal",
      ),
    ]

    return {
      "type": "vertical-stack",
      "cards": full_cards,
    }

  @callback  # noqa: E111
  def get_cache_stats(self) -> TemplateCacheStats:  # noqa: E111
    """Get template cache statistics."""
    return self._cache.get_stats()

  @callback  # noqa: E111
  def get_cache_snapshot(self) -> TemplateCacheSnapshot:  # noqa: E111
    """Return a diagnostics snapshot of the template cache."""

    return self._cache.coordinator_snapshot()
