"""Unit tests for feeding compliance localisation helpers."""

from __future__ import annotations

from custom_components.pawcontrol.feeding_translations import (
    build_feeding_compliance_notification,
    get_feeding_compliance_translations,
)


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
    assert "Missed meals:" in message_en
    assert "Next steps:" in message_en
    assert "Buddy" in title_en

    title_de, message_de = build_feeding_compliance_notification(
        "de", display_name="Buddy", compliance=compliance
    )
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
    assert "No telemetry available" in message
