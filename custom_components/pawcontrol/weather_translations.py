"""Helpers for PawControl weather translations."""

from __future__ import annotations

from copy import deepcopy
from typing import Final, Literal, TypedDict, cast

DEFAULT_LANGUAGE: Final[LanguageCode] = "en"


class WeatherAlertTranslation(TypedDict):
    """Localized strings for a specific weather alert."""

    title: str
    message: str


type WeatherAlertKey = Literal[
    "extreme_cold_warning",
    "extreme_heat_warning",
    "extreme_uv_warning",
    "high_cold_advisory",
    "high_heat_advisory",
    "high_humidity_alert",
    "high_uv_advisory",
    "snow_ice_alert",
    "storm_warning",
    "warm_weather_caution",
    "wet_weather_advisory",
]


type WeatherAlertTranslations = dict[WeatherAlertKey, WeatherAlertTranslation]


type WeatherRecommendationKey = Literal[
    "avoid_peak_hours",
    "avoid_peak_uv",
    "avoid_until_passes",
    "breed_specific_caution",
    "check_toe_irritation",
    "cold_surface_protection",
    "comfort_anxious",
    "consider_clothing",
    "cool_ventilated_areas",
    "cooler_day_parts",
    "cooler_surfaces",
    "dry_paws_thoroughly",
    "ensure_shade",
    "essential_only",
    "extra_water",
    "good_air_circulation",
    "heart_avoid_strenuous",
    "keep_indoors",
    "keep_indoors_storm",
    "limit_outdoor_time",
    "limit_peak_exposure",
    "monitor_breathing",
    "monitor_overheating",
    "monitor_skin_irritation",
    "never_leave_in_car",
    "pet_sunscreen",
    "postpone_activities",
    "protect_nose_ears",
    "protect_paws",
    "protective_clothing",
    "provide_shade_always",
    "provide_traction",
    "provide_water",
    "puppy_extra_monitoring",
    "reduce_exercise_intensity",
    "respiratory_monitoring",
    "rinse_salt_chemicals",
    "secure_id_tags",
    "senior_extra_protection",
    "shade_during_activities",
    "shorten_activities",
    "use_cooling_aids",
    "use_paw_balm",
    "use_paw_protection",
    "uv_protective_clothing",
    "warm_shelter",
    "warm_shelter_available",
    "watch_heat_signs",
    "watch_heat_stress",
    "watch_hypothermia",
    "watch_ice_buildup",
    "waterproof_protection",
]


type WeatherRecommendationTranslations = dict[WeatherRecommendationKey, str]


class WeatherTranslations(TypedDict):
    """Structured translation catalog for weather health guidance."""

    alerts: WeatherAlertTranslations
    recommendations: WeatherRecommendationTranslations


type LanguageCode = Literal["de", "en"]


type LanguageMap[T] = dict[LanguageCode, T]


