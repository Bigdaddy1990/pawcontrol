"""Report generator for Paw Control integration."""

from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from typing import Any

try:
    from typing import TypeAlias
except ImportError:
    # Python < 3.10 compatibility
    TypeAlias = type

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import (
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOGS,
    CONF_EXPORT_PATH,
)

_LOGGER = logging.getLogger(__name__)

ReportData: TypeAlias = dict[str, Any]


class ReportGenerator:
    """Generate reports for Paw Control."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        coordinator: Any | None = None,
    ) -> None:
        """Initialize report generator.

        Earlier versions of the integration accessed ``entry.runtime_data``
        during initialisation which is not yet populated at this stage of the
        setup process.  The tests construct the ``ReportGenerator`` before the
        runtime data is attached to the config entry which previously resulted
        in an ``AttributeError``.  Accepting an optional coordinator allows the
        caller to provide it directly while still falling back to the runtime
        data when available.
        """

        self.hass = hass
        self.entry = entry
        # Store the coordinator if provided; otherwise lazily resolve it from
        # the config entry when accessed via the ``coordinator`` property.  This
        # ensures that the report generator still works when constructed before
        # ``runtime_data`` is attached to the config entry.
        self._coordinator: PawControlCoordinator | None = coordinator  # noqa: F821

    @property
    def coordinator(self) -> PawControlCoordinator | None:  # noqa: F821
        """Return the data coordinator.

        When the report generator is created before ``runtime_data`` is
        attached to the config entry, the coordinator may not yet be available.
        Accessing it via this property allows us to fall back to the coordinator
        provided in ``runtime_data`` once it becomes available.
        """

        if self._coordinator is not None:
            return self._coordinator

        return getattr(getattr(self.entry, "runtime_data", None), "coordinator", None)

    async def generate_report(
        self,
        scope: str = "daily",
        target: str = "notification",
        format_type: str = "text",
    ) -> bool:
        """Generate a report based on scope and target."""
        try:
            # Gather report data
            report_data = await self._gather_report_data(scope)

            if target == "notification":
                # Send as notification
                await self._send_notification_report(report_data, scope)
            elif target == "file":
                # Save to file
                await self._save_file_report(report_data, scope, format_type)

            return True

        except Exception as err:
            _LOGGER.error(f"Failed to generate report: {err}")
            return False

    async def _gather_report_data(self, scope: str) -> ReportData:
        """Gather data for report generation."""
        dogs = self.entry.options.get(CONF_DOGS, [])
        report_data = {
            "generated_at": dt_util.now().isoformat(),
            "scope": scope,
            "dogs": {},
        }

        coordinator = self.coordinator
        if coordinator is None:
            _LOGGER.warning("No coordinator available when generating report")
            return report_data

        for dog in dogs:
            dog_id = dog.get(CONF_DOG_ID)
            if not dog_id:
                continue

            dog_name = dog.get(CONF_DOG_NAME, dog_id)
            try:
                dog_data = coordinator.get_dog_data(dog_id)
            except AttributeError:
                _LOGGER.debug("Coordinator missing get_dog_data when generating report")
                continue

            # Compile statistics
            dog_report = {
                "name": dog_name,
                "walk": {
                    "walks_today": dog_data.get("walk", {}).get("walks_today", 0),
                    "total_distance": dog_data.get("walk", {}).get(
                        "total_distance_today", 0
                    ),
                    "last_walk": dog_data.get("walk", {}).get("last_walk"),
                    "needs_walk": dog_data.get("walk", {}).get("needs_walk", False),
                },
                "feeding": {
                    "breakfast": dog_data.get("feeding", {})
                    .get("feedings_today", {})
                    .get("breakfast", 0),
                    "lunch": dog_data.get("feeding", {})
                    .get("feedings_today", {})
                    .get("lunch", 0),
                    "dinner": dog_data.get("feeding", {})
                    .get("feedings_today", {})
                    .get("dinner", 0),
                    "snacks": dog_data.get("feeding", {})
                    .get("feedings_today", {})
                    .get("snack", 0),
                    "total_portions": dog_data.get("feeding", {}).get(
                        "total_portions_today", 0
                    ),
                    "is_hungry": dog_data.get("feeding", {}).get("is_hungry", False),
                },
                "health": {
                    "weight": dog_data.get("health", {}).get("weight_kg", 0),
                    "medications_given": dog_data.get("health", {}).get(
                        "medications_today", 0
                    ),
                    "last_medication": dog_data.get("health", {}).get(
                        "last_medication"
                    ),
                },
                "grooming": {
                    "needs_grooming": dog_data.get("grooming", {}).get(
                        "needs_grooming", False
                    ),
                    "last_grooming": dog_data.get("grooming", {}).get("last_grooming"),
                },
                "activity": {
                    "play_time": dog_data.get("activity", {}).get(
                        "play_duration_today_min", 0
                    ),
                    "training_sessions": dog_data.get("training", {}).get(
                        "training_sessions_today", 0
                    ),
                    "activity_level": dog_data.get("activity", {}).get(
                        "activity_level", "medium"
                    ),
                    "calories_burned": dog_data.get("activity", {}).get(
                        "calories_burned_today", 0
                    ),
                },
                "statistics": {
                    "poop_count": dog_data.get("statistics", {}).get(
                        "poop_count_today", 0
                    ),
                    "last_action": dog_data.get("statistics", {}).get("last_action"),
                },
            }

            report_data["dogs"][dog_id] = dog_report

        return report_data

    async def _send_notification_report(
        self, report_data: ReportData, scope: str
    ) -> None:
        """Send report as notification."""
        router = self.entry.runtime_data.notification_router

        # Format report as text
        title = f"🐾 Paw Control {scope.capitalize()} Report"
        message = self._format_text_report(report_data)

        await router.send_notification(
            title=title,
            message=message,
            category="report",
            priority="normal",
            tag=f"pawcontrol_report_{scope}_{dt_util.now().strftime('%Y%m%d')}",
        )

    async def _save_file_report(
        self, report_data: ReportData, scope: str, format_type: str
    ) -> None:
        """Save report to file."""
        export_path = self.entry.options.get(CONF_EXPORT_PATH)

        if not export_path:
            _LOGGER.warning("No export path configured")
            return

        # Create directory if it doesn't exist
        path = Path(export_path)
        path.mkdir(parents=True, exist_ok=True)

        # Generate filename
        timestamp = dt_util.now().strftime("%Y%m%d_%H%M%S")
        filename = f"pawcontrol_{scope}_report_{timestamp}.{format_type}"
        filepath = path / filename

        try:
            if format_type == "json":
                await self._save_json_report(filepath, report_data)
            elif format_type == "csv":
                await self._save_csv_report(filepath, report_data)
            elif format_type == "pdf":
                # PDF generation would require additional libraries
                _LOGGER.warning("PDF export not yet implemented")
                await self._save_text_report(filepath.with_suffix(".txt"), report_data)
            else:
                await self._save_text_report(filepath, report_data)

            _LOGGER.info(f"Report saved to {filepath}")

        except Exception as err:
            _LOGGER.error(f"Failed to save report: {err}")

    async def _save_json_report(self, filepath: Path, report_data: ReportData) -> None:
        """Save report as JSON.

        File I/O is executed in the executor to avoid blocking the event loop.
        """

        def _write_json() -> None:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(report_data, f, indent=2, ensure_ascii=False, default=str)

        await self.hass.async_add_executor_job(_write_json)

    async def _save_csv_report(self, filepath: Path, report_data: ReportData) -> None:
        """Save report as CSV.

        File I/O is executed in the executor to avoid blocking the event loop.
        """

        def _write_csv() -> None:
            with open(filepath, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)

                # Write header
                writer.writerow(
                    [
                        "Dog Name",
                        "Walks Today",
                        "Distance (m)",
                        "Breakfast",
                        "Lunch",
                        "Dinner",
                        "Snacks",
                        "Medications",
                        "Play Time (min)",
                        "Training Sessions",
                        "Activity Level",
                        "Calories Burned",
                        "Poop Count",
                    ]
                )

                # Write data for each dog
                for _dog_id, dog_data in report_data["dogs"].items():
                    writer.writerow(
                        [
                            dog_data["name"],
                            dog_data["walk"]["walks_today"],
                            dog_data["walk"]["total_distance"],
                            dog_data["feeding"]["breakfast"],
                            dog_data["feeding"]["lunch"],
                            dog_data["feeding"]["dinner"],
                            dog_data["feeding"]["snacks"],
                            dog_data["health"]["medications_given"],
                            dog_data["activity"]["play_time"],
                            dog_data["activity"]["training_sessions"],
                            dog_data["activity"]["activity_level"],
                            dog_data["activity"]["calories_burned"],
                            dog_data["statistics"]["poop_count"],
                        ]
                    )

        await self.hass.async_add_executor_job(_write_csv)

    async def _save_text_report(self, filepath: Path, report_data: ReportData) -> None:
        """Save report as text.

        File I/O is executed in the executor to avoid blocking the event loop.
        """

        def _write_text() -> None:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(self._format_text_report(report_data))

        await self.hass.async_add_executor_job(_write_text)

    def _format_text_report(self, report_data: ReportData) -> str:
        """Format report data as text."""
        lines = []
        lines.append(f"Report Generated: {report_data['generated_at']}")
        lines.append(f"Scope: {report_data['scope'].capitalize()}")
        lines.append("=" * 50)

        for _dog_id, dog_data in report_data["dogs"].items():
            lines.append(f"\n🐕 {dog_data['name']}")
            lines.append("-" * 30)

            # Walk statistics
            lines.append(f"🚶 Walks: {dog_data['walk']['walks_today']}")
            lines.append(f"   Distance: {dog_data['walk']['total_distance']}m")
            if dog_data["walk"]["needs_walk"]:
                lines.append("   ⚠️ Needs walk!")

            # Feeding statistics
            meals = dog_data["feeding"]
            lines.append(
                f"🍽️ Meals: B:{meals['breakfast']} L:{meals['lunch']} D:{meals['dinner']} S:{meals['snacks']}"
            )
            lines.append(f"   Total portions: {meals['total_portions']}g")
            if meals["is_hungry"]:
                lines.append("   ⚠️ Is hungry!")

            # Health statistics
            health = dog_data["health"]
            lines.append(f"💊 Medications given: {health['medications_given']}")
            if health["weight"] > 0:
                lines.append(f"   Weight: {health['weight']}kg")

            # Activity statistics
            activity = dog_data["activity"]
            lines.append(f"🎾 Activity: {activity['activity_level']}")
            lines.append(f"   Play time: {activity['play_time']} min")
            lines.append(f"   Training sessions: {activity['training_sessions']}")
            lines.append(f"   Calories burned: {activity['calories_burned']} kcal")

            # Other statistics
            lines.append(f"💩 Poop count: {dog_data['statistics']['poop_count']}")

            # Grooming
            if dog_data["grooming"]["needs_grooming"]:
                lines.append("   ⚠️ Needs grooming!")

        return "\n".join(lines)

    async def export_health_data(
        self, dog_id: str, date_from: str, date_to: str, format_type: str = "csv"
    ) -> bool:
        """Export health data for a specific dog."""
        try:
            dog_data = self.coordinator.get_dog_data(dog_id)

            if not dog_data:
                _LOGGER.error(f"Dog {dog_id} not found")
                return False

            export_path = self.entry.options.get(CONF_EXPORT_PATH)
            if not export_path:
                _LOGGER.warning("No export path configured")
                return False

            # Create directory if it doesn't exist
            path = Path(export_path)
            path.mkdir(parents=True, exist_ok=True)

            # Generate filename
            timestamp = dt_util.now().strftime("%Y%m%d_%H%M%S")
            filename = f"pawcontrol_{dog_id}_health_{timestamp}.{format_type}"
            filepath = path / filename

            # Prepare health data
            health_export = {
                "dog_id": dog_id,
                "export_date": dt_util.now().isoformat(),
                "date_range": {"from": date_from, "to": date_to},
                "health_data": {
                    "current_weight": dog_data.get("health", {}).get("weight_kg", 0),
                    "weight_trend": dog_data.get("health", {}).get("weight_trend", []),
                    "medications": dog_data.get("health", {}).get(
                        "medication_history", []
                    ),
                    "health_notes": dog_data.get("health", {}).get("health_notes", []),
                },
                "grooming_history": dog_data.get("grooming", {}).get(
                    "grooming_history", []
                ),
                "training_history": dog_data.get("training", {}).get(
                    "training_history", []
                ),
            }

            if format_type == "json":

                def _write_json() -> None:
                    with open(filepath, "w", encoding="utf-8") as f:
                        json.dump(
                            health_export, f, indent=2, ensure_ascii=False, default=str
                        )

                await self.hass.async_add_executor_job(_write_json)
            elif format_type == "csv":
                # For CSV, create a simpler format
                def _write_csv() -> None:
                    with open(filepath, "w", newline="", encoding="utf-8") as f:
                        writer = csv.writer(f)
                        writer.writerow(["Date", "Type", "Value", "Notes"])

                        # Write weight trends
                        for weight_entry in health_export["health_data"][
                            "weight_trend"
                        ]:
                            writer.writerow(
                                [
                                    weight_entry.get("date", ""),
                                    "Weight",
                                    weight_entry.get("weight", ""),
                                    "",
                                ]
                            )

                        # Write health notes
                        for note in health_export["health_data"]["health_notes"]:
                            writer.writerow(
                                [
                                    note.get("date", ""),
                                    "Health Note",
                                    "",
                                    note.get("note", ""),
                                ]
                            )

                await self.hass.async_add_executor_job(_write_csv)

            _LOGGER.info(f"Health data exported to {filepath}")
            return True

        except Exception as err:
            _LOGGER.error(f"Failed to export health data: {err}")
            return False
