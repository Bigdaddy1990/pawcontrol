"""Localised templates for feeding compliance notifications."""

from __future__ import annotations

from typing import Any, Final

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


def build_feeding_compliance_notification(
    language: str | None,
    *,
    display_name: str,
    compliance: dict[str, Any],
) -> tuple[str, str | None]:
    """Return localised title and body for a feeding compliance result."""

    translations = get_feeding_compliance_translations(language)
    status = compliance.get("status")

    if status != "completed":
        message = str(compliance.get("message") or translations["no_data_fallback"])
        title = translations["no_data_title"].format(display_name=display_name)
        return title, message

    score = float(compliance.get("compliance_score", 0))
    days_analyzed = int(compliance.get("days_analyzed", 0))
    lines: list[str] = [
        translations["score_line"].format(score=score, days_analyzed=days_analyzed)
    ]

    missed_meals = compliance.get("missed_meals") or []
    if missed_meals:
        lines.append(translations["missed_meals_header"])
        lines.extend(
            "- "
            + translations["missed_meal_item"].format(
                date=entry.get("date", "unknown"),
                actual=entry.get("actual", "?"),
                expected=entry.get("expected", "?"),
            )
            for entry in missed_meals[:3]
        )

    issues = compliance.get("compliance_issues") or []
    if issues:
        lines.append(translations["issues_header"])
        for issue in issues[:3]:
            description = ""
            if issue.get("issues"):
                description = str(issue["issues"][0])
            else:
                description = str(issue.get("severity", "issue"))
            lines.append(
                "- "
                + translations["issue_item"].format(
                    date=issue.get("date", "unknown"),
                    description=description,
                )
            )

    recommendations = compliance.get("recommendations") or []
    if recommendations:
        lines.append(translations["recommendations_header"])
        lines.extend(
            "- "
            + translations["recommendation_item"].format(recommendation=recommendation)
            for recommendation in recommendations[:2]
        )
    elif issues or missed_meals:
        lines.append(translations["recommendations_header"])
        lines.append(f"- {translations['no_recommendations']}")

    title = translations["alert_title"].format(display_name=display_name)
    message = "\n".join(lines) if lines else None
    return title, message