_WEATHER_TRANSLATIONS: LanguageMap[WeatherTranslations] = {
    "en": {
        "alerts": {
            "extreme_heat_warning": {
                "title": "🔥 Extreme Heat Warning",
                "message": "Temperature {temperature}°C (feels like {feels_like}°C) poses extreme heat risk to dogs",
            },
            "high_heat_advisory": {
                "title": "🌡️ High Heat Advisory",
                "message": "Temperature {temperature}°C requires heat precautions for dogs",
            },
            "warm_weather_caution": {
                "title": "☀️ Warm Weather Caution",
                "message": "Temperature {temperature}°C requires basic heat precautions",
            },
            "extreme_cold_warning": {
                "title": "🥶 Extreme Cold Warning",
                "message": "Temperature {temperature}°C (feels like {feels_like}°C) poses extreme cold risk",
            },
            "high_cold_advisory": {
                "title": "❄️ High Cold Advisory",
                "message": "Temperature {temperature}°C requires cold weather precautions",
            },
            "extreme_uv_warning": {
                "title": "☢️ Extreme UV Warning",
                "message": "UV Index {uv_index} poses extreme UV risk to dogs",
            },
            "high_uv_advisory": {
                "title": "🌞 High UV Advisory",
                "message": "UV Index {uv_index} requires UV protection for dogs",
            },
            "high_humidity_alert": {
                "title": "💨 High Humidity Alert",
                "message": "Humidity {humidity}% may cause breathing difficulties",
            },
            "wet_weather_advisory": {
                "title": "🌧️ Wet Weather Advisory",
                "message": "Rainy conditions require paw care precautions",
            },
            "storm_warning": {
                "title": "⛈️ Storm Warning",
                "message": "Storms can cause anxiety and safety risks for dogs",
            },
            "snow_ice_alert": {
                "title": "🌨️ Snow/Ice Alert",
                "message": "Icy conditions require paw protection",
            },
        },
        "recommendations": {
            "avoid_peak_hours": "Avoid outdoor activities during peak hours",
            "provide_water": "Provide constant access to cool water",
            "keep_indoors": "Keep dog indoors with air conditioning",
            "watch_heat_signs": "Watch for signs of heat exhaustion: heavy panting, drooling, lethargy",
            "use_cooling_aids": "Consider cooling mats or vests",
            "never_leave_in_car": "Never leave dog in car or direct sunlight",
            "limit_outdoor_time": "Limit outdoor activities to early morning or evening",
            "ensure_shade": "Ensure adequate water availability",
            "monitor_overheating": "Monitor for signs of overheating",
            "cooler_surfaces": "Consider shorter walks on cooler surfaces",
            "extra_water": "Provide extra water during outdoor activities",
            "cooler_day_parts": "Plan walks during cooler parts of the day",
            "watch_heat_stress": "Watch for early signs of heat stress",
            "essential_only": "Limit outdoor exposure to essential needs only",
            "protective_clothing": "Use protective clothing for short-haired breeds",
            "protect_paws": "Protect paws from ice and salt",
            "warm_shelter": "Provide warm, draft-free sleeping area",
            "watch_hypothermia": "Watch for signs of hypothermia: shivering, lethargy, weakness",
            "postpone_activities": "Consider postponing non-essential outdoor activities",
            "shorten_activities": "Shorten outdoor activities",
            "consider_clothing": "Consider protective clothing for sensitive breeds",
            "cold_surface_protection": "Protect paws from cold surfaces",
            "warm_shelter_available": "Ensure warm shelter is available",
            "avoid_peak_uv": "Avoid outdoor activities during peak UV hours (10am-4pm)",
            "provide_shade_always": "Provide shade for all outdoor time",
            "uv_protective_clothing": "Consider UV-protective clothing for light-colored dogs",
            "protect_nose_ears": "Protect nose and ear tips from UV exposure",
            "pet_sunscreen": "Use pet-safe sunscreen on exposed areas",
            "shade_during_activities": "Provide shade during outdoor activities",
            "limit_peak_exposure": "Limit exposure during peak hours",
            "monitor_skin_irritation": "Monitor light-colored dogs for skin irritation",
            "reduce_exercise_intensity": "Reduce exercise intensity and duration",
            "good_air_circulation": "Ensure good air circulation indoors",
            "monitor_breathing": "Monitor brachycephalic breeds closely",
            "cool_ventilated_areas": "Provide cool, well-ventilated rest areas",
            "dry_paws_thoroughly": "Dry paws thoroughly after outdoor activities",
            "check_toe_irritation": "Check for irritation between toes",
            "use_paw_balm": "Use protective paw balm if needed",
            "waterproof_protection": "Consider waterproof protection for sensitive paws",
            "keep_indoors_storm": "Keep dog indoors during storm",
            "comfort_anxious": "Provide comfort for anxious dogs",
            "secure_id_tags": "Ensure identification tags are secure before storm",
            "avoid_until_passes": "Avoid outdoor activities until storm passes",
            "use_paw_protection": "Use paw protection or boots",
            "watch_ice_buildup": "Watch for ice buildup between toes",
            "rinse_salt_chemicals": "Rinse paws after walks to remove salt/chemicals",
            "provide_traction": "Provide traction on slippery surfaces",
            "breed_specific_caution": "Extra caution needed for {breed} breed during {alert_type}",
            "puppy_extra_monitoring": "Puppies are more vulnerable - monitor closely",
            "senior_extra_protection": "Senior dogs need extra protection",
            "respiratory_monitoring": "Respiratory condition requires extra monitoring",
            "heart_avoid_strenuous": "Heart condition - avoid strenuous activity",
        },
    },
    "de": {
        "alerts": {
            "extreme_heat_warning": {
                "title": "🔥 Warnung vor extremer Hitze",
                "message": "Temperatur {temperature}°C (gefühlte {feels_like}°C) stellt ein extremes Hitzerisiko für Hunde dar",
            },
            "high_heat_advisory": {
                "title": "🌡️ Hitzewarnung",
                "message": "Temperatur {temperature}°C erfordert Hitzeschutzmaßnahmen für Hunde",
            },
            "warm_weather_caution": {
                "title": "☀️ Vorsicht bei warmem Wetter",
                "message": "Temperatur {temperature}°C erfordert grundlegende Hitzeschutzmaßnahmen",
            },
            "extreme_cold_warning": {
                "title": "🥶 Warnung vor extremer Kälte",
                "message": "Temperatur {temperature}°C (gefühlte {feels_like}°C) stellt ein extremes Kälterisiko dar",
            },
            "high_cold_advisory": {
                "title": "❄️ Kältehinweis",
                "message": "Temperatur {temperature}°C erfordert Kälteschutzmaßnahmen",
            },
            "extreme_uv_warning": {
                "title": "☢️ Warnung vor extremem UV",
                "message": "UV-Index {uv_index} bedeutet extremes UV-Risiko für Hunde",
            },
            "high_uv_advisory": {
                "title": "🌞 UV-Hinweis",
                "message": "UV-Index {uv_index} erfordert UV-Schutz für Hunde",
            },
            "high_humidity_alert": {
                "title": "💨 Warnung vor hoher Luftfeuchtigkeit",
                "message": "Luftfeuchtigkeit {humidity}% kann zu Atembeschwerden führen",
            },
            "wet_weather_advisory": {
                "title": "🌧️ Hinweis auf nasses Wetter",
                "message": "Regenbedingungen erfordern Pfotenschutzmaßnahmen",
            },
            "storm_warning": {
                "title": "⛈️ Unwetterwarnung",
                "message": "Stürme können Angst und Sicherheitsrisiken für Hunde verursachen",
            },
            "snow_ice_alert": {
                "title": "🌨️ Schnee-/Eiswarnung",
                "message": "Vereiste Bedingungen erfordern Pfotenschutz",
            },
        },
        "recommendations": {
            "avoid_peak_hours": "Außenaktivitäten während der Spitzenzeiten vermeiden",
            "provide_water": "Ständigen Zugang zu kühlem Wasser bereitstellen",
            "keep_indoors": "Hund im Haus mit Klimaanlage lassen",
            "watch_heat_signs": "Auf Anzeichen von Hitzschlag achten: starkes Hecheln, Sabbern, Trägheit",
            "use_cooling_aids": "Kühlmatten oder -westen in Betracht ziehen",
            "never_leave_in_car": "Hund niemals im Auto oder in direkter Sonne lassen",
            "limit_outdoor_time": "Aktivitäten im Freien auf frühen Morgen oder späten Abend begrenzen",
            "ensure_shade": "Für ausreichende Wasserverfügbarkeit sorgen",
            "monitor_overheating": "Auf Anzeichen von Überhitzung achten",
            "cooler_surfaces": "Kürzere Spaziergänge auf kühleren Untergründen erwägen",
            "extra_water": "Bei Aktivitäten im Freien zusätzlich Wasser anbieten",
            "cooler_day_parts": "Spaziergänge auf kühlere Tageszeiten legen",
            "watch_heat_stress": "Frühe Anzeichen von Hitzestress beobachten",
            "essential_only": "Aufenthalt im Freien auf das Notwendigste beschränken",
            "protective_clothing": "Schutzkleidung für kurzhaarige Rassen verwenden",
            "protect_paws": "Pfotenschutz vor Eis und Salz einsetzen",
            "warm_shelter": "Warmen, zugfreien Schlafplatz bereitstellen",
            "watch_hypothermia": "Auf Anzeichen von Unterkühlung achten: Zittern, Trägheit, Schwäche",
            "postpone_activities": "Nicht zwingende Außenaktivitäten verschieben",
            "shorten_activities": "Aktivitäten im Freien verkürzen",
            "consider_clothing": "Schutzkleidung für empfindliche Rassen erwägen",
            "cold_surface_protection": "Pfotenschutz vor kalten Oberflächen verwenden",
            "warm_shelter_available": "Sicherstellen, dass ein warmer Unterschlupf verfügbar ist",
            "avoid_peak_uv": "Aktivitäten im Freien während hoher UV-Zeiten (10-16 Uhr) vermeiden",
            "provide_shade_always": "Bei Außenaufenthalten stets Schatten bereitstellen",
            "uv_protective_clothing": "UV-Schutzkleidung für hellfarbige Hunde erwägen",
            "protect_nose_ears": "Nase und Ohrenspitzen vor UV-Strahlung schützen",
            "pet_sunscreen": "Tierfreundliche Sonnencreme auf exponierte Stellen auftragen",
            "shade_during_activities": "Während Outdoor-Aktivitäten Schatten anbieten",
            "limit_peak_exposure": "Exposition während Spitzenzeiten begrenzen",
            "monitor_skin_irritation": "Helle Hunde auf Hautreizungen beobachten",
            "reduce_exercise_intensity": "Intensität und Dauer der Bewegung reduzieren",
            "good_air_circulation": "Für gute Luftzirkulation im Innenraum sorgen",
            "monitor_breathing": "Brachycephale Rassen besonders beobachten",
            "cool_ventilated_areas": "Kühle, gut belüftete Ruhebereiche bereitstellen",
            "dry_paws_thoroughly": "Pfoten nach Spaziergängen gründlich trocknen",
            "check_toe_irritation": "Zwischen den Zehen auf Reizungen prüfen",
            "use_paw_balm": "Bei Bedarf schützenden Pfotenbalsam verwenden",
            "waterproof_protection": "Wasserdichten Schutz für empfindliche Pfoten erwägen",
            "keep_indoors_storm": "Hund während des Sturms im Haus lassen",
            "comfort_anxious": "Ängstliche Hunde beruhigen und unterstützen",
            "secure_id_tags": "Vor dem Sturm ID-Marken sicher befestigen",
            "avoid_until_passes": "Aktivitäten im Freien vermeiden, bis der Sturm vorbei ist",
            "use_paw_protection": "Pfotenschutz oder Schuhe verwenden",
            "watch_ice_buildup": "Auf Eisansammlungen zwischen den Zehen achten",
            "rinse_salt_chemicals": "Pfoten nach Spaziergängen von Salz/Chemikalien abspülen",
            "provide_traction": "Für Halt auf rutschigen Oberflächen sorgen",
            "breed_specific_caution": "Zusätzliche Vorsicht für {breed} während {alert_type} erforderlich",
            "puppy_extra_monitoring": "Welpen sind anfälliger - besonders aufmerksam beobachten",
            "senior_extra_protection": "Senior-Hunde benötigen zusätzlichen Schutz",
            "respiratory_monitoring": "Atemwegserkrankungen erfordern zusätzliche Überwachung",
            "heart_avoid_strenuous": "Bei Herzproblemen anstrengende Aktivitäten vermeiden",
        },
    },
}

WEATHER_ALERT_KEYS: Final[tuple[WeatherAlertKey, ...]] = tuple(
    cast(WeatherAlertKey, key)
    for key in _WEATHER_TRANSLATIONS[DEFAULT_LANGUAGE]["alerts"]
)

WEATHER_RECOMMENDATION_KEYS: Final[tuple[WeatherRecommendationKey, ...]] = tuple(
    cast(WeatherRecommendationKey, key)
    for key in _WEATHER_TRANSLATIONS[DEFAULT_LANGUAGE]["recommendations"]
)

WEATHER_ALERT_KEY_SET: Final[frozenset[WeatherAlertKey]] = frozenset(
    WEATHER_ALERT_KEYS
)
WEATHER_RECOMMENDATION_KEY_SET: Final[
    frozenset[WeatherRecommendationKey]
] = frozenset(WEATHER_RECOMMENDATION_KEYS)

SUPPORTED_LANGUAGES: Final[frozenset[LanguageCode]] = frozenset(_WEATHER_TRANSLATIONS)


def get_weather_translations(language: str) -> WeatherTranslations:
    """Return weather translations for the requested language.

    Falls back to English when translations are unavailable.
    """
    if language in SUPPORTED_LANGUAGES:
        language_code = cast(LanguageCode, language)
    else:
        language_code = DEFAULT_LANGUAGE

    base = _WEATHER_TRANSLATIONS[language_code]
    return cast(WeatherTranslations, deepcopy(base))
